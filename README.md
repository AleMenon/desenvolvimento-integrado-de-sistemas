# Desenvolvimento Integrado de Sistemas

Projeto acadêmico de reconstrução de imagens por tomografia, desenvolvido na UTFPR.

O sistema permite enviar sinais numéricos por HTTP para servidores implementados em **Python** e **C++**, reconstruir imagens utilizando o algoritmo **CGNR** e comparar o comportamento das implementações por meio de testes, métricas e gráficos.

## 1. Funcionalidades

- Reconstrução de imagens pelo método CGNR.
- Servidores HTTP/JSON em Python e C++.
- Cliente HTTP para envio e recuperação de reconstruções.
- Execução concorrente de requisições.
- Controle de fila e rejeição por saturação.
- Monitoramento de CPU, memória, tempos e fila.
- Consolidação estatística dos experimentos.
- Geração de cinco gráficos comparativos.
- Testes unitários, de integração e C++.

A reconstrução depende de uma matriz de sistema e de um vetor de sinais compatível com ela.

O repositório inclui o modelo demonstrativo `demo_identity_3`, que permite testar o fluxo sem arquivos externos.

## 2. Tecnologias

| Componente | Tecnologia |
|---|---|
| Servidor Python | Python 3.12, FastAPI, Uvicorn |
| Processamento Python | NumPy |
| Servidor C++ | C++17, cpp-httplib, nlohmann/json |
| Processamento C++ | Eigen, OpenBLAS |
| Compilação | CMake |
| Dependências Python | uv |
| Comunicação | HTTP/JSON |
| Monitoramento | psutil, CSV, JSON |
| Gráficos | Matplotlib |
| Testes | pytest, CTest |

## 3. Pré-requisitos

Ambiente recomendado: Linux ou WSL com Ubuntu/Debian.

São necessários:

- Git.
- Python 3.12.
- uv.
- Compilador C++ com suporte a C++17.
- CMake 3.18 ou superior.
- Eigen3.
- OpenBLAS.
- Conexão com a internet para instalar dependências e, quando necessário, baixar bibliotecas C++ utilizadas pelo CMake.

No Ubuntu/Debian, instale as dependências de sistema:

    sudo apt update
    sudo apt install -y git curl build-essential g++ cmake libeigen3-dev libopenblas-dev

Instale o uv, seguindo o instalador oficial:

    curl -LsSf https://astral.sh/uv/install.sh | sh

Depois, abra um novo terminal ou atualize o PATH conforme a mensagem do instalador.

Confira:

    uv --version
    cmake --version
    g++ --version

Para outros sistemas, consulte [Configuração do ambiente](docs/development-setup.md).

## 4. Instalação

Clone o repositório e entre no diretório:

    git clone https://github.com/AleMenon/desenvolvimento-integrado-de-sistemas.git
    cd desenvolvimento-integrado-de-sistemas

Instale o Python 3.12 e sincronize as dependências:

    uv python install 3.12
    uv sync --locked

O uv gerencia o ambiente virtual `.venv` do projeto.

Não é necessário ativar o ambiente manualmente se os comandos forem executados com `uv run`.

Verifique a instalação:

    uv run --locked python -c "import numpy, fastapi, matplotlib, psutil; print('Dependências Python OK')"

Execute todos os comandos seguintes a partir da raiz do repositório.

## 5. Compilação C++

Configure o projeto em modo Release, incluindo os executáveis de teste:

    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON

Compile:

    cmake --build build -j 4

Os principais executáveis são:

- `build/reconstruction_server`: servidor HTTP C++.
- `build/cgnr_runner`: runner de integração do CGNR.
- `build/matrix_operations_runner`: runner de operações matriciais.
- `build/environment_check`: validação básica do ambiente.

Execute a verificação inicial:

    ./build/environment_check

Execute os testes C++:

    ctest --test-dir build --output-on-failure

O CMake procura Eigen e OpenBLAS no sistema. Para cpp-httplib e nlohmann/json, pode usar dependências instaladas ou FetchContent.

## 6. Executar o servidor Python

Em um terminal, na raiz do projeto:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked uvicorn server.python.reconstruction_server:app --host 127.0.0.1 --port 8000

Confira a disponibilidade em outro terminal:

    curl http://127.0.0.1:8000/health

Liste os modelos disponíveis:

    curl http://127.0.0.1:8000/models

O servidor utiliza o catálogo `models/catalog.json` por padrão.

Para encerrar, pressione Ctrl+C no terminal do servidor.

## 7. Executar o servidor C++

Em outro terminal, na raiz do projeto, depois de compilar:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ./build/reconstruction_server --host 127.0.0.1 --port 8080 --catalog models/catalog.json

Verifique:

    curl http://127.0.0.1:8080/health

Liste os modelos:

    curl http://127.0.0.1:8080/models

Os dois servidores podem funcionar simultaneamente porque utilizam portas diferentes.

Utilize `127.0.0.1` para experimentos locais: o projeto não implementa autenticação para exposição pública.

