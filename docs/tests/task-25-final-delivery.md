# TASK-25 — Validação da entrega final

## Escopo e limitações

Esta task fecha a validação de instalação, concorrência, reconstrução, relatórios,
gráficos e integridade. **Não** deve ser marcada como concluída apenas por existir
um script: a execução deve ocorrer em um checkout limpo, **ambos os integrantes**
devem conferir o funcionamento e o pacote precisa ser enviado no Moodle.

Não há integração de envio ao Moodle. **A entrega e o comprovante são manuais.**

## Dependências do sistema

Consulte o [README](../../README.md) e [a configuração do ambiente](../development-setup.md).
São necessários Git, `uv`, CMake, compilador C++17, Eigen, OpenBLAS e acesso às
dependências Python/C++ a partir de uma instalação limpa. No Arch Linux,
confira se `base-devel`, `cmake`, `eigen`, `openblas` e `uv` estão instalados.

## 1. Preparar a branch e commitar a implementação

```bash
git switch main
git pull --ff-only
git switch -c task-25
# aplicar os arquivos da TASK-25
git add scripts/task25_validate.py scripts/task25_release.py \
  tests/unit/test_task25_delivery.py docs/tests/task-25-final-delivery.md
git commit -m "test(task-25): automate final clean-install delivery validation"
```

O validador faz `git archive HEAD` e extrai o código versionado em um diretório
temporário **sem** `.venv` nem `build`; portanto, rode-o **após** o commit.
Ele recusa modificações locais não commitadas para não validar uma versão
diferente da que será entregue.

## 2. Verificar o conjunto de evidências já versionadas

```bash
python -m scripts.task25_validate --only-evidence \
  --output results/task25/evidence-check
```

`PARTIAL` significa que o histórico da TASK-21, os relatórios da TASK-23 e
os gráficos foram conferidos, **mas não houve instalação limpa nem execução
dos servidores reais**. Esse modo não satisfaz o critério de aceite.

## 3. Executar a validação completa em instalação limpa

Na raiz do repositório, depois de commitar:

```bash
python -m scripts.task25_validate \
  --output results/task25/verification
```

O comando cria um checkout limpo a partir do commit atual e executa:

1. Verificação dos arquivos de projeto e lockfiles.
2. `uv sync --locked` no checkout limpo.
3. `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON`
   e `cmake --build build -j 4`.
4. `ctest --test-dir build --output-on-failure`.
5. Suíte completa `uv run --locked python -m pytest tests/ -q --tb=short`.
6. **Novo teste real TASK-20:** três clientes, quinze sinais por cliente e
   quarenta e cinco reconstruções em cada servidor, totalizando **90 imagens**.
   O resultado é persistido e validado campo a campo.
7. Verificação de todas as **18 execuções comparáveis** da TASK-21 (CSV, JSON,
   SHA-256 do plano e reconciliação dos IDs de requisição e reconstrução).
8. Verificação do relatório técnico da TASK-23, dos **15 PNGs** e dos
   manifestos da TASK-22, incluindo estrutura e CRC dos gráficos.
9. Verificação da presença e completude dos relatórios das TASK-18 e TASK-19.

O programa retorna código diferente de zero se falhar alguma verificação.
Um relatório `validation.json` com `status=PASS` demonstra apenas os requisitos
automatizados; não equivale à aprovação dos dois integrantes ou à entrega Moodle.

As saídas ficam em:

```text
results/task25/verification/
├── validation.json
├── validation.md
├── integration/
│   ├── execution.json
│   └── images.json
└── logs/
    ├── clean_install.log
    ├── cpp_build.log
    ├── cpp_build_compile.log
    ├── cpp_tests.log
    ├── python_tests.log
    └── real_integration.log
```

A imagem de teste é a identidade demonstrativa `demo_identity_3`, suficiente
para verificar fluxo e consistência numérica. Os **dados de benchmark**
permanecem os ensaios reais da TASK-21 com matriz sintética densa de dimensão
512. Não misturar estes ensaios ao calcular tempos comparativos.

## 4. Verificação dos dois integrantes e pacote ZIP final

Cada integrante deve repetir a validação em sua instalação (preferencialmente
em máquinas/ambientes independentes), inspecionar `validation.md`, conferir
`integration/images.json`, os gráficos e o relatório técnico. Os nomes abaixo
**devem ser substituídos pelas identidades reais**, somente após a conferência.

```bash
python -m scripts.task25_release \
  --validation results/task25/verification/validation.json \
  --validated-by "NOME INTEGRANTE 1" \
  --validated-by "NOME INTEGRANTE 2" \
  --output results/task25/desenvolvimento-integrado-de-sistemas-final.zip

python -m scripts.task25_release \
  --verify results/task25/desenvolvimento-integrado-de-sistemas-final.zip

(cd results/task25 && sha256sum -c desenvolvimento-integrado-de-sistemas-final.zip.sha256)
```

O script de empacotamento exige dois nomes distintos para um pacote final,
mas **não tem como atestar sozinho** que ambos efetivamente validaram.
Se apenas um integrante tiver executado os testes, pode gerar um pacote
provisório com `--draft`; ele não deve ser apresentado como validado por dois.

O ZIP inclui os arquivos rastreados no commit Git, as evidências de validação,
`release_manifest.json` com SHA-256 de cada arquivo, e o checksum do ZIP em
arquivo adjacente. `.git/`, `.venv/` e `build/` não entram no pacote. O script
se recusa a sobrescrever uma release existente: escolha outro nome se precisar
recriar a entrega.

O arquivo `validation.json` guarda o commit testado. A release é recusada se
o commit atual for diferente daquele testado ou se houver mudanças locais.

Se desejar versionar as evidências no PR, copie `validation.md` e os JSON
pertinentes para `docs/tests/results/task-25/` **após o primeiro teste** e
faça um novo commit. Como isso altera o SHA de `HEAD`, reexecute a validação
completa nesse commit antes de criar o ZIP final. Não reescreva o SHA do
relatório manualmente.

## 5. Moodle — etapa manual obrigatória

- [ ] Os dois integrantes executaram/conferiram a validação e registraram o acordo.
- [ ] A versão final ZIP passou em `--verify` e `sha256sum -c`.
- [ ] O(s) integrante(s) responsável(is) enviou(aram) o pacote no Moodle.
- [ ] O comprovante, horário e identificação da entrega foram preservados.
- [ ] A issue #25 só foi fechada após a confirmação da entrega.

O projeto não tem acesso às credenciais do Moodle. O PR pode reunir os scripts
e os resultados técnicos, mas **não** comprova, sozinho, que a entrega foi
realizada ou que os dois integrantes validaram.

## Reprodutibilidade e auditoria

- Fonte: commit Git gravado no relatório de validação e no manifesto da release.
- Dependências: `uv.lock`, `.python-version`, `CMakeLists.txt`, Eigen/OpenBLAS.
- Funcional: `tests/integration/test_task20_full_flow.py` executado novamente.
- Imagens: `integration/images.json` e `integration/execution.json`.
- Comparativo: `docs/tests/task-21-evidence/`, inclusive hash do plano.
- Gráficos e relatório: `docs/reports/task-23/`.
- Logs: `results/task25/verification/logs/`.

**Limitação:** verificações de hash comprovam a integridade contra o manifesto
gerado, não uma assinatura digital confiável de terceiro. Dependências externas
instaladas sem rede/cache controlados podem afetar a reprodutibilidade e o tempo
de instalação. Resultados experimentais históricos não são reexecutados pelo
validador; sua integridade e completude são auditadas a partir dos arquivos
versionados.
