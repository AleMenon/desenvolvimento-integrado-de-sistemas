# TASK-17 — Cálculos estatísticos

O módulo `monitoring.statistics` lê os três arquivos exportados pela TASK-16:
`summary.json`, `samples.csv` e `reconstructions.csv`. Não depende de servidores
ativos e não modifica os dados originais. Aceita um ou mais ensaios por versão.

```bash
uv run python -m monitoring.statistics \
  results/metrics/python results/metrics/cpp \
  --output results/statistics
```

Exporta `comparison.csv`, `comparison.json` e `comparison.md`, com uma linha por
`implementation` (`python` ou `cpp`). JSON inclui também as fontes e resultados
individuais por ensaio. Todos os tempos estão em milissegundos.

| Campo | Definição |
| --- | --- |
| `completed_count` | Soma das imagens concluídas com sucesso nas janelas; falhas não contam. |
| `failed_count` | Soma das falhas, apresentada separadamente. |
| `mean_reconstruction_time_ms` | Soma das durações CGNR das imagens concluídas / quantidade dessas imagens. Não inclui fila, HTTP nem falhas. |
| `total_execution_time_ms` | Por ensaio completo: última conclusão (incluindo falhas) menos primeira aceitação. Por versão: soma das durações dos ensaios. Não soma tempos de imagens simultâneas nem inclui intervalos entre ensaios. |
| `queue_mean` | Soma de tamanho da fila × duração observada / tempo observado. |
| `queue_mode` | Tamanho de fila com maior duração observada. Em empate, menor tamanho. |
| `queue_observation_time_ms` | Soma dos intervalos cobertos pelas amostras. |
| `workload_complete` | Todos os ensaios do grupo cobrem cargas completas, sem tarefas pendentes ou registros faltantes. |

## Fila e agregação

Cada amostra é considerada válida até a próxima (retenção à esquerda). A última
não ganha uma duração fictícia. Períodos de fila vazia participam do cálculo.
Isso é uma **estimativa baseada em amostras**, não uma reconstrução exata dos
eventos entre consultas. A média e a moda do endpoint desde o início do servidor
não são usadas: abrangem outra janela. Também não se reutiliza a média aritmética
`queue_mean_sampled` da TASK-16, pois amostras podem ter intervalos diferentes.

Na consolidação são somados os tempos por tamanho da fila e as durações individuais
das reconstruções. Não se faz média de médias nem moda de modas. Ensaios devem ser
independentes e usar a mesma carga, hardware e configuração para comparação de
desempenho; o módulo calcula estatísticas, não certifica essas condições.

## Dados incompletos e validação

Se qualquer ensaio estiver incompleto, o tempo total consolidado fica `null`.
Contadores continuam disponíveis. A média de reconstrução fica `null` quando
faltam registros de conclusão ou não há imagens concluídas. Uma janela sem imagens
mas com falhas pode ter duração total válida. Sem pelo menos duas amostras, média
e moda da fila ficam `null`. CSV usa células vazias; Markdown usa `N/D`.

Se `execution_time_ms` estiver vazio em uma reconstrução `completed`,
o registro é tratado como incompleto: os contadores e as estatísticas da fila
são preservados, mas `mean_reconstruction_time_ms` e `total_execution_time_ms`
ficam `null` e `workload_complete` fica `false`. Uma duração vazia em registro
`failed` é permitida, pois falhas não entram na média CGNR. Durações preenchidas
mas inválidas continuam sendo rejeitadas.

São rejeitados caminhos duplicados, versões desconhecidas, IDs duplicados dentro
do ensaio, estados não finais, contadores booleanos/fracionários/negativos,
valores não finitos, horários sem fuso ou invertidos e amostras sem tempos crescentes.
IDs podem se repetir entre ensaios, pois o servidor pode ter sido reiniciado.
O tempo total usa os horários UTC disponíveis no export; ajustes no relógio do
sistema podem afetá-lo. Não há timestamps monotônicos por tarefa no formato atual.

## Verificação

```bash
uv run python -m pytest tests/unit/test_statistics.py -q
```

Os testes usam resultados calculáveis à mão: fila 0 por 100 ms e fila 2 por 300 ms
(média 1,5; moda 2), reconstruções de 10/30/100 ms (média conjunta 140/3), falhas
excluídas da média, empates, janela vazia/parcial, registros ausentes, dados
inválidos e leitura das três tabelas exportadas. Não são benchmarks reais.

Há também um teste de integração do formato de arquivos que usa `Collector.run()`
da TASK-16, com registros de métricas simulados para `python` e `cpp`, para gerar
os arquivos `summary.json`, `samples.csv` e `reconstructions.csv` e alimentar
a consolidação da TASK-17. Isso valida o contrato do exportador, não constitui
um benchmark real de dois servidores.

O teste `tests/unit/test_python_metrics_api.py` pertence à TASK-16 e foi relatado
como bloqueado na execução completa anterior. O problema não foi atribuído
à TASK-17. Antes do merge, execute-o separadamente para verificar a condição:

```bash
timeout 30s uv run python -m pytest tests/unit/test_python_metrics_api.py -vv -s
```

Se retornar código 124, o teste excedeu 30 segundos; nesse caso, registre o log
e investigue o ambiente do `TestClient` antes de afirmar que a suíte completa passou.
