# TASK-18 — Testes de saturação e estabilidade

## Objetivo

Executar **três clientes simultâneos**, aumentar a quantidade de sinais por
cliente e identificar gargalos dos servidores Python e C++ por meio de dados
observados. A implementação reutiliza a fila limitada da TASK-15, a coleta
de CPU/RSS e histórico da TASK-16 e as tabelas comparativas da TASK-17.

**Importante:** os testes de unidade/integração com servidor simulado validam o
*executor*. Não substituem os benchmarks dos **dois servidores reais**. O
critério de aceite da TASK-18 depende de anexar os resultados efetivamente
medidos (sem inventar números) e de registrar as limitações observadas.

## Estratégia

- Em cada etapa, iniciar **um processo novo** do servidor para não misturar
  contadores/tempo de aquecimento e garantir que `queue_peak` seja específico
  do cenário.
- Fixar 3 clientes, com largada sincronizada por barreira, identificadores
  únicos de cliente e sinal; cada cliente envia `N` sinais, para `N=15,30,60`
  (respectivamente 45, 90 e 180 requisições totais).
- Usar **o mesmo modelo, sinal, algoritmo, critérios de parada, número de
  workers e capacidade de fila** nos servidores Python e C++.
- Registrar HTTP `202` como trabalho aceito e HTTP `503/QUEUE_FULL` como
  mecanismo de saturação **esperado**, que não indica perda de trabalho aceito.
- Ao final dos envios, consultar `GET /queue` até não haver tarefas pendentes
  e `completed_count + failed_count` alcançar o número aceito (ou atingir
  `--drain-timeout`). Conferir a integridade dos IDs, o endpoint `/health`
  e os contadores. Persistir a diferença entre tentativas, aceites, rejeições,
  falhas de processamento e falhas inesperadas de rede/HTTP.
- Em paralelo, o `Collector` da TASK-16 registra CPU, RAM, fila e tempos de
  reconstrução. Se a janela de coleta fechar cedo, o ensaio será marcado como
  **incompleto** (`workload_complete=false`), em vez de publicar uma vazão
  enganosa. Aumentar `--monitor-seconds` para ensaios longos.
- O CSV de reconstruções é conservado pelo servidor até terminar a medição:
  o executor configura automaticamente `max-retained-results` para cobrir
  a maior carga (respeitando o máximo configurável pelo servidor).

## Pré-requisitos

Na raiz do projeto, com as TASK-12, 13, 15, 16 e 17 integradas:

```bash
uv sync --locked
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build -j
```

É necessário que a porta local esteja disponível e que o arquivo executável
`build/reconstruction_server` exista. O executor inicia servidores em portas
livres de `127.0.0.1`; **não execute manualmente** Uvicorn ou C++ ao mesmo tempo.
Usa um processo Uvicorn apenas (não `uvicorn --workers N`) e controla a
quantidade de workers **internos** de CGNR pela TASK-15. As variáveis
`OPENBLAS_NUM_THREADS=1` e `OMP_NUM_THREADS=1` são aplicadas aos dois.

## Execução 1 — verificar controle de carga

A matriz `demo_identity_3` (3 × 3) serve para verificar protocolo,
concorrência, rejeições e confiabilidade, mas é **pequena demais para medir
um limite real de CPU**. Executar o cenário leve:

```bash
uv run python -m monitoring.saturation \
  --implementations python cpp \
  --levels 15 30 60 \
  --workers 1 --queue-capacity 8 \
  --monitor-seconds 3 --drain-timeout 20
```

Não observar `QUEUE_FULL` com esta matriz **não é falha**: ela pode ser
processada mais rapidamente do que os clientes conseguem enfileirar.

## Execução 2 — modelo sintético denso, carga progressiva

Para induzir trabalho numérico controlado e reproduzível, gerar **uma única
matriz CSV** e um sinal JSON, compartilhados pelos dois servidores:

```bash
uv run python -m monitoring.generate_task18_fixture \
  --size 512 --seed 18 --output results/task18-fixture

uv run python -m monitoring.saturation \
  --implementations python cpp \
  --catalog results/task18-fixture/models/catalog.json \
  --model-id task18_dense_512 \
  --signal-file results/task18-fixture/signal.json \
  --levels 15 30 60 \
  --workers 1 --queue-capacity 8 \
  --monitor-seconds 30 --drain-timeout 60 \
  --sample-interval 0.025
```

A matriz sintética é densa e bem condicionada, mas **não equivale às matrizes
experimentais reais**. Se não houver saturação, testar maior dimensão (por
exemplo `--size 1024`) ou capacidade de fila menor (`--queue-capacity 2`),
registrando a configuração modificada para permitir reprodução.

Se o exame real exigir outra quantidade de elementos, criar um catálogo
compatível e fornecer um `--signal-file` JSON com exatamente um número finito
por linha da matriz. O mesmo arquivo é enviado para as duas linguagens.

## Arquivos produzidos

Cada invocação usa uma pasta própria `results/saturation/run-<timestamp>/`,
para não sobrescrever ou misturar resultados de execuções anteriores.
Também é possível escolher uma pasta **vazia** com `--output DIR`.

