# TASK-05 — Operações matriciais em C++

Implementação em `server/cpp/matrix_operations.hpp` e `.cpp`, no namespace
`reconstruction`, usando C++17, Eigen e precisão `double` (equivalente ao
`float64` da TASK-04).

| Função | Condição | Resultado |
| --- | --- | --- |
| `multiply_matrices(m, n)` | colunas de m = linhas de n | matriz |
| `multiply_scalar_matrix(a, m)` | escalar finito | matriz |
| `multiply_matrix_vector(m, a)` | colunas de m = tamanho de a | vetor |
| `multiply_vector_matrix(a, m)` | tamanho de a = linhas de m | vetor |

A última operação acompanha a TASK-04 e o arquivo oficial `aM.csv`; não substitui
a multiplicação escalar × matriz. As funções retornam novos objetos, recebem as
matrizes e os vetores por referência constante e rejeitam entradas vazias,
dimensões incompatíveis, NaN e infinito com `std::invalid_argument`.
Os tipos da API C++ são `Eigen::MatrixXd`, `Eigen::VectorXd` e `double`;
a conversão/validação de JSON pertence à futura camada HTTP.

O alvo CMake `matrix_operations` pode ser vinculado pelo futuro servidor.
Ele propaga os cabeçalhos, `EIGEN_USE_BLAS` e as dependências Eigen/OpenBLAS.
O CMake mínimo foi corrigido para 3.18 (`BLAS::BLAS`), e a descoberta de Eigen
aceita o pacote Eigen3 instalado, incluindo a versão 5 do Arch.

## Executar

Com as dependências do sistema instaladas e na raiz do repositório:

```bash
uv sync --locked
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 2
ctest --test-dir build --output-on-failure
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m pytest tests/ -q
```

O CTest executa o teste de ambiente C++. O pytest executa os testes Python e a
comparação entre linguagens. Para rodar somente a comparação, use
`tests/integration/test_cpp_matrix_operations.py` no lugar de `tests/`.
Para outro diretório de build, defina `MATRIX_OPERATIONS_RUNNER` com o caminho
do executável `matrix_operations_runner`.

O adaptador C++ recebe valores em texto por linhas, com 17 dígitos significativos,
e devolve dimensões e resultados. Esse formato existe somente nos testes;
não altera o contrato HTTP/JSON da arquitetura. O Python envia as mesmas entradas
às funções reais de `server/python/matrix_operations.py` e ao executável C++.

## Critério numérico e cobertura

Para a comparação C++/Python, em cada elemento:

```text
abs(cpp - python) <= 1e-12 + 1e-12 * abs(python)
```

Também são verificadas as dimensões de saída e a ausência de resultados não
finitos nos casos testados. São reutilizadas as entradas sintéticas da TASK-04,
acrescentando casos retangulares aleatórios com semente 42, valores negativos,
zero, decimais, dimensões unitárias e cancelamento. Entradas inválidas são
submetidas às duas implementações para comparar a rejeição.

O `tests/fixtures/Dados.zip` é lido diretamente, sem duplicar os dados:

- `M.csv` e `N.csv`: produto comparado com Python e `MN.csv`.
- `M.csv` e `a.csv`: produtos matriz × vetor e vetor × matriz comparados com Python.
- `aM.csv`: referência arredondada, comparada separadamente com `atol=0.005`
  e `rtol=0`, conforme a TASK-04. A comparação entre linguagens mantém `1e-12`.
- `M.csv` multiplicada pelo escalar `-2.5`: comparada com Python.

## Validação realizada

Em 2026-11-13: Arch Linux, GCC 16.2.1, CMake 4.4.5, Eigen 5.0.1,
OpenBLAS do sistema 0.3.34, Python 3.12.16 e NumPy 2.5.4 (ambiente do `uv.lock`).

- Build Release concluído.
- CTest: 1 teste aprovado.
- Pytest: **65 testes aprovados**, incluindo 40 novos casos da TASK-05 e os
  25 testes anteriores. Alguns casos verificam mais de uma operação.
- `ldd` identificou OpenBLAS no executável; `nm -D` identificou referências às
  rotinas `dgemm_` e `dgemv_`.

Esta validação verifica correção numérica e integração do build, não desempenho.
O alinhamento das versões/builds de OpenBLAS entre Python e C++ permanece
necessário antes dos ensaios de desempenho previstos na TASK-01.
