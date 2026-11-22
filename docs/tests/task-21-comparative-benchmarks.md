# TASK-21 — Benchmarks comparativos Python e C++

## Objetivo e requisitos

Realizar medições **reproduzíveis** de tempo total, tempo médio de reconstrução,
CPU, memória RSS e tamanho da fila dos servidores Python e C++ com **exatamente
os mesmos sinais, modelo e parâmetros**. Esta task usa a infraestrutura já
implementada nas TASK-15/16/17/18, sem modificar os algoritmos CGNR.

A TASK-18 avaliou saturação e rejeição de pedidos; a TASK-21 avalia **desempenho de
uma carga inteiramente processada**. Misturar tempos de 6 aceites no Python e 44
aceites no C++ não constitui comparação justa. Portanto, `monitoring.benchmark`
marca ensaios com qualquer rejeição, falha, perda de registro, timeout ou
`workload_complete=false` como **não comparáveis**.

## Protocolo fixo

- **3 clientes** simultâneos, sincronizados no início de cada execução.
- Cargas **15, 30, 60 sinais por cliente** (45, 90 e 180 por implementação).
- **3 repetições por combinação** de carga e implementação (18 execuções).
- Mesma matriz, sinal base, máximo de 10 iterações CGNR e tolerância `1e-8`.
- Para cada cliente, sinais numéricos diferentes são gerados por variação
  determinística do vetor base, com `random.Random(seed)` e identificadores
  fixos. O mesmo `plan.json` é usado para **todas** as repetições e servidores;
  cada carga usa um prefixo imutável da sequência de cada cliente.
- `plan.json` contém todos os vetores e SHA-256 canônico; `--reuse-plan`
  permite reproduzir exatamente a mesma sequência e recusa arquivos alterados
  ou configurações incompatíveis.
- Para evitar viés por saturação, a fila precisa suportar pelo menos
  `3 × max(levels)` sinais; sugestão: capacidade **256**, **2 workers** em ambas
  as implementações. Configurar o limite de admissão da TASK-19 (se mesclada)
  para não bloquear a mesma carga. O teste recusa alterações no conjunto de
  sinais ou no tamanho do sinal.
- Cada repetição usa **um processo servidor novo**. A ordem de execução é
  alternada: Python/C++ na primeira repetição, C++/Python na segunda etc.
- Os envs `OPENBLAS_NUM_THREADS=1` e `OMP_NUM_THREADS=1` são aplicados aos
  servidores pelo lançador herdado da TASK-18. `uvicorn` usa um processo.
- A ordem é fixa **dentro de cada cliente**; a intercalação global entre
  clientes depende do agendador do sistema e não é determinística. Registrar
  a duração e repetir a medição reduz, mas não elimina, esse ruído.

## Preparação

Na raiz do projeto:

```bash
uv sync --locked
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build -j 4

uv run python -m monitoring.generate_task18_fixture \
  --size 512 --seed 18 --output results/task21-fixture
```

A matriz `task18_dense_512` é **sintética e densa**. Não deve ser apresentada
como representação geral das matrizes médicas reais.

## Execução de benchmark

Primeiro, apenas preparar e auditar o plano:

```bash
uv run python -m monitoring.benchmark \
  --catalog results/task21-fixture/models/catalog.json \
  --model-id task18_dense_512 \
  --signal-file results/task21-fixture/signal.json \
  --levels 15 30 60 --repeats 3 --workers 2 --queue-capacity 256 \
  --seed 21 --output results/task21/benchmark --plan-only
```

Depois executar as 18 medições com esse **mesmo** plano:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run python -m monitoring.benchmark \
  --catalog results/task21-fixture/models/catalog.json \
  --model-id task18_dense_512 \
  --signal-file results/task21-fixture/signal.json \
  --levels 15 30 60 --repeats 3 --workers 2 --queue-capacity 256 \
  --seed 21 --sample-interval 0.025 --drain-timeout 120 \
  --reuse-plan results/task21/benchmark/plan.json \
  --output results/task21/benchmark
```

O programa retorna código de saída **1** caso falte alguma execução ou alguma
carga não tenha todos os pares completos. Para cargas maiores, aumentar
`--drain-timeout` e conferir se o tempo de observação inclui todas as tarefas.
Não aumente a duração apenas em uma implementação. Reduzir o número de workers,
a capacidade da fila ou o limite de admissão pode voltar a produzir `503`, o que
torna a comparação inválida.

## Evidências produzidas

```
results/task21/benchmark/
├── plan.json                  # sinais, parâmetros e SHA-256
├── comparison.md              # tabela consolidada e metodologia
├── comparison.csv             # uma linha por carga
├── comparison.json            # configurações, ambiente e execuções
├── runs.csv                   # métricas por repetição
└── runs/
    ├── python/level-15/repeat-1/
    └── cpp/level-15/repeat-1/
        ├── requests.csv       # envios e latências HTTP
        ├── scenario.json      # validação da execução
        ├── summary.json       # coletor TASK-16
        ├── samples.csv        # CPU, RSS e fila por amostra
        ├── reconstructions.csv # reconstruções e tempos CGNR
        └── server.log
