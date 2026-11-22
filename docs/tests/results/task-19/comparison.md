# TASK-19 — Comparação antes/depois do controle de saturação

Modelo: `task18_dense_512`; três clientes simultâneos; servidor novo em cada execução.

**Validação da campanha:** APROVADA. Todos os pares devem ser estáveis e ter `workload_complete=true`.

| Versão | Sinais/cliente | Repetição | 202 antes/depois | 503 antes/depois | Variação de rejeição (p.p.) | Fila máxima antes/depois | Estável antes/depois |
| --- | ---: | ---: | --- | --- | ---: | --- | --- |
| python | 15 | 1 | 7/9 | 38/36 | -4.444 | 2/4 | True/True |
| python | 15 | 2 | 5/10 | 40/35 | -11.111 | 2/4 | True/True |
| python | 30 | 1 | 12/12 | 78/78 | +0.000 | 2/4 | True/True |
| python | 30 | 2 | 10/24 | 80/66 | -15.556 | 2/4 | True/True |
| python | 60 | 1 | 18/22 | 162/158 | -2.222 | 2/4 | True/True |
| python | 60 | 2 | 20/30 | 160/150 | -5.556 | 2/4 | True/True |
| cpp | 15 | 1 | 42/45 | 3/0 | -6.667 | 2/3 | True/True |
| cpp | 15 | 2 | 43/45 | 2/0 | -4.444 | 2/2 | True/True |
| cpp | 30 | 1 | 89/90 | 1/0 | -1.111 | 2/2 | True/True |
| cpp | 30 | 2 | 89/90 | 1/0 | -1.111 | 2/2 | True/True |
| cpp | 60 | 1 | 177/180 | 3/0 | -1.667 | 2/2 | True/True |
| cpp | 60 | 2 | 179/180 | 1/0 | -0.556 | 2/3 | True/True |

## Interpretação

- `202` mede aceitação HTTP, não produtividade do CGNR. Uma fila maior pode elevar a aceitação sem melhorar o tempo de processamento.
- Rejeições `503/QUEUE_FULL` são backpressure esperado, não perda de tarefas aceitas.
- Os resultados só são comparáveis sob o mesmo hardware, modelo, carga, ritmo de envio, bibliotecas numéricas e políticas de amostragem.
- Mudar workers, capacidade da fila e limite de admissão simultaneamente impede atribuir qualquer melhoria a uma única variável.
- CPU% usa 100% por núcleo lógico, incluindo processos filhos (TASK-16); picos acima de 100% são possíveis.
- Resultados de vazão com `workload_complete=false` devem ser ignorados; a coluna 202 sozinha não comprova maior throughput.

## Evidências

Os diretórios `before/` e `after/` contêm `scenario.json`, `requests.csv`, `summary.json`, `samples.csv` e `reconstructions.csv` por versão/carga/repetição.
