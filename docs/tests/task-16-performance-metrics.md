# TASK-16 — Coleta de métricas de desempenho

## Contrato único: Python e C++

A instrumentação tem duas partes:

1. **Dentro do servidor:** eventos `accepted`, `started`, `finished` e estado da fila. O C++ da TASK-13 já está integrado. Para a implementação Python da TASK-12, há `PerformanceMetrics` e `create_metrics_router` prontos para integração.
2. **Fora do servidor:** `monitoring.collect` amostra CPU e RAM de um **PID** e seus processos filhos, consulta a mesma API HTTP e exporta os dados para CSV e JSON. O coletor é exatamente o mesmo nas duas linguagens.

Endpoints adicionais (não modificam o contrato de reconstrução da TASK-09):

- `GET /metrics` — `schema_version`, `implementation`, `timestamp_utc`, `uptime_ms`, `received_count`, `completed_count`, `failed_count`, `running_count`, `queue_size`, `queue_mean`, `queue_mode` e `mean_reconstruction_time_ms`.
- `GET /metrics/reconstructions` — lista de requisições com IDs, estado, horários, duração individual em ms, iterações e motivo de parada. **Não retorna imagens/vetores.**

Os horários são ISO 8601 UTC, as durações usam relógio **monotônico**, memória é medida em **bytes (RSS)** e CPU é porcentagem de **um núcleo lógico** (o processo com múltiplos núcleos pode passar de 100%). A memória soma o RSS do processo e de seus filhos; páginas compartilhadas podem ser contadas mais de uma vez. Aplicar o mesmo procedimento nas duas implementações.

A fila conta **somente requisições aguardando processamento**; tarefas em execução são contadas separadamente. `queue_mean` e `queue_mode` no endpoint são **ponderadas pelo tempo, desde o início do servidor**, inclusive períodos com fila vazia. No arquivo de resumo, `queue_mean_sampled` e `queue_mode_sampled` são estimativas baseadas nas amostras colhidas no ensaio, diferentes das estatísticas desde a inicialização.

A duração individual `execution_time_ms` corresponde apenas ao cálculo CGNR, **não** ao tempo de espera na fila, serialização JSON nem à comunicação. `total_execution_time_ms` no resumo é o intervalo entre a primeira requisição aceita e a última concluída dentro da janela (inclui espera na fila); `monitoring_window_ms` é o tempo em que o monitor ficou aberto. Se a janela terminar com tarefas ainda em andamento, começar com trabalhos já pendentes ou não contiver todos os registros de conclusão, `workload_complete` será `false`: `total_execution_time_ms` e `images_per_second` serão `null`, em vez de estimativas enganosas. Os contadores (`received_count`, `completed_count`, `failed_count`), as amostras e os registros de tarefas concluídas permanecem disponíveis. `inflight_at_start` e `unfinished_count_at_end` indicam a carga pendente nos dois extremos da janela. Se nenhuma requisição terminar, `total_execution_time_ms` também será `null`. Para comparar um experimento, inicie o monitor antes dos envios e finalize-o depois da última conclusão. O total de imagens reconstruídas é `completed_count` (diferença do contador entre início e fim da observação), não o número de requisições recebidas.

## C++ — executar

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/reconstruction_server --host 127.0.0.1 --port 8080 --catalog models/catalog.json &
SERVER_PID=$!
```

Em outro terminal, com o PID correto da execução acima:

```bash
uv sync --locked
uv run python -m monitoring.collect --url http://127.0.0.1:8080 \
  --pid "$SERVER_PID" --interval 0.1 --duration 30 \
  --output results/metrics/cpp
