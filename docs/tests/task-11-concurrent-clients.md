# TASK-11 — Execução Simultânea de Clientes

## 1. Objetivo

Implementar a execução simultânea de pelo menos três clientes experimentais, com envio de no mínimo 15 sinais por cliente, intervalos aleatórios, identificadores únicos e registro das requisições realizadas.

A implementação reutiliza a preparação reproduzível de sinais da TASK-10 e o cliente HTTP da TASK-09.

O objetivo é permitir que os servidores Python e C++ recebam entradas experimentais equivalentes, mesmo quando vários clientes estão enviando requisições simultaneamente.

## 2. Requisitos da Issue

| Requisito | Implementação |
| --- | --- |
| Três clientes simultâneos | ThreadPoolExecutor com uma tarefa por cliente. |
| Pelo menos 15 sinais por cliente | Validação do tamanho mínimo de cada plano. |
| Intervalos aleatórios | Atrasos configuráveis com geradores independentes por cliente. |
| Identificação única dos clientes | Identificadores associados às entradas de `plans`. |
| Identificação única dos sinais | Prefixo com o ID do cliente e posição da sequência. |
| Registro das requisições | Relatório estruturado e persistência JSON. |
| Entradas equivalentes nos dois servidores | Reutilização do sinal preparado e dos parâmetros para cada par de envios. |

Na configuração mínima, são 45 sinais experimentais distribuídos entre três clientes, resultando em 90 submissões HTTP: 45 ao servidor Python e 45 ao servidor C++.

## 3. Arquivos da Implementação

| Arquivo | Responsabilidade |
| --- | --- |
| `client/concurrent_experiment.py` | Gerenciamento da execução simultânea, intervalos, resultados e erros. |
| `client/experiment_runner.py` | Envio de cada plano aos dois servidores; recebeu parâmetros opcionais de callback e prefixo de sinal. |
| `client/signal_preparation.py` | Preparação reproduzível dos sinais, desenvolvida na TASK-10. |
| `client/reconstruction_client.py` | Comunicação HTTP, desenvolvida na TASK-09. |
| `tests/unit/test_concurrent_experiment.py` | Testes de concorrência, identificação, intervalos e falhas. |
| `tests/integration/test_task11_http.py` | Integração HTTP com três clientes e duas instâncias de servidor simulado. |

As alterações no executor da TASK-10 são retrocompatíveis: quando os novos parâmetros opcionais não são informados, a função mantém o comportamento anterior.

## 4. Arquitetura de Execução

A função principal é `run_concurrent_experiment`.

Ela recebe um dicionário de planos, indexados pelo identificador de cada cliente, e uma função fábrica que cria os dois clientes HTTP utilizados por cada execução.

O sistema utiliza `ThreadPoolExecutor` para iniciar uma tarefa por cliente. Cada tarefa realiza suas submissões sequencialmente, enquanto diferentes clientes podem operar simultaneamente.

Fluxo de execução:

1. Validar a quantidade de clientes e os planos recebidos.
2. Ordenar os identificadores de clientes.
3. Criar uma tarefa de execução para cada cliente.
4. Preparar os intervalos reproduzíveis de cada tarefa.
5. Consultar os metadados dos modelos em ambos os servidores.
6. Validar e preparar a sequência completa de sinais.
7. Enviar cada sinal preparado primeiro ao servidor Python e depois ao servidor C++.
8. Registrar identificadores de requisição, posição, ganho, horário e atraso programado.
9. Consolidar os resultados ou preservar as informações parciais quando ocorrer um erro.

A execução concorrente não garante uma ordem global fixa entre clientes. A ordem de cada sequência individual é preservada.

O uso de threads é apropriado principalmente para a concorrência dos envios HTTP e dos intervalos de espera. Ele não equivale a três processos Python independentes executando cálculos CGNR.

## 5. Identificadores

Cada cliente possui um identificador exclusivo, como:

    cliente-01
    cliente-02
    cliente-03

Cada sinal enviado recebe um identificador que combina:

- ID do cliente;
- Identificador original do arquivo de sinal;
- Posição da sequência.

Formato:

    cliente-01:sinal-a-000
    cliente-01:sinal-b-001
    cliente-02:sinal-a-000

Isso evita que clientes diferentes utilizem o mesmo `signal_id` para envios distintos.

O mesmo par `(client_id, signal_id)` é utilizado nos dois servidores, permitindo identificar a correspondência entre as submissões.

Os identificadores são únicos dentro de uma execução quando cada cliente possui um ID diferente e cada posição aparece apenas uma vez no plano.

## 6. Intervalos Aleatórios Reproduzíveis

Os intervalos são gerados individualmente por cliente utilizando `random.Random`.

A semente de cada gerador deriva de um SHA-256 aplicado à combinação da semente experimental e do identificador do cliente.

Isso evita que os atrasos dependam da ordem de escalonamento das threads.

