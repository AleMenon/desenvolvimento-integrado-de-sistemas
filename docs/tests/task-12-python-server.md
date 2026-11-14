# TASK-12 — Implementação do Servidor Python de Reconstrução

## 1. Objetivo

Implementar um servidor HTTP em Python capaz de receber sinais experimentais, validar as requisições, identificar o modelo matricial correspondente, executar o algoritmo CGNR e disponibilizar a imagem reconstruída e os metadados do processamento.

A implementação segue o contrato de comunicação da TASK-09 e reutiliza diretamente o algoritmo CGNR desenvolvido na TASK-06.

O processamento é realizado por um worker separado, enquanto a API permite consultar o estado de cada reconstrução.

## 2. Escopo da Implementação

A TASK-12 contempla:

1. Interface HTTP/JSON utilizando FastAPI.
2. Recebimento de sinais enviados pelos clientes.
3. Validação de identificadores, dimensões, valores e parâmetros.
4. Consulta ao catálogo de modelos matriciais.
5. Execução do CGNR com NumPy e precisão `float64`.
6. Disponibilização do vetor de imagem reconstruída.
7. Retorno de metadados numéricos e de execução.
8. Tratamento de erros de comunicação e processamento.
9. Testes unitários e testes reais de integração HTTP.

A implementação inicial utiliza uma matriz de demonstração 3 × 3 para permitir testes reproduzíveis sem depender dos arquivos experimentais de grande porte.

## 3. Organização dos Arquivos

| Arquivo | Responsabilidade |
| --- | --- |
| `server/python/reconstruction_server.py` | Aplicação FastAPI, rotas HTTP, validação, armazenamento de requisições e worker CGNR. |
| `server/python/model_catalog.py` | Carregamento de matrizes, validação dimensional e metadados dos modelos. |
| `server/python/cgnr.py` | Algoritmo CGNR existente, reutilizado da TASK-06. |
| `models/catalog.json` | Descrição dos modelos disponibilizados pelo servidor. |
| `models/demo_identity_3.csv` | Matriz identidade 3 × 3 utilizada nos testes. |
| `tests/unit/test_model_catalog.py` | Testes do catálogo e validação de modelos. |
| `tests/unit/test_reconstruction_service.py` | Testes de validação, erros, fila e processamento. |
| `tests/integration/test_python_reconstruction_server.py` | Testes HTTP com Uvicorn e o `ReconstructionClient` real. |

## 4. Dependências

O projeto declara as dependências necessárias em `pyproject.toml`, incluindo:

- Python 3.12 ou superior;
- FastAPI;
- Uvicorn;
- NumPy;
- Requests;
- Pytest.

A instalação e execução podem ser realizadas com `uv` e o arquivo de lock existente.

## 5. Como Executar o Servidor

A partir da raiz do repositório, executar:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked uvicorn server.python.reconstruction_server:app --host 127.0.0.1 --port 8000

O endereço padrão deste exemplo é:

    http://127.0.0.1:8000

A documentação interativa gerada automaticamente pelo FastAPI pode ser consultada em:

    http://127.0.0.1:8000/docs

O servidor inicia o catálogo e o worker no ciclo de vida da aplicação, utilizando o mecanismo `lifespan` do FastAPI.

A porta 8000 é apenas uma sugestão e pode ser modificada.

## 6. Catálogo de Modelos

O catálogo descreve as matrizes que podem ser selecionadas por `model_id`.

Exemplo de `models/catalog.json`:

    {
      "models": [
        {
          "model_id": "demo_identity_3",
          "file": "demo_identity_3.csv",
          "image_shape": [1, 3],
          "version": "1.0"
        }
      ]
    }

O caminho do arquivo matricial é interpretado relativamente ao diretório do catálogo.

A implementação inicial carrega matrizes CSV numéricas completas para memória RAM.

O catálogo verifica:

- Existência do arquivo do modelo;
- Identificadores não vazios e não duplicados;
- Formato bidimensional da matriz;
- Ausência de valores NaN e infinito;
- Dimensões válidas para a imagem;
- Compatibilidade entre o número de colunas e o produto de `image_shape`;
- Versão não vazia.

Para cada modelo, são disponibilizados metadados como `rows`, `columns`, `image_shape`, `data_type`, `version` e `checksum_sha256`.

O hash SHA-256 é calculado sobre os bytes do arquivo CSV original, e não diretamente sobre os valores numéricos normalizados.

### 6.1 Modelo de Demonstração

O modelo `demo_identity_3` possui a matriz:

    1,0,0
    0,1,0
    0,0,1

Como a matriz é identidade, o sistema Hx = g tem solução x = g.

Isso permite testar a reconstrução com uma resposta conhecida.

