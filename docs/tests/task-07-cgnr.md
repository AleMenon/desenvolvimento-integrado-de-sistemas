# TASK-07 — CGNR em C++

Implementação: `server/cpp/cgnr.hpp` e `server/cpp/cgnr.cpp`.
Alvo CMake: `cgnr`, vinculado a `matrix_operations` (Eigen/OpenBLAS, C++17).

```cpp
#include "cgnr.hpp"
// H: matriz m × n; g: vetor de m medições, ambos em double.
auto result = reconstruction::cgnr(H, g, 1e-4, 10);
// result.solution tem n elementos.
```

## Algoritmo e parada

Inicializa `f=0`, `r=g`, `z=H.transpose()*r` e `p=z`. Em cada iteração:

1. `w = H*p`, `alpha = (zᵀz)/(wᵀw)`.
2. `f = f + alpha*p`, `r = r - alpha*w`.
3. `z_new = Hᵀr`; verifica a convergência.
4. `beta = (z_newᵀz_new)/(zᵀz)` e `p = z_new + beta*p`.

Não forma `HᵀH`. Valida as entradas uma vez e usa expressões Eigen nos laços,
evitando repetir a varredura de validação da matriz a cada produto.

**Critério do enunciado**, com a tolerância escrita como `10⁻⁴`:

```text
epsilon = ||r_novo||₂ - ||r_anterior||₂
parar quando epsilon < 1e-4
```

A diferença é assinada, sem valor absoluto e sem normalização. Portanto, uma
redução do resíduo já satisfaz o critério e pode encerrar na primeira iteração,
mesmo longe da solução exata. `converged` indica que esse critério foi satisfeito,
não que o resíduo final seja pequeno. A branch Python consultada usa outro
critério e deverá ser alinhada ao enunciado antes da comparação entre linguagens.

O limite padrão e máximo permitido é **10 iterações**. Valores fora de `[1, 10]`
são rejeitados. A branch Python consultada permite limites maiores e estimativa
inicial opcional; aqui `f0=0` é fixo, conforme a tarefa.

## Resultado e estabilidade

O resultado contém `solution`, `iterations`, `converged`, `stop_reason`,
`residual_norm`, `normal_residual_norm`, `residual_history` e `error`.
O campo `error` registra epsilon; fica ausente antes da primeira iteração.

- `tolerance_reached`: diferença assinada menor que a tolerância.
- `zero_residual`: sinal inicial nulo, solução zero sem precisar dividir por zero.
- `max_iterations`: limite atingido sem convergência.
- `numerical_breakdown`: divisão degenerada, overflow, underflow que inviabiliza
  os coeficientes ou atualização/resíduos finais não finitos.

São rejeitados dimensões incompatíveis/vazias, entradas não finitas e tolerância
não positiva ou não finita com `std::invalid_argument`. Não se usa um epsilon
absoluto fixo para descartar denominadores pequenos: sua escala depende dos dados.

As atualizações são verificadas antes de substituir a solução anterior. Somente
passos aceitos são contabilizados; o histórico tem `iterations + 1` entradas.
Ao encerrar, recalcula `g-Hf` e `Hᵀ(g-Hf)` para informar as normas finais.
Se esses cálculos também excederem a faixa de `double`, as normas podem ser não
finitas e o resultado indica falha numérica; a futura API deve tratar esse estado
antes de serializar JSON. O método sinaliza instabilidade, sem prometer resolver
sistemas de escala arbitrária ou aplicar pré-condicionamento.

Sinal inicial nulo encerra com sucesso e zero iterações. Se a direção inicial é
nula mas o sinal não é, encerra como `numerical_breakdown`, sem afirmar que o
critério de erro foi atingido.

## Validação

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 2
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ctest --test-dir build --output-on-failure
```

`tests/unit/test_cgnr.cpp` verifica soluções conhecidas de um passo e resultados
do primeiro passo calculados à mão para sistemas diagonal e retangular. Testa
explicitamente a parada pela diferença negativa com resíduo ainda não nulo,
preservação das entradas, metadados, limites permitidos de 1 e 10, rejeição de
limites maiores, validação de entradas, escalas pequenas
representáveis e detecção de overflow/underflow. As verificações executam em Release.

Na validação local, os dois testes CTest (`cgnr_cpp` e `environment_cpp`) passaram.
O aceite de equivalência com Python permanece **pendente**, conforme solicitado.
Não foram importados arquivos da outra branch nem alterada sua implementação.
Os modelos `H-2.csv.zip` e sinais de reconstrução citados na TASK-06 não estão
disponíveis neste checkout; o `Dados.zip` existente contém exemplos de operações
matriciais, não uma referência de reconstrução CGNR.
