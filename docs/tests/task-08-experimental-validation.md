# TASK-08 — Validação Experimental do CGNR

## 1. Objetivo

Validar experimentalmente as implementações do algoritmo CGNR em Python e C++, utilizando matrizes e sinais de tomografia científica nas resoluções de 30 × 30 e 60 × 60 pixels.

A validação compara:

- Soluções reconstruídas;
- Normas dos resíduos;
- Quantidade de iterações;
- Estado de convergência;
- Tempos de execução;
- Diferenças numéricas entre Python e C++;
- Similaridade visual das reconstruções.

## 2. Ambiente de execução

| Componente | Versão ou configuração |
|---|---|
| Sistema operacional | Ubuntu 24.04 |
| Python | 3.12.3 |
| NumPy | 2.5.4 |
| Pytest | 9.2.0 |
| Compilador | GCC 13.3 |
| Biblioteca C++ | Eigen |
| Algoritmo | CGNR |
| Precisão numérica | float64 |
| Tolerância | 1e-8 |
| Máximo de iterações | 10 |
| OPENBLAS_NUM_THREADS | 1 |
| OMP_NUM_THREADS | 1 |

## 3. Dados experimentais

Foram utilizados dois modelos de reconstrução.

| Modelo | Matriz | Dimensões de H | Sinais |
|---|---|---|---|
| 30 × 30 | H-2 | 27904 × 900 | g-30x30-1, g-30x30-2 |
| 60 × 60 | H-1 | 50816 × 3600 | G-1, G-2 |

A quantidade de colunas de cada matriz corresponde ao número de pixels da imagem reconstruída.

### 3.1. Modelo 30 × 30

A matriz H-2 possui 27.904 linhas e 900 colunas.

Cada sinal de medição contém 27.904 elementos, produzindo uma reconstrução com 900 valores, organizados em uma imagem de 30 × 30 pixels.

### 3.2. Modelo 60 × 60

A matriz H-1 possui 50.816 linhas e 3.600 colunas.

Cada sinal de medição contém 50.816 elementos, produzindo uma reconstrução com 3.600 valores, organizados em uma imagem de 60 × 60 pixels.

A matriz H-1 contém 182.937.600 elementos e ocupa aproximadamente 1,36 GiB em representação densa `float64`.

### 3.3. Armazenamento dos dados

As matrizes experimentais não são versionadas no repositório devido ao tamanho dos arquivos.

Os dados são disponibilizados localmente no diretório:

`build/data/`

Para evitar conversões repetidas, as matrizes CSV comprimidas são convertidas para arquivos NumPy (`.npy`).

O carregamento utiliza `numpy.load` com `mmap_mode="r"`, permitindo acessar os dados por meio de memória mapeada.

Para a execução C++, os dados são exportados para um formato binário compatível com a organização de memória do Eigen.

## 4. Metodologia

Foram executados quatro experimentos:

1. Reconstrução 30 × 30 com `g-30x30-1`.
2. Reconstrução 30 × 30 com `g-30x30-2`.
3. Reconstrução 60 × 60 com `G-1`.
4. Reconstrução 60 × 60 com `G-2`.

Cada experimento foi executado separadamente em Python e C++.

As implementações utilizaram os mesmos dados de entrada e os seguintes parâmetros:

- Algoritmo: CGNR;
- Tolerância: `1e-8`;
- Máximo de iterações: `10`;
- Precisão: `float64`;
- Vetor inicial: zero.

O critério de convergência utilizado foi:

`||Hᵀrₖ|| <= tolerância × ||Hᵀr₀||`

As soluções foram comparadas por meio da norma L2 da diferença, da diferença relativa L2 e da maior diferença absoluta entre os elementos reconstruídos.

Também foram comparadas as normas dos resíduos finais, a quantidade de iterações e o estado de convergência.

## 5. Resultados numéricos

### 5.1. Diferenças entre Python e C++

| Modelo | Sinal | Elementos | Diferença relativa L2 | Maior diferença absoluta |
|---|---|---:|---:|---:|
| 30 × 30 | g-30x30-1 | 900 | 1.289653e-13 | 2.422507e-13 |
| 30 × 30 | g-30x30-2 | 900 | 1.783644e-13 | 4.116707e-13 |
| 60 × 60 | G-1 | 3600 | 8.424675e-14 | 2.449152e-13 |
| 60 × 60 | G-2 | 3600 | 1.381681e-13 | 4.221068e-13 |

As diferenças relativas ficaram na ordem de `1e-13`.

