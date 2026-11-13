# TASK-01 — Stack tecnológica e bibliotecas BLAS

## Tecnologias escolhidas

| Uso | Tecnologia | Justificativa |
| --- | --- | --- |
| Versão interpretada | Python 3 | Desenvolvimento simples e bom suporte a cálculos científicos. |
| Versão compilada | C++17 | Compilação nativa e controle de recursos para a implementação dos algoritmos. |
| Matrizes e vetores em Python | NumPy | Permite escrever operações matemáticas diretamente. |
| Matrizes e vetores em C++ | Eigen | Facilita a manipulação de matrizes e vetores. |
| Biblioteca BLAS | OpenBLAS | Implementação otimizada de operações de álgebra linear, compatível com NumPy e Eigen. |

## Integração com OpenBLAS

**Python / NumPy:** instalar pelo `uv` e verificar o backend com `numpy.show_config()` e `numpy.show_runtime()`. Só considerar o ambiente pronto para a comparação quando a saída identificar OpenBLAS. Instalar OpenBLAS no sistema não troca o backend de um NumPy já instalado. Se necessário, compilar NumPy a partir do código-fonte, selecionando `-Dblas=openblas` e `-Dlapack=openblas` nas opções de build. [Configuração do NumPy](https://numpy.org/doc/stable/building/blas_lapack.html), [inspeção em execução](https://numpy.org/doc/stable/reference/generated/numpy.show_runtime.html).

**C++ / Eigen:** instalar OpenBLAS no sistema, compilar com `-DEIGEN_USE_BLAS` e vincular com `-lopenblas`. No CMake, isso corresponde a definir `EIGEN_USE_BLAS` no alvo e adicionar OpenBLAS às bibliotecas vinculadas. A integração delega operações compatíveis à BLAS; nem toda operação do Eigen passa por ela. [Integração do Eigen](https://libeigen.gitlab.io/eigen/docs-nightly/TopicUsingBlasLapack.html).

**Comparação de desempenho:** registrar as versões de NumPy, Eigen e OpenBLAS, o caminho da biblioteca carregada e o número de threads. Um pacote NumPy pode trazer sua própria cópia de OpenBLAS; portanto, conferir e alinhar as versões nas duas implementações antes do ensaio controlado. Fixar as dependências Python no `uv.lock` e registrar separadamente as versões das bibliotecas do sistema.

Começar com uma thread BLAS por processo, definindo antes de iniciar ambos os servidores:

```bash
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
```

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
As bibliotecas de comunicação abaixo são sugestões; a escolha final e os detalhes da integração serão definidos na **TASK-02**, junto com a arquitetura.

- **Requests:** envio dos sinais pelo cliente Python.
- **FastAPI + Uvicorn:** API do servidor Python.
- **cpp-httplib + nlohmann/json:** HTTP e JSON no servidor C++.
- **psutil:** coleta de consumo de CPU e memória.
- **Matplotlib:** geração das imagens e dos gráficos do relatório.

## Links úteis
- [NumPy — álgebra linear](https://numpy.org/doc/stable/reference/routines.linalg.html)
- [Eigen — integração com BLAS](https://libeigen.gitlab.io/eigen/docs-nightly/TopicUsingBlasLapack.html)
- [OpenBLAS — documentação](https://www.openmathlib.org/OpenBLAS/docs/)