```

O programa gera um diretório para cada implementação/carga/repetição. Só os
pares com **todas** as requisições aceitas e finalizadas e exportações completas
entram nos cálculos. A consistência dos `request_id` e `signal_id` é verificada.

O comparador apresenta **mediana** das repetições válidas para duração total,
tempo médio por imagem, CPU média, pico de RSS e fila média. O speedup é
`mediana_tempo_Python / mediana_tempo_C++`: acima de 1 favorece C++.

- Tempo total: período do primeiro aceite à última conclusão, obtido por
  timestamps UTC exportados (resolução de milissegundos).
- Tempo CGNR médio: média interna por execução, depois mediana entre repetições;
  **não** é a duração total nem inclui espera HTTP.
- CPU: tempo de CPU usuário+sistema do processo **e filhos** sobre tempo de
  parede. **100% = 1 núcleo lógico**; acima de 100% não é erro. A média é
  ponderada pela duração entre amostras.
- RSS: máximo amostrado da soma da memória residente de processo e filhos;
  regiões compartilhadas podem ser contadas mais de uma vez.
- Fila: média ponderada por tempo entre amostras (retenção à esquerda), moda
  de tempo de fila e pico do endpoint `/queue` da TASK-15.
- Resultados muito curtos podem não permitir uma amostragem fina de recursos;
  usar matriz mais pesada, repetir e discutir esse limite. Não comparar a CPU
  em janelas de duração muito diferentes sem contextualização.

## Publicar os resultados no PR

A pasta `results/` é ignorada pelo Git. Depois de conferir os números reais:

```bash
mkdir -p docs/tests/task-21-evidence
cp results/task21/benchmark/{comparison.md,comparison.csv,comparison.json,runs.csv,plan.json} \
  docs/tests/task-21-evidence/
# Opcional: anexar os registros brutos por execução (não incluir arquivos grandes sem necessidade)
cp -r results/task21/benchmark/runs docs/tests/task-21-evidence/
git add docs/tests/task-21-evidence/ docs/tests/task-21-comparative-benchmarks.md
```

`docs/tests/task-21-evidence/` evita o padrão de exclusão de `results/` no
`.gitignore`. Não registre dados reais antes de executar os benchmarks na
máquina onde serão medidos. As evidências brutas também permitem gerar os
**gráficos da TASK-22**, por exemplo:

```bash
uv run python -m monitoring.plots \
  docs/tests/task-21-evidence/runs/python/level-15/repeat-1 \
  docs/tests/task-21-evidence/runs/cpp/level-15/repeat-1 \
  --output results/task21/plots
```

## Testes de regressão

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run python -m pytest \
  tests/unit/test_task21_benchmark.py \
  tests/integration/test_task21_benchmark_http.py \
  tests/integration/test_task21_real_servers.py -v
```

O teste HTTP usa um servidor **simulado** para verificar geração de plano,
protocolo, três clientes, métricas e rejeições. Os testes `real_servers` usam
as versões Python e C++ reais e exigem binário C++ compilado; se ausente, o
teste C++ é explicitamente ignorado. Fixtures artificiais não provam a
performance dos servidores.

## Observações sobre latência HTTP e tempo de reconstrução

Nas execuções publicadas, o Python apresentou menor tempo total de
processamento das cargas HTTP, enquanto o C++ apresentou menor tempo médio
de execução do CGNR.

Essas métricas representam etapas diferentes. O tempo total inclui o
comportamento da admissão HTTP, o ritmo de envio, o agendamento e a
conclusão dos trabalhos; o tempo médio do CGNR considera apenas a
reconstrução numérica registrada pelo servidor.

O cliente do benchmark utiliza três clientes concorrentes, mas cada
cliente aguarda a resposta de um POST antes de enviar o próximo.

Na primeira repetição da carga de 45 sinais, os registros de
`requests.csv` mostram aproximadamente 3,1 ms no primeiro POST do C++
e cerca de 43 ms em diversos POSTs seguintes. A duração total da fase
de envio foi de aproximadamente 620 ms para o C++, contra 49,5 ms
para o Python na mesma configuração experimental.

Esse padrão é compatível com uma possível influência da comunicação
HTTP/TCP e da reutilização de conexões, mas os dados disponíveis não
permitem identificar sua causa com certeza.

Portanto, os resultados demonstram o desempenho das implementações
sob o protocolo HTTP adotado, sem comprovar superioridade geral
de um algoritmo CGNR sobre o outro. Uma investigação futura pode
comparar conexões persistentes e não persistentes e diferentes
configurações de transporte.

## Critério de aceite

A TASK-21 só deve ser considerada concluída com **18 execuções reais**
(para os valores padrão) e arquivos de evidências publicados, com
`comparison.json` indicando `comparable=true` nas três cargas, ou com
limitações experimentais explicitamente documentadas e justificadas.