```

`$SERVER_PID` é uma variável do terminal onde o servidor foi iniciado. Se o coletor estiver em outro terminal, passe o PID numérico exibido por `echo "$SERVER_PID"`. Envie a carga de sinais durante esses 30 segundos, com o servidor ainda ativo. Sem `--duration`, interrompa o coletor com **Ctrl+C** depois do último resultado para salvar as métricas. Não encerre o servidor antes do export.

Para conferir as métricas diretamente:

```bash
curl -s http://127.0.0.1:8080/metrics | python -m json.tool
```

## Python — integração com a TASK-12

A instrumentação está integrada ao servidor Python real em
`server/python/reconstruction_server.py`.

A aplicação FastAPI expõe `GET /metrics` e
`GET /metrics/reconstructions`, reutilizando os componentes da TASK-16.

A instância de `PerformanceMetrics("python")` é compartilhada pelo
serviço de reconstrução e pelo router de métricas.

Eventos registrados:

1. `accepted`: somente após aceitação e inserção na fila.
2. `started`: quando o worker inicia o processamento.
3. `finished(success=True)`: reconstrução concluída.
4. `finished(success=False)`: falha numérica ou falha de execução.

Requisições inválidas ou rejeitadas pela fila não são contabilizadas.

O tempo `execution_time_ms` mede exclusivamente a chamada ao CGNR,
inclusive quando o algoritmo lança uma exceção.

O campo `stop_reason` utiliza o valor retornado pelo CGNR,
distinguindo `tolerance_reached`, `max_iterations` e
`numerical_breakdown`. Falhas genéricas recebem
`reconstruction_failed`.

A integração é verificada por testes HTTP reais em
`tests/integration/test_python_metrics_integration.py`.

A comparação experimental Python × C++ continua exigindo
executar ambos os servidores com a mesma carga, parâmetros
e condições de monitoramento.

## Arquivos exportados

`results/metrics/{cpp|python}/` conterá:

| Arquivo | Dados |
| --- | --- |
| `samples.csv` | horário, tempo decorrido, CPU %, RSS bytes, tamanho da fila, ativos, recebidos, concluídos e falhas |
| `reconstructions.csv` | IDs, estado, início, término, `execution_time_ms`, iterações, convergência e motivo da parada |
| `summary.json` | tempo total da carga e tempo da observação, imagens concluídas, falhas, média de reconstrução, picos de CPU/RSS, média e moda amostradas da fila |

**Comparabilidade:** executar uma implementação por vez na mesma máquina, fixando modelos, sinais, número de clientes, critérios de parada e número de threads BLAS (`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`). Usar o mesmo período de amostragem e incluir o tratamento da carga de trabalho inteira na janela. O monitor externo adiciona uma pequena carga de CPU às medições, mas não é incluído na CPU/RSS do PID do servidor.

As métricas ficam em memória no servidor; após reinício os contadores e registros voltam a zero. O cliente deve iniciar o monitor antes do ensaio e salvar o resultado antes de encerrar o servidor. `GET /metrics/reconstructions` recupera todas as tarefas desde o último início; o exportador filtra apenas as finalizadas na janela atual. Essa consulta detalhada é O(n) no número de trabalhos armazenados e deve ser usada preferencialmente ao finalizar o ensaio. Já `GET /metrics` atualiza seus contadores incrementalmente, sem percorrer todo o histórico, para reduzir o custo de amostragem. A expiração/paginação de registros permanece para a TASK-15.

## Testes

```bash
uv run python -m pytest tests/unit/test_performance_metrics.py \
  tests/unit/test_python_metrics_api.py \
  tests/integration/test_metrics_collector.py -v

# Requer servidor C++ compilado:
uv run python -m pytest tests/integration/test_cpp_performance_metrics.py -v
```

Os testes Python cobrem estados/cálculos de fila, o router FastAPI, janelas parciais e a exportação CSV/JSON para `implementation=python` e `cpp`. O teste C++ utiliza os hooks de teste da TASK-13 (`BUILD_TESTING=ON`) para criar uma fila real com cinco submissões concorrentes; as estatísticas `queue_mean`/`queue_mode` podem então ser verificadas sem depender da velocidade da matriz identidade. O teste C++ inicia o executável real, envia reconstruções e valida o export. **Os testes só comprovam equivalência real Python/C++ quando os dois servidores reais estiverem integrados e executados com a mesma carga.**

## Estado da integração e dependência de teste

**Comparação real ainda pendente:** o registro `PerformanceMetrics` e o router FastAPI estão prontos, mas a integração com o `worker` e a fila do servidor Python da TASK-12 deve ocorrer antes de um benchmark Python × C++ ponta a ponta. Testes com um servidor HTTP simulado provam compatibilidade do contrato, não equivalência experimental dos servidores reais.

A dependência de desenvolvimento `httpx2` é usada pelo `fastapi.testclient.TestClient` na versão instalada de Starlette (1.2+). O `httpx` tradicional continua possível em versões compatíveis, mas não satisfazia o erro de importação apresentado no ambiente de teste atual.

A TASK-16 foi desenvolvida sobre a TASK-13. Antes de concluir o PR, incorporar a TASK-13 atualizada à `main` e atualizar a branch `task-16`, preservando as instrumentações e os hooks de teste.
