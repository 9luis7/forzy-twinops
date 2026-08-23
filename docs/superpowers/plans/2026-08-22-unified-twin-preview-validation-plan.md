# Unified Twin Preview Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:verification-before-completion` before every commit and `superpowers:requesting-code-review` before any remote gate.

**Goal:** Integrar histórico, timeline, decisão e twin 3D em uma jornada verificável; empacotar o runtime; e, somente após autorizações separadas, provar migration, stage/importação, materialização causal, ativação e preview sem promover produção.

**Architecture:** A validação começa totalmente local em SQLite e browser fixture-driven. Depois o bundle Vercel é auditado. Mudanças no Neon preview seguem compare-and-swap e fingerprint fail-closed. O preview é exercitado primeiro por GETs, depois por E2E de navegação sem refresh. Usabilidade humana e produção permanecem gates próprios.

**Tech Stack:** Python 3.12, FastAPI, SQLite, PostgreSQL/Neon, React 18, Vite 5, Playwright 1.47, pytest, Vitest, Vercel CLI e PowerShell.

**Spec:** `docs/superpowers/specs/2026-08-22-unified-history-interactive-twin-design.md`

**Depends on:** Task E1 is the ledger and frontend-only bundled-browser bootstrap and has no implementation dependency. Tasks E2–E9 depend on reviewed outputs from `2026-08-22-forzy-history-foundation-plan.md`, `2026-08-22-operational-timeline-api-plan.md`, `2026-08-22-decision-oriented-timeline-ui-plan.md`, and `2026-08-22-interactive-engineering-twin-plan.md`.

## Global Constraints

- Base de planejamento: `4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e`; execução começa no SHA que integra A+B+C+D com re-reviews verdes.
- Não iniciar esta execução se qualquer plano dependente tiver Critical/Important aberto.
- Migration preview, stage do CSV, materialização das avaliações causais, ativação do lote e deploy preview exigem cinco confirmações explícitas distintas.
- Nenhuma etapa autoriza produção. Migration, stage/importação, materialização de assessments, ativação e deploy/promoção production são cinco operações proibidas até autorizações novas e independentes; `vercel deploy --prod` e `vercel promote` nunca aparecem neste fluxo preview.
- O CSV nunca entra no Git, build context, bundle, rota ou log. Seu path absoluto só existe na entrada local do operador.
- O smoke padrão usa apenas GET. Nenhum `POST /refresh` participa da prova de histórico/3D.
- Preview deve usar banco/branch isolado e fingerprint esperado; mismatch bloqueia antes de `BEGIN`.
- `assessment.recommendation`, bytes brutos, DSN, host completo, path local e payload Forzy não entram em screenshots ou relatórios.
- A Vercel CLI não está instalada no ambiente atual. Esta execução reproduzível requer aprovação explícita para `npm.cmd install --global vercel@59.3.0`, além de rede; não tente contornar a ausência com wrappers ad hoc nem instalar outra versão.
- O worktree compartilhado deve fixar `PYTHONPATH` para não importar o editable install do checkout principal.
- A Task E1 é um bootstrap de coordenação e do browser frontend-only; roda antes da Fase A e recebe review independente antes de qualquer worker A começar. As Tasks E2–E9 só começam depois que A+B+C+D estiverem integrados e revisados.
- O navegador E2E é o Chromium versionado pelo `@playwright/test`/lockfile; `channel: "chrome"` ou outro navegador instalado no sistema é proibido.
- Nenhum `vercel build`, `vercel env run` ou processo filho que receba variáveis preview começa sem autorização explícita de acesso ao ambiente preview. Variáveis são injetadas somente na memória do processo filho; `vercel pull`, `vercel env pull`, `.env.local` e qualquer export persistido são proibidos.
- Deployment Protection permanece habilitada. GETs automatizados usam o caminho oficial `vercel curl`; Playwright usa `x-vercel-protection-bypass` somente a partir de `VERCEL_AUTOMATION_BYPASS_SECRET` fornecido com autorização explícita e mantido apenas no ambiente do filho. Query-string de bypass, exceção pública, remoção ou relaxamento da proteção são proibidos.
- Toda retomada após uma autorização começa em um novo comando do controlador versionado `scripts/unified_preview_gate.py`, que relê um checkpoint sanitizado `preview-gate-checkpoint-v1`. Nenhuma retomada depende de variáveis, funções ou objetos mantidos por uma sessão PowerShell anterior.
- Antes de cada comando remoto — inclusive proteção, dry-run, apply, check, revalidation, build, deploy, list/inspect, smoke, browser, sessão humana e logs — o controlador revalida SHA de código, status Git com allowlist explícita de untracked, blobs dos scripts executáveis, path/hash/versão `59.3.0` da CLI, path/hash congelados de `curl.exe`, link, project, team e scope. Qualquer divergência bloqueia antes de rede ou `BEGIN`.
- Todo processo nativo em bloco executável captura e testa `$LASTEXITCODE` **imediatamente**, antes de qualquer outro comando. Isso inclui RED/GREEN, cada mutação/verificação do ledger, `git add|commit|rev-parse|diff|status|merge-base`, Vercel, Node/npm e o controlador; um teste RED exige explicitamente exit não zero. Captura tardia ou depender do exit de um comando posterior é proibido.
- Toda fronteira de commit começa com índice vazio, fixa o `HEAD` pai esperado, recebe uma allowlist exata de paths, confirma que o diff staged é exatamente essa allowlist, executa `git diff --cached --check`, cria o commit e prova tanto o novo `HEAD` 40-hex quanto seu pai direto. A Task E1 faz essa prova manualmente no bootstrap; todas as fronteiras posteriores usam o helper PS5.1 versionado e testado `scripts/verify_git_commit_boundary.ps1`.
- Estado de Deployment Protection é uma entrada tipada e read-only: método, scope, bypass configurado e exceptions são lidos somente após autorização, e reatestados antes/depois do deploy, antes de smoke/browser e no gate final. O host da URL preview exata não pode estar exceptuado.

### Task E1: Freeze the integrated acceptance matrix and bundled-browser bootstrap

**Files:**
- Create: `docs/verification/unified-twin-acceptance-v1.json`
- Create: `docs/verification/unified-twin-acceptance-v1.md`
- Create: `scripts/verify_unified_acceptance.py`
- Create: `services/twinops/tests/test_verify_unified_acceptance.py`
- Create: `scripts/verify_git_commit_boundary.ps1`
- Create: `services/twinops/tests/test_git_commit_boundary_script.py`
- Create: `playwright.twin.config.js`
- Create: `tests/e2e/playwright-twin-config.test.js`
- Modify: `docs/superpowers/plans/2026-08-22-unified-history-interactive-twin-execution-index.md`
- Create after independent review: `docs/verification/phase-e1-bootstrap-findings.json`

- [ ] **Step 1: Write the failing acceptance-ledger test**

Create a fixture in the test with all 28 spec criteria, owning plan, gate and allowed evidence kinds:

```python
HUMAN_ONLY = {"AC-18", "AC-28"}
OWNER_CRITERIA = {
    "A": ("AC-06",),
    "B": ("AC-13", "AC-14"),
    "C": ("AC-01", "AC-02", "AC-03", "AC-04", "AC-05", "AC-07", "AC-11", "AC-16", "AC-17", "AC-19", "AC-21", "AC-22", "AC-25", "AC-26", "AC-27"),
    "D": ("AC-08", "AC-09", "AC-10", "AC-20", "AC-23"),
    "E": ("AC-12", "AC-15", "AC-18", "AC-24", "AC-28"),
}

def test_acceptance_ledger_has_every_spec_criterion_and_never_auto_closes_human_gates():
    report = verify_acceptance(Path("docs/verification/unified-twin-acceptance-v1.json"))
    assert report.criteria == tuple(f"AC-{index:02d}" for index in range(1, 29))
    owned = tuple(criterion for criteria in OWNER_CRITERIA.values() for criterion in criteria)
    assert len(owned) == 28
    assert len(set(owned)) == 28
    assert tuple(sorted(owned, key=lambda value: int(value.removeprefix("AC-")))) == report.criteria
    assert all(report.entries[criterion].owner_plan == owner for owner, criteria in OWNER_CRITERIA.items() for criterion in criteria)
    assert {entry.owner_plan for entry in report.entries.values()} <= set("ABCDE")
    assert all(entry.gate in {"local", "database", "preview", "human"} for entry in report.entries.values())
    for criterion_id in HUMAN_ONLY:
        entry = report.entries[criterion_id]
        assert entry.allowed_evidence_kinds == ("human",)
        assert entry.status != "passed" or entry.evidence_kind == "human"
```

Add one narrow `test_acceptance_verifier_contract_is_required` that performs the optional import inside the test body and emits `E1_ACCEPTANCE_VERIFIER_MISSING` only while the implementation is absent. In `test_git_commit_boundary_script.py`, add `test_commit_boundary_helper_is_required`, which invokes PS5.1 in an isolated fixture and emits `E1_COMMIT_BOUNDARY_HELPER_MISSING` only while the helper/functions are absent. Both become positive interface tests after GREEN; neither may break collection.

- [ ] **Step 2: Run RED**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
$pythonRedOutput=@(& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest `
  services/twinops/tests/test_verify_unified_acceptance.py::test_acceptance_verifier_contract_is_required `
  services/twinops/tests/test_git_commit_boundary_script.py::test_commit_boundary_helper_is_required -q 2>&1)
