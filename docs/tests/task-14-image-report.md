# TASK-14 — Relatório de imagens reconstruídas

## Objetivo

Registrar todas as imagens reconstruídas recebidas pelos clientes,
incluindo metadados e identificação da execução experimental.

## Implementação

O módulo `client/image_report.py` disponibiliza:

- `collect_reconstruction()`: consulta o estado e recupera o resultado.
- `generate_image_report()`: reúne resultados Python e C++.
- `save_image_report()`: persiste o relatório em JSON.

O formato JSON preserva os vetores numéricos e dimensões das imagens.

## Organização do relatório

Cada reconstrução contém:

- `experiment_id`
- `implementation` (Python ou C++)
- `client_id`
- `signal_id`
- `model_id`
- `request_id`
- `position`
- `status`
- `image.vector` e `image.shape`
- `metadata`, incluindo algoritmo, horários e iterações

Reconstruções com falha ou pendentes não são descartadas.
Elas são registradas sem imagem e com o estado correspondente.

## Fluxo de utilização

Após executar `run_concurrent_experiment()`, o resultado pode
ser passado para `generate_image_report()` com uma fábrica de
clientes capaz de consultar os mesmos servidores.

O retorno pode ser persistido com `save_image_report()`.

## Testes

Os testes unitários cobrem armazenamento, falhas,
resultados pendentes e serialização JSON.

O teste de integração utiliza o executor real da TASK-11
com três clientes, 15 sinais por cliente e dois servidores
simulados, verificando 90 reconstruções no relatório.

A validação com servidores HTTP reais constitui uma etapa
adicional de integração.

## Validação HTTP real

O teste `tests/integration/test_image_report_real_servers.py`
inicia os servidores Python e C++ reais e executa o fluxo
de clientes concorrentes da TASK-11.

Resultados verificados:

- 3 clientes simultâneos;
- 15 sinais por cliente;
- 45 reconstruções no servidor Python;
- 45 reconstruções no servidor C++;
- 90 imagens recuperadas e armazenadas;
- identificação de cliente, sinal, modelo e algoritmo;
- horários de início e término;
- quantidade de iterações;
- persistência e leitura do relatório JSON.

A suíte completa foi executada com:

- 220 testes aprovados;
- 4 testes ignorados;
- 2 testes C++ aprovados pelo CTest.
