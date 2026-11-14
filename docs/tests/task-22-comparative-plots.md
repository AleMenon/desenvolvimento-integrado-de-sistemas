# TASK-22 — Gráficos comparativos de desempenho

## Objetivo

Gerar gráficos de comparação entre servidores Python e C++,
a partir dos arquivos reais exportados pela TASK-16 e das
estatísticas consolidadas pela TASK-17.

## Entradas

Cada diretório de ensaio deve conter:

- summary.json
- samples.csv
- reconstructions.csv

O módulo aceita múltiplos ensaios por implementação.

## Saídas

- cpu_comparison.png
- memory_comparison.png
- total_execution_time.png
- mean_reconstruction_time.png
- image_counts.png
- plots_manifest.json

O manifesto registra as fontes e as estatísticas utilizadas.

## Metodologia

CPU:

Série temporal baseada no campo cpu_percent de samples.csv.
Os valores representam uso de CPU do processo monitorado e
podem exceder 100% quando vários núcleos são utilizados.

Memória:

Série temporal de memory_rss_bytes, convertida para MiB.

Tempo total:

Consolidação de total_execution_time_ms segundo a TASK-17.
Ensaios incompletos produzem N/D, nunca duração zero.

Tempo médio:

Média das durações das reconstruções concluídas, ponderada
pela quantidade de imagens, segundo a TASK-17.

Imagens:

Quantidade total de reconstruções concluídas e falhas,
mantendo as categorias separadas.

## Execução

Instalar as dependências do projeto usando uv.

A partir da raiz do repositório, executar:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m monitoring.plots results/metrics/python results/metrics/cpp --output results/plots

Para múltiplos ensaios:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m monitoring.plots results/run-1/python results/run-1/cpp results/run-2/python results/run-2/cpp --output results/plots

## Testes

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m pytest tests/unit/test_plots.py -v

Os testes usam fixtures sintéticas apenas para conferir
cálculos, validações e exportação dos arquivos PNG.

## Critério de aceite

Os gráficos finais destinados ao relatório técnico devem
ser gerados com arquivos reais de experimentos.

Os testes automatizados não substituem a medição real.

Python e C++ devem usar cargas, hardware, parâmetros e
configurações equivalentes para comparação de desempenho.

## Estado das evidências

A implementação do gerador pode ser validada antes da TASK-21.

A geração final dos gráficos reais depende da disponibilização
dos arquivos de benchmark, que não estavam presentes no
worktree durante a preparação da TASK-22.

## Resultados da validação local

Ambiente: Linux/WSL, Python 3.12 e compilação C++ Release.

- Testes específicos da TASK-22: 10 aprovados.
- Suíte Python completa: 266 aprovados, 4 ignorados.
- CTest C++: 2 de 2 aprovados.
- Interface CLI do gerador: validada com `--help`.
- Exportação dos cinco PNGs: verificada com fixtures sintéticas.
- Manifesto JSON: gerado e validado nos testes.

### Pendência para o critério de aceite

Os gráficos definitivos ainda precisam ser gerados a partir de
exports reais dos experimentos comparativos da TASK-21.

As fixtures sintéticas validam o gerador, mas não constituem
evidência de desempenho real dos servidores.
