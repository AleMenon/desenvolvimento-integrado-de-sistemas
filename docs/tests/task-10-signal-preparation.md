# TASK-10 — Preparação Reproduzível de Sinais no Cliente

## 1. Objetivo

Implementar a preparação de sinais experimentais no cliente Python, incluindo carregamento de dados, seleção aleatória do modelo matricial, cálculo e aplicação de ganho, geração de sequências e reprodução dos mesmos experimentos nos servidores Python e C++.

A implementação utiliza o contrato HTTP/JSON definido na TASK-09, sem exigir alterações nos servidores.

## 2. Arquivos Implementados

| Arquivo | Responsabilidade |
| --- | --- |
| `client/signal_preparation.py` | Carregamento, validação, cálculo de ganho e persistência do plano experimental. |
| `client/experiment_runner.py` | Preparação e envio da mesma sequência aos dois servidores. |
| `tests/unit/test_signal_preparation.py` | Testes de carregamento, ganho, reprodutibilidade e persistência. |
| `tests/unit/test_experiment_runner.py` | Testes de compatibilidade, envio e falhas parciais. |
| `tests/integration/test_task10_http.py` | Teste de integração HTTP com o cliente real da TASK-09. |

## 3. Carregamento dos Sinais Experimentais

Os sinais são carregados de arquivos CSV numéricos, sem cabeçalho, utilizando NumPy e representação `float64`.

A validação rejeita sinais vazios, multidimensionais, contendo valores não finitos ou com tamanho incompatível com o modelo.

Os dados analisados na TASK-08 utilizam os seguintes formatos:

| Modelo Experimental | Elementos por Sinal | Dimensões da Imagem |
| --- | ---: | --- |
| H-2 | 27.904 | 30 × 30 |
| H-1 | 50.816 | 60 × 60 |

Os arquivos experimentais de grande porte não são versionados no repositório.

O identificador enviado pelo cliente deve corresponder ao `model_id` disponibilizado pelos servidores.

## 4. Cálculo e Aplicação do Ganho

A implementação atual utiliza uma proposta de normalização pela amplitude RMS (*Root Mean Square*).

Para um sinal com N amostras:

    RMS = sqrt(sum(sinal[i]²) / N)
    ganho = RMS_desejado / RMS_original
    sinal_preparado = sinal_original × ganho

O valor padrão de `target_rms` é 1.0, podendo ser configurado na criação do plano.

Sinais nulos e ganhos inválidos são rejeitados.

**Observação:** a normalização por RMS é uma decisão técnica provisória. A fórmula precisa ser confirmada com a especificação do experimento antes da aprovação definitiva deste requisito.

## 5. Seleção Aleatória e Reprodutibilidade

A seleção utiliza `numpy.random.default_rng(seed)`.

A partir de uma semente fixa, o cliente:

1. Ordena os identificadores dos modelos disponíveis.
2. Seleciona aleatoriamente um modelo.
3. Ordena os arquivos de sinais associados ao modelo.
4. Seleciona uma sequência de sinais, permitindo repetição.
5. Calcula o ganho correspondente a cada sinal.
6. Registra o plano experimental em JSON.

A sequência padrão contém 15 sinais, mas a quantidade é configurável.

O plano registra:

- Versão do formato (`schema_version`);
- Semente aleatória (`seed`);
- RMS desejado (`target_rms`);
- Posição de cada sinal na sequência;
- Identificadores de modelo e sinal;
- Caminho absoluto do arquivo CSV;
- Hash SHA-256 do arquivo;
- Ganho calculado.

O hash permite detectar alterações no conteúdo dos sinais antes do envio.

## 6. Exemplo de Criação do Plano

Os caminhos abaixo são ilustrativos e exigem arquivos CSV existentes:

    from client.signal_preparation import create_plan, save_plan

    models = {
        "mock_3": [
            "build/data/signal-a.csv",
            "build/data/signal-b.csv",
        ]
    }

    plan = create_plan(
        models,
        seed=42,
        count=15,
        target_rms=2.0,
    )

    save_plan(plan, "build/results/task-10/plan.json")

## 7. Reutilização nos Servidores Python e C++

O mesmo plano pode ser carregado do JSON e enviado para duas implementações independentes:

    from client.reconstruction_client import ReconstructionClient
    from client.signal_preparation import load_plan
    from client.experiment_runner import submit_plan_to_servers

    plan = load_plan("build/results/task-10/plan.json")

    python_client = ReconstructionClient("http://127.0.0.1:8000")
    cpp_client = ReconstructionClient("http://127.0.0.1:8080")

    submissions = submit_plan_to_servers(
        plan,
        python_client,
        cpp_client,
        client_id="cliente-01",
        max_iterations=10,
        tolerance=1e-8,
    )

Os dois servidores devem estar ativos e disponibilizar modelos compatíveis com os identificadores, dimensões e metadados utilizados pelo plano.

O cliente valida os sinais antes de iniciar a transmissão e aplica o mesmo ganho a cada sinal enviado.

Para cada elemento da sequência, os servidores recebem os mesmos valores e parâmetros numéricos, na mesma ordem de submissão.

O envio é assíncrono: os identificadores retornados podem ser utilizados posteriormente para consultar estados e resultados por meio do `ReconstructionClient`.

## 8. Tratamento de Falhas Parciais

A classe `PartialSubmissionError` registra as requisições com aceitação confirmada até o momento de uma falha.

Cada registro pode conter:

- Posição e identificador do sinal;
- Modelo selecionado;
- Ganho aplicado;
- Identificador retornado pelo servidor Python;
- Identificador retornado pelo servidor C++.

Em caso de timeout, não é possível garantir que a requisição tenha sido rejeitada pelo servidor remoto. Por isso, a implementação não realiza reenvio automático.

Não existe garantia de envio atômico entre os dois servidores.

## 9. Testes Automatizados

Os testes específicos da TASK-10 verificam:

- Carregamento e validação de sinais CSV;
- Cálculo e aplicação do ganho RMS;
- Rejeição de sinais nulos;
- Seleção reproduzível com semente fixa;
- Verificação de integridade dos arquivos;
- Persistência e carregamento de planos JSON;
- Rejeição de planos inválidos;
- Compatibilidade das dimensões dos modelos;
- Identidade dos dados enviados aos dois clientes;
- Preservação do histórico em falhas parciais;
- Integração HTTP com duas instâncias de servidor simulado.

Execução:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m pytest tests/unit/test_signal_preparation.py tests/unit/test_experiment_runner.py tests/integration/test_task10_http.py -q

Na última execução, os 12 testes específicos da TASK-10 foram aprovados.

Os testes HTTP utilizam duas instâncias do servidor mock da TASK-09. Portanto, validam o envio e o contrato de comunicação, mas não a equivalência numérica dos servidores CGNR reais.

## 10. Limitações e Próximas Validações

- Confirmar a fórmula de ganho exigida pelo experimento.
- Validar o fluxo ponta a ponta com os servidores Python e C++ reais.
- Confirmar a identidade matemática dos modelos utilizados por ambas as implementações.
- Disponibilizar localmente os sinais experimentais de grande porte.
- Considerar a portabilidade dos caminhos absolutos armazenados no JSON.
- Registrar os resultados de execução e os identificadores retornados por cada servidor para comparação posterior.

## 11. Critério de Aceite

A implementação prepara sinais numéricos, aplica ganho configurável e permite reproduzir a mesma seleção e sequência nos dois servidores.

A validação automatizada atual cobre os módulos de preparação e a integração com servidores simulados.

A confirmação definitiva do requisito de ganho e a validação com dados experimentais e servidores reais permanecem pendentes.
