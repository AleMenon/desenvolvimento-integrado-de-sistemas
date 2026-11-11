# TASK-01 — Stack tecnológica e bibliotecas BLAS

## Tecnologias escolhidas

| Uso | Tecnologia | Justificativa |
| --- | --- | --- |
| Versão interpretada | Python 3 | Desenvolvimento simples e bom suporte a cálculos científicos. |
| Versão compilada | C++17 | Compilação nativa e controle de recursos para a implementação dos algoritmos. |
| Matrizes e vetores em Python | NumPy | Permite escrever operações matemáticas diretamente. |
| Matrizes e vetores em C++ | Eigen | Facilita a manipulação de matrizes e vetores. |
| Biblioteca BLAS | OpenBLAS | Implementação otimizada de operações de álgebra linear, compatível com NumPy e Eigen. |

## Suporte às operações necessárias
Será utilizado `float64` no NumPy e `double` no Eigen para manter a mesma precisão numérica.

| Operação | NumPy | Eigen |
| --- | --- | --- |
| Produto matriz-vetor | `H @ p` | `H * p` |
| Transposta | `H.T` | `H.transpose()` |
| Produto escalar | `np.dot(r, r)` | `r.dot(r)` |
| Norma de vetor | `np.linalg.norm(r)` | `r.norm()` |
| Atualização de vetor | `f + alpha * p` | `f + alpha * p` |
| Valor absoluto e máximo | `np.max(np.abs(v))` | `v.cwiseAbs().maxCoeff()` |

Essas operações atendem aos algoritmos **CGNE e CGNR**.

## Bibliotecas de apoio sugeridas
- **Requests:** envio dos sinais pelo cliente Python.
- **FastAPI + Uvicorn:** API do servidor Python.
- **cpp-httplib + nlohmann/json:** HTTP e JSON no servidor C++.
- **psutil:** coleta de consumo de CPU e memória.
- **Matplotlib:** geração das imagens e dos gráficos do relatório.

## Links úteis
- [NumPy — álgebra linear](https://numpy.org/doc/stable/reference/routines.linalg.html)
- [Eigen — integração com BLAS](https://libeigen.gitlab.io/eigen/docs-nightly/TopicUsingBlasLapack.html)
- [OpenBLAS — documentação](https://www.openmathlib.org/OpenBLAS/docs/)
