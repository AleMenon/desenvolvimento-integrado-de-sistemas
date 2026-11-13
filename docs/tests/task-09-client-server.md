# TASK-09 — Comunicação cliente-servidor

## Objetivo
Implementar cliente HTTP/JSON para envio de sinais, identificação de clientes/sinais,
consulta de execução e recebimento de reconstruções, conforme
`docs/architecture/client-server.md` (TASK-02).

## Arquivos
- `client/reconstruction_client.py`: cliente `requests`.
- `scripts/mock_reconstruction_server.py`: servidor de teste HTTP; **não executa CGNR**.
- `scripts/demo_task09.py`: demonstração ponta a ponta.
- `tests/integration/test_client_server.py`: testes automatizados.

## Contrato HTTP/JSON
- `GET /health` retorna `{ "status": "ok" }`.
- `GET /models` lista os modelos e `GET /models/{model_id}` retorna seus metadados.
- `POST /reconstructions` recebe `client_id`, `signal_id`, `model_id`,
  `algorithm: "cgnr"`, `signal` e `parameters: {"max_iterations": 10, "tolerance": 1e-8}`.
  Retorna HTTP **202**, `request_id`, `status: "queued"` e `status_url`.
- `GET /reconstructions/{request_id}` informa `queued`, `running`, `completed` ou `failed`.
- `GET /reconstructions/{request_id}/result` retorna `request_id`, `status: "completed"`,
  `result: {"vector": [...], "shape": [linhas, colunas]}` e `metadata`.
- Falhas usam `{ "error": { "code": "...", "message": "..." } }`.

O mock registra a tarefa imediatamente como concluída, pois **apenas ecoa** o sinal.
Seu modelo fictício `mock_3` aceita três números e retorna `shape: [1, 3]`.
Não representa a matriz real `H-2`. `implementation: "mock"`, `iterations: 0`,
`converged: false` e `stop_reason: "mock_echo"` deixam isso explícito.

A tolerância padrão acompanha o CGNR Python da TASK-06 (`1e-8`); o limite padrão
é 10. Ambos podem ser configurados pelo cliente, respeitando o limite de 10.
O critério de parada numérico das implementações Python/C++ permanece um ponto
a alinhar com as TASK-06/07; o mock não testa equivalência matemática.

## Como executar

Terminal 1:

```bash
uv run python -m scripts.mock_reconstruction_server --port 8765
```

Terminal 2:

```bash
uv run python -m scripts.demo_task09
```

Testes (o servidor de testes usa porta efêmera; não precisa iniciar o mock):

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run python -m pytest tests/integration/test_client_server.py -v
```

Os testes de comparação C++ das outras tarefas exigem previamente o binário
`build/matrix_operations_runner`, gerado por CMake.

## Limites
A geração de sinais, execução simultânea e os servidores reais são tarefas
posteriores. O mock não possui fila real nem processamento assíncrono ou
persistência: apenas simula o contrato de transporte para o aceite da TASK-09.