## 8. Executar o cliente

O cliente HTTP está em `client/reconstruction_client.py`.

Com o servidor Python ou C++ em execução, o exemplo abaixo envia o sinal `[1, 2, 3]` para o modelo `demo_identity_3`, acompanha a reconstrução e recupera o resultado.

Execute na raiz do projeto:

    uv run --locked python -c "from client.reconstruction_client import ReconstructionClient; c = ReconstructionClient('http://127.0.0.1:8000'); print(c.reconstruct('cliente-demo', 'sinal-demo', 'demo_identity_3', [1, 2, 3]))"

Para usar o servidor C++, substitua a porta `8000` por `8080`.

A classe `ReconstructionClient` também fornece os métodos:

- `health()`: consulta a disponibilidade.
- `list_models()`: lista os modelos.
- `get_model(model_id)`: consulta um modelo.
- `submit_signal(...)`: envia uma requisição e recebe seu ID.
- `get_status(request_id)`: consulta o estado.
- `get_result(request_id)`: recupera a imagem final.
- `reconstruct(...)`: executa o fluxo de envio, consulta e recuperação.

Estados possíveis: `queued`, `running`, `completed` e `failed`.

O envio é assíncrono: HTTP 202 significa que a requisição foi aceita, não que a reconstrução terminou.

Consulte também [Comunicação cliente-servidor](docs/tests/task-09-client-server.md).