```text
results/saturation/run-<timestamp>/
├── report.md                 # resumo e indícios de gargalos
├── report.csv                # indicadores por implementação/carga
├── report.json               # ambiente, configuração e indicadores
├── comparisons/
│   ├── signals-15-per-client/ # tabelas TASK-17 quando ambos executados
│   ├── signals-30-per-client/
│   └── signals-60-per-client/
├── python/
│   ├── signals-15-per-client/
│   │   ├── server.log
│   │   ├── requests.csv      # resposta/latência de cada envio
│   │   ├── scenario.json     # contadores, integridade e hipóteses
│   │   ├── samples.csv       # coleta TASK-16: CPU, RSS, fila
│   │   ├── reconstructions.csv
│   │   └── summary.json      # janela/estatísticas TASK-16
│   └── ...
└── cpp/
    └── ...
```

### Leitura e interpretação

| Indicador | Interpretação |
| --- | --- |
| `queue_peak` | pico exato observado pelo controle da fila desde a inicialização (uma inicialização por cenário) |
| `queue_peak_sampled` | pico amostrado pelo coletor; pode perder picos muito rápidos |
| `queue_full_http_503` | requisições rejeitadas intencionalmente por saturação |
| `server_accepted_delta` | total aceito segundo o servidor; deve coincidir com os HTTP 202 válidos |
| `server_finished_delta` | concluídas + falhas após a carga; deve coincidir com o total aceito após drenagem |
| `server_failed_delta` | falhas de cálculo/processamento, não confundidas com rejeições na fila |
| `peak_cpu_percent` | CPU percentual por núcleo lógico; pode superar 100% em múltiplos núcleos |
| `peak_memory_rss_bytes` / `rss_growth_bytes` | pico e variação de RSS observados, **não** prova de vazamento de memória |
| `workload_complete` | coleta cobriu todos os registros necessários para o cálculo completo da TASK-16 |
| `stable` | servidor vivo/saudável, sem falhas inesperadas e sem perda de tarefas aceitas no prazo |

Uma fila cheia, tempo médio ou RSS crescente **não prova** qual recurso é o
único gargalo. Comparar tendências de vazão com o aumento da carga, CPU e
RSS, verificar se `QUEUE_FULL` cresce e repetir o ensaio em ambiente
controlado. Os resultados C++ e Python devem ser analisados apenas para a
**mesma carga e modelo**. O utilitário da TASK-17 é aplicado separadamente
por nível, nunca misturando 45, 90 e 180 solicitações em uma comparação só.

### Como preencher a conclusão empírica do PR

Após executar os dois servidores, anexar/commitar o relatório real, a
configuração e os CSVs relevantes; completar o quadro abaixo com **os seus**
valores, sem copiar números hipotéticos:

**Atenção:** o projeto ignora `results/` no `.gitignore`. Para incluir ao
menos a conclusão no PR, copie o `report.md` produzido para um caminho
rastreável, por exemplo:

```bash
mkdir -p docs/tests/results
cp results/saturation/run-<timestamp>/report.md \
  docs/tests/results/task-18-benchmark-local.md
git add docs/tests/results/task-18-benchmark-local.md
```

Substitua `<timestamp>` pelo diretório realmente gerado; registre nele
também a configuração da máquina e as limitações identificadas. Não use
`git add -f results/` indiscriminadamente, pois os CSVs e matrizes
experimentais podem ser grandes.

| Cenário | Python: 503 | C++: 503 | Pico da fila Python/C++ | CPU e RSS | Estabilidade |
| --- | --- | --- | --- | --- | --- |
| 3 × 15 | A medir | A medir | A medir | A medir | A medir |
| 3 × 30 | A medir | A medir | A medir | A medir | A medir |
| 3 × 60 | A medir | A medir | A medir | A medir | A medir |

Ao discutir gargalos, registrar se houve rejeições, queda/estabilização de
vazão, crescimento da fila, CPU alta ou aumento de memória, além de condições
experimentais (CPU, RAM, SO, tamanho da matriz e threads BLAS).

**Política de retenção TASK-15:** resultados antigos podem retornar HTTP 404
após expiração; o executor aumenta a retenção por ensaio para reduzir esse
risco. Se o coletor informar `workload_complete=false`, aumentar também
`--monitor-seconds` e conferir `reconstruction_rows_exported`.

## Testes automatizados do executor

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  uv run python -m pytest tests/integration/test_task18_saturation.py -v
```

Estes testes verificam: entrada/configuração inválida, geração determinística
da matriz, 3 clientes com envio simultâneo, 45 sinais nos servidores reais,
consistência de métricas TASK-16, saturação em um servidor simulado com
worker atrasado, integridade dos aceites e gravação dos arquivos. O teste
C++ real é ignorado **somente quando o executável não existe**. O teste
simulado não é usado como resultado de desempenho real.

Para garantir a integridade da fila em cenários controlados também podem ser
executados os testes já existentes da TASK-15:

```bash
uv run python -m pytest \
  tests/unit/test_task15_queue_control.py \
  tests/unit/test_task15_service.py \
  tests/integration/test_task15_cpp_queue.py -v
```
