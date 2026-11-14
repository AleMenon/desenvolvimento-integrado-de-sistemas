# TASK-13 — Servidor C++ para reconstrução de imagens

## Implementação

O executável `reconstruction_server` implementa em C++17 a interface HTTP/JSON da TASK-09, reutilizando o CGNR da TASK-07. Utiliza `cpp-httplib`, `nlohmann/json`, Eigen e OpenBLAS.

- `GET /health`: disponibilidade do servidor.
- `GET /models` e `GET /models/{model_id}`: catálogo e metadados.
- `POST /reconstructions`: valida sinal e parâmetros, devolve HTTP 202 e `request_id`.
- `GET /reconstructions/{request_id}`: estado (`queued`, `running`, `completed`, `failed`) e horários UTC.
- `GET /reconstructions/{request_id}/result`: vetor, formato da imagem e metadados. Enquanto não concluída, retorna HTTP 409.

Os erros seguem `{ "error": { "code": "...", "message": "..." } }` com códigos HTTP apropriados (400, 404, 409, 413, 415, 422 e 503). O servidor executa uma reconstrução de cada vez e usa uma fila em memória limitada (64 pendências por padrão). As requisições processadas ficam em memória até o encerramento do processo; não há persistência ou retomada após reinício.

## Compilação e execução

No Arch Linux, instalar: `sudo pacman -S --needed base-devel cmake eigen openblas`. `cpp-httplib` e `nlohmann/json` são procurados no sistema pelo CMake; quando ausentes, serão baixados pelo FetchContent (requer conexão no primeiro build).

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/reconstruction_server --host 127.0.0.1 --port 8080 --catalog models/catalog.json
```

Testar usando o cliente existente:

```python
from client.reconstruction_client import ReconstructionClient

client = ReconstructionClient("http://127.0.0.1:8080")
print(client.reconstruct("cliente-01", "sinal-01", "demo_identity_3", [1, 2, 3]))
```

`models/catalog.json` inclui um exemplo com matriz identidade 3×3 para o servidor funcionar imediatamente. Para utilizar os dados do professor, descompactar as matrizes em CSV numérico sem cabeçalho, criar entradas com `model_id`, `file`, `image_shape` e `version` no catálogo e informar o caminho em `--catalog`. O arquivo de matriz é resolvido relativamente ao catálogo. Cada linha do CSV corresponde a uma linha de H, cada coluna a um pixel, e `image_shape[0] * image_shape[1]` deve ser igual ao número de colunas. As matrizes permanecem carregadas em memória durante a execução; matrizes grandes exigem RAM suficiente.

## Testes

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  uv run python -m pytest tests/integration/test_cpp_server.py -v
```

Os testes iniciam o servidor em porta local efêmera, exercitam o `ReconstructionClient` real, conferem os metadados, rejeições de entrada, três clientes simultâneos e a equivalência da saída CGNR com o Python para a matriz identidade. Esta entrega **não** mede desempenho nem implementa geração dos 15 sinais por cliente.

**Limitações:** os modelos reais ainda precisam ser adicionados; o catálogo é local e de confiança; o formato HTTP/JSON de vetores grandes pode ser custoso; o servidor não oferece autenticação nem persistência. Usar `127.0.0.1` em testes locais. O relatório comparativo de desempenho é escopo posterior.


### Testes de concorrência e falhas (revisão da TASK-13)

Além do fluxo principal, `test_cpp_server.py` inclui cenários de falha numérica
(`failed`), resultado ainda indisponível (`409 RESULT_NOT_READY`) e
saturação de fila (`503 QUEUE_FULL`). A falha numérica utiliza uma matriz
1×1 com valor `1e-200` para provocar `numerical_breakdown` no CGNR.

Os testes da fila utilizam uma trava por arquivo para controlar o avanço do
worker, sem depender da velocidade de execução. O mecanismo só é compilado
quando `BUILD_TESTING=ON` e só é acionado quando a variável de ambiente
`TASK13_TEST_GATE_FILE` aponta para um arquivo existente. O próprio pytest
cria e remove esse arquivo. **Não utilize essa variável ao executar o
servidor normalmente.**

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build -j
uv run python -m pytest tests/integration/test_cpp_server.py -v
```
