# TASK-07 — CGNR em C++

Implementação em `server/cpp/cgnr.hpp` e `.cpp`, alvo CMake `cgnr`.
Usa Eigen/OpenBLAS, C++17 e `double`, sem formar HᵀH.

```cpp
#include "cgnr.hpp"
auto result = reconstruction::cgnr(H, g); // tolerance=1e-8, max_iterations=10
```

## Critério de parada revisado

Por decisão da dupla após o review, o C++ foi alinhado à TASK-06:

```text
||Hᵀ r_k||₂ <= tolerance * ||Hᵀ r_0||₂
```

A tolerância padrão é `1e-8`, relativa ao resíduo normal inicial. A inicialização
continua `f0=0`, `r0=g`, `z0=Hᵀr0`, `p0=z0`. As recorrências de alpha, beta,
solução, resíduo e direção seguem o CGNR. O limite permitido permanece entre
1 e 10 iterações, com padrão 10.

A diferença assinada entre normas dos resíduos deixou de decidir a parada: ela
podia encerrar na primeira redução do resíduo. O campo opcional `error` preserva
essa diferença apenas para diagnóstico, ficando ausente antes do primeiro passo.
Esta decisão difere da leitura literal do enunciado e deve ser confirmada com o
professor; não representa uma alteração na fórmula das iterações do CGNR.

## Resultado e estabilidade

Retorna `solution`, `iterations`, `converged`, `stop_reason`, `residual_norm`,
`normal_residual_norm`, `residual_history` e `error`.

- `tolerance_reached`: critério relativo satisfeito e confirmado pelos resíduos
  finais recalculados a partir de `g-Hf`.
- `max_iterations`: limite atingido sem convergência.
- `numerical_breakdown`: cálculo degenerado/não finito, ou divergência entre a
  parada pela recorrência e a verificação final.

Resíduo normal inicial nulo retorna solução zero com zero iterações, inclusive
para mínimos quadrados com resíduo convencional não nulo. Entradas vazias,
incompatíveis, não finitas e parâmetros inválidos lançam `std::invalid_argument`.
Overflow/underflow inviabilizando os coeficientes é detectado; atualizações não
finitas não substituem a última solução válida. Normas finais podem ser não finitas
em falhas extremas; a futura API deve tratar esse estado antes de serializar JSON.
Não se usa epsilon absoluto fixo para descartar denominadores pequenos.

A interface C++ mantém estimativa inicial zero e limite máximo obrigatório de 10.
Python também permite `x0` e limites superiores; os testes comparam o domínio comum.
As proteções C++ podem encerrar de forma mais conservadora em instabilidades
extremas; equivalência não é afirmada para todos os dados possíveis.

## Testes

```bash
uv sync --locked
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 2
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ctest --test-dir build --output-on-failure
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m pytest tests/ -q
```

`tests/unit/test_cgnr.cpp` verifica soluções conhecidas, preservação das entradas,
metadados, limites, instabilidades e que a redução do resíduo não encerre sozinha
a execução na primeira iteração. As verificações funcionam em Release.

`tests/integration/test_cpp_cgnr.py` executa as funções reais Python e C++ com os
mesmos valores (transmitidos com 17 dígitos), tolerância e limite. São 22 casos:
identidade, diagonal, retangular, mínimos quadrados inconsistentes, sinal zero,
matriz nula, posto deficiente, subdeterminado, sistema diagonal de 20 variáveis,
sistema aleatório com semente fixa e dados de pequena escala; cada caso roda com
limites de 1 e 10 passos.

Compara solução, histórico e normas finais com `rtol=1e-8`, `atol=1e-10`, além de
igualdade na contagem de iterações e no indicador de convergência. Verifica também
formas, finitude e limite de iterações. `CGNR_RUNNER` permite informar um caminho
alternativo ao executável padrão `build/cgnr_runner`.

Resultado após o review: **2 testes CTest e 104 testes pytest aprovados**, incluindo
as 22 novas comparações entre linguagens. Isso comprova equivalência nos casos
testados; os experimentos completos dos modelos 30×30 e 60×60 devem ser repetidos
na TASK-08 após incorporar esta revisão.
