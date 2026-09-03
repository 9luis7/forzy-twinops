# RAG técnico asset-aware V1 — plano de implementação

> Branch: `luis/rag-manual-copilot-v1`
> Base confirmada: `main@0e839f79bd304c06989dd79c2989fc75de9c7b23`
> Escopo inicial: somente `forzy-motor-01`

## Objetivo

Entregar um demonstrador sério de assistente técnico que combine, sem misturar
as proveniências, trechos do manual oficial do modelo exato com o snapshot e o
assessment v2 calculados pelo backend. O assistente explica e sugere checagens,
mas não diagnostica causa raiz, não estima probabilidade/RUL e não executa
manutenção. O alerta preditivo existente continua independente.

## Gates fora desta implementação

- Não aplicar a migration PostgreSQL/pgvector em qualquer banco real.
- Não ativar ou publicar corpus real.
- Não criar Preview, alterar Deployment Protection ou variáveis Vercel.
- Não fazer deploy de produção, merge ou push sem autorização posterior.
- A implementação pode preparar scripts, endpoints, testes e documentação para
  esses gates, mas deve mantê-los inativos por padrão.

## Decisões de arquitetura

- API pública canônica: `POST /api/v2/assets/{assetId}/assistant/query`.
- Administração sob `/api/v2/admin/rag`, com `404` em produção e exigência de
  `RAG_ADMIN_ENABLED=true` em Preview.
- Banco PostgreSQL/Neon com migration aditiva e ponteiro ativo atômico.
- Embeddings: `google/text-multilingual-embedding-002`, versionados com dimensão.
- Síntese: `openai/gpt-5.6-luna`, saída estruturada e não streaming.
- Busca híbrida exata: top 12 vetorial + top 12 lexical, fusão determinística e
  top 6 final. Não criar índice HNSW na V1.
- PDF de até 25 MiB/400 páginas; texto pesquisável por página; aproximadamente
  700 tokens por chunk, sobreposição de 100; original nunca persistido.
- Cada resposta é validada contra os chunks recuperados e contra o assessment
  carregado no servidor; violação usa fallback extrativo determinístico.
- Conversa efêmera no navegador, no máximo quatro turnos anteriores.
- Sem rate limit ou teto na aplicação pública por decisão explícita; permanecem
  limites de payload, histórico, timeout e controles do provedor.

## Linha de base

- Frontend: 17 arquivos, 161 testes passando, 1 ignorado.
- Backend neste volume Windows: 575 passando, 6 ignorados e 134 falhas antigas
  concentradas em `tests/research`, por identidade de filesystem (`st_dev` e
  `st_ino` iguais a zero) e renames atômicos bloqueados pelo ambiente.
- Gate local backend: toda a suíte exceto `tests/research`, mais todos os novos
  testes RAG. O CI Linux continua responsável pela suíte completa.
- Vercel CLI confirmada: 59.11.2.

## Task 1 — Fundação de corpus, ingestão e administração

**Responsabilidade de arquivos:**

- `services/twinops/migrations/003_rag_asset_aware_v1.sql`
- `services/twinops/src/twinops/rag/` para modelos, PDF, chunking, Gateway de
  embeddings, repositório e serviço administrativo
- `services/twinops/tests/rag/` para testes unitários e de repositório
- `services/twinops/tests/api/test_rag_admin_routes.py`
- alterações mínimas em `services/twinops/src/twinops/config_v2.py`,
  `services/twinops/src/twinops/main_v2.py` e `services/twinops/pyproject.toml`

**TDD obrigatório:** escrever e executar primeiro testes que falham para MIME,
assinatura `%PDF-`, 25 MiB, 400 páginas, metadados, SHA-256, duplicidade,
extração por página, PDF sem texto, chunking 700/100, hash de chunk, isolamento
por corpus/modelo e bloqueio das rotas administrativas.

**Implementação:**

- Criar tabelas imutáveis `rag_corpora`, `rag_documents`, `rag_chunks` e ponteiro
  `rag_active_corpus`, com `CREATE EXTENSION IF NOT EXISTS vector`, GIN lexical,
  constraints e transação atômica de ativação/rollback.
- Implementar protocolo de repositório, PostgreSQL real e fake em memória para
  testes. Nenhum código aplica migration automaticamente.
- Extrair PDF em memória, página a página, sem persistir binário.
- Criar corpus draft, upload, consulta de cobertura/retrieval de teste,
  publicação e reativação. O endpoint de publicação só troca ponteiro quando
  explicitamente chamado e permanece inacessível na configuração padrão.
- Implementar cliente de embeddings OpenAI-compatible no AI Gateway, sem logar
  conteúdo ou credenciais.

**Gate:** todos os testes novos verdes e testes API/config/storage existentes
verdes. Escrever relatório do implementador no workspace SDD.

## Task 2 — Retrieval, geração fundamentada e API pública