Parâmetros:

| Parâmetro | Descrição |
| --- | --- |
| `seed` | Semente base do experimento. |
| `min_interval` | Menor atraso permitido, em segundos. |
| `max_interval` | Maior atraso permitido, em segundos. |
| `sleep_fn` | Função de espera, substituível durante testes. |

O primeiro envio de cada cliente não recebe uma espera inicial. Os envios seguintes utilizam os atrasos sorteados.

A reprodutibilidade refere-se aos atrasos programados e à sequência experimental, não aos horários reais de execução, que dependem do sistema operacional e da rede.

## 7. Garantia das Entradas Experimentais

Cada cliente utiliza um plano produzido pela TASK-10.

O executor:

1. Consulta os modelos nos dois servidores.
2. Verifica a compatibilidade dos metadados disponíveis.
3. Confere a integridade dos arquivos por SHA-256.
4. Aplica os ganhos definidos no plano.
5. Envia os mesmos valores e parâmetros ao Python e ao C++.

Os sinais são previamente preparados e validados antes da transmissão de cada plano.

A implementação garante a equivalência dos dados que o cliente solicita enviar. Ela não garante que ambos os servidores aceitem ou concluam todos os trabalhos quando ocorrerem erros de comunicação ou processamento.

Também não realiza comparação numérica das imagens reconstruídas durante a função de envio; essa validação pertence aos testes de integração e aos experimentos comparativos.

## 8. Exemplo de Utilização

O exemplo abaixo pressupõe que três planos da TASK-10 já foram gerados e salvos e que os dois servidores estejam ativos.

    from client.concurrent_experiment import (
        run_concurrent_experiment,
        save_experiment_log,
        ConcurrentExperimentError,
    )
    from client.reconstruction_client import ReconstructionClient
    from client.signal_preparation import load_plan

    plans = {
        "cliente-01": load_plan("build/plans/cliente-01.json"),
        "cliente-02": load_plan("build/plans/cliente-02.json"),
        "cliente-03": load_plan("build/plans/cliente-03.json"),
    }

    def client_factory(client_id):
        return (
            ReconstructionClient("http://127.0.0.1:8000"),
            ReconstructionClient("http://127.0.0.1:8080"),
        )

    try:
        report = run_concurrent_experiment(
            plans,
            client_factory,
            seed=42,
            min_interval=0.01,
            max_interval=0.10,
        )
    except ConcurrentExperimentError as error:
        save_experiment_log(error, "build/results/task-11/partial.json")
        raise
    else:
        save_experiment_log(report, "build/results/task-11/experiment.json")

Os endereços e as portas são ilustrativos e devem corresponder às instâncias reais em execução.

A fábrica cria objetos `ReconstructionClient` distintos para cada tarefa, evitando compartilhar indiscriminadamente a mesma sessão HTTP entre threads.

## 9. Estrutura do Relatório Experimental

O relatório JSON contém:

- `schema_version`: versão da estrutura do relatório;
- `seed`: semente utilizada;
- `min_interval` e `max_interval`: limites dos atrasos;
- `client_count`: quantidade de clientes;
- `total_signals`: quantidade de sinais registrados;
- `total_http_submissions`: total de aceitações confirmadas pelos servidores;
- `clients`: resultados individuais;
- `status`: estado consolidado da execução;
- `errors`: erros identificados por cliente.

Cada cliente pode registrar:

- Identificador e estado;
- Horários de início e término;
- Duração total;
- Quantidade de sinais;
- Lista de submissões.

Cada submissão registra a posição do sinal, modelo, identificador, ganho, atraso programado, horário de despacho e os IDs das requisições aceitas por cada servidor.

O relatório não inclui os valores completos dos sinais, para evitar duplicação desnecessária de arquivos experimentais grandes. Os planos da TASK-10 devem ser preservados separadamente para permitir a reprodução da execução.

## 10. Tratamento de Falhas Parciais

A classe `ConcurrentExperimentError` disponibiliza:

- `results`: resultados conhecidos de todos os clientes;
- `errors`: descrição das falhas;
- `report`: relatório consolidado que pode ser salvo em JSON.

Se um cliente falhar durante um envio, os demais continuam suas execuções.

Quando há uma falha parcial reconhecida pelo executor, são preservados os IDs das requisições que tiveram aceitação confirmada, além dos horários e da duração da execução do cliente afetado.

Por exemplo, se o servidor Python confirmar o terceiro sinal de um cliente, mas o servidor C++ falhar nesse envio, o registro mantém o `python_request_id` e deixa o `cpp_request_id` sem valor.

Em caso de timeout, a ausência de ID confirmado não significa necessariamente que o servidor rejeitou o trabalho.

A implementação não utiliza transações distribuídas nem realiza reenvio automático. O operador deve analisar o histórico antes de repetir um experimento parcialmente executado.

## 11. Testes Automatizados

### 11.1 Testes Unitários

