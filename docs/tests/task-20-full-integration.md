# TASK-20 — Testes completos de integração

## Objetivo

Executar e validar o fluxo completo de reconstrução utilizando
os servidores HTTP reais Python e C++, os clientes concorrentes
e os relatórios produzidos pelo projeto.

## Cenário de integração

- 3 clientes simultâneos.
- 15 sinais por cliente.
- 45 sinais distintos por posição de execução.
- 45 solicitações para Python.
- 45 solicitações para C++.
- 90 reconstruções esperadas.
- Algoritmo CGNR.
- Modelo demo_identity_3.
- 2 workers por servidor.
- Capacidade de 64 tarefas aguardando por servidor.
- Retenção de 128 resultados por servidor.
- TTL de 3600 segundos.

Os clientes utilizam os mesmos sinais e parâmetros nas
duas implementações.

## Critérios verificados

1. Envio dos sinais para os servidores Python e C++.
2. Aceitação das requisições e obtenção dos request_id.
3. Identificação correta de client_id e signal_id.
4. Recuperação dos resultados das 90 requisições.
5. Validação numérica das reconstruções.
6. Comparação dos resultados Python e C++ por sinal.
7. Ausência de reconstruções pendentes ou com falha.
8. Conferência dos contadores de fila da TASK-15.
9. Conferência das métricas da TASK-16.
10. Persistência e leitura dos relatórios de execução e imagens.

## Execução dos testes

Compilar primeiro o servidor C++:

    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
    cmake --build build -j 4

Executar o teste completo de integração:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m pytest tests/integration/test_task20_full_flow.py -v --tb=short

Executar a suíte completa:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked python -m pytest tests/ -q --tb=short

Executar os testes C++:

    ctest --test-dir build --output-on-failure

## Relatórios

O teste salva dois arquivos temporários:

- execution.json: execução dos clientes e requisições.
- images.json: imagens e metadados reconstruídos.

Os arquivos são reabertos para garantir que os dados
persistidos correspondem aos resultados originais.

## Retenção

O teste configura capacidade para armazenar todos os
resultados do experimento.

A retenção deve ser suficiente para permitir que a TASK-14
recupere as imagens antes de sua remoção.

## Critério de aceite

O fluxo completo deve ser executado sem falhas nas duas
implementações, com 90 reconstruções recuperadas e validadas.

Os relatórios de execução e imagens devem preservar todos
os registros e seus metadados.

## Evidências

Os resultados reais dos testes devem ser registrados
após a execução local.

Não considerar a TASK-20 aprovada apenas pelas respostas
HTTP 202: todas as imagens devem ser recuperadas e verificadas.

## Resultados da validação local

Ambiente: Linux/WSL, Python 3.12, compilação C++ Release.

### Integração real

- Teste: `test_task20_complete_integration`
- Resultado: PASSED.
- Tempo observado: 6,24 segundos.
- Clientes simultâneos: 3.
- Sinais por cliente: 15.
- Requisições aceitas: 90.
- Reconstruções recuperadas: 90.
- Imagens numericamente válidas: 90.
- Falhas e pendências: 0.
- Servidores: Python e C++.
- Relatórios JSON persistidos e conferidos: 2.
- Filas e métricas verificadas.

A comparação numérica considera os sinais preparados pela
TASK-10, incluindo o ganho aplicado antes da transmissão.

### Regressão

A suíte Python e o CTest foram executados com sucesso
após a integração. Os totais detalhados constam no log
da execução local.

### Conclusão

O fluxo completo de integração foi validado sem falhas
nas duas implementações, atendendo ao critério de aceite
da TASK-20.
