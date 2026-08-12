# Integração e verificação do demonstrador — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compor dados, scorer, frontend 3D e copiloto em um fluxo verificável, preservando replay e impedindo claims além da evidência.

**Architecture:** O coordenador integra branches na ordem dos contratos, resolve somente pontos de composição e executa uma suíte E2E baseada em fixtures antes do smoke opcional contra endpoints reais.

**Tech Stack:** Git, React/Vite/Vitest, Python/pytest/FastAPI, Playwright, JSON Schemas v1.

## Global Constraints

- Nenhum pacote é declarado completo isoladamente; a verificação usa o SHA composto.
- Smoke real não pertence à suíte determinística.
- Replay offline deve permanecer funcional.
- Ausência, stale e gap nunca viram zero ou normal.
- Nenhuma tela usa “probabilidade de falha”, “causa raiz”, “RUL”, “falha evitada” ou “tempo até falha” como resultado atual.
- Segredos e hostname temporário não podem aparecer no bundle.

---

### Task 1: Integrar branches e resolver somente contratos

**Files:**
- Modify: apenas arquivos de composição conflitantes (`package.json`, app/router, contracts).
- Create: `.sdd/integration-report.md` (scratch ignorado).

- [ ] **Step 1: Registrar SHAs e ordem de merge**

Ordem: contratos, aquisição, ML, frontend 3D, copiloto. Registrar base/head de
cada pacote e executar `git diff --check` após cada merge.

- [ ] **Step 2: Rodar testes focados após cada pacote**

Run: `npm.cmd run test:run`

Run: `python -m pytest services/twinops/tests -q`

Expected: PASS; se um pacote ainda não introduziu Python, registrar `not applicable`.

- [ ] **Step 3: Commit somente resoluções reais de composição**

```bash
git add <arquivos-de-composicao>
git commit -m "chore: integrate predictive demo workstreams"
```

### Task 2: E2E das rotas e estados degradados

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json`
- Create: `playwright.config.js`
- Create: `e2e/predictive-demo.spec.js`
- Create: `e2e/fixtures/*.json`

- [ ] **Step 1: Adicionar Playwright e escrever cenários falhando**

Cobrir replay, live S1+S2, S1 indisponível, payload repetido, stale,
insufficient data, GLB ausente e copiloto determinístico.

Run: `npm.cmd run test:e2e`

Expected: FAIL antes de fixtures/routes de interceptação estarem completas.

- [ ] **Step 2: Implementar fixtures/intercepts mínimos**

Não iniciar endpoint real. Cada cenário usa `TwinSnapshot` v1 versionado.

- [ ] **Step 3: Rodar E2E e commit**

Run: `npm.cmd run test:e2e`

Expected: todos os cenários PASS.

```bash
git add package.json package-lock.json playwright.config.js e2e
git commit -m "test: verify predictive demo end to end"
```

### Task 3: Auditoria automática de claims e bundle

**Files:**
- Create: `scripts/verify-demo-claims.mjs`
- Test: `scripts/verify-demo-claims.test.mjs`
- Modify: `package.json`

- [ ] **Step 1: Testar termos e segredos proibidos**

O teste cria fixture com claim indevido e exige exit code 1. O scanner verifica
`src`, `dist` e docs de resultado, permitindo termos apenas em seções marcadas
como capacidade futura/limitação.

- [ ] **Step 2: Implementar scanner e rodar build**

Run: `npm.cmd run build`

Run: `npm.cmd run verify:claims`

Expected: PASS e nenhuma ocorrência de `trycloudflare.com`, chaves ou claim
indevido no bundle.

- [ ] **Step 3: Commit**

```bash
git add scripts package.json
git commit -m "test: guard evidence claims and bundle secrets"
```

### Task 4: Relatório final reproduzível

**Files:**
- Modify: `docs/jornada/experimentos.md`
- Modify: `docs/jornada/storytelling-pitch.md`
- Create: `docs/jornada/resultados-demonstrador.md`

- [ ] **Step 1: Registrar versões, comandos e resultados numéricos**

Incluir SHA, dataset/hash, modelo/config hash, resultados por ciclo, latências,
status do Qwen/API, tamanho/FPS do GLB, limitações e falhas observadas.

- [ ] **Step 2: Verificar narrativa**

Run: `npm.cmd run verify:claims`

Expected: PASS.

- [ ] **Step 3: Rodar todas as suítes**

Run: `npm.cmd run test:run`

Run: `python -m pytest services/twinops/tests -q`

Run: `npm.cmd run test:e2e`

Run: `npm.cmd run build`

Expected: todas PASS; warnings preexistentes são registrados separadamente.

- [ ] **Step 4: Commit**

```bash
git add docs/jornada
git commit -m "docs: record predictive demo evidence"
```