Os testes da TASK-11 verificam:

- Três clientes enviando 15 sinais cada;
- Total de 45 sinais e 90 submissões;
- Equivalência entre os dados solicitados aos servidores;
- Intervalos reproduzíveis para a mesma semente;
- Rejeição de menos de três clientes;
- Rejeição de planos com menos de 15 sinais;
- Persistência JSON do relatório;
- Identificação única dos sinais entre clientes;
- Sobreposição real da execução de três threads, utilizando uma barreira;
- Preservação dos IDs confirmados após uma falha parcial;
- Salvamento de relatório parcial após falha.

### 11.2 Integração HTTP

O teste `tests/integration/test_task11_http.py` utiliza três clientes concorrentes e duas instâncias HTTP do servidor mock.

Ele verifica a execução com 45 sinais, 90 submissões, IDs únicos, identificação dos clientes e equivalência dos vetores retornados pelas duas instâncias simuladas.

Esse teste utiliza comunicação HTTP real, porém não executa o algoritmo CGNR nos servidores simulados.

### 11.3 Regressão da TASK-10

Também são executados testes do executor anterior para garantir que os parâmetros opcionais não alteraram o comportamento existente.

### 11.4 Comandos

Executar os testes específicos:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m pytest tests/unit/test_concurrent_experiment.py tests/integration/test_task11_http.py -q

Executar a suíte Python completa:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m pytest tests/ -q

Executar a suíte C++ após compilar:

    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build -j 2
    ctest --test-dir build --output-on-failure

### 11.5 Resultados da Última Execução

| Verificação | Resultado |
| --- | --- |
| Testes específicos e de regressão selecionados | 15 aprovados |
| Suíte Python completa | 147 aprovados, 4 ignorados |
| CTest | 2 de 2 aprovados |
| Falhas de teste | Nenhuma |

Os quatro testes ignorados pertencem à suíte geral e não representam falhas da execução concorrente.

## 12. Limitações Conhecidas

### 12.1 Servidores Reais

O teste completo de 90 envios foi realizado com servidores HTTP simulados.

A validação simultânea contra os servidores Python e C++ reais ainda depende da disponibilidade e integração das implementações correspondentes.

### 12.2 Resultados das Reconstruções

O executor registra confirmações de submissão, mas não aguarda automaticamente o término de todos os cálculos CGNR.

O estado final `completed` do relatório indica que os envios foram concluídos, não que todas as reconstruções foram finalizadas pelos servidores.

### 12.3 Concorrência e Agendamento

As threads começam de forma concorrente, porém não existe garantia de simultaneidade exata em cada envio.

A ordem entre clientes, a latência da rede e o tempo de espera real variam entre execuções.

### 12.4 Memória e Dados Experimentais

A TASK-10 prepara a sequência de sinais antes dos envios de cada cliente. O consumo de memória depende do tamanho dos vetores e da quantidade de clientes ativos.

Os arquivos CSV são referenciados por caminhos absolutos nos planos, o que exige atenção ao reproduzir o experimento em outra máquina.

### 12.5 Persistência e Falhas Não Tratadas

O histórico é salvo explicitamente ao final da execução ou no tratamento de `ConcurrentExperimentError`.

Falhas durante a criação de clientes ou preparação inicial são registradas por cliente, permitindo que as demais tarefas concluam seus envios. Nesses casos, ainda não existem IDs de submissão confirmados para o cliente afetado. Uma interrupção abrupta do processo pode impedir a gravação do relatório.

Não há mecanismo de recuperação automática após encerramento abrupto do processo.

### 12.6 Intervalos de Envio

Os intervalos são aplicados antes de cada par de submissões. O segundo servidor recebe o sinal após a resposta do primeiro; os dois envios do mesmo sinal não são simultâneos.

## 13. Integração com Outras Tarefas

| Tarefa | Relação |
| --- | --- |
| TASK-09 | Comunicação HTTP/JSON com os servidores. |
| TASK-10 | Geração dos planos, seleção e ganho dos sinais. |
| TASK-12 | Servidor Python real para reconstruções. |
| TASK-13 | Servidor C++ real para reconstruções. |
| TASK-14 | Geração de relatórios de imagens a partir dos resultados. |
| TASK-18 | Testes de saturação com cargas progressivas. |
| TASK-20 | Testes completos de integração entre clientes e servidores. |
| TASK-21 | Benchmarks comparativos reproduzíveis. |

## 14. Critério de Aceite

A implementação executa três clientes concorrentes com pelo menos 15 sinais por cliente e registra as 90 submissões esperadas para os dois destinos HTTP.

Os testes automatizados comprovam a concorrência das threads, a reprodutibilidade dos intervalos, os identificadores únicos e o tratamento das falhas parciais.

A validação funcional com servidores simulados foi concluída. A execução completa contra os servidores CGNR reais permanece como etapa de integração do projeto.