Os resultados demonstram equivalência numérica entre as implementações Python e C++ nos quatro casos experimentais analisados.

### 5.2. Normas dos resíduos finais

| Sinal | Norma do resíduo | Norma do resíduo normal |
|---|---:|---:|
| g-30x30-1 | 8.008660e-06 | 5.563088e-10 |
| g-30x30-2 | 1.125361e-05 | 8.906981e-10 |
| G-1 | 2.692938e-05 | 1.996227e-09 |
| G-2 | 4.271699e-05 | 3.008455e-09 |

Os valores calculados por Python e C++ coincidiram nos dígitos apresentados.

### 5.3. Iterações e convergência

Todos os experimentos executaram exatamente 10 iterações.

Nenhum dos quatro casos atingiu o critério de convergência estabelecido para a tolerância de `1e-8`.

O motivo de parada registrado pela implementação C++ foi:

`max_iterations`

A ausência de convergência não invalida a comparação entre as implementações, mas limita as conclusões sobre a solução matemática obtida.

## 6. Tempos de execução

| Modelo | Sinal | Python (s) | C++ (s) |
|---|---|---:|---:|
| 30 × 30 | g-30x30-1 | 0.2106 | 0.2009 |
| 30 × 30 | g-30x30-2 | 0.2014 | 0.2302 |
| 60 × 60 | G-1 | 1.5802 | 1.3422 |
| 60 × 60 | G-2 | 1.5994 | 1.4777 |

Os tempos correspondem a execuções individuais do cálculo numérico CGNR.

O tempo de preparação e carregamento dos arquivos não está necessariamente incluído nas medições.

O C++ apresentou menores tempos nas duas execuções de 60 × 60 observadas.

Entretanto, esses resultados não permitem concluir que uma implementação seja sistematicamente mais rápida, pois não foram realizadas repetições suficientes para uma análise estatística de desempenho.

## 7. Comparação visual

Foram geradas figuras comparativas para os quatro experimentos.

Cada figura apresenta três painéis:

1. Reconstrução CGNR Python.
2. Reconstrução CGNR C++.
3. Diferença absoluta entre as reconstruções.

As reconstruções Python e C++ utilizaram a mesma escala de intensidade, permitindo comparação visual direta.

Em todos os experimentos, as imagens apresentaram padrões visualmente indistinguíveis na escala utilizada.

Os painéis de diferença absoluta apresentaram valores da ordem de `1e-13`.

### 7.1. Gerar as figuras

Execute:

```bash
uv run --locked python -m scripts.visualize_task08 --signal g-30x30-1
uv run --locked python -m scripts.visualize_task08 --signal g-30x30-2
uv run --locked python -m scripts.visualize_task08 --signal G-1
uv run --locked python -m scripts.visualize_task08 --signal G-2
```

As figuras são geradas em:

`build/results/comparisons/`

Os arquivos produzidos são:

- `g-30x30-1_comparison.png`
- `g-30x30-2_comparison.png`
- `G-1_comparison.png`
- `G-2_comparison.png`

## 8. Reprodução dos experimentos Python

As matrizes e os sinais devem estar disponíveis em `build/data/`.

O script reutiliza o cache NumPy quando disponível.

### 8.1. Modelo 30 × 30

Primeiro sinal:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --locked python -m scripts.run_cgnr_experiment \
  --matrix-zip build/data/H-2.csv.zip \
  --measurements build/data/g-30x30-1.csv \
  --max-iterations 10 \
  --tolerance 1e-8
```

Segundo sinal:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --locked python -m scripts.run_cgnr_experiment \
  --matrix-zip build/data/H-2.csv.zip \
  --measurements build/data/g-30x30-2.csv \
  --max-iterations 10 \
  --tolerance 1e-8
```

### 8.2. Modelo 60 × 60

Primeiro sinal:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --locked python -m scripts.run_cgnr_experiment \
  --matrix-zip build/data/H-1.csv.zip \
  --measurements build/data/G-1.csv \
  --max-iterations 10 \
  --tolerance 1e-8
```

Segundo sinal:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --locked python -m scripts.run_cgnr_experiment \
  --matrix-zip build/data/H-1.csv.zip \
  --measurements build/data/G-2.csv \
  --max-iterations 10 \
  --tolerance 1e-8
```

Os resultados são salvos em `build/results/`, em diretórios separados por sinal.

Cada experimento gera:

- Imagem reconstruída em CSV;
- Imagem reconstruída em PNG;
- Histórico dos resíduos;
- Metadados experimentais em JSON.

## 9. Reprodução dos experimentos C++

### 9.1. Compilação