## 9. API HTTP

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/health` | Estado do servidor |
| GET | `/models` | Modelos disponíveis |
| GET | `/models/{model_id}` | Metadados do modelo |
| POST | `/reconstructions` | Envia um sinal |
| GET | `/reconstructions/{request_id}` | Estado da tarefa |
| GET | `/reconstructions/{request_id}/result` | Resultado da reconstrução |
| GET | `/queue` | Estado da fila |
| GET | `/metrics` | Indicadores do processamento |
| GET | `/metrics/reconstructions` | Histórico de reconstruções |

Exemplo de envio via curl para o servidor Python:

    curl -X POST http://127.0.0.1:8000/reconstructions -H "Content-Type: application/json" -d '{"client_id":"cliente-01","signal_id":"sinal-01","model_id":"demo_identity_3","algorithm":"cgnr","signal":[1,2,3],"parameters":{"max_iterations":10,"tolerance":1e-8}}'

O servidor retorna um `request_id`, usado para consultar o status e recuperar o resultado.

As requisições ficam em uma fila limitada. Quando a capacidade é atingida, o servidor pode responder HTTP 503 com o código `QUEUE_FULL`. Isso indica rejeição controlada, não perda de uma tarefa previamente aceita.

## 10. Modelos e matrizes

O catálogo padrão fica em:

    models/catalog.json

Ele contém o modelo de demonstração `demo_identity_3`, cuja matriz CSV está no mesmo diretório.

Para acrescentar outro modelo:

1. Disponibilize uma matriz CSV numérica sem cabeçalho.
2. Registre `model_id`, `file`, `image_shape` e `version` no catálogo.
3. Garanta que o comprimento do sinal corresponda ao número de linhas da matriz.
4. Garanta que o produto das dimensões de `image_shape` corresponda ao número de colunas.

As matrizes experimentais podem demandar memória significativa e não são substituídas pela matriz demonstrativa.

## 11. Executar os testes

Depois de instalar as dependências e compilar os executáveis C++, execute:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLBACKEND=Agg uv run --locked python -m pytest tests/ -q --tb=short

Para validar especificamente a integração entre os dois servidores e os clientes concorrentes:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m pytest tests/integration/test_task20_full_flow.py -v --tb=short

Para os testes C++:

    ctest --test-dir build --output-on-failure

Alguns testes podem ser ignorados quando dependem de dados experimentais opcionais.

## 12. Executar benchmarks e coletar métricas

O coletor de desempenho da TASK-16 exporta:

- `summary.json`: contadores e resumo estatístico.
- `samples.csv`: amostras temporais de CPU, memória e fila.
- `reconstructions.csv`: histórico das tarefas.

Para monitorar um servidor, inicie-o e obtenha seu PID.

Exemplo de coleta no servidor C++ iniciado em primeiro plano em outro terminal:

    pgrep -af reconstruction_server

Escolha o PID correto do servidor e execute, substituindo `PID_DO_SERVIDOR` pelo número encontrado:

    uv run --locked python -m monitoring.collect --url http://127.0.0.1:8080 --pid PID_DO_SERVIDOR --interval 0.1 --duration 30 --output results/metrics/cpp

Envie requisições durante a janela de monitoramento, mantendo o servidor ativo até finalizar a exportação.

Repita o procedimento para o servidor Python, ajustando URL, PID e pasta de saída.

Para comparação válida, use a mesma matriz, sinais, parâmetros numéricos, quantidade de workers e condições de máquina.

Se a carga não tiver terminado dentro da janela observada, `workload_complete` será falso e algumas estatísticas de tempo não serão comparáveis.

Para detalhes, consulte [Coleta de métricas](docs/tests/task-16-performance-metrics.md).

## 13. Comparar estatísticas

Após produzir os diretórios de coleta das duas implementações:

    uv run --locked python -m monitoring.statistics results/metrics/python results/metrics/cpp --output results/comparison

Os arquivos gerados são:

- `comparison.csv`
- `comparison.json`
- `comparison.md`

Os valores seguem a metodologia da [TASK-17](docs/tests/task-17-statistics.md).

## 14. Gerar gráficos comparativos

Com os exports válidos de Python e C++ disponíveis:

    MPLBACKEND=Agg uv run --locked python -m monitoring.plots results/metrics/python results/metrics/cpp --output results/plots

O gerador exporta:

- `cpu_comparison.png`
- `memory_comparison.png`
- `total_execution_time.png`
- `mean_reconstruction_time.png`
- `image_counts.png`
- `plots_manifest.json`

Os gráficos finais devem usar dados de experimentos reais, e não apenas fixtures de teste.

Consulte [Gráficos comparativos](docs/tests/task-22-comparative-plots.md).

## 15. Testes de carga e saturação

A TASK-18 fornece um executor que inicia automaticamente servidores e três clientes concorrentes, com cargas progressivas.

Quando `monitoring/saturation.py` estiver presente na versão utilizada, execute:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m monitoring.saturation --implementations python cpp --levels 15 30 60 --workers 1 --queue-capacity 8 --monitor-seconds 3 --drain-timeout 20

O modelo `demo_identity_3` é pequeno: ele valida o fluxo e a concorrência, mas pode não provocar saturação.

Para uma matriz sintética mais exigente, siga as instruções da TASK-18 quando essa implementação estiver integrada à branch principal.

Não trate resultados de modelos sintéticos como desempenho de matrizes experimentais reais.

## 16. Estrutura de diretórios

    .
    ├── client/          Cliente HTTP, sinais e execução de experimentos
    ├── server/
    │   ├── python/      Servidor FastAPI e CGNR Python
    │   └── cpp/         Servidor HTTP e CGNR C++
    ├── models/          Catálogo e matrizes CSV
    ├── monitoring/      Coleta, estatísticas e gráficos
    ├── scripts/         Exemplos e utilitários
    ├── tests/
    │   ├── unit/        Testes unitários
    │   ├── integration/ Testes de integração
    │   ├── environment/ Testes do ambiente
    │   └── api/         Testes HTTP/API
    ├── docs/            Arquitetura, instalação e documentação técnica
    ├── CMakeLists.txt   Configuração de compilação C++
    ├── pyproject.toml   Dependências Python
    ├── uv.lock          Versões travadas das dependências
    └── README.md        Guia principal

Diretórios criados localmente, como `build/`, `.venv/` e `results/`, não devem ser tratados como código-fonte versionado.

## 17. Reprodutibilidade e limitações

- Use Python 3.12 e o arquivo `uv.lock`.
- Compile C++ em modo Release para ensaios de desempenho.
- Controle as threads BLAS usando `OPENBLAS_NUM_THREADS=1` e `OMP_NUM_THREADS=1`.
- Execute as implementações sob cargas equivalentes.
- Registre CPU, memória, sistema operacional e configuração dos experimentos.
- Não compare estatísticas de ensaios incompletos.
- Considere que os resultados de reconstrução são mantidos em memória e possuem política de retenção.
- Não exponha os servidores sem controles adicionais de segurança.
- Diferencie a validação funcional com matrizes demonstrativas da avaliação experimental de desempenho.

## 18. Documentação complementar

- [Configuração do ambiente](docs/development-setup.md)
- [Tecnologias utilizadas](docs/stack.md)
- [Arquitetura cliente-servidor](docs/architecture/client-server.md)
- [Cliente HTTP e protocolo](docs/tests/task-09-client-server.md)
- [Servidor Python](docs/tests/task-12-python-server.md)
- [Servidor C++](docs/tests/task-13-cpp-server.md)
- [Concorrência e controle de fila](docs/tests/task-15-queue-concurrency.md)
- [Métricas de desempenho](docs/tests/task-16-performance-metrics.md)
- [Análise estatística](docs/tests/task-17-statistics.md)
- [Integração completa](docs/tests/task-20-full-integration.md)
- [Gráficos comparativos](docs/tests/task-22-comparative-plots.md)

## 19. Verificação da entrega

A TASK-24 será considerada concluída após validar, seguindo estas instruções:

1. Instalação das dependências Python.
2. Configuração e compilação C++.
3. Inicialização independente dos dois servidores.
4. Consulta dos endpoints de saúde e catálogo.
5. Envio e recuperação de uma reconstrução pelo cliente.
6. Execução dos testes automatizados.
7. Geração de métricas e gráficos com dados válidos.

O objetivo é que outra pessoa consiga instalar e executar o projeto utilizando apenas este README e os documentos complementares vinculados.
