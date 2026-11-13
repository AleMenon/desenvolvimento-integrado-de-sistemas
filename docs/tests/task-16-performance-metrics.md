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

A duração individual `execution_time_ms` corresponde apenas ao cálculo CGNR, **não** ao tempo de espera na fila, serialização JSON nem à comunicação. `total_execution_time_ms` no resumo é o intervalo entre a primeira requisição aceita e a última concluída dentro da janela (inclui espera na fila); `monitoring_window_ms` é o tempo em que o monitor ficou aberto. Se nenhuma requisição terminar, `total_execution_time_ms` será `null`. Para comparar um experimento, inicie o monitor antes dos envios e finalize-o depois da última conclusão. O total de imagens reconstruídas é `completed_count` (diferença do contador entre início e fim da observação), não o número de requisições recebidas.

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

## Python — integração na TASK-12

A implementação Python do servidor ainda não estava integrada à `main`/`task-13` no momento da TASK-16. O código a seguir **não substitui** o servidor da colega: são pontos de integração a aplicar onde a API, a fila e o executor forem definidos.

```python
from fastapi import FastAPI
from server.python.metrics_api import create_metrics_router
from server.python.performance_metrics import PerformanceMetrics

app = FastAPI()
metrics = PerformanceMetrics("python")
app.include_router(create_metrics_router(metrics))

# Após validar e inserir uma requisição na fila:
metrics.accepted(request_id, client_id, signal_id, model_id)

# Ao retirar da fila, antes do cálculo:
metrics.started(request_id)

# Ao finalizar o CGNR (reaproveite o tempo do algoritmo medido no servidor):
metrics.finished(request_id, success=True, iterations=result["iterations"],
                 converged=result["converged"],
                 stop_reason="tolerance_reached" if result["converged"] else "max_iterations",
                 execution_time_ms=elapsed_cgnr_ms)

# Em caso de erro, se já havia iniciado:
# metrics.finished(request_id, success=False, stop_reason="reconstruction_failed",
#                  execution_time_ms=elapsed_cgnr_ms)
```

**Importante:** não chame `accepted` antes de aceitar a requisição nem `started` antes de retirar a tarefa da fila. Os callbacks devem refletir **os mesmos eventos** utilizados para atualizar o estado HTTP do servidor. Não registre a mesma requisição duas vezes. Para falhas de validação rejeitadas antes do enfileiramento, não registre uma reconstrução. Para preservar o tempo exclusivo do algoritmo, meça `elapsed_cgnr_ms` com `time.perf_counter()` imediatamente ao redor de `cgnr()`.

Quando a TASK-12 estiver integrada, inicie esse servidor Python e use o **mesmo comando do coletor**, trocando `--url`, `--pid` e `--output results/metrics/python`.

## Arquivos exportados

`results/metrics/{cpp|python}/` conterá:

| Arquivo | Dados |
| --- | --- |
| `samples.csv` | horário, tempo decorrido, CPU %, RSS bytes, tamanho da fila, ativos, recebidos, concluídos e falhas |
| `reconstructions.csv` | IDs, estado, início, término, `execution_time_ms`, iterações, convergência e motivo da parada |
| `summary.json` | tempo total da carga e tempo da observação, imagens concluídas, falhas, média de reconstrução, picos de CPU/RSS, média e moda amostradas da fila |

**Comparabilidade:** executar uma implementação por vez na mesma máquina, fixando modelos, sinais, número de clientes, critérios de parada e número de threads BLAS (`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`). Usar o mesmo período de amostragem e incluir o tratamento da carga de trabalho inteira na janela. O monitor externo adiciona uma pequena carga de CPU às medições, mas não é incluído na CPU/RSS do PID do servidor.

As métricas ficam em memória no servidor; após reinício os contadores e registros voltam a zero. O cliente deve iniciar o monitor antes do ensaio e salvar o resultado antes de encerrar o servidor. `GET /metrics/reconstructions` recupera todas as tarefas desde o último início; o exportador filtra apenas as finalizadas na janela atual.

## Testes

```bash
uv run python -m pytest tests/unit/test_performance_metrics.py \
  tests/unit/test_python_metrics_api.py \
  tests/integration/test_metrics_collector.py -v

# Requer servidor C++ compilado:
uv run python -m pytest tests/integration/test_cpp_performance_metrics.py -v
```

Os testes Python cobrem estados/cálculos de fila, o router FastAPI e a exportação CSV/JSON para `implementation=python` e `cpp`. O teste C++ inicia o executável real, envia reconstruções e valida o export. **Os testes só comprovam equivalência real Python/C++ quando os dois servidores reais estiverem integrados e executados com a mesma carga.**