## 7. Endpoints HTTP

### 7.1 GET /health

Verifica se a API está respondendo.

Resposta HTTP 200:

    {
      "status": "ok"
    }

Este endpoint verifica a disponibilidade da API; não executa uma reconstrução de diagnóstico.

### 7.2 GET /models

Lista os metadados dos modelos carregados.

Resposta HTTP 200, em formato resumido:

    {
      "models": [
        {
          "model_id": "demo_identity_3",
          "rows": 3,
          "columns": 3,
          "image_shape": [1, 3],
          "data_type": "float64",
          "version": "1.0",
          "checksum_sha256": "<hash SHA-256 do arquivo>"
        }
      ]
    }

O hash ilustrado deve ser substituído pelo valor real calculado durante o carregamento.

### 7.3 GET /models/{model_id}

Retorna os metadados de um modelo específico.

Exemplo:

    GET /models/demo_identity_3

Resposta HTTP 200:

    {
      "model_id": "demo_identity_3",
      "rows": 3,
      "columns": 3,
      "image_shape": [1, 3],
      "data_type": "float64",
      "version": "1.0",
      "checksum_sha256": "<hash SHA-256 do arquivo>"
    }

Um modelo inexistente retorna HTTP 404.

### 7.4 POST /reconstructions

Recebe um sinal e registra uma reconstrução para processamento assíncrono.

Exemplo de requisição:

    {
      "client_id": "cliente-01",
      "signal_id": "sinal-01",
      "model_id": "demo_identity_3",
      "algorithm": "cgnr",
      "signal": [2.0, -3.0, 5.0],
      "parameters": {
        "max_iterations": 10,
        "tolerance": 1e-8
      }
    }

A requisição deve utilizar `Content-Type: application/json`.

Resposta de aceitação HTTP 202:

    {
      "request_id": "<identificador UUID>",
      "status": "queued",
      "status_url": "/reconstructions/<identificador UUID>"
    }

O HTTP 202 confirma que a requisição foi aceita; não significa que a reconstrução já terminou.

### 7.5 GET /reconstructions/{request_id}

Consulta o estado da reconstrução.

Estados possíveis:

| Estado | Significado |
| --- | --- |
| `queued` | Requisição aceita e aguardando processamento. |
| `running` | O worker iniciou a reconstrução. |
| `completed` | O resultado está disponível. |
| `failed` | O processamento apresentou uma falha. |

A resposta inclui o identificador, dados da solicitação, estado, horários e informações de erro quando aplicáveis.

Os campos `created_at`, `started_at` e `finished_at` utilizam timestamps UTC em formato ISO 8601, quando disponíveis.

### 7.6 GET /reconstructions/{request_id}/result

Retorna o resultado de uma reconstrução concluída.

Exemplo ilustrativo de resposta HTTP 200:

    {
      "request_id": "<identificador UUID>",
      "status": "completed",
      "result": {
        "vector": [2.0, -3.0, 5.0],
        "shape": [1, 3]
      },
      "metadata": {
        "client_id": "cliente-01",
        "signal_id": "sinal-01",
        "model_id": "demo_identity_3",
        "model_version": "1.0",
        "model_checksum": "<hash SHA-256 do modelo>",
        "algorithm": "cgnr",
        "implementation": "python",
        "iterations": 1,
        "converged": true,
        "stop_reason": "tolerance_reached",
        "residual_norm": 0.0,
        "normal_residual_norm": 0.0,
        "execution_time_ms": 0.1,
        "parameters": {
          "max_iterations": 10,
          "tolerance": 1e-8
        },
        "created_at": "<timestamp UTC>",
        "started_at": "<timestamp UTC>",
        "finished_at": "<timestamp UTC>"
      }
    }

O valor `execution_time_ms` acima é meramente ilustrativo; o tempo efetivo depende da execução.

Se o processamento ainda estiver pendente, este endpoint retorna HTTP 409.

## 8. Execução do Algoritmo CGNR

Após validar a requisição, o serviço localiza a matriz H correspondente ao modelo solicitado e executa o algoritmo da TASK-06:

    result = cgnr(
        matrix,
        signal,
        max_iterations=max_iterations,
        tolerance=tolerance,
    )

A implementação busca aproximar a solução do problema de mínimos quadrados:

    minimizar ||H @ x - g||²

O resultado inclui:

- Vetor solução;
- Número de iterações;
- Indicador de convergência;
- Norma do resíduo;
- Norma do resíduo normal;
- Histórico dos resíduos.

O servidor devolve a solução como um vetor numérico e o formato da imagem separadamente em `shape`.

A API não renderiza um arquivo de imagem nesta etapa; a visualização ou geração de relatórios fica a cargo do cliente.

