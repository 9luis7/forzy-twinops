# Runbook — RAG técnico asset-aware V1

Este runbook prepara a demonstração do RAG para `forzy-motor-01`. Nenhum passo
abaixo autoriza o passo seguinte. Luis é o aprovador técnico e deve autorizar
explicitamente cada gate. Os comandos são modelos operacionais; o estado real
de cada ambiente deve ser confirmado pela saída sanitizada da CLI e pelo ledger
do deployment correspondente.

## Invariantes de segurança

- O chat público lê somente o corpus publicado e o assessment calculado no
  backend. O navegador nunca é autoridade para telemetria ou diagnóstico.
- O assistente não diagnostica causa raiz, não estima probabilidade de falha ou
  RUL e não executa manutenção. O alerta preditivo continua independente.
- PDF, pergunta, chunks, credenciais e DSN não devem aparecer em logs. O PDF
  original não é persistido.
- `RAG_ADMIN_ENABLED=true` e `VITE_RAG_ADMIN_ENABLED=true` são exclusivos de
  Preview; produção deve responder `404` nas rotas administrativas.
- Não existe rate limit ou teto de consumo na aplicação pública por decisão de
  produto. Isso cria risco explícito de abuso e custo. Devem permanecer ativos
  os limites de payload/histórico/timeout e os controles financeiros e técnicos
  do provedor.

## Gate 1 — confirmar Preview protegido

**Aprovação necessária:** Luis autoriza verificar/configurar Deployment
Protection para o projeto e domínio de Preview, sem alterar produção.

