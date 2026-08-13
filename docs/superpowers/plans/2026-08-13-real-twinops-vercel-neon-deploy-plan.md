# Real TwinOps Vercel and Neon Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar frontend Vite, FastAPI v2, artefato ML, GLB e Postgres Neon em um demonstrador Vercel de custo zero.

**Architecture:** Um entrypoint Python fino expõe `create_app_v2`; Vercel serve Vite/GLB pela CDN e roteia `/api/**` para a Function FastAPI. Neon fornece persistência pooled; testes de preview usam upstream stub controlado antes do smoke real.

**Tech Stack:** Vercel Hobby/Fluid Compute, Python runtime, FastAPI, Vite, Neon Postgres, Playwright e Vercel CLI.

**Spec:** `docs/superpowers/specs/2026-08-13-forzy-twinops-real-vercel-zero-cost-design.md`

## Global Constraints

- Começar somente após integrar planos 01–04 e executar seus gates.
- Antes de provisionar Neon, instalar dependência ou criar projeto Vercel, obter confirmação do usuário; são mudanças externas.
- A CLI Vercel não está instalada. Instalação recomendada: `npm i -g vercel`.
- Hobby é demonstrativo/pessoal, sem SLA e sem cron frequente; não adicionar cron.
- `DATABASE_URL` usa conexão pooled e SSL.
- Secrets somente no backend; nunca prefixar com `VITE_`.
- Upstream real só é usado no smoke opt-in. Preview E2E usa stub HTTPS/controlado.
- Fixar os hashes ML exatos do índice; não recalculá-los a partir do próprio manifesto durante startup.
- Nenhuma cobrança automática, upgrade de plano ou domínio pago.
- Não fazer push ou deploy de produção sem autorização explícita no respectivo step.

## Mapa de arquivos

- `api/index.py`: entrypoint FastAPI Vercel.
- `requirements.txt`: instalação do pacote local e deps runtime.
- `vercel.json`: build Vite + roteamento API/SPA.
- `.vercelignore`: excluir CSV, notebooks, caches e artefatos de pesquisa.
- `.env.example`: contrato de env server-side.
- `scripts/verify_deployment.py`: probes sanitizados.
- `tests/e2e/deployed-real.spec.js`: jornada de preview.

---

### Task 1: Empacotamento Vercel reproduzível

**Files:**
- Create: `api/index.py`
- Create: `requirements.txt`
- Modify: `vercel.json`
- Create: `.vercelignore`
- Modify: `.env.example`
- Test: `services/twinops/tests/api/test_vercel_entrypoint.py`

**Interfaces:**
- Produces: `api.index.app` como FastAPI v2.
- Produces: build Vite em `dist` e Function Python para `/api/**`.

- [ ] **Step 1: Escrever teste de import sem side effects externos**

```python
def test_vercel_entrypoint_exposes_fastapi_without_contacting_upstream(monkeypatch):
    monkeypatch.setenv("TWINOPS_STARTUP_VALIDATE_ONLY", "1")
    module = importlib.import_module("api.index")
    assert isinstance(module.app, FastAPI)
```

