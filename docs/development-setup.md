# Configuração do ambiente de desenvolvimento

## 1. Tecnologias

O projeto utiliza:

- Python 3.12
- C++17
- NumPy
- Eigen
- OpenBLAS
- CMake
- FastAPI e Uvicorn
- Requests
- Pytest
- uv (gerenciamento de dependências Python)

## 2. Pré-requisitos

### 2.1 Dependências do sistema

Em distribuições Linux baseadas em Ubuntu/Debian:

```bash
sudo apt update

sudo apt install -y \
    python3 \
    g++ \
    cmake \
    build-essential \
    libeigen3-dev \
    libopenblas-dev
```

### 2.2 Instalação do uv

O projeto utiliza o `uv` para gerenciar o ambiente virtual e as dependências Python.

Instale utilizando o instalador oficial:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verifique a instalação:

```bash
uv --version
```

## 3. Ambiente Python

### 3.1 Versão do Python

O projeto utiliza Python 3.12, definido no arquivo `.python-version`.

O `uv` permite instalar essa versão caso ela não esteja disponível:

```bash
uv python install 3.12
```

### 3.2 Instalação das dependências

Na raiz do repositório:

```bash
uv sync --locked
```

O comando cria ou atualiza automaticamente o ambiente virtual `.venv/` de acordo com o `pyproject.toml` e o `uv.lock`.

Os arquivos possuem as seguintes responsabilidades:

| Arquivo | Finalidade |
|---|---|
| `pyproject.toml` | Declara as dependências e configurações do projeto |
| `uv.lock` | Registra as versões resolvidas das dependências |
| `.python-version` | Define a versão de Python utilizada |

O arquivo `uv.lock` deve ser versionado para permitir a reprodução das dependências em diferentes ambientes.

### 3.3 Verificação do NumPy

Para verificar a instalação:

```bash
uv run python -c "import numpy as np; print(np.__version__); np.show_config()"
```

Para consultar as bibliotecas utilizadas durante a execução:

```bash
uv run python -c "import numpy as np; np.show_runtime()"
```

A configuração deve ser inspecionada para confirmar qual implementação BLAS está sendo utilizada.

A instalação de OpenBLAS no sistema não garante que o NumPy utilize automaticamente essa mesma biblioteca.

## 4. Compilação C++

### 4.1 Configuração

O projeto utiliza CMake para compilar os componentes C++17.

Na raiz do repositório:

```bash
cmake -S . -B build
```

### 4.2 Compilação

```bash
cmake --build build
```

### 4.3 Teste do ambiente

```bash
./build/environment_check
```

Resultado esperado:

```text
Ambiente C++ configurado!
Resultado: 3 7
```

O teste verifica a compilação C++ e uma operação matricial com Eigen.

### 4.4 Integração com OpenBLAS

O CMake configura a vinculação com OpenBLAS e utiliza a definição `EIGEN_USE_BLAS` para habilitar a integração em operações compatíveis.

Nem todas as operações do Eigen são necessariamente executadas por meio do OpenBLAS.

A utilização efetiva do backend deverá ser validada durante a implementação e os testes de desempenho.

## 5. Testes Python

Execute:

```bash
uv run python -m pytest tests/environment/ -v
```

Os testes verificam:

- Produto matriz-vetor utilizando NumPy.
- Utilização da precisão numérica `float64`.

Os testes de ambiente não substituem os testes específicos dos algoritmos de reconstrução.

## 6. Estrutura do projeto

```text
client/python/        Cliente Python
server/python/        Servidor Python
server/cpp/           Servidor C++
models/               Modelos matriciais
docs/                 Documentação
tests/environment/    Testes do ambiente
tests/api/            Testes da API
tests/integration/    Testes de integração
```

A organização permite separar os componentes de comunicação, processamento numérico, documentação e testes.

## 7. Reprodutibilidade e desempenho

Para manter condições consistentes entre os ambientes de desenvolvimento:

- Utilizar Python 3.12.
- Instalar dependências conforme o `uv.lock`.
- Registrar as versões de NumPy, Eigen e OpenBLAS.
- Verificar o backend BLAS efetivamente utilizado.
- Utilizar os mesmos parâmetros numéricos nos experimentos.
- Controlar o número de threads utilizadas pelas bibliotecas matemáticas.

Para iniciar testes com uma thread BLAS por processo, configure antes de executar as aplicações:

```bash
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
```

Essas configurações buscam reduzir diferenças relacionadas ao paralelismo durante as comparações.

## 8. Observações

- O ambiente virtual `.venv/` não deve ser versionado.
- O diretório `build/` também deve permanecer fora do Git.
- Os arquivos `pyproject.toml`, `uv.lock` e `.python-version` devem ser versionados.
- As versões das bibliotecas C++ instaladas no sistema devem ser registradas para os experimentos.
- A utilização efetiva de OpenBLAS deverá ser verificada nas implementações numéricas.

## 9. Validação inicial

O ambiente inicial foi validado em Linux com Python 3.12.3 e GCC 13.3.0.

Resultados obtidos:

- Configuração CMake concluída.
- OpenBLAS encontrado em `/usr/lib/x86_64-linux-gnu/libopenblas.so`.
- Compilação C++ concluída.
- Teste matricial com Eigen executado.
- Dois testes Python aprovados com Pytest.
- Dependências Python resolvidas e sincronizadas utilizando `uv`.