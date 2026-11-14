# TASK-15 — Fila de reconstrução e controle de concorrência

## Política adotada

Os dois servidores usam fila **FIFO**, capacidade limitada e quantidade de workers
configurável. A API continua aceitando requisições válidas com HTTP **202**, devolvendo
`request_id`; pedidos que excedam a quantidade de tarefas **aguardando na fila** são
rejeitados com HTTP **503** e `error.code = QUEUE_FULL`, sem afetar tarefas já aceitas.

Por padrão há **1 worker**, **64 tarefas aguardando**, **1024 resultados finais retidos**
e retenção máxima de **3600 segundos**. O número de workers pode ir de 1 a 32.
Com dois workers e fila de capacidade 2, podem existir simultaneamente **duas**
reconstruções em execução e **duas** aguardando, totalizando quatro aceitas.
O limite de fila nunca conta tarefas em processamento.

Os dois servidores expõem **`GET /queue`**, com o mesmo formato de chaves:

| Campo | Significado |
| --- | --- |
| `implementation` | `python` ou `cpp` |
| `queue_policy` | `fifo` |
| `queue_capacity` | Limite de tarefas aguardando |
| `queue_size` | Tarefas aguardando agora |
| `queue_peak` | Maior tamanho de fila registrado desde a inicialização |
| `worker_count` | Total de workers configurados |
| `running_count` | Reconstruções atualmente executadas |
| `accepted_count` | Total de tarefas aceitas desde a inicialização |
| `completed_count` | Reconstruções concluídas com sucesso |
| `failed_count` | Reconstruções finalizadas com falha |
| `rejected_count` | Requisições rejeitadas por saturação da fila |
| `retained_results` | Registros terminados ainda consultáveis |
| `evicted_count` | Registros terminados removidos por expiração/limite |

Os contadores são acumulados desde a inicialização e **não diminuem** quando
um resultado expira. O pico se refere a observações de enfileiramento, não a
média ponderada de fila da TASK-16. Não são contadas como `rejected_count`
as entradas inválidas por validação HTTP.

## Retenção dos resultados

Somente trabalhos no estado `completed` ou `failed` são elegíveis à remoção.
A política descarta os **mais antigos primeiro** quando o total retido ultrapassa
`max_retained_results`, ou quando passam `result_ttl_seconds` da conclusão.
Um registro removido passa a responder **HTTP 404** nas consultas de status e resultado.
Requisições `queued` e `running` **não são descartadas** pela política.

A limpeza é realizada na conclusão e nas consultas/novos envios, sem uma thread
adicional. Por isso a memória não é reduzida exatamente no instante do TTL quando
o servidor está ocioso; ela é reduzida na próxima operação que aciona a limpeza.
Os arquivos de modelo continuam carregados na memória durante a execução.

### Integração com a TASK-14 — entrega das imagens

A retenção da TASK-15 é uma política de uso de memória, **não** um mecanismo de
entrega garantida de imagens. Após `POST /reconstructions` (HTTP 202), a TASK-14
deve acompanhar cada `request_id` até `completed` e buscar o resultado por
`GET /reconstructions/{request_id}/result` **antes** que a retenção o remova.
O cliente deve então salvar a imagem fora do servidor, em armazenamento próprio.

Depois da expiração ou da remoção por capacidade, tanto o status quanto o
resultado retornam HTTP **404** com `REQUEST_NOT_FOUND`. O cliente não consegue
recuperar a imagem por esse identificador: será necessário reenviar o sinal com
o mesmo modelo e parâmetros para uma nova reconstrução, se os dados originais
ainda estiverem disponíveis. Não há confirmação de entrega, armazenamento
persistente ou mecanismo de reprocessamento automático neste servidor.

