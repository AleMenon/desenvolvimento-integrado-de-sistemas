# TASK-21 — Benchmarks comparativos Python × C++

Gerado em: `2026-11-22T02:26:46.828719+00:00`.
Plano de sinais SHA-256: `6e5cc719f3efa33ba1be7209705402e44a18359d3d7f025f1d0e133d9ab42cad`.

## Ambiente e protocolo

- SO: `Linux-7.3.5-arch1-1-x86_64-with-glibc2.44`; Python: `3.12.16`; CPUs lógicas: `8`; RAM: `20749221888` bytes
- Modelo: `task18_dense_512`; dimensão do sinal: `512`; seed: `21`
- Três clientes sincronizados; 3 repetições por implementação/carga, com ordem alternada
- Cargas: [15, 30, 60] sinais/cliente; workers: 2; fila: 256
- CGNR: 10 iterações, tolerância 1e-08; BLAS threads por processo: 1
- Amostragem: 0.025 s; timeout de drenagem: 120.0 s
- Cada execução inicia um servidor novo, e usa **o mesmo conjunto de sinais e a mesma ordem por cliente**.
- São elegíveis à comparação somente execuções com todas as respostas HTTP 202, sem falhas e com exportação completa.

## Medianas por carga (somente pares completos)

| total_signals | paired_valid | comparable | python_median_total_ms | cpp_median_total_ms | speedup_cpp_vs_python | python_median_cpu_percent | cpp_median_cpu_percent | python_median_rss_mib | cpp_median_rss_mib | python_median_queue | cpp_median_queue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 45 | 3 | True | 87.000 | 580.000 | 0.150 | 122.706 | 25.493 | 69.383 | 15.117 | 11.609 | 0.000 |
| 90 | 3 | True | 188.000 | 1234.000 | 0.152 | 143.668 | 26.510 | 70.586 | 15.820 | 22.395 | 0.000 |
| 180 | 3 | True | 344.000 | 2530.000 | 0.136 | 146.720 | 25.630 | 72.953 | 17.250 | 38.491 | 0.000 |

## Todas as execuções

| implementation | signals_per_client | repeat | accepted | rejected | finished | valid | total_execution_time_ms | cpu_mean_percent | rss_peak_bytes | queue_peak |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| python | 15 | 1 | 45 | 0 | 45 | True | 86.000 | 114.446 | 72753152 | 39 |
| cpp | 15 | 1 | 45 | 0 | 45 | True | 580.000 | 25.449 | 15851520 | 1 |
| cpp | 15 | 2 | 45 | 0 | 45 | True | 595.000 | 26.465 | 15872000 | 1 |
| python | 15 | 2 | 45 | 0 | 45 | True | 88.000 | 126.370 | 72749056 | 37 |
| python | 15 | 3 | 45 | 0 | 45 | True | 87.000 | 122.706 | 72773632 | 38 |
| cpp | 15 | 3 | 45 | 0 | 45 | True | 579.000 | 25.493 | 15822848 | 2 |
| python | 30 | 1 | 90 | 0 | 90 | True | 202.000 | 140.280 | 74014720 | 76 |
| cpp | 30 | 1 | 90 | 0 | 90 | True | 1248.000 | 23.888 | 16588800 | 2 |
| cpp | 30 | 2 | 90 | 0 | 90 | True | 1229.000 | 27.388 | 16588800 | 1 |
| python | 30 | 2 | 90 | 0 | 90 | True | 172.000 | 143.668 | 73981952 | 78 |
| python | 30 | 3 | 90 | 0 | 90 | True | 188.000 | 147.302 | 74014720 | 75 |
| cpp | 30 | 3 | 90 | 0 | 90 | True | 1234.000 | 26.510 | 16588800 | 2 |
| python | 60 | 1 | 180 | 0 | 180 | True | 344.000 | 148.669 | 76496896 | 146 |
| cpp | 60 | 1 | 180 | 0 | 180 | True | 2527.000 | 25.630 | 18100224 | 2 |
| cpp | 60 | 2 | 180 | 0 | 180 | True | 2532.000 | 26.281 | 18087936 | 2 |
| python | 60 | 2 | 180 | 0 | 180 | True | 340.000 | 146.720 | 76513280 | 149 |
| python | 60 | 3 | 180 | 0 | 180 | True | 428.000 | 145.551 | 76447744 | 154 |
| cpp | 60 | 3 | 180 | 0 | 180 | True | 2530.000 | 24.430 | 18079744 | 2 |

## Interpretação e limitações

- Speedup = mediana do tempo total Python / mediana do tempo total C++; >1 favorece C++.
- Tempos refletem a janela de aceitação até última conclusão de cada carga, e não a inicialização do servidor.
- CPU% da TASK-16 soma processo e filhos: 100% corresponde a um núcleo lógico; pode ultrapassar 100%.
- RSS é soma do processo e descendentes (páginas compartilhadas podem ser contadas várias vezes).
- Fila média é ponderada pela duração entre amostras (retenção à esquerda), não pelo número de amostras.
- CPU média é ponderada pelos intervalos observados; picos de duração curta podem escapar à amostragem.
- Resultados não garantem causalidade nem superioridade geral: hardware, bibliotecas, agendamento e concorrência variam.
- `N/D` significa dado ausente ou rodada não comparável, nunca tempo zero.

## Evidências

- `plan.json` contém os vetores enviados e o hash verificável.
- `runs/<implementação>/level-*/repeat-*/` contém `requests.csv`, `scenario.json`, `summary.json`, `samples.csv`, `reconstructions.csv` e `server.log`.
- `comparison.json` e `comparison.csv` guardam resultados estruturados para a TASK-22.