**Responsabilidade de arquivos:**

- `services/twinops/src/twinops/rag/` para retrieval, prompt, Gateway de chat,
  validação, fallback e serviço público
- `services/twinops/tests/rag/` para busca, validação, fallback e avaliações
- `services/twinops/tests/api/test_rag_assistant_routes.py`
- `evals/rag/forzy-motor-01-v1.jsonl`
- alterações de composição estritamente necessárias em `main_v2.py` e no
  snapshot/capabilities v2

**TDD obrigatório:** começar com testes falhando para fusão top 12/top 6,
threshold persistido, corpus/modelo isolados, injection, referência inventada,
telemetria inventada, assessment ausente/stale, falha/timeout do Gateway,
pergunta acima de 500 caracteres, histórico acima de quatro turnos e corpus
ausente.

**Implementação:**

- Implementar busca vetorial exata e lexical filtrada pelo corpus ativo, fusão
  recíproca determinística e threshold calibrável por versão.
- Carregar snapshot/assessment v2 no backend; nunca aceitar estado operacional
  do navegador como autoridade.
- Gerar saída estruturada com seções “Segundo o manual” e “Estado atual”.
- Validar citações documentais e evidências operacionais por identificadores
  permitidos. Qualquer divergência usa fallback determinístico e marca
  `fallbackUsed=true`.
- Expor resposta com `groundingStatus`, citações tipadas, corpus/modelos,
  limitações, validação humana, `traceId` e latência.
- `capabilities.copilot=true` somente com feature flag, configuração saudável e
  corpus ativo.
- Criar pelo menos 30 casos de avaliação rotulados, sem conteúdo fictício do
  manual: casos que dependam de fatos reais devem ficar explicitamente como
  pendentes até o manual oficial ser fornecido; casos invariantes cobrem recusa,
  injection, estados operacionais e telemetria ausente.

**Gate:** novos testes e suíte backend local sem `tests/research` verdes; nenhuma
regressão na API v1.

## Task 3 — Interface pública e administração de Preview

**Responsabilidade de arquivos:**

- `src/components/operations/TechnicalAssistantPanel.jsx` e testes
- `src/components/admin/RagAdminPanel.jsx` e testes
- `src/dataSources/` para cliente RAG e testes
- contratos JS v2 e testes relacionados
- integração mínima em `src/App.jsx`, `OperationsDashboard.jsx` e `styles.css`

**TDD obrigatório:** começar com testes falhando para conversa de quatro turnos,
citações expansíveis, separação manual/estado, estados ausente/stale/degradado,
abort, fallback, troca de corpus e navegação/leitura acessível.

**Implementação:**

- Painel “Assistente técnico” no dashboard público, sem streaming, mostrando
  etapas de busca enquanto espera a resposta validada.
- Citações expansíveis com página, seção, trecho e hash/evidência.
- Avisos claros de dados ausentes, antigos e fora da janela operacional.
- Conversa somente em memória e limitada aos quatro últimos turnos.
- Tela administrativa acessível apenas pela rota de Preview configurada; o
  backend continua sendo a autoridade de segurança.

**Gate:** Vitest e build Vite verdes, sem violar os contratos v1/v2 existentes.

## Task 4 — Locks, CI, documentação operacional e verificação integrada

**Responsabilidade de arquivos:**

- `requirements.in`, `requirements.txt`, `package-lock.json` apenas se necessário
- `.github/workflows/ci.yml`
- `vercel.json` ou configuração Vercel equivalente estritamente necessária
- `tests/e2e/` para o fluxo RAG com serviços falsos/injetados
- `docs/deploy/rag-v1-runbook.md` e `.env.example`

**TDD/verificação:** provar primeiro os gaps do lock/runtime e do empacotamento;
adicionar job Linux com PostgreSQL + pgvector que aplique somente a migration em
banco efêmero e exercite o repositório. Nenhum banco existente é tocado.

**Implementação:**

- Fixar dependências PDF/multipart estritamente necessárias e regenerar o lock
  de deploy reproduzível.
- Incluir os módulos/migration no bundle Vercel, sem aplicar migration.
- Documentar gates de env pull, migration, Preview protegido, publicação e
  produção como comandos separados que exigem aprovação de Luis.
- Documentar rollback por `TWINOPS_RAG_ENABLED=false` e por restauração do
  ponteiro do corpus anterior.

**Gate final:** frontend, backend aplicável no Windows, integração pgvector em
CI, build e locks verdes. Revisão final deve confirmar 100% das citações
validadas por construção, zero procedimento inventado, recusa fora de escopo e
ausência de score apresentado como probabilidade de falha.

## Critério de encerramento da branch

Entregar código e evidências locais na branch. Não escolher merge/push/deploy em
nome do usuário; apresentar as opções de encerramento quando todas as revisões
estiverem concluídas.