## 9. Validação das Requisições

Antes de registrar um trabalho, o serviço verifica:

1. Corpo JSON do tipo objeto.
2. Presença dos campos obrigatórios.
3. Identificadores como strings não vazias.
4. Existência do modelo solicitado.
5. Algoritmo igual a `cgnr`.
6. Parâmetros numéricos válidos.
7. Quantidade de amostras igual ao número de linhas da matriz.
8. Valores reais e finitos no sinal.
9. Capacidade disponível na fila.

O limite implementado para `max_iterations` é de 1 a 10, seguindo o cliente da TASK-09.

A tolerância deve ser positiva e finita.

A implementação também limita o corpo das requisições HTTP a 2.000.000 de bytes.

## 10. Tratamento de Erros

Os erros HTTP são representados por um objeto JSON contendo código e mensagem:

    {
      "error": {
        "code": "MODEL_NOT_FOUND",
        "message": "Modelo não encontrado."
      }
    }

Principais respostas implementadas:

| HTTP | Situação |
| --- | --- |
| 400 | Identificador, algoritmo, parâmetros ou sinal inválido. |
| 404 | Modelo ou requisição não encontrado. |
| 409 | Resultado ainda indisponível ou reconstrução que falhou. |
| 413 | Corpo da requisição maior que o limite permitido. |
| 415 | Tipo de conteúdo não suportado. |
| 422 | JSON inválido ou campos obrigatórios ausentes. |
| 503 | Fila cheia ou servidor em encerramento. |

Falhas internas do CGNR são registradas no estado `failed` e não expõem detalhes internos da exceção ao cliente.

Os testes incluem a simulação de uma falha do algoritmo e a conferência do registro do erro.

## 11. Modelo Inicial de Processamento Assíncrono

A aplicação mantém um registro de requisições em memória e utiliza uma fila FIFO limitada.

Fluxo de processamento:

1. O cliente realiza um POST com o sinal.
2. O servidor valida os dados e retorna HTTP 202.
3. O trabalho é inserido na fila.
4. O worker altera o estado para `running`.
5. O algoritmo CGNR executa a reconstrução.
6. O resultado e seus metadados são registrados.
7. O estado passa para `completed` ou `failed`.
8. O cliente consulta o estado e recupera o resultado.

O worker é iniciado durante o ciclo de vida do FastAPI, e não durante a importação do módulo.

A implementação atual usa apenas um worker por processo e capacidade padrão de 64 trabalhos aguardando na fila.

A concorrência avançada, o controle de recursos e o escalonamento mais completo serão tratados na TASK-15.

## 12. Exemplo de Uso com o Cliente da TASK-09

Com o servidor em execução na porta 8000, o cliente pode realizar uma reconstrução da seguinte forma:

    from client.reconstruction_client import ReconstructionClient

    client = ReconstructionClient(
        "http://127.0.0.1:8000"
    )

    reconstruction = client.reconstruct(
        client_id="cliente-01",
        signal_id="sinal-01",
        model_id="demo_identity_3",
        signal=[2.0, -3.0, 5.0],
        max_iterations=10,
        tolerance=1e-8,
        poll_interval=0.01,
        max_polls=100,
    )

    print(reconstruction["result"]["vector"])
    print(reconstruction["metadata"])

Para o modelo de demonstração, o vetor reconstruído esperado é aproximadamente:

    [2.0, -3.0, 5.0]

Esse exemplo confirma a compatibilidade com a interface HTTP da TASK-09.

## 13. Testes Automatizados

### 13.1 Testes Unitários

Os testes do catálogo cobrem:

- Leitura de matriz CSV;
- Consulta e listagem de modelos;
- Modelo inexistente;
- Formato incompatível da imagem;
- Matriz contendo valores não finitos;
- Catálogo ausente;
- Modelo duplicado.

Os testes do serviço cobrem:

- Parâmetros inválidos;
- Erro interno durante a execução do CGNR;
- Limite da fila;
- Rejeição de novas requisições após o encerramento;
- Reconstrução de um sinal nulo.

### 13.2 Testes de Integração HTTP

Os testes iniciam uma instância real do servidor Uvicorn em uma porta local e utilizam o cliente implementado na TASK-09.

As verificações incluem:

- Endpoint de saúde;
- Listagem e consulta de modelos;
- Reconstrução CGNR com matriz identidade;
- Envio, acompanhamento e recuperação de resultados;
- Múltiplas requisições;
- Modelos e requisições inexistentes;
- Dimensões inválidas;
- Algoritmo não suportado;
- Campos ausentes;
- JSON malformado;
- Content-Type inválido.

### 13.3 Comandos de Teste

