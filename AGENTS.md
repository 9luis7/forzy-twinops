# Forzy TwinOps — Instruções para agentes

Convenções duráveis deste repositório. O estado transitório da entrega em curso
fica em `.superpowers/sdd/` (ver §8).

---

## 1. O que é este projeto

Demonstrador de gêmeo digital operacional para **um único conjunto motor-bomba
real**, publicável na Vercel sem custo. Não é uma demo multiplanta e não é um
protótipo com dados sintéticos.

- Identidade interna única: `forzy-motor-01`. `officialTag` permanece `null`.
- Dois sensores reais: `s1` e `s2`.
- Frontend React 18 + Vite 5; backend FastAPI + Pydantic 2; Postgres/Neon.

## 2. Princípio inegociável: honestidade do dado

Este é o requisito que governa todos os outros. Quando houver conflito entre
"a interface fica mais bonita/completa" e "a interface diz a verdade sobre o
dado", a verdade ganha.

- Falha **nunca** produz snapshot normal nem dados sintéticos.
- `observedAt = receivedAt` só é aceito com `timestampQuality="assumed_from_retrieval"`
  e `sourceTimestampProvided=false`. Nesse caso a interface escreve
  **"capturado pelo TwinOps às"**, não "medido às".
- O score publicado é `relative_to_historical_baseline_not_failure_probability`.
  Nunca apresentar como probabilidade de falha.
- Payload idêntico é auditado, mas não vira novo ponto de tendência nem nova
  informação para ML.
- Mock, replay, ativos fictícios, copiloto, documentos, ordens e alertas
  inventados **não pertencem ao runtime publicável**.
- O navegador nunca acessa o hostname Forzy diretamente. A API é same-origin.
- CSV Forzy não entra no banco nem na interface publicável; serve a treino,
  backtest e auditoria offline.

### Janela de coleta

Polling automático somente com a página visível **e** dentro de
**segunda, terça e quarta, `[12:00, 14:00)`** em `America/Sao_Paulo`
(fechado no início, aberto no fim). Fora da janela: apenas `GET` snapshot;
`POST` refresh não é agendado.

Derive isso de um helper puro e testado com
`Intl.DateTimeFormat("en-US", {timeZone:"America/Sao_Paulo", weekday:"short", hour:"2-digit", minute:"2-digit", hourCycle:"h23"})`.
Nunca dependa do timezone do navegador.

## 3. Ambiente (Windows)

Rode a partir da raiz do worktree.

| Objetivo | Comando |
| --- | --- |
| Suíte JS completa | `npm.cmd run test:run` |
| Suíte JS focada | `npm.cmd run test:run -- <caminho>` |
| Build de produção | `npm.cmd run build` |
| Suíte Python | `services/twinops/.venv/Scripts/python.exe -m pytest services/twinops/tests -q` |
| E2E | `npm.cmd run test:e2e` |

- Use **`npm.cmd`**, não `npm` — `npm` puro falha no PowerShell.
- Cada worktree tem seu próprio `node_modules` e seu próprio
  `services/twinops/.venv`. Um worktree recém-criado precisa de `npm.cmd ci`.
- Shell disponível: Git Bash (POSIX) e PowerShell. Cada um com sua sintaxe.

## 4. Roadmap versionado

A entrega é dirigida por planos versionados, não por improviso.

- **Spec:** `docs/superpowers/specs/2026-08-13-forzy-twinops-real-vercel-zero-cost-design.md`
- **Índice de execução:** `docs/superpowers/plans/2026-08-13-real-twinops-execution-index.md`
  — ordem dos planos, dependências, ownership e gates.
- **Planos:** `docs/superpowers/plans/2026-08-13-real-twinops-*.md`

| Ordem | Plano | Entrega |
| --- | --- | --- |
| 01 | `contract-v2` | Schemas, modelos e validators v2 |
| 02 | `backend` | Refresh, Postgres, snapshot, health e scorer |
| 03 | `single-asset-ui` | Interface única sem mock |
| 04 | `3d` | GLB real, manifesto e canvas |
| 05 | `vercel-neon-deploy` | Preview e produção demonstrativa |
| 06 | `public-fault-datasets-lab` | Matriz, ablação e validação cross-bench |

Os planos declaram `REQUIRED SUB-SKILL: superpowers:subagent-driven-development`
(ou `superpowers:executing-plans`). Siga a skill: um agente implementador por
task, revisão por task, revisão ampla no fim.

**No Codex**, `spawn_agent`/`wait_agent`/`close_agent` exigem
`[features] multi_agent = true` em `~/.codex/config.toml`.

