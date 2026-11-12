# Configuração do ambiente de desenvolvimento

## 1. Tecnologias

O projeto utiliza:

- Python 3
- C++17
- NumPy
- Eigen
- OpenBLAS
- CMake
- FastAPI e Uvicorn
- Requests
- Pytest

## 2. Pré-requisitos

Em distribuições Linux baseadas em Ubuntu/Debian:

```bash
sudo apt update

sudo apt install -y \
    python3 \
    python3-venv \
    python3-pip \
    g++ \
    cmake \
    build-essential \
    libeigen3-dev \
    libopenblas-dev
```

## 3. Ambiente Python

Na raiz do repositório:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Para verificar a instalação e a configuração do NumPy:

```bash
python -c "import numpy as np; print(np.__version__); np.show_config()"
```

## 4. Compilação C++

Configurar o projeto:

```bash
cmake -S . -B build
```

Compilar:

```bash
cmake --build build
```

Executar o teste do ambiente:

```bash
./build/environment_check
```

Resultado esperado:

```text
Ambiente C++ configurado!
Resultado: 3 7
```

## 5. Testes Python

Com o ambiente virtual ativado:

```bash
python -m pytest tests/environment/ -v
```

Os testes verificam o produto matriz-vetor e a utilização de precisão `float64`.

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

## 7. Observações

- O ambiente virtual `.venv/` e o diretório `build/` não devem ser versionados.
- A configuração do CMake permite localizar Eigen e OpenBLAS.
- A utilização efetiva do OpenBLAS como backend numérico deverá ser verificada nas implementações.
- Os testes de ambiente não substituem os testes dos algoritmos de reconstrução.

## 8. Validação inicial

O ambiente foi validado em Linux com Python 3.12.3 e GCC 13.3.0.

Resultados obtidos:

- Configuração CMake concluída.
- OpenBLAS encontrado em `/usr/lib/x86_64-linux-gnu/libopenblas.so`.
- Compilação C++ concluída.
- Teste de operações matriciais com Eigen executado.
- Dois testes Python aprovados com Pytest.