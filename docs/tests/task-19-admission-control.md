# TASK-19 — Ajuste de concorrência e controle de saturação

## Motivação: evidência real da TASK-18

A versão de referência da TASK-18, registrada em
`docs/tests/results/task-18/report.json`, usou matriz sintética densa
`task18_dense_512`, três clientes sincronizados, um worker, fila FIFO com
capacidade de 2 tarefas pendentes, sem intervalo artificial entre POSTs.
O ambiente documentado era Linux/WSL2, com 16 CPUs lógicas e cerca de 8 GB de RAM.

| Tentativas | Python 202 / 503 | C++ 202 / 503 |
| ---: | ---: | ---: |
| 45 | 6 / 39 | 44 / 1 |
| 90 | 11 / 79 | 89 / 1 |
| 180 | 19 / 161 | 179 / 1 |

Os dois servidores concluíram suas tarefas **aceitas** e permaneceram estáveis.
Os `503` eram backpressure, não perda de `202`. A quantidade de aceites não é,
por si só, vazão; depende da velocidade dos POSTs, da fila e do processamento.
Não inferir eficiência geral a partir dessa única campanha.

## Alteração técnica

Os dois servidores continuam com **fila FIFO limitada**, workers configuráveis
(TASK-15) e instrumentação de métricas (TASK-16). A TASK-19 acrescenta um teto
**atômico de tarefas em voo**, incluindo `queued` **e** `running`:

```
inflight = accepted_count - completed_count - failed_count
aceitar POST somente se inflight < max_inflight e fila não estiver cheia
```

No Python, o contador de tarefas em voo é atualizado sob `ReconstructionService.lock`
no ato do aceite e da conclusão. Ele não depende do tamanho instantâneo de
`queue.Queue`, evitando uma janela de corrida durante a retirada por um worker.
No C++, a decisão e os contadores são atualizados sob `mutex_`.

Um POST válido recusado recebe **HTTP 503**, `error.code=QUEUE_FULL` e cabeçalho
`Retry-After: 1`. O cabeçalho é uma recomendação mínima ao cliente, **não** uma
promessa de que haverá capacidade após um segundo. Não há descarte de tarefas
aceitas, não há espera ilimitada no POST e não há fila de tamanho ilimitado.

O valor padrão é `max_inflight = workers + queue_capacity`, preservando o limite
existente na TASK-15. Um valor menor reduz o total de tarefas pendentes e ativas
sem exigir uma alteração no limite físico da fila. Configurações inválidas são
rejeitadas na inicialização: `1 <= max_inflight <= workers + queue_capacity`.

O endpoint **GET `/queue`** agora inclui os mesmos campos em ambos os servidores:

- `admission_limit`: teto de trabalhos aceitos e ainda não finalizados;
- `inflight_count`: trabalhos `queued` + `running` ainda não finalizados;
- `admission_rejected_count`: subconjunto dos `rejected_count` recusado pelo
  teto de admissão.

Os demais campos e o contrato dos endpoints da TASK-15 são mantidos. Contadores
da TASK-16 são vitalícios e não diminuem após remoção de resultados antigos.

### Executar o servidor Python

```bash
RECONSTRUCTION_WORKERS=2 \
RECONSTRUCTION_QUEUE_CAPACITY=8 \
RECONSTRUCTION_MAX_INFLIGHT=6 \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run uvicorn server.python.reconstruction_server:app --host 127.0.0.1 --port 8000
```

### Executar o servidor C++

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build -j
./build/reconstruction_server --workers 2 --queue-capacity 8 --max-inflight 6
```

A quantidade de workers CGNR não é equivalente ao número total de threads do
processo. Também há threads da biblioteca HTTP e, potencialmente, de BLAS.

## Reexecutar e comparar antes/depois

**Obrigatório para concluir a issue:** o experimento precisa ser realizado na
máquina do projeto. Os resultados desta seção não são previsões do desempenho.

Gerar o mesmo modelo denso da TASK-18 (seed 18):

```bash
uv run python -m monitoring.generate_task18_fixture \
  --size 512 --seed 18 --output results/task19-fixture
```

Executar duas configurações, com **três clientes**, as mesmas cargas (45, 90,
180 tentativas), modelo, sinal, parâmetros CGNR e threads BLAS. Cada combinação
usa um processo novo:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run python -m monitoring.task19_compare \
  --catalog results/task19-fixture/models/catalog.json \
  --model-id task18_dense_512 \
  --signal-file results/task19-fixture/signal.json \
  --levels 15 30 60 \
  --workers-before 1 --queue-before 2 --max-inflight-before 3 \
  --workers-after 2 --queue-after 8 --max-inflight-after 6 \
  --monitor-seconds 30 --drain-timeout 90 \
  --repeats 2 \
  --output results/task19/before-after
```

`--repeats 2` executa dois pares por carga; para repetir em uma outra execução,
use um novo diretório. A configuração exemplo modifica **três parâmetros**:
workers, capacidade física e teto de admissão, então não identifica o efeito
isolado de nenhum deles. Para isolar a política de admissão, compare duas
configurações com os **mesmos** `workers` e `queue`, variando apenas
`max_inflight`. Considere também usar `--jitter-ms` constante nas duas versões
para estudar o comportamento sob diferentes ritmos de envio.

O comando gera `comparison.json`, `comparison.csv`, `comparison.md` e os cinco
arquivos brutos da TASK-16 por cenário, perfil, linguagem e repetição. Compare:

1. Rejeições 503 e proporção de aceites HTTP, sempre separadas das conclusões;
2. Fila máxima, tempo de espera efetivo e tarefas em andamento;
3. Conclusão de todos os `202`, ausência de erros inesperados, estabilidade;
4. Vazão em **ensaios completos**, duração de reconstrução, CPU e RSS;
5. Consistência das condições de hardware, matriz e configuração.

Se o coletor marcar `workload_complete=false`, aumente `--monitor-seconds` e
reexecute; não use aquela vazão. Um pico de CPU acima de 100% é possível porque
100% representa um núcleo lógico, com tempo de CPU somado do processo e filhos.

O relatório da TASK-18 é **baseline histórica**, não uma medição comparável a
uma campanha de TASK-19 executada em outra data, ambiente ou com outras
configurações. A comparação antes/depois é produzida **na mesma campanha**.

## Testes

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run python -m pytest \
  tests/unit/test_task19_admission.py \
  tests/unit/test_task19_comparison.py \
  tests/integration/test_task19_admission.py -v

uv run python -m pytest tests/unit/test_task15_queue_control.py \
  tests/unit/test_task15_service.py \
  tests/integration/test_task15_cpp_queue.py \
  tests/integration/test_task18_saturation.py -v
```

O teste C++ de admissão requer `build/reconstruction_server` compilado com
`BUILD_TESTING=ON` e usa o gancho já existente na TASK-13. Se o binário não
existir, o teste é ignorado; não significa que o C++ foi validado.

## Limitações

- Sem persistência de tarefas em encerramentos abruptos;
- O limite de admissão é estático, não um ajuste automático orientado a CPU/RAM;
- `Retry-After: 1` é uma indicação mínima, não agendamento nem garantia;
- A redução dos 503 não prova aceleração do CGNR; filas maiores podem elevar
  latência e memória;
- Ajustes de workers precisam ser avaliados com threads BLAS e CPU disponível;
- A conclusão da TASK-19 depende do relatório **medido** da nova campanha.

Depois da execução, registre o `comparison.md` e dados relevantes em
`docs/tests/results/task-19/`, sem colocar matrizes densas grandes no Git.
