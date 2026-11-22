# TASK-18 — Resultados de saturação

Gerado em: `2026-11-19T19:20:49Z`.
Três clientes com largada sincronizada; um servidor novo por cenário.
Rejeição `503/QUEUE_FULL` = **backpressure intencional**; não é perda de uma tarefa aceita (`202`).

## Ambiente medido

- Sistema: `Linux-6.6.87.2-microsoft-standard-WSL2-x86_64-with-glibc2.43`
- Python: `3.12.16`
- CPUs lógicas: `16`
- RAM física total (bytes): `8172802048`

## Configuração do experimento

- Modelo: `task18_dense_512`; amostras por sinal: `512`
- Catálogo utilizado: `[external catalog] catalog.json`
- Cargas: `15, 30, 60` sinais por cliente × 3 clientes
- Workers internos por servidor: `1`; capacidade de espera: `2`
- Monitoramento: `30.0` s, amostragem: `0.025` s, drenagem: `90.0` s
- Intervalo aleatório entre envios: `0–0.0` ms
- CGNR: máximo de `10` iterações, tolerância `1e-08`
- BLAS: `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1` (definidos pelo executor para os processos iniciados)

Modelo `task18_dense_512`: matriz **sintética densa**, gerada de forma reproduzível (seed `18`). Não é uma matriz experimental real; seu custo depende da dimensão, algoritmo e parâmetros escolhidos.

## Medições por cenário

| implementation | signals_per_client | attempted | accepted_http_202 | queue_full_http_503 | queue_peak | peak_cpu_percent | peak_memory_rss_bytes | workload_complete | stable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| python | 15 | 45 | 6 | 39 | 2 | 234.1682733366133 | 62902272 | True | True |
| python | 30 | 90 | 11 | 79 | 2 | 714.9254591107086 | 63066112 | True | True |
| python | 60 | 180 | 19 | 161 | 2 | 381.773879011138 | 63168512 | True | True |
| cpp | 15 | 45 | 44 | 1 | 2 | 80.58891803657315 | 11796480 | True | True |
| cpp | 30 | 90 | 89 | 1 | 2 | 80.71647168065223 | 12451840 | True | True |
| cpp | 60 | 180 | 179 | 1 | 2 | 158.34606897407915 | 14024704 | True | True |

## Interpretação da taxa de aceitação

`accepted_http_202` conta **envios HTTP aceitos**, não imagens/s reconstruídas. O desempenho do CGNR, os workers disponíveis, a capacidade da fila e o intervalo entre POSTs afetam quantos envios recebem `202` antes que a fila fique cheia. Comparar somente cargas, modelos e configurações equivalentes. Sem múltiplas repetições, os valores não são uma conclusão geral de desempenho entre linguagens.

| Carga total | Python (202/503) | C++ (202/503) |
| ---: | ---: | ---: |
| 45 | 6 / 39 | 44 / 1 |
| 90 | 11 / 79 | 89 / 1 |
| 180 | 19 / 161 | 179 / 1 |

## Metodologia de CPU e memória

O coletor da TASK-16 soma o **tempo de CPU (usuário + sistema) do processo monitorado e dos processos filhos**; calcula, entre duas amostras, `CPU% = 100 × Δ(tempo de CPU) / Δ(tempo de parede)`. Por convenção, **100% equivale ao uso contínuo de um núcleo lógico**. Por isso, o valor pode ultrapassar 100% quando há processamento paralelo em múltiplos núcleos: por exemplo, 715% equivalem a aproximadamente 7,15 núcleos lógicos durante o intervalo observado, e **não** a 715% da capacidade total da máquina. O número de workers CGNR não equivale necessariamente ao número de threads de todo o processo. O pico é uma **amostra temporal**, não a média sobre toda a carga.

A memória é a **soma do RSS** do processo e dos filhos em cada amostra. Memória compartilhada pode ser contabilizada em mais de um processo; aumento de RSS isoladamente não comprova vazamento de memória.

## Observações e gargalos

- **python — 15 sinais/cliente:** Saturação: QUEUE_FULL observado (backpressure intencional); CPU elevada para a quantidade de workers (indício; não diagnóstico definitivo)
- **python — 30 sinais/cliente:** Saturação: QUEUE_FULL observado (backpressure intencional); CPU elevada para a quantidade de workers (indício; não diagnóstico definitivo)
- **python — 60 sinais/cliente:** Saturação: QUEUE_FULL observado (backpressure intencional); CPU elevada para a quantidade de workers (indício; não diagnóstico definitivo)
- **cpp — 15 sinais/cliente:** Saturação: QUEUE_FULL observado (backpressure intencional)
- **cpp — 30 sinais/cliente:** Saturação: QUEUE_FULL observado (backpressure intencional)
- **cpp — 60 sinais/cliente:** Saturação: QUEUE_FULL observado (backpressure intencional); CPU elevada para a quantidade de workers (indício; não diagnóstico definitivo)

## Progressão da carga

- cpp: vazão estável ou menor entre 15 e 30 sinais/cliente (indício; verificar se ambas as janelas são completas).
- cpp: vazão estável ou menor entre 30 e 60 sinais/cliente (indício; verificar se ambas as janelas são completas).
- python: vazão estável ou menor entre 15 e 30 sinais/cliente (indício; verificar se ambas as janelas são completas).
- python: vazão estável ou menor entre 30 e 60 sinais/cliente (indício; verificar se ambas as janelas são completas).

## Limitações e evidências

- `workload_complete=false`: a janela de coleta não cobre toda a carga; não comparar os tempos de execução e a vazão como se fossem completos.
- A matriz sintética é um cenário controlado, não um modelo experimental real.
- `queue_peak` é observado pelo servidor; o pico amostrado da TASK-16 pode perder alterações de fila muito rápidas.
- O pacote de evidências inclui `report.json`, `report.csv` e, para cada cenário, `scenario.json`, `requests.csv`, `summary.json`, `samples.csv` e `reconstructions.csv`. Os números são derivados da execução registrada, não de estimativas manuais.

Gargalos e comparação de implementações dependem da carga, hardware e configuração observados; outros ambientes exigem novas medições.