Execute:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 2
```

O executável experimental é:

`build/cgnr_experiment_runner`

### 9.2. Exportação da matriz

Para o modelo 60 × 60:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --locked python -m scripts.export_task08_binary \
  --matrix-npy build/data/H-1.npy \
  --output build/data/H-1-eigen.bin
```

Para o modelo 30 × 30:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --locked python -m scripts.export_task08_binary \
  --matrix-npy build/data/H-2.npy \
  --output build/data/H-2-eigen.bin
```

A exportação preserva os valores em `float64` e utiliza uma organização compatível com `Eigen::MatrixXd`.

### 9.3. Exportação dos sinais

Exemplo com G-1:

```bash
uv run --locked python -m scripts.export_task08_binary \
  --signal-csv build/data/G-1.csv \
  --output build/data/G-1.bin
```

O mesmo procedimento deve ser repetido para os demais sinais.

### 9.4. Execução C++

Exemplo com G-1:

```bash
mkdir -p build/results/cpp/G-1

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
build/cgnr_experiment_runner \
  build/data/H-1-eigen.bin \
  build/data/G-1.bin \
  build/results/cpp/G-1/solution.csv \
  build/results/cpp/G-1/metrics.json
```

O procedimento é equivalente para os demais sinais, ajustando os caminhos da matriz, do sinal e dos resultados.

## 10. Comparação numérica

O script `scripts/compare_task08.py` identifica automaticamente a resolução da imagem a partir dos metadados experimentais.

Exemplo para G-1:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --locked python -m scripts.compare_task08 \
  --python-dir build/results/G-1 \
  --cpp-dir build/results/cpp/G-1
```

O script apresenta:

- Quantidade de elementos reconstruídos;
- Número de iterações;
- Estado de convergência;
- Norma L2 da diferença;
- Diferença relativa L2;
- Maior diferença absoluta;
- Tempos de execução;
- Normas dos resíduos finais.

O arquivo `comparison.json` é salvo no diretório de resultados C++ correspondente.

## 11. Testes automatizados

Foram implementados testes opcionais para validar os resultados experimentais previamente gerados.

Arquivo:

`tests/integration/test_experimental_reconstructions.py`

Os testes verificam:

- Dimensões das matrizes;
- Dimensões das imagens reconstruídas;
- Quantidade de elementos;
- Valores numéricos finitos;
- Limite de iterações;
- Estado de convergência;
- Diferença relativa entre as soluções;
- Normas dos resíduos;
- Consistência do histórico de resíduos C++.

Esses testes não executam novamente o CGNR com as matrizes experimentais.

Quando os resultados não estão disponíveis, os casos são ignorados utilizando `pytest.skip`.

### 11.1. Testes experimentais

Execute:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --locked python -m pytest \
  tests/integration/test_experimental_reconstructions.py -v
```

Resultado observado:

`4 passed`

### 11.2. Suíte Python completa

Execute:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --locked python -m pytest tests/ -q
```

Resultado observado:

`108 passed`

### 11.3. Testes C++

Execute:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
ctest --test-dir build --output-on-failure
```

Resultado observado:

`2 tests passed`

## 12. Limitações

As seguintes limitações foram identificadas:

1. Nenhum dos quatro experimentos atingiu o critério de convergência em 10 iterações.
2. A equivalência numérica entre Python e C++ não comprova, isoladamente, a fidelidade das imagens reconstruídas às referências experimentais.
3. A comparação quantitativa com imagens de referência depende da identificação e validação desses arquivos.
4. Os tempos representam medições isoladas, não um benchmark estatístico.
5. Os testes automatizados experimentais verificam resultados previamente salvos, não novas execuções dos algoritmos.
6. As matrizes experimentais são grandes e devem ser obtidas separadamente.
7. O processamento da matriz 60 × 60 exige atenção ao consumo de memória.

## 13. Conclusão

As implementações Python e C++ do algoritmo CGNR produziram reconstruções numericamente equivalentes para os quatro sinais experimentais analisados, utilizando as resoluções de 30 × 30 e 60 × 60 pixels.

As diferenças relativas L2 ficaram na ordem de `1e-13`, demonstrando elevada consistência entre as soluções reconstruídas pelas duas implementações.

Todos os experimentos respeitaram o limite máximo de 10 iterações, embora nenhum tenha atingido a tolerância de convergência estabelecida.

Os resultados demonstram que as implementações apresentam comportamento numérico equivalente nos casos experimentais testados.

A validação da fidelidade das reconstruções em relação às imagens de referência permanece como uma atividade complementar.