- [ ] **Step 2: Rodar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/api/test_vercel_entrypoint.py -v`

Expected: FAIL por `api/index.py` ausente.

- [ ] **Step 3: Criar entrypoint e configuração**

`api/index.py` chama factory de env que seleciona Postgres e carrega o scorer. `requirements.txt` usa `-e ./services/twinops`. `vercel.json` preserva SPA fallback sem capturar `/api`. `.vercelignore` exclui `docs/**`, `notebooks/**`, `data/**`, `.worktrees/**`, `services/twinops/.venv/**`, caches e `artifacts/ml-public/**`, mas inclui `artifacts/ml/real-forzy/{pipeline.joblib,pipeline-config.json,backtest-report.json,model-card.md,feature-manifest.json}` e `public/models/**`.

- [ ] **Step 4: Validar build local**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/api/test_vercel_entrypoint.py -v`

Run: `npm.cmd run build`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add api/index.py requirements.txt vercel.json .vercelignore .env.example services/twinops/tests/api/test_vercel_entrypoint.py
git commit -m "build: package real twinops for Vercel"
```

### Task 2: Provisionar Neon e aplicar migração

**Files:**
- Create: `docs/deploy/neon.md`
- Create: `scripts/check_postgres.py`

**Interfaces:**
- Produces: integração Neon Marketplace ligada ao projeto Vercel e `DATABASE_URL`.

- [ ] **Step 1: Pedir autorização para instalar a CLI**

Pergunta exata: “Posso instalar a Vercel CLI globalmente e executar a descoberta somente leitura do Marketplace para confirmar a integração Neon Free?”

Expected: não instalar nada sem “sim”.

- [ ] **Step 2: Instalar CLI e confirmar a oferta pelo Marketplace**

Run: `npm i -g vercel`

Run: `vercel integration categories`

Run: `vercel integration discover --category storage`

Expected: Neon aparece como integração de storage e o plano Free está claramente disponível. Se a CLI devolver outro slug para storage, usar exatamente o slug listado por `categories`; não escolher provedor pago.

- [ ] **Step 3: Autorizar e provisionar Neon pelo Marketplace**

Pergunta exata: “A integração Neon Free foi confirmada. Posso criar/conectar o recurso ao projeto Vercel e aplicar a migração `002_real_twin_v2.sql`?”

Após “sim”, rode `vercel login`, `vercel link` e `vercel integration add neon --yes --no-claim`. Se a integração exigir claim ou etapa no navegador, pare para o usuário concluir; não substitua por provisionamento manual. Depois rode `vercel env pull .env.local --yes` e nunca commite o arquivo.

- [ ] **Step 4: Aplicar migração e verificar**

Run: `services\twinops\.venv\Scripts\python.exe scripts/check_postgres.py --migrate services/twinops/migrations/002_real_twin_v2.sql`

Expected: tabelas v2 existem; insert/read/delete de uma transação de teste passam; script não imprime DSN.

- [ ] **Step 5: Documentar a integração**

`docs/deploy/neon.md` registra plano Free, região, pooling, nomes de env, migração e como desconectar; não inclui IDs sensíveis/credenciais.

- [ ] **Step 6: Commit**

```powershell
git add docs/deploy/neon.md scripts/check_postgres.py
git commit -m "docs: add Neon deployment runbook"
```

### Task 3: Variáveis de ambiente e anchors confiáveis

**Files:**
- Create: `scripts/verify_env.py`
- Test: `services/twinops/tests/test_deploy_env.py`

**Interfaces:**
- Produces: `verify_deploy_env(env) -> DeployEnvReport` sem revelar valores.

- [ ] **Step 1: Escrever teste de env incompleto**

```python
def test_deploy_requires_database_upstream_and_pinned_artifact_hashes():
    report = verify_deploy_env({})
    assert set(report.missing) == {
        "DATABASE_URL", "TWINOPS_UPSTREAM_BASE_URL",
        "TWINOPS_ML_ARTIFACT_PATH", "TWINOPS_ML_MANIFEST_HASH", "TWINOPS_ML_MODEL_HASH",
    }
```

- [ ] **Step 2: Rodar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/test_deploy_env.py -v`

Expected: FAIL por script ausente.

- [ ] **Step 3: Implementar verificador e cadastrar envs**

Cadastre `TWINOPS_ML_MANIFEST_HASH=sha256:3319936da354fe9bb1ec37755940688abacd57876a44bfeda3e1d78fef39aed5` e `TWINOPS_ML_MODEL_HASH=sha256:68d00121edbf8c4c01cf7cd231cd57c4c8eff25661135494e3c791ca78e562ba` exatamente. `TWINOPS_ASSET_ID=forzy-motor-01`, timezone e intervalos são não-secretos. Use `vercel env add` ou Dashboard; não passar segredo em argumento que apareça no histórico.

- [ ] **Step 4: Executar verificação local e remota**

Run: `services\twinops\.venv\Scripts\python.exe scripts/verify_env.py --file .env.local`

Run: `vercel env ls`

Expected: nomes completos; saída não contém DSN nem hostname upstream completo.

- [ ] **Step 5: Commit**

```powershell
git add scripts/verify_env.py services/twinops/tests/test_deploy_env.py
git commit -m "test: validate zero cost deploy environment"
```

### Task 4: Preview deploy com upstream stub

**Files:**
- Create: `scripts/stub_forzy.py`
- Create: `tests/e2e/deployed-real.spec.js`
- Modify: `playwright.config.js`

**Interfaces:**
- Produces: stub controlado S1/S2 e E2E configurável por `DEPLOYMENT_URL`.

- [ ] **Step 1: Escrever E2E antes do deploy**

```js
test("preview refreshes and renders only the real asset", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Conjunto motor-bomba monitorado")).toBeVisible();
  await expect(page.getByText("TAG não fornecida")).toBeVisible();
  await expect(page.getByText(/Capturado pelo TwinOps às/).first()).toBeVisible();
  await expect(page.getByText(/MTR-BMB-042|Área 01|Ordens de serviço/)).toHaveCount(0);
});
```

- [ ] **Step 2: Rodar RED local**

Run: `npm.cmd run test:e2e -- tests/e2e/deployed-real.spec.js`

Expected: FAIL até o app v2 integrado estar configurado.

- [ ] **Step 3: Pedir autorização e fazer preview**

Pergunta exata: “Posso criar um preview Vercel desta branch usando o Neon Free e o upstream stub controlado?”

Run após aprovação: `vercel deploy`

Expected: URL de preview HTTPS.

- [ ] **Step 4: Executar E2E contra preview**

Defina `DEPLOYMENT_URL` fora do commit e rode Playwright. Valide GET snapshot, POST refresh, Postgres, ML e GLB. Confira logs com `vercel logs` sem payload raw/segredos.

- [ ] **Step 5: Commit dos testes**

```powershell
git add scripts/stub_forzy.py tests/e2e/deployed-real.spec.js playwright.config.js
git commit -m "test: validate deployed real twin flow"
```

### Task 5: Smoke real e deploy demonstrativo

**Files:**
- Create: `scripts/verify_deployment.py`
- Create: `docs/deploy/demo-runbook.md`

**Interfaces:**
- Produces: relatório sanitizado de health, snapshot e asset estático.

- [ ] **Step 1: Implementar probes sem escrita fora da janela**

O script sempre testa `GET snapshot`, `GET health`, HEAD/GET do manifesto/GLB. Só faz `POST refresh` com `--allow-live-refresh` e se a resposta do backend confirmar janela aberta.

- [ ] **Step 2: Executar smoke de preview**

Run: `services\twinops\.venv\Scripts\python.exe scripts/verify_deployment.py --url <preview>`

Expected: status 200, schema 2.0, asset correto, GLB alcançável, nenhum `assetTag`.

- [ ] **Step 3: Pedir autorização para produção**

Pergunta exata: “Preview validado. Posso promover esta versão para a URL de produção demonstrativa na Vercel?”

Run após aprovação: `vercel deploy --prod`

- [ ] **Step 4: Executar runbook de apresentação**

Registre: como verificar última captura, como demonstrar stale/expected_idle, como explicar score relativo, como confirmar cotas Vercel/Neon e como voltar ao deploy anterior. Não inclua fallback mock.

- [ ] **Step 5: Commit**

```powershell
git add scripts/verify_deployment.py docs/deploy/demo-runbook.md
git commit -m "docs: add real twin demo runbook"
```
