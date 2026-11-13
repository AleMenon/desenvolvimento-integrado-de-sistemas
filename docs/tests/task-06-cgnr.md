# TASK-06 — Implementação e validação do algoritmo CGNR em Python

## 1. Objetivo

Documentar a implementação e a validação experimental do algoritmo CGNR (*Conjugate Gradient on Normal Residual*) em Python.

O algoritmo é utilizado para obter uma solução aproximada de sistemas lineares associados à reconstrução de imagens.

## 2. Implementação

O algoritmo foi implementado no arquivo:

`server/python/cgnr.py`

A implementação utiliza NumPy com precisão numérica `float64`.

O CGNR busca minimizar:

$$
\min_x \|Hx - g\|_2^2
$$

sem construir explicitamente a matriz \(H^TH\).

A implementação contempla:

- Inicialização da solução.
- Cálculo do resíduo.
- Cálculo do resíduo normal.
- Atualização da direção de busca.
- Atualização da solução.
- Controle do número máximo de iterações.
- Critério de parada baseado no resíduo normal.
- Registro das normas dos resíduos.
- Validação das dimensões dos operandos.

## 3. Testes automatizados

Os testes foram implementados em:

`tests/unit/test_cgnr.py`

Foram executados 15 testes específicos do CGNR.

O comando utilizado foi:

```bash
uv run python -m pytest tests/unit/test_cgnr.py -v
```

Resultado:

```text
15 passed in 0.17s
```

Também foi executada a suíte completa do projeto:

```bash
uv run python -m pytest tests/ -v
```

Resultado:

```text
40 passed in 0.11s
```

## 4. Dados utilizados

A validação experimental utilizou os arquivos fornecidos pelo professor:

- `H-2.csv.zip`: matriz do sistema.
- `g-30x30-1.csv`: primeiro vetor de medições.
- `g-30x30-2.csv`: segundo vetor de medições.

A matriz possui dimensões de 27.904 × 900.

Cada vetor de medições possui 27.904 elementos.

As soluções obtidas possuem 900 elementos, organizados como imagens de 30 × 30 pixels.

## 5. Configuração dos experimentos

Os experimentos utilizaram:

| Parâmetro | Configuração |
|---|---|
| Linguagem | Python 3.12.3 |
| Biblioteca numérica | NumPy |
| Precisão | float64 |
| Tolerância relativa | 1e-6 |
| Máximo de iterações | 100 |
| Threads OpenBLAS | 1 |
| Threads OpenMP | 1 |

O experimento foi executado utilizando:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run python -m scripts.run_cgnr_experiment \
    --matrix-zip build/data/H-2.csv.zip \
    --measurements build/data/g-30x30-1.csv \
    --max-iterations 100 \
    --tolerance 1e-6
```

O segundo experimento utilizou os mesmos parâmetros, substituindo o vetor de medições por `g-30x30-2.csv`.

## 6. Resultados experimentais

### 6.1 Primeiro vetor de medições

Arquivo: `g-30x30-1.csv`

| Métrica | Resultado |
|---|---:|
| Iterações executadas | 100 |
| Norma do resíduo | 4.159255e-09 |
| Resíduo relativo | 1.321190e-05 |
| Norma do resíduo normal | 1.288809e-13 |
| Tempo de execução | 1.52 s |
| Critério de convergência atingido | Não |

### 6.2 Segundo vetor de medições

Arquivo: `g-30x30-2.csv`

| Métrica | Resultado |
|---|---:|
| Iterações executadas | 100 |
| Norma do resíduo | 8.528886e-09 |
| Resíduo relativo | 2.376094e-05 |
| Norma do resíduo normal | 3.698137e-13 |
| Tempo de execução | 1.59 s |
| Critério de convergência atingido | Não |

## 7. Análise da convergência

Nos experimentos, o CGNR apresentou redução das normas dos resíduos.

Para o primeiro vetor, também foram realizadas execuções com 10 e 30 iterações.

| Iterações | Norma do resíduo | Resíduo relativo |
|---|---:|---:|
| 10 | 8.008660e-06 | 2.543955e-02 |
| 30 | 1.389277e-06 | 4.413047e-03 |
| 100 | 4.159255e-09 | 1.321190e-05 |

Apesar da redução dos resíduos, o critério de convergência não foi atingido nas execuções realizadas.

O critério de parada implementado é baseado na norma relativa do resíduo normal:

$$
\left\|H^T(g-Hx_k)\right\|_2
\leq
\mathrm{tolerance}\cdot
\left\|H^T(g-Hx_0)\right\|_2
$$

Portanto, a redução do resíduo convencional não implica necessariamente que o critério de parada seja satisfeito.

## 8. Arquivos gerados

O programa de experimentação está localizado em:

`scripts/run_cgnr_experiment.py`

Durante a execução, são gerados:

- Imagem reconstruída em PNG.
- Matriz reconstruída em CSV.
- Histórico das normas dos resíduos.
- Arquivo JSON com métricas do experimento.

Os resultados são armazenados localmente em `build/results/`.

O diretório `build/` não é versionado no repositório.

## 9. Limitações e trabalhos futuros

A implementação atual utiliza matrizes densas NumPy.

Para modelos maiores, deverá ser avaliado o uso de estruturas esparsas e outras estratégias de armazenamento, considerando o consumo de memória.

A análise experimental também poderá ser ampliada com:

- Comparação com imagens de referência.
- Avaliação de diferentes tolerâncias.
- Estudo da estabilidade numérica.
- Comparação de desempenho com a implementação C++.
- Avaliação do segundo modelo disponibilizado pelo professor.

## 10. Conclusão

O algoritmo CGNR foi implementado e validado em sistemas pequenos por meio de testes automatizados.

Também foram realizadas reconstruções com a matriz H-2 e dois conjuntos reais de medições.

Os resultados demonstram redução dos resíduos e execução do algoritmo com os dados experimentais.

O critério de convergência adotado não foi satisfeito dentro das 100 iterações dos experimentos realizados. Portanto, os resultados devem ser interpretados como soluções aproximadas obtidas dentro desse limite.