Executar somente os testes da TASK-12:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m pytest tests/unit/test_model_catalog.py tests/unit/test_reconstruction_service.py tests/integration/test_python_reconstruction_server.py -q

Executar a suíte Python completa:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m pytest tests/ -q

Executar os testes C++ após configurar e compilar o projeto:

    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build -j 2
    ctest --test-dir build --output-on-failure

### 13.4 Resultados da Última Execução

| Verificação | Resultado |
| --- | --- |
| Testes específicos da TASK-12 | 31 aprovados |
| Suíte Python completa | 156 aprovados e 4 ignorados |
| CTest | 2 de 2 aprovados |
| Importação do módulo | Nenhum worker iniciado prematuramente |
| Erros de teste | Nenhum |

Esses resultados foram obtidos usando o modelo de demonstração e os testes existentes no repositório.

## 14. Limitações Conhecidas

### 14.1 Dados Experimentais Reais

A matriz de demonstração tem dimensões reduzidas. Ainda é necessário validar o carregamento e o processamento com as matrizes experimentais reais.

### 14.2 Memória RAM

O catálogo utiliza `numpy.loadtxt` e mantém matrizes densas em memória. Matrizes maiores podem consumir vários gigabytes de RAM.

Uma evolução possível é utilizar armazenamento binário, carregamento eficiente e `numpy.memmap`, desde que sejam preservadas as condições exigidas pelo algoritmo.

### 14.3 Persistência

As requisições, estados e resultados ficam somente em memória. Reiniciar o servidor elimina os registros.

### 14.4 Processamento e Concorrência

Há um worker por processo. O processamento CGNR é sequencial dentro dessa instância.

A capacidade da fila é limitada, mas não existe uma política completa de retenção ou descarte dos resultados já concluídos.

### 14.5 Encerramento

O serviço deixa de aceitar novos trabalhos durante o encerramento e tenta concluir os itens pendentes, aguardando o worker por até 10 segundos.

Para reconstruções longas, o término de todas as tarefas não está garantido antes do encerramento do processo.

### 14.6 Segurança e Acesso

A implementação foi planejada para testes e execução local. Não inclui autenticação, autorização, TLS próprio ou controle de acesso por cliente.

Não deve ser exposta diretamente à Internet sem proteção adicional.

### 14.7 Comparação Python e C++

A integração HTTP real foi validada com o servidor Python.

A equivalência numérica ponta a ponta entre os servidores Python e C++ reais permanece como validação futura, relacionada à integração completa do projeto.

## 15. Relação com Outras Tarefas

| Tarefa | Relação |
| --- | --- |
| TASK-06 | Fornece o algoritmo CGNR em Python. |
| TASK-09 | Define o cliente e o contrato de comunicação HTTP. |
| TASK-10 | Prepara sinais e permite selecionar sequências reproduzíveis. |
| TASK-13 | Implementa o servidor C++ correspondente. |
| TASK-14 | Consome os resultados para gerar relatórios de imagens. |
| TASK-15 | Amplia o controle de fila e concorrência. |
| TASK-16 | Fornece funcionalidades de métricas a serem integradas conforme o projeto. |
| TASK-20 | Realiza validações completas de integração. |

## 16. Critério de Aceite

O servidor Python implementa as operações HTTP necessárias para receber sinais, selecionar modelos matriciais, executar o CGNR e retornar reconstruções e metadados.

A aceitação funcional foi verificada por testes reais HTTP utilizando a matriz de demonstração e o cliente da TASK-09.

O processamento de matrizes experimentais reais, a persistência dos trabalhos e o gerenciamento avançado de concorrência não fazem parte desta validação inicial e permanecem documentados como limitações.


## Tratamento de interrupções numéricas do CGNR

O algoritmo CGNR Python informa explicitamente a causa de parada
por meio do campo `stop_reason`:

- `tolerance_reached`: convergência pelo critério de tolerância;
- `max_iterations`: limite configurado de iterações atingido;
- `numerical_breakdown`: interrupção por problema numérico,
  como divisão inválida, underflow ou valores não finitos.

O servidor registra reconstruções com `tolerance_reached` ou
`max_iterations` como `completed`. Atingir o limite de iterações
não implica necessariamente convergência.

Quando ocorre `numerical_breakdown`, a requisição é registrada
como `failed` e recebe o código de erro `NUMERICAL_BREAKDOWN`.
Nesse caso, não é publicado um resultado de reconstrução concluída.

O servidor também valida a coerência entre `converged`,
`iterations` e `stop_reason`, rejeitando resultados inconsistentes.

Os testes verificam a diferenciação entre convergência,
limite de iterações e falha numérica, além da atualização
do estado HTTP em um cenário simulado de interrupção.
