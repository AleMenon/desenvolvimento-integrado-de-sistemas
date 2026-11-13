# TASK-04 — Validação das operações matriciais em Python

## 1. Objetivo

Documentar a implementação e a validação das operações matriciais básicas em Python, conforme os requisitos da TASK-04 (#4).

As operações foram implementadas utilizando a biblioteca NumPy, com precisão numérica `float64`, e serão utilizadas como base para as etapas posteriores do projeto, especialmente a implementação do algoritmo CGNR em Python (TASK-06).

## 2. Operações implementadas

Foram implementadas as seguintes operações:

| Operação | Descrição | Função |
|---|---|---|
| `MN = M × N` | Multiplicação matriz-matriz | `multiply_matrices(m, n)` |
| `aM = a × M` | Multiplicação vetor-matriz | `multiply_vector_matrix(a, m)` |
| `Ma = M × a` | Multiplicação matriz-vetor | `multiply_matrix_vector(m, a)` |

Também foi implementada uma operação adicional:

| Operação | Descrição | Função |
|---|---|---|
| Escalar × matriz | Multiplicação de uma matriz por um escalar | `multiply_scalar_matrix(a, m)` |

Todas as operações retornam resultados com precisão `float64`.

### 2.1 Validação de dimensões

Antes da execução, são verificadas as dimensões dos operandos.

Para a multiplicação matriz-matriz:

- M possui dimensões `(m, n)`.
- N possui dimensões `(n, p)`.
- O resultado possui dimensões `(m, p)`.

Para a multiplicação vetor-matriz:

- O vetor possui `m` elementos.
- A matriz possui dimensões `(m, n)`.
- O resultado possui `n` elementos.

Para a multiplicação matriz-vetor:

- A matriz possui dimensões `(m, n)`.
- O vetor possui `n` elementos.
- O resultado possui `m` elementos.

Caso as dimensões sejam incompatíveis, a implementação lança uma exceção `ValueError`.

Também são rejeitadas entradas vazias, tipos não numéricos e valores `NaN` ou infinitos.

## 3. Ambiente de execução

A validação foi realizada no seguinte ambiente:

| Componente | Configuração |
|---|---|
| Sistema operacional | Linux |
| Python | 3.12.3 |
| Biblioteca numérica | NumPy 2.5.4 |
| Precisão numérica | float64 |
| Framework de testes | Pytest 9.2.0 |
| Gerenciamento do ambiente | Ambiente virtual Python |

A implementação está localizada em:

`server/python/matrix_operations.py`

Os testes automatizados estão localizados em:

`tests/unit/test_matrix_operations.py`

## 4. Testes unitários

Foram implementados testes automatizados utilizando Pytest.

Os testes verificam:

- Multiplicação de matrizes quadradas.
- Multiplicação de matrizes retangulares.
- Multiplicação de matrizes por escalares positivos, negativos e zero.
- Multiplicação matriz-vetor.
- Multiplicação vetor-matriz.
- Validação de dimensões incompatíveis.
- Rejeição de entradas vazias.
- Rejeição de valores `NaN` e infinitos.
- Validação dos tipos numéricos.
- Utilização da precisão `float64`.
- Preservação dos dados de entrada.
- Dimensões dos resultados.

## 5. Validação com dados do professor

Além dos testes unitários com matrizes sintéticas, foram utilizados os dados disponibilizados pelo professor.

### 5.1 Arquivos utilizados

Os arquivos estão armazenados no conjunto `Dados.zip`, utilizado pelos testes na pasta `tests/fixtures/`.

Foram utilizados:

| Arquivo | Descrição |
|---|---|
| `M.csv` | Matriz M |
| `N.csv` | Matriz N |
| `a.csv` | Vetor a |
| `MN.csv` | Resultado esperado da multiplicação M × N |
| `aM.csv` | Resultado esperado da multiplicação a × M |

### 5.2 Multiplicação matriz-matriz

A operação `MN = M × N` foi executada utilizando os arquivos `M.csv` e `N.csv`.

O resultado calculado foi comparado com o arquivo `MN.csv`, fornecido pelo professor.

**Resultado:** teste aprovado.

### 5.3 Multiplicação vetor-matriz

A operação `aM = a × M` foi executada utilizando `a.csv` e `M.csv`.

O resultado foi comparado com `aM.csv`.

Como os valores de referência estão registrados com arredondamento decimal, foi utilizada uma tolerância absoluta de `0.005`, sem tolerância relativa.

**Resultado:** teste aprovado.

### 5.4 Multiplicação matriz-vetor

A operação `Ma = M × a` foi executada utilizando `M.csv` e `a.csv`.

Como o conjunto utilizado não contém um arquivo de referência `Ma.csv`, os resultados foram comparados com valores calculados pela definição matemática do produto matriz-vetor.

Foi utilizada tolerância absoluta e relativa de `1e-12`.

**Resultado:** teste aprovado.

### 5.5 Validação de dimensões

Foi realizado um teste adicional para verificar o comportamento da multiplicação vetor-matriz quando os operandos apresentam dimensões incompatíveis.

**Resultado:** teste aprovado.

## 6. Resultados obtidos

O comando utilizado para executar os testes foi:

```bash
.venv/bin/python -m pytest tests/unit/ -v
```

Resultado registrado:

```text
collected 23 items

23 passed in 0.08s
```

Todos os testes executados foram aprovados.

| Categoria | Quantidade |
|---|---:|
| Testes unitários iniciais | 19 |
| Testes adicionais de validação | 4 |
| Total de testes | 23 |
| Testes aprovados | 23 |
| Testes reprovados | 0 |

## 7. Considerações

A implementação utiliza operações vetorizadas do NumPy e valida os operandos antes de executar os cálculos.

Os resultados demonstram a correção das operações para os casos testados, incluindo os dados fornecidos pelo professor.

A validação apresentada não constitui uma análise de desempenho. As comparações entre as implementações Python e C++ serão realizadas nas tarefas específicas de avaliação de desempenho.

## 8. Conclusão

A TASK-04 apresenta os seguintes resultados:

- Operações matriciais básicas implementadas.
- Validação de dimensões implementada.
- Testes automatizados executados.
- Dados fornecidos pelo professor utilizados na validação.
- Resultados documentados.
- 23 testes aprovados.

Com base nos testes realizados, a implementação atende aos requisitos funcionais verificados da TASK-04 e está pronta para revisão.

A integração com o algoritmo CGNR em Python será realizada posteriormente na TASK-06.