Confirme no painel da Vercel que o Preview administrativo exige autenticação e
que `/rag-admin` não é acessível anonimamente. Referência oficial:
[Deployment Protection](https://vercel.com/docs/deployment-protection).

Não habilite as flags administrativas antes dessa verificação.

## Gate 2 — acessar e configurar ambiente de Preview

**Aprovação necessária:** Luis autoriza ler e alterar somente variáveis do
ambiente Preview.

```powershell
vercel env run -e preview -- python scripts/verify_env.py
```

O comando injeta as variáveis somente no subprocesso e não cria arquivo local
com segredos. Saída válida contém apenas nomes de variáveis inválidas/ausentes,
nunca valores.

Para a demo com free tier, configure `TWINOPS_RAG_PROVIDER=gemini` e grave
`GEMINI_API_KEY` como variável sensível somente no backend. Esse caminho chama
a Gemini API diretamente e não depende do AI Gateway. O Gateway continua como
alternativa: `TWINOPS_RAG_PROVIDER=gateway` usa `VERCEL_OIDC_TOKEN` ou
`AI_GATEWAY_API_KEY`. Configure no backend a identidade exata do manual, IDs de
modelo, dimensão e timeouts. Configure também `RAG_PREVIEW_DATABASE_NAME` e
`RAG_PREVIEW_DATABASE_USER` com a identidade exata permitida para o banco de
Preview; esses valores vêm do ambiente Preview e nunca são inferidos do DSN nem
impressos. O segredo não recebe prefixo `VITE_`. Para o Preview administrativo,
`VERCEL_ENV=preview`, `RAG_ADMIN_ENABLED=true` e `VITE_RAG_ADMIN_ENABLED=true`
devem estar coerentes. O recurso público continua desligado com
`TWINOPS_RAG_ENABLED=false` até a publicação. Referência oficial:
[variáveis de ambiente](https://vercel.com/docs/environment-variables).

Modelos Gemini ancorados nesta versão:

- [gemini-embedding-2](https://ai.google.dev/gemini-api/docs/embeddings)
- [gemini-3.5-flash-lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)

O modelo generativo usa `reasoning_effort=minimal` para reduzir a latência da
seleção estruturada e extrativa. O backend continua validando toda referência
antes de exibir a resposta.

No free tier, entradas e saídas podem ser usadas pelo Google para melhorar seus
produtos. Para esta demo, trate como permitido somente o manual público, as
perguntas do chat público e o snapshot operacional expressamente aprovado.
Não envie credenciais, DSNs, PDFs privados ou dados pessoais.

Trocar o modelo de embedding ou a dimensão exige um corpus novo e reindexado;
embeddings de versões diferentes nunca são misturados. O modelo generativo
permanece uma âncora explícita de deploy, mas não altera os vetores persistidos.

## Gate 3 — aplicar migration aditiva 003

**Aprovação necessária:** Luis autoriza a migration no banco exato do Preview.
Verifique antes o alvo sem copiar DSN para tickets, logs ou mensagens.

```powershell
vercel env run -e preview -- python scripts/check_rag_postgres.py --target preview --migrate services/twinops/migrations/003_rag_asset_aware_v1.sql
```

O checker recusa qualquer alvo que não seja literalmente `preview`, valida a
identidade do banco e usuário contra a allowlist explícita do ambiente antes da
migration sem imprimir DSN/credenciais/identidade, aceita
somente a migration 003 e valida TLS, extensão `vector`, quatro tabelas, dois
índices, ausência de HNSW/IVFFlat e cada constraint essencial por nome e
definição canônica exata. A
migration e as verificações ocorrem na mesma transação: qualquer falha executa
rollback. A migration é aditiva e não altera tabelas operacionais. Referências:
[imagem pgvector](https://hub.docker.com/r/pgvector/pgvector) e
[busca exata pgvector](https://github.com/pgvector/pgvector#querying).

## Gate 4 — deploy ou redeploy do Preview

**Aprovação necessária:** Luis autoriza criar um Preview protegido desta branch.

Antes do deploy, rode as suítes, o build e o lock reproduzível. O lock Python é
regenerado apenas por:

```powershell
uv pip compile requirements.in --python-version 3.12 --python-platform x86_64-unknown-linux-gnu --generate-hashes --only-binary :all: --output-file requirements.txt
python -m pip install --require-hashes -r requirements.txt
npm ci
npm run test:run
npm run build
```

Referência: [uv pip compile](https://docs.astral.sh/uv/pip/compile/). Depois do
deploy, confirme novamente a proteção e o `404` administrativo em produção.

## Gate 5 — ingestão exploratória

**Aprovação necessária:** Luis autoriza enviar o PDF oficial pesquisável ao
Preview protegido.

1. Crie um draft exploratório com `minRelevanceScore=0`.
2. Envie o PDF de até 25 MB/400 páginas com fabricante, modelo, revisão, idioma
   e URL oficial.
3. Confira SHA-256, cobertura de páginas, chunks e identidade do equipamento.
4. Execute consultas de recuperação. Capture por caso os seis resultados, com
   `chunkId`, `absoluteScore`, `rankScore`, `vectorRank` e `lexicalRank`.

Upload não publica. Um draft com threshold zero é deliberadamente
impublicável.

## Gate 6 — rotular e calibrar

**Aprovação necessária:** Luis aprova os rótulos e âncoras derivados do manual.

Complete pelo menos 30 casos. Casos reais suportados exigem página, trecho
exato, hash do documento, hash do chunk e `chunkId`; casos `absent` ou
`out_of_scope` exigem evidência manual vazia. Fixtures sintéticas não contam
como aceite real.

O manifesto completo continua sendo `forzy-motor-01-v1.jsonl` e deve conter os
30 casos. A captura de calibração contém exatamente os IDs `real_manual`
completos; fixtures sintéticas são excluídas desta captura e não podem ocupar o
lugar de casos reais. Cada linha da captura tem somente `caseId`, `question` e
até seis `hits` ordenados. Cada hit tem exatamente `chunkId`, `absoluteScore`,
`rankScore`, `vectorRank` e `lexicalRank`. As duas chaves de rank são
obrigatórias no wire format mesmo quando uma delas contém `null`; nomes internos
`snake_case` são inválidos. Não inclua métricas ou decisões calculadas pelo
produtor. Então execute:

```powershell
python evals/rag/validate.py evals/rag/forzy-motor-01-v1.jsonl --require-complete
python evals/rag/calibrate.py evals/rag/forzy-motor-01-v1.jsonl captured-retrieval.jsonl
```

O calibrador deriva o threshold do score do próprio chunk esperado e do maior
negativo, reaplica o candidato hit a hit e só então calcula micro Recall@6 e
recusa. Ele apenas imprime as métricas e um threshold finito/positivo; nunca
escreve no banco. A recomendação só passa com Recall@6 de pelo menos 90% e 100%
de recusas corretas.

## Gate 7 — criar e publicar o corpus final

**Aprovação necessária em duas etapas:** (a) criar/reindexar o draft final; (b)
publicar o ID exato após revisão.

Versões de corpus são imutáveis. O fluxo correto é:

```text
draft exploratório (threshold 0)
  -> captura, rótulo e calibração
  -> novo draft final (threshold positivo recomendado)
  -> nova ingestão e avaliação
  -> publicação explícita
```

O mesmo SHA-256 pode ser reindexado no novo corpus porque a duplicidade é
isolada por corpus. Antes da publicação, capture as respostas finais e rode:

```powershell
python evals/rag/score.py completed-acceptance.jsonl captured-answers.jsonl
```

`completed-acceptance.jsonl` deve ser o manifesto completo validado, com no
mínimo 30 casos e 15 casos reais. `captured-answers.jsonl` deve conter exatamente
um registro para cada caso, sem IDs extras/ausentes/duplicados, composto por:
pergunta; hits brutos com texto, proveniência e scores; resposta pública
estruturada integral; âncoras do snapshot/evidência operacional; corpus/modelo;
e latência. Não inclua booleanos produzidos como `citationValid` ou
`policyCompliant`: o scorer recompõe essas decisões a partir da resposta, dos
hits e das âncoras.

Cada captura declara `flowStage`. Use `retrieval` somente com `retrieval` e
`operationalSnapshot` completos. Para uma recusa `out_of_scope` executada no
preflight público, use `preflight_refusal` e envie explicitamente ambos como
`null`: isso prova que corpus, hits e snapshot não foram consultados, em vez de
inventar dependências para a avaliação. Fixtures sintéticas suportadas usam
âncoras string canônicas `fixture:...`; elas são verificadas, mas nunca contam
como recall do manual real.

Exija 100% de citações válidas, zero evidência/procedimento inventado,
Recall@6 >= 90%, 100% de recusa, nenhuma apresentação de score como
probabilidade e p95 <= 12.000 ms. Só então confirme no painel o ID final e a
ação explícita de publicação.

## Gate 8 — habilitar chat público no Preview

**Aprovação necessária:** Luis autoriza `TWINOPS_RAG_ENABLED=true` somente no
Preview e um novo deploy/redeploy. Verifique a rota pública, estado degradado,
fallback, citações e separação “Segundo o manual”/“Estado atual”. Isso não
autoriza produção.

## Gate 9 — produção

**Aprovação separada e final:** Luis autoriza variáveis, migration, corpus e
deploy no ambiente Production. Refaça todas as verificações no SHA aprovado.
Não reutilize autorização de Preview como autorização de produção.

Configure `RAG_PRODUCTION_DATABASE_NAME` e `RAG_PRODUCTION_DATABASE_USER` com
a identidade exata do banco alvo e execute a migration somente pelo checker:

```powershell
vercel env run -e production -- python scripts/check_rag_postgres.py --target production --migrate services/twinops/migrations/003_rag_asset_aware_v1.sql
```

O checker seleciona a allowlist pelo `--target`, valida identidade e TLS antes
de executar SQL e mantém o mesmo rollback transacional do Preview. As rotas
administrativas continuam ausentes em Production; a ingestão e publicação
devem ocorrer no Preview protegido que compartilha o banco aprovado ou por uma
rotina operacional offline com as mesmas validações e autorização explícita.

## Rollback

Rollback do recurso, sem remover dados:

1. obter aprovação para alterar o ambiente afetado;
2. definir `TWINOPS_RAG_ENABLED=false`;
3. redeployar e confirmar `capabilities.copilot=false`.

Rollback de conteúdo:

1. identificar o corpus publicado anterior e validar fabricante/modelo/modelo
   de embedding/dimensão;
2. obter aprovação explícita para o ID;
3. usar a ação de reativação no Preview protegido;
4. confirmar que o ponteiro atômico voltou ao corpus anterior.

Não apague corpus durante rollback. A restauração troca apenas o ponteiro ativo
e preserva as versões imutáveis para auditoria.
