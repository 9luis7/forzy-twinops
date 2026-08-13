# Real TwinOps Execution Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coordenar a migração do protótipo fictício para um demonstrador real, de ativo único, publicável na Vercel sem custo e com uma trilha científica separada para datasets públicos.

**Architecture:** Seis planos isolam contrato, backend, frontend, 3D, deploy e pesquisa de ML. O contrato v2 é o primeiro gate; backend, frontend, 3D e laboratório podem então avançar sem compartilhar ownership, e o deploy integra somente entregas revisadas.

**Tech Stack:** React 18, Vite 5, Three.js/R3F, Python 3.11+, FastAPI, Pydantic 2, PostgreSQL/Neon, scikit-learn, pytest, Vitest, Playwright e Vercel.

**Spec:** `docs/superpowers/specs/2026-08-13-forzy-twinops-real-vercel-zero-cost-design.md`

## Global Constraints

- Base congelada para criação dos worktrees: `d1e919f0fab40b2d504ae00d2ad719899e26b7a2`.
- Identidade interna única: `forzy-motor-01`; `officialTag` permanece `null`.
- O navegador nunca acessa o hostname Forzy diretamente.
- `observedAt = receivedAt` somente com `timestampQuality="assumed_from_retrieval"` e `sourceTimestampProvided=false`.
- Polling automático somente com a página visível e dentro de seg/ter/qua `[12:00,14:00)` em `America/Sao_Paulo`.
- CSV Forzy não entra no banco nem na interface publicável; serve a treino, backtest e auditoria offline.
- Payload idêntico é auditado, mas não vira novo ponto de tendência nem nova informação para ML.
- O score publicado continua `relative_to_historical_baseline_not_failure_probability`.
- Mock, replay, ativos fictícios, copiloto, documentos, ordens e alertas inventados não pertencem ao runtime publicável.
- Nenhum dataset público substitui o artefato operacional sem validação por rolamento, entre bancadas e compatibilidade semântica.
- Provisionamento Neon e deploy Vercel são mudanças externas e exigem confirmação no início do plano 05.

## Baseline verificado

- Python: `119 passed, 1 skipped` em 2026-08-13.
- JavaScript: `79 passed` em 2026-08-13.
- Branch: `main`, 51 commits à frente de `origin/main` no SHA-base.
- Hash do manifesto ML: `sha256:3319936da354fe9bb1ec37755940688abacd57876a44bfeda3e1d78fef39aed5`.
- Hash do modelo ML: `sha256:68d00121edbf8c4c01cf7cd231cd57c4c8eff25661135494e3c791ca78e562ba`.

## Planos e dependências

| Ordem | Plano | Entrega | Depende de |
| --- | --- | --- | --- |
| 01 | `2026-08-13-real-twinops-contract-v2-plan.md` | Schemas, modelos e validators v2 | nenhuma |
| 02 | `2026-08-13-real-twinops-backend-plan.md` | Refresh, Postgres, snapshot, health e scorer | 01 |
| 03 | `2026-08-13-real-twinops-single-asset-ui-plan.md` | Interface única sem mock | 01; integra 02 |
| 04 | `2026-08-13-real-twinops-3d-plan.md` | GLB real, manifesto e canvas | 01 somente para identidade |
| 05 | `2026-08-13-real-twinops-vercel-neon-deploy-plan.md` | Preview e produção demonstrativa | 01–04 |
| 06 | `2026-08-13-public-fault-datasets-lab-plan.md` | Matriz, ablação e validação cross-bench | 01 para vocabulário; não bloqueia 05 |

## Ownership sem colisões

| Plano | Ownership exclusivo |
| --- | --- |
| 01 | `contracts/v2/**`, `services/twinops/src/twinops/contracts/v2_*`, `src/contracts/twinV2.*` |
| 02 | `services/twinops/src/twinops/{config_v2,ingestion/refresh_service,ingestion/live_adapter_v2,storage/postgres_repository,storage/v2_repository,api/v2_routes}.py`, `services/twinops/migrations/**` |
| 03 | `src/App.jsx`, `src/TwinOpsContext.jsx`, `src/dataSources/GatewayTwinDataSourceV2.js`, `src/components/operations/**`, `src/styles.css`, remoção dos módulos fictícios listados no plano |
| 04 | `tools/twin3d/**`, `public/models/**`, `src/components/Twin3D.jsx`, `src/components/twin3d/**` |
| 05 | `api/index.py`, `requirements.txt`, `vercel.json`, `.env.example`, `tests/e2e/deployed-real.spec.js`, documentação de deploy |
| 06 | `services/twinops/src/twinops/research/**`, `services/twinops/tests/research/**`, `data/public/README.md`, `artifacts/ml-public/**`, relatório da jornada |

`services/twinops/pyproject.toml` é serializado: plano 02 adiciona Postgres; plano 06 só altera o arquivo depois que 02 estiver integrado. O plano 04 usa `tools/twin3d/requirements.txt` para não colidir.

## Gates de integração

1. **Gate V2:** schemas JSON, Pydantic e validator JS aceitam as mesmas fixtures.
2. **Gate dados:** refresh parcial, dedupe, Postgres e artefato ML passam sem rede real.
3. **Gate honestidade:** busca estática não encontra imports de `data/mock`, replay ou TAG fictícia no bundle publicável.
4. **Gate 3D:** GLB carrega, manifesto referencia apenas nós existentes e nenhum sensor ganha posição.
5. **Gate deploy:** preview usa Neon e stub controlado; smoke real é separado e opt-in.
6. **Gate científico:** splits são por rolamento; resultado público não altera o modelo operacional.

## Estratégia de Git

Cada plano começa em um worktree criado a partir do SHA-base ou do SHA do gate anterior. Cada Task gera um commit pequeno. O integrador aplica os commits na ordem da tabela e executa, após cada integração:

```powershell
npm.cmd run test:run
services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests -q
npm.cmd run build
git diff --check
```

O aviso existente de bundle Vite acima de 500 kB não fecha o gate; regressões novas, testes ignorados inesperados ou alteração de hashes do artefato fecham.