Para uma rodada com **45 sinais por servidor**, sem outras requisições, configure
`max_retained_results` para pelo menos 45 e `result_ttl_seconds` para um valor
maior que o tempo entre a **primeira conclusão** e a **última recuperação** de
resultado. Para execuções compartilhadas, considere também os demais resultados
concluídos no intervalo. Mesmo com essa configuração, a TASK-14 deve consultar e
persistir os resultados prontamente; não espere o término de toda a carga com
retenção insuficiente.

### Relação com o coletor da TASK-16

Os contadores de `GET /metrics` continuam acumulados após a remoção de
resultados, mas `GET /metrics/reconstructions` lista apenas os registros ainda
retidos. Se a coleta terminar sem todos os registros esperados, o coletor da
TASK-16 identifica `workload_complete = false` e não produz um tempo total nem
uma vazão que pareçam representar a carga completa. Isso **não recupera** as
imagens descartadas. Para comparações completas, mantenha a retenção suficiente
até o fim da coleta e da recuperação de resultados.

## Execução Python

Configurar a instância Uvicorn por variáveis de ambiente:

```bash
RECONSTRUCTION_WORKERS=2 \
RECONSTRUCTION_QUEUE_CAPACITY=64 \
RECONSTRUCTION_MAX_RESULTS=1024 \
RECONSTRUCTION_RESULT_TTL_SECONDS=3600 \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run uvicorn server.python.reconstruction_server:app --host 127.0.0.1 --port 8000
```

Para testes, também é possível chamar `create_app(..., worker_count=2,
queue_capacity=2, max_retained_results=2, result_ttl_seconds=60)` ou criar o
`ReconstructionService` com os mesmos parâmetros.

**Importante:** os workers deste documento são *threads dentro de um processo*,
e não a opção `--workers` do Uvicorn (que inicia múltiplos processos independentes,
cada um com sua própria fila e contadores). Não combine os dois para obter uma fila
global compartilhada.

## Execução C++

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build -j
./build/reconstruction_server --host 127.0.0.1 --port 8080 \
  --catalog models/catalog.json --workers 2 --queue-capacity 64 \
  --max-retained-results 1024 --result-ttl-seconds 3600
```

Consultar em ambos:

```bash
curl -s http://127.0.0.1:8080/queue | python -m json.tool
curl -s http://127.0.0.1:8000/queue | python -m json.tool
```

## Encerramento e garantias

No encerramento **normal** do serviço Python (`shutdown()`) ou destruição do objeto
C++, novas tarefas deixam de ser aceitas e os workers terminam **todas as tarefas
já aceitas** antes de encerrar. A espera é potencialmente longa para matrizes grandes.

**Não existe persistência**: `SIGKILL`, queda de energia ou encerramento abrupto do
processo podem perder tarefas, mesmo que tenham retornado HTTP 202. O executável C++
ainda não gerencia explicitamente `SIGINT`/`SIGTERM` para efetuar desligamento
ordenado em nível de processo; `worker.join()` cobre o encerramento normal do objeto.
Para garantia durável seria necessário armazenamento persistente, fora do escopo.

## Testes

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run python -m pytest \
  tests/unit/test_task15_queue_control.py \
  tests/unit/test_task15_service.py \
  tests/integration/test_task15_cpp_queue.py -v
ctest --test-dir build --output-on-failure
```

Os testes verificam validação de configuração, saturação HTTP 503,
`running_count` limitado, tarefas pendentes preservadas, três clientes com
15 sinais cada, drenagem no encerramento normal, retenção FIFO de resultados e
mesmo formato/semântica de métricas entre Python e C++. No C++, a verificação de
concorrência usa a trava de teste disponibilizada pela TASK-13, exclusivamente
quando `BUILD_TESTING=ON`; assim o resultado não depende da duração da reconstrução.

Para comparações de desempenho da TASK-16, mantenha o **mesmo** número de workers,
mesmos parâmetros de fila, retenção e threads BLAS em ambas as implementações.
Os endpoints de métricas da TASK-16 devem usar contadores vitalícios e não o
tamanho do histórico retido de resultados.