## 5. Fronteiras de ownership

Cada plano tem ownership exclusivo. Tocar arquivo de outro plano é falha grave,
mesmo que a mudança pareça inofensiva — é o que permite que os planos avancem
em worktrees separados sem colisão.

| Plano | Ownership exclusivo |
| --- | --- |
| 01 | `contracts/v2/**`, `services/twinops/src/twinops/contracts/v2_*`, `src/contracts/twinV2.*` |
| 02 | `services/twinops/src/twinops/{config_v2,ingestion/refresh_service,ingestion/live_adapter_v2,storage/postgres_repository,storage/v2_repository,api/v2_routes}.py`, `services/twinops/migrations/**` |
| 03 | `src/App.jsx`, `src/main.jsx`, `src/TwinOpsContext.jsx`, `src/dataSources/GatewayTwinDataSourceV2.js`, `src/components/operations/**`, `src/styles.css` |
| 04 | `tools/twin3d/**`, `public/models/**`, `src/components/Twin3D.jsx`, `src/components/twin3d/**` |
| 05 | `api/index.py`, `requirements.txt`, `vercel.json`, `.env.example`, `tests/e2e/deployed-real.spec.js` |
| 06 | `services/twinops/src/twinops/research/**`, `services/twinops/tests/research/**`, `data/public/**`, `artifacts/ml-public/**` |

`services/twinops/pyproject.toml` é **serializado**: o plano 02 adiciona
Postgres; o plano 06 só altera o arquivo depois que 02 estiver integrado.

`docs/superpowers/plans/**` e `docs/superpowers/specs/**` são documentação do
roadmap: não os altere como efeito colateral de implementação. Se um plano
estiver errado, levante a contradição com o humano em vez de editar o plano
silenciosamente.

## 6. Gates de integração

1. **Gate V2:** schemas JSON, Pydantic e validator JS aceitam as mesmas fixtures.
2. **Gate dados:** refresh parcial, dedupe, Postgres e artefato ML passam sem rede real.
3. **Gate honestidade:** busca estática não encontra imports de `data/mock`,
   replay ou TAG fictícia no bundle publicável.
4. **Gate 3D:** GLB carrega, manifesto referencia apenas nós existentes e nenhum
   sensor ganha posição.
5. **Gate deploy:** preview usa Neon e stub controlado; smoke real é separado e opt-in.
6. **Gate científico:** splits são por rolamento; resultado público não altera o
   modelo operacional.

Após cada integração, rode:

```bash
npm.cmd run test:run
services/twinops/.venv/Scripts/python.exe -m pytest services/twinops/tests -q
npm.cmd run build
git diff --check
```

**Não fecham o gate** (conhecidos e aceitos):

- Aviso do Vite de bundle acima de 500 kB.
- `StarletteDeprecationWarning` do FastAPI/httpx na suíte Python.

**Fecham o gate:** regressão nova, teste ignorado inesperado, queda de contagem
de testes não justificada por arquivos deletados, ou alteração dos hashes do
artefato ML.

## 7. Disciplina de git

- Um commit pequeno por task, com a mensagem exata que o plano especifica.
- `git add` apenas os caminhos que a task lista. Nunca `git commit -a`.
- Nunca `git reset --hard`, `git checkout .`, `git clean -fdx` — isso destrói o
  ledger de progresso em `.superpowers/sdd/`, que é git-ignored.
- Não faça push nem toque em `main` sem pedido explícito do humano.
- Cada plano começa em um worktree criado a partir do SHA do **gate anterior**,
  não de `main`.

## 8. Estado da entrega em curso

`.superpowers/sdd/` (git-ignored) guarda o estado vivo:

| Arquivo | Conteúdo |
| --- | --- |
| `progress.md` | Ledger: quais tasks estão completas, com SHAs e veredito de revisão |
| `HANDOFF-CODEX.md` | Onde a execução parou e qual é a próxima ação concreta |
| `plano-03-context.md` | Contexto compartilhado dos agentes do plano 03 |
| `task-N-brief.md` | Texto integral de cada task, extraído do plano |
| `task-N-report.md` | Relatório do implementador, com evidência de TDD |
| `review-<base>..<head>.diff` | Pacote de revisão de cada rodada |

**Leia `progress.md` e `HANDOFF-CODEX.md` antes de escrever qualquer código.**
O ledger é a fonte da verdade sobre o que já foi feito — confie nele e em
`git log`, não em suposição. Nunca re-execute uma task que o ledger marca como
completa.