$pythonRedExit=$LASTEXITCODE
if ($pythonRedExit -ne 1) { throw "Python RED had unexpected exit $pythonRedExit" }
$pythonRedText=($pythonRedOutput -join "`n")
if ($pythonRedText -notmatch 'E1_ACCEPTANCE_VERIFIER_MISSING' -or $pythonRedText -notmatch 'E1_COMMIT_BOUNDARY_HELPER_MISSING' -or $pythonRedText -notmatch '\b2 failed\b' -or $pythonRedText -match 'ERROR collecting|ModuleNotFoundError|ImportError|not found') { throw 'Python RED did not fail only on the two targeted E1 contract assertions' }
$frontendRedOutput=@(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" tests/e2e/playwright-twin-config.test.js 2>&1)
$frontendRedExit=$LASTEXITCODE
if ($frontendRedExit -ne 1) { throw "frontend RED had unexpected exit $frontendRedExit" }
$frontendRedText=($frontendRedOutput -join "`n")
if ($frontendRedText -notmatch 'E1_PLAYWRIGHT_TWIN_CONFIG_MISSING' -or $frontendRedText -notmatch '\b1 failed\b' -or $frontendRedText -match 'No test files found|ERR_MODULE_NOT_FOUND|Cannot find module') { throw 'frontend RED did not fail on the targeted E1 config contract' }
```

Expected: both commands exit exactly `1`; the tests catch absent implementation inside the targeted test body and emit only the stable contract markers above. Exit `2`, collection/import/path failures or a different test failure are not an acceptable RED.

Also create a RED test for `playwright.twin.config.js`. It must require the bundled `chromium` project with no `channel`, a fixed loopback Vite base URL and frontend-only web server, `reuseExistingServer: false`, and a narrow `testMatch` limited to the D-owned twin specs. It must reject any Python backend command, database path, `.env` loader, deployment URL or network credential. The test catches the absent file in its own test body and fails with `E1_PLAYWRIGHT_TWIN_CONFIG_MISSING`; it must not fail during test discovery.

- [ ] **Step 3: Implement the closed ledger format**

`unified-twin-acceptance-v1.json` is the tracked source of truth. `verify_unified_acceptance.py` must parse it and render `unified-twin-acceptance-v1.md`; the Markdown file is generated evidence and is never edited independently. The JSON contains exactly `schemaVersion`, `specSha256`, `criteria`, `plans` and `findings`. Every criterion contains exactly `criterionId`, `ownerPlan`, `gate`, `allowedEvidenceKinds`, `status`, nullable `evidenceKind`, `evidenceRefs` and nullable `verifiedCodeCommit`. Freeze the literal ownership above. AC-06 uses gate/evidence kind `database`; AC-13/14 and every C/D-owned criterion use `local`/`automated`; AC-12 and AC-24 use `preview`/`preview`; AC-15 is E-owned `local`/`automated`; AC-18 and AC-28 use `human`/`human`. C authors the AC-15 scenario and locators, but only E executes it on the exact final integrated code SHA and closes it. No criterion changes owner at runtime. `plans` has exactly `A` through `E`, each with `status`, nullable `verifiedCodeCommit`, nullable `reviewVerdict`, cumulative `findingIds` and `evidenceRefs`. `findings` is a root map keyed by globally unique finding ID, so a later review can close but never erase an earlier issue. The Git commit containing a ledger mutation is the **evidence commit** and is recorded in the handoff/review metadata after the commit exists; it is deliberately not embedded into that same JSON, avoiding a self-referential commit loop.

Create `playwright.twin.config.js` in this same bootstrap commit. It serves only the Vite frontend on a fixed loopback origin, uses the bundled Playwright Chromium with no system-browser channel, disables server reuse, and selects only the D-owned twin specs. It must not start Python, import backend state, read env files or accept a deployment URL. This lets D close its visual interaction gate before E Task E2 introduces the separate integrated SQLite/backend configuration in `playwright.config.js`.

Every independent reviewer emits this one strict JSON shape:

```json
{
  "schemaVersion": "finding-review-v1",
  "plan": "A",
  "reviewedSha": "0000000000000000000000000000000000000000",
  "verdict": { "critical": 0, "important": 0, "minor": 0 },
  "findings": []
}
```

Each non-empty review finding has exactly `findingId`, `severity`, `status`, `title`, `evidenceRefs` and nullable `resolvedSha`; status is `open|fixed|accepted`, severity is `critical|important|minor`, only `fixed|accepted` may carry `resolvedSha`, and `accepted` is legal only for a Minor explicitly accepted by the user. On first `open`, the ledger derives immutable `introducedSha` from the report's `reviewedSha`; a later `fixed|accepted` must retain ID/severity/title lineage and supply exact resolution SHA plus evidence. The verdict counts the currently open findings by severity and must equal the report contents. There is no `update-plan` command: only authenticated code-review ingestion may set `verifiedCodeCommit` and `reviewVerdict`. E1 provides ordinary `ingest-review`; E5 later adds the narrower `ingest-authenticated-review-lineage` solely for the digest-bound operational→final E review. A distinct `ingest-evidence-review` command exists only for a review whose `reviewedSha` is an already-created evidence commit: it requires the immutable code SHA and evidence SHA separately, preserves `plans.E.verifiedCodeCommit` and `plans.E.reviewVerdict` byte-for-byte, merges only cumulative finding history/evidence refs, and re-derives blocking state without ever treating the evidence SHA as deployed code. The plan closes through explicit commands such as:

```powershell
& "..\..\services\twinops\.venv\Scripts\python.exe" scripts/verify_unified_acceptance.py ingest-review --ledger docs/verification/unified-twin-acceptance-v1.json --review-report docs/verification/phase-a-findings.json
if ($LASTEXITCODE -ne 0) { throw 'review ingestion failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" scripts/verify_unified_acceptance.py ingest-evidence-review --ledger docs/verification/unified-twin-acceptance-v1.json --review-report docs/verification/phase-e-evidence-findings.json --verified-code-commit $env:VERIFIED_CODE_COMMIT --evidence-commit $env:EVIDENCE_COMMIT
if ($LASTEXITCODE -ne 0) { throw 'evidence-review ingestion failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" scripts/verify_unified_acceptance.py update-criterion --ledger docs/verification/unified-twin-acceptance-v1.json --criterion AC-01 --status passed --evidence-kind automated --evidence-ref services/twinops/tests/example.py --verified-code-commit $env:VERIFIED_CODE_COMMIT
if ($LASTEXITCODE -ne 0) { throw 'criterion update failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
if ($LASTEXITCODE -ne 0) { throw 'ledger rendering failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'ledger verification failed' }
```

The same verifier also exposes a non-ledger evidence command used later by B:

```powershell
& "..\..\services\twinops\.venv\Scripts\python.exe" scripts/verify_unified_acceptance.py export-local-causal-manifest --source-result $localAssessmentResult --source-not-before $localAssessmentStartedAt.ToString('o') --reviewed-code-commit $phaseBCodeCommit --expected-batch-id $batchId --expected-artifact-sha256 $artifactSha --expected-report-sha256 $reportSha --expected-config-sha256 $configSha --output docs/verification/phase-b-local-causal-manifest.json
if ($LASTEXITCODE -ne 0) { throw 'local causal manifest export failed' }
```

`export-local-causal-manifest` accepts only a fresh, direct, non-reparse child named `build-assessments-local-causal-<nonce>.json` under the guarded worktree `tmp/twinops-admin-results` directory; `--source-not-before` is mandatory and the source mtime must be no older than that RFC3339 instant. The source must have the closed `build-assessments` result shape, `environment="local"`, `mode="dry-run"`, `writesPerformed=0`, batch/artifact/report/config identities equal to the four explicit `--expected-*` arguments, `validatedAnchorCount=assessmentCount`, `validatedEpisodeCount=candidateCount`, both violation counts zero and no path, DSN, timestamp, row or target fingerprint. The output is canonical JSON with exactly `schemaVersion="1.0"`, `kind="phase-b-local-causal-manifest"`, `reviewedCodeCommit`, `batchId`, `artifactSha256`, `reportSha256`, `configSha256`, `assessmentManifestSha256`, `assessmentCount`, `candidateCount`, `validatedAnchorCount`, `validatedEpisodeCount`, `anchorInvariantViolationCount`, `episodeInvariantViolationCount` and `sourceResultSha256`. It is written by temp file + fsync + atomic replace, reparsed and byte-verified. Tests reject stale/reparse/external sources, nonlocal or write-capable results, extra/missing keys, causal/count/expected-identity mismatches and a reviewed SHA other than the exact B code commit.

All E1 mutation commands use temp-file + atomic replace, reject unknown plans/criteria/findings or stale reviewed SHAs, preserve all prior findings/evidence refs, then atomically render and byte-verify Markdown before returning success; the E5 lineage extension must preserve the same guarantees. `ingest-review` records `reviewedSha` as that plan's `verifiedCodeCommit`; plan status is derived as `blocked` for any open Critical/Important or failed/blocked owned criterion, `in_progress` for a clean review with any owned criterion still pending, and `passed` only when the incoming verdict has zero Critical/Important, every cumulative Critical/Important is `fixed`, and every plan-owned criterion is `passed`. It may close an existing Critical/Important only as `fixed`; only a Minor may be `accepted` with user-acceptance evidence. `ingest-evidence-review` accepts only `plan="E"`, requires `reviewedSha == --evidence-commit`, requires both SHAs to exist as commits, and requires the current ledger's `plans.E.verifiedCodeCommit == --verified-code-commit`; it rejects equal code/evidence SHAs and any attempt to change the stored code verdict/SHA. Its report may open/fix/accept findings under the same lineage rules, so open Critical/Important blocks E, but it does not promote a pending E criterion or replace the code/deployment review. `update-criterion` requires an allowed evidence kind, refuses human-only criteria unless `evidence-kind=human`, and refuses a SHA different from its owning plan's `verifiedCodeCommit`. The parser uses these closed entries:

```python
@dataclass(frozen=True)
class AcceptanceEntry:
    criterion_id: str
    owner_plan: Literal["A", "B", "C", "D", "E"]
    gate: Literal["local", "database", "preview", "human"]
    allowed_evidence_kinds: tuple[Literal["automated", "database", "preview", "human"], ...]
    status: Literal["pending", "passed", "failed", "blocked"]
    evidence_kind: Literal["automated", "database", "preview", "human"] | None
    evidence_refs: tuple[str, ...]
    verified_code_commit: str | None

@dataclass(frozen=True)
class FindingEntry:
    finding_id: str
    plan: Literal["A", "B", "C", "D", "E"]
    severity: Literal["critical", "important", "minor"]
    status: Literal["open", "fixed", "accepted"]
    title: str
    introduced_sha: str
    resolved_sha: str | None
    evidence_refs: tuple[str, ...]

@dataclass(frozen=True)
class PlanLedger:
    plan: Literal["A", "B", "C", "D", "E"]
    status: Literal["pending", "in_progress", "passed", "failed", "blocked"]
    verified_code_commit: str | None
    review_verdict: tuple[int, int, int] | None  # critical, important, minor
    finding_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
```

Reject duplicate/missing IDs, malformed review-count totals, unknown evidence kinds, `passed` without refs/code SHA, a plan status that discards a prior finding, Critical/Important `accepted`, and human criteria marked passed by an automated ref. Tests ingest open→fixed code reviews; ingest an evidence review while asserting the stored code SHA/verdict are unchanged; reject a mismatched evidence `reviewedSha`, equal code/evidence SHAs, Critical/Important open→accepted, stale-SHA reviews and conflicting finding reuse; update criteria; export and byte-verify the guarded local causal manifest; derive plan state; prove the owner matrix covers AC-01..AC-28 exactly once; and prove Markdown is reproduced byte-for-byte from JSON after **every** ledger mutation. The final PASS review of an evidence commit is intentionally delivered externally and never self-ingested into the commit it reviews. The initial JSON maps AC-01..AC-28 to owning plans/gates/allowed kinds, initializes five plan ledgers, and starts all criteria and remote/human gates as `pending`.

The normal `verify` command intentionally accepts a valid initial or in-progress ledger. It also implements `verify --require-complete` for Task E9. That closed mode requires plans A–E all `passed`; AC-01..AC-28 exactly once, all `passed`, owned by the frozen matrix, bound to the owning plan's verified code SHA and carrying a valid allowed evidence kind/ref; zero open Critical/Important; and no unresolved Minor (each Minor must be `fixed` or explicitly user-`accepted`). Tests prove pending is legal in normal mode and rejected by `--require-complete`, and cover wrong owner SHA, missing evidence, duplicate/missing AC, open Critical/Important and unresolved Minor.

Implement `scripts/verify_git_commit_boundary.ps1` as a dot-sourced PS5.1 helper exposing `Get-ExactGitHead` and `Invoke-ExactGitCommit -ExpectedParent <40hex> -Paths <string[]> -Message <string>`. `Get-ExactGitHead` captures native output, checks exit before trimming/parsing and returns one 40-hex SHA. The commit helper rejects a moved/invalid parent, nonempty initial index, duplicate/non-repository-relative paths, missing or unchanged allowlisted paths, any staged path outside or absent from the exact allowlist, cached whitespace errors, commit failure, a non-40-hex/moved new `HEAD`, merge commits or a parent other than `ExpectedParent`; it returns only the new commit SHA after re-reading `HEAD`. Every native exit is checked immediately. Its Python test creates isolated temporary repositories and covers success plus each fail-closed case, including an extra pre-staged file and a concurrent parent move. The helper never resets, unstages or deletes user state.

- [ ] **Step 4: Run GREEN and full ledger self-check**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/test_verify_unified_acceptance.py services/twinops/tests/test_git_commit_boundary_script.py -q
if ($LASTEXITCODE -ne 0) { throw 'ledger tests failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
if ($LASTEXITCODE -ne 0) { throw 'ledger rendering failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'ledger verification failed' }
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" tests/e2e/playwright-twin-config.test.js
if ($LASTEXITCODE -ne 0) { throw 'frontend-only Playwright config test failed' }
```

Expected: focused test passes and CLI prints only `acceptance_ledger_ok criteria=28 passed=<n> pending=<n>`.

- [ ] **Step 5: Probe, install only with authorization, and launch the pinned Chromium**

Run the executable probe from the exact lockfile-owned package. The probe prints only the Playwright package version, Chromium revision/executable SHA-256 and a boolean launch result; it never prints the absolute browser-cache path:

```powershell
$probe = @'
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { chromium } = require("@playwright/test");
const packageVersion = require("@playwright/test/package.json").version;
const browsersPath = path.join(path.dirname(require.resolve("playwright-core/package.json")), "browsers.json");
const browsers = JSON.parse(fs.readFileSync(browsersPath, "utf8"));
const chromiumRevision = String(browsers.browsers.find(({ name }) => name === "chromium")?.revision ?? "");
if (!/^\d+$/.test(chromiumRevision)) process.exit(45);
const executable = chromium.executablePath();
if (!fs.existsSync(executable)) process.exit(42);
(async () => {
  const bytes = fs.readFileSync(executable);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setContent("<main>bundled chromium ready</main>");
  if ((await page.textContent("main")) !== "bundled chromium ready") process.exit(43);
  await browser.close();
  console.log(JSON.stringify({ packageVersion, chromiumRevision, executableSha256: crypto.createHash("sha256").update(bytes).digest("hex"), launched: true }));
})().catch(() => process.exit(44));
'@
$probeBase64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($probe))
$nodeBase64Launcher='eval(Buffer.from(process.argv[1],process.argv[2]).toString())'
node -e $nodeBase64Launcher $probeBase64 base64
$chromiumProbeExit=$LASTEXITCODE
if ($chromiumProbeExit -eq 42) { throw 'bundled Chromium missing; stop and request the exact install authorization' }
if ($chromiumProbeExit -eq 45) { throw 'canonical Chromium revision could not be proven' }
if ($chromiumProbeExit -ne 0) { throw "bundled Chromium probe failed with exit $chromiumProbeExit" }
```

If exit is `42`, stop and request explicit network/install authorization for exactly `npx.cmd playwright install chromium`; immediately require its exit zero, do not run it before approval and do not add `channel: "chrome"`. After an authorized install, rerun the same probe from a fresh PowerShell process. Exit `45` means the canonical `playwright-core/browsers.json` revision could not be proven; any other nonzero exit is a launch failure. The reviewer reruns the probe and requires the reported revision to equal the lockfile-owned Chromium entry selected by `@playwright/test@1.47.2`.

- [ ] **Step 6: Commit the E1 code bootstrap and freeze its SHA**

```powershell
$phaseE1ExpectedParentRaw=@(git rev-parse HEAD)
$phaseE1ExpectedParentExit=$LASTEXITCODE
if ($phaseE1ExpectedParentExit -ne 0) { throw 'E1 expected-parent lookup failed' }
$phaseE1ExpectedParent=($phaseE1ExpectedParentRaw -join '').Trim()
if ($phaseE1ExpectedParent -notmatch '^[0-9a-f]{40}$') { throw 'invalid E1 expected parent' }
$initialIndex=@(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0 -or $initialIndex.Count -ne 0) { throw 'E1 bootstrap requires an empty index' }
$phaseE1Paths=@(
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md',
  'scripts/verify_unified_acceptance.py',
  'services/twinops/tests/test_verify_unified_acceptance.py',
  'scripts/verify_git_commit_boundary.ps1',
  'services/twinops/tests/test_git_commit_boundary_script.py',
  'playwright.twin.config.js',
  'tests/e2e/playwright-twin-config.test.js',
  'docs/superpowers/plans/2026-08-22-unified-history-interactive-twin-execution-index.md'
)
git add -- $phaseE1Paths
if ($LASTEXITCODE -ne 0) { throw 'E1 staging failed' }
$actualE1Raw=@(git diff --cached --name-only)
$actualE1Exit=$LASTEXITCODE
if ($actualE1Exit -ne 0) { throw 'E1 cached path enumeration failed' }
$actualE1Paths=@($actualE1Raw | Sort-Object)
if (Compare-Object ($phaseE1Paths | Sort-Object) $actualE1Paths) { throw 'E1 staged scope is not exact' }
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'E1 cached diff check failed' }
git commit -m "test: freeze unified twin acceptance ledger"
if ($LASTEXITCODE -ne 0) { throw 'E1 code commit failed' }
$phaseE1CodeCommitRaw=@(git rev-parse HEAD)
$phaseE1CodeCommitExit=$LASTEXITCODE
if ($phaseE1CodeCommitExit -ne 0) { throw 'E1 code-commit lookup failed' }
$phaseE1CodeCommit=($phaseE1CodeCommitRaw -join '').Trim()
if ($phaseE1CodeCommit -notmatch '^[0-9a-f]{40}$' -or $phaseE1CodeCommit -ceq $phaseE1ExpectedParent) { throw 'invalid E1 code commit' }
$phaseE1ActualParentRaw=@(git rev-parse "$phaseE1CodeCommit^")
$phaseE1ActualParentExit=$LASTEXITCODE
if ($phaseE1ActualParentExit -ne 0) { throw 'E1 direct-parent lookup failed' }
$phaseE1ActualParent=($phaseE1ActualParentRaw -join '').Trim()
if ($phaseE1ActualParent -cne $phaseE1ExpectedParent) { throw 'E1 code commit has the wrong direct parent' }
```

- [ ] **Step 7: Independently review E1 before Phase A starts**

An independent reviewer checks exactly `$phaseE1CodeCommit`, reruns the ledger/config tests and Chromium probe, verifies that the config is frontend-only, and writes `docs/verification/phase-e1-bootstrap-findings.json` in strict `finding-review-v1` shape with `plan="E"` and `reviewedSha=$phaseE1CodeCommit`. Zero open Critical/Important is mandatory. Fixes require a new code commit, new probe and new review.

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$phaseE1CodeCommit=Get-ExactGitHead
$review=Get-Content -Raw -Encoding UTF8 docs/verification/phase-e1-bootstrap-findings.json | ConvertFrom-Json
if ([string]$review.plan -cne 'E' -or [string]$review.reviewedSha -cne $phaseE1CodeCommit -or [int]$review.verdict.critical -ne 0 -or [int]$review.verdict.important -ne 0) { throw 'E1 independent review is not clean or is misbound' }
& $python scripts/verify_unified_acceptance.py ingest-review --ledger docs/verification/unified-twin-acceptance-v1.json --review-report docs/verification/phase-e1-bootstrap-findings.json
if ($LASTEXITCODE -ne 0) { throw 'E1 review ingestion failed' }
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
if ($LASTEXITCODE -ne 0) { throw 'E1 ledger rendering failed' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'E1 ledger ingestion failed' }
$phaseE1EvidenceCommit=Invoke-ExactGitCommit -ExpectedParent $phaseE1CodeCommit -Paths @(
  'docs/verification/phase-e1-bootstrap-findings.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) -Message 'docs: record reviewed E1 bootstrap'
git merge-base --is-ancestor $phaseE1CodeCommit $phaseE1EvidenceCommit
if ($LASTEXITCODE -ne 0) { throw 'E1 evidence does not descend from E1 code' }
```

A second independent check of `$phaseE1EvidenceCommit` confirms its diff from `$phaseE1CodeCommit` contains only the three declared evidence files and returns PASS externally. Record both SHAs in the E1 handoff; never write `$phaseE1EvidenceCommit` into the commit that created it. Phase A remains blocked until this check passes.

### Task E2: Preflight the integrated ancestry and prove the complete journey in isolated SQLite

**Files:**
- Create: `scripts/verify_phase_e_preflight.py`
- Create: `services/twinops/tests/test_verify_phase_e_preflight.py`
- Create during execution only: `tmp/twinops-preview-gate/e2-preflight-v1.json` (sanitized, ignored, direct child)
- Modify: `scripts/e2e_backend.py`
- Modify: `playwright.config.js`
- Create: `services/twinops/tests/integration/test_unified_history_timeline_sqlite.py`
- Replace: `tests/e2e/real-history-live.spec.js`
- Create: `scripts/support/unified_history_fixture.py`

- [ ] **Step 1: Write RED tests for the executable E2 preflight**

`test_verify_phase_e_preflight.py` builds temporary Git graphs and strict JSON fixtures. Require failures for: wrong spec hash; execution-index blob not descending from reviewed E1; missing/failed A–D plan; any open cumulative Critical/Important; review report missing from or differing from its separately supplied evidence commit; code/evidence SHA not ancestral to the integrated commit; any extra/missing/renamed path in the exact E1 three-file, A three-file, B four-file, C four-file or D seven-file code→evidence allowlist; any immutable phase report/manifest/artifact in the current tree that differs from its raw `git show <evidence>:<path>` blob; any raw ledger snapshot that is invalid, misbound or not monotonically represented in the final cumulative ledger; Phase B manifest read from the B code commit instead of the B evidence commit; absent, stale or failed `phase-c-gate-manifest-v1`; dirty tracked or untracked files; equal/reordered D7/C11/D8 SHAs; D7 without the public seam paths; C11 without dashboard wiring or with D-owned implementation paths; and D8 without the interactive browser gate. The passing graph must prove `base → E1`, every A–D code/evidence commit ancestral to `integrated`, and independently the strict visual chain `D7 → C11 → D8 → integrated`; it allows parallel commits only when all required ancestry edges remain true.

- [ ] **Step 2: Run the preflight RED test**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$redOutput=@(& $python -m pytest services/twinops/tests/test_verify_phase_e_preflight.py::test_preflight_rejects_missing_executable_with_targeted_marker -q 2>&1)
$redExit=$LASTEXITCODE
if ($redExit -ne 1) { throw "E2 preflight RED had unexpected exit $redExit" }
$redText=($redOutput -join "`n")
if ($redText -notmatch 'E2_PREFLIGHT_EXECUTABLE_MISSING' -or $redText -notmatch '\b1 failed\b' -or $redText -match 'ERROR collecting|ModuleNotFoundError|ImportError|not found') { throw 'E2 preflight RED did not fail on its targeted contract assertion' }
```

Expected: exit exactly `1` and `E2_PREFLIGHT_EXECUTABLE_MISSING`. The test performs the optional import inside the named test body; exit `2`, collection/import/path errors or any unrelated failure are rejected.

- [ ] **Step 3: Implement the closed E2 preflight**

The verifier accepts only repository-relative fixed paths for the spec, index, ledger, E1/A/B/C/D review reports, B causal manifest and C gate manifest. It accepts the five separately recorded evidence-commit SHAs, plus exact D7/C11/D8 handoff SHAs. It must:

1. require spec SHA-256 `20629d860f19a212bc2b941d6270e2316c747a0b85c473f0b51bbee6106e3a44` and require the current execution-index blob to equal the blob reviewed in `$phaseE1CodeCommit`;
2. parse JSON with duplicate-key rejection and exact key sets; require plans A–D `status="passed"`, 40-hex `verifiedCodeCommit`, zero review Critical/Important, every A–D-owned criterion passed on its owning SHA, and no open cumulative Critical/Important finding;
3. for E1 and A–D, require `git diff --name-only <code>..<evidence>` to equal its literal allowlist and read **every** allowed path as raw bytes with `git show <evidence>:<path>`; rehash those bytes and bind the parsed review's `reviewedSha` to the corresponding ledger code SHA. The exact allowlists are: E1 = `docs/verification/phase-e1-bootstrap-findings.json` plus ledger JSON/Markdown; A = `docs/verification/phase-a-findings.json` plus ledger JSON/Markdown; B = `docs/verification/phase-b-local-causal-manifest.json`, `docs/verification/phase-b-findings.json` plus ledger JSON/Markdown; C = `docs/verification/phase-c-findings.json`, `docs/verification/phase-c-gate-manifest.json` plus ledger JSON/Markdown; D = `artifacts/twin3d/preview-render-report.json`, `artifacts/twin3d/performance-profile.json`, `artifacts/twin3d/production-claims-report.json`, `artifacts/twin3d/interactive-twin-verification.json`, `docs/verification/phase-d-findings.json` plus ledger JSON/Markdown. Require current bytes to match only the immutable phase-specific review/manifest/artifact paths; the ledger JSON/Markdown are intentional point-in-time snapshots, so parse and reproduce each raw pair, validate the owning phase state at that commit, and prove every finding/evidence lineage remains present without regression in the final cumulative ledger instead of demanding byte equality across phases. For B, parse the causal manifest only from `$phaseBEvidenceCommit`, never `$phaseBCodeCommit`, require `manifest.reviewedCodeCommit == $phaseBCodeCommit`, and require its pinned `artifactSha256="sha256:68d00121edbf8c4c01cf7cd231cd57c4c8eff25661135494e3c791ca78e562ba"`, `reportSha256="sha256:2a9d9e407dcd1e71977e84acc78b7620e2ed742841699c7cf51b8056bbab6ebb"` and canonical-config `configSha256="sha256:5ff7b883606cf692a0eb1ba7e0a7f5d6b5468c3899cd508194d2e6fca3360415"`. For C, parse the gate manifest from its authenticated evidence blob, require `reviewedCodeCommit == $phaseCCodeCommit`, and reject any gate not explicitly passed;
4. prove base/code/evidence/current ancestry for E1 and A–D, then prove strict `D7 → C11 → D8 → integrated`; inspect commit path sets so D7 materially contains `src/components/Twin3D.jsx` plus its test and no dashboard wiring, C11 materially contains `src/components/operations/OperationsDashboard.jsx`/`src/App.jsx` and no `src/components/twin3d/**`, and D8 materially contains `tests/e2e/interactive-twin.spec.js` plus the D8 quality-gate scripts;
5. require `git status --porcelain=v1 -z --untracked-files=all` empty before creating output, require the output path absent/direct/non-reparse under `tmp/twinops-preview-gate`, require the ignored `tmp/twinops-admin-results` root absent or empty before the remote gate begins, and reject any `.env*` other than tracked `.env.example`, CSV, SQLite/DB or raw-log file in the operational temp root. Unknown ignored residue is reported for explicit scoped cleanup; the verifier never deletes it.

The C manifest is parsed independently with exact root keys `{schemaVersion,plan,verifiedCodeCommit,phaseB,commands,gates}`; require `schemaVersion="phase-c-gate-manifest-v1"`, `plan="C"` and `verifiedCodeCommit=$phaseCCodeCommit`. `phaseB` contains exactly `{phaseBCodeCommit,phaseBEvidenceCommit,bToCContractHandoffCommit}` and must match the authenticated B→C chain. `commands` contains exactly `{fullVitest,productionBuild,playwrightDiscovery,prohibitedOwnershipScan}` as non-empty argv arrays. `gates` contains exactly `{bToCAuthentication,fullVitest,productionBuild,playwrightDiscovery,prohibitedOwnershipScan}`; every value is exactly `{passed,exitCode}`, every `passed` is `true`, and exit codes are respectively `0,0,0,0,1` (the ownership scan's `1` is the explicitly contracted no-match result). Unknown keys, scalar command strings, a different exit or any manifest/worktree blob mismatch block E before remote access.

The canonical output has exactly `schemaVersion="phase-e-preflight-v1"`, `kind="phase-e-integrated-preflight"`, `baseCommit`, `integratedCommit`, `specSha256`, `executionIndexBlob`, `ledgerSha256`, `phaseE1`, `plans`, `phaseBEvidenceCommit`, `phaseBManifestBlob`, `phaseBManifestSha256`, `phaseCEvidenceCommit`, `phaseCGateManifestBlob`, `phaseCGateManifestSha256`, `d7PublicSeamCommit`, `c11DashboardIntegrationCommit`, `d8QualityGateCommit`, `cumulativeFindingIds` and `clean=true`. `phaseE1` and every A–D record under `plans` contain exactly `codeCommit`, `evidenceCommit`, `evidencePaths`, `evidenceBlobSha256ByPath`, `reviewBlob` and `reviewSha256`; the evidence paths equal the literal allowlist above and the digest map has exactly the same keys, derived from the raw evidence-commit blobs. B's and C's external evidence commits are duplicated at the root only as explicit cross-checks and must equal `plans.B.evidenceCommit` and `plans.C.evidenceCommit`. It contains no absolute path, timestamps, environment values, target fingerprint, URL or secret and is written temp+fsync+atomic-replace, then reparsed and byte-verified.

- [ ] **Step 4: Run GREEN and commit the preflight verifier**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
& $python -m pytest services/twinops/tests/test_verify_phase_e_preflight.py -q
if ($LASTEXITCODE -ne 0) { throw 'E2 preflight tests failed' }
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$e2PreflightParent=Get-ExactGitHead
$e2PreflightCommit=Invoke-ExactGitCommit -ExpectedParent $e2PreflightParent -Paths @(
  'scripts/verify_phase_e_preflight.py',
  'services/twinops/tests/test_verify_phase_e_preflight.py'
) -Message 'test: gate phase E integrated ancestry'
```

- [ ] **Step 5: Run the real E2 preflight from a clean tree**

Start a fresh PowerShell process. Values come from the independently reviewed handoffs; the script validates them rather than trusting their labels:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$output=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/e2-preflight-v1.json'))
& $python scripts/verify_phase_e_preflight.py `
  --phase-e1-evidence-commit (Read-Host 'E1 evidence commit') `
  --phase-a-evidence-commit (Read-Host 'Phase A evidence commit') `
  --phase-b-evidence-commit (Read-Host 'Phase B evidence commit') `
  --phase-c-evidence-commit (Read-Host 'Phase C evidence commit') `
  --phase-d-evidence-commit (Read-Host 'Phase D evidence commit') `
  --d7-public-seam-commit (Read-Host 'D7 public seam commit') `
  --c11-dashboard-integration-commit (Read-Host 'C11 dashboard integration commit') `
  --d8-quality-gate-commit (Read-Host 'D8 quality gate commit') `
  --output $output
if ($LASTEXITCODE -ne 0) { throw 'E2 integrated preflight failed' }
```

Expected: one sanitized canonical JSON result and no repository mutation. Do not begin the SQLite journey if any check fails.

- [ ] **Step 6: Write the RED Python journey**

The test creates a temporary SQLite DB and a three-row byte fixture through an explicitly injected **test-only** `HistoryProfileV1`. Canonical synthetic bytes live only once, as `bytes`, in `scripts/support/unified_history_fixture.py`; both the Python integration test and `scripts/e2e_backend.py` import that same generator. The helper creates a process-owned temporary directory, materializes `history.csv` there immediately before use, returns its SHA/path/owned-directory identity, and removes only that revalidated directory during teardown. No `.csv` fixture is tracked and JavaScript never duplicates the bytes. The profile is not registered by `registered_profile`, cannot be selected by `history_admin.py`, and is accepted only by `scripts/e2e_backend.py` when `TWINOPS_E2E_TEST_MODE=1`. The journey stages the prepared batch, stores one synthetic causal assessment satisfying `trainingEnd < windowStart <= windowEnd <= anchor.eventAt`, activates the batch, inserts two live refresh cycles, then asserts:

```python
overview = timeline.overview(query)
assert [segment.source_kind for segment in overview.segments] == [
    "historical_archive", "live_collection"
]
assert any(gap.gap_type == "source_discontinuity" for gap in overview.gaps)
context = timeline.context(TimelineContextQueryV1(
    asset_id="forzy-motor-01", at=selected_at, segment_id=archive_segment
))
assert context.anchor.event_at <= selected_at
assert context.channels.s1.sample_pair_id == context.channels.s2.sample_pair_id
assert context.decision_facts.condition_temporal_scope == "historical"
assert context.decision_facts.collection_state == "historical_context"
```

Also assert the live snapshot still reports current live data, `snapshot.history` has at most 50 frames per sensor, and no historical row appears in `latest_readings_v2`.

- [ ] **Step 7: Run the journey RED test**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$redOutput=@(& $python -m pytest services/twinops/tests/integration/test_unified_history_timeline_sqlite.py::test_unified_history_live_journey_preserves_source_boundary -q 2>&1)
$redExit=$LASTEXITCODE
if ($redExit -ne 1) { throw "integrated journey RED had unexpected exit $redExit" }
$redText=($redOutput -join "`n")
if ($redText -notmatch 'E2_JOURNEY_CONTRACT_MISSING' -or $redText -notmatch '\b1 failed\b' -or $redText -match 'ERROR collecting|ModuleNotFoundError|ImportError|not found') { throw 'integrated journey RED did not fail on its targeted contract assertion' }
```

Expected: exit exactly `1`, the exact named test and `E2_JOURNEY_CONTRACT_MISSING`. The test lazily detects the absent composition/helper inside the test body; collection/import/path failures are rejected.

- [ ] **Step 8: Make `scripts/e2e_backend.py` compose v2 history/timeline**

The script receives `--database-path`, `--use-built-in-test-history` and `--port`; it never accepts an arbitrary production CSV in this path. It rejects the fixture mode unless `TWINOPS_E2E_TEST_MODE=1`, imports the shared Python generator, materializes/revalidates its temporary file, builds the unregistered profile from those bytes, initializes migrations, stages the batch, stores the synthetic causal assessment, activates it and starts the same FastAPI factory used by deployment. The test asserts that the production registry still rejects this profile ID.

- [ ] **Step 9: Replace the stale v1 Playwright spec**

`real-history-live.spec.js` must assert:

```js
await expect(page.getByRole("button", { name: "Voltar para agora" })).toHaveCount(0);
await page.getByRole("button", { name: /candidato histórico/i }).click();
await expect(page.locator("[data-display-mode='historical']")).toBeVisible();
await expect(page.getByText("não representa condição atual", { exact: false })).toBeVisible();
await page.getByRole("button", { name: "Voltar para agora" }).click();
await expect(page.locator("[data-display-mode='now']")).toBeVisible();
```

Intercept browser mutations and fail if any POST occurs. Assert the gap text and no SVG path crosses the gap marker.

In the same task, update only the integrated `playwright.config.js`: remove `channel: "chrome"`; use bundled Chromium from the pinned Playwright package; set the web server command with `--use-built-in-test-history`, database path/port and `TWINOPS_E2E_TEST_MODE=1`; require an explicit `TWINOPS_PYTHON` absolute Python 3.12 executable; set `PYTHONPATH` to the current worktree; and wait on `/api/v2/integration/health`. Do not modify the frontend-only `playwright.twin.config.js` frozen in Task E1. If the pinned Chromium executable is absent, stop and request authorization before `npx.cmd playwright install chromium` rather than silently falling back to system Chrome.

- [ ] **Step 10: Run GREEN**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
$env:TWINOPS_PYTHON=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/integration/test_unified_history_timeline_sqlite.py -q
if ($LASTEXITCODE -ne 0) { throw 'integrated Python journey failed' }
npm.cmd run test:e2e -- tests/e2e/real-history-live.spec.js
if ($LASTEXITCODE -ne 0) { throw 'integrated browser journey failed' }
```

Expected: Python and Playwright pass without network or external writes.

- [ ] **Step 11: Commit**

```powershell
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$e2JourneyParent=Get-ExactGitHead
$e2JourneyCommit=Invoke-ExactGitCommit -ExpectedParent $e2JourneyParent -Paths @(
  'scripts/e2e_backend.py',
  'scripts/support/unified_history_fixture.py',
  'playwright.config.js',
  'services/twinops/tests/integration/test_unified_history_timeline_sqlite.py',
  'tests/e2e/real-history-live.spec.js'
) -Message 'test: prove unified history journey locally'
```

### Task E3: Package migration 003 and timeline runtime without data

**Files:**
- Modify: `vercel.json`
- Modify: `services/twinops/tests/api/test_vercel_entrypoint.py`
- Modify: `requirements.in` only if a new runtime direct dependency is actually imported
- Modify: `requirements.txt` only through the repository's locked generation command

- [ ] **Step 1: Write RED bundle-contract assertions**

Extend `test_vercel_entrypoint.py` to require the exact final modules from A/B — `twinops/ingestion/history_profiles_v1.py`, `twinops/ingestion/historical_import_v1.py`, `twinops/storage/historical_repository_v1.py`, both SQL historical repositories, `twinops/history_admin.py`, `twinops/timeline/**`, timeline contract models and both migration 003 dialect files — plus the decision ruleset modules. Do not assert a synthetic `twinops/history` package that no plan creates. Forbid CSV and source blobs:

```python
assert "003_unified_history_timeline_sqlite.sql" in included
assert "003_unified_history_timeline_postgres.sql" in included
for forbidden in ("History_Forzy.csv", "historical_source_bytes", "data/raw"):
    assert forbidden not in included
```

Also import `api.index` in a subprocess with socket/connect patched to fail and prove cold import performs no migration/import/network.

- [ ] **Step 2: Run RED**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$redOutput=@(& $python -m pytest services/twinops/tests/api/test_vercel_entrypoint.py::test_vercel_bundle_includes_migration_003_without_history_data -q 2>&1)
$redExit=$LASTEXITCODE
if ($redExit -ne 1) { throw "Vercel entrypoint RED had unexpected exit $redExit" }
$redText=($redOutput -join "`n")
if ($redText -notmatch 'E3_MIGRATION_003_BUNDLE_MISSING' -or $redText -notmatch '\b1 failed\b' -or $redText -match 'ERROR collecting|ModuleNotFoundError|ImportError|not found') { throw 'Vercel entrypoint RED did not fail on its targeted includeFiles assertion' }
```

Expected: exit exactly `1`, the exact named test and `E3_MIGRATION_003_BUNDLE_MISSING`; collection/import/path/environment failures do not count.

- [ ] **Step 3: Extend only `includeFiles`**

Keep `outputDirectory: "dist"`, existing source/artifact inclusion and all `excludeFiles`. Add the exact migration 003 paths; do not include `data/**`, local history, reports or tests.

- [ ] **Step 4: Run focused GREEN and build**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/api/test_vercel_entrypoint.py -q
if ($LASTEXITCODE -ne 0) { throw 'Vercel entrypoint tests failed' }
npm.cmd run build:manifest
if ($LASTEXITCODE -ne 0) { throw 'local manifest build failed' }
```

Expected: tests pass; Vite emits a lazy Twin3D chunk; no `dist` artifact is staged.

- [ ] **Step 5: Tool checkpoint**

Run `$vercelCommand=Get-Command vercel -CommandType Application -ErrorAction SilentlyContinue`. If absent, stop and request authorization for:

```powershell
npm.cmd install --global vercel@59.3.0
if ($LASTEXITCODE -ne 0) { throw 'authorized Vercel CLI installation failed' }
```

Do not continue until the user approves and installation succeeds; test the install process exit immediately. Close the install shell; from a fresh PowerShell process re-run `Get-Command`, freeze only the canonical application path and SHA-256, and reject an alias, relative path, reparse point or later executable change. Resolve `curl.exe` through `Get-Command curl.exe -CommandType Application`, require a canonical absolute non-reparse regular file, freeze both the SHA-256 of its canonical path string and its executable bytes, and reject any second `curl` candidate that would precede it in the later controlled child `PATH`. Require exact local Vercel version `59.3.0` and a closed duplicate-key-safe parse/hash of the existing `.vercel/project.json`. At E3, **do not** call `whoami`, `project inspect`, `list`, `api`, or any authenticated/network command: project/org values in the link are untrusted candidates until `initialize` reattests them after preview-access authorization. Never print token or raw IDs and never run `vercel link` automatically.

Run each local help command with stdin closed and capture its exit immediately: `build --help`, `deploy --help`, `env run --help`, `curl --help`, `whoami --help`, `project inspect --help`, `inspect --help`, `list --help`, `logs --help` and `api --help`. Fail closed unless this exact executable documents: preview target; `--prebuilt`; repeatable deploy `--meta KEY=VALUE`; `env run -e preview --`; `curl --deployment`/`--scope`; `whoami --format json`; `project inspect --non-interactive` and its actually documented output mode; `list` or `ls` with `--format json` and filtering by all supplied metadata; typed deployment inspection with `--non-interactive` plus only an output mode explicitly present in audited help; deployment-scoped JSON logs with `fatal`, `--no-branch`, `--since` and `--until`; and authenticated read-only API GET. `--json` is not guessed for `whoami`, project inspection or list/recovery. Tests pin these exact argv/capabilities and reject a flag not present in the captured help. No help command authenticates or validates remote access. A path/hash/version/link/help/curl mismatch requires a new ruling rather than relinking, upgrading or guessing a flag.

- [ ] **Step 6: Defer the preview-env build to the reviewed checkpoint controller**

Do not request preview variables or run `vercel env run`/`vercel build` in Task E3: the versioned controller does not exist until E4 and any E4/E5 commit would invalidate this output. Treat the focused entrypoint test plus `build:manifest` as the local packaging proof. Require `.vercel` to contain only the already-audited `project.json` and optional `README.txt`; if stale output exists, stop and request exact scoped cleanup rather than deleting an unknown tree. Task E7 performs the first authoritative prebuilt build only after E1–E5 are frozen/independently reviewed and preview-env access is explicitly authorized, then audits every runtime module/migration/asset and excludes CSV, `.env*`, tests, `.agents`, source data and secrets.

- [ ] **Step 7: Commit**

```powershell
$e3Paths=@('vercel.json','services/twinops/tests/api/test_vercel_entrypoint.py')
foreach ($optional in @('requirements.in','requirements.txt')) {
  $optionalStatus=@(git status --porcelain=v1 -- $optional)
  if ($LASTEXITCODE -ne 0) { throw "optional-file status failed: $optional" }
  if ($optionalStatus.Count -gt 0) {
    $e3Paths += $optional
  }
}
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$e3Parent=Get-ExactGitHead
$e3Commit=Invoke-ExactGitCommit -ExpectedParent $e3Parent -Paths $e3Paths -Message 'build: package unified timeline runtime'
```

### Task E4: Harden the remote database preflight and add the resumable controller

**Files:**
- Modify: `scripts/check_postgres.py`
- Modify: `services/twinops/tests/test_check_postgres.py`
- Modify: `scripts/verify_env.py`
- Modify: `services/twinops/tests/test_deploy_env.py`
- Create: `scripts/verify_timeline_db.py`
- Create: `services/twinops/tests/test_verify_timeline_db.py`
- Create: `scripts/unified_preview_gate.py`
- Create: `services/twinops/tests/test_unified_preview_gate.py`
- Modify: `docs/deploy/neon.md`

- [ ] **Step 1: Write RED fingerprint and version tests**

Require the checker to receive expected environment/project/branch/database/schema fingerprint and to report only booleans/counts:

```python
with pytest.raises(PostgresCheckError, match="deployment_identity_mismatch"):
    check_postgres(connection, expected=PREVIEW, migrate=False)
assert connection.executed_migration is False
```

Test that runtime health fails closed with `schema_upgrade_required` when migration 003 is absent; cold start must not apply 003. Add a read-only verifier test that composes the production repositories and timeline service against an active fixture, requires exact batch/source/history/assessment manifests, exact raw-row/historical-point/sample/cycle/assessment counts and at least one event candidate whose original anchor and causal episode satisfy `episodeStartedAt <= assessmentWindow.end <= assessmentAt <= anchor.eventAt`. Spy on the connection/repositories and prove the verifier never begins a write transaction. A mismatch exits nonzero and creates no success result.

Add RED tests for guarded migration result JSON and the controller. Cover nonzero child exit, missing result, stale result, path traversal, external path, symlink/junction/reparse point, hard-link where detectable, size `>65536` bytes, invalid UTF-8/BOM, duplicate JSON keys, extra/missing keys, wrong nonce/command/mode/environment/fingerprint/schema, and a file replaced between metadata check/read. Controller tests use injected Git/Vercel/subprocess runners and prove that **every** remote payload child receives a fresh identity prelude; no child starts after a SHA/status/script-blob/CLI/curl/link/project/team/scope/help/protection mismatch. Include Windows paths with spaces, canonical `.cmd` Vercel launch and absolute `.exe` Python launch as argv arrays without shell interpolation. Test process restart by creating a checkpoint, discarding every Python object, then resuming from bytes in a second controller instance. Simulate deploy success before checkpoint completion: recovery must issue one `vercel list|ls ... --format json` filtered by all three intent metadata values, reject unproven flags and zero/multiple/malformed entries without redeploying, and inspect the sole entry non-interactively before adoption.

- [ ] **Step 2: Run RED**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$redOutput=@(& $python -m pytest `
  services/twinops/tests/test_check_postgres.py::test_schema_003_fingerprint_contract_is_required `
  services/twinops/tests/test_deploy_env.py::test_preview_env_contract_is_closed `
  services/twinops/tests/test_verify_timeline_db.py::test_read_only_timeline_verifier_requires_schema_003 `
  services/twinops/tests/test_unified_preview_gate.py::test_remote_child_never_runs_after_identity_mismatch -q 2>&1)
$redExit=$LASTEXITCODE
if ($redExit -ne 1) { throw "remote-gate/controller RED had unexpected exit $redExit" }
$redText=($redOutput -join "`n")
foreach ($marker in @('E4_POSTGRES_003_CONTRACT_MISSING','E4_ENV_CONTRACT_MISSING','E4_TIMELINE_VERIFIER_MISSING','E4_CONTROLLER_IDENTITY_GATE_MISSING')) {
  if ($redText -notmatch [regex]::Escape($marker)) { throw "remote-gate/controller RED omitted $marker" }
}
if ($redText -match 'ERROR collecting|ModuleNotFoundError|ImportError|not found') { throw 'remote-gate/controller RED failed during collection/import/path resolution' }
if ($redText -notmatch '\b4 failed\b') { throw 'remote-gate/controller RED did not fail exactly four targeted tests' }
```

Expected: exit exactly `1` with all four stable markers. Each test lazily probes the missing contract in its own body; collection/import/path/environment failures are rejected.

- [ ] **Step 3: Implement read-only preflight and explicit migration mode**

`--check` requires `--expected-environment`, `--expected-target-fingerprint`, `--expected-schema-version` and a new, direct `--result-json`, then validates SSL, deployment identity, migration versions and catalog. `--migrate` additionally requires `--target-schema-version 003`, `--initial-policy-effective-from <RFC3339 UTC>` and exactly one of `--dry-run|--apply`. Migration remains under advisory transaction lock and rechecks afterward. Tests assert every missing flag fails before connecting/writing and the initial policy retains the operator-supplied effective time on idempotent rerun.

All success is machine-readable and goes through `AdminResultWriterV1`; every `--result-json` is a fresh nonce-qualified direct child of the existing guarded worktree root `tmp/twinops-admin-results`, and stdout/stderr never count as evidence. Migrate dry/apply results have exactly `command="check-postgres"`, `operation="migrate"`, `mode`, `environment`, `targetFingerprint`, `schemaVersion`, `beforeSchemaVersion`, `targetSchemaVersion`, `migrationId`, `migrationSha256`, `initialPolicyId`, `initialPolicySha256`, `initialPolicyEffectiveFrom`, `catalogSha256`, `tableCount`, `indexCount`, `policyCount`, `plannedStatementCount`, `appliedStatementCount`, `writesPerformed` and `verified`. Check results have exactly `command="check-postgres"`, `operation="check"`, `mode="read-only"`, `environment`, `targetFingerprint`, `schemaVersion`, `migrationId`, `migrationSha256`, `initialPolicyId`, `initialPolicySha256`, `initialPolicyEffectiveFrom`, `catalogSha256`, `tableCount`, `indexCount`, `policyCount`, `writesPerformed=0` and `verified=true`. Dry-run has zero applied statements/writes; apply reports actual counts; apply and both post-apply checks must identify schema `003` and match migration, initial-policy and canonical-catalog fields exactly. Failure writes no success JSON.

Implement `scripts/verify_timeline_db.py` as an executable read-only post-activation gate. It requires `--environment preview`, expected target fingerprint/schema `003`, asset ID, batch ID, source/history/assessment manifest hashes, exact raw-row/historical-point/sample/cycle/assessment counts and `--result-json`. It accepts neither `--dry-run` nor `--apply`, uses the production repository/service composition, and writes through `AdminResultWriterV1` only after all assertions pass. Its flat result contains exactly `command="verify-timeline-db"`, `environment`, `targetFingerprint`, `schemaVersion`, `assetId`, `activeBatchId`, `sourceSha256`, `manifestSha256`, `assessmentManifestSha256`, `rawRowCount`, `historicalPointCount`, `sampleCount`, `operatingCycleCount`, `assessmentCount`, `eventCandidateCount`, `validAnchorEpisodeCount` and `verified=true`. For `forzy-history-2026-05-19-v1`, the independent count invariants are `rawRowCount=7183` and `sampleCount=historicalPointCount=14366`; raw rows must never be reported as historical points. It never exposes rows, timestamps, DSN, host or paths.

- [ ] **Step 4: Implement the versioned sanitized checkpoint controller**

`scripts/unified_preview_gate.py` is the only executable entrypoint used after an access/write approval. It exposes `initialize`, `migration-dry-run`, `migration-apply`, `stage-dry-run`, `stage-apply`, `assess-dry-run`, `assess-apply`, `activation-dry-run`, `activation-apply`, `build-preview`, `deploy-preview`, `attest-protection`, `smoke-preview`, `browser-preview`, `logs-preview`, `human-usability-session`, `export-usability-harness`, `export-database-report`, `export-preview-report` and `verify-evidence-scope`. Every subcommand opens the checkpoint from disk, validates it, reasserts all frozen identity, performs at most its declared transition, and atomically replaces the checkpoint. There is no importable mutable singleton and no PowerShell dot-sourcing. `attest-protection` is a typed read-only transition over the reviewed verifier and exact bound deployment; it changes only the latest protection-result digest. `human-usability-session` is a browser-only, read-only transition that launches the reviewed facilitator harness for exactly one opaque participant/role and four frozen fixtures after a fresh protection attestation and per-child bypass authorization; `export-usability-harness` reconnects nowhere and combines the two digest-bound sanitized session manifests. `export-preview-report` has a finalization mode whose only additional inputs are the fixed repository-relative AC-15, usability result/harness/assessment and sanitized final log-summary paths; it invokes their already-reviewed validators, requires the log summary to cover through the latest successful smoke, binds their SHA-256 digests and the latest smoke/protection-result digests, and refuses to alter remote state.

The checkpoint has `schemaVersion="preview-gate-checkpoint-v1"` and exact top-level keys `schemaVersion`, `runId`, `codeCommit`, `e2PreflightSha256`, `operationalReviewSha256`, `phaseBEvidenceCommit`, `phaseBManifestSha256`, `scriptBlobs`, `vercel`, `curl`, `link`, `protection`, `previewEnvAccessApprovalRefSha256`, `targetFingerprintSha256`, `policy`, `database`, `build`, `deployment`, `smoke`, `human`, `approvals` and `state`. `vercel` binds only canonical CLI/help plus hashed authenticated user/project/org identities. `curl` contains exactly `canonicalPathSha256`, `executableSha256`, `fileName="curl.exe"` and `resolver="where.exe"`; the raw absolute path is re-resolved in each fresh process but never persisted. `protection` binds the latest typed result digest, method/scope, exception-host hashes and `previewUrlExcepted=false`; `human` binds only the two expected role classes, opaque-session-ID hashes and digest-bound sanitized harness session/result paths. It stores only hashes, counts, bounded UTC gate intervals, stable IDs already allowed in sanitized reports and approval-reference hashes. It never stores raw target fingerprint, CSV path, DSN, host/user/email, env name/value pairs, participant answers, bypass secret, token, raw stdout/stderr/logs or source rows. State transitions are closed and monotonic; replay is accepted only for explicitly idempotent revalidation and must produce identical identities/counts with zero writes.

Before **each remote payload child** (protection read, dry/apply/check/revalidation/build/deploy/list/inspect/smoke/browser/human-session/log), not merely once per subcommand, the controller executes one non-recursive identity prelude: local Git/status/blob/CLI/link/curl checks; frozen-CLI `whoami --format json --scope 9luis7s-projects --no-color` and `project inspect forzy-twinops --non-interactive --scope 9luis7s-projects --no-color` read-only children with `CI=1`, closed stdin, bounded output/time and no token on argv; `project inspect` uses an additional machine-readable format flag only if that exact flag/value was captured from the pinned help, otherwise a closed parser for the audited non-interactive output; then the local checks once more and comparison of both closed typed results immediately before the payload child. Every Vercel/Vercel-curl child receives `cwd` equal to the canonical guarded worktree root containing the frozen `.vercel/project.json`; `--cwd`, parent/main checkout execution and link discovery from another directory are forbidden and tested. `whoami`/`project inspect` are the identity prelude, not payload children that recursively invoke another prelude. Missing login, SAML reauthentication, inaccessible team/project, prompt/HTML/prose output, wrong scope/role or nonzero exit fails closed without launching the payload. No authenticated identity request occurs before `initialize` has validated the preview-access approval. No other network child is exempt. The bound checks are:

- `git rev-parse HEAD`, ancestry to `codeCommit`, and byte equality of all executable/build-input blobs to `codeCommit`;
- `git status --porcelain=v1 -z --untracked-files=all` plus explicit enumeration of ignored operational roots, rejecting every tracked mutation and every untracked/ignored path except exact `e2-preflight-v1.json`, `phase-e-operational-findings.json`, the current checkpoint, and nonce-qualified direct children of `tmp/twinops-admin-results` whose relative names/digests are already bound in the checkpoint (plus the one absent destination allocated for the current child); state `browser_verified` and later additionally permit only the fourteen recorded screenshot files. `.vercel/project.json` and `.vercel/README.txt` are frozen linked inputs, while `.vercel/output/**`, `.vercel/python/**` and `.vercel/static-build/**` are additionally allowed only during a build/deploy audit. Declared uncommitted E7/E8/E9 evidence destinations are permitted only for the exact state/subcommand that creates or consumes them; any other `.vercel`, screenshot, admin-result or evidence child blocks for investigation/authorized cleanup;
- exact blobs for the controller, E2 preflight verifier, `verify_unified_acceptance.py`, `check_postgres.py`, `verify_env.py`, `history_admin.py`, `verify_timeline_db.py`, `verify_deployment.py`, `verify_vercel_logs.py`, `verify_vercel_protection.py`, `verify_usability_result.py`, `verify_e_review_lineage.py`, `run_ac15_gate.py`, the browser-only usability harness/fixture manifest, the protected-preview Playwright fixture, `playwright.config.js`, `vercel.json`, `api/index.py`, `package.json` and the lockfile;
- canonical Vercel application path, executable SHA-256, exact version `59.3.0`, audited help-capability digest, strict typed identity results (`whoami` duplicate-key JSON plus project inspection parsed only in its audited output mode), `.vercel/project.json` blob/hash, project `forzy-twinops`, team/scope `9luis7s-projects`, and exact hashed user/project/org identities.
- canonical `curl.exe` path-string digest and executable SHA-256. For every `vercel curl` payload, construct a minimal child environment whose `PATH` resolves `curl.exe` exactly once to that frozen file (plus only the audited Vercel/Node runtime directories), run `where.exe curl` in that exact environment, require the sole canonical result and rehash it immediately before and after the protected requests. A fake/earlier curl, duplicate resolution, path/hash drift or an ambient PATH segment blocks before network; injected-runner tests prove the Vercel child receives this exact environment and cannot resolve another curl.

The result reader resolves the worktree/result root once, requires a nonce-qualified direct regular-file child, uses `lstat`/reparse checks before and after an exclusive bounded read, rejects links and size above 64 KiB, decodes strict UTF-8 without BOM, rejects duplicate keys via `object_pairs_hook`, enforces closed command-specific key sets and freshness, and rechecks file identity/size/mtime after read. It deletes no caller path. Fixed tracked AC-15/usability evidence is read only through its dedicated reviewed validator, never through this admin-result reader. The controller captures child output only in bounded memory, checks the native exit before parsing, emits no secret-bearing output, and persists only the guarded typed result/checkpoint. Tests simulate process death after a remote apply but before checkpoint update; a rerun must safely re-read remote state and either prove the idempotent outcome or stop, never infer failure/success from missing in-memory state.

- [ ] **Step 5: Run GREEN**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/test_check_postgres.py services/twinops/tests/test_deploy_env.py -q
if ($LASTEXITCODE -ne 0) { throw 'Postgres/env gate tests failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/test_verify_timeline_db.py -q
if ($LASTEXITCODE -ne 0) { throw 'timeline DB verifier tests failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/test_unified_preview_gate.py -q
if ($LASTEXITCODE -ne 0) { throw 'preview controller tests failed' }
```

- [ ] **Step 6: Update runbook with the distinct database operations**

Document sanitized controller examples for: preview-env read access; migration 003; `stage-history`; `build-assessments`; and `activate-history`. State that migration, stage, assessment materialization and activation each require their own explicit approval, and every resume begins from a fresh process/checkpoint. Document that `vercel env run` is in-memory only and every `env pull`/`pull` path is forbidden.

- [ ] **Step 7: Commit**

```powershell
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$e4Parent=Get-ExactGitHead
$e4Commit=Invoke-ExactGitCommit -ExpectedParent $e4Parent -Paths @(
  'scripts/check_postgres.py',
  'services/twinops/tests/test_check_postgres.py',
  'scripts/verify_env.py',
  'services/twinops/tests/test_deploy_env.py',
  'scripts/verify_timeline_db.py',
  'services/twinops/tests/test_verify_timeline_db.py',
  'scripts/unified_preview_gate.py',
  'services/twinops/tests/test_unified_preview_gate.py',
  'docs/deploy/neon.md'
) -Message 'chore: gate unified timeline database changes'
```

### Task E5: Extend protected-preview verification and freeze E1–E5

**Files:**
- Modify: `scripts/verify_deployment.py`
- Create: `scripts/verify_vercel_logs.py`
- Create: `scripts/verify_vercel_protection.py`
- Modify: `services/twinops/tests/test_verify_deployment.py`
- Create: `services/twinops/tests/test_verify_vercel_logs.py`
- Create: `services/twinops/tests/test_verify_vercel_protection.py`
- Modify: `tests/e2e/deployed-real.spec.js`
- Modify: `tests/e2e/operational-scenarios.spec.js` only to import the shared reviewed route-fixture module
- Modify: `tests/e2e/operational-accessibility.spec.js` and `tests/e2e/interactive-twin.spec.js` only to import the protected-preview fixture
- Create: `tests/e2e/support/protected-preview-fixture.js`
- Create: `tests/e2e/support/operational-usability-routes-v1.js`
- Create: `scripts/run-operational-usability-harness.mjs`
- Create: `tests/e2e/operational-usability-harness.test.js`
- Modify: `playwright.config.js`
- Create: `tests/e2e/deployed-protection-config.test.js`
- Create: `scripts/verify_usability_result.py`
- Create: `services/twinops/tests/test_verify_usability_result.py`
- Create: `scripts/run_ac15_gate.py`
- Create: `services/twinops/tests/test_run_ac15_gate.py`
- Create: `scripts/verify_e_review_lineage.py`
- Create: `services/twinops/tests/test_verify_e_review_lineage.py`
- Modify: `scripts/verify_unified_acceptance.py`
- Modify: `services/twinops/tests/test_verify_unified_acceptance.py`
- Modify: `scripts/unified_preview_gate.py`
- Modify: `services/twinops/tests/test_unified_preview_gate.py`
- Create during independent review only: `tmp/twinops-preview-gate/phase-e-operational-findings.json` (sanitized, ignored)

- [ ] **Step 1: Write RED probe tests**

Expected GET sequence adds timeline and an exact historical context. For a deployed run, `verify_deployment.py` requires the canonical credential-free `--url`, exact `--deployment-id dpl_...`, absolute frozen `--vercel-executable`, absolute frozen `--curl-executable` plus `--expected-curl-sha256`, `--project forzy-twinops`, `--scope 9luis7s-projects`, a fresh guarded read-only `verify-timeline-db` result supplied by the controller, and guarded `--result-json`. It requires the controller-supplied minimal child environment to resolve exactly that curl and rehashes it before/after the request set. Direct `httpx`, `requests`, ambient/system curl resolution, raw deployment URL fetches and manually supplied protection headers are forbidden in deployed mode. The injected runner must invoke the official protected-preview path once per request:

```python
assert calls == [
    ("GET", "/api/v2/integration/health"),
    ("GET", "/api/v2/assets/forzy-motor-01/snapshot"),
    ("GET", "/api/v2/assets/forzy-motor-01/timeline"),
    ("GET", "/api/v2/assets/forzy-motor-01/timeline/context?pointId=00000000-0000-5000-8000-000000000011"),
    ("GET", "/models/conjunto-motor-bomba.manifest.json"),
    ("GET", "/models/conjunto-motor-bomba.glb"),
    ("GET", "/models/conjunto-motor-bomba-preview.png"),
]
assert not any(method == "POST" for method, _ in calls)
```

For every tuple above, assert the native argv is exactly the frozen Vercel executable followed by `curl`, the path, `--deployment <canonical-url>`, `--scope 9luis7s-projects`, `--no-color`, and native-curl flags `--silent --show-error --fail-with-body --request GET`. The child environment explicitly removes `VERCEL_AUTOMATION_BYPASS_SECRET`; `vercel curl` obtains its Deployment Protection bypass through the authenticated Vercel CLI, and the script accepts neither `--protection-bypass` nor a secret. The wrapper checks the Vercel/curl exit before parsing and bounds every body in memory. JSON endpoints use strict UTF-8/duplicate-key/closed-shape parsing; GLB/PNG responses stay bounded bytes and are checked only by media signature, exact length and SHA-256. No response body is persisted.

The verifier first validates the overview and deterministically chooses an original anchor from `eventCandidates[0].anchorPointId`, or accepts exactly one explicit selector form: `--context-point-id`, or `--context-at` together with `--context-segment-id`. Missing/ambiguous selectors fail before the context request. Require explicit expected values for the exact active batch, source SHA, history manifest, assessment manifest, artifact/report/config hashes, `rawRowCount=7183`, `historicalPointCount=14366`, `sampleCount=14366`, `operatingCycleCount=204`, exact assessment/candidate/event-candidate/valid-anchor-episode counts, schema `003`, and immutable model manifest/GLB/PNG hashes. Any mismatch fails even if HTTP is 200. This is the smoke's complete batch/manifests/counts contract; `>=1` is insufficient.

All new Python tests catch absent modules/interfaces inside their targeted test bodies and use these stable initial-failure markers: `E5_DEPLOYMENT_CONTRACT_MISSING`, `E5_LOG_CONTRACT_MISSING`, `E5_PROTECTION_CONTRACT_MISSING`, `E5_USABILITY_CONTRACT_MISSING`, `E5_AC15_CONTRACT_MISSING`, `E5_REVIEW_LINEAGE_CONTRACT_MISSING`, `E5_LEDGER_LINEAGE_INGEST_MISSING`, `E5_FINAL_LOG_REVALIDATION_MISSING` and `E5_FROZEN_CURL_RESOLUTION_MISSING`. The two frontend contract tests use `E5_PROTECTED_FIXTURE_CONTRACT_MISSING` and `E5_USABILITY_HARNESS_CONTRACT_MISSING`. They must not rely on collection/import/path/environment failure as RED.

- [ ] **Step 2: Run RED, then implement the protected typed report**

Run the exact mixed RED before implementation:

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$pythonRedOutput=@(& $python -m pytest `
  services/twinops/tests/test_verify_deployment.py::test_deployed_report_contract_is_closed `
  services/twinops/tests/test_verify_vercel_logs.py::test_log_contract_is_bounded_and_sanitized `
  services/twinops/tests/test_verify_vercel_protection.py::test_protection_contract_is_positive_and_typed `
  services/twinops/tests/test_verify_usability_result.py::test_usability_contract_is_fail_closed `
  services/twinops/tests/test_run_ac15_gate.py::test_ac15_runner_is_isolated `
  services/twinops/tests/test_verify_e_review_lineage.py::test_operational_findings_cannot_disappear `
  services/twinops/tests/test_verify_unified_acceptance.py::test_authenticated_external_review_lineage_is_ingested_without_erasure `
  services/twinops/tests/test_unified_preview_gate.py::test_final_logs_cover_last_preview_access `
  services/twinops/tests/test_unified_preview_gate.py::test_fake_curl_earlier_on_path_blocks_before_network -q 2>&1)
$pythonRedExit=$LASTEXITCODE
if ($pythonRedExit -ne 1) { throw "E5 Python RED had unexpected exit $pythonRedExit" }
$pythonRedText=($pythonRedOutput -join "`n")
foreach ($marker in @('E5_DEPLOYMENT_CONTRACT_MISSING','E5_LOG_CONTRACT_MISSING','E5_PROTECTION_CONTRACT_MISSING','E5_USABILITY_CONTRACT_MISSING','E5_AC15_CONTRACT_MISSING','E5_REVIEW_LINEAGE_CONTRACT_MISSING','E5_LEDGER_LINEAGE_INGEST_MISSING','E5_FINAL_LOG_REVALIDATION_MISSING','E5_FROZEN_CURL_RESOLUTION_MISSING')) {
  if ($pythonRedText -notmatch [regex]::Escape($marker)) { throw "E5 Python RED omitted $marker" }
}
if ($pythonRedText -match 'ERROR collecting|ModuleNotFoundError|ImportError|not found') { throw 'E5 Python RED failed during collection/import/path resolution' }
if ($pythonRedText -notmatch '\b9 failed\b') { throw 'E5 Python RED did not fail exactly nine targeted tests' }
$frontendRedOutput=@(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" tests/e2e/deployed-protection-config.test.js tests/e2e/operational-usability-harness.test.js 2>&1)
$frontendRedExit=$LASTEXITCODE
if ($frontendRedExit -ne 1) { throw "E5 frontend RED had unexpected exit $frontendRedExit" }
$frontendRedText=($frontendRedOutput -join "`n")
foreach ($marker in @('E5_PROTECTED_FIXTURE_CONTRACT_MISSING','E5_USABILITY_HARNESS_CONTRACT_MISSING')) {
  if ($frontendRedText -notmatch [regex]::Escape($marker)) { throw "E5 frontend RED omitted $marker" }
}
if ($frontendRedText -match 'No test files found|ERR_MODULE_NOT_FOUND|Cannot find module') { throw 'E5 frontend RED failed during discovery/import/path resolution' }
if ($frontendRedText -notmatch '\b2 failed\b') { throw 'E5 frontend RED did not fail exactly two targeted tests' }
```

Expected: both commands exit exactly `1` and emit every listed contract marker; any collection, import, test-discovery, path or environment failure is rejected.

Add `transport="vercel-curl"`, `deployment_url`, `deployment_id`, `database_verification_sha256`, `timeline`, `history_batch`, `context`, `causality`, `counts`, `twin_interaction_assets` and `refresh="not_requested"` to `DeploymentReport`. Each nested value is a closed typed record containing only sanitized IDs/hashes/counts/booleans; it includes every expected-versus-observed identity above. The controller/result reader validates the fresh DB result first; the HTTP probe must corroborate its exact `activeBatchId` and observable timeline/context counts, while the report binds all source/history/assessment manifests and raw/history/sample/cycle/assessment/candidate/anchor counts to that same fresh read-only DB verification. Validate URL/ID/project/scope and all expected hashes/counts before network, use temp+fsync+atomic-replace for the result, and keep failure output to stage/code only.

Write a second RED for `verify_vercel_logs.py`. Its injected subprocess runner receives an absolute frozen Vercel executable plus exact fixed arguments `logs --deployment <dpl_...> --environment preview --level error --level warning --level fatal --limit 100 --json --since <window-start-rfc3339> --until <window-end-rfc3339> --no-branch --scope 9luis7s-projects --project forzy-twinops --no-color`, captures stdout/stderr in bounded memory, and returns exit status. Bounds come from the checkpoint, are ordered and each window spans at most 30 minutes; a result at the limit fails as possibly truncated. The initial call covers deploy through the first browser gate. `logs-preview --revalidate` later partitions deploy intent through the latest preview access/final smoke into a deterministic sequence of contiguous nonoverlapping windows of at most 30 minutes, queries every window and atomically replaces the same sanitized summary only if all windows pass. Prove no gap/overlap, final bound before the latest access, nonzero exit, oversized/malformed JSON Lines, any record outside its window and exactly 100 records all fail closed. The canonical summary has exactly `schemaVersion="vercel-log-summary-v1"`, `deploymentId`, `environment="preview"`, `windowStart`, `windowEnd`, `windows`, `totalCount`, `countsByLevel`, `statusClass`, `source="vercel-logs"` and `verified=true`; each window has exactly `start`, `end`, `recordCount`, `countsByLevel` and a digest of that canonical sanitized aggregate (never raw messages), while `countsByLevel` has exactly `error|warning|fatal`. It never emits raw `message`, request path, headers, body, query, env-like values or an intermediate raw-log file.

Write a third RED for `verify_vercel_protection.py`. Through the frozen `vercel api` command it permits only authenticated GETs for the exact project/team and, once known, deployment/alias state; stdin is closed, output is bounded strict JSON, and no token appears on argv. Its closed `vercel-protection-state-v1` result contains only project/org hashes, `environment="preview"`, normalized `protectionScope`, sorted nonempty `protectionMethods`, `automationBypassConfigured`, sorted exception-host SHA-256 values, nullable deployment ID/URL-host hash, `previewUrlExcepted=false`, `checkedBy="vercel-api-read-only"` and `verified=true`. Unknown/missing API fields, disabled/none scope, a scope not covering preview, no active protection method, a mismatched project/team/deployment, or the exact preview hostname in Deployment Protection Exceptions fails before a success result. Fixtures cover Vercel Authentication, Password and Trusted-IP methods without assuming all are enabled; no test accepts an HTTP challenge as a substitute for positive typed state.

- [ ] **Step 3: Strengthen deployed Playwright**

Keep the browser mutation firewall. Add assertions for decision summary, active historical batch, gap, `data-display-mode`, exact group selection and model-ready marker. Do not rely on current collection window.

`playwright.config.js` must never set global `extraHTTPHeaders`. When and only when a canonical `DEPLOYMENT_URL` is supplied, every remote spec imports `protected-preview-fixture.js`; before navigation, that fixture installs routing bound to the exact deployment origin. It permits only `GET|HEAD` to `/`, reviewed Vite `/assets/**`, the frozen API/model paths and the one validated context query; it aborts every other method/path, every websocket/beacon/service-worker request and **every other origin before headers are constructed**. Only for an allowed same-origin request does it merge `x-vercel-protection-bypass: <in-memory secret>` and `x-vercel-set-bypass-cookie: true`. Local loopback rejects/clears deployment/secret values and installs no bypass route. Tests inject cross-origin image/script/fetch redirects and disallowed same-origin paths/methods, assert zero continuation and zero header visibility, and prove reporters/traces/errors cannot observe the secret. Never append it to URL/query, serialize it, read an env file, disable protection or create an exception.

Create `operational-usability-routes-v1.js` by moving, not rewriting, the four C-authored route fixtures `normal_fresh`, `persistent_candidate`, `gap` and `acquisition_failure` from the reviewed C scenario spec. A canonical manifest binds the Phase-C source blob plus each closed fixture digest; equivalence tests run the old/new builders against the same requests and require byte-identical responses. `operational-scenarios.spec.js` imports this test-only module, while production source/bundle scanners forbid it. `run-operational-usability-harness.mjs` is a facilitator-controlled browser-only harness: it loads real reviewed preview assets through the protected fixture, fulfills only the exact same-origin API GET routes from one selected C fixture, blocks all other origins and every mutation, starts a fresh context in `now` for each scenario and never imports/injects a runtime mock. Through the controller and `AdminResultWriterV1`, each child writes one fresh nonce-qualified direct result under `tmp/twinops-admin-results`; the closed result is a sanitized `operational-triage-usability-harness-v1` session manifest with code SHA, output-manifest digest, deployment ID/URL hash, harness/fixture-manifest digests and the four fixture digests—never participant answers, secret, response bodies or PII.

In the same RED/GREEN cycle, implement `verify_usability_result.py` before code freeze. It strictly parses `operational-triage-usability-v1-results.json` plus the harness manifest with duplicate-key rejection and closed keys; requires two actual role classes, all eight role×scenario observations, exact code/output/deployment/harness/four-fixture binding, computed thresholds, explicit unsafe-inference answers and no personal-data fields. Its `assess` command atomically writes closed `operational-triage-usability-assessment-v1` JSON with per-criterion `passed|failed|blocked`; malformed/fabricated/misbound evidence exits nonzero with no assessment or ledger mutation. It renders Markdown deterministically and exposes a guarded `record-nonpass` mutation that may set only AC-18/AC-28 from a valid non-PASS assessment. Task E8 uses this already-reviewed executable; no validator code is introduced after deployment.

Also implement `run_ac15_gate.py` before code freeze. Its tests require an absolute Python 3.12 executable and a fresh guarded result path, construct a closed child environment from an allowlist, remove `DEPLOYMENT_URL`, `TWINOPS_DEPLOYMENT_ID`, `VERCEL_AUTOMATION_BYPASS_SECRET`, DSN/database/upstream/token/proxy variables, force fixed loopback frontend/backend origins plus `TWINOPS_E2E_TEST_MODE=1` and worktree `PYTHONPATH`, and execute exactly both C-authored `@ac15-first-fold` cases with bundled Chromium. It verifies executable/test/config blobs against the reviewed code SHA, captures bounded structured reporter output, and atomically writes the closed `ac15-first-fold-result-v1`; it never launches against preview or inherits a system browser.

Implement `verify_e_review_lineage.py` before code freeze. `verify` accepts only the ignored operational review, the tracked final E review, sanitized checkpoint, exact expected E code SHA and one fixed repository-relative output. It parses the checkpoint and both `finding-review-v1` reports with duplicate-key/closed-key validation; requires checkpoint `codeCommit` and `operationalReviewSha256` to match the arguments/raw bytes; requires both reports use `plan="E"`, both `reviewedSha` equal the exact operational code SHA, zero Critical/Important and no unaccepted Minor; and requires every operational finding ID to appear in the final review with identical severity/title and a legal non-regressing status/resolution lineage. It rejects a missing ID even when both aggregate verdicts are green. The atomic canonical `phase-e-review-lineage-v1` output contains exactly `schemaVersion`, `verifiedCodeCommit`, `operationalReviewSha256`, `finalReviewSha256`, `findingLineage` (closed ID/severity/title/status tuples) and `verified=true`. This binds an empty operational finding set by digest too. Tests cover omission, ID reuse, severity/title drift, status regression, checkpoint/SHA/digest mismatch and a valid open→fixed or Minor→accepted transition with explicit user evidence.

In the same E5 code commit, extend `verify_unified_acceptance.py` with `ingest-authenticated-review-lineage`. It accepts only plan E's strict final review, the raw ignored operational review, sanitized checkpoint and canonical lineage result; rehashes all three files; requires checkpoint/code/digests and every lineage tuple to agree; then performs one atomic ledger/Markdown mutation. Unlike ordinary `ingest-review`, it may import an externally reviewed finding first observed in the authenticated operational report already in a closed `fixed|accepted` state: it records the operational `reviewedSha` as the conservative durable `introducedSha`, preserves the report's exact `resolvedSha`, ID/severity/title/status/evidence, and permits `accepted` only for a Minor with explicit user-acceptance evidence. Existing ledger findings must follow the normal immutable lineage rules; nothing may be overwritten or erased. It sets `plans.E.verifiedCodeCommit` and the `[critical,important,minor]` verdict only from the final review's exact code SHA, never from the evidence/lineage commit. Tests prove a green aggregate with an omitted operational ID is rejected, a hand-edited lineage result cannot pass, imported closed findings remain cumulative, E1 findings survive, code/evidence SHAs cannot be confused and Markdown remains byte-reproducible.

- [ ] **Step 4: Run GREEN locally with MockTransport/route fixtures**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/test_verify_deployment.py -q
if ($LASTEXITCODE -ne 0) { throw 'deployment verifier tests failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/test_verify_vercel_logs.py -q
if ($LASTEXITCODE -ne 0) { throw 'Vercel log verifier tests failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/test_verify_vercel_protection.py -q
if ($LASTEXITCODE -ne 0) { throw 'Vercel protection verifier tests failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/test_verify_usability_result.py -q
if ($LASTEXITCODE -ne 0) { throw 'usability validator tests failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/test_run_ac15_gate.py -q
if ($LASTEXITCODE -ne 0) { throw 'AC-15 runner tests failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/test_verify_e_review_lineage.py services/twinops/tests/test_unified_preview_gate.py -q
if ($LASTEXITCODE -ne 0) { throw 'review-lineage/final-log/curl controller tests failed' }
& "..\..\services\twinops\.venv\Scripts\python.exe" -m pytest services/twinops/tests/test_verify_unified_acceptance.py -q
if ($LASTEXITCODE -ne 0) { throw 'authenticated ledger-lineage ingestion tests failed' }
npm.cmd run test:e2e -- tests/e2e/deployed-real.spec.js --list
if ($LASTEXITCODE -ne 0) { throw 'deployed E2E enumeration failed' }
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" tests/e2e/deployed-protection-config.test.js
if ($LASTEXITCODE -ne 0) { throw 'protected preview fixture tests failed' }
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" tests/e2e/operational-usability-harness.test.js
if ($LASTEXITCODE -ne 0) { throw 'usability harness tests failed' }
```

- [ ] **Step 5: Commit**

```powershell
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$e5Parent=Get-ExactGitHead
$e5Commit=Invoke-ExactGitCommit -ExpectedParent $e5Parent -Paths @(
  'scripts/verify_deployment.py','scripts/verify_vercel_logs.py','scripts/verify_vercel_protection.py',
  'services/twinops/tests/test_verify_deployment.py','services/twinops/tests/test_verify_vercel_logs.py','services/twinops/tests/test_verify_vercel_protection.py',
  'tests/e2e/deployed-real.spec.js','tests/e2e/operational-scenarios.spec.js','tests/e2e/operational-accessibility.spec.js','tests/e2e/interactive-twin.spec.js',
  'tests/e2e/support/protected-preview-fixture.js','tests/e2e/support/operational-usability-routes-v1.js',
  'scripts/run-operational-usability-harness.mjs','tests/e2e/operational-usability-harness.test.js','playwright.config.js','tests/e2e/deployed-protection-config.test.js',
  'scripts/verify_usability_result.py','services/twinops/tests/test_verify_usability_result.py','scripts/run_ac15_gate.py','services/twinops/tests/test_run_ac15_gate.py',
  'scripts/verify_e_review_lineage.py','services/twinops/tests/test_verify_e_review_lineage.py','scripts/verify_unified_acceptance.py','services/twinops/tests/test_verify_unified_acceptance.py',
  'scripts/unified_preview_gate.py','services/twinops/tests/test_unified_preview_gate.py'
) -Message 'test: verify unified timeline deployments read only'
```

- [ ] **Step 6: Freeze and fully verify the exact E1–E5 code commit**

Start clean, run the entire local matrix, then freeze the implementation SHA. The ignored E2 result is allowed only at its exact path; no other tracked/untracked operational file is allowed.

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
& $python -m pytest services/twinops/tests -q
if ($LASTEXITCODE -ne 0) { throw 'Python matrix failed' }
npm.cmd run test:run -- --exclude "**/.pytest_cache/**"
if ($LASTEXITCODE -ne 0) { throw 'frontend matrix failed' }
npm.cmd run test:e2e -- tests/e2e/real-history-live.spec.js
if ($LASTEXITCODE -ne 0) { throw 'integrated local browser journey failed' }
npm.cmd run build:manifest
if ($LASTEXITCODE -ne 0) { throw 'manifest build failed' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'diff check failed' }
$pending=@(git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $pending.Count -ne 0) { throw 'E1-E5 code commit is not clean' }
$operationalRoot=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate'))
$allowedOperational=@([IO.Path]::GetFullPath((Join-Path $operationalRoot 'e2-preflight-v1.json')))
$actualOperational=@(Get-ChildItem -LiteralPath $operationalRoot -Force -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
if (Compare-Object $allowedOperational $actualOperational) { throw 'ignored operational scope is not the exact E2 preflight allowlist' }
$vercelChildren=@(Get-ChildItem -LiteralPath (Join-Path $PWD '.vercel') -Force -ErrorAction SilentlyContinue | ForEach-Object { $_.Name } | Sort-Object)
if ('project.json' -notin $vercelChildren -or @($vercelChildren | Where-Object { $_ -notin @('project.json','README.txt') }).Count -ne 0) { throw 'disposable build output or unexpected linked-project child remains' }
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$phaseEOperationalCodeCommit=Get-ExactGitHead
```

- [ ] **Step 7: Independently review E1–E5 before any remote write**

An independent reviewer receives `$phaseEOperationalCodeCommit`, the E2 preflight result and all A–D handoffs. It reviews Tasks E1–E5, the controller state machine, result containment, CLI/link/curl pinning, protected-preview transport, absence of persistent env, and every cumulative E1 finding. It writes `tmp/twinops-preview-gate/phase-e-operational-findings.json` in strict `finding-review-v1` shape with `plan="E"`, `reviewedSha=$phaseEOperationalCodeCommit`, zero Critical/Important, and no unaccepted Minor. The file is ignored operational input; its SHA-256 is bound into the checkpoint. Every finding ID/severity/title/status must be carried into the final tracked E review and is later proven by the reviewed lineage validator before ledger ingestion; a merely green aggregate verdict cannot erase it. Any code/config/script finding requires fix, a new commit, full rerun and a new independent review. Task E6 is blocked until this review is clean.

### Task E6: Run the authorized preview database gates through resumable checkpoints

**Files:**
- Create during execution: `tmp/twinops-preview-gate/checkpoint-v1.json` plus nonce-qualified direct result children under `tmp/twinops-admin-results/` (sanitized, ignored, guarded by `AdminResultWriterV1`)
- Create during execution: `docs/verification/unified-twin-preview-database-report.md` (sanitized, tracked)
- Reuse without modification: `tmp/twinops-preview-gate/e2-preflight-v1.json`
- Reuse from its evidence commit: `docs/verification/phase-b-local-causal-manifest.json`
- Never create/stage: `.env.local`, any `.env*` export, CSV copies, DB dumps, raw command/log output

**Precondition:** E1–E5 are committed at the clean `$phaseEOperationalCodeCommit`; `tmp/twinops-preview-gate/phase-e-operational-findings.json` independently reviews that exact SHA with zero Critical/Important; the E2 result binds the separately recorded A–D evidence commits, including `$phaseBEvidenceCommit`. No command below authorizes production.

- [ ] **Step 1: Obtain preview-environment access authorization and initialize a restart-safe checkpoint**

Before any authenticated Vercel request, `vercel env run` or preview build in the operational gate, present the exact code SHA, E2 result digest, operational-review digest, locally frozen CLI path/hash/version/help and the duplicate-key-safe `.vercel/project.json` candidate hash. Project/team/scope values from that local link are explicitly **untrusted candidates**, not an authenticated audit. Request explicit authorization for **read/in-memory access to the preview environment plus the bounded read-only identity and Deployment Protection attestations needed to establish that access**. This authorization does not authorize migration, stage, assessment, activation or deploy. After approval, start a fresh PowerShell process:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
$vercelExe=[IO.Path]::GetFullPath((Get-Command vercel -CommandType Application -ErrorAction Stop).Source)
& $python scripts/unified_preview_gate.py initialize `
  --checkpoint $checkpoint `
  --e2-preflight tmp/twinops-preview-gate/e2-preflight-v1.json `
  --operational-review tmp/twinops-preview-gate/phase-e-operational-findings.json `
  --code-commit (Read-Host 'Reviewed E1-E5 code commit') `
  --vercel-executable $vercelExe `
  --expected-vercel-version 59.3.0 `
  --expected-project forzy-twinops `
  --expected-team 9luis7s-projects `
  --expected-scope 9luis7s-projects `
  --preview-env-access-approval-ref (Read-Host 'Approval reference for preview-env access')
if ($LASTEXITCODE -ne 0) { throw 'preview gate initialization failed' }
```

`initialize` rejects an existing checkpoint, validates the operational report and every E2 binding, captures script/config blobs from the reviewed code commit, and repeats the local CLI/help/link/curl audit. Only then does it perform the first authenticated identity prelude: exact frozen-CLI `whoami --format json --scope 9luis7s-projects --no-color` plus `project inspect forzy-twinops --non-interactive --scope 9luis7s-projects --no-color`; project inspection adds a machine-readable output flag only when that exact flag/value was captured from audited pinned help, otherwise it uses the tested closed parser for the documented non-interactive output. Both run with `CI=1`, closed stdin, bounded output/time and immediate native-exit checks; JSON, when selected, is duplicate-key strict. It requires the expected logged-in identity, team `9luis7s-projects`, project `forzy-twinops`, preview access and scope; missing login, SAML reauthentication, prompt/HTML/prose outside the audited grammar, inaccessible team/project, wrong scope or ambiguous identity blocks before environment access. It then runs the reviewed `verify_vercel_protection.py` through authenticated read-only `vercel api` GETs and requires the typed preview protection method/scope/bypass/exception contract before `verify_env.py` is invoked only through `vercel env run -e preview --`. The exact preview host is still nullable at initialization, but project preview scope must be protected and automation bypass configured. Scans before/after prove that no env file was persisted. The checkpoint stores only sanitized hashes, including Vercel/curl path and executable digests, plus the protection-result digest. Close this shell; later steps must not reuse `$checkpoint`, `$vercelExe`, functions or secrets from it. Every later database subcommand prompts again for the raw expected fingerprint, verifies its hash against the checkpoint, obtains preview variables only inside that command's `vercel env run` child and discards them when the child exits.

- [ ] **Step 2: Dry-run typed migration 003 and stop for migration authorization**

Start a new process. The controller securely prompts for the expected preview fingerprint and audited UTC policy `effectiveFrom`, stores only their hashes/sanitized policy identity, creates a fresh guarded destination, and invokes the typed `check_postgres.py --migrate --dry-run --result-json ...`:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py migration-dry-run --checkpoint $checkpoint
if ($LASTEXITCODE -ne 0) { throw 'migration dry-run gate failed' }
```

The controller reasserts code/status/script blobs/CLI/link/project/team/scope immediately before `verify_env` and again before the dry-run child. Require operation `migrate`, mode `dry-run`, before `002`, target/after `003`, zero applied statements/writes, exact migration/policy hashes and `verified=true`. Present only the sanitized catalog delta, checksum, policy ID/hash/effectiveFrom, rollback semantics and checkpoint digest. Await a distinct explicit migration-apply approval.

- [ ] **Step 3: Apply migration, then run two independently re-audited typed checks**

After approval, use a new process and an approval reference:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py migration-apply --checkpoint $checkpoint --approval-ref (Read-Host 'Migration apply approval reference')
if ($LASTEXITCODE -ne 0) { throw 'migration apply/recheck gate failed' }
```

The subcommand performs three separate children: typed apply, typed check 1 and typed check 2. It reasserts every frozen identity before **each** child, uses a new nonce result for each, and binds identical schema/migration/policy/catalog identity. Apply may report only the planned bounded writes; both checks are read-only with zero writes. If the process dies after apply, rerunning from checkpoint first performs typed read-only recovery and proves the idempotent state; it never assumes apply failed.

- [ ] **Step 4: Dry-run staging from a freshly re-entered local CSV path and stop for stage authorization**

Start a new PowerShell process and reconstruct only the executable/checkpoint paths shown below:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py stage-dry-run --checkpoint $checkpoint
if ($LASTEXITCODE -ne 0) { throw 'stage dry-run gate failed' }
```

The controller prompts for the absolute CSV path only in this process, resolves/revalidates it as a regular non-reparse file, requires source SHA `sha256:f09a6613bf6ba3416555a15de6b381bd842474f5f3f33c20660416c7164f0be4`, invokes `stage-history` with profile `forzy-history-2026-05-19-v1`, and never stores the path. Require the exact A-owned closed result shape (which does not invent a `profile` field), asset `forzy-motor-01`, deterministic batch/history-manifest IDs, `rawRowCount=7183`, `sampleCount=14366`, `operatingCycleCount=204`, the deterministic dry-run prediction for `inserted`, zero writes and no activation. Historical-point count is verified later by `verify-timeline-db`; it is not invented as a `stage-history` field. Present the sanitized result and await a distinct stage-apply approval.

- [ ] **Step 5: Stage, fully revalidate idempotence, and keep the batch inactive**

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py stage-apply --checkpoint $checkpoint --approval-ref (Read-Host 'Stage apply approval reference')
if ($LASTEXITCODE -ne 0) { throw 'stage apply/revalidation gate failed' }
```

The fresh process prompts for/revalidates the CSV again. It runs apply and then a second `stage-history --apply` as an idempotent revalidation, with a full identity audit before each child. The second result must equal the first and dry-run for source/batch/history manifest and all three A-owned counts, while `inserted=false` and `writesPerformed=0`. Then a separately re-audited read-only `show-active` must equal the pre-stage active identity, proving staging did not activate the new batch. Partial equality, invented fields or non-null checks do not pass.

- [ ] **Step 6: Dry-run causal assessments bound to the Phase B evidence commit and stop for assessment authorization**

Start a new PowerShell process; no CSV path, fingerprint value or child environment from staging is reusable:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py assess-dry-run --checkpoint $checkpoint
if ($LASTEXITCODE -ne 0) { throw 'assessment dry-run gate failed' }
```

The controller reads `phase-b-local-causal-manifest.json` from the exact `$phaseBEvidenceCommit` recorded in E2, verifies the current tracked blob matches that evidence-commit blob, and separately requires `manifest.reviewedCodeCommit == plans.B.verifiedCodeCommit`. It must never resolve the manifest as `$phaseBCodeCommit:path`. Bind batch; the literal artifact/report/canonical-config hashes `sha256:68d00121edbf8c4c01cf7cd231cd57c4c8eff25661135494e3c791ca78e562ba`, `sha256:2a9d9e407dcd1e71977e84acc78b7620e2ed742841699c7cf51b8056bbab6ebb` and `sha256:5ff7b883606cf692a0eb1ba7e0a7f5d6b5468c3899cd508194d2e6fca3360415`; assessment manifest; exact assessment/candidate/validated-anchor/validated-episode counts; both zero violation counts; and zero remote writes. Present the Phase B evidence commit, manifest blob/digest and exact local↔remote equality; await a new assessment-materialization approval.

- [ ] **Step 7: Materialize assessments and run both apply-no-op and dry-run revalidation**

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py assess-apply --checkpoint $checkpoint --approval-ref (Read-Host 'Assessment materialization approval reference')
if ($LASTEXITCODE -ne 0) { throw 'assessment apply/revalidation gate failed' }
```

Run three separately re-audited children: apply; idempotent apply again with `insertedCount=0`, `existingCount=assessmentCount` and `writesPerformed=0`; and dry-run with `writesPerformed=0`. Enforce the full B-owned result shape, including `insertedCount`/`existingCount` algebra, and require every manifest identity, assessment/candidate/validated count and violation invariant to equal the reviewed Phase B evidence manifest field by field. Revalidation also proves every causal episode satisfies `episodeStartedAt <= assessmentWindow.end <= assessmentAt <= anchor.eventAt`. Any failure leaves the staged batch inactive.

- [ ] **Step 8: Read fresh active state, dry-run CAS activation, and stop for activation authorization**

Start a new PowerShell process and re-enter the expected fingerprint; never copy an active-batch expectation from operator input:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py activation-dry-run --checkpoint $checkpoint
if ($LASTEXITCODE -ne 0) { throw 'activation dry-run gate failed' }
```

The controller first runs a fresh typed `show-active` and uses its observed `activeBatchId|null` as the CAS expectation; operator-entered expected state is forbidden. It then re-audits and runs `activate-history --dry-run` with exact source/history/assessment manifests and all counts. Store the show-active result digest/CAS value in the checkpoint and present it with the staged identities. Await a distinct activation approval.

- [ ] **Step 9: Re-read CAS immediately before apply, activate, and prove the full read-only contract**

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py activation-apply --checkpoint $checkpoint --approval-ref (Read-Host 'Activation approval reference')
if ($LASTEXITCODE -ne 0) { throw 'activation apply/verification gate failed' }
```

Immediately before apply, run a **new** typed `show-active`. If it equals the dry-run CAS value, apply with that fresh expected value, then run separately re-audited `show-active`, `verify-active` and `verify-timeline-db`. For restart recovery only, if fresh `show-active` already equals the intended new batch because a prior authorized apply committed before its checkpoint replace, do not write again: require the complete intended source/history/assessment identities and counts, rerun `verify-active` plus `verify-timeline-db`, bind the prior apply-result digest if still guarded, and advance as a proven idempotent recovery. Any state equal to neither the approved CAS value nor the fully verified intended batch aborts before `BEGIN` and requires a new dry-run/approval.

The A-owned activation/show/verify results must agree on their exact shared fields: asset, active batch, source/history/assessment manifests, schema `003`, raw `7183`, samples `14366`, cycles `204` and exact assessment count; apply must also bind `previousActiveBatchId`, `activated` and writes. The E-owned timeline verifier independently adds `historicalPointCount=14366`, exact event-candidate/valid-anchor-episode counts and causal validity. `show-active`/`verify-active` accept no write mode; timeline verification proves the production repository/service composition and no write transaction. This full union of closed contracts, not invented cross-command fields or merely `activeBatchId`, closes the activation gate.

- [ ] **Step 10: Export and commit only the sanitized database report**

Use a fresh process; the exporter reads only the validated checkpoint and its digest-bound direct results under `tmp/twinops-admin-results` and never reconnects:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py export-database-report --checkpoint $checkpoint --output docs/verification/unified-twin-preview-database-report.md
if ($LASTEXITCODE -ne 0) { throw 'database report export failed' }
& $python scripts/unified_preview_gate.py verify-evidence-scope --checkpoint $checkpoint --allow docs/verification/unified-twin-preview-database-report.md
if ($LASTEXITCODE -ne 0) { throw 'database evidence scope failed' }
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$databaseEvidenceParent=Get-ExactGitHead
$databaseEvidenceCommit=Invoke-ExactGitCommit -ExpectedParent $databaseEvidenceParent -Paths @(
  'docs/verification/unified-twin-preview-database-report.md'
) -Message 'docs: record authorized preview database gates'
```

The report records code SHA, typed migration/check digests, fingerprint **digest** only, policy identity, batch/all manifests/all exact counts, `$phaseBEvidenceCommit`, local→dry→apply→revalidate equality, fresh CAS sequence and approval-reference hashes. It contains no raw fingerprint/path/env/DSN/host/secret and states production untouched. `$databaseEvidenceCommit` is evidence only; E7 continues to bind executable code to `$phaseEOperationalCodeCommit`.



### Task E7: Create and verify a protected preview

**Files:**
- Modify: `docs/deploy/demo-runbook.md`
- Create during execution: `docs/verification/unified-twin-preview-report.md`
- Create during execution: `docs/verification/unified-twin-preview-log-summary.json`
- Create during execution: `docs/verification/phase-e-findings.json`
- Create during execution: `docs/verification/phase-e-review-lineage-v1.json`
- Create only as ignored transient evidence: `tmp/twinops-preview-gate/screenshots/<runId>/{desktop,mobile}/{normal,watch,alert,insufficient-data,historical-alert,historical-gap,fallback}.png` (never stage)

**Precondition:** The checkpoint is at `database_verified`; `$phaseEOperationalCodeCommit` remains the reviewed executable identity even though Task E6 may have added an evidence-only commit. The controller proves every build input and executable blob still equals that code commit and the only later changes are closed evidence paths.

- [ ] **Step 1: Build the reviewed code through in-memory preview env, audit it, and stop for deploy authorization**

Start a fresh process. The previously recorded preview-env access authorization must still match the checkpoint; otherwise request a new access authorization before this command.

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py build-preview --checkpoint $checkpoint
if ($LASTEXITCODE -ne 0) { throw 'reviewed preview build/audit failed' }
```

The controller reasserts code/status/untracked allowlist/script blobs/CLI path+hash+59.3.0/help/link/project/team/scope, reruns the typed read-only Deployment Protection attestation for preview scope, rejects any `.env*`, and runs `vercel env run -e preview -- <frozen-vercel> build --target=preview --yes`. It checks no env file appeared, then audits `.vercel/output` with closed paths, file modes, sizes and content hashes. Require all runtime modules/migrations/assets and exclude CSV, raw/history bytes, reports, tests, `.agents`, env files and secret-like material. Store one deterministic output-manifest digest bound to `$phaseEOperationalCodeCommit`; no current `HEAD` substitution.

Present the code SHA, E1–E5 independent verdict, full local matrix, E2 result, preview DB report, exact output digest, protected-preview smoke contract and production prohibition. Await a separate explicit deployment-preview authorization. A build is not deploy authorization.

- [ ] **Step 2: Immediately re-audit prebuilt output/CLI/link and deploy preview in one controller process**

After deploy authorization, start a new process:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py deploy-preview --checkpoint $checkpoint --approval-ref (Read-Host 'Preview deploy approval reference')
if ($LASTEXITCODE -ne 0) { throw 'protected preview deployment failed' }
```

Before the final identity prelude, atomically persist a `deploying` intent containing only run ID, approval-reference hash, reviewed code SHA and output digest. Then, inside this single subcommand and immediately before the network write, re-run Git code/evidence scope, every frozen blob, CLI and curl canonical path/hash/version/help, `.vercel/project.json` hash, whoami/project/team/scope, the typed read-only project-preview Deployment Protection attestation and the complete `.vercel/output` audit/digest. Invoke the frozen CLI as `deploy --prebuilt --target=preview --yes --no-color --scope 9luis7s-projects --meta twinopsGateRun=<runId> --meta twinopsCodeCommit=<codeSha> --meta twinopsOutputSha256=<digest>`; the already-frozen link selects project `forzy-twinops`, and an unsupported/invented deploy `--project` flag is forbidden. Allow 10 minutes. Capture stdout/stderr only in bounded memory, require one canonical credential-free HTTPS `.vercel.app` URL, then run `inspect <exact-url> --non-interactive --scope 9luis7s-projects --no-color` with only the output-format option proven verbatim by the pinned help audit (or the closed audited non-interactive parser if none exists), and require a `dpl_...` ID, target `preview`, state `READY`, the same project/team and all three exact intent metadata values. Re-run `verify_vercel_protection.py` against that exact deployment/host and require a protection scope/method that covers it, `automationBypassConfigured=true`, and `previewUrlExcepted=false`. Bind code SHA → output digest → deployment ID → URL plus both protection-result digests in the checkpoint.

If the process restarts with `state="deploying"` and no bound deployment, it must not prompt for a candidate and must not issue `deploy` again under the old approval. After the full identity/protection prelude it runs exactly the audited frozen-CLI form `list forzy-twinops --environment preview --meta twinopsGateRun=<runId> --meta twinopsCodeCommit=<codeSha> --meta twinopsOutputSha256=<digest> --format json --scope 9luis7s-projects --no-color` (or the synonymous `ls` only if that is the help-audited command), with closed stdin and bounded strict duplicate-key JSON. The controller filters the returned typed records again in-process by **all three exact metadata values**, project, team and preview target. Exactly one match is required: it then runs the same non-interactive audited `inspect`, validates READY/project/team/preview plus all intent fields, and reattests the exact deployment's protection before adoption. Zero matches stops and requires a **new explicit deploy authorization** before replacing the intent; more than one, malformed metadata or a mismatch blocks for investigation. Neither case permits implicit redeploy or operator selection. A normal successful deploy runs this same list-exactly-one plus inspect/protection sequence before checkpoint binding, so crash and non-crash paths converge. `--json` and `--yes` are not accepted on the list path unless separately documented for that command; `--format json` is mandatory.

`--prod`, `promote`, alias mutation, project relink and every Deployment Protection setting mutation are forbidden. A challenge response is not accepted as proof: the typed authorized read-only state must positively show the enabled method, preview-covering scope, configured automation bypass and exception-host hashes. Protection remains enabled; no public exception is created and the exact preview URL host must not be excepted.

- [ ] **Step 3: Run the exact GET-only smoke through official `vercel curl`**

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py smoke-preview --checkpoint $checkpoint
if ($LASTEXITCODE -ne 0) { throw 'protected preview GET smoke failed' }
```

The controller re-audits identity, reattests the exact deployment's typed protection state and `previewUrlExcepted=false`, runs a new `verify-timeline-db` through in-memory preview env, re-audits again, and only then calls `verify_deployment.py` with that guarded result and checkpoint values. The verifier uses only `vercel curl ... --deployment <exact-url> --scope 9luis7s-projects ... --request GET` for the seven frozen HTTP paths. Require exact batch, source/history/assessment manifests, artifact/report/config hashes, schema, all exact raw/history/sample/cycle/assessment/candidate/event/valid-anchor counts and model asset hashes; HTTP active batch/timeline/context must corroborate the fresh DB result. The guarded report must say `transport=vercel-curl`, carry the DB-result and protection-result digests and `refresh=not_requested`; any POST, direct URL client or partial/minimum count fails.

- [ ] **Step 4: Run Playwright with an explicitly authorized in-memory bypass secret**

Present that Playwright needs the project's automation bypass secret only on the reviewed fixture's allowed same-origin requests while protection stays enabled; it is never configured as a browser-context/global header. Request explicit authorization to use it for this one E2E child. After approval, start a fresh process:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py browser-preview --checkpoint $checkpoint --approval-ref (Read-Host 'In-memory automation-bypass approval reference')
if ($LASTEXITCODE -ne 0) { throw 'protected preview browser gate failed' }
```

Before accepting the secret, the controller reattests the exact deployment's typed protection state and `previewUrlExcepted=false`. It prompts for `VERCEL_AUTOMATION_BYPASS_SECRET` with non-echoing input, never accepts it on argv, and passes it only in the child environment together with the exact checkpoint URL/ID. It executes exactly `deployed-real.spec.js`, `operational-scenarios.spec.js`, `operational-accessibility.spec.js` and `interactive-twin.spec.js`, all through `protected-preview-fixture.js`. `playwright.config.js` has no global `extraHTTPHeaders`. The fixture installs an exact-origin route before navigation, aborts every other origin plus every websocket/beacon/service-worker request, and permits only `GET|HEAD` to `/`, reviewed `/assets/**`, frozen API/model paths and the one validated context query. It constructs and merges `x-vercel-protection-bypass` plus `x-vercel-set-bypass-cookie: true` only after an allowed same-origin request passes; redirects, cross-origin subresources and disallowed same-origin methods/paths are aborted before header construction. Tests prove the secret is absent from cross-origin requests, reporters, traces and errors. No query parameter, env file, report attachment or log may contain it. The controller removes its in-memory reference after child exit. Playwright writes with traces/videos disabled into a fresh controller-owned temporary output root; after success, the controller requires exactly fourteen scenario×viewport PNG attachments, validates dimensions/content, strips metadata and atomically materializes only the fourteen fixed evidence paths declared above, then containment-checks and removes the temporary output root. It records only relative evidence paths/hashes in the checkpoint/report and never stages them. Route interception proves zero outbound POSTs. Never disable protection to make a test pass.

- [ ] **Step 5: Inspect deployment-scoped logs through the sanitizer**

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py logs-preview --checkpoint $checkpoint --output docs/verification/unified-twin-preview-log-summary.json
if ($LASTEXITCODE -ne 0) { throw 'deployment log verification failed' }
```

The wrapper re-audits identity and invokes only the frozen deployment-scoped command `logs --deployment <dpl_...> --environment preview --level error --level warning --level fatal --limit 100 --json --since <deploy-intent-rfc3339> --until <browser-finished-rfc3339> --no-branch --scope 9luis7s-projects --project forzy-twinops --no-color`. The checkpoint supplies both UTC bounds: they enclose deployment, smoke and browser execution, are ordered, and span at most 30 minutes. The controller captures `browser-finished-rfc3339` immediately after the browser child. The wrapper checks native exit first, bounds raw JSONL in memory, rejects any out-of-window/other-level record and treats exactly 100 records as possibly truncated, then writes aggregate `error|warning|fatal` counts only. No raw/intermediate log file is allowed. Any suspicious import/migration/cold-start category blocks closure and triggers a controller-reviewed investigation, not a broader dump.

- [ ] **Step 6: Assemble sanitized evidence and verify tracked plus untracked scope**

Update the runbook and create the preview report only through the controller exporter:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py export-preview-report --checkpoint $checkpoint --output docs/verification/unified-twin-preview-report.md
if ($LASTEXITCODE -ne 0) { throw 'preview report export failed' }
& $python scripts/unified_preview_gate.py verify-evidence-scope --checkpoint $checkpoint
if ($LASTEXITCODE -ne 0) { throw 'preview evidence scope failed' }
```

`verify-evidence-scope` uses NUL-delimited Git status plus `git ls-files --others --exclude-standard` and a filesystem scan for ignored operational roots. Its closed allowlist includes only E2/operational-review inputs, the checkpoint and its digest-bound direct `tmp/twinops-admin-results` children, frozen `.vercel/project.json`/`README.txt`, currently audited build roots, database/preview/log reports, the fourteen exact ignored screenshot paths recorded by `browser-preview`, runbook, ledger/generated Markdown, final review and review-lineage result. Any other tracked or untracked path—including `.env*`, CSV, DB, raw log/body, alternate screenshot directory or implementation file—fails. The report records code/output/deployment chain, typed protection scope/method plus exception-host/protection-result digests, `previewUrlExcepted=false`, screenshot hashes, exact DB/smoke identities and no-POST result, never protection credentials.

- [ ] **Step 7: Independently review the frozen code/deployment identity**

An independent reviewer inspects exactly `$phaseEOperationalCodeCommit`, its E1–E5 operational review, audited output digest, deployment ID/URL, protected-access method and uncommitted sanitized evidence. It carries every operational finding entry forward with the same ID/severity/title and legal status lineage—not merely the aggregate verdict—and writes `docs/verification/phase-e-findings.json` in strict `finding-review-v1` shape with `plan="E"` and `reviewedSha=$phaseEOperationalCodeCommit`. Zero Critical/Important and no unaccepted Minor are required. An executable/config/controller finding returns to E5, creates a new reviewed code SHA, rebuilds/re-audits and requires fresh relevant remote approvals; an evidence-only correction does not redefine code.

- [ ] **Step 8: Ingest the code review, close only preview criteria, and commit evidence**

Use a fresh process; derive the immutable code SHA from the strict review, not `HEAD`:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$review=Get-Content -Raw -Encoding UTF8 docs/verification/phase-e-findings.json | ConvertFrom-Json
$verifiedCodeCommit=[string]$review.reviewedSha
if ([string]$review.plan -cne 'E' -or $verifiedCodeCommit -notmatch '^[0-9a-f]{40}$' -or [int]$review.verdict.critical -ne 0 -or [int]$review.verdict.important -ne 0 -or [int]$review.verdict.minor -ne 0) { throw 'Plan E deployment review is not clean or is misbound' }
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/verify_e_review_lineage.py verify --checkpoint $checkpoint --operational-review tmp/twinops-preview-gate/phase-e-operational-findings.json --final-review docs/verification/phase-e-findings.json --expected-code-commit $verifiedCodeCommit --output docs/verification/phase-e-review-lineage-v1.json
if ($LASTEXITCODE -ne 0) { throw 'operational-to-final E review lineage failed' }
& $python scripts/verify_unified_acceptance.py ingest-authenticated-review-lineage --ledger docs/verification/unified-twin-acceptance-v1.json --review-report docs/verification/phase-e-findings.json --operational-review tmp/twinops-preview-gate/phase-e-operational-findings.json --checkpoint $checkpoint --lineage-result docs/verification/phase-e-review-lineage-v1.json --expected-code-commit $verifiedCodeCommit
if ($LASTEXITCODE -ne 0) { throw 'Plan E authenticated deployment-review lineage ingestion failed' }
& $python scripts/verify_unified_acceptance.py update-criterion --ledger docs/verification/unified-twin-acceptance-v1.json --criterion AC-12 --status passed --evidence-kind preview --evidence-ref docs/verification/unified-twin-preview-report.md --verified-code-commit $verifiedCodeCommit
if ($LASTEXITCODE -ne 0) { throw 'AC-12 preview criterion update failed' }
& $python scripts/verify_unified_acceptance.py update-criterion --ledger docs/verification/unified-twin-acceptance-v1.json --criterion AC-24 --status passed --evidence-kind preview --evidence-ref docs/verification/unified-twin-preview-report.md --verified-code-commit $verifiedCodeCommit
if ($LASTEXITCODE -ne 0) { throw 'AC-24 preview criterion update failed' }
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
if ($LASTEXITCODE -ne 0) { throw 'Plan E preview ledger rendering failed' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'Plan E preview ledger update failed' }
& $python scripts/unified_preview_gate.py verify-evidence-scope --checkpoint $checkpoint
if ($LASTEXITCODE -ne 0) { throw 'post-review preview evidence scope failed' }
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$previewEvidenceParent=Get-ExactGitHead
$previewEvidenceCommit=Invoke-ExactGitCommit -ExpectedParent $previewEvidenceParent -Paths @(
  'docs/deploy/demo-runbook.md',
  'docs/verification/unified-twin-preview-report.md',
  'docs/verification/unified-twin-preview-log-summary.json',
  'docs/verification/phase-e-findings.json',
  'docs/verification/phase-e-review-lineage-v1.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) -Message 'docs: record protected preview evidence'
```

The screenshot files remain ignored transient review inputs and are never added to Git; the tracked report carries their sanitized hashes. After commit, verify the ledger still stores `$verifiedCodeCommit`; `$previewEvidenceCommit` is evidence only and is recorded externally. Critical/Important cannot be accepted.



### Task E8: Execute and validate the human usability gate

**Files:**
- Modify: `docs/verification/unified-twin-acceptance-v1.json`
- Create from the facilitated browser sessions: `docs/usability/operational-triage-usability-v1-harness.json`
- Create from actual sessions: `docs/usability/operational-triage-usability-v1-results.json`
- Generate from the reviewed validator: `docs/usability/operational-triage-usability-v1-assessment.json`
- Generate from JSON: `docs/usability/operational-triage-usability-v1-results.md`
- Modify: `docs/verification/unified-twin-acceptance-v1.md`
- Reuse unchanged: `scripts/run-operational-usability-harness.mjs`, `tests/e2e/support/protected-preview-fixture.js`, `tests/e2e/support/operational-usability-routes-v1.js`, the four C-authored fixture payloads, `scripts/verify_usability_result.py` and their E5-reviewed tests

**Precondition:** Task E7 ingested a clean review and froze `plans.E.verifiedCodeCommit`; human sessions use the protected preview for that exact code/output/deployment binding. Before each facilitated session, the controller reattests the exact deployment's typed protection state and `previewUrlExcepted=false`. Participants access the browser-only harness through normal authorized Vercel access or a separately authorized, non-echoed bypass secret confined to that one reviewed harness child; never disable protection, create an exception or disclose the secret. A code/output/deployment/protection/harness/fixture change invalidates all sessions.

- [ ] **Step 1: Confirm participant classes, consent and protocol binding**

Use exactly two actual technical role classes: `operation_instrumentation` and `reliability_rotating_equipment_vibration`. Record role class and opaque session ID only—no name, email, employer ID, voice/video, free-form biography or other personal data. Record consent as a boolean. Bind the protocol to rubric `operational-triage-usability-v1`, the immutable Plan E code SHA, audited output-manifest digest, deployment ID, sanitized URL hash, typed protection-result digest, reviewed harness code digest, fixture-manifest digest, all four individual fixture digests and viewport `1366x768`.

- [ ] **Step 2: Run all eight role×scenario observations and author the JSON SSoT**

For each participant, `run-operational-usability-harness.mjs` opens the real protected preview in bundled Chromium, loading its deployed HTML/JS/CSS/model assets through `protected-preview-fixture.js`. The separate reviewed `operational-usability-routes-v1.js` intercepts only the exact frozen API GET paths and supplies exactly the four C-authored fixtures `normal_fresh`, `persistent_candidate`, `gap` and `acquisition_failure`; byte-equivalence tests bind them to their Phase C blobs. This is a controlled evaluation fixture, never a product/runtime mock: no runtime source, build output, preview database, API route or deployment configuration may be changed, and external origins plus non-GET/HEAD traffic are blocked. A fresh context is created for each scenario with `now` selected and the first details panel closed.

For each role, obtain a distinct authorization to provide the bypass only to that one facilitator child, then start a **new PowerShell process** and run the corresponding command. Never run the two approved children from retained PowerShell state:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py human-usability-session --checkpoint $checkpoint --role operation_instrumentation --opaque-session-id (Read-Host 'Opaque session ID') --approval-ref (Read-Host 'Per-session bypass approval reference')
if ($LASTEXITCODE -ne 0) { throw 'operation/instrumentation usability session failed' }
```

Close that process. In another fresh process:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py human-usability-session --checkpoint $checkpoint --role reliability_rotating_equipment_vibration --opaque-session-id (Read-Host 'Opaque session ID') --approval-ref (Read-Host 'Per-session bypass approval reference')
if ($LASTEXITCODE -ne 0) { throw 'reliability/vibration usability session failed' }
& $python scripts/unified_preview_gate.py export-usability-harness --checkpoint $checkpoint --output docs/usability/operational-triage-usability-v1-harness.json
if ($LASTEXITCODE -ne 0) { throw 'usability harness export failed' }
```

The facilitator, not the harness, records each participant's answers. For every observation record duration seconds, primary interaction count, whether the participant correctly identified data trust, motivating sensor/quantity, deviation start or explicit unavailability, and safe next verification, plus an explicit list of unsupported inferences. Normal/fresh has a 30-second limit; the other scenarios require at most 60 seconds and three primary interactions. Any claim of failure, cause, stop/run instruction or physical sensor/component location fails regardless of time. After the eighth observation, the harness emits only sanitized `operational-triage-usability-harness-v1` evidence: code/output/deployment/URL/protection/harness/fixture-manifest digests, the four fixture digests, scenario order, viewport and pass/fail transport invariants. It contains no answers, response body, secret, URL, timestamps or personal data.

The result JSON has exactly `schemaVersion`, `protocolVersion`, `verifiedCodeCommit`, `outputManifestSha256`, `deploymentId`, `deploymentUrlSha256`, `protectionStateSha256`, `harnessManifestSha256`, `fixtureManifestSha256`, `fixtureSha256ByScenario`, `viewport`, `participants`, `observations`, `findings` and `declaredVerdict`. Participants and observations use closed keys/enums; there are exactly two participant roles and eight unique role×scenario pairs. `findings` uses stable IDs/severity/status/evidence refs and contains every ambiguity, missing evidence or unsafe inference. The human recorder may declare a verdict, but only the validator computes eligibility. The result's digests must equal the independently parsed harness/checkpoint bindings; copying self-declared identities is insufficient.

- [ ] **Step 3: Validate first, then deterministically render the human result**

Start a fresh process and run the already-reviewed validator before touching the ledger:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
& $python scripts/verify_usability_result.py verify `
  --input docs/usability/operational-triage-usability-v1-results.json `
  --harness docs/usability/operational-triage-usability-v1-harness.json `
  --ledger docs/verification/unified-twin-acceptance-v1.json `
  --checkpoint tmp/twinops-preview-gate/checkpoint-v1.json
if ($LASTEXITCODE -ne 0) { throw 'human usability result is incomplete, unsafe or misbound' }
& $python scripts/verify_usability_result.py assess `
  --input docs/usability/operational-triage-usability-v1-results.json `
  --harness docs/usability/operational-triage-usability-v1-harness.json `
  --ledger docs/verification/unified-twin-acceptance-v1.json `
  --checkpoint tmp/twinops-preview-gate/checkpoint-v1.json `
  --output docs/usability/operational-triage-usability-v1-assessment.json
if ($LASTEXITCODE -ne 0) { throw 'human usability assessment failed closed' }
& $python scripts/verify_usability_result.py render `
  --input docs/usability/operational-triage-usability-v1-results.json `
  --harness docs/usability/operational-triage-usability-v1-harness.json `
  --assessment docs/usability/operational-triage-usability-v1-assessment.json `
  --output docs/usability/operational-triage-usability-v1-results.md
if ($LASTEXITCODE -ne 0) { throw 'human usability rendering failed' }
& $python scripts/verify_usability_result.py verify-render `
  --input docs/usability/operational-triage-usability-v1-results.json `
  --harness docs/usability/operational-triage-usability-v1-harness.json `
  --assessment docs/usability/operational-triage-usability-v1-assessment.json `
  --output docs/usability/operational-triage-usability-v1-results.md
if ($LASTEXITCODE -ne 0) { throw 'human usability Markdown is not reproducible' }
```

The validator rejects duplicate/unknown/missing keys, duplicate roles/scenarios, missing consent, PII-like fields, wrong code/output/deployment/protection/harness/fixture/viewport binding, non-finite/negative measures, a self-declared PASS inconsistent with computed thresholds, omitted unsafe-inference answers and any Critical/Important finding hidden by a PASS. `assess` creates closed `operational-triage-usability-assessment-v1` JSON with an independently computed `passed|failed|blocked` status and evidence refs for AC-18 and AC-28. It prints only a sanitized eligibility summary. Validation proves shape, bindings and calculations; it does not fabricate or replace human sessions.

- [ ] **Step 4: Preserve failures and block rather than auto-close**

If either computed criterion is not `passed`, persist the non-PASS evidence before stopping. The reviewed validator is the only writer allowed to translate the assessment into ledger status, and `record-nonpass` can mutate only AC-18/AC-28:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$review=Get-Content -Raw -Encoding UTF8 docs/verification/phase-e-findings.json | ConvertFrom-Json
$verifiedCodeCommit=[string]$review.reviewedSha
if ($verifiedCodeCommit -notmatch '^[0-9a-f]{40}$') { throw 'Plan E has no reviewed code commit' }
& $python scripts/verify_usability_result.py record-nonpass --input docs/usability/operational-triage-usability-v1-results.json --harness docs/usability/operational-triage-usability-v1-harness.json --assessment docs/usability/operational-triage-usability-v1-assessment.json --ledger docs/verification/unified-twin-acceptance-v1.json --verified-code-commit $verifiedCodeCommit
if ($LASTEXITCODE -ne 0) { throw 'non-PASS human result could not be recorded safely' }
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
if ($LASTEXITCODE -ne 0) { throw 'non-PASS ledger rendering failed' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'non-PASS ledger verification failed' }
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$humanNonpassParent=Get-ExactGitHead
$humanNonpassEvidenceCommit=Invoke-ExactGitCommit -ExpectedParent $humanNonpassParent -Paths @(
  'docs/usability/operational-triage-usability-v1-harness.json',
  'docs/usability/operational-triage-usability-v1-results.json',
  'docs/usability/operational-triage-usability-v1-assessment.json',
  'docs/usability/operational-triage-usability-v1-results.md',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) -Message 'docs: record non-passing operational triage sessions'
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'committed non-PASS ledger is invalid' }
$pending=(git status --porcelain=v1 -z)
if ($LASTEXITCODE -ne 0 -or $pending.Length -ne 0) { throw 'non-PASS evidence commit is not clean' }
throw "Human gate is non-PASS at evidence commit $humanNonpassEvidenceCommit; stop before production eligibility"
```

Malformed, fabricated or misbound evidence exits before `record-nonpass` and creates neither assessment nor ledger mutation. A valid `failed|blocked` assessment must follow the branch above, carry every finding into Task E9's cumulative review and end execution only after the rendered ledger is verified and committed. Green automated tests cannot override it, and the preview is not eligible for production review.

- [ ] **Step 5: Explicitly update AC-18 and AC-28 only after validator PASS**

Only when the validator reports both `eligibleAC18=true` and `eligibleAC28=true`, read the immutable reviewed SHA from the already-ingested strict E review and update the two criteria explicitly:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$review=Get-Content -Raw -Encoding UTF8 docs/verification/phase-e-findings.json | ConvertFrom-Json
$verifiedCodeCommit=[string]$review.reviewedSha
if ($verifiedCodeCommit -notmatch '^[0-9a-f]{40}$') { throw 'Plan E has no reviewed code commit' }
& $python scripts/verify_usability_result.py verify --input docs/usability/operational-triage-usability-v1-results.json --harness docs/usability/operational-triage-usability-v1-harness.json --assessment docs/usability/operational-triage-usability-v1-assessment.json --ledger docs/verification/unified-twin-acceptance-v1.json --checkpoint tmp/twinops-preview-gate/checkpoint-v1.json --require-ac18-pass --require-ac28-pass
if ($LASTEXITCODE -ne 0) { throw 'human criteria are not validator-eligible' }
& $python scripts/verify_unified_acceptance.py update-criterion --ledger docs/verification/unified-twin-acceptance-v1.json --criterion AC-18 --status passed --evidence-kind human --evidence-ref docs/usability/operational-triage-usability-v1-results.json --verified-code-commit $verifiedCodeCommit
if ($LASTEXITCODE -ne 0) { throw 'AC-18 human criterion update failed' }
& $python scripts/verify_unified_acceptance.py update-criterion --ledger docs/verification/unified-twin-acceptance-v1.json --criterion AC-28 --status passed --evidence-kind human --evidence-ref docs/usability/operational-triage-usability-v1-results.json --verified-code-commit $verifiedCodeCommit
if ($LASTEXITCODE -ne 0) { throw 'AC-28 human criterion update failed' }
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
if ($LASTEXITCODE -ne 0) { throw 'human ledger rendering failed' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'human criterion ledger update failed' }
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$humanEvidenceParent=Get-ExactGitHead
$humanEvidenceCommit=Invoke-ExactGitCommit -ExpectedParent $humanEvidenceParent -Paths @(
  'docs/usability/operational-triage-usability-v1-harness.json',
  'docs/usability/operational-triage-usability-v1-results.json',
  'docs/usability/operational-triage-usability-v1-assessment.json',
  'docs/usability/operational-triage-usability-v1-results.md',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) -Message 'docs: record validated operational triage sessions'
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'committed human ledger is invalid' }
$pending=(git status --porcelain=v1 -z)
if ($LASTEXITCODE -ne 0 -or $pending.Length -ne 0) { throw 'human evidence commit is not clean' }
```

Never use current `HEAD` as the code identity and never hand-edit the generated Markdown.



### Task E9: Final exact-SHA verification and independent evidence review

**Files:**
- Modify: `docs/verification/unified-twin-acceptance-v1.json`
- Modify: `docs/verification/unified-twin-acceptance-v1.md`
- Modify: `docs/verification/unified-twin-preview-report.md`
- Modify: `docs/verification/unified-twin-preview-log-summary.json`
- Create from the isolated run: `docs/verification/ac15-first-fold-result-v1.json`
- Reuse without modification: `scripts/run_ac15_gate.py` and `tests/e2e/operational-scenarios.spec.js`
- Reuse without modification: `docs/usability/operational-triage-usability-v1-harness.json`, `docs/usability/operational-triage-usability-v1-results.json` and `docs/usability/operational-triage-usability-v1-assessment.json`
- Reuse without modification: `docs/verification/phase-e-review-lineage-v1.json`
- Create only after a non-PASS evidence review: `docs/verification/phase-e-evidence-findings.json`

- [ ] **Step 1: Run full local gates without redefining the deployed code SHA**

```powershell
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
& $python -m pytest services/twinops/tests -q
if ($LASTEXITCODE -ne 0) { throw 'full Python gate failed' }
npm.cmd run test:run -- --exclude "**/.pytest_cache/**"
if ($LASTEXITCODE -ne 0) { throw 'full frontend gate failed' }
npm.cmd run build:manifest
if ($LASTEXITCODE -ne 0) { throw 'full build gate failed' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'diff check failed' }
```

Read the immutable code SHA from the ingested `phase-e-findings.json`/ledger and require it equals the checkpoint's deployed code SHA. Run `verify-evidence-scope` to compare every executable frontend/backend source, test, script, package/lockfile, Playwright/Vercel config and asset used below against that code commit. Evidence-only commits may differ only at the closed evidence allowlist; current `HEAD` is never substituted.

- [ ] **Step 2: Run AC-15 in an isolated loopback child and validate its versioned result**

Start a new PowerShell process. Do not set deployment/bypass values in the parent. Supply the absolute worktree Python and exact reviewed code SHA:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$review=Get-Content -Raw -Encoding UTF8 docs/verification/phase-e-findings.json | ConvertFrom-Json
$verifiedCodeCommit=[string]$review.reviewedSha
if ($verifiedCodeCommit -notmatch '^[0-9a-f]{40}$') { throw 'invalid reviewed Plan E code commit' }
& $python scripts/run_ac15_gate.py run `
  --verified-code-commit $verifiedCodeCommit `
  --python-executable $python `
  --config playwright.config.js `
  --spec tests/e2e/operational-scenarios.spec.js `
  --result docs/verification/ac15-first-fold-result-v1.json
if ($LASTEXITCODE -ne 0) { throw 'isolated AC-15 run failed' }
& $python scripts/run_ac15_gate.py verify --verified-code-commit $verifiedCodeCommit --result docs/verification/ac15-first-fold-result-v1.json
if ($LASTEXITCODE -ne 0) { throw 'AC-15 result validation failed' }
```

The runner constructs a closed child environment rather than inheriting the parent. It rejects/removes `DEPLOYMENT_URL`, `TWINOPS_DEPLOYMENT_ID`, `VERCEL_AUTOMATION_BYPASS_SECRET`, DSN/database/upstream/token/proxy values; passes only fixed loopback origins, `TWINOPS_E2E_TEST_MODE=1`, absolute `TWINOPS_PYTHON`, worktree `PYTHONPATH`, and a tested minimum Windows process set (`SystemRoot`/`WINDIR` plus controller-owned `TEMP`/`TMP`). Node, Python and Vite entrypoints are absolute argv entries, so `PATH`, `ComSpec`, user profile and ambient package shims are not inherited. The SQLite path is a fresh guarded command argument, not an environment value. It launches backend and Vite on fixed loopback ports with `reuseExistingServer=false`, uses bundled Chromium with no `channel`, runs exactly both C-authored `@ac15-first-fold` cases and fails on any outbound non-loopback request or POST.

The canonical result has exactly `schemaVersion="ac15-first-fold-result-v1"`, `verifiedCodeCommit`, `pythonVersion`, `playwrightVersion`, `chromiumRevision`, `chromiumExecutableSha256`, `configBlob`, `specBlob`, `originMode="loopback"`, `viewport`, `scenarioIds`, `fixtureIds`, `requiredLocators`, `explicitUnavailableStates`, `outboundPostCount=0` and `passed=true`. `chromiumRevision` is read from the canonical `playwright-core/browsers.json` selected by the reviewed lockfile-owned package and must equal the E1 probe; it is never inferred from an executable filename or system browser. The result contains no absolute executable path, URL, env, secret, timestamp or reporter body. Both scenarios must show at 1366×768 the seven contracted locators—mode, trust, last observation, persistence, dominant evidence, summary and next check—with explicit unavailable states where the fixture requires them.

- [ ] **Step 3: Explicitly update AC-15 immediately after the validated result**

Do not defer this mutation or infer it from a green suite:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$review=Get-Content -Raw -Encoding UTF8 docs/verification/phase-e-findings.json | ConvertFrom-Json
$verifiedCodeCommit=[string]$review.reviewedSha
& $python scripts/run_ac15_gate.py verify --verified-code-commit $verifiedCodeCommit --result docs/verification/ac15-first-fold-result-v1.json
if ($LASTEXITCODE -ne 0) { throw 'AC-15 evidence is not eligible' }
& $python scripts/verify_unified_acceptance.py update-criterion --ledger docs/verification/unified-twin-acceptance-v1.json --criterion AC-15 --status passed --evidence-kind automated --evidence-ref docs/verification/ac15-first-fold-result-v1.json --verified-code-commit $verifiedCodeCommit
if ($LASTEXITCODE -ne 0) { throw 'AC-15 criterion update failed' }
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
if ($LASTEXITCODE -ne 0) { throw 'AC-15 ledger rendering failed' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'explicit AC-15 ledger update failed' }
```

- [ ] **Step 4: Run protected-scope scans with a closed untracked allowlist**

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py verify-evidence-scope --checkpoint $checkpoint
if ($LASTEXITCODE -ne 0) { throw 'final tracked/untracked evidence scope failed' }
```

The scan consumes NUL-delimited tracked status, `git ls-files --others --exclude-standard`, and explicit filesystem enumeration for ignored operational roots. The final allowlist contains only the checkpoint, its digest-bound nonce result files directly under `tmp/twinops-admin-results`, audited `.vercel/output`, exact ledger/reports/review/usability/AC15/runbook paths, and the fourteen ignored screenshot paths recorded in the checkpoint. Reject any extra untracked file as well as tracked CSV/raw DB/env, hardcoded deployment/upstream/DSN, forbidden mechanical claim, `assessment.recommendation` consumption, changed immutable GLB/manifest/conversion report, raw log/body or bypass material. A directory-prefix match is insufficient: every allowed file/path pattern is closed and tested.

- [ ] **Step 5: Re-run the protected GET smoke with exact identities and counts**

Require the checkpoint's preview-env access authorization to remain valid; otherwise obtain a new explicit read/in-memory-access authorization before starting this fresh process.

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py smoke-preview --checkpoint $checkpoint --revalidate
if ($LASTEXITCODE -ne 0) { throw 'final protected GET smoke failed' }
```

This fresh controller process reasserts code/status/blobs/CLI/curl/link/project/team/scope, positively reattests the typed Deployment Protection method/scope/bypass/exceptions against the exact deployment with `previewUrlExcepted=false`, reruns typed read-only `verify-timeline-db`, proves the controlled child resolves only the checkpoint-bound `curl.exe`, and uses official `vercel curl` against the exact stored deployment. Require the same code SHA/output digest/deployment ID/URL, protection-result identity and exact batch/all manifests/all counts as E7, with HTTP active batch/context corroborating the fresh DB result. Any binding change requires a new preview only after fresh authorization.

- [ ] **Step 6: Revalidate bounded deployment logs through the final preview access**

The E8 human sessions and E9 final smoke occurred after the initial E7 log query, so a stale summary cannot close the plan. From a fresh process, atomically replace it only through the reviewed controller:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
& $python scripts/unified_preview_gate.py attest-protection --checkpoint $checkpoint --phase final
if ($LASTEXITCODE -ne 0) { throw 'final typed Deployment Protection attestation failed' }
& $python scripts/unified_preview_gate.py logs-preview --checkpoint $checkpoint --revalidate --output docs/verification/unified-twin-preview-log-summary.json
if ($LASTEXITCODE -ne 0) { throw 'final bounded deployment log revalidation failed' }
```

The controller first records the successful final-smoke bound and the fresh final protection-attestation digest in the checkpoint. Only then does it partition deploy intent through the later of those two remote accesses into contiguous nonoverlapping windows of at most 30 minutes. It reaudits identities before every window, rejects a gap, overlap, 100-record truncation signal, unexpected level or any window ending before the latest E8/E9 preview access, and writes only aggregate sanitized counts/digests. `export-preview-report --finalize` must require and bind this latest summary digest/end bound and the protection-attestation digest it covers; an older E7 digest is rejected.

- [ ] **Step 7: Finalize and commit the evidence bundle**

Start a fresh PowerShell process. Plans A–D remain immutable. Plan E owns exactly AC-12, AC-15, AC-18, AC-24 and AC-28. AC-12/AC-24 must already be preview-passed by E7; AC-15 must now reference the validated isolated result; AC-18/AC-28 may be passed only by E8's validated actual sessions. Assert all five mappings/statuses, render/byte-verify Markdown, run the scope gate again, and commit only declared evidence:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$checkpoint=[IO.Path]::GetFullPath((Join-Path $PWD 'tmp/twinops-preview-gate/checkpoint-v1.json'))
$ledger=Get-Content -Raw -Encoding UTF8 docs/verification/unified-twin-acceptance-v1.json | ConvertFrom-Json
$verifiedCodeCommit=[string]$ledger.plans.E.verifiedCodeCommit
if ($verifiedCodeCommit -notmatch '^[0-9a-f]{40}$') { throw 'final ledger has no reviewed Plan E code commit' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json --require-complete
if ($LASTEXITCODE -ne 0) { throw 'final complete acceptance ledger failed' }
& $python scripts/unified_preview_gate.py export-preview-report --checkpoint $checkpoint --finalize --ac15-result docs/verification/ac15-first-fold-result-v1.json --usability-harness docs/usability/operational-triage-usability-v1-harness.json --usability-result docs/usability/operational-triage-usability-v1-results.json --usability-assessment docs/usability/operational-triage-usability-v1-assessment.json --log-summary docs/verification/unified-twin-preview-log-summary.json --output docs/verification/unified-twin-preview-report.md
if ($LASTEXITCODE -ne 0) { throw 'final preview report binding failed' }
& $python scripts/unified_preview_gate.py verify-evidence-scope --checkpoint $checkpoint
if ($LASTEXITCODE -ne 0) { throw 'final post-export evidence scope failed' }
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$finalEvidenceParent=Get-ExactGitHead
$evidenceCommit=Invoke-ExactGitCommit -ExpectedParent $finalEvidenceParent -Paths @(
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md',
  'docs/verification/unified-twin-preview-report.md',
  'docs/verification/unified-twin-preview-log-summary.json',
  'docs/verification/ac15-first-fold-result-v1.json'
) -Message 'docs: finalize unified twin acceptance evidence'
& $python scripts/unified_preview_gate.py verify-evidence-scope --checkpoint $checkpoint --verified-code-commit $verifiedCodeCommit --evidence-commit $evidenceCommit
if ($LASTEXITCODE -ne 0) { throw 'committed final evidence scope failed' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json --require-complete
if ($LASTEXITCODE -ne 0) { throw 'committed final complete ledger failed' }
$finalHead=Get-ExactGitHead
if ($finalHead -cne $evidenceCommit) { throw 'final HEAD moved from evidence commit' }
$pending=(git status --porcelain=v1 -z)
if ($LASTEXITCODE -ne 0 -or $pending.Length -ne 0) { throw 'final evidence worktree is not clean' }
```

Add no human/screenshot file unless it actually changed and is in the closed allowlist. Record `$evidenceCommit` externally; never write it back into the commit that defines it.

- [ ] **Step 8: Independently review the exact evidence commit**

Reviewer checks `$evidenceCommit`, cumulative E1/operational/deployment/human findings and the authenticated `phase-e-review-lineage-v1` digest/entries, spec AC-01..AC-28, `$phaseBEvidenceCommit`, DB identities and causal inequalities, typed Deployment Protection scope/method/exceptions, frozen curl identity, protected `vercel curl`/same-origin header paths, final bounded log coverage through the last E9 smoke, no-POST/nonleak evidence, bundle contents, AC15 isolation/result, validated human harness/result/assessment, screenshots, keyboard flow, assets, tracked+untracked scope and production non-promotion. It proves the diff from `plans.E.verifiedCodeCommit` contains only the closed evidence allowlist and that `verify --require-complete` succeeds on raw committed ledger bytes, then emits strict `finding-review-v1` with `plan="E"`, `reviewedSha=$evidenceCommit`. Required verdict: 0 Critical / 0 Important; a Minor may be accepted only with explicit user evidence.

For a non-PASS report, save `docs/verification/phase-e-evidence-findings.json` and ingest it only into the **next** evidence revision:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$ledger=Get-Content -Raw -Encoding UTF8 docs/verification/unified-twin-acceptance-v1.json | ConvertFrom-Json
$verifiedCodeCommit=[string]$ledger.plans.E.verifiedCodeCommit
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$evidenceCommit=Get-ExactGitHead
& $python scripts/verify_unified_acceptance.py ingest-evidence-review --ledger docs/verification/unified-twin-acceptance-v1.json --review-report docs/verification/phase-e-evidence-findings.json --verified-code-commit $verifiedCodeCommit --evidence-commit $evidenceCommit
if ($LASTEXITCODE -ne 0) { throw 'evidence review ingestion failed' }
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
if ($LASTEXITCODE -ne 0) { throw 'evidence-review ledger rendering failed' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'evidence-review ledger verification failed' }
. "$PWD\scripts\verify_git_commit_boundary.ps1"
$nextEvidenceCommit=Invoke-ExactGitCommit -ExpectedParent $evidenceCommit -Paths @(
  'docs/verification/phase-e-evidence-findings.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) -Message 'docs: record independent evidence review'
```

The command preserves code SHA/verdict and records only the reviewed evidence commit. `$nextEvidenceCommit` is frozen and re-reviewed. Evidence corrections beyond the three paths above require a separately enumerated exact subset of the already closed evidence allowlist and another helper-guarded direct-parent commit; a later `fixed` evidence review repeats the mechanism. Any executable/code/config change abandons this loop and returns to E5/E6/E7 with a new code commit and fresh applicable approvals. The final PASS is delivered externally and is not self-ingested.

- [ ] **Step 9: Handoff without another repository mutation**

Handoff records `verifiedCodeCommit`, final `$evidenceCommit`, reviewer verdict, protected preview deployment ID/URL, final typed Deployment Protection method/scope/exception digest with `previewUrlExcepted=false`, exact batch/source/history/assessment/artifact/report/config identities and counts, `$phaseBEvidenceCommit`, AC15 result digest, human harness/result/assessment digests and remaining limitations. State what is live in preview, what remains unvalidated, that Deployment Protection stayed enabled, and that production migration/stage/assessment/activation/deploy each require new independent authorization. Any repository mutation after review creates a new evidence commit and requires re-review; there is no trailing “record the review” commit.
