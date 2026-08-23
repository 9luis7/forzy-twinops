# Forzy TwinOps Decision-Oriented Timeline UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar a aplicação TwinOps em um dashboard orientado a decisões que alterna atomicamente entre o snapshot live e um contexto histórico real, apresenta situação, confiança, evidência e próximo check antes da telemetria detalhada, e oferece timeline, candidatos, ciclos e twin 3D sem alegações causais não sustentadas.

**Architecture:** O frontend manterá um único bundle confirmado `{ displayContext, decisionSupport }`, produzido e validado por completo antes de um único commit do reducer para `now` ou `historical`; nenhum render recebe contexto novo com decisão antiga. Contratos JS validarão toda resposta da timeline antes do estado, os adaptadores apenas projetarão os fatos versionados e backend-owned de A/B, e o ruleset JSON versionado produzirá `OperationalDecisionViewV1` e todo o copy operacional. Uma regra separada ordenará apenas candidatos comparáveis. Requests live, overview, contexto e amostras terão ownership/abort independentes para impedir mistura temporal.

**Tech Stack:** React 18.3.1, JavaScript ES modules/JSDoc, Vite 5.4, Vitest 2.1, Testing Library 16, Recharts 2.12, Playwright 1.47, Web Crypto SHA-256, React Three Fiber 8.17.

**Spec:** `docs/superpowers/specs/2026-08-22-unified-history-interactive-twin-design.md`

## Global Constraints

- O commit `4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e` é apenas a base de planejamento. A execução começa no SHA que já integra o bootstrap da Task 1 do plano E e os contratos revisados de A/B; interromper se o spec hash, o ledger ou qualquer contrato compartilhado divergir.
- O snapshot continua significando **Agora**; timeline e contexto histórico são leituras GET carregadas sob demanda e não reativam `capabilities.replayControls`.
- A tela inicia em `now`; selecionar ponto/candidato/ciclo só troca todos os painéis para `historical` depois que `TimelineContextV1`, `DisplayContextV1` e `OperationalDecisionViewV1` forem construídos, validados, tiverem hash correspondente e forem confirmados em uma única ação. A volta a `now` segue a mesma regra.
- Refresh live em background nunca move o cursor nem substitui valores históricos; durante inspeção histórica apenas sinaliza “Novo dado disponível”.
- O contexto por cursor aceita exatamente `pointId`, ou `at + segmentId`; o frontend nunca escolhe o “mais próximo” e nunca resolve contexto usando pontos reduzidos.
- `from` é inclusivo, `to` é exclusivo; overview usa tempo proporcional real e toda lacuna permanece explícita.
- Todo timestamp público da timeline é uma string UTC canônica representável por JavaScript com precisão exata de milissegundos (`YYYY-MM-DDTHH:mm:ss.sssZ`). Valores com fração mais precisa, datas normalizadas silenciosamente ou instantes fora do intervalo de `Date` falham fechados; o sucessor exclusivo de um instante inclusivo soma exatamente 1 ms.
- `assessment.recommendation` livre nunca aparece na UI, no clipboard ou no export.
- `anomalyScore` e `deteriorationScore` nunca são urgência, percentual, probabilidade de falha, criticidade ou chave de ordenação; se exibidos em detalhe, vêm junto de semântica, baseline e limitações.
- Condição do ativo, escopo temporal, disponibilidade, frescura e confiança dos dados são dimensões independentes; erro de upstream/banco jamais produz `alert` de condição.
- Somente `now + received_now + alert + complete + fresh + sufficient` permite `escalate_engineering_review`; histórico, stale, last-known, expected-idle, partial ou degraded nunca permitem escalonamento atual.
- A fila declara `candidateRankingVersion: forzy-review-priority-v1` e nunca mistura live/archive, lotes históricos, famílias ou versões de modelo.
- Textos, checks e limitações vêm apenas do ruleset allowlisted `forzy-operational-triage-v1`; combinações não enumeradas falham fechadas.
- Componentes renderizam diretamente o bundle canônico validado do ruleset; mapas locais podem mapear somente estrutura/apresentação e nunca duplicam frases operacionais.
- S1/S2 não possuem posição física validada; selecionar motor, bomba, acoplamento ou base no 3D não atribui desvio ao grupo.
- Em 1366×768, ativo, modo, confiança, última observação, persistência, evidência dominante, resumo e próximo check devem aparecer sem scroll. Persistência/evidência ausentes aparecem como indisponibilidade explícita no mesmo viewport; o twin 3D fica abaixo de decisão, sensores, investigação temporal e avaliação.
- A UI usa controles HTML, foco visível, teclado e texto/padrões além de cor; a timeline oferece tabela visível alternativa.
- Nenhum teste E2E read-only envia POST refresh. O POST existente só permanece nos testes opt-in do stub explicitamente autorizado.
- Não adicionar mock, dado sintético ou asset fictício ao runtime; fixtures determinísticas existem somente em testes.
- Reutilizar sem editar `contracts/timeline/v1/**`, `src/contracts/timelineV1.js`, `src/contracts/timelineV1.test.js` e `src/contracts/schemaTimelineV1.test.js`, entregues pelo plano Foundation; este plano só adiciona fixtures UI ao namespace Foundation.
- Reutilizar sem editar `src/components/Twin3D.jsx`, `src/components/Twin3D.test.jsx` e `src/components/twin3d/**`, pertencentes exclusivamente ao plano D; a integração ocorre somente pelo seam público injetado em `App`/`OperationsDashboard`.
- O fallback context-aware é único e pertence ao plano D. Este plano não importa, instancia nem injeta `TwinFallback`/`fallback`; apenas verifica o seam de cinco props e o marcador público `data-twin-fallback="true"`.
- `playwright.config.js`, escolha do Chromium, argumentos do `webServer` e healthcheck pertencem ao plano E. O navegador autorizado é exclusivamente o Chromium bundled da versão pinada no lockfile; `channel: "chrome"` ou fallback para navegador do sistema são proibidos.

---

## File Structure

### Shared contract and decision files

- Create `contracts/v2/rulesets/forzy-operational-triage-v1.json`: matriz fechada, copy pt-BR, ordem de checks e limitações.
- Create `contracts/v2/rulesets/fixtures/b-live-display-context-v1-cases.json`: corpus C-owned de `DisplayContextV1` completos, literal e 1:1 com todos os case IDs B; nenhum default/base spread.
- Create `contracts/v2/rulesets/forzy-review-priority-v1.json`: escopo comparável e desempates do ranking.
- Reuse `contracts/timeline/v1/**`: schemas e fixtures-base canônicos entregues pelo plano Foundation.
- Reuse unchanged `contracts/timeline/v1/fixtures/live-decision-facts-v1-cases.json`: matriz compartilhada produzida por B; C importa `expectedDecisionFacts` literalmente e nunca reimplementa os descritores/evidências do projetor.
- Reuse `src/contracts/timelineV1.js`, `src/contracts/timelineV1.test.js`, and `src/contracts/schemaTimelineV1.test.js`: validadores e matrizes já entregues; nunca modificar ou stagear neste plano.
- Create `contracts/timeline/v1/fixtures/timeline-overview-mixed.valid.json`: fixture UI adicional com archive, gap, live, redução, ciclos e candidatos.
- Create `contracts/timeline/v1/fixtures/timeline-overview-single-point.valid.json`: fixture UI adicional de um ponto visível.
- Create `contracts/timeline/v1/fixtures/timeline-context-live-normal.valid.json`: fixture UI adicional de contexto live confiável.
- Create `contracts/timeline/v1/fixtures/timeline-context-historical-candidate.valid.json`: fixture UI adicional walk-forward retrospectiva.
- Create `contracts/timeline/v1/fixtures/timeline-context-gap.valid.json`: fixture UI adicional sem carry-forward.
- Create `src/contracts/operationalDecisionV1.js`: validador fechado do resumo operacional.
- Create `src/contracts/operationalDecisionV1.test.js`: enums, campos extras, hashes e ordenação allowlisted.
- Create in Task C1 `src/displayContext/displayContextV1.js`: `DISPLAY_CONTEXT_V1_FIELDS`, fechamento recursivo, `assertDisplayContextV1` e `cloneAndFreezeDisplayContextV1`; Task C5 modifica o mesmo módulo apenas para acrescentar adaptadores.
- Create in Task C1 `src/displayContext/displayContextV1.test.js`: shape/invariantes compartilhados com D; Task C5 estende o mesmo teste com casos dos adaptadores.
- Create in Task C1 `src/displayContext/displayContextV1.fixtures.js`: fixtures completas, congeladas e exclusivas de teste consumidas por C/D; nenhum import de runtime.

### State and deterministic decision files

- Create `src/decisionSupport/canonicalJson.js`: serialização canônica e SHA-256 assíncrono.
- Create `src/decisionSupport/operationalDecisionV1.js`: matcher único do ruleset e montagem de `OperationalDecisionViewV1`.
- Create `src/decisionSupport/candidateRankingV1.js`: builder de grupos comparáveis por fonte/batch/sensor/fold/modelo, filtragem por escopo e ranking determinístico.
- Create `src/decisionSupport/evidenceSummaryV1.js`: export sanitizado e allowlisted.
- Create matching `*.test.js` beside each module.
- Create `src/time/canonicalUtcMillis.js` and `.test.js`: parser/comparador UTC canônico e sucessor público de 1 ms.
- Modify after checkpoint C1 `src/displayContext/displayContextV1.js`: acrescentar adaptadores live/historical sem redefinir o shape/validator congelado.
- Modify after checkpoint C1 `src/displayContext/displayContextV1.test.js`: acrescentar invariantes temporais, ausência, qualidade e recomendação livre.
- Create `src/state/twinOpsReducer.js`: transições puras, commit atômico do bundle de apresentação e paginação.
- Create `src/state/twinOpsReducer.test.js`: corridas, observação de todos os renders, refresh background, return-to-now e seleção.

### Data access and provider files

- Modify `src/dataSources/GatewayTwinDataSourceV2.js:1-84`: adicionar GETs de overview, samples e context com query estrita.
- Modify `src/dataSources/GatewayTwinDataSourceV2.test.js:1-end`: URL, limites, seletores XOR, AbortSignal e validação de resposta.
- Modify `src/TwinOpsContext.jsx:1-245`: usar reducer, requests independentes e construir `displayContext` + decisão assíncrona antes do commit único.
- Modify `src/TwinOpsContext.test.jsx:1-342`: provar ownership, atomicidade e ações públicas.

### Decision-first UI files

- Create `src/components/operations/DecisionSummary.jsx` and `.test.jsx`: primeira dobra, confiança, escopo e next checks renderizados do bundle canônico do ruleset.
- Create `src/components/operations/DataReliabilityPanel.jsx` and `.test.jsx`: substituir linguagem de integração por fatos de confiabilidade.
- Create `src/components/operations/EvidenceExportButton.jsx` and `.test.jsx`: clipboard/download do resumo puro.
- Modify `src/components/operations/AssetHeader.jsx:1-end`: modo, instante da condição e instante da decisão.
- Modify `src/components/operations/SensorCard.jsx:1-end`: valor/unidade/contexto/baseline/desvio/direção/persistência/flags.
- Modify `src/components/operations/AssessmentPanel.jsx:1-end`: evidência e limitações antes de scores secundários.
- Modify `src/components/operations/OperationsPanels.test.jsx:1-142`: novos contratos visuais e proibições.

### Timeline files

- Create `src/components/timeline/timelineViewModel.js` and `.test.js`: separar séries por sensor/origem/segmento e preservar gaps.
- Create `src/components/timeline/TimelineWorkspace.jsx` and `.test.jsx`: composição e estados de loading/error/empty.
- Create `src/components/timeline/TimelineControls.jsx`: presets, métrica, sensor, zoom e voltar para agora.
- Create `src/components/timeline/TimelineOverview.jsx`: calendário proporcional, bandas, gaps e candidatos.
- Create `src/components/timeline/TimelineDetailChart.jsx`: detalhe sincronizado e single-point marker.
- Create `src/components/timeline/CandidateQueue.jsx` and `.test.jsx`: prioridade relativa declarada.
- Create `src/components/timeline/OperatingCycleNavigator.jsx`: 204 ciclos vindos do contrato, nunca hardcoded.
- Create `src/components/timeline/TimelineDataTable.jsx` and `.test.jsx`: tabela paginada original.
- Create `src/components/timeline/EventEvidencePanel.jsx` and `.test.jsx`: fatos do candidato, início de episódio contratado e comparação causal permitida sem inferência.

### Integration, 3D seam, CSS and verification

- Modify `src/components/operations/OperationsDashboard.jsx:1-end`: ordem decisão-first e um único `displayContext`.
- Stop importing `src/components/operations/TelemetryTrend.jsx`; keep the file only until all compatibility tests have migrated, then delete it in the integration commit.
- Stop importing `src/components/operations/IntegrationHealth.jsx`; delete it when `DataReliabilityPanel` tests pass.
- Modify `src/App.jsx:1-end` and `src/App.test.jsx:1-176`: seam de `Twin3DComponent` baseado no contexto.
- Reuse `src/components/Twin3D.jsx`, `src/components/Twin3D.test.jsx`, and `src/components/twin3d/**`: implementação exclusiva do plano D; o UI plan não abre nem altera esses arquivos.
- Modify `src/styles.css:1-end`: primeira dobra compacta, padrões de fonte/gap, foco e responsividade.
- Reuse unchanged: `playwright.config.js`; remoção de `channel: "chrome"`, viewport, `webServer` e healthcheck são ownership exclusivo do plano E.
- Create `tests/e2e/operational-scenarios.spec.js` and `tests/e2e/operational-accessibility.spec.js`.
- Reuse unchanged: `tests/e2e/real-history-live.spec.js` and `tests/e2e/deployed-real.spec.js`; o plano E os substitui/estende e executa a matriz integrada.
- Create `docs/usability/operational-triage-usability-v1.md` and `docs/usability/operational-triage-usability-v1-result-template.md`.
- Create at the independent C1 checkpoint and cumulatively update at C11/final `docs/verification/phase-c-findings.json`; each exact report version is ingested before its evidence commit so finding lineage cannot disappear.
- Create before Task C3 `docs/verification/checkpoints/b-to-c-contract-handoff.json`: attestation closed over the exact reviewed Phase-B code/evidence SHAs, PASS report/ledger identities and raw-byte SHA-256 values of every B-owned contract/fixture consumed by C.
- Create after the independent C1 checkpoint review `docs/verification/checkpoints/c1-display-contract-handoff.json`; commit it separately from the reviewed C1 code SHA.
- Create after the independent C11 checkpoint review `docs/verification/checkpoints/c11-dashboard-integration-handoff.json`; commit it separately from the reviewed C11 code SHA.
- Create in Task C1 `scripts/phase_c_plan_gates.ps1`: PowerShell 5.1 checked-session bootstrap, native-exit guard, closed verdict validators and exact-index commit helper used by every C commit.
- Create in Task C1 `scripts/phase_c_evidence.py`: closed Python CLI for raw `git show` hashing/projections and atomic `phase-c-gate-manifest-v1` rendering; no `python -c` remains in this plan.
- Create in Task C1 `scripts/tests/phase_c_plan_gates.tests.ps1` and `scripts/tests/test_phase_c_evidence.py`: disposable-repository tests for empty/staged index enforcement, verdict shapes, raw-byte hashing, projections, path rejection and gate-manifest atomicity.
- Create after the final reviewed C code SHA `docs/verification/phase-c-gate-manifest.json`: durable automated-gate evidence bound to that exact code SHA and committed only in the final evidence commit.
- Modify generated SSoT: `docs/verification/unified-twin-acceptance-v1.json` and `docs/verification/unified-twin-acceptance-v1.md` only through `scripts/verify_unified_acceptance.py`.

## Execution Preconditions

All executable snippets in this plan run in Windows PowerShell 5.1. Task C1 first authors and tests `scripts/phase_c_plan_gates.ps1`; from that point, **every fresh shell and every checkpoint block** begins with this exact self-contained bootstrap before any native command:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
```

The dot-sourced helper itself executes `Set-StrictMode -Version Latest` and sets `$global:ErrorActionPreference='Stop'`, then exports exactly `Assert-PhaseCCheckedSession`, `Assert-NativeExit`, `Assert-FindingVerdictObject`, `Assert-ReviewVerdictArray`, `Assert-EmptyGitIndex`, `Assert-StagedPaths` and `Invoke-PhaseCExactCommit`. `Assert-PhaseCCheckedSession` proves strict-mode behavior with a private unbound-variable probe, proves the caller preference is `Stop`, and verifies all seven functions exist. `Assert-FindingVerdictObject` requires the exact object keys `critical,important,minor` and non-negative integer counts. `Assert-ReviewVerdictArray` requires exactly three non-negative integers ordered `[critical, important, minor]`; a string such as `"PASS"` is always invalid.

`Invoke-PhaseCExactCommit -Label <label> -Message <message> -Paths <repo-relative string[]>` performs this indivisible checked sequence: require a non-empty, unique, canonically sorted path allowlist; call `Assert-EmptyGitIndex`; run `git add -- $Paths` and immediately check exit `0`; call `Assert-StagedPaths`, which compares `git diff --cached --name-only --diff-filter=ACDMRTUXB` exactly to the allowlist and runs checked `git diff --cached --check`; then run `git commit -m $Message` and immediately check exit `0`. Directory paths, globs, pathspec magic and an already-populated index are rejected. No task calls raw `git add` or `git commit` outside this helper.

For any other output-producing native command, capture output first, assign `$nativeExit=$LASTEXITCODE` on the very next statement, call `Assert-NativeExit $nativeExit '<label>'`, and only then sort/parse/use the output. `rg` absence checks explicitly allow only exit `1`; green gates allow only `0`; an intentional RED test allows only Vitest exit `1` and must additionally match its declared missing behavior—an infrastructure/other exit remains blocking. Cmdlets that read/hash/parse evidence use `-LiteralPath`/`-ErrorAction Stop`. These rules apply equally to every compact `Checked Run:`/`Checked RED Run:` macro below. Every such macro begins by running the four-line bootstrap above in its checkpoint shell; no executor may rely on a function or `$LASTEXITCODE` inherited from an earlier shell.

`scripts/phase_c_evidence.py` uses `argparse`, rejects non-40-hex commits and absolute/empty/dot-segment paths, invokes Git only as argument arrays with `check=True`, reads stdout as raw bytes and emits canonical UTF-8 JSON (`sort_keys=True`, separators `(',', ':')`). It exposes only these subcommands:

```text
hash-paths --commit SHA --paths PATH [PATH ...]
b-evidence-projection --commit SHA
checkpoint-projection --commit SHA --handoff-path PATH
final-ledger-projection --commit SHA --criteria ID [ID ...]
write-gate-manifest --output PATH --verified-code-commit SHA
  --phase-b-code-commit SHA --phase-b-evidence-commit SHA --b-to-c-handoff-commit SHA
  --vitest-exit 0 --build-exit 0 --playwright-list-exit 0 --ownership-scan-exit 1
validate-gate-manifest --path PATH [--commit SHA] --verified-code-commit SHA
  --phase-b-code-commit SHA --phase-b-evidence-commit SHA --b-to-c-handoff-commit SHA
```

The manifest writer uses temp-file + flush + `fsync` + `os.replace`, reparses the bytes and refuses any exit tuple other than `0,0,0,1`. Its root is exactly `{schemaVersion,plan,verifiedCodeCommit,phaseB,commands,gates}`; `schemaVersion="phase-c-gate-manifest-v1"`, `plan="C"`; `phaseB` is exactly `{phaseBCodeCommit,phaseBEvidenceCommit,bToCContractHandoffCommit}`; `commands` is exactly `{fullVitest,productionBuild,playwrightDiscovery,prohibitedOwnershipScan}` with the exact argv arrays; and `gates` is exactly `{bToCAuthentication,fullVitest,productionBuild,playwrightDiscovery,prohibitedOwnershipScan}`, each value exactly `{passed,exitCode}`. Every gate has `passed=true`; exit codes are respectively `0,0,0,0,1`. The validator rechecks every key/value/command and exact SHA binding; with `--commit`, it reads `COMMIT:PATH` as raw `git show` bytes rather than the working tree. `checkpoint-projection` reads the committed checkpoint handoff, cumulative review and ledger with raw `git show` and returns `handoffHash`, `reviewHash` and `ledgerHash` as `sha256:<lowercase-hex>` plus parsed objects. The final projection likewise reads the committed manifest, ledger and review with raw `git show`, returns `gateManifestHash`, `reviewHash` and `ledgerHash` plus parsed objects, and never accepts working-tree substitutes.

- A Task 1 do plano E deve ter criado e commitado `docs/verification/unified-twin-acceptance-v1.json`, seu Markdown gerado e `scripts/verify_unified_acceptance.py` antes da fase A; este plano reutiliza esses arquivos e nunca cria um ledger paralelo. Cada critério já declara `ownerPlan`, `gate` e `allowedEvidenceKinds`; C não altera esse ownership nem inventa evidence kind. Em particular, AC-15 deve permanecer `ownerPlan="E"`, `status="pending"` durante C: C só autora seus testes/locators.
- The Foundation plan must have committed `contracts/timeline/v1/**`, `src/contracts/timelineV1.js`, `src/contracts/timelineV1.test.js`, and `src/contracts/schemaTimelineV1.test.js`; verify those tests pass before Task 1 and do not include them in any UI-plan commit.
- Before C3, the controller must map Phase B's externally frozen values to `PHASE_B_VERIFIED_CODE_COMMIT` and `PHASE_B_EVIDENCE_COMMIT`. C authenticates both SHAs, the strict PASS report, ledger, ancestry/evidence-only scope, and raw `git show` SHA-256 for its consumed contract set into `b-to-c-contract-handoff.json`. C5 and the final C review reperform the same checks; neither a branch name, current HEAD, working-tree-only file nor hash supplied without the two commits is trusted.
- Task C1 must commit and independently review the closed `DisplayContextV1` field list/validator and the separate `OperationalDecisionViewV1` validator before D consumes the interface. Its checkpoint handoff carries the exact reviewed code SHA in `C1_DISPLAY_CONTRACT_COMMIT`, a separate evidence-commit SHA and verdict `0 Critical / 0 Important`; Task C5 may add adapter functions to the same display-context module but cannot alter the frozen root shape or make B produce the UI decision.
- The plan D must publish the five-prop public contract `Twin3DComponent({ displayContext, selectedGroup, onSelectGroup, selectedSensor, onSelectSensor })` and its internal context-aware fallback before Task 11; Task 11 adapts only `App.jsx`, its mocks, and `OperationsDashboard.jsx` to that contract.
- Task C11 starts only from a HEAD containing the exact tested `D7_PUBLIC_SEAM_COMMIT`, then commits and independently reviews the dashboard integration. Its checkpoint handoff carries the exact reviewed code SHA in `C11_DASHBOARD_INTEGRATION_COMMIT` plus a separate evidence-commit SHA before D8 starts. C1 and C11 each call only `ingest-review` on the same cumulative C report, immediately render/verify, and assert plan C remains `in_progress` with every criterion pending; only final Task 12 may call `update-criterion`, after carrying all C1/C11 finding IDs and dispositions forward.
- The backend timeline plan must expose these exact read-only methods before Tasks 8-12 integrate against a real server:

```text
GET /api/v2/assets/{assetId}/timeline
GET /api/v2/assets/{assetId}/timeline/samples
GET /api/v2/assets/{assetId}/timeline/context
```

- `TimelineOverviewV1` must provide exactly `requestedRange`, nullable `effectiveRange`, nullable `availableRange`, `aggregationSummary`, `segments`, `gaps`, `operatingCycles`, `series`, `eventCandidates` and `capabilities`; aliases `from/to` ou `aggregation` no root são inválidos.
- `TimelineContextV1` must provide an original `anchor`, paired nullable `channels.s1/s2`, causal `assessment`, nested `decisionFacts`, provenance, capabilities and limitations. The frontend copies the backend dimensions literally and never derives freshness, collection expectation or trust from clock/presence.
- O snapshot v2 entregue por B deve conter a projeção live versionada `decisionFacts: TimelineDecisionFactsV1` com `schemaVersion: "1.0"`, incluindo `conditionEpisodeStartedAt`; contexto histórico usa o mesmo objeto fechado. Ambos os adaptadores validam/copiam essa versão literalmente e não aplicam policy, cadence, freshness, expectation ou trust no browser.
- Tasks C1-C2 can run against the Foundation contracts while backend work proceeds. C3 stops for the authenticated final B handoff; C3-C12 require the recorded B contract/fixture hashes to remain unchanged. Task 12 authors C-owned specs, while their execução em Chromium e toda integração real/deployed pertencem ao plano E.

---

### Task 1: C1 Closed Display Context, Timeline UI Fixtures and Decision Contract

**Files:**
- Reuse unchanged: `contracts/timeline/v1/**`
- Reuse unchanged: `src/contracts/timelineV1.js`
- Reuse unchanged: `src/contracts/timelineV1.test.js`
- Reuse unchanged: `src/contracts/schemaTimelineV1.test.js`
- Create: `contracts/timeline/v1/fixtures/timeline-overview-mixed.valid.json`
- Create: `contracts/timeline/v1/fixtures/timeline-overview-single-point.valid.json`
- Create: `contracts/timeline/v1/fixtures/timeline-context-live-normal.valid.json`
- Create: `contracts/timeline/v1/fixtures/timeline-context-historical-candidate.valid.json`
- Create: `contracts/timeline/v1/fixtures/timeline-context-gap.valid.json`
- Create: `src/displayContext/displayContextV1.js`
- Create: `src/displayContext/displayContextV1.test.js`
- Create: `src/displayContext/displayContextV1.fixtures.js`: objetos completos, imutáveis e exclusivos de teste, exportados para o plano D; nunca importados pelo runtime.
- Create: `src/contracts/operationalDecisionV1.js`
- Create: `src/contracts/operationalDecisionV1.test.js`
- Create: `scripts/phase_c_plan_gates.ps1`
- Create: `scripts/phase_c_evidence.py`
- Create: `scripts/tests/phase_c_plan_gates.tests.ps1`
- Create: `scripts/tests/test_phase_c_evidence.py`
- Create from independent review: `docs/verification/phase-c-findings.json` (cumulative C report reused at C11 and final review)
- Create after review: `docs/verification/checkpoints/c1-display-contract-handoff.json`
- Modify through verifier only: `docs/verification/unified-twin-acceptance-v1.json`
- Regenerate through verifier only: `docs/verification/unified-twin-acceptance-v1.md`

**Interfaces:**
- Consumes: Foundation exports `assertTimelineOverviewV1(value)`, `assertTimelinePageV1(value)`, and `assertTimelineContextV1(value)` without modifying their implementation or tests.
- Produces: the two closed Phase-C execution helpers and their tests; the frozen root field list `DISPLAY_CONTEXT_V1_FIELDS`, identity validator `assertDisplayContextV1(value)`, fresh-copy boundary `cloneAndFreezeDisplayContextV1(value)`, the matching-only allowlist `toOperationalDecisionInput(displayContext)`, five additional contract-valid timeline fixtures, complete test-only exports `nowDisplayContextV1Fixture`, `historicalDisplayContextV1Fixture`, `historicalGapDisplayContextV1Fixture` and aggregate `DISPLAY_CONTEXT_V1_FIXTURES`, plus `assertOperationalDecisionViewV1(value)`. Both validators return the original object or throw `TypeError` with a field path; the clone boundary validates, manually JSON-clones and recursively freezes without retaining caller-owned references. This is checkpoint **C1** consumed by D; B produces only `TimelineDecisionFactsV1` and never produces either `DisplayContextV1` or the separate UI-owned `OperationalDecisionViewV1`.

- [ ] **Step 0: Author and test the closed Phase-C execution helpers**

Implement `scripts/phase_c_plan_gates.ps1` and `scripts/phase_c_evidence.py` exactly to the Execution Preconditions interfaces before running any later Phase-C native command. The PowerShell test creates a disposable Git repository, proves an empty index passes, a pre-staged path is rejected, an exact add/delete allowlist passes, an omitted/extra path fails, cached whitespace errors fail, path directories/globs fail, native exits outside the allowed set fail, finding verdict objects reject extra/missing/string counts, and ledger verdict arrays reject `"PASS"`, wrong order/length and negative/string counts. It removes only its resolved disposable directory in `finally` after proving that path is under `[System.IO.Path]::GetTempPath()`.

The Python unittest creates its own disposable repository and proves `hash-paths` hashes raw bytes including CRLF/non-ASCII/NUL, single and multiple paths stay arrays of individual argv values, absolute/traversal/duplicate paths and non-40-hex commits fail, the B/checkpoint/final projections reject missing/duplicate criteria and malformed JSON, manifest writing is atomic and canonical, working-tree and `--commit` validation reject every missing/extra key/command/SHA/exit mutation, `checkpoint-projection` returns raw digests plus the exact committed handoff/review/ledger objects, and `final-ledger-projection` returns raw digests plus the exact committed ledger/review/manifest objects.

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe" -ErrorAction Stop).Path
& $python -m unittest scripts.tests.test_phase_c_evidence
Assert-NativeExit $LASTEXITCODE 'Phase C Python evidence helper tests'
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File scripts/tests/phase_c_plan_gates.tests.ps1
Assert-NativeExit $LASTEXITCODE 'Phase C PowerShell gate helper tests'
```

Expected: both helper suites exit `0`; no test writes outside its resolved disposable repository.

- [ ] **Step 1: Write the failing UI-fixture and decision-contract tests**

```js
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { assertTimelineContextV1, assertTimelineOverviewV1 } from "./timelineV1.js";
import { assertOperationalDecisionViewV1 } from "./operationalDecisionV1.js";

const fixture = (name) => JSON.parse(readFileSync(
  new URL(`../../contracts/timeline/v1/fixtures/${name}`, import.meta.url),
  "utf8",
));

describe("additional timeline UI fixtures", () => {
  it("reuses the Foundation overview validator", () => {
    const value = fixture("timeline-overview-mixed.valid.json");
    expect(assertTimelineOverviewV1(value)).toBe(value);
    expect(Object.keys(value).sort()).toEqual([
      "activeHistoricalBatchId", "aggregationSummary", "assetId", "availableRange",
      "capabilities", "effectiveRange", "eventCandidates", "gaps",
      "operatingCycles", "queryFingerprint", "requestedRange", "schemaVersion",
      "segments", "series",
    ].sort());
    expect(value.requestedRange).toEqual({
      from: "2026-05-19T14:46:10.921Z",
      to: "2026-08-12T15:00:15.000Z",
    });
    expect(value.effectiveRange).toEqual({ from: expect.any(String), to: expect.any(String) });
    expect(value.availableRange).toEqual({ from: expect.any(String), to: expect.any(String) });
    expect(value).not.toHaveProperty("from");
    expect(value).not.toHaveProperty("to");
    expect(value).not.toHaveProperty("aggregation");
    expect(Object.keys(value.aggregationSummary).sort()).toEqual([
      "omittedPointCount", "originalPointCount", "reducedSeriesCount",
      "requestedMaxPoints", "returnedPointCount",
    ].sort());
    expect(value.aggregationSummary.originalPointCount)
      .toBeGreaterThan(value.aggregationSummary.returnedPointCount);
    expect(value.segments.map(({ sourceKind }) => sourceKind)).toEqual([
      "historical_archive", "live_collection",
    ]);
    expect(value.gaps[0].gapType).toBe("source_discontinuity");
    for (const series of value.series) {
      expect(Object.keys(series).sort()).toEqual([
        "aggregation", "metric", "points", "segmentId", "sensorId", "sourceKind",
      ].sort());
      expect(Object.keys(series.aggregation).sort()).toEqual([
        "method", "omittedPointCount", "originalPointCount",
        "requestedMaxPoints", "returnedPointCount",
      ].sort());
      expect(["none", "time_bucket_envelope_v1"]).toContain(series.aggregation.method);
      for (const point of series.points) {
        expect(Object.keys(point).sort()).toEqual(["eventAt", "pointId", "value"]);
        expect(point).not.toHaveProperty("provenance");
        expect(point).not.toHaveProperty("flags");
      }
    }
    expect(value.eventCandidates[0]).toMatchObject({
      schemaVersion: "1.0",
      anchorPointId: expect.any(String),
      modelFamily: expect.any(String),
      modelVersion: expect.any(String),
      candidateRankingVersion: "forzy-review-priority-v1",
    });
    expect(Object.keys(value.eventCandidates[0]).sort()).toEqual([
      "anchorPointId", "batchId", "candidateId", "candidateRankingVersion",
      "dataTrust", "eventAt", "foldId", "modelFamily", "modelVersion",
      "operatingCycleId", "persistenceCount", "quality", "schemaVersion", "episodeStartedAt",
      "sensorId", "sourceKind", "status",
    ].sort());
    expect(value.eventCandidates[0]).not.toHaveProperty("pointId");
    expect(value.operatingCycles[1]).toMatchObject({
      previousOperatingCycleId: value.operatingCycles[0].operatingCycleId,
      gapBeforeSeconds: expect.any(Number),
    });
    expect(Object.keys(value.operatingCycles[1]).sort()).toEqual([
      "assumptions", "batchId", "candidateCount", "durationSeconds", "endAt",
      "gapBeforeSeconds", "operatingCycleId", "previousOperatingCycleId",
      "sensorCounts", "sourceKind", "startAt", "totalPoints",
    ].sort());
  });

  it("reuses the Foundation context validator for gap and causal context", () => {
    const gap = fixture("timeline-context-gap.valid.json");
    expect(assertTimelineContextV1(gap)).toEqual(gap);
    expect(gap).toMatchObject({
      anchor: null,
      channels: { s1: null, s2: null },
      assessment: null,
      decisionFacts: {
        schemaVersion: "1.0", conditionTemporalScope: "none",
        conditionAsOf: null, conditionEpisodeStartedAt: null,
        conditionSource: "none", collectionState: "historical_gap",
        dataAvailability: "gap", dataFreshness: "historical",
      },
    });
    expect(assertTimelineContextV1(fixture("timeline-context-historical-candidate.valid.json")))
      .toEqual(fixture("timeline-context-historical-candidate.valid.json"));
    const selectedLive = fixture("timeline-context-live-normal.valid.json");
    expect(assertTimelineContextV1(selectedLive)).toEqual(selectedLive);
    expect(selectedLive).toMatchObject({
      anchor: { sourceKind: "live_collection" },
      decisionFacts: {
        conditionTemporalScope: "historical", conditionSource: "live_assessment",
        collectionState: "historical_context", collectionExpectation: "not_applicable",
        dataFreshness: "historical",
      },
    });
  });
});

it("rejects duplicate checks and historical current escalation", () => {
  const invalid = {
    ...validDecision,
    viewMode: "historical",
    nextCheckCodes: ["review_evidence", "review_evidence", "escalate_engineering_review"],
  };
  expect(() => assertOperationalDecisionViewV1(invalid)).toThrow(/nextCheckCodes/);
});
```

In `src/displayContext/displayContextV1.test.js`, freeze the independent C1 shape consumed by D:

```js
import { expect, it } from "vitest";
import {
  DISPLAY_CONTEXT_V1_FIELDS,
  assertDisplayContextV1,
  cloneAndFreezeDisplayContextV1,
} from "./displayContextV1.js";

it("freezes the closed C1 display context consumed by D", () => {
  const value = {
    schemaVersion: "1.0",
    viewMode: "now",
    decisionAsOf: "2026-08-12T15:00:15.000Z",
    decisionFactsSchemaVersion: "1.0",
    asset: {
      assetId: "forzy-motor-01",
      displayName: "Conjunto motor-bomba monitorado",
      officialTag: null,
    },
    channels: { s1: null, s2: null },
    assessment: null,
    conditionState: "unknown",
    conditionTemporalScope: "none",
    conditionAsOf: null,
    conditionEpisodeStartedAt: null,
    conditionSource: "none",
    collectionState: "unavailable",
    collectionExpectation: "not_applicable",
    dataAvailability: "unavailable",
    dataFreshness: "unknown",
    dataTrust: "insufficient",
    anchor: null,
    driverEvidenceIds: [],
    emphasizedSensorIds: [],
    exportableMeasurements: [],
    exportableEvidence: [],
    publicQualityFlags: [],
    publicProvenance: {
      pointSourceKind: null, pointSourceSystem: null, activeHistoricalBatchId: null,
      collectionPolicyId: null, assessmentSource: "none",
    },
    publicModel: null,
    publicAcquisition: {
      expectedCollectionNow: null, policyEvidenceKind: "missing", gapType: null,
      sensors: { s1: null, s2: null },
    },
    capabilities: {
      hasComparablePreviousCycle: false,
      hasSensorChainEvidence: false,
      hasDriverEvidence: false,
    },
  };
  expect(Object.keys(value).sort()).toEqual([...DISPLAY_CONTEXT_V1_FIELDS].sort());
  expect(Object.keys(value.asset).sort()).toEqual(["assetId", "displayName", "officialTag"]);
  expect(assertDisplayContextV1(value)).toBe(value);
  const immutableClone = cloneAndFreezeDisplayContextV1(value);
  expect(immutableClone).not.toBe(value);
  expect(immutableClone).toEqual(value);
  expect(Object.isFrozen(immutableClone.publicAcquisition.sensors)).toBe(true);
  expect(() => assertDisplayContextV1({ ...value, status: "alert" }))
    .toThrow(/displayContext\.status/);
  expect(() => assertDisplayContextV1({
    ...value,
    asset: { ...value.asset, assetId: "forzy-provisional-asset" },
  })).toThrow(/displayContext\.asset\.assetId/);
});
```

Create `src/displayContext/displayContextV1.fixtures.js` as a test-only module. It exports the exact frozen asset below and three **complete** `DisplayContextV1` root objects; each export contains every key in `DISPLAY_CONTEXT_V1_FIELDS`, the closed capabilities object and the exact asset object, rather than a partial object completed by a D-local spread:

```js
import receivedNowSnapshotFixture from "../../contracts/v2/fixtures/snapshot-received-now.valid.json";
import historicalCandidateContextFixture from "../../contracts/timeline/v1/fixtures/timeline-context-historical-candidate.valid.json";
import { cloneAndFreezeDisplayContextV1 } from "./displayContextV1.js";

export const displayContextV1AssetFixture = Object.freeze({
  assetId: "forzy-motor-01",
  displayName: "Conjunto motor-bomba monitorado",
  officialTag: null,
});

export const nowDisplayContextV1Fixture = cloneAndFreezeDisplayContextV1({
  schemaVersion: "1.0", viewMode: "now",
  decisionAsOf: receivedNowSnapshotFixture.generatedAt, decisionFactsSchemaVersion: "1.0",
  asset: displayContextV1AssetFixture,
  channels: {
    s1: projectDisplayChannelFixture({
      value: receivedNowSnapshotFixture.channels.find(({ sensorId }) => sensorId === "s1"),
      sourceKind: "live_collection", pointId: null, samplePairId: null,
      operatingCycleId: null, batchId: null,
    }),
    s2: null,
  },
  assessment: null,
  conditionState: "unknown", conditionTemporalScope: "none", conditionAsOf: null,
  conditionEpisodeStartedAt: null, conditionSource: "none", collectionState: "received_now",
  collectionExpectation: "expected_now", dataAvailability: "partial",
  dataFreshness: "fresh", dataTrust: "degraded", anchor: null,
  driverEvidenceIds: [], emphasizedSensorIds: [], exportableMeasurements: [],
  exportableEvidence: [], publicQualityFlags: [],
  publicProvenance: {
    pointSourceKind: "live_collection", pointSourceSystem: "forzy-api",
    activeHistoricalBatchId: null, collectionPolicyId: null, assessmentSource: "none",
  }, publicModel: null,
  publicAcquisition: {
    expectedCollectionNow: true, policyEvidenceKind: "valid", gapType: null,
    sensors: { s1: projectSensorHealthFixture(receivedNowSnapshotFixture.integration.sensors.s1), s2: null },
  }, capabilities: {
    hasComparablePreviousCycle: false, hasSensorChainEvidence: true, hasDriverEvidence: false,
  },
});

export const historicalDisplayContextV1Fixture = cloneAndFreezeDisplayContextV1({
  schemaVersion: "1.0", viewMode: "historical",
  decisionAsOf: historicalCandidateContextFixture.selectedAt,
  decisionFactsSchemaVersion: historicalCandidateContextFixture.decisionFacts.schemaVersion,
  asset: displayContextV1AssetFixture,
  channels: {
    s1: projectDisplayChannelFixture({ value: historicalCandidateContextFixture.channels.s1 }),
    s2: projectDisplayChannelFixture({ value: historicalCandidateContextFixture.channels.s2 }),
  },
  assessment: projectDisplayAssessmentFixture(historicalCandidateContextFixture.assessment),
  conditionState: historicalCandidateContextFixture.decisionFacts.conditionState,
  conditionTemporalScope: historicalCandidateContextFixture.decisionFacts.conditionTemporalScope,
  conditionAsOf: historicalCandidateContextFixture.decisionFacts.conditionAsOf,
  conditionEpisodeStartedAt: historicalCandidateContextFixture.decisionFacts.conditionEpisodeStartedAt,
  conditionSource: historicalCandidateContextFixture.decisionFacts.conditionSource,
  collectionState: historicalCandidateContextFixture.decisionFacts.collectionState,
  collectionExpectation: historicalCandidateContextFixture.decisionFacts.collectionExpectation,
  dataAvailability: historicalCandidateContextFixture.decisionFacts.dataAvailability,
  dataFreshness: historicalCandidateContextFixture.decisionFacts.dataFreshness,
  dataTrust: historicalCandidateContextFixture.decisionFacts.dataTrust,
  anchor: projectDisplayAnchorFixture(historicalCandidateContextFixture.anchor),
  driverEvidenceIds: ["evidence-s1-velocity"], emphasizedSensorIds: ["s1"],
  exportableMeasurements: projectMeasurementExportsFixture(historicalCandidateContextFixture),
  exportableEvidence: projectEvidenceExportsFixture(historicalCandidateContextFixture.assessment),
  publicQualityFlags: [], publicProvenance: {
    pointSourceKind: "historical_archive", pointSourceSystem: "forzy-csv",
    activeHistoricalBatchId: historicalCandidateContextFixture.provenance.activeHistoricalBatchId,
    collectionPolicyId: null, assessmentSource: "historical_walk_forward",
  },
  publicModel: projectPublicModelFixture(historicalCandidateContextFixture.assessment),
  publicAcquisition: {
    expectedCollectionNow: null, policyEvidenceKind: "not_applicable", gapType: null,
    sensors: { s1: null, s2: null },
  },
  capabilities: {
    hasComparablePreviousCycle: true, hasSensorChainEvidence: true, hasDriverEvidence: true,
  },
});

export const historicalGapDisplayContextV1Fixture = cloneAndFreezeDisplayContextV1({
  schemaVersion: "1.0", viewMode: "historical",
  decisionAsOf: "2026-06-01T00:00:00.000Z", decisionFactsSchemaVersion: "1.0",
  asset: displayContextV1AssetFixture, channels: { s1: null, s2: null }, assessment: null,
  conditionState: "unknown", conditionTemporalScope: "none", conditionAsOf: null,
  conditionEpisodeStartedAt: null, conditionSource: "none", collectionState: "historical_gap",
  collectionExpectation: "not_applicable", dataAvailability: "gap",
  dataFreshness: "historical", dataTrust: "insufficient", anchor: null,
  driverEvidenceIds: [], emphasizedSensorIds: [], exportableMeasurements: [],
  exportableEvidence: [], publicQualityFlags: [],
  publicProvenance: {
    pointSourceKind: null, pointSourceSystem: null,
    activeHistoricalBatchId: historicalCandidateContextFixture.provenance.activeHistoricalBatchId,
    collectionPolicyId: null, assessmentSource: "none",
  }, publicModel: null, publicAcquisition: {
    expectedCollectionNow: null, policyEvidenceKind: "not_applicable",
    gapType: "source_discontinuity", sensors: { s1: null, s2: null },
  },
  capabilities: {
    hasComparablePreviousCycle: false, hasSensorChainEvidence: false, hasDriverEvidence: false,
  },
});

export const DISPLAY_CONTEXT_V1_FIXTURES = Object.freeze({
  nowZero: nowDisplayContextV1Fixture,
  historicalAlert: historicalDisplayContextV1Fixture,
  historicalGap: historicalGapDisplayContextV1Fixture,
});
```

The seven `project*Fixture` helpers above are private, test-only **literal allowlist projectors** whose returned key sets are exactly the recursive C1 shapes below; none uses object spread, `structuredClone`, a producer-policy hydrator or a fallback value. Every nullable source field is supplied explicitly by its call. Each exported root passes through `cloneAndFreezeDisplayContextV1`, so it is a fresh recursively frozen clone and cannot freeze/mutate the imported canonical JSON modules. The referenced snapshot and timeline-context fixtures have already passed their owning validators; the display fixture test additionally requires the live S1 acceleration value to remain exact `0`, the historical S1 velocity value to remain exact `9.25`, and the historical facts to remain `alert/historical/historical_walk_forward`. `displayContextV1.test.js` imports all three named exports plus `DISPLAY_CONTEXT_V1_FIXTURES`, asserts the aggregate has exactly `nowZero`, `historicalAlert`, `historicalGap`, asserts every object's root and recursive key set, calls `assertDisplayContextV1` on each and proves mutation throws. Plan D imports only this aggregate in tests instead of owning partial `displayContext` literals.

Extend this C1 test file with exact `now`, `historical_context`, `historical_gap`, unknown-policy `last_known/not_applicable/unknown` and unknown-policy `unavailable/not_applicable/unknown` values. Assert missing/extra keys independently at **every** recursive shape above; incomplete/extra/wrong-valued asset fields; noncanonical times; crossed scope/source/times; future episode start; gap carry-forward; `not_applicable+fresh|stale`; and `not_applicable+received_now|expected_idle` are rejected with the first offending field path. Add adversarial cases for nested `raw`, `payload`, `dsn`, `authorization`, `apiKey`, `__proto__` and symbol keys; accessor/non-enumerable properties; `undefined`, function, symbol and bigint values; `NaN`, both infinities and `-0`; sparse/extended arrays; `Date`, `Map`, `Set`, typed array, class instance and a direct plus indirect cycle. Prove a repeated acyclic child remains valid, `assertDisplayContextV1` retains identity, and `cloneAndFreezeDisplayContextV1` returns a distinct deeply frozen tree unaffected by subsequent mutation of the caller's nested channel/assessment/acquisition values. Add focused invariant failures for every availability/channel cardinality, assessment/condition/episode crossing, anchor/pair/source/batch crossing, unresolved measurement/evidence/driver IDs and each false/true capability mismatch. These are validator tests over literal contexts, not adapter tests and not a second B decision-fact implementation.

- [ ] **Step 2: Run tests to verify RED while Foundation stays GREEN**

Checked RED Run: capture output from `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/contracts/timelineV1.test.js src/contracts/schemaTimelineV1.test.js src/displayContext/displayContextV1.test.js src/contracts/operationalDecisionV1.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C1 expected-red contract tests' @(1)`, then require the captured failure to name only the not-yet-created C1 fixtures/exports.

Expected: Foundation timeline tests PASS; the command exits nonzero because the additional fixtures and both C1 validator module exports do not exist yet.

- [ ] **Step 3: Add only the five additional UI fixtures under the Foundation namespace**

Use these authoring constants while conforming exactly to the already-delivered TimelineV1 schemas; these labels are test-construction notes and are **not** serialized as extra fixture properties:

```text
ASSET_ID=forzy-motor-01
HISTORICAL_FROM=2026-05-19T14:46:10.921Z
HISTORICAL_TO=2026-05-19T15:30:00.000Z
LIVE_FROM=2026-08-12T15:00:00.000Z
LIVE_TO=2026-08-12T15:00:15.000Z
SOURCE_GAP_TYPE=source_discontinuity
SERIES_AGGREGATION_METHOD=time_bucket_envelope_v1
CANDIDATE_RANKING_VERSION=forzy-review-priority-v1
```

The mixed overview contains the literal root fields from A/B: caller bounds in `requestedRange`, the actual non-null `[from,to)` in `effectiveRange`, all-source coverage in `availableRange` (including A/B's exact one-millisecond UTC successor for the latest original point), and `aggregationSummary` with `originalPointCount > returnedPointCount`. It contains two non-overlapping segments, one explicit open gap, one `alert` historical event candidate anchored by `anchorPointId` (never `pointId`), with closed `modelFamily` + `modelVersion` and contracted `episodeStartedAt`, plus two operating cycles linked only by nullable `previousOperatingCycleId` and nullable `gapBeforeSeconds`. Put two candidate fixtures at the same millisecond and retain a terminal original point plus candidate exactly at an inclusive cycle `endAt`; their cycle query must include both by ending at `addOneMillisecondUtc(endAt)`. Every reduced-series point contains exactly `{pointId,eventAt,value}`. The single-point overview contains exactly one original/returned S1 point, per-series `aggregation.method: "none"`, and root aggregation totals that remain internally consistent. `timeline-context-historical-candidate.valid.json` contains a causally valid `alert` archive context whose S1 `vibrationVelocityRms.value` is exactly `9.25`; the existing received-now snapshot fixture supplies exact live acceleration `0`. These are deliberate test values consumed by `DISPLAY_CONTEXT_V1_FIXTURES`, not simulated runtime data. The gap context uses the exact Foundation gap representation, including `gapType`, null anchor/channels/assessment and no carry-forward fields; do not add UI-only properties forbidden by the schema.

- [ ] **Step 4: Implement the two closed C1 validators**

Create `src/displayContext/displayContextV1.js` with the complete root shape before any adapter exists:

```js
export const DISPLAY_CONTEXT_V1_FIELDS = Object.freeze([
  "schemaVersion", "viewMode", "decisionAsOf", "decisionFactsSchemaVersion",
  "asset", "channels", "assessment", "conditionState", "conditionTemporalScope",
  "conditionAsOf", "conditionEpisodeStartedAt", "conditionSource", "collectionState",
  "collectionExpectation", "dataAvailability", "dataFreshness", "dataTrust", "anchor",
  "driverEvidenceIds", "emphasizedSensorIds", "exportableMeasurements",
  "exportableEvidence", "publicQualityFlags", "publicProvenance", "publicModel",
  "publicAcquisition", "capabilities",
]);

const UTC_MILLIS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const ENUMS = Object.freeze({
  viewMode: ["now", "historical"],
  conditionState: ["normal", "watch", "alert", "insufficient_data", "unknown"],
  conditionTemporalScope: ["current", "last_known", "historical", "none"],
  conditionSource: ["live_assessment", "historical_walk_forward", "none"],
  collectionState: ["received_now", "last_known", "expected_idle", "unavailable", "historical_context", "historical_gap"],
  collectionExpectation: ["expected_now", "expected_idle", "not_applicable"],
  dataAvailability: ["complete", "partial", "gap", "unavailable"],
  dataFreshness: ["fresh", "stale", "historical", "unknown"],
  dataTrust: ["sufficient", "degraded", "insufficient"],
});
const CAPABILITY_FIELDS = Object.freeze([
  "hasComparablePreviousCycle", "hasSensorChainEvidence", "hasDriverEvidence",
]);

export function assertDisplayContextV1(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError("displayContext must be an object");
  }
  const extras = Object.keys(value).filter((key) => !DISPLAY_CONTEXT_V1_FIELDS.includes(key));
  const missing = DISPLAY_CONTEXT_V1_FIELDS.filter((key) => !Object.hasOwn(value, key));
  if (extras.length) throw new TypeError(`displayContext.${extras[0]} is not allowed`);
  if (missing.length) throw new TypeError(`displayContext.${missing[0]} is required`);
  if (value.schemaVersion !== "1.0" || value.decisionFactsSchemaVersion !== "1.0") {
    throw new TypeError("displayContext schema versions must be 1.0");
  }
  if (!UTC_MILLIS.test(value.decisionAsOf)) throw new TypeError("displayContext.decisionAsOf must be canonical UTC milliseconds");
  for (const [key, allowed] of Object.entries(ENUMS)) {
    if (!allowed.includes(value[key])) throw new TypeError(`displayContext.${key} is invalid`);
  }
  const isRecord = (candidate) => candidate !== null && typeof candidate === "object" && !Array.isArray(candidate);
  if (!isRecord(value.asset)) throw new TypeError("displayContext.asset must be an object");
  const assetFields = ["assetId", "displayName", "officialTag"];
  const extraAssetFields = Object.keys(value.asset).filter((key) => !assetFields.includes(key));
  const missingAssetFields = assetFields.filter((key) => !Object.hasOwn(value.asset, key));
  if (extraAssetFields.length) throw new TypeError(`displayContext.asset.${extraAssetFields[0]} is not allowed`);
  if (missingAssetFields.length) throw new TypeError(`displayContext.asset.${missingAssetFields[0]} is required`);
  if (value.asset.assetId !== "forzy-motor-01") throw new TypeError("displayContext.asset.assetId is invalid");
  if (value.asset.displayName !== "Conjunto motor-bomba monitorado") throw new TypeError("displayContext.asset.displayName is invalid");
  if (value.asset.officialTag !== null) throw new TypeError("displayContext.asset.officialTag must be null");
  if (!isRecord(value.channels)) throw new TypeError("displayContext.channels must be an object");
  if (Object.keys(value.channels).sort().join(",") !== "s1,s2") throw new TypeError("displayContext.channels must contain exactly s1,s2");
  for (const key of ["s1", "s2"]) {
    if (value.channels[key] !== null && (typeof value.channels[key] !== "object" || Array.isArray(value.channels[key]))) {
      throw new TypeError(`displayContext.channels.${key} must be object|null`);
    }
  }
  for (const key of ["driverEvidenceIds", "emphasizedSensorIds", "exportableMeasurements", "exportableEvidence", "publicQualityFlags"]) {
    if (!Array.isArray(value[key])) throw new TypeError(`displayContext.${key} must be an array`);
  }
  if (new Set(value.driverEvidenceIds).size !== value.driverEvidenceIds.length || value.driverEvidenceIds.some((id) => typeof id !== "string" || id.length === 0)) {
    throw new TypeError("displayContext.driverEvidenceIds must contain unique non-empty strings");
  }
  if (new Set(value.emphasizedSensorIds).size !== value.emphasizedSensorIds.length || value.emphasizedSensorIds.some((id) => !["s1", "s2"].includes(id))) {
    throw new TypeError("displayContext.emphasizedSensorIds must be unique s1|s2 values");
  }
  if (!isRecord(value.capabilities)) throw new TypeError("displayContext.capabilities must be an object");
  if (Object.keys(value.capabilities).sort().join(",") !== [...CAPABILITY_FIELDS].sort().join(",") || CAPABILITY_FIELDS.some((key) => typeof value.capabilities[key] !== "boolean")) {
    throw new TypeError("displayContext.capabilities must be the closed boolean capability object");
  }
  return value;
}
```

Complete this validator recursively; checking only the root and then accepting arbitrary nested objects is forbidden. Freeze the following field manifest beside `DISPLAY_CONTEXT_V1_FIELDS`, and make the validator require every listed key exactly once and reject every unlisted key at its full path:

```text
DisplayChannelV1
  channelId, pointId|null, samplePairId|null, operatingCycleId|null,
  sensorId, eventAt, sourceKind, batchId|null, timestampQuality,
  measurements, qualityFlags[]
DisplayMeasurementsV1
  vibrationVelocityRms: {value,unit,semanticConfidence}|null
  vibrationAcceleration: {value,unit,statistic,semanticConfidence}|null
  temperature: {value,unit,semanticConfidence}|null
DisplayAssessmentV1
  assessmentId, assessmentKind, sensorId, anchorPointId|null, assessmentAt,
  status, anomalyScore|null, deteriorationScore|null, scoreSemantics,
  episodeId|null, episodeStartedAt|null, persistenceSeconds|null,
  persistenceCount|null, quality, evidence[], model,
  humanValidationRequired, limitations[]
DisplayAssessmentQualityV1
  status, flags[]
DisplayEvidenceV1
  evidenceId, feature, value, unit, baseline|null, deviation|null,
  direction|null, windowSeconds|null
DisplayModelV1 / PublicModelV1
  family, version, configHash, trainedUntil, foldId|null, foldHash|null,
  reportHash|null
DisplayAnchorV1
  pointId, samplePairId, operatingCycleId|null, sensorId, eventAt,
  sourceKind, batchId|null
ExportableMeasurementV1
  pointId|null, sensorId, metric, value, unit, eventAt
ExportableEvidenceV1
  evidenceId, assessmentId, sensorId, feature, value, unit,
  baseline|null, deviation|null, direction|null, windowSeconds|null
PublicQualityFlagV1
  scope, sensorId|null, code
PublicProvenanceV1
  pointSourceKind|null, pointSourceSystem|null, activeHistoricalBatchId|null,
  collectionPolicyId|null, assessmentSource
PublicAcquisitionV1
  expectedCollectionNow: boolean|null, policyEvidenceKind, gapType|null,
  sensors: {s1: PublicSensorHealthV1|null,s2: PublicSensorHealthV1|null}
PublicSensorHealthV1
  lastAttemptAt|null, lastSuccessAt|null, latencyMs|null, error|null,
  sampleCount
CapabilitiesV1
  hasComparablePreviousCycle, hasSensorChainEvidence, hasDriverEvidence
```

All public timestamps are canonical UTC milliseconds; all identifier/hash/string fields are non-empty and use their owning Foundation patterns. Numeric values are finite and never negative zero. Measurement units are exactly `mm/s`, `g`, `degC`; acceleration `statistic` is exactly `unknown`; confidence is `confirmed|inferred_from_datasheet|unconfirmed`. `metric` is exactly `vibrationVelocityRms|vibrationAcceleration|temperature`; quality status is `ok|degraded|insufficient_data`; direction is `up|down|stable|unknown|null`; `assessmentKind` is `live_assessment|historical_walk_forward`; `scoreSemantics` is exactly `relative_to_historical_baseline_not_failure_probability`. `policyEvidenceKind` is `valid|missing|invalid|not_applicable`; acquisition error is `upstream_unavailable|invalid_payload|null`; quality flags, limitations and evidence IDs are unique non-empty strings in their preserved input order. `publicModel` is null exactly when `assessment` is null, otherwise it is byte-for-byte equal to `assessment.model`; no recommendation, component attribution, raw provenance or payload is admitted.

Source discriminants are closed. An archive channel/anchor has `sourceKind="historical_archive"`, non-null point/pair/cycle IDs, a non-null `sha256:` batch and `timestampQuality="source_without_offset_assumed_timezone"`. A live channel/anchor has `sourceKind="live_collection"`, null batch, `timestampQuality="assumed_from_retrieval"`, and may have nullable point/pair/cycle identifiers only where the validated B source lacks them. `PublicProvenanceV1` admits exactly three tuples: archive (`historical_archive`,`forzy-csv`,non-null active batch,null policy, assessment source `historical_walk_forward|none`), live (`live_collection`,`forzy-api`,nullable global active batch,nullable collection policy, assessment source `live_assessment|none`), or no point (both point fields null, nullable global active batch, null policy, assessment source `none`). The global active archive may therefore coexist with a live point and is never used as the live point's batch discriminator.

Before reading nested values, run one path-aware `assertJsonTreeV1` over the entire candidate. It accepts only null, booleans, strings, finite non-negative-zero numbers, dense arrays and plain data objects with `Object.prototype|null`; it rejects `undefined`, functions, symbols, bigint, `NaN`, infinities, `-0`, sparse arrays, array extra properties, `Date`, `Map`, `Set`, typed arrays, class instances, accessors, non-enumerable data fields, symbol keys and cycles. Inspect `Reflect.ownKeys` plus property descriptors before reading values. Reject case-insensitive secret-like keys at any depth (`dsn`, `password`, `secret`, `token`, `authorization`, `cookie`, `apiKey`, `privateKey`, `raw`, `payload`) and pollution keys `__proto__`, `prototype`, `constructor`. Shared acyclic subobjects may appear twice, but traversal tracks the active recursion stack so a cycle always fails with the first path. This same accepted JSON domain is the only input domain of Task C3's canonicalizer.

Then enforce all cross-object invariants, not merely types:

- `dataAvailability="complete"` iff both channels exist; `partial` iff exactly one exists; `gap|unavailable` iff neither exists. Existing channels have their map-key `sensorId`, unique `channelId`, same public instant/pair when paired, and no crossed source/batch.
- `conditionTemporalScope/source/asOf/episodeStartedAt` is exactly coherent with `assessment`: `none/none/null/null` iff no usable assessed condition; otherwise assessment kind/status/sensor/time/episode equals the flattened facts. Watch/alert requires non-null episode ID/start and positive persistence count where contracted; normal/insufficient-data has no invented episode. Episode start is not after condition/assessment time.
- `viewMode="now"` has `anchor=null`; `viewMode="historical"` uses `historical_context|historical_gap + not_applicable + historical`. A historical context has a non-null original anchor; a gap has the exact unknown/none/null tuple, null anchor/channels/assessment/model/evidence and no carry-forward. For `viewMode="now"`, `not_applicable` is valid only with `last_known|unavailable + unknown` and is never repaired.
- A non-null anchor resolves to its matching channel; every non-null channel has the anchor's `samplePairId`, source and batch, and the anchor sensor channel has the same point/event identity. Archive anchors require the public provenance active batch to equal the anchor batch; live anchors require null anchor batch even when global `activeHistoricalBatchId` is non-null.
- Every exportable measurement resolves to exactly one non-null channel/metric with identical point, sensor, event, value and unit. Every exportable evidence item resolves to exactly one assessment evidence entry and repeats that assessment/sensor identity. IDs are unique; `driverEvidenceIds` is an ordered subset of exportable evidence IDs; `emphasizedSensorIds` is exactly the canonical `s1,s2` set named by those resolved drivers.
- `hasDriverEvidence` is exactly `driverEvidenceIds.length > 0`; `hasSensorChainEvidence` is true exactly when acquisition/quality evidence exists for the displayed channels; `hasComparablePreviousCycle` requires an archive anchor, non-null cycle and explicit contracted previous-cycle evidence. No capability is inferred from a score. `publicAcquisition` contains only this context's source facts: archive/gap sensors are null, live health belongs only to displayed live sensors, and `gapType` is non-null only for `historical_gap`.

Keep `assertDisplayContextV1(value)` as the identity validator for compatibility. Also export `cloneAndFreezeDisplayContextV1(value)`: call the identity validator, manually clone only the accepted JSON primitives/arrays/plain-object data properties, revalidate the clone, recursively freeze every node, and return the new root. Do not use `structuredClone`, JSON stringify/parse or caller-owned references at this trust boundary. Tests mutate the input immediately after the clone and prove the clone/hash cannot change.

In this C1 module, also export `toOperationalDecisionInput(displayContext)`. It first calls `assertDisplayContextV1`, then returns a newly frozen allowlist containing only `decisionFactsSchemaVersion`, `viewMode`, `decisionAsOf`, the ten non-version fields of `TimelineDecisionFactsV1` (including `conditionEpisodeStartedAt`), `driverEvidenceIds` and the three closed capability booleans. This projection exists **only for ruleset matching and output field selection**. It is never the input to `displayContextHash` or `decisionId`; those identifiers bind the complete validated `DisplayContextV1` in Task C3. C1 tests assert the exact projection keys and byte-for-byte fact values. Task C5 may add named adapter exports below this code but cannot change `DISPLAY_CONTEXT_V1_FIELDS`, either function signature, the allowlist or these invariants.

Create `src/contracts/operationalDecisionV1.js` separately. It validates only the UI-owned presentation result; it never accepts a B snapshot/context as an `OperationalDecisionViewV1` and B never imports or constructs it:

```js
const SHA256 = /^sha256:[0-9a-f]{64}$/;
const REQUIRED = [
  "schemaVersion", "ruleSetVersion", "ruleSetHash", "decisionId", "displayContextHash",
  "viewMode", "decisionAsOf", "conditionState", "conditionTemporalScope", "conditionAsOf",
  "conditionSource", "collectionState", "collectionExpectation", "dataAvailability",
  "dataFreshness", "dataTrust", "triageState", "summaryCode", "driverEvidence",
  "nextCheckCodes", "limitationCodes",
];
const NEXT_CHECK_ORDER = [
  "monitor_next_expected_sample", "review_evidence", "compare_previous_cycle",
  "review_data_gap", "verify_acquisition", "review_sensor_chain_evidence",
  "escalate_engineering_review",
];
const LIMITATION_ORDER = [
  "not_failure_probability", "component_not_localized", "sensor_placement_unvalidated",
  "source_timestamp_assumed", "data_partial", "data_quality_degraded", "data_stale",
  "historical_context_only", "no_causal_assessment", "lead_time_not_validated",
  "site_procedure_unavailable",
];

const assertOrderedUnique = (values, order, path) => {
  if (!Array.isArray(values) || new Set(values).size !== values.length) throw new TypeError(`${path} must be unique`);
  const indexes = values.map((value) => order.indexOf(value));
  if (indexes.some((value) => value < 0) || indexes.some((value, index) => index > 0 && value < indexes[index - 1])) {
    throw new TypeError(`${path} must use canonical order`);
  }
};

export function assertOperationalDecisionViewV1(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new TypeError("decision must be an object");
  if (Object.keys(value).length !== REQUIRED.length || REQUIRED.some((key) => !Object.hasOwn(value, key))) {
    throw new TypeError("decision must contain exactly the closed V1 fields");
  }
  if (value.schemaVersion !== "1.0" || value.ruleSetVersion !== "forzy-operational-triage-v1") {
    throw new TypeError("decision schema/ruleset is invalid");
  }
  for (const key of ["ruleSetHash", "decisionId", "displayContextHash"]) {
    if (!SHA256.test(value[key])) throw new TypeError(`decision.${key} must be sha256`);
  }
  assertOrderedUnique(value.nextCheckCodes, NEXT_CHECK_ORDER, "decision.nextCheckCodes");
  assertOrderedUnique(value.limitationCodes, LIMITATION_ORDER, "decision.limitationCodes");
  if (value.viewMode === "historical" && value.nextCheckCodes.includes("escalate_engineering_review")) {
    throw new TypeError("decision.nextCheckCodes cannot escalate historical context");
  }
  return value;
}
```

Add exact enum assertions from Spec §9.1, canonical UTC-millisecond checks for decision/condition times, reciprocal `conditionAsOf === null` / scope-source `none` coherence, unique non-empty `driverEvidence`, closed summary codes, and rejection of every extra property. `conditionEpisodeStartedAt` stays in the hashed `DisplayContextV1` rather than being added to this closed Spec §9.1 presentation contract. Add a negative test proving a valid `TimelineDecisionFactsV1` is rejected as a missing-field `OperationalDecisionViewV1`, so the B-owned fact projection and C-owned decision presentation cannot collapse into one type.

- [ ] **Step 5: Run focused tests to verify GREEN**

Checked Run: rerun both Step 0 helper suites, then run `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/contracts/timelineV1.test.js src/contracts/schemaTimelineV1.test.js src/displayContext/displayContextV1.test.js src/contracts/operationalDecisionV1.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C1 complete tests'`.

Expected: PASS; Foundation validators accept the five additional fixtures, the C1 display validator freezes the exact shared shape/invariants, and the separate UI-owned decision validator rejects B facts, extra fields, invalid hashes/order and historical escalation.

- [ ] **Step 6: Commit only UI-owned additions**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c1CodePaths=@(
  'contracts/timeline/v1/fixtures/timeline-context-gap.valid.json',
  'contracts/timeline/v1/fixtures/timeline-context-historical-candidate.valid.json',
  'contracts/timeline/v1/fixtures/timeline-context-live-normal.valid.json',
  'contracts/timeline/v1/fixtures/timeline-overview-mixed.valid.json',
  'contracts/timeline/v1/fixtures/timeline-overview-single-point.valid.json',
  'scripts/phase_c_evidence.py',
  'scripts/phase_c_plan_gates.ps1',
  'scripts/tests/phase_c_plan_gates.tests.ps1',
  'scripts/tests/test_phase_c_evidence.py',
  'src/contracts/operationalDecisionV1.js',
  'src/contracts/operationalDecisionV1.test.js',
  'src/displayContext/displayContextV1.fixtures.js',
  'src/displayContext/displayContextV1.js',
  'src/displayContext/displayContextV1.test.js'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'C1 display contract code' -Message 'feat: freeze C1 display and decision contracts' -Paths $c1CodePaths
```

Immediately freeze the code identity, but do not hand it to D yet:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$rawC1DisplayContractCommit = git rev-parse HEAD
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'freeze C1 display contract commit'
$c1DisplayContractCommit = ($rawC1DisplayContractCommit -join "`n").Trim()
$rawC1BaseCommit = git rev-parse "$c1DisplayContractCommit^"
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'freeze C1 base commit'
$c1BaseCommit = ($rawC1BaseCommit -join "`n").Trim()
if ($c1DisplayContractCommit -notmatch '^[0-9a-f]{40}$' -or $c1BaseCommit -notmatch '^[0-9a-f]{40}$') { throw 'invalid C1 code/base SHA' }
```

- [ ] **Step 7: Independently review the exact C1 code SHA with a closed scope**

Start the reviewer from `$c1DisplayContractCommit`, never from a branch name or the later evidence commit. Re-run the focused C1 suites and prove the whole code range contains exactly the declared checkpoint paths:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$expectedC1Scope = @(
  'contracts/timeline/v1/fixtures/timeline-context-gap.valid.json',
  'contracts/timeline/v1/fixtures/timeline-context-historical-candidate.valid.json',
  'contracts/timeline/v1/fixtures/timeline-context-live-normal.valid.json',
  'contracts/timeline/v1/fixtures/timeline-overview-mixed.valid.json',
  'contracts/timeline/v1/fixtures/timeline-overview-single-point.valid.json',
  'scripts/phase_c_evidence.py',
  'scripts/phase_c_plan_gates.ps1',
  'scripts/tests/phase_c_plan_gates.tests.ps1',
  'scripts/tests/test_phase_c_evidence.py',
  'src/contracts/operationalDecisionV1.js',
  'src/contracts/operationalDecisionV1.test.js',
  'src/displayContext/displayContextV1.fixtures.js',
  'src/displayContext/displayContextV1.js',
  'src/displayContext/displayContextV1.test.js'
) | Sort-Object
$rawC1Scope = @(git diff --name-only $c1BaseCommit $c1DisplayContractCommit)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read C1 reviewed scope'
$actualC1Scope = @($rawC1Scope | Sort-Object)
if (Compare-Object $expectedC1Scope $actualC1Scope) { throw 'C1 reviewed range has out-of-scope or missing paths' }
git diff --check $c1BaseCommit $c1DisplayContractCommit
Assert-NativeExit $LASTEXITCODE 'C1 diff check'
& $python -m unittest scripts.tests.test_phase_c_evidence
Assert-NativeExit $LASTEXITCODE 'reviewed C1 Python helper tests'
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File scripts/tests/phase_c_plan_gates.tests.ps1
Assert-NativeExit $LASTEXITCODE 'reviewed C1 PowerShell helper tests'
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/contracts/timelineV1.test.js src/contracts/schemaTimelineV1.test.js src/displayContext/displayContextV1.test.js src/contracts/operationalDecisionV1.test.js
Assert-NativeExit $LASTEXITCODE 'reviewed C1 complete tests'
```

The independent reviewer creates the cumulative `docs/verification/phase-c-findings.json` in the common strict `finding-review-v1` shape, with `plan="C"` and `reviewedSha=$c1DisplayContractCommit`. Preserve finding IDs across every re-review. Fix/recommit only the declared C1 scope and replace `$c1DisplayContractCommit` until the exact reviewed SHA has zero open Critical/Important and no unaccepted Minor; then repeat the ancestry, exact scope, both helper suites and the complete four-file C1 Vitest command above. A clean checkpoint requires verdict `0 Critical / 0 Important`; no executor may self-author that verdict.

- [ ] **Step 8: Materialize the C1 handoff in a separate evidence commit without closing plan C**

Validate the independent report, ingest that exact review through the shared verifier, and prove this changes C only to `in_progress`: no criterion is updated and the phase is not closed. Then create `docs/verification/checkpoints/c1-display-contract-handoff.json` with exactly `schemaVersion`, `checkpoint`, `producerPlan`, `consumerTask`, `baseCommit`, `reviewedCodeCommit`, `reviewReport`, `reviewReportSha256`, `verdict` and `environment`. Use `schemaVersion="phase-checkpoint-handoff-v1"`, `checkpoint="C1"`, `producerPlan="C"`, `consumerTask="D1"`, `reviewReport="docs/verification/phase-c-findings.json"`, both `reviewedCodeCommit` and `environment.C1_DISPLAY_CONTRACT_COMMIT` equal to `$c1DisplayContractCommit`, and the lowercase SHA-256 of the exact report. `verdict` copies the report's three integer counts; it never invents a pass.

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c1Review = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/phase-c-findings.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
Assert-FindingVerdictObject $c1Review.verdict 'C1 review verdict'
if ($c1Review.schemaVersion -cne 'finding-review-v1' -or $c1Review.plan -cne 'C' -or [string]$c1Review.reviewedSha -cne $c1DisplayContractCommit -or $c1Review.verdict.critical -ne 0 -or $c1Review.verdict.important -ne 0) { throw 'C1 review is absent, stale or blocking' }
$c1UnacceptedMinor = @($c1Review.findings | Where-Object { $_.severity -eq 'minor' -and $_.status -notin @('fixed','accepted') })
if ($c1UnacceptedMinor.Count -ne 0) { throw 'C1 has an unaccepted Minor finding' }
git merge-base --is-ancestor $c1BaseCommit $c1DisplayContractCommit
Assert-NativeExit $LASTEXITCODE 'C1 base ancestry'
$ledgerBeforeC1Handoff = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/unified-twin-acceptance-v1.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$prematureC1Criteria = @($ledgerBeforeC1Handoff.criteria | Where-Object { $_.ownerPlan -eq 'C' -and $_.status -ne 'pending' })
if ($ledgerBeforeC1Handoff.plans.C.status -ne 'pending' -or $null -ne $ledgerBeforeC1Handoff.plans.C.verifiedCodeCommit -or $prematureC1Criteria.Count -ne 0) { throw 'C ledger was mutated before C1 review ingestion' }
$python = (Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe" -ErrorAction Stop).Path
& $python scripts/verify_unified_acceptance.py ingest-review --ledger docs/verification/unified-twin-acceptance-v1.json --review-report docs/verification/phase-c-findings.json
Assert-NativeExit $LASTEXITCODE 'ingest C1 independent review'
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
Assert-NativeExit $LASTEXITCODE 'render ledger after C1 review'
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
Assert-NativeExit $LASTEXITCODE 'verify ledger after C1 review'
$ledgerAfterC1Review = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/unified-twin-acceptance-v1.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
Assert-ReviewVerdictArray $ledgerAfterC1Review.plans.C.reviewVerdict @($c1Review.verdict.critical,$c1Review.verdict.important,$c1Review.verdict.minor) 'C1 ledger review verdict'
$closedC1Criteria = @($ledgerAfterC1Review.criteria | Where-Object { $_.ownerPlan -eq 'C' -and $_.status -ne 'pending' })
$ac15AfterC1 = @($ledgerAfterC1Review.criteria | Where-Object criterionId -eq 'AC-15')
if ($ledgerAfterC1Review.plans.C.status -ne 'in_progress' -or [string]$ledgerAfterC1Review.plans.C.verifiedCodeCommit -cne $c1DisplayContractCommit -or $closedC1Criteria.Count -ne 0 -or $ac15AfterC1.Count -ne 1 -or $ac15AfterC1[0].ownerPlan -ne 'E' -or $ac15AfterC1[0].status -ne 'pending') { throw 'C1 review ingestion closed or reassigned acceptance criteria' }
$c1ReviewSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath 'docs/verification/phase-c-findings.json' -ErrorAction Stop).Hash.ToLowerInvariant()
```

After substituting those exact values into the closed handoff JSON, validate its exact key set and bindings, then commit only the checkpoint report/handoff and verifier-generated ledger pair:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c1Handoff = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/checkpoints/c1-display-contract-handoff.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$expectedC1HandoffKeys = @('baseCommit','checkpoint','consumerTask','environment','producerPlan','reviewedCodeCommit','reviewReport','reviewReportSha256','schemaVersion','verdict') | Sort-Object
$actualC1HandoffKeys = @($c1Handoff.PSObject.Properties.Name) | Sort-Object
if (Compare-Object $expectedC1HandoffKeys $actualC1HandoffKeys) { throw 'C1 handoff shape mismatch' }
$c1EnvironmentKeys = @($c1Handoff.environment.PSObject.Properties.Name) | Sort-Object
$c1VerdictKeys = @($c1Handoff.verdict.PSObject.Properties.Name) | Sort-Object
Assert-FindingVerdictObject $c1Handoff.verdict 'C1 handoff verdict'
if (Compare-Object @('C1_DISPLAY_CONTRACT_COMMIT') $c1EnvironmentKeys -CaseSensitive -SyncWindow 0) { throw 'C1 handoff environment must contain exactly one SHA' }
if (Compare-Object @('critical','important','minor') $c1VerdictKeys -CaseSensitive -SyncWindow 0) { throw 'C1 handoff verdict shape mismatch' }
if ($c1Handoff.schemaVersion -cne 'phase-checkpoint-handoff-v1' -or $c1Handoff.checkpoint -cne 'C1' -or $c1Handoff.producerPlan -cne 'C' -or $c1Handoff.consumerTask -cne 'D1' -or [string]$c1Handoff.baseCommit -cne $c1BaseCommit -or [string]$c1Handoff.reviewedCodeCommit -cne $c1DisplayContractCommit -or [string]$c1Handoff.reviewReport -cne 'docs/verification/phase-c-findings.json' -or [string]$c1Handoff.environment.C1_DISPLAY_CONTRACT_COMMIT -cne $c1DisplayContractCommit -or [string]$c1Handoff.reviewReportSha256 -cne $c1ReviewSha256 -or $c1Handoff.verdict.critical -ne 0 -or $c1Handoff.verdict.important -ne 0 -or $c1Handoff.verdict.minor -ne $c1Review.verdict.minor) { throw 'C1 handoff binding mismatch' }
$c1EvidencePaths=@(
  'docs/verification/checkpoints/c1-display-contract-handoff.json',
  'docs/verification/phase-c-findings.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'C1 handoff evidence' -Message 'docs: record reviewed C1 display contract handoff' -Paths $c1EvidencePaths
$rawC1HandoffEvidenceCommit = git rev-parse HEAD
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'freeze C1 handoff evidence commit'
$c1HandoffEvidenceCommit = ($rawC1HandoffEvidenceCommit -join "`n").Trim()
if ($c1HandoffEvidenceCommit -notmatch '^[0-9a-f]{40}$') { throw 'invalid C1 evidence SHA' }
$rawC1EvidenceParent=git rev-parse "$c1HandoffEvidenceCommit^"
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read C1 evidence parent'
if ((($rawC1EvidenceParent -join "`n").Trim()) -cne $c1DisplayContractCommit) { throw 'C1 evidence commit is not immediately after reviewed C1 code' }
$rawC1EvidenceScope=@(git diff-tree --no-commit-id --name-only -r $c1HandoffEvidenceCommit)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read C1 evidence diff'
if (Compare-Object $c1EvidencePaths @($rawC1EvidenceScope | Sort-Object)) { throw 'C1 evidence commit scope mismatch' }
$c1ProjectionJson=@(& $python scripts/phase_c_evidence.py checkpoint-projection --commit $c1HandoffEvidenceCommit --handoff-path 'docs/verification/checkpoints/c1-display-contract-handoff.json')
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'reparse committed C1 evidence blobs'
$c1Projection=(($c1ProjectionJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
Assert-FindingVerdictObject $c1Projection.review.verdict 'committed C1 review verdict'
Assert-FindingVerdictObject $c1Projection.handoff.verdict 'committed C1 handoff verdict'
Assert-ReviewVerdictArray $c1Projection.planC.reviewVerdict @($c1Projection.review.verdict.critical,$c1Projection.review.verdict.important,$c1Projection.review.verdict.minor) 'committed C1 ledger review verdict'
if ($c1Projection.reviewHash -cne ('sha256:' + $c1ReviewSha256) -or $c1Projection.handoff.reviewReportSha256 -cne $c1ReviewSha256 -or $c1Projection.review.schemaVersion -cne 'finding-review-v1' -or $c1Projection.review.plan -cne 'C' -or [string]$c1Projection.review.reviewedSha -cne $c1DisplayContractCommit -or $c1Projection.handoff.schemaVersion -cne 'phase-checkpoint-handoff-v1' -or $c1Projection.handoff.checkpoint -cne 'C1' -or [string]$c1Projection.handoff.baseCommit -cne $c1BaseCommit -or [string]$c1Projection.handoff.reviewedCodeCommit -cne $c1DisplayContractCommit -or [string]$c1Projection.handoff.environment.C1_DISPLAY_CONTRACT_COMMIT -cne $c1DisplayContractCommit -or $c1Projection.planC.status -cne 'in_progress' -or [string]$c1Projection.planC.verifiedCodeCommit -cne $c1DisplayContractCommit) { throw 'committed C1 evidence blobs or bindings mismatch' }
git diff --exit-code $c1HandoffEvidenceCommit -- $c1EvidencePaths
Assert-NativeExit $LASTEXITCODE 'working C1 evidence equals committed evidence'
$env:C1_DISPLAY_CONTRACT_COMMIT = $c1DisplayContractCommit
$env:C1_HANDOFF_EVIDENCE_COMMIT = $c1HandoffEvidenceCommit
```

Do **not** call `update-criterion` here; `ingest-review` is the sole checkpoint ledger mutation, and `render`/`verify` must immediately follow it. Record both exact environment SHAs in the execution handoff. D1 may start only after reading the committed handoff, reproducing its report hash/verdict and proving `$c1DisplayContractCommit` is an ancestor of its clean HEAD. Task C5 later adds adapters to the same module while tests prove the frozen field list, validator and matching-only projection did not drift; it does not create a competing display-context type.

---

### Task 2: Same-Origin Timeline Data Source

**Files:**
- Modify: `src/dataSources/GatewayTwinDataSourceV2.js:1-84`
- Modify: `src/dataSources/GatewayTwinDataSourceV2.test.js:1-end`
- Create: `src/time/canonicalUtcMillis.js`
- Create: `src/time/canonicalUtcMillis.test.js`

**Interfaces:**
- Consumes: Foundation timeline validators plus the Task 1 operational-decision validator.
- Produces:

```js
getTimelineOverview(assetId, { from, to, sensorId, metric, maxPoints, signal })
getTimelineSamples(assetId, { from, to, sensorId, limit, cursor, signal })
getTimelineContext(assetId, { pointId, at, segmentId, signal })
```

- [ ] **Step 1: Write failing URL and selector tests**

```js
it("builds a bounded read-only timeline query", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => overview });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });
  await source.getTimelineOverview("forzy-motor-01", {
    from: "2026-05-19T14:46:10.921Z",
    to: "2026-08-13T00:00:00.000Z",
    sensorId: "all",
    metric: "temperature",
    maxPoints: 1200,
  });
  expect(fetchImpl).toHaveBeenCalledWith(
    "/api/v2/assets/forzy-motor-01/timeline?from=2026-05-19T14%3A46%3A10.921Z&to=2026-08-13T00%3A00%3A00.000Z&metric=temperature&maxPoints=1200",
    expect.objectContaining({ method: "GET" }),
  );
});

it.each([
  [{ pointId: "point-1", at: "2026-05-19T14:46:10.921Z", segmentId: "seg-1" }],
  [{ at: "2026-05-19T14:46:10.921Z" }],
  [{ segmentId: "seg-1" }],
  [{}],
])("rejects ambiguous context selector %j", async (selector) => {
  await expect(source.getTimelineContext("forzy-motor-01", selector)).rejects.toThrow(/exactly pointId or at with segmentId/);
  expect(fetchImpl).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run test to verify RED**

Checked RED Run: capture output from `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/time/canonicalUtcMillis.test.js src/dataSources/GatewayTwinDataSourceV2.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C2 expected-red tests' @(1)`, then require the captured failure to name the missing parser/gateway behavior.

Expected: FAIL because the three timeline methods do not exist.

- [ ] **Step 3: Implement strict query builders and response validation**

```js
const CANONICAL_UTC_MILLIS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;

export const parseCanonicalUtcMillis = (value, name = "timestamp") => {
  if (typeof value !== "string" || !CANONICAL_UTC_MILLIS.test(value)) {
    throw new TypeError(`${name} must be canonical UTC with millisecond precision`);
  }
  const millis = Date.parse(value);
  if (!Number.isFinite(millis) || new Date(millis).toISOString() !== value) {
    throw new TypeError(`${name} must be a JS-representable canonical UTC instant`);
  }
  return millis;
};

export const compareCanonicalUtcMillis = (left, right) =>
  Math.sign(
    parseCanonicalUtcMillis(left, "left timestamp")
      - parseCanonicalUtcMillis(right, "right timestamp"),
  );

export const addOneMillisecondUtc = (value) => {
  const next = parseCanonicalUtcMillis(value) + 1;
  if (!Number.isFinite(next)) throw new TypeError("timestamp has no JS-representable successor");
  const rendered = new Date(next).toISOString();
  if (!CANONICAL_UTC_MILLIS.test(rendered)) throw new RangeError("timestamp has no public millisecond successor");
  return rendered;
};

const assertUtc = (value, name) => {
  if (value !== undefined) parseCanonicalUtcMillis(value, `TwinOps timeline ${name}`);
};

const timelineQuery = ({ from, to, sensorId, metric, maxPoints }) => {
  assertUtc(from, "from");
  assertUtc(to, "to");
  if (from && to && compareCanonicalUtcMillis(from, to) >= 0) throw new TypeError("TwinOps timeline from must precede to");
  if (sensorId !== undefined && !["s1", "s2", "all"].includes(sensorId)) throw new TypeError("TwinOps timeline sensorId is invalid");
  if (metric !== undefined && !TIMELINE_METRICS.includes(metric)) throw new TypeError("TwinOps timeline metric is invalid");
  if (maxPoints !== undefined && (!Number.isInteger(maxPoints) || maxPoints < 40 || maxPoints > 4000)) {
    throw new TypeError("TwinOps timeline maxPoints must be an integer from 40 to 4000");
  }
  const query = new URLSearchParams();
  if (from) query.set("from", from);
  if (to) query.set("to", to);
  if (sensorId && sensorId !== "all") query.set("sensorId", sensorId);
  if (metric) query.set("metric", metric);
  if (maxPoints) query.set("maxPoints", String(maxPoints));
  return query;
};
```

Each method calls `requestJson` with `method: "GET"`, passes the exact caller signal, and immediately calls the reused Foundation timeline validator. Keep existing `/history` compatibility unchanged. `src/time/canonicalUtcMillis.js` is the only public-time parser/comparator/successor: reject microseconds, offset forms, impossible normalized dates and overflow instead of relying on permissive `Date.parse` or string collation.

- [ ] **Step 4: Add edge and abort tests**

Cover invalid UTC (including six fractional digits), impossible normalized dates, non-representable instants, equal/inverted range, an exact +1 ms successor across second/day boundaries, invalid metric/sensor, 39/4001 points, sample limit 0/501, blank cursor, XOR context selector, encoded IDs, 409 response, invalid JSON shape and the same AbortSignal for all three methods.

- [ ] **Step 5: Run tests to verify GREEN**

Checked Run: `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/time/canonicalUtcMillis.test.js src/dataSources/GatewayTwinDataSourceV2.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C2 green tests'`.

Expected: PASS; all new calls are GET, same-origin and contract-validated.

- [ ] **Step 6: Commit**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c2CodePaths=@(
  'src/dataSources/GatewayTwinDataSourceV2.js',
  'src/dataSources/GatewayTwinDataSourceV2.test.js',
  'src/time/canonicalUtcMillis.js',
  'src/time/canonicalUtcMillis.test.js'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'C2 gateway code' -Message 'feat: add read-only timeline gateway client' -Paths $c2CodePaths
```

---

### Task 3: Versioned Operational Decision Ruleset and Stable Hashes

**Files:**
- Reuse unchanged: `contracts/timeline/v1/fixtures/live-decision-facts-v1-cases.json`
- Reuse unchanged and authenticate from Phase B: `contracts/timeline/v1/timeline-overview.schema.json`, `timeline-page.schema.json`, `timeline-context.schema.json`, `timeline-decision-facts.schema.json`, `contracts/v2/digital-twin-snapshot.schema.json`, `contracts/v2/fixtures/snapshot-received-now.valid.json`, `contracts/v2/fixtures/snapshot-last-known.valid.json`, `src/contracts/timelineV1.js`, and `src/contracts/twinV2.js`
- Create before decision code: `docs/verification/checkpoints/b-to-c-contract-handoff.json`
- Create: `contracts/v2/rulesets/forzy-operational-triage-v1.json`
- Create: `contracts/v2/rulesets/fixtures/b-live-display-context-v1-cases.json` (C-owned complete non-derived contexts keyed one-for-one to B case IDs)
- Create: `src/decisionSupport/canonicalJson.js`
- Create: `src/decisionSupport/canonicalJson.test.js`
- Create: `src/decisionSupport/operationalDecisionV1.js`
- Create: `src/decisionSupport/operationalDecisionV1.test.js`

**Interfaces:**
- Consumes: Task C1 `DisplayContextV1`, `assertDisplayContextV1`, the matching-only `toOperationalDecisionInput`, and `assertOperationalDecisionViewV1`, plus the authenticated final B code/evidence commits, PASS report/ledger and exact raw-byte SHA-256 map in `b-to-c-contract-handoff.json`. Task 3 imports each B `expectedDecisionFacts` value literally into complete validated `DisplayContextV1` test cases; it never hydrates producer descriptors or recreates B's policy/quality logic. Task C5 must reauthenticate the same identities before provider integration.
- Produces: `canonicalJson(value)`, `sha256Text(text, cryptoImpl)`, `DISPLAY_CONTEXT_HASH_CONTRACT_V1`, `canonicalDisplayContextV1(displayContext)`, `hashDisplayContextV1(displayContext, cryptoImpl)`, `operationalTriageRulesetV1` as the single deep-frozen validated JSON bundle, and `buildOperationalDecisionViewV1(displayContext, { cryptoImpl }) -> Promise<OperationalDecisionViewV1>`. The builder accepts the **complete** display context; the reduced decision input is internal matching data and is never a hash preimage.

- [ ] **Step 0: Authenticate and persist the exact B→C contract handoff**

The controller supplies the two externally frozen B SHAs; never derive either from HEAD. Run this in the checked PowerShell 5.1 session defined above:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$phaseBCodeCommit=[string]$env:PHASE_B_VERIFIED_CODE_COMMIT
$phaseBEvidenceCommit=[string]$env:PHASE_B_EVIDENCE_COMMIT
if ($phaseBCodeCommit -notmatch '^[0-9a-f]{40}$' -or $phaseBEvidenceCommit -notmatch '^[0-9a-f]{40}$') { throw 'exact Phase B code/evidence SHAs are required' }
git merge-base --is-ancestor $phaseBCodeCommit $phaseBEvidenceCommit
Assert-NativeExit $LASTEXITCODE 'B code to evidence ancestry'
git merge-base --is-ancestor $phaseBEvidenceCommit HEAD
Assert-NativeExit $LASTEXITCODE 'B evidence to C3 HEAD ancestry'

$rawBEvidencePaths=@(git diff --name-only "$phaseBCodeCommit..$phaseBEvidenceCommit")
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read Phase B evidence scope'
$actualBEvidencePaths=@($rawBEvidencePaths | Sort-Object)
$expectedBEvidencePaths=@(
  'docs/verification/phase-b-findings.json',
  'docs/verification/phase-b-local-causal-manifest.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) | Sort-Object
if (Compare-Object $expectedBEvidencePaths $actualBEvidencePaths) { throw 'Phase B evidence-only scope mismatch' }

$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe" -ErrorAction Stop).Path
$bContractPaths=@(
  'contracts/timeline/v1/timeline-overview.schema.json',
  'contracts/timeline/v1/timeline-page.schema.json',
  'contracts/timeline/v1/timeline-context.schema.json',
  'contracts/timeline/v1/timeline-decision-facts.schema.json',
  'contracts/timeline/v1/fixtures/live-decision-facts-v1-cases.json',
  'contracts/v2/digital-twin-snapshot.schema.json',
  'contracts/v2/fixtures/snapshot-received-now.valid.json',
  'contracts/v2/fixtures/snapshot-last-known.valid.json',
  'src/contracts/timelineV1.js',
  'src/contracts/twinV2.js'
) | Sort-Object
$contractHashJson=@(& $python scripts/phase_c_evidence.py hash-paths --commit $phaseBCodeCommit --paths $bContractPaths)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'hash raw git-show Phase B contracts'
$phaseBContractSha256=(($contractHashJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
foreach($path in $bContractPaths) {
  $recorded=[string]$phaseBContractSha256.PSObject.Properties[$path].Value
  if ($recorded -notmatch '^sha256:[0-9a-f]{64}$') { throw "missing git-show SHA-256: $path" }
  $working='sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath $path -ErrorAction Stop).Hash.ToLowerInvariant()
  if ($working -cne $recorded) { throw "working contract differs from Phase B reviewed code: $path" }
}

$reviewPath='docs/verification/phase-b-findings.json'
$reviewHashJson=@(& $python scripts/phase_c_evidence.py hash-paths --commit $phaseBEvidenceCommit --paths $reviewPath)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'hash raw git-show Phase B review'
$reviewHashMap=(($reviewHashJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
$phaseBReviewSha256=[string]$reviewHashMap.PSObject.Properties[$reviewPath].Value
$currentBReviewSha256='sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath $reviewPath -ErrorAction Stop).Hash.ToLowerInvariant()
if ($currentBReviewSha256 -cne $phaseBReviewSha256) { throw 'current Phase B review differs from evidence commit' }
$phaseBReview=Get-Content -Raw -Encoding utf8 -LiteralPath $reviewPath -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
Assert-FindingVerdictObject $phaseBReview.verdict 'Phase B finding review verdict'
if ($phaseBReview.schemaVersion -cne 'finding-review-v1' -or $phaseBReview.plan -cne 'B' -or [string]$phaseBReview.reviewedSha -cne $phaseBCodeCommit -or $phaseBReview.verdict.critical -ne 0 -or $phaseBReview.verdict.important -ne 0) { throw 'Phase B review is stale or not PASS' }
$phaseBUnacceptedMinor=@($phaseBReview.findings | Where-Object { $_.severity -eq 'minor' -and $_.status -notin @('fixed','accepted') })
if ($phaseBUnacceptedMinor.Count -ne 0) { throw 'Phase B review has an unaccepted Minor finding' }

$ledgerProjectionJson=@(& $python scripts/phase_c_evidence.py b-evidence-projection --commit $phaseBEvidenceCommit)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'git-show and parse Phase B review plus ledger'
$phaseBLedgerProjection=(($ledgerProjectionJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
Assert-FindingVerdictObject $phaseBLedgerProjection.review.verdict 'committed Phase B finding review verdict'
$phaseBVerdictCounts=@($phaseBLedgerProjection.review.verdict.critical,$phaseBLedgerProjection.review.verdict.important,$phaseBLedgerProjection.review.verdict.minor)
Assert-ReviewVerdictArray $phaseBLedgerProjection.planB.reviewVerdict $phaseBVerdictCounts 'committed Phase B ledger review verdict'
if ($phaseBLedgerProjection.reviewHash -cne $phaseBReviewSha256 -or $phaseBLedgerProjection.review.schemaVersion -cne 'finding-review-v1' -or $phaseBLedgerProjection.review.plan -cne 'B' -or [string]$phaseBLedgerProjection.review.reviewedSha -cne $phaseBCodeCommit -or $phaseBLedgerProjection.planB.status -cne 'passed' -or [string]$phaseBLedgerProjection.planB.verifiedCodeCommit -cne $phaseBCodeCommit -or $phaseBLedgerProjection.criteria.'AC-13'.status -cne 'passed' -or $phaseBLedgerProjection.criteria.'AC-14'.status -cne 'passed') { throw 'Phase B review/ledger projection is not closed on its reviewed code SHA' }
$currentLedger=Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/unified-twin-acceptance-v1.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
Assert-ReviewVerdictArray $currentLedger.plans.B.reviewVerdict $phaseBVerdictCounts 'current Phase B ledger review verdict'
if ($currentLedger.plans.B.status -cne 'passed' -or [string]$currentLedger.plans.B.verifiedCodeCommit -cne $phaseBCodeCommit -or @($currentLedger.criteria | Where-Object criterionId -eq 'AC-13').Count -ne 1 -or @($currentLedger.criteria | Where-Object criterionId -eq 'AC-13')[0].status -cne 'passed' -or @($currentLedger.criteria | Where-Object criterionId -eq 'AC-14').Count -ne 1 -or @($currentLedger.criteria | Where-Object criterionId -eq 'AC-14')[0].status -cne 'passed') { throw 'current cumulative ledger regressed Phase B' }
```

Create `b-to-c-contract-handoff.json` with exactly `schemaVersion`, `phaseBCodeCommit`, `phaseBEvidenceCommit`, `reviewVerdict`, `phaseBReviewSha256`, `phaseBLedgerSha256`, `evidencePaths` and `contractSha256`. Values are the exact variables above; `schemaVersion="phase-b-to-c-contract-handoff-v1"`, `reviewVerdict="PASS"`, arrays are canonically ordered, and `contractSha256` has exactly the ten `$bContractPaths` keys. Reparse it, compare every key/value/hash to the live attestation, then commit only this file:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$bToCPath='docs/verification/checkpoints/b-to-c-contract-handoff.json'
$bToC=Get-Content -Raw -Encoding utf8 -LiteralPath $bToCPath -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$expectedBToCKeys=@('contractSha256','evidencePaths','phaseBCodeCommit','phaseBEvidenceCommit','phaseBLedgerSha256','phaseBReviewSha256','reviewVerdict','schemaVersion') | Sort-Object
$actualBToCKeys=@($bToC.PSObject.Properties.Name) | Sort-Object
if (Compare-Object $expectedBToCKeys $actualBToCKeys) { throw 'B-to-C handoff shape mismatch' }
if ($bToC.schemaVersion -cne 'phase-b-to-c-contract-handoff-v1' -or $bToC.reviewVerdict -cne 'PASS' -or [string]$bToC.phaseBCodeCommit -cne $phaseBCodeCommit -or [string]$bToC.phaseBEvidenceCommit -cne $phaseBEvidenceCommit -or [string]$bToC.phaseBReviewSha256 -cne $phaseBReviewSha256 -or [string]$bToC.phaseBLedgerSha256 -cne [string]$phaseBLedgerProjection.ledgerHash -or (Compare-Object $expectedBEvidencePaths @($bToC.evidencePaths | Sort-Object)) -or (Compare-Object $bContractPaths @($bToC.contractSha256.PSObject.Properties.Name | Sort-Object))) { throw 'B-to-C handoff identity/scope mismatch' }
foreach($path in $bContractPaths) { if ([string]$bToC.contractSha256.PSObject.Properties[$path].Value -cne [string]$phaseBContractSha256.PSObject.Properties[$path].Value) { throw "B-to-C recorded contract hash mismatch: $path" } }
$rawBToCBaseCommit=git rev-parse HEAD
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'freeze B-to-C handoff parent'
$bToCBaseCommit=($rawBToCBaseCommit -join "`n").Trim()
$bToCPaths=@('docs/verification/checkpoints/b-to-c-contract-handoff.json')
Invoke-PhaseCExactCommit -Label 'B-to-C contract handoff' -Message 'docs: authenticate Phase B frontend contracts' -Paths $bToCPaths
$rawBToCContractHandoffCommit=git rev-parse HEAD
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'freeze B-to-C handoff commit'
$bToCContractHandoffCommit=($rawBToCContractHandoffCommit -join "`n").Trim()
if ($bToCContractHandoffCommit -notmatch '^[0-9a-f]{40}$') { throw 'invalid B-to-C handoff commit' }
$rawBToCParent=git rev-parse "$bToCContractHandoffCommit^"
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read B-to-C handoff parent'
if ((($rawBToCParent -join "`n").Trim()) -cne $bToCBaseCommit) { throw 'B-to-C handoff parent mismatch' }
$rawBToCScope=@(git diff-tree --no-commit-id --name-only -r $bToCContractHandoffCommit)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read B-to-C handoff diff'
if (Compare-Object $bToCPaths @($rawBToCScope | Sort-Object)) { throw 'B-to-C handoff commit scope mismatch' }
$committedBToCHashJson=@(& $python scripts/phase_c_evidence.py hash-paths --commit $bToCContractHandoffCommit --paths $bToCPath)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'hash committed B-to-C handoff raw blob'
$committedBToCHashMap=(($committedBToCHashJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
if ([string]$committedBToCHashMap.PSObject.Properties[$bToCPath].Value -notmatch '^sha256:[0-9a-f]{64}$') { throw 'committed B-to-C handoff digest missing' }
$committedBToCJson=@(git show "${bToCContractHandoffCommit}:$bToCPath")
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read committed B-to-C handoff blob'
$committedBToC=(($committedBToCJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
if ($committedBToC.schemaVersion -cne 'phase-b-to-c-contract-handoff-v1' -or [string]$committedBToC.phaseBCodeCommit -cne $phaseBCodeCommit -or [string]$committedBToC.phaseBEvidenceCommit -cne $phaseBEvidenceCommit -or $committedBToC.reviewVerdict -cne 'PASS' -or [string]$committedBToC.phaseBReviewSha256 -cne $phaseBReviewSha256 -or [string]$committedBToC.phaseBLedgerSha256 -cne [string]$phaseBLedgerProjection.ledgerHash -or (Compare-Object $expectedBEvidencePaths @($committedBToC.evidencePaths | Sort-Object)) -or (Compare-Object $bContractPaths @($committedBToC.contractSha256.PSObject.Properties.Name | Sort-Object))) { throw 'committed B-to-C handoff bindings mismatch' }
$env:B_TO_C_CONTRACT_HANDOFF_COMMIT=$bToCContractHandoffCommit
```

Record all three SHAs plus the immutable contract-hash map in the execution handoff. Any mismatch blocks C3; it is never repaired by copying a working-tree file over the reviewed B blob.

- [ ] **Step 1: Create the complete ruleset fixture**

The root has exactly these keys and values:

```json
{
  "schemaVersion": "1.0",
  "ruleSetVersion": "forzy-operational-triage-v1",
  "modeTitles": {
    "now": "Situação agora",
    "historical": "Situação naquele instante"
  },
  "conditionLabels": {
    "normal": "normal",
    "watch": "em revisão",
    "alert": "alerta para revisão",
    "insufficient_data": "não avaliável",
    "unknown": "desconhecida"
  },
  "dataTrustLabels": {
    "sufficient": "Dados suficientes",
    "degraded": "Confiança degradada",
    "insufficient": "Dados insuficientes"
  },
  "summaryTemplates": {
    "current_no_relevant_deviation": "Sem desvio relevante detectado neste baseline.",
    "current_deviation_for_review": "Desvio para revisão.",
    "current_priority_deviation_for_review": "Desvio persistente prioritário para revisão.",
    "current_condition_not_evaluable": "Condição atual não avaliável com os dados disponíveis.",
    "last_known_condition": "Última condição conhecida em {conditionAsOf}: {conditionLabel}.",
    "expected_idle_last_known": "Coleta não esperada agora. Última condição conhecida em {conditionAsOf}: {conditionLabel}.",
    "expected_idle_no_condition": "Coleta não esperada agora e nenhuma condição anterior está disponível.",
    "historical_no_relevant_deviation": "Sem desvio relevante detectado neste baseline no instante selecionado.",
    "historical_candidate_for_review": "Candidato histórico para revisão; não representa condição atual.",
    "historical_condition_not_evaluable": "Condição histórica não avaliável com os dados disponíveis.",
    "context_gap": "O TwinOps não possui dados para o intervalo selecionado.",
    "data_source_verification_required": "Verifique a aquisição antes de interpretar a condição."
  },
  "nextCheckOrder": [
    "monitor_next_expected_sample", "review_evidence", "compare_previous_cycle",
    "review_data_gap", "verify_acquisition", "review_sensor_chain_evidence",
    "escalate_engineering_review"
  ],
  "nextCheckLabels": {
    "monitor_next_expected_sample": "Monitorar a próxima amostra esperada.",
    "review_evidence": "Revisar evidências numéricas e qualidade.",
    "compare_previous_cycle": "Comparar com o ciclo causalmente anterior.",
    "review_data_gap": "Revisar o intervalo sem cobertura de dados.",
    "verify_acquisition": "Verificar aquisição, timestamps e último sucesso.",
    "review_sensor_chain_evidence": "Revisar digitalmente timestamps, tentativas, flags e integração do sensor.",
    "escalate_engineering_review": "Encaminhar a evidência para revisão de engenharia."
  },
  "limitationOrder": [
    "not_failure_probability", "component_not_localized", "sensor_placement_unvalidated",
    "source_timestamp_assumed", "data_partial", "data_quality_degraded", "data_stale",
    "historical_context_only", "no_causal_assessment", "lead_time_not_validated",
    "site_procedure_unavailable"
  ],
  "limitationLabels": {
    "not_failure_probability": "O score não é probabilidade de falha.",
    "component_not_localized": "A origem mecânica do desvio não foi localizada.",
    "sensor_placement_unvalidated": "A posição física de S1/S2 não foi validada.",
    "source_timestamp_assumed": "O horário usa a hipótese temporal declarada pela origem.",
    "data_partial": "Parte dos dados esperados está ausente.",
    "data_quality_degraded": "A qualidade dos dados reduz a confiança da avaliação.",
    "data_stale": "A condição exibida não representa uma leitura atual.",
    "historical_context_only": "Este contexto é retrospectivo e não representa a condição atual.",
    "no_causal_assessment": "A evidência não demonstra causa mecânica.",
    "lead_time_not_validated": "Antecedência de falha não foi validada.",
    "site_procedure_unavailable": "O TwinOps não possui procedimento operacional autorizado do local."
  },
  "baseLimitationCodes": [
    "not_failure_probability", "component_not_localized", "sensor_placement_unvalidated",
    "lead_time_not_validated", "site_procedure_unavailable"
  ],
  "conditionalLimitations": {
    "sourceTimestampAssumed": "source_timestamp_assumed",
    "dataPartial": "data_partial",
    "dataQualityDegraded": "data_quality_degraded",
    "dataStale": "data_stale",
    "historicalContext": "historical_context_only",
    "noCausalAssessment": "no_causal_assessment"
  },
  "rows": [
    {
      "id": "now_received_normal_complete_fresh_sufficient",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["current"], "conditionSource": ["live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["received_now"], "collectionExpectation": ["expected_now"], "conditionState": ["normal"], "dataAvailability": ["complete"], "dataFreshness": ["fresh"], "dataTrust": ["sufficient"] },
      "then": { "summaryCode": "current_no_relevant_deviation", "triageState": "monitor", "nextChecks": [{ "code": "monitor_next_expected_sample" }] }
    },
    {
      "id": "now_received_watch_complete_fresh_sufficient",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["current"], "conditionSource": ["live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["received_now"], "collectionExpectation": ["expected_now"], "conditionState": ["watch"], "dataAvailability": ["complete"], "dataFreshness": ["fresh"], "dataTrust": ["sufficient"] },
      "then": { "summaryCode": "current_deviation_for_review", "triageState": "review_candidate", "nextChecks": [{ "code": "review_evidence" }, { "code": "compare_previous_cycle", "requires": "hasComparablePreviousCycle" }] }
    },
    {
      "id": "now_received_alert_complete_fresh_sufficient",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["current"], "conditionSource": ["live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["received_now"], "collectionExpectation": ["expected_now"], "conditionState": ["alert"], "dataAvailability": ["complete"], "dataFreshness": ["fresh"], "dataTrust": ["sufficient"] },
      "then": { "summaryCode": "current_priority_deviation_for_review", "triageState": "review_candidate", "nextChecks": [{ "code": "review_evidence" }, { "code": "compare_previous_cycle", "requires": "hasComparablePreviousCycle" }, { "code": "escalate_engineering_review" }] }
    },
    {
      "id": "now_received_watch_degraded",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["current"], "conditionSource": ["live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["received_now"], "collectionExpectation": ["expected_now"], "conditionState": ["watch"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["fresh"], "dataTrust": ["degraded", "insufficient"] },
      "then": { "summaryCode": "current_deviation_for_review", "triageState": "review_candidate", "nextChecks": [{ "code": "review_evidence" }, { "code": "compare_previous_cycle", "requires": "hasComparablePreviousCycle" }, { "code": "verify_acquisition" }, { "code": "review_sensor_chain_evidence", "requires": "hasSensorChainEvidence" }] }
    },
    {
      "id": "now_received_alert_degraded",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["current"], "conditionSource": ["live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["received_now"], "collectionExpectation": ["expected_now"], "conditionState": ["alert"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["fresh"], "dataTrust": ["degraded", "insufficient"] },
      "then": { "summaryCode": "current_priority_deviation_for_review", "triageState": "review_candidate", "nextChecks": [{ "code": "review_evidence" }, { "code": "compare_previous_cycle", "requires": "hasComparablePreviousCycle" }, { "code": "verify_acquisition" }, { "code": "review_sensor_chain_evidence", "requires": "hasSensorChainEvidence" }] }
    },
    {
      "id": "now_received_normal_degraded",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["received_now"], "collectionExpectation": ["expected_now"], "conditionState": ["normal"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["fresh"], "dataTrust": ["degraded", "insufficient"] },
      "then": { "summaryCode": "data_source_verification_required", "triageState": "verify_data_source", "nextChecks": [{ "code": "verify_acquisition" }, { "code": "review_sensor_chain_evidence", "requires": "hasSensorChainEvidence" }] }
    },
    {
      "id": "now_received_insufficient_assessed",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["current"], "conditionSource": ["live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["received_now"], "collectionExpectation": ["expected_now"], "conditionState": ["insufficient_data"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["fresh"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "current_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "monitor_next_expected_sample" }] }
    },
    {
      "id": "now_received_insufficient_no_assessment",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["received_now"], "collectionExpectation": ["expected_now"], "conditionState": ["insufficient_data"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["fresh"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "current_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "monitor_next_expected_sample" }] }
    },
    {
      "id": "now_received_unknown_complete",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["received_now"], "collectionExpectation": ["expected_now"], "conditionState": ["unknown"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["fresh"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "current_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "monitor_next_expected_sample" }] }
    },
    {
      "id": "now_last_known_condition",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["last_known"], "conditionSource": ["live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["last_known"], "collectionExpectation": ["expected_now"], "conditionState": ["normal", "watch", "alert", "insufficient_data"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["stale"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "last_known_condition", "triageState": "review_candidate", "nextChecks": [{ "code": "review_evidence", "requires": "hasDriverEvidence" }, { "code": "verify_acquisition" }] }
    },
    {
      "id": "now_last_known_normal_suppressed",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["last_known"], "collectionExpectation": ["expected_now"], "conditionState": ["normal"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["stale"], "dataTrust": ["degraded", "insufficient"] },
      "then": { "summaryCode": "data_source_verification_required", "triageState": "verify_data_source", "nextChecks": [{ "code": "verify_acquisition" }, { "code": "review_sensor_chain_evidence", "requires": "hasSensorChainEvidence" }] }
    },
    {
      "id": "now_last_known_insufficient_no_assessment",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["last_known"], "collectionExpectation": ["expected_now"], "conditionState": ["insufficient_data"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["stale"], "dataTrust": ["insufficient"] },
      "then": { "summaryCode": "current_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "verify_acquisition" }] }
    },
    {
      "id": "now_last_known_unknown",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["last_known"], "collectionExpectation": ["expected_now"], "conditionState": ["unknown"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["stale"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "data_source_verification_required", "triageState": "verify_data_source", "nextChecks": [{ "code": "verify_acquisition" }, { "code": "review_sensor_chain_evidence", "requires": "hasSensorChainEvidence" }] }
    },
    {
      "id": "now_policy_unknown_last_known_condition",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["last_known"], "conditionSource": ["live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["last_known"], "collectionExpectation": ["not_applicable"], "conditionState": ["normal", "watch", "alert", "insufficient_data"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["unknown"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "last_known_condition", "triageState": "review_candidate", "nextChecks": [{ "code": "review_evidence", "requires": "hasDriverEvidence" }, { "code": "verify_acquisition" }] }
    },
    {
      "id": "now_policy_unknown_last_known_normal_suppressed",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["last_known"], "collectionExpectation": ["not_applicable"], "conditionState": ["normal"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["unknown"], "dataTrust": ["degraded", "insufficient"] },
      "then": { "summaryCode": "data_source_verification_required", "triageState": "verify_data_source", "nextChecks": [{ "code": "verify_acquisition" }, { "code": "review_sensor_chain_evidence", "requires": "hasSensorChainEvidence" }] }
    },
    {
      "id": "now_policy_unknown_last_known_insufficient_no_assessment",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["last_known"], "collectionExpectation": ["not_applicable"], "conditionState": ["insufficient_data"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["unknown"], "dataTrust": ["insufficient"] },
      "then": { "summaryCode": "current_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "verify_acquisition" }] }
    },
    {
      "id": "now_policy_unknown_last_known_unknown",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["last_known"], "collectionExpectation": ["not_applicable"], "conditionState": ["unknown"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["unknown"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "data_source_verification_required", "triageState": "verify_data_source", "nextChecks": [{ "code": "verify_acquisition" }, { "code": "review_sensor_chain_evidence", "requires": "hasSensorChainEvidence" }] }
    },
    {
      "id": "now_expected_idle_candidate",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["last_known"], "conditionSource": ["live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["expected_idle"], "collectionExpectation": ["expected_idle"], "conditionState": ["watch", "alert"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["fresh", "stale"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "expected_idle_last_known", "triageState": "review_candidate", "nextChecks": [{ "code": "monitor_next_expected_sample" }, { "code": "review_evidence", "requires": "hasDriverEvidence" }] }
    },
    {
      "id": "now_expected_idle_non_candidate",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["last_known"], "conditionSource": ["live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["expected_idle"], "collectionExpectation": ["expected_idle"], "conditionState": ["normal", "insufficient_data"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["fresh", "stale"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "expected_idle_last_known", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "monitor_next_expected_sample" }, { "code": "review_evidence", "requires": "hasDriverEvidence" }] }
    },
    {
      "id": "now_expected_idle_normal_suppressed",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["expected_idle"], "collectionExpectation": ["expected_idle"], "conditionState": ["normal"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["fresh", "stale", "unknown"], "dataTrust": ["degraded", "insufficient"] },
      "then": { "summaryCode": "expected_idle_no_condition", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "monitor_next_expected_sample" }] }
    },
    {
      "id": "now_expected_idle_insufficient_no_assessment",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["expected_idle"], "collectionExpectation": ["expected_idle"], "conditionState": ["insufficient_data"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["fresh", "stale", "unknown"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "expected_idle_no_condition", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "monitor_next_expected_sample" }] }
    },
    {
      "id": "now_expected_idle_unknown",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["expected_idle"], "collectionExpectation": ["expected_idle"], "conditionState": ["unknown"], "dataAvailability": ["complete", "partial", "unavailable"], "dataFreshness": ["fresh", "stale", "unknown"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "expected_idle_no_condition", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "monitor_next_expected_sample" }] }
    },
    {
      "id": "now_unavailable_expected_now",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["unavailable"], "collectionExpectation": ["expected_now"], "conditionState": ["unknown"], "dataAvailability": ["unavailable"], "dataFreshness": ["unknown"], "dataTrust": ["insufficient"] },
      "then": { "summaryCode": "data_source_verification_required", "triageState": "verify_data_source", "nextChecks": [{ "code": "verify_acquisition" }, { "code": "review_sensor_chain_evidence", "requires": "hasSensorChainEvidence" }] }
    },
    {
      "id": "now_unavailable_expected_idle",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["unavailable"], "collectionExpectation": ["expected_idle"], "conditionState": ["unknown"], "dataAvailability": ["unavailable"], "dataFreshness": ["unknown"], "dataTrust": ["insufficient"] },
      "then": { "summaryCode": "current_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "monitor_next_expected_sample" }] }
    },
    {
      "id": "now_unavailable_normal_suppressed",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["unavailable"], "collectionExpectation": ["expected_now", "expected_idle"], "conditionState": ["normal"], "dataAvailability": ["unavailable"], "dataFreshness": ["unknown"], "dataTrust": ["insufficient"] },
      "then": { "summaryCode": "data_source_verification_required", "triageState": "verify_data_source", "nextChecks": [{ "code": "verify_acquisition" }] }
    },
    {
      "id": "now_unavailable_insufficient_no_assessment",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["unavailable"], "collectionExpectation": ["expected_now", "expected_idle"], "conditionState": ["insufficient_data"], "dataAvailability": ["unavailable"], "dataFreshness": ["unknown"], "dataTrust": ["insufficient"] },
      "then": { "summaryCode": "current_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "verify_acquisition" }] }
    },
    {
      "id": "now_policy_unknown_unavailable",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["unavailable"], "collectionExpectation": ["not_applicable"], "conditionState": ["unknown"], "dataAvailability": ["unavailable"], "dataFreshness": ["unknown"], "dataTrust": ["insufficient"] },
      "then": { "summaryCode": "data_source_verification_required", "triageState": "verify_data_source", "nextChecks": [{ "code": "verify_acquisition" }, { "code": "review_sensor_chain_evidence", "requires": "hasSensorChainEvidence" }] }
    },
    {
      "id": "now_policy_unknown_unavailable_normal_suppressed",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["unavailable"], "collectionExpectation": ["not_applicable"], "conditionState": ["normal"], "dataAvailability": ["unavailable"], "dataFreshness": ["unknown"], "dataTrust": ["insufficient"] },
      "then": { "summaryCode": "data_source_verification_required", "triageState": "verify_data_source", "nextChecks": [{ "code": "verify_acquisition" }] }
    },
    {
      "id": "now_policy_unknown_unavailable_insufficient_no_assessment",
      "when": { "viewMode": ["now"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["unavailable"], "collectionExpectation": ["not_applicable"], "conditionState": ["insufficient_data"], "dataAvailability": ["unavailable"], "dataFreshness": ["unknown"], "dataTrust": ["insufficient"] },
      "then": { "summaryCode": "current_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "verify_acquisition" }] }
    },
    {
      "id": "historical_normal",
      "when": { "viewMode": ["historical"], "conditionTemporalScope": ["historical"], "conditionSource": ["historical_walk_forward", "live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["historical_context"], "collectionExpectation": ["not_applicable"], "conditionState": ["normal"], "dataAvailability": ["complete"], "dataFreshness": ["historical"], "dataTrust": ["sufficient"] },
      "then": { "summaryCode": "historical_no_relevant_deviation", "triageState": "review_history", "nextChecks": [{ "code": "review_evidence", "requires": "hasDriverEvidence" }, { "code": "compare_previous_cycle", "requires": "hasComparablePreviousCycle" }] }
    },
    {
      "id": "historical_normal_suppressed",
      "when": { "viewMode": ["historical"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["historical_context"], "collectionExpectation": ["not_applicable"], "conditionState": ["normal"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["historical"], "dataTrust": ["degraded", "insufficient"] },
      "then": { "summaryCode": "historical_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "review_evidence" }] }
    },
    {
      "id": "historical_candidate",
      "when": { "viewMode": ["historical"], "conditionTemporalScope": ["historical"], "conditionSource": ["historical_walk_forward", "live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["historical_context"], "collectionExpectation": ["not_applicable"], "conditionState": ["watch", "alert"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["historical"], "dataTrust": ["sufficient", "degraded"] },
      "then": { "summaryCode": "historical_candidate_for_review", "triageState": "review_candidate", "nextChecks": [{ "code": "review_evidence" }, { "code": "compare_previous_cycle", "requires": "hasComparablePreviousCycle" }] }
    },
    {
      "id": "historical_insufficient_assessed",
      "when": { "viewMode": ["historical"], "conditionTemporalScope": ["historical"], "conditionSource": ["historical_walk_forward", "live_assessment"], "conditionAsOf": ["rfc3339"], "collectionState": ["historical_context"], "collectionExpectation": ["not_applicable"], "conditionState": ["insufficient_data"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["historical"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "historical_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "review_evidence" }] }
    },
    {
      "id": "historical_insufficient_no_assessment",
      "when": { "viewMode": ["historical"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["historical_context"], "collectionExpectation": ["not_applicable"], "conditionState": ["insufficient_data"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["historical"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "historical_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "review_evidence" }] }
    },
    {
      "id": "historical_unknown",
      "when": { "viewMode": ["historical"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["historical_context"], "collectionExpectation": ["not_applicable"], "conditionState": ["unknown"], "dataAvailability": ["complete", "partial"], "dataFreshness": ["historical"], "dataTrust": ["sufficient", "degraded", "insufficient"] },
      "then": { "summaryCode": "historical_condition_not_evaluable", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "review_evidence" }] }
    },
    {
      "id": "historical_gap",
      "when": { "viewMode": ["historical"], "conditionTemporalScope": ["none"], "conditionSource": ["none"], "conditionAsOf": [null], "collectionState": ["historical_gap"], "collectionExpectation": ["not_applicable"], "conditionState": ["unknown"], "dataAvailability": ["gap"], "dataFreshness": ["historical"], "dataTrust": ["insufficient"] },
      "then": { "summaryCode": "context_gap", "triageState": "insufficient_evidence", "nextChecks": [{ "code": "review_data_gap" }] }
    }
  ]
}
```

The matcher treats every ordinary `when` array as exact membership; no wildcard syntax exists. `conditionAsOf` is the sole typed predicate: `[null]` accepts only literal null and `["rfc3339"]` accepts only a non-null timestamp already validated as canonical UTC millisecond precision. Every row includes `conditionTemporalScope`, `conditionSource` and `conditionAsOf`; `then` cannot contain or overwrite those backend-owned facts. Conditional checks recognize only `hasComparablePreviousCycle`, `hasSensorChainEvidence` and `hasDriverEvidence`. The seven `now_policy_unknown_*` rows are the only `now` rows that accept `collectionExpectation="not_applicable"`; each requires `dataFreshness="unknown"` and a B-owned `last_known|unavailable` collection state. They preserve missing/invalid-policy facts instead of borrowing an expected-now/idle row. Valid B facts with `collectionState="expected_idle"` may be `fresh`, `stale` or, where evidence is absent, `unknown`; the ruleset preserves that freshness literally. `conditionState="insufficient_data"|"unknown"` is not a trust proxy: current `received_now/expected_now/fresh` facts cover every B-valid trust branch, including `complete/fresh/sufficient`, and the composed B invariant validator rejects impossible availability/quality/trust crossings before the matcher. The only row containing `escalate_engineering_review` is `now_received_alert_complete_fresh_sufficient`.

- [ ] **Step 2: Write failing canonicalization and matrix tests**

```js
import liveDecisionFactsCasesV1 from "../../contracts/timeline/v1/fixtures/live-decision-facts-v1-cases.json";
import { assertTimelineDecisionFactsV1 } from "../contracts/timelineV1.js";
import {
  DISPLAY_CONTEXT_V1_FIELDS,
  assertDisplayContextV1,
  cloneAndFreezeDisplayContextV1,
  toOperationalDecisionInput,
} from "../displayContext/displayContextV1.js";
import { DISPLAY_CONTEXT_V1_FIXTURES } from "../displayContext/displayContextV1.fixtures.js";
import bLiveDisplayContextCasesV1 from "../../contracts/v2/rulesets/fixtures/b-live-display-context-v1-cases.json";

it("hashes identical logical JSON identically", async () => {
  expect(await sha256Text(canonicalJson({ b: 2, a: 1 }))).toBe(
    await sha256Text(canonicalJson({ a: 1, b: 2 })),
  );
});

const sharedBDecisionFacts = Object.freeze(Object.fromEntries(
  liveDecisionFactsCasesV1.cases.map(({ caseId, expectedDecisionFacts }) => (
    [caseId, Object.freeze(structuredClone(expectedDecisionFacts))]
  )),
));
expect(Object.keys(liveDecisionFactsCasesV1).sort()).toEqual(["cases", "schemaVersion"]);
expect(liveDecisionFactsCasesV1.schemaVersion).toBe("1.0");
expect(Object.keys(sharedBDecisionFacts)).toHaveLength(liveDecisionFactsCasesV1.cases.length);

expect(Object.keys(bLiveDisplayContextCasesV1).sort()).toEqual(["cases", "schemaVersion"]);
expect(bLiveDisplayContextCasesV1.schemaVersion).toBe("1.0");
const explicitContextCaseIds = bLiveDisplayContextCasesV1.cases.map(({ caseId }) => caseId);
expect(new Set(explicitContextCaseIds).size).toBe(explicitContextCaseIds.length);
expect(explicitContextCaseIds).toEqual([...explicitContextCaseIds].sort());
const completeContextByBCaseId = Object.freeze(Object.fromEntries(
  bLiveDisplayContextCasesV1.cases.map(({ caseId, displayContext }) => (
    [caseId, cloneAndFreezeDisplayContextV1(displayContext)]
  )),
));
const bCaseIds = Object.keys(sharedBDecisionFacts).sort();
expect(Object.keys(completeContextByBCaseId).sort()).toEqual(bCaseIds);
expect(bLiveDisplayContextCasesV1.cases.map(({ caseId }) => caseId).sort()).toEqual(bCaseIds);

const contextForBCase = (caseId) => {
  if (!Object.hasOwn(sharedBDecisionFacts, caseId) || !Object.hasOwn(completeContextByBCaseId, caseId)) {
    throw new TypeError(`missing explicit complete display context for B case ${caseId}`);
  }
  const facts = assertTimelineDecisionFactsV1(sharedBDecisionFacts[caseId]);
  const context = assertDisplayContextV1(completeContextByBCaseId[caseId]);
  const flattened = toOperationalDecisionInput(context);
  for (const [key, value] of Object.entries(facts)) {
    const displayKey = key === "schemaVersion" ? "decisionFactsSchemaVersion" : key;
    expect(flattened[displayKey]).toEqual(value);
  }
  return context;
};

it.each([
  ["expected_idle_fresh_boundary", "expected_idle_last_known"],
  [
    "received_now_insufficient_assessed_complete_fresh_sufficient",
    "current_condition_not_evaluable",
  ],
])("consumes B fixture %s literally without recomputing facts", async (caseId, summaryCode) => {
  const facts = sharedBDecisionFacts[caseId];
  expect(assertTimelineDecisionFactsV1(facts)).toBe(facts);
  const displayContext = contextForBCase(caseId);
  const result = await buildOperationalDecisionViewV1(
    displayContext,
    { cryptoImpl: crypto },
  );
  expect(result).toMatchObject({
    conditionState: facts.conditionState,
    conditionTemporalScope: facts.conditionTemporalScope,
    conditionAsOf: facts.conditionAsOf,
    conditionSource: facts.conditionSource,
    collectionState: facts.collectionState,
    collectionExpectation: facts.collectionExpectation,
    dataAvailability: facts.dataAvailability,
    dataFreshness: facts.dataFreshness,
    dataTrust: facts.dataTrust,
    summaryCode,
  });
});

it.each(decisionCases)("maps $name through the closed ruleset", async ({ displayContext, expected }) => {
  expect(assertDisplayContextV1(displayContext)).toBe(displayContext);
  const result = await buildOperationalDecisionViewV1(displayContext, { cryptoImpl: crypto });
  expect(result).toMatchObject(expected);
  expect(result.ruleSetVersion).toBe("forzy-operational-triage-v1");
  expect(result.ruleSetHash).toMatch(/^sha256:[0-9a-f]{64}$/);
});

it("fails closed when no row matches", async () => {
  await expect(buildOperationalDecisionViewV1({
    ...liveNormalDisplayContext,
    collectionState: "historical_gap",
  }, { cryptoImpl: crypto })).rejects.toThrow(/exactly one decision rule/);
});

const policyUnknownLastKnownContext = contextForBCase("missing_policy_retained_complete_watch");
const policyUnknownUnavailableContext = contextForBCase("missing_policy_without_usable_evidence");

it.each([
  ["missing retained", "missing_policy_retained_complete_watch", "last_known"],
  ["invalid retained", "invalid_policy_retained_complete_watch", "last_known"],
  ["missing unavailable", "missing_policy_without_usable_evidence", "unavailable"],
  ["invalid unavailable", "invalid_policy_without_usable_evidence", "unavailable"],
])("keeps the exact backend unknown-policy tuple for %s", async (
  _name, caseId, collectionState,
) => {
  const displayContext = contextForBCase(caseId);
  expect(displayContext).toMatchObject({
    collectionState,
    collectionExpectation: "not_applicable",
    dataFreshness: "unknown",
  });
  const result = await buildOperationalDecisionViewV1(displayContext, { cryptoImpl: crypto });
  expect(result).toMatchObject({
    collectionState,
    collectionExpectation: "not_applicable",
    dataFreshness: "unknown",
  });
});

it.each([
  { ...policyUnknownLastKnownContext, collectionExpectation: "expected_now" },
  { ...policyUnknownLastKnownContext, dataFreshness: "stale" },
])("rejects a frontend repair of unknown-policy facts", async (displayContext) => {
  await expect(buildOperationalDecisionViewV1(displayContext, { cryptoImpl: crypto }))
    .rejects.toThrow(/decision facts|exactly one decision rule/);
});

it("binds both identifiers to the complete canonical DisplayContextV1", async () => {
  const original = DISPLAY_CONTEXT_V1_FIXTURES.nowZero;
  const changedOutsideDecisionInput = validDisplayContextHashMutations.publicAcquisition(original);
  expect(toOperationalDecisionInput(changedOutsideDecisionInput)).toEqual(
    toOperationalDecisionInput(original),
  );
  const [before, after] = await Promise.all([
    buildOperationalDecisionViewV1(original, { cryptoImpl: crypto }),
    buildOperationalDecisionViewV1(changedOutsideDecisionInput, { cryptoImpl: crypto }),
  ]);
  expect(after.displayContextHash).not.toBe(before.displayContextHash);
  expect(after.decisionId).not.toBe(before.decisionId);
});

it.each(DISPLAY_CONTEXT_V1_FIELDS)("covers hash relevance or closed-constant rejection for %s", async (field) => {
  await assertHashMutationOrClosedConstant(field, {
    fixture: DISPLAY_CONTEXT_V1_FIXTURES.nowZero,
    validMutations: validDisplayContextHashMutations,
    rejectedConstants: rejectedDisplayContextConstants,
    cryptoImpl: crypto,
  });
});
```

`sharedBDecisionFacts` reads only `caseId + expectedDecisionFacts`; it never imports the B test hydrator or interprets `policyEvidenceKind`, windows, frame ages, quality descriptors or gaps. The C-owned `b-live-display-context-v1-cases.json` contains one **full literal `DisplayContextV1`** per B case ID—no base fixture, spread, default or runtime fact hydrator. Its root is exactly `{schemaVersion:"1.0",cases:[...]}`; each case is exactly `{caseId,displayContext}`, case IDs are unique, sorted and equal as a set to B's IDs. `contextForBCase` validates both complete objects, compares all eleven B fields byte-for-byte and fails on any missing/extra ID or mismatch. The two mandatory fixture identities are `expected_idle_fresh_boundary` (`watch/last_known/live_assessment + expected_idle/expected_idle/complete/fresh/sufficient`) and `received_now_insufficient_assessed_complete_fresh_sufficient` (`insufficient_data/current/live_assessment + received_now/expected_now/complete/fresh/sufficient`). Their complete contexts pass C1, match one C row, and copy those facts into decision output. Any mismatch fails instead of prompting C to derive a replacement.

`policyUnknownLastKnownContext` and `policyUnknownUnavailableContext` are the complete validated literal entries for B's `missing_policy_retained_complete_watch` and `missing_policy_without_usable_evidence` rows. The first preserves `watch/last_known/live_assessment`, non-null condition/episode times and `complete/unknown/sufficient`; the second preserves `unknown/none/none/null/null` and `unavailable/unknown/insufficient`. The invalid-policy counterparts must be byte-identical in expected facts but remain separately named complete cases. They contain no policy object or browser default. Task C5 later parity-tests its missing/invalid-policy adapter outputs against these exact shared rows before provider integration.

Every `decisionCases` entry and every accepted Cartesian tuple must reference a full C1-validated context from an explicit immutable corpus keyed by the exact eleven-field fact canonical JSON; no lookup has a default. The corpus entry includes all six coherence groups—`channels`, `assessment`, `anchor`, `exportable* + driver IDs`, `publicProvenance + publicModel + publicAcquisition`, and `capabilities`—rather than cloning `nowZero`. Before matching, assert (a) availability iff channel cardinality, (b) condition source/scope/time/episode iff the exact assessment, and (c) anchor/pair/source/batch plus resolvable evidence iff capabilities. Thus, for example, a `complete` B fact gets two same-pair channels, an assessed `current/live_assessment` fact gets the matching live assessment/time/episode, and `none/none/null/null` gets null assessment and no driver; an unavailable fact gets null channels/assessment/anchor and explicit unavailable acquisition. Explicit corpus values may differ even when decision facts match; they are never inferred from condition/trust labels.

The table includes live normal/watch/alert trusted; watch/alert partial or degraded with `current/live_assessment/non-null`; normal degraded with the B-owned `none/none/null`; and current `insufficient_data` split between assessed and no-assessment facts. The latter plus current `unknown` are table-driven independently across every B-valid trust value and include the non-collapsible `complete/fresh/sufficient` cases. It separately covers expected-now `last_known`, every B-valid `expected_idle` freshness branch (including `fresh`), expected-policy `unavailable`, and unknown-policy `last_known|unavailable` for every structurally valid relevant branch. Historical cases cover normal supported/suppressed, watch/alert archive and live selected segments, assessed/no-assessment insufficiency, unknown and gap. Generate the closed fact-enum Cartesian matrix, pass facts through composed Foundation validation with no defaults/coercion, require an explicit complete-context corpus hit for each accepted tuple and assert **exactly one** rule. A validator-accepted fact lacking a corpus entry is a test failure, never an instruction to synthesize a context. Every rejected fact or adversarial fact/context crossing fails before matching.

- [ ] **Step 3: Run tests to verify RED**

Checked RED Run: capture output from `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/decisionSupport/canonicalJson.test.js src/decisionSupport/operationalDecisionV1.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C3 expected-red tests' @(1)`, then require the captured failure to name the missing C3 modules/behavior.

Expected: FAIL because the modules do not exist.

- [ ] **Step 4: Implement canonical hashing and one-rule matching**

```js
const FORBIDDEN_CANONICAL_KEYS = new Set([
  "proto", "prototype", "constructor", "dsn", "password", "secret", "token",
  "authorization", "cookie", "apikey", "privatekey", "raw", "payload",
]);

const normalizedKey = (key) => key.replace(/[-_]/g, "").toLowerCase();

function canonicalNode(value, path, active) {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Object.is(value, -0)) throw new TypeError(`${path} must be a finite non-negative-zero JSON number`);
    return JSON.stringify(value);
  }
  if (typeof value !== "object") throw new TypeError(`${path} is not JSON data`);
  if (active.has(value)) throw new TypeError(`${path} contains a cycle`);
  active.add(value);
  try {
    if (Array.isArray(value)) {
      if (Object.getPrototypeOf(value) !== Array.prototype) throw new TypeError(`${path} must be a plain array`);
      const ownKeys = Reflect.ownKeys(value);
      if (ownKeys.some((key) => typeof key === "symbol")) throw new TypeError(`${path} has a symbol key`);
      const expected = new Set(["length", ...Array.from({ length: value.length }, (_, i) => String(i))]);
      if (ownKeys.some((key) => !expected.has(key)) || expected.size !== ownKeys.length) throw new TypeError(`${path} must be dense and have no extra properties`);
      return `[${Array.from({ length: value.length }, (_, i) => {
        const descriptor = Object.getOwnPropertyDescriptor(value, String(i));
        if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) throw new TypeError(`${path}[${i}] must be an enumerable data property`);
        return canonicalNode(descriptor.value, `${path}[${i}]`, active);
      }).join(",")}]`;
    }
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) throw new TypeError(`${path} must be a plain object`);
    const ownKeys = Reflect.ownKeys(value);
    if (ownKeys.some((key) => typeof key === "symbol")) throw new TypeError(`${path} has a symbol key`);
    const keys = ownKeys.sort();
    return `{${keys.map((key) => {
      if (FORBIDDEN_CANONICAL_KEYS.has(normalizedKey(key))) throw new TypeError(`${path}.${key} is forbidden`);
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) throw new TypeError(`${path}.${key} must be an enumerable data property`);
      return `${JSON.stringify(key)}:${canonicalNode(descriptor.value, `${path}.${key}`, active)}`;
    }).join(",")}}`;
  } finally {
    active.delete(value);
  }
}

export function canonicalJson(value) {
  return canonicalNode(value, "$", new WeakSet());
}

export async function sha256Text(text, cryptoImpl = globalThis.crypto) {
  if (typeof text !== "string") throw new TypeError("sha256Text text must be a string");
  if (!cryptoImpl?.subtle) throw new TypeError("Web Crypto SHA-256 is required");
  const digest = await cryptoImpl.subtle.digest("SHA-256", new TextEncoder().encode(text));
  if (!(digest instanceof ArrayBuffer) || digest.byteLength !== 32) throw new TypeError("Web Crypto returned an invalid SHA-256 digest");
  return `sha256:${[...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

export const DISPLAY_CONTEXT_HASH_CONTRACT_V1 = Object.freeze({
  version: "forzy-display-context-sha256-v1",
  canonicalizer: "canonical-json-v1",
  digest: "sha256",
  excludedFields: Object.freeze([]),
});

export function canonicalDisplayContextV1(displayContext) {
  return canonicalJson(cloneAndFreezeDisplayContextV1(displayContext));
}

export async function hashDisplayContextV1(displayContext, cryptoImpl = globalThis.crypto) {
  return sha256Text(canonicalDisplayContextV1(displayContext), cryptoImpl);
}
```

Keep the generic `canonicalJson`/`sha256Text` exports in `canonicalJson.js`. Its walker independently enforces the same fail-closed JSON domain as C1, so generic ruleset hashing cannot stringify `undefined`, holes, exotic objects, accessors, cycles, secret-like keys, non-finite values or `-0`. Put `DISPLAY_CONTEXT_HASH_CONTRACT_V1`, `canonicalDisplayContextV1`, `hashDisplayContextV1` and the decision builder in `operationalDecisionV1.js`, which imports the generic hash helpers plus C1's clone/validator/projection. `displayContextV1.js` never imports the decision module, so this dependency direction has no module cycle.

Validate the imported JSON once at module load: exact root keys, closed mode/condition/trust codes, unique rows, canonical orders, every `then.summaryCode` present in `summaryTemplates`, every check/limitation code present in its label map, allowed template placeholders only, and no unreferenced/duplicate operational phrase. Deep-freeze and export that same object as `operationalTriageRulesetV1`; both decision evaluation and UI presentation consume this reference. Do not reconstruct `modeTitles`, `conditionLabels`, `dataTrustLabels`, `summaryTemplates`, `nextCheckLabels` or `limitationLabels` in JavaScript.

`buildOperationalDecisionViewV1` immediately obtains one `frozenDisplayContext = cloneAndFreezeDisplayContextV1(displayContext)` and uses only that immutable snapshot for canonicalization, matching and output; it never rereads the caller object after an `await`. It obtains `canonicalDisplayContext = canonicalJson(frozenDisplayContext)` and only then calls C1 `toOperationalDecisionInput(frozenDisplayContext)` for matching/output selection. It requires `input.decisionFactsSchemaVersion === "1.0"`, reconstructs only the exact eleven-field `TimelineDecisionFactsV1` object from that matching projection, passes it through the composed Foundation `assertTimelineDecisionFactsV1` validator, and validates `viewMode` plus capability/input-only fields before matching. It never enables AJV coercion/defaults and never edits the returned facts. It finds rows by every closed `when` dimension and throws unless `matches.length === 1`. Its cross-field validator accepts `viewMode="now"` + `collectionExpectation="not_applicable"` only with `collectionState="last_known"|"unavailable"` and `dataFreshness="unknown"`; mismatched expected/fresh/stale facts fail before matching. Output copies the fields admitted by closed `OperationalDecisionViewV1` directly from the frozen projection. The fact schema version and backend-owned `conditionEpisodeStartedAt` remain in the complete canonical display-context hash input without adding an uncontracted field to `OperationalDecisionViewV1`. It filters conditional checks from explicit boolean capability facts, reapplies canonical orders, deduplicates evidence IDs by first occurrence, hashes the canonical ruleset and the complete canonical context, and computes exactly the Spec §9.1 identities:

```js
const frozenDisplayContext = cloneAndFreezeDisplayContextV1(displayContext);
const canonicalDisplayContext = canonicalJson(frozenDisplayContext);
const input = toOperationalDecisionInput(frozenDisplayContext);
const displayContextHash = await sha256Text(canonicalDisplayContext, cryptoImpl);
const decisionId = await sha256Text(`1.0\n${ruleSetHash}\n${canonicalDisplayContext}`, cryptoImpl);
```

`DISPLAY_CONTEXT_HASH_CONTRACT_V1` documents, but does not prefix, the digest bytes: `displayContextHash` is exactly SHA-256 of the UTF-8 bytes of the complete recursively validated/frozen `DisplayContextV1` canonical JSON. `decisionId` hashes the UTF-8 bytes of schema version `1.0`, one LF, the complete `ruleSetHash` string, one LF, then those same canonical context bytes, with no trailing LF. Its exact exclusion set is empty. There is no circularity because `DISPLAY_CONTEXT_V1_FIELDS` contains neither `displayContextHash` nor `decisionId`; both are fields only of the separately produced `OperationalDecisionViewV1`/presentation bundle. An attempt to add either ID to a V1 display context fails as an extra root field. A future context that embeds a derived identifier must introduce `DisplayContextV2` plus a new hash-contract version and an explicit exclusion rule; it cannot silently change V1 or prune a field. Never read or copy `assessmentRecommendation` from any source.

- [ ] **Step 5: Add safety assertions**

Assert identical complete contexts produce identical three hashes/IDs; reordered object keys at every nested level do not. Build `validDisplayContextHashMutations` so every nonconstant root field in `DISPLAY_CONTEXT_V1_FIELDS` has a contract-valid alternate context (using correlated changes where the validator requires them), and assert each canonical-context change changes both `displayContextHash` and `decisionId`. Include every recursive shape: channel identity/measurement/flag, assessment quality/evidence/model, anchor, each export, public quality/provenance/model/acquisition/sensor health and each capability. `rejectedDisplayContextConstants` covers immutable schema versions and asset; their changes fail instead of hashing. Assert the union of mutation/rejected sets equals `DISPLAY_CONTEXT_V1_FIELDS`, extra derived IDs are rejected, exclusion set is frozen `[]`, and a public-only mutation leaves matching input byte-identical while changing both IDs.

In `canonicalJson.test.js`, replay the full C1 hostile JSON corpus directly against the generic canonicalizer: `undefined`, function, symbol, bigint, non-finite numbers, `-0`, holes/extra array fields, accessors, non-enumerable/symbol keys, exotic instances, secret/pollution keys and direct/indirect cycles all throw with paths. Prove repeated acyclic references succeed, object key order is irrelevant, array order is relevant, distinct accepted strings/numbers/arrays/objects yield distinct canonical byte strings in the fixture corpus, and no rejected numeric (`-0`, non-finite) collapses to an accepted JSON number. Inject caller mutations before and during delayed `subtle.digest`; the decision still uses the one pre-await frozen snapshot. This is a semantic no-normalization/no-known-collision test, not a claim to mathematically disprove SHA-256 collisions.

Retain the focused `conditionEpisodeStartedAt` mutation. Inject a legacy recommendation containing “pare”, “continue operando” and a DSN, then assert no serialized decision contains those strings. Assert every ruleset row matches at least one test case and no case matches two rows, including the full structurally valid missing/invalid-policy matrix. Assert the exported presentation bundle is deep-frozen, is the exact validated import used to compute `ruleSetHash`, and rejects missing/extra/duplicated copy keys. Assert every `when` declares the three matched condition dimensions, every `then` omits them, `conditionAsOf` and episode start are coherent with scope/source, selected live timeline facts match only a historical row, unknown-policy facts retain `not_applicable/unknown`, and the current/historical insufficient-data variants preserve their backend-owned facts while sharing the intended safe summary.

- [ ] **Step 6: Run tests to verify GREEN**

Checked Run: `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/decisionSupport/canonicalJson.test.js src/decisionSupport/operationalDecisionV1.test.js src/contracts/operationalDecisionV1.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C3 green tests'`.

Expected: PASS with stable SHA-256 identifiers and closed decisions.

- [ ] **Step 7: Commit**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c3CodePaths=@(
  'contracts/v2/rulesets/fixtures/b-live-display-context-v1-cases.json',
  'contracts/v2/rulesets/forzy-operational-triage-v1.json',
  'src/contracts/operationalDecisionV1.js',
  'src/contracts/operationalDecisionV1.test.js',
  'src/decisionSupport/canonicalJson.js',
  'src/decisionSupport/canonicalJson.test.js',
  'src/decisionSupport/operationalDecisionV1.js',
  'src/decisionSupport/operationalDecisionV1.test.js'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'C3 decision code and complete B-case context corpus' -Message 'feat: add deterministic operational triage rules' -Paths $c3CodePaths
```

---

### Task 4: Comparable Candidate Ranking and Sanitized Evidence Export

**Files:**
- Create: `contracts/v2/rulesets/forzy-review-priority-v1.json`
- Create: `src/decisionSupport/candidateRankingV1.js`
- Create: `src/decisionSupport/candidateRankingV1.test.js`
- Create: `src/decisionSupport/evidenceSummaryV1.js`
- Create: `src/decisionSupport/evidenceSummaryV1.test.js`

**Interfaces:**
- Consumes: timeline `eventCandidates`, active view scope, `OperationalDecisionViewV1`.
- Produces: deep-frozen validated `reviewPriorityRulesetV1`, `buildCandidateReviewScopesV1({ overview, viewMode, inspectedSourceKind, inspectedBatchId, inspectedSensorId, focusedOperatingCycleIds }) -> CandidateReviewScopeV1[]`, `rankCandidatesV1(candidates, scope) -> TimelineEventCandidateV1[]` without reshaping candidates, and `buildEvidenceSummaryV1({ displayContext, decision, candidate }) -> object`.
- Produces também `resolveContractedEpisodeStartedAt({ candidate, assessment, evidence }) -> string|null`, sem inferência temporal.

- [ ] **Step 1: Write failing ranking tests**

```js
it("sorts only comparable historical candidates", () => {
  const [scope] = buildCandidateReviewScopesV1({
    overview: historicalOverview,
    viewMode: "historical",
    inspectedSourceKind: "historical_archive",
    inspectedBatchId: historicalOverview.activeHistoricalBatchId,
    inspectedSensorId: "s1",
    focusedOperatingCycleIds: [
      "00000000-0000-5000-8000-000000000101",
      "00000000-0000-5000-8000-000000000102",
    ],
  });
  const result = rankCandidatesV1(historicalOverview.eventCandidates, scope);
  expect(result.map(({ candidateId }) => candidateId)).toEqual([
    "00000000-0000-5000-8000-000000000001",
    "00000000-0000-5000-8000-000000000002",
    "00000000-0000-5000-8000-000000000003",
  ]);
  expect(result.some(({ candidateId }) => candidateId === "00000000-0000-5000-8000-000000000004")).toBe(false);
  expect(result.every(({ anchorPointId, modelFamily, modelVersion }) => (
    typeof anchorPointId === "string"
      && modelFamily === "robust-baseline"
      && modelVersion === "1.0.0"
  ))).toBe(true);
  expect(result.every(({ schemaVersion, persistenceCount, quality }) => (
    schemaVersion === "1.0"
      && Number.isInteger(persistenceCount)
      && persistenceCount >= 1
      && quality && typeof quality.status === "string"
  ))).toBe(true);
  expect(result.every((candidate) => !("pointId" in candidate))).toBe(true);
});

it("treats activeHistoricalBatchId as global context while ranking now-live candidates", () => {
  expect(mixedOverview.activeHistoricalBatchId).toMatch(/^sha256:/);
  const groups = buildCandidateReviewScopesV1({
    overview: mixedOverview,
    viewMode: "now",
    inspectedSourceKind: null,
    inspectedBatchId: null,
    inspectedSensorId: null,
    focusedOperatingCycleIds: [],
  });
  expect(groups.length).toBeGreaterThan(0);
  expect(groups.every((scope) => (
    scope.sourceKind === "live_collection"
      && scope.batchId === null
      && scope.activeHistoricalBatchId === mixedOverview.activeHistoricalBatchId
  ))).toBe(true);
  expect(groups.flatMap((scope) => rankCandidatesV1(mixedOverview.eventCandidates, scope))
    .every(({ sourceKind, batchId }) => sourceKind === "live_collection" && batchId === null))
    .toBe(true);
});

it.each([
  ["point", {
    sourceKind: selectedLivePoint.sourceKind,
    batchId: null,
    sensorId: selectedLivePoint.sensorId,
  }],
  ["candidate", {
    sourceKind: selectedLiveCandidate.sourceKind,
    batchId: selectedLiveCandidate.batchId,
    sensorId: selectedLiveCandidate.sensorId,
  }],
])(
  "keeps historical inspection of a live %s in live candidate groups",
  (_selectionKind, inspected) => {
    const groups = buildCandidateReviewScopesV1({
      overview: mixedOverview,
      viewMode: "historical",
      inspectedSourceKind: inspected.sourceKind,
      inspectedBatchId: inspected.batchId,
      inspectedSensorId: inspected.sensorId,
      focusedOperatingCycleIds: [],
    });
    expect(groups.every((scope) => (
      scope.sourceKind === "live_collection"
        && scope.batchId === null
        && scope.activeHistoricalBatchId === mixedOverview.activeHistoricalBatchId
    ))).toBe(true);
    const visible = groups.flatMap((scope) => rankCandidatesV1(mixedOverview.eventCandidates, scope));
    expect(visible.length).toBeGreaterThan(0);
    expect(visible.every(({ sourceKind, batchId, sensorId }) => (
      sourceKind === "live_collection" && batchId === null && sensorId === "s1"
    ))).toBe(true);
  },
);

it("does not use raw scores as a tie breaker", () => {
  expect(compareCandidatesV1({ ...left, anomalyScore: 999 }, { ...right, anomalyScore: 0 }))
    .toBe(compareCandidatesV1(left, right));
});

it("orders candidates in the same millisecond only by the next declared tie breaker", () => {
  const sameInstant = "2026-05-19T14:50:00.123Z";
  const first = { ...left, candidateId: "00000000-0000-5000-8000-000000000001", eventAt: sameInstant };
  const second = { ...left, candidateId: "00000000-0000-5000-8000-000000000002", eventAt: sameInstant };
  expect([second, first].sort(compareCandidatesV1).map(({ candidateId }) => candidateId))
    .toEqual([first.candidateId, second.candidateId]);
});
```

- [ ] **Step 2: Run tests to verify RED**

Checked RED Run: capture output from `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/decisionSupport/candidateRankingV1.test.js src/decisionSupport/evidenceSummaryV1.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C4 expected-red tests' @(1)`, then require the captured failure to name the missing ranking/evidence behavior.

Expected: FAIL because both modules are absent.

- [ ] **Step 3: Add exact ranking fixture and comparator**

```json
{
  "schemaVersion": "1.0",
  "candidateRankingVersion": "forzy-review-priority-v1",
  "queueDisclaimer": "Prioridade relativa de revisão no TwinOps; não representa risco, criticidade ou prioridade de ordem de serviço.",
  "persistenceTemplate": "{count} avaliações causais consecutivas",
  "statusOrder": { "alert": 0, "watch": 1 },
  "dataTrustOrder": { "sufficient": 0, "degraded": 1, "insufficient": 2 },
  "tieBreakers": [
    "status", "persistenceCount:desc", "dataTrust", "eventAt:desc", "candidateId:asc"
  ]
}
```

```js
import { compareCanonicalUtcMillis } from "../time/canonicalUtcMillis.js";

const compareCanonicalId = (left, right) => left === right ? 0 : left < right ? -1 : 1;

export function compareCandidatesV1(left, right) {
  return STATUS_ORDER[left.status] - STATUS_ORDER[right.status]
    || right.persistenceCount - left.persistenceCount
    || TRUST_ORDER[left.dataTrust] - TRUST_ORDER[right.dataTrust]
    || compareCanonicalUtcMillis(right.eventAt, left.eventAt)
    || compareCanonicalId(left.candidateId, right.candidateId);
}
```

Validate and deep-freeze the ranking JSON once; comparator, queue disclaimer and persistence rendering consume that exact exported `reviewPriorityRulesetV1` bundle. `buildCandidateReviewScopesV1` first validates the complete `TimelineOverviewV1`; `rankCandidatesV1` therefore accepts only candidates already validated as members of that overview and reads every closed A/B field literally: `schemaVersion`, `candidateId`, `anchorPointId`, nullable `operatingCycleId`, `sensorId`, `eventAt`, contracted non-null `episodeStartedAt`, `sourceKind`, `status`, `persistenceCount`, `dataTrust`, `quality{status,flags}`, nullable `batchId`, `modelFamily`, `modelVersion`, nullable `foldId` and `candidateRankingVersion`. `episodeStartedAt` is canonical UTC milliseconds and `episodeStartedAt <= eventAt`. A candidate property named `pointId`, guessed aliases, a duration synthesized from nominal polling or extra UI fields are forbidden.

`STATUS_ORDER` and `TRUST_ORDER` are read-only aliases of `reviewPriorityRulesetV1.statusOrder` and `.dataTrustOrder`; do not duplicate their numeric values in source.

`activeHistoricalBatchId` is overview-wide context, not the candidate discriminator: it may remain non-null while the overview also contains live candidates. Candidate source identity is always the pair `sourceKind + batchId`; archive requires `historical_archive + activeHistoricalBatchId`, while live requires `live_collection + null` regardless of whether an archive is active. `viewMode` describes navigation and never rewrites that source pair, so a live point/candidate inspected in historical mode remains a live candidate group.

`buildCandidateReviewScopesV1` is the only scope builder used before `CandidateQueue`. In `viewMode="now"` it selects the `live_collection + null` source pair. In historical mode it requires the inspected pair explicitly: a selected candidate supplies its literal `sourceKind + batchId`; a selected original point supplies `sourceKind` plus `provenance.batchId` only for the historical discriminator and literal null for live. Archive inspection requires the active non-null batch and focused cycle IDs; live inspection requires null batch and empty archive cycle IDs. It then partitions the selected candidates into exact comparable groups by `sourceKind + batchId + sensorId + modelFamily + modelVersion + foldId`, carrying `activeHistoricalBatchId` only as global context and the validated `effectiveRange` as a range bound. Each frozen `CandidateReviewScopeV1` contains exactly `schemaVersion`, `viewMode`, `sourceKind`, nullable `batchId`, nullable `activeHistoricalBatchId`, `sensorId`, `modelFamily`, `modelVersion`, nullable `foldId`, `effectiveRange` and `operatingCycleIds`. An empty source selection returns `[]`; missing/crossed discriminants, inactive archive batch, archive candidate without cycle/fold, live candidate with batch/fold, or a candidate outside range/cycle fails closed. No UI-only `batchId` is added to a `TimelinePointV1`.

`rankCandidatesV1` filters the already-validated overview candidates to one exact scope and sorts only that group. It never interleaves two sensors, folds, sources, batches or model versions into one priority order. Both source branches require `schemaVersion="1.0"`, quality/trust coherence and the canonical ranking version. Tests cover mixed archive/live overview data with a non-null active archive, now-live queue construction, historical inspection of both a live point and a live candidate, archive selection, multiple sensors/folds/models and adversarial crossed batch/source fields; every queue entry belongs to exactly one group and no candidate is duplicated or silently normalized.

- [ ] **Step 4: Implement allowlisted export**

```js
export function buildEvidenceSummaryV1({ displayContext, decision, candidate = null }) {
  const episodeStartedAt = resolveContractedEpisodeStartedAt({
    candidate,
    assessment: displayContext.assessment,
    evidence: { conditionEpisodeStartedAt: displayContext.conditionEpisodeStartedAt },
  });
  return Object.freeze({
    schemaVersion: decision.schemaVersion,
    ruleSetVersion: decision.ruleSetVersion,
    ruleSetHash: decision.ruleSetHash,
    displayContextHash: decision.displayContextHash,
    candidateRankingVersion: "forzy-review-priority-v1",
    assetId: displayContext.asset.assetId,
    viewMode: decision.viewMode,
    decisionAsOf: decision.decisionAsOf,
    conditionAsOf: decision.conditionAsOf,
    pointId: displayContext.anchor?.pointId ?? null,
    candidateId: candidate?.candidateId ?? null,
    episodeStartedAt,
    operatingCycleId: candidate?.operatingCycleId ?? null,
    measurements: displayContext.exportableMeasurements,
    evidence: displayContext.exportableEvidence,
    qualityFlags: displayContext.publicQualityFlags,
    provenance: displayContext.publicProvenance,
    model: displayContext.publicModel,
    nextCheckCodes: decision.nextCheckCodes,
    limitationCodes: decision.limitationCodes,
  });
}
```

`resolveContractedEpisodeStartedAt` inspects only explicitly contracted values: `candidate.episodeStartedAt`, `evidence.conditionEpisodeStartedAt` copied from `TimelineDecisionFactsV1`, and `assessment.persistence.episodeStartedAt` **only** when the validated assessment is the discriminated `HistoricalAssessmentV1` variant that owns `persistence`. The existing live `AssetConditionAssessmentV2` has no persistence member and contributes no value through that path; live episode evidence comes from the candidate/decision facts supplied by B. It validates each provided non-null value with `parseCanonicalUtcMillis`, requires all provided values to be identical, and returns that exact value or `null`; disagreement or an unrecognized assessment shape fails closed. It never subtracts cadence from `persistenceCount`, never uses the earliest chart point, and never derives a start from `eventAt`. All export properties are reconstructed from the allowlist; never spread `snapshot`, `assessment`, errors, provenance internals or candidate objects. Unknown quality flags export as `unknown_quality_flag`, not their raw string.

- [ ] **Step 5: Add negative export tests and run GREEN**

Assert `reviewPriorityRulesetV1` has exactly the seven declared root keys, is deeply frozen, permits only `{count}` in the persistence template and is the exact bundle used by the comparator/queue. Inject `recommendation`, `raw`, `path`, `dsn`, `connectionString`, arbitrary upstream error and secret-like unknown flag. Assert `JSON.stringify(summary)` contains none. Assert zero remains `0` and null remains `null`. Cover exact candidate/assessment/evidence agreement for `episodeStartedAt`, a single contracted source, total absence returning null, disagreement failing closed, same-millisecond ranking by candidate ID, and rejection of noncanonical microsecond timestamps; no test may infer episode start from persistence or cadence.

Checked Run: `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/decisionSupport/candidateRankingV1.test.js src/decisionSupport/evidenceSummaryV1.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C4 green tests'`.

Expected: PASS; ranking is deterministic and export contains only public fields.

- [ ] **Step 6: Commit**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c4CodePaths=@(
  'contracts/v2/rulesets/forzy-review-priority-v1.json',
  'src/decisionSupport/candidateRankingV1.js',
  'src/decisionSupport/candidateRankingV1.test.js',
  'src/decisionSupport/evidenceSummaryV1.js',
  'src/decisionSupport/evidenceSummaryV1.test.js'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'C4 ranking code' -Message 'feat: rank review candidates and sanitize evidence' -Paths $c4CodePaths
```

---

### Task 5: Unified Live and Historical Display Context

**Files:**
- Reuse unchanged: `docs/verification/checkpoints/b-to-c-contract-handoff.json`
- Modify: `src/displayContext/displayContextV1.js` (created and shape-frozen by Task C1)
- Modify: `src/displayContext/displayContextV1.test.js` (created by Task C1)

**Interfaces:**
- Consumes: Task C1 `DISPLAY_CONTEXT_V1_FIELDS`, `assertDisplayContextV1(value)`, `cloneAndFreezeDisplayContextV1(value)` and unchanged matching-only `toOperationalDecisionInput(displayContext)`, plus a validated v2 snapshot or `TimelineContextV1`.
- Produces: adapter exports added to the C1 module: `fromLiveSnapshot(snapshot) -> deeply frozen DisplayContextV1` and `fromHistoricalContext(context, liveAsset) -> deeply frozen DisplayContextV1`. It does not redefine `DisplayContextV1` or the C1 projection; `OperationalDecisionViewV1` remains a separate Task C1/C3 UI result and is not produced by B or by these adapters.

`fromHistoricalContext` always produces `viewMode: "historical"`, including when `context.anchor.sourceKind === "live_collection"`; selecting a live timeline point is retrospective inspection, not a return to Now. It reads the backend-owned decision dimensions only from `context.decisionFacts` and flattens those exact values into `DisplayContextV1`. A selected live context therefore retains backend facts `conditionSource: "live_assessment"` and `conditionTemporalScope: "historical"`. It must not expect `conditionState`, `collectionState`, `dataAvailability`, `dataFreshness` or `dataTrust` as top-level `TimelineContextV1` fields, branch mode on `sourceKind`, or recompute any fact. `context.provenance` and `context.capabilities` are copied through their explicit public allowlists.

- [ ] **Step 0: Reauthenticate B→C before any live/historical adapter work**

In a fresh checked PowerShell 5.1 session, load `B_TO_C_CONTRACT_HANDOFF_COMMIT`, `PHASE_B_VERIFIED_CODE_COMMIT` and `PHASE_B_EVIDENCE_COMMIT`; require all three 40-hex values and exact equality to the closed handoff JSON. Prove `B code → B evidence → B-to-C handoff commit → HEAD`, the same four-path evidence diff, PASS review hash/identity and current ledger B PASS. Then recompute raw-byte hashes with `git show` and the Task C3.0 Python helper, and compare every current file:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$bToCPath='docs/verification/checkpoints/b-to-c-contract-handoff.json'
$bToCCommit=[string]$env:B_TO_C_CONTRACT_HANDOFF_COMMIT
$phaseBCodeCommit=[string]$env:PHASE_B_VERIFIED_CODE_COMMIT
$phaseBEvidenceCommit=[string]$env:PHASE_B_EVIDENCE_COMMIT
if ($bToCCommit -notmatch '^[0-9a-f]{40}$' -or $phaseBCodeCommit -notmatch '^[0-9a-f]{40}$' -or $phaseBEvidenceCommit -notmatch '^[0-9a-f]{40}$') { throw 'B-to-C reauthentication requires three exact SHAs' }
$bToC=Get-Content -Raw -Encoding utf8 -LiteralPath $bToCPath -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$expectedBToCKeys=@('contractSha256','evidencePaths','phaseBCodeCommit','phaseBEvidenceCommit','phaseBLedgerSha256','phaseBReviewSha256','reviewVerdict','schemaVersion') | Sort-Object
$expectedBEvidencePaths=@(
  'docs/verification/phase-b-findings.json',
  'docs/verification/phase-b-local-causal-manifest.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) | Sort-Object
$bContractPaths=@(
  'contracts/timeline/v1/fixtures/live-decision-facts-v1-cases.json',
  'contracts/timeline/v1/timeline-context.schema.json',
  'contracts/timeline/v1/timeline-decision-facts.schema.json',
  'contracts/timeline/v1/timeline-overview.schema.json',
  'contracts/timeline/v1/timeline-page.schema.json',
  'contracts/v2/digital-twin-snapshot.schema.json',
  'contracts/v2/fixtures/snapshot-last-known.valid.json',
  'contracts/v2/fixtures/snapshot-received-now.valid.json',
  'src/contracts/timelineV1.js',
  'src/contracts/twinV2.js'
) | Sort-Object
if ((Compare-Object $expectedBToCKeys @($bToC.PSObject.Properties.Name | Sort-Object)) -or $bToC.schemaVersion -cne 'phase-b-to-c-contract-handoff-v1' -or [string]$bToC.phaseBCodeCommit -cne $phaseBCodeCommit -or [string]$bToC.phaseBEvidenceCommit -cne $phaseBEvidenceCommit -or $bToC.reviewVerdict -cne 'PASS' -or (Compare-Object $expectedBEvidencePaths @($bToC.evidencePaths | Sort-Object)) -or (Compare-Object $bContractPaths @($bToC.contractSha256.PSObject.Properties.Name | Sort-Object))) { throw 'B-to-C environment/file shape or identity mismatch' }
foreach($edge in @(@($phaseBCodeCommit,$phaseBEvidenceCommit),@($phaseBEvidenceCommit,$bToCCommit),@($bToCCommit,'HEAD'))) {
  git merge-base --is-ancestor $edge[0] $edge[1]
  Assert-NativeExit $LASTEXITCODE "B-to-C ancestry $($edge[0]) -> $($edge[1])"
}
$rawAuthBlob=git rev-parse "$bToCCommit`:$bToCPath"
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read committed B-to-C handoff blob'
$authBlob=($rawAuthBlob -join "`n").Trim()
$rawWorkingAuthBlob=git hash-object -- $bToCPath
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'hash current B-to-C handoff'
$workingAuthBlob=($rawWorkingAuthBlob -join "`n").Trim()
if ($workingAuthBlob -cne $authBlob) { throw 'B-to-C handoff file changed after authentication' }
$committedBToCJson=@(git show "${bToCCommit}:$bToCPath")
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'parse committed B-to-C handoff'
$committedBToC=(($committedBToCJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
if ((Compare-Object $expectedBToCKeys @($committedBToC.PSObject.Properties.Name | Sort-Object)) -or $committedBToC.schemaVersion -cne 'phase-b-to-c-contract-handoff-v1' -or [string]$committedBToC.phaseBCodeCommit -cne $phaseBCodeCommit -or [string]$committedBToC.phaseBEvidenceCommit -cne $phaseBEvidenceCommit -or $committedBToC.reviewVerdict -cne 'PASS' -or (Compare-Object $expectedBEvidencePaths @($committedBToC.evidencePaths | Sort-Object)) -or (Compare-Object $bContractPaths @($committedBToC.contractSha256.PSObject.Properties.Name | Sort-Object))) { throw 'committed B-to-C handoff shape or binding mismatch' }

$rawBEvidencePaths=@(git diff --name-only "$phaseBCodeCommit..$phaseBEvidenceCommit")
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 're-read Phase B evidence scope'
if ((Compare-Object $expectedBEvidencePaths @($rawBEvidencePaths | Sort-Object)) -or (Compare-Object $expectedBEvidencePaths @($bToC.evidencePaths | Sort-Object))) { throw 'Phase B evidence scope drifted' }
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe" -ErrorAction Stop).Path
$contractHashJson=@(& $python scripts/phase_c_evidence.py hash-paths --commit $phaseBCodeCommit --paths $bContractPaths)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'reauthenticate raw git-show B contracts'
$actualContractHashes=(($contractHashJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
foreach($path in $bContractPaths) {
  $expected=[string]$bToC.contractSha256.PSObject.Properties[$path].Value
  $fromCommit=[string]$actualContractHashes.PSObject.Properties[$path].Value
  $working='sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath $path -ErrorAction Stop).Hash.ToLowerInvariant()
  if ($expected -cne $fromCommit -or $expected -cne $working) { throw "B contract drift before C5: $path" }
}
$reviewHashJson=@(& $python scripts/phase_c_evidence.py hash-paths --commit $phaseBEvidenceCommit --paths 'docs/verification/phase-b-findings.json')
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'reauthenticate raw git-show B review'
$reviewHashMap=(($reviewHashJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
$currentBReviewHash='sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath 'docs/verification/phase-b-findings.json' -ErrorAction Stop).Hash.ToLowerInvariant()
if ([string]$reviewHashMap.PSObject.Properties['docs/verification/phase-b-findings.json'].Value -cne [string]$bToC.phaseBReviewSha256 -or $currentBReviewHash -cne [string]$bToC.phaseBReviewSha256) { throw 'Phase B PASS review hash drifted' }
$bEvidenceProjectionJson=@(& $python scripts/phase_c_evidence.py b-evidence-projection --commit $phaseBEvidenceCommit)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'reauthenticate and parse committed B review plus ledger'
$bEvidenceProjection=(($bEvidenceProjectionJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
Assert-FindingVerdictObject $bEvidenceProjection.review.verdict 'C5 committed Phase B finding review verdict'
$bVerdictCounts=@($bEvidenceProjection.review.verdict.critical,$bEvidenceProjection.review.verdict.important,$bEvidenceProjection.review.verdict.minor)
Assert-ReviewVerdictArray $bEvidenceProjection.planB.reviewVerdict $bVerdictCounts 'C5 committed Phase B ledger review verdict'
if ($bEvidenceProjection.reviewHash -cne $bToC.phaseBReviewSha256 -or $bEvidenceProjection.ledgerHash -cne $bToC.phaseBLedgerSha256 -or $bEvidenceProjection.review.schemaVersion -cne 'finding-review-v1' -or $bEvidenceProjection.review.plan -cne 'B' -or [string]$bEvidenceProjection.review.reviewedSha -cne $phaseBCodeCommit -or $bEvidenceProjection.review.verdict.critical -ne 0 -or $bEvidenceProjection.review.verdict.important -ne 0 -or $bEvidenceProjection.planB.status -cne 'passed' -or [string]$bEvidenceProjection.planB.verifiedCodeCommit -cne $phaseBCodeCommit -or $bEvidenceProjection.criteria.'AC-13'.status -cne 'passed' -or $bEvidenceProjection.criteria.'AC-14'.status -cne 'passed') { throw 'committed Phase B review/ledger is not a closed PASS at C5' }
if (@($bEvidenceProjection.review.findings | Where-Object { $_.severity -eq 'minor' -and $_.status -notin @('fixed','accepted') }).Count -ne 0) { throw 'committed Phase B review has an unaccepted Minor at C5' }
$currentLedger=Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/unified-twin-acceptance-v1.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
Assert-ReviewVerdictArray $currentLedger.plans.B.reviewVerdict $bVerdictCounts 'C5 current Phase B ledger review verdict'
if ($currentLedger.plans.B.status -cne 'passed' -or [string]$currentLedger.plans.B.verifiedCodeCommit -cne $phaseBCodeCommit -or @($currentLedger.criteria | Where-Object criterionId -eq 'AC-13').Count -ne 1 -or @($currentLedger.criteria | Where-Object criterionId -eq 'AC-13')[0].status -cne 'passed' -or @($currentLedger.criteria | Where-Object criterionId -eq 'AC-14').Count -ne 1 -or @($currentLedger.criteria | Where-Object criterionId -eq 'AC-14')[0].status -cne 'passed') { throw 'Phase B ledger state regressed before C5' }
```

Any failure blocks C5. Do not refresh the JSON from current files; only a newly reviewed B code/evidence pair may replace this handoff and restart C3.

- [ ] **Step 1: Write failing adapter tests**

```js
import liveDecisionFactsCasesV1 from "../../contracts/timeline/v1/fixtures/live-decision-facts-v1-cases.json";

const bDecisionFactsByCaseId = Object.freeze(Object.fromEntries(
  liveDecisionFactsCasesV1.cases.map(({ caseId, expectedDecisionFacts }) => (
    [caseId, Object.freeze(structuredClone(expectedDecisionFacts))]
  )),
));

it("maps received-now facts without a frontend freshness clock", () => {
  expect(Object.keys(receivedSnapshot.decisionFacts).sort()).toEqual([
    "schemaVersion", "conditionState", "conditionTemporalScope", "conditionAsOf",
    "conditionEpisodeStartedAt", "conditionSource", "collectionState", "collectionExpectation",
    "dataAvailability", "dataFreshness", "dataTrust",
  ].sort());
  const context = fromLiveSnapshot(receivedSnapshot);
  expect(context).toMatchObject({
    viewMode: "now",
    decisionAsOf: receivedSnapshot.generatedAt,
    decisionFactsSchemaVersion: receivedSnapshot.decisionFacts.schemaVersion,
    conditionState: receivedSnapshot.decisionFacts.conditionState,
    conditionTemporalScope: receivedSnapshot.decisionFacts.conditionTemporalScope,
    conditionAsOf: receivedSnapshot.decisionFacts.conditionAsOf,
    conditionEpisodeStartedAt: receivedSnapshot.decisionFacts.conditionEpisodeStartedAt,
    conditionSource: receivedSnapshot.decisionFacts.conditionSource,
    collectionState: receivedSnapshot.decisionFacts.collectionState,
    collectionExpectation: receivedSnapshot.decisionFacts.collectionExpectation,
    dataAvailability: receivedSnapshot.decisionFacts.dataAvailability,
    dataFreshness: receivedSnapshot.decisionFacts.dataFreshness,
    dataTrust: receivedSnapshot.decisionFacts.dataTrust,
    anchor: null,
  });
  expect(context.dataFreshness).toBe(receivedSnapshot.decisionFacts.dataFreshness);
  expect(context.dataTrust).toBe(receivedSnapshot.decisionFacts.dataTrust);
});

it.each([
  ["missing retained", snapshotWithMissingPolicyRetained, "missing_policy_retained_complete_watch"],
  ["invalid retained", snapshotWithInvalidPolicyRetained, "invalid_policy_retained_complete_watch"],
  ["missing unavailable", snapshotWithMissingPolicyUnavailable, "missing_policy_without_usable_evidence"],
  ["invalid unavailable", snapshotWithInvalidPolicyUnavailable, "invalid_policy_without_usable_evidence"],
])("preserves B fixture facts byte-for-byte for %s", (
  _name, snapshot, caseId,
) => {
  const expected = bDecisionFactsByCaseId[caseId];
  expect(snapshot.decisionFacts).toEqual(expected);
  const context = fromLiveSnapshot(snapshot);
  const input = toOperationalDecisionInput(context);
  for (const [key, value] of Object.entries(expected)) {
    const displayKey = key === "schemaVersion" ? "decisionFactsSchemaVersion" : key;
    expect(context[displayKey]).toEqual(value);
    expect(input[displayKey]).toEqual(value);
  }
});

it("keeps historical channels and condition on the same original pair", () => {
  const context = fromHistoricalContext(historicalContext, receivedSnapshot.asset);
  expect(context.asset).toEqual(receivedSnapshot.asset);
  expect(Object.keys(context.asset).sort()).toEqual(["assetId", "displayName", "officialTag"]);
  expect(context.decisionFactsSchemaVersion).toBe(historicalContext.decisionFacts.schemaVersion);
  expect(context.channels.s1.samplePairId).toBe(context.anchor.samplePairId);
  expect(context.channels.s2.samplePairId).toBe(context.anchor.samplePairId);
  expect(context.conditionTemporalScope).toBe("historical");
  expect(context.decisionAsOf).toBe(historicalContext.selectedAt);
});

it("rejects any historical/live asset crossing", () => {
  expect(() => fromHistoricalContext(
    { ...historicalContext, assetId: "another-asset" },
    receivedSnapshot.asset,
  )).toThrow(/context\.assetId/);
  expect(() => fromHistoricalContext(historicalContext, {
    ...receivedSnapshot.asset,
    displayName: "Alias local",
  })).toThrow(/liveAsset\.displayName/);
});

it("treats a selected live timeline point as historical without rewriting its source", () => {
  const context = fromHistoricalContext(selectedLiveTimelineContext, receivedSnapshot.asset);
  expect(selectedLiveTimelineContext.anchor.sourceKind).toBe("live_collection");
  expect(context).toMatchObject({
    viewMode: "historical",
    decisionAsOf: selectedLiveTimelineContext.selectedAt,
    conditionTemporalScope: "historical",
    conditionSource: "live_assessment",
    collectionState: "historical_context",
    collectionExpectation: "not_applicable",
    dataFreshness: "historical",
  });
});

it("does not carry values into a gap", () => {
  const context = fromHistoricalContext(gapContext, receivedSnapshot.asset);
  expect(context.anchor).toBeNull();
  expect(context.channels).toEqual({ s1: null, s2: null });
  expect(context.assessment).toBeNull();
  expect(context.conditionState).toBe("unknown");
  expect(context.conditionTemporalScope).toBe("none");
  expect(context.conditionSource).toBe("none");
  expect(context.conditionAsOf).toBeNull();
  expect(context.conditionEpisodeStartedAt).toBeNull();
  expect(context.dataAvailability).toBe("gap");
  expect(context.dataFreshness).toBe("historical");
});
```

- [ ] **Step 2: Run tests to verify RED**

Checked RED Run: capture output from `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/displayContext/displayContextV1.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C5 expected-red tests' @(1)`, then require the captured failure to name only the missing source adapters.

Expected: FAIL because the C1 module does not yet export the two source adapters; all pre-existing C1 validator/projection tests remain GREEN.

- [ ] **Step 3: Extend the C1 module with normalized adapters**

```js
export function fromLiveSnapshot(snapshot) {
  const validated = assertDigitalTwinSnapshotV2(snapshot);
  return cloneAndFreezeDisplayContextV1(projectLiveSnapshotWithoutPolicyRepair(validated));
}

export function fromHistoricalContext(context, liveAsset) {
  const validated = assertTimelineContextV1(context);
  const validatedLiveAsset = assertExactForzyAssetV1(liveAsset, "liveAsset");
  if (validated.assetId !== validatedLiveAsset.assetId) {
    throw new TypeError("context.assetId must equal liveAsset.assetId");
  }
  const projected = projectHistoricalContextWithoutCarryForward(validated, validatedLiveAsset);
  if (projected.asset !== validatedLiveAsset) {
    throw new TypeError("displayContext.asset must equal liveAsset");
  }
  return cloneAndFreezeDisplayContextV1(projected);
}
```

Implement the private projection helpers and `assertExactForzyAssetV1(value, path)` in the same module as literal allowlists; they may not be exported as alternative context types. The asset helper enforces the same exact three-key constant frozen by C1 and emits the supplied path in errors. Every public adapter return passes through `cloneAndFreezeDisplayContextV1`, not only the identity validator, so no snapshot/context/asset reference escapes. The helper names above are private implementation units defined in this step, not extension hooks. Preserve `schemaVersion: "1.0"`, every root and recursive key frozen by C1, and the closed capability object exactly; do not add aliases or embed `OperationalDecisionViewV1`. `fromHistoricalContext` requires `context.assetId === liveAsset.assetId`, projects the exact validated asset values into the fresh clone and proves canonical equality before returning; it never reconstructs a display name or substitutes a provisional asset.

For live data, `fromLiveSnapshot` accepts only the B-produced `snapshot.decisionFacts: TimelineDecisionFactsV1` after snapshot validation, requires exactly `schemaVersion: "1.0"`, stores it as `decisionFactsSchemaVersion`, and copies all ten closed decision dimensions, including `conditionEpisodeStartedAt`, literally. It may project asset, paired channels, assessment and public evidence, but it must not infer policy, cadence, `collectionState`, `collectionExpectation`, availability, freshness, trust, condition state/scope/source, `conditionAsOf` or episode start from timestamps, channel presence, quality flags, assessment content, `Date.now()` or runtime defaults. In particular, missing/invalid policy snapshots remain exactly `collectionExpectation="not_applicable"` + `dataFreshness="unknown"` with their B-owned `last_known|unavailable` collection state; neither the adapter nor the decision builder coerces them to expected/fresh/stale values. Missing/extra/crossed live facts or another version fail closed. Historical data follows the identical rule from `context.decisionFacts`; `fromHistoricalContext` never expects those dimensions at context root, always sets only the UI navigation dimension `viewMode: "historical"`, and copies the backend's selected-context `historical/live_assessment` combination without converting it to current. The unchanged C1 `toOperationalDecisionInput` allowlists `decisionFactsSchemaVersion`, all ten flattened dimensions and explicit capability booleans solely for ruleset matching and never reevaluates them; Task C3 hashes the complete validated display context, never this projection.

Build `exportableMeasurements`, `exportableEvidence`, `publicQualityFlags`, `publicProvenance`, `publicModel` and `publicAcquisition` as explicit allowlists for Task 4/UI. `publicAcquisition` copies only backend-provided attempt/success/expected-collection/gap facts appropriate to that exact context and never computes age/cadence. Historical bundles do not silently include the latest live integration object. Preserve evidence input order. Derive `emphasizedSensorIds` only from an allowlisted `sensorId` carried by contracted driver evidence or the contracted assessment; deduplicate in canonical `s1,s2` order. Never select the sensor with the largest numeric oscillation. If the contract does not identify a driver, keep both `driverEvidenceIds: []` and `emphasizedSensorIds: []`, and show “Métrica causadora não determinada”.

- [ ] **Step 4: Add invariant and safety tests**

Cover valid zero, missing metric, one missing sensor, assumed timestamp, degraded quality, last-known `conditionAsOf`, expected-idle without condition, unknown condition, assessment-free null-anchor gap, selected live timeline context, historical/live asset equality, wrong/incomplete/extra live asset rejection, mismatched context asset ID, mismatched sample pair rejection, ordered/deduplicated `emphasizedSensorIds`, absence of emphasis without contracted sensor evidence, contracted `episodeStartedAt` pass-through, and a recommendation containing operational commands that never reaches the display context. Define `snapshotWithMissingPolicyRetained`, `snapshotWithInvalidPolicyRetained`, `snapshotWithMissingPolicyUnavailable` and `snapshotWithInvalidPolicyUnavailable` from validated B serializer outputs. Assert each `snapshot.decisionFacts` is exactly its named row from `live-decision-facts-v1-cases.json`, then prove `fromLiveSnapshot` and `toOperationalDecisionInput` preserve all eleven fields byte-for-byte: retained watch stays `last_known/not_applicable/complete/unknown/sufficient` with its condition/episode timestamps, while no usable evidence stays `unknown/none/null/null/none + unavailable/not_applicable/unavailable/unknown/insufficient`. Add adversarial live fixtures where timestamps/presence/quality would suggest `expected_now`, `fresh` or `stale`; assert every flattened policy/freshness/expectation/trust field remains byte-for-byte backend-owned, no adapter reads a runtime policy, and absent/invalid decision facts throw. Assert the gap has no copied anchor/channel/assessment/evidence from the preceding valid context and selected live context cannot enter `fromLiveSnapshot` merely because its anchor source is live.

- [ ] **Step 5: Run tests to verify GREEN**

Checked Run: `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/displayContext/displayContextV1.test.js src/contracts/timelineV1.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C5 green tests'`.

Expected: PASS; live and history produce one stable shape without time mixing.

- [ ] **Step 6: Commit**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c5CodePaths=@('src/displayContext/displayContextV1.js','src/displayContext/displayContextV1.test.js') | Sort-Object
Invoke-PhaseCExactCommit -Label 'C5 display adapters' -Message 'feat: unify live and historical display context' -Paths $c5CodePaths
```

---

### Task 6: Pure TwinOps Navigation Reducer

**Files:**
- Create: `src/state/twinOpsReducer.js`
- Create: `src/state/twinOpsReducer.test.js`

**Interfaces:**
- Consumes: validated snapshots, overview/page/context, prebuilt hash-matched presentation bundles and UI controls.
- Produces: `initialTwinOpsState`, `twinOpsReducer(state, action)`, `committedPresentation(state)`.

- [ ] **Step 1: Write failing atomicity tests**

```js
it("does not switch panels when historical context is only pending", () => {
  const live = twinOpsReducer(initialTwinOpsState, {
    type: "LIVE_BUNDLE_RESOLVED", snapshot, bundle: liveBundle,
  });
  const pending = twinOpsReducer(live, {
    type: "CONTEXT_REQUESTED",
    requestId: 1,
    selector: { pointId: "point-1" },
  });
  expect(pending.navigation.viewMode).toBe("now");
  expect(pending.navigation.pendingSelection).toEqual({ pointId: "point-1" });
  expect(committedPresentation(pending)).toBe(liveBundle);
});

it("ignores a stale context response", () => {
  const pending = { ...stateWithRequest2 };
  const next = twinOpsReducer(pending, {
    type: "CONTEXT_BUNDLE_RESOLVED",
    requestId: 1,
    context: olderContext,
    bundle: olderHistoricalBundle,
  });
  expect(next).toBe(pending);
});

it("keeps history fixed when a new live snapshot arrives", () => {
  const next = twinOpsReducer(historicalState, {
    type: "LIVE_BUNDLE_RESOLVED", snapshot: newerSnapshot, bundle: newerLiveBundle,
  });
  expect(next.navigation.historicalContext).toBe(historicalState.navigation.historicalContext);
  expect(committedPresentation(next)).toBe(committedPresentation(historicalState));
  expect(next.navigation.newLiveAvailable).toBe(true);
});

it("commits context and its hash-matched decision in one reducer result", () => {
  const next = twinOpsReducer(pendingHistoricalState, {
    type: "CONTEXT_BUNDLE_RESOLVED",
    requestId: 2,
    context: historicalContext,
    bundle: historicalBundle,
  });
  expect(next.navigation.viewMode).toBe("historical");
  expect(committedPresentation(next)).toEqual(historicalBundle);
  expect(historicalBundle.displayContext.viewMode).toBe("historical");
  expect(historicalBundle.decisionSupport.viewMode).toBe("historical");
  expect(historicalBundle.decisionSupport.displayContextHash).toBe(historicalBundle.displayContextHash);
});

it("replaces the prior context with a valid null-anchor gap bundle", () => {
  const next = twinOpsReducer(pendingFromCommittedHistory, {
    type: "CONTEXT_BUNDLE_RESOLVED",
    requestId: 3,
    context: gapContext,
    bundle: gapBundle,
  });
  expect(next.navigation.viewMode).toBe("historical");
  expect(next.navigation.historicalContext).toBe(gapContext);
  expect(committedPresentation(next)).toBe(gapBundle);
  expect(gapBundle.displayContext).toMatchObject({
    anchor: null,
    channels: { s1: null, s2: null },
    assessment: null,
    collectionState: "historical_gap",
  });
  expect(JSON.stringify(gapBundle)).not.toContain(priorHistoricalPointId);
});

it("preserves the exact prior bundle when a different context request fails", () => {
  const next = twinOpsReducer(pendingFromCommittedHistory, {
    type: "CONTEXT_FAILED", requestId: 99, error: publicError,
  });
  expect(next).toBe(pendingFromCommittedHistory);
});
```

- [ ] **Step 2: Run tests to verify RED**

Checked RED Run: capture output from `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/state/twinOpsReducer.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C6 expected-red tests' @(1)`, then require the captured failure to name the missing atomic reducer behavior.

Expected: FAIL because the reducer module does not exist.

- [ ] **Step 3: Implement state and explicit actions**

```js
export const initialTwinOpsState = Object.freeze({
  live: {
    snapshot: null, preparedBundle: null, status: "idle", error: null,
    refreshing: false, lastRefreshAttemptAt: null,
  },
  presentation: { committedBundle: null },
  navigation: {
    viewMode: "now", overview: null, overviewStatus: "idle", overviewError: null,
    overviewQuery: null, pendingSelection: null, activeContextRequestId: null,
    selectedAt: null, selectedPointId: null, selectedSegmentId: null,
    historicalContext: null, contextStatus: "idle", contextError: null,
    newLiveAvailable: false,
    samples: { items: [], nextCursor: null, hasMore: false, status: "idle", error: null },
  },
  controls: {
    sensor: "all", metric: "vibrationVelocityRms", range: "recent",
    selectedCandidateId: null, selectedOperatingCycleId: null, selectedGroup: null,
  },
});
```

Implement exact actions `LIVE_REQUESTED`, `LIVE_BUNDLE_RESOLVED`, `LIVE_FAILED`, `REFRESH_STARTED`, `REFRESH_FINISHED`, `OVERVIEW_REQUESTED`, `OVERVIEW_RESOLVED`, `OVERVIEW_FAILED`, `CONTEXT_REQUESTED`, `CONTEXT_BUNDLE_RESOLVED`, `CONTEXT_FAILED`, `SAMPLES_REQUESTED`, `SAMPLES_RESOLVED`, `SAMPLES_FAILED`, `SET_SENSOR`, `SET_METRIC`, `SET_RANGE`, `SELECT_CANDIDATE`, `SELECT_CYCLE`, `SELECT_GROUP`, and `RETURN_TO_NOW`. Both resolved actions accept an already frozen `{ displayContext, decisionSupport, displayContextHash }` and reject a missing/mismatched hash before changing state. `CONTEXT_BUNDLE_RESOLVED` commits view mode, selection, context and both presentation objects in one returned object only when request IDs match. A contract-valid `historical_gap` is a successful context with nullable anchor: it replaces the entire prior committed bundle atomically and must not merge or carry forward anchor, channels, assessment or evidence. A selected context anchored in `live_collection` is still committed as historical. `CONTEXT_FAILED` ignores unrelated request IDs; for the matching request it records only error metadata and preserves the exact preceding committed bundle. `LIVE_BUNDLE_RESOLVED` commits the full bundle in `now`, but in `historical` only updates the cached live bundle and `newLiveAvailable`. `RETURN_TO_NOW` requires that cached hash-matched live bundle as action payload and atomically clears historical selection while retaining cached overview; there is no intermediate now context with historical decision.

- [ ] **Step 4: Cover all state transitions**

Test overview failure preserving live, context failure preserving the exact committed bundle reference, successful null-anchor gap replacing the prior historical bundle with no carry-forward, selected-live-context committing historical mode, rejection of bundle hash/view-mode mismatches, samples pagination replacing on new fingerprint and appending on same fingerprint, candidate/cycle selection, atomic return-to-now, invalid action throwing, and refresh failure retaining the last real snapshot/bundle.

- [ ] **Step 5: Run tests to verify GREEN**

Checked Run: `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/state/twinOpsReducer.test.js`; immediately run `Assert-NativeExit $LASTEXITCODE 'C6 green tests'`.

Expected: PASS; no action can expose a context without its matching decision in either direction.

- [ ] **Step 6: Commit**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c6CodePaths=@('src/state/twinOpsReducer.js','src/state/twinOpsReducer.test.js') | Sort-Object
Invoke-PhaseCExactCommit -Label 'C6 reducer code' -Message 'feat: add atomic twin navigation reducer' -Paths $c6CodePaths
```

---

### Task 7: Provider Orchestration and Public Actions

**Files:**
- Modify: `src/TwinOpsContext.jsx:1-245`
- Modify: `src/TwinOpsContext.test.jsx:1-342`

**Interfaces:**
- Consumes: Tasks 2, 3, 5 and 6.
- Produces through `useTwinOps()`:

```js
{
  state, liveSnapshot, displayContext, decisionSupport,
  refreshNow, loadTimeline, loadMoreSamples,
  setSensorFilter, setMetric, setRange,
  selectTimelinePoint, selectTimelineAt,
  selectCandidate, selectOperatingCycle, selectGroup,
  returnToNow
}
```

- [ ] **Step 1: Extend provider tests with a complete source stub**

```js
const sourceStub = () => ({
  getSnapshot: vi.fn().mockResolvedValue(snapshot),
  refresh: vi.fn().mockResolvedValue({ refreshAttempted: true, snapshot }),
  getTimelineOverview: vi.fn().mockResolvedValue(overview),
  getTimelineSamples: vi.fn().mockResolvedValue(page),
  getTimelineContext: vi.fn().mockResolvedValue(historicalContext),
});

it("commits a selected point and decision atomically", async () => {
  const observed = [];
  let current;
  function Probe() {
    current = useTwinOps();
    if (current.displayContext && current.decisionSupport) {
      observed.push({
        displayContext: current.displayContext,
        decisionSupport: current.decisionSupport,
      });
    }
    return null;
  }
  render(<Probe />, { wrapper });
  await flush();
  await act(async () => current.selectTimelinePoint("00000000-0000-5000-8000-000000000011"));
  expect(current.state.navigation.viewMode).toBe("historical");
  expect(current.displayContext.anchor.pointId).toBe("00000000-0000-5000-8000-000000000011");
  expect(current.decisionSupport.viewMode).toBe("historical");
  expect(current.decisionSupport.displayContextHash).toMatch(/^sha256:/);
  for (const renderValue of observed) {
    expect(renderValue.displayContext.viewMode).toBe(renderValue.decisionSupport.viewMode);
    expect(renderValue.decisionSupport.displayContextHash).toBe(
      await hashDisplayContextV1(renderValue.displayContext),
    );
  }
});

it("keeps a selected live timeline point in historical mode", async () => {
  source.getTimelineContext.mockResolvedValueOnce(selectedLiveTimelineContext);
  await act(async () => current.selectTimelinePoint(selectedLiveTimelineContext.anchor.pointId));
  expect(current.displayContext).toMatchObject({
    viewMode: "historical",
    conditionTemporalScope: "historical",
    conditionSource: "live_assessment",
  });
  expect(current.decisionSupport.viewMode).toBe("historical");
  expect(current.decisionSupport.nextCheckCodes).not.toContain("escalate_engineering_review");
});

it("commits a successful gap without carrying the previous point", async () => {
  source.getTimelineContext.mockResolvedValueOnce(gapContext);
  await act(async () => current.selectTimelineAt({ at: gapAt, segmentId: gapSegmentId }));
  expect(current.displayContext).toMatchObject({
    viewMode: "historical", anchor: null,
    channels: { s1: null, s2: null }, assessment: null,
    collectionState: "historical_gap",
  });
  expect(JSON.stringify(current.displayContext)).not.toContain(previousPointId);
});
```

- [ ] **Step 2: Run tests to verify RED**

Checked RED Run: capture output from `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/TwinOpsContext.test.jsx`; immediately run `Assert-NativeExit $LASTEXITCODE 'C7 expected-red tests' @(1)`, then require the captured failure to name the missing provider navigation behavior.

Expected: FAIL because the provider does not expose navigation actions.

- [ ] **Step 3: Prepare complete presentation bundles without regressing live polling**

Keep the existing Forzy window, visibility, serialized live request and StrictMode generation tests. Add separate refs `overviewRequestRef`, `contextRequestRef`, `samplesRequestRef`, `decisionGenerationRef`. Aborting one class must not abort another. Every new request captures an integer request ID; only the active ID dispatches success/failure.

```js
async function preparePresentationBundle(displayContext, cryptoImpl = globalThis.crypto) {
  const frozenDisplayContext = cloneAndFreezeDisplayContextV1(displayContext);
  const decisionSupport = await buildOperationalDecisionViewV1(frozenDisplayContext, { cryptoImpl });
  const displayContextHash = await hashDisplayContextV1(frozenDisplayContext, cryptoImpl);
  if (decisionSupport.displayContextHash !== displayContextHash) {
    throw new TypeError("presentation bundle hash mismatch");
  }
  return Object.freeze({
    displayContext: frozenDisplayContext,
    decisionSupport,
    displayContextHash,
  });
}
```

- [ ] **Step 4: Commit only complete hash-matched bundles**

For snapshot load/refresh, first validate the B response, call `fromLiveSnapshot(snapshot)`, await `preparePresentationBundle`, recheck request/generation ownership and only then dispatch one `LIVE_BUNDLE_RESOLVED`. For historical navigation, first validate `TimelineContextV1`, call `fromHistoricalContext` even when the selected anchor's `sourceKind` is `live_collection`, await the same helper, recheck ownership and only then dispatch one `CONTEXT_BUNDLE_RESOLVED`. A valid null-anchor gap follows this success path and replaces the previous bundle; a transport/validation/hash failure follows `CONTEXT_FAILED` and preserves it. Pending/loading metadata may render separately, but `useTwinOps()` continues exposing the previous `committedPresentation` until the new bundle is complete. Do not use a `useMemo` + later decision effect, do not calculate from `pendingSelection`, and do not dispatch raw context before its decision exists.

- [ ] **Step 5: Implement navigation actions**

`selectTimelinePoint(pointId)` calls context with only `pointId`. `selectTimelineAt({ at, segmentId })` calls only those two fields. `selectCandidate(candidateId)` finds the validated/ranked candidate in the current overview, dispatches selection metadata, then delegates only to `candidate.anchorPointId`; no other candidate member supplies the context point. A selected point/candidate always enters historical inspection regardless of live/archive source; only `returnToNow` enters `now`. `selectOperatingCycle` uses only the selected `TimelineOperatingCycleV1.startAt/endAt` and `operatingCycleId`, converts its contracted inclusive end to the public half-open query through the shared helper below, and updates focus/reloads the overview:

```js
const cycleToHalfOpenRange = (cycle) => ({
  from: cycle.startAt,
  to: addOneMillisecondUtc(cycle.endAt),
});
```

The +1 ms query must return the terminal original point and terminal candidate whose `eventAt === cycle.endAt`; it never uses a microsecond or locale/string trick. `refreshNow` keeps the committed historical bundle. `returnToNow` aborts pending context and dispatches `RETURN_TO_NOW` only with the newest already-prepared live bundle.

- [ ] **Step 6: Add race/failure tests**

Resolve context request 2 before request 1 and assert request 1 is ignored. Delay historical hashing and record every provider render: every non-null pair must have the same `viewMode`, matching canonical hash and matching `decisionAsOf`; the sequence may be all-now followed by all-historical, never a mixed render. Repeat the observation while returning to now. Select a live-source point and assert every committed render remains historical with `historical/live_assessment`, then call `returnToNow` explicitly. Resolve a valid gap and assert it replaces all prior values; separately fail a context request and assert the exact prior bundle remains. Test `cycleToHalfOpenRange` across a second boundary and assert same-millisecond terminal point/candidate fixtures are included. Refresh live during historical inspection and assert `newLiveAvailable` without changing the committed bundle. Fail overview/context/samples/hash independently and assert the previous bundle remains. Unmount and assert all active signals abort. Change dataSource during pending requests and assert old responses never own state.

- [ ] **Step 7: Run focused and regression tests**

Checked Run: `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/TwinOpsContext.test.jsx src/App.test.jsx`; immediately run `Assert-NativeExit $LASTEXITCODE 'C7 green tests'`.

Expected: PASS, including all existing schedule/visibility/StrictMode tests and a render ledger with zero context/decision mixtures.

- [ ] **Step 8: Commit**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c7CodePaths=@('src/TwinOpsContext.jsx','src/TwinOpsContext.test.jsx') | Sort-Object
Invoke-PhaseCExactCommit -Label 'C7 provider code' -Message 'feat: orchestrate live and historical display state' -Paths $c7CodePaths
```

---

### Task 8: Decision Summary, Contextual Sensor Cards and Data Reliability

**Files:**
- Create: `src/components/operations/DecisionSummary.jsx`
- Create: `src/components/operations/DecisionSummary.test.jsx`
- Create: `src/components/operations/DataReliabilityPanel.jsx`
- Create: `src/components/operations/DataReliabilityPanel.test.jsx`
- Create: `src/components/operations/EvidenceExportButton.jsx`
- Create: `src/components/operations/EvidenceExportButton.test.jsx`
- Modify: `src/components/operations/AssetHeader.jsx:1-end`
- Modify: `src/components/operations/SensorCard.jsx:1-end`
- Modify: `src/components/operations/AssessmentPanel.jsx:1-end`
- Modify: `src/components/operations/OperationsPanels.test.jsx:1-142`

**Interfaces:**
- Consumes: `DisplayContextV1`, `OperationalDecisionViewV1`, Task 4 summary builder and the exact validated `operationalTriageRulesetV1` bundle from Task 3.
- Produces: semantic first-fold components with no independent business rules.

- [ ] **Step 1: Write failing first-fold and forbidden-copy tests**

```jsx
render(<DecisionSummary decision={decision} displayContext={displayContext} />);
expect(screen.getByRole("heading", {
  name: operationalTriageRulesetV1.modeTitles[decision.viewMode],
})).toBeVisible();
expect(screen.getByText(
  operationalTriageRulesetV1.summaryTemplates[decision.summaryCode],
)).toBeVisible();
expect(screen.getByText(
  operationalTriageRulesetV1.dataTrustLabels[decision.dataTrust],
)).toBeVisible();
expect(screen.getByText(
  operationalTriageRulesetV1.nextCheckLabels[decision.nextCheckCodes[0]],
)).toBeVisible();
expect(screen.getByTestId("decision-persistence")).toHaveAttribute(
  "data-evidence-state", "available",
);
expect(screen.getByTestId("decision-persistence")).toHaveTextContent("3 leituras");
expect(screen.getByTestId("decision-dominant-evidence")).toHaveAttribute(
  "data-evidence-state", "available",
);
expect(screen.getByTestId("decision-dominant-evidence")).toHaveTextContent(/S1.*vibração/i);
expect(screen.queryByText(/anomalyScore|deteriorationScore|continue operando|pare o equipamento/i)).not.toBeInTheDocument();
```

Rerender with a contract-valid no-evidence context and assert `decision-persistence` says “Persistência indisponível no contrato” and `decision-dominant-evidence` says “Evidência dominante não determinada”, both with `data-evidence-state="unavailable"`. Add historical assertions for “naquele instante”, `conditionAsOf`, “não representa condição atual”, gap and last-known.

- [ ] **Step 2: Run tests to verify RED**

Checked RED Run: capture output from `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/operations/DecisionSummary.test.jsx src/components/operations/OperationsPanels.test.jsx`; immediately run `Assert-NativeExit $LASTEXITCODE 'C8 expected-red tests' @(1)`, then require the captured failure to name the missing decision-first UI.

Expected: FAIL because the decision-first components do not exist.

- [ ] **Step 3: Implement DecisionSummary as pure code-to-copy rendering**

```jsx
export default function DecisionSummary({ decision, displayContext, newLiveAvailable, onReturnToNow }) {
  const title = operationalTriageRulesetV1.modeTitles[decision.viewMode];
  const summary = formatCanonicalTemplate(
    operationalTriageRulesetV1.summaryTemplates[decision.summaryCode],
    {
      conditionAsOf: decision.conditionAsOf,
      conditionLabel: operationalTriageRulesetV1.conditionLabels[decision.conditionState],
    },
  );
  return (
    <section className="decision-summary" aria-labelledby="decision-title" data-testid="decision-guidance">
      <div>
        <p className="eyebrow">Suporte à decisão</p>
        <h2 id="decision-title">{title}</h2>
        <p className="decision-summary__copy">{summary}</p>
      </div>
      <DecisionFacts decision={decision} displayContext={displayContext} />
      <NextChecks codes={decision.nextCheckCodes} labels={operationalTriageRulesetV1.nextCheckLabels} />
      {newLiveAvailable && <button type="button" onClick={onReturnToNow}>Novo dado disponível · Voltar para agora</button>}
    </section>
  );
}
```

Mode/condition/trust labels plus summary, check and limitation copy are indexed directly from the deep-frozen validated `operationalTriageRulesetV1` bundle. `formatCanonicalTemplate` substitutes only the prevalidated `{conditionAsOf}`/`{conditionLabel}` tokens and owns no phrase. No component, helper, fixture or local map repeats canonical text. Local maps may contain only non-text presentation metadata such as CSS class/icon/ARIA relationship; unknown canonical codes are contract errors handled by the existing safe error boundary, never by a second fallback-copy table. Add an `rg` assertion/test that every value of `modeTitles`, `conditionLabels`, `dataTrustLabels`, `summaryTemplates`, `nextCheckLabels` and `limitationLabels` occurs as authored copy only in `contracts/v2/rulesets/forzy-operational-triage-v1.json`.

`DecisionFacts` also renders two stable first-fold locators: `[data-testid="decision-persistence"]` and `[data-testid="decision-dominant-evidence"]`. It selects persistence and dominant sensor/metric only by matching `displayContext.driverEvidenceIds` against the already allowlisted `displayContext.exportableEvidence` order; it never ranks raw magnitudes. A contracted count/duration and sensor/metric receive `data-evidence-state="available"`; absence receives the two explicit unavailable strings tested above with `data-evidence-state="unavailable"`. These facts remain inside `DecisionSummary`, not a collapsed details panel or tooltip.

Freeze the remaining first-fold locator contract in the same component tests: `AssetHeader` exposes `[data-testid="asset-mode"]` and `[data-testid="last-observation"]`; `DecisionFacts` exposes `[data-testid="data-trust"]`; the rendered canonical summary uses `[data-testid="decision-summary"]`; and each visible next-check item uses `[data-testid="next-check"]`. Test IDs provide stable automation hooks only and never carry business state or copy.

- [ ] **Step 4: Upgrade sensors and assessment**

`SensorCard` receives `{ channel, evidence, displayContext }`. Each metric renders value, unit and temporal context; evidence adds baseline, deviation, direction, persistence and window. Missing comparison renders “Comparação indisponível”, never zero. Flags render individual operational descriptions and impact. `AssessmentPanel` puts evidence/limitations first and raw scores inside a closed `<details>` labelled “Detalhes técnicos do modelo”; the detail includes exact score semantics, baseline and “não é probabilidade de falha”.

- [ ] **Step 5: Replace integration language with data reliability**

`DataReliabilityPanel` receives only `{ displayContext }`. It renders last reading, backend-supplied age/facts, last attempt, last success, next expected collection, gaps and S1/S2 state from `displayContext.publicAcquisition` plus the same bundle's decision dimensions. It never reads `liveSnapshot` while historical. Upstream error changes availability/trust text and never condition styling. Unknown errors render “Erro de integração” without raw detail.

- [ ] **Step 6: Implement export control with clipboard fallback**

The button calls `buildEvidenceSummaryV1`, serializes canonical pretty JSON, tries `navigator.clipboard.writeText`, and on denied permission exposes a readonly labelled textarea plus download link made from a Blob. Announce “Resumo copiado” or “Cópia manual disponível” through `role="status"`.

- [ ] **Step 7: Run tests to verify GREEN**

Checked Run: `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/operations/DecisionSummary.test.jsx src/components/operations/DataReliabilityPanel.test.jsx src/components/operations/EvidenceExportButton.test.jsx src/components/operations/OperationsPanels.test.jsx`; immediately run `Assert-NativeExit $LASTEXITCODE 'C8 green tests'`.

Expected: PASS for now/historical/gap/degraded/zero/missing metric, sanitized errors and clipboard fallback.

- [ ] **Step 8: Commit**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c8CodePaths=@(
  'src/components/operations/AssessmentPanel.jsx',
  'src/components/operations/AssetHeader.jsx',
  'src/components/operations/DataReliabilityPanel.jsx',
  'src/components/operations/DataReliabilityPanel.test.jsx',
  'src/components/operations/DecisionSummary.jsx',
  'src/components/operations/DecisionSummary.test.jsx',
  'src/components/operations/EvidenceExportButton.jsx',
  'src/components/operations/EvidenceExportButton.test.jsx',
  'src/components/operations/OperationsPanels.test.jsx',
  'src/components/operations/SensorCard.jsx'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'C8 operations UI' -Message 'feat: present operational decisions before telemetry' -Paths $c8CodePaths
```

---

### Task 9: Proportional Timeline View Model and Charts

**Files:**
- Create: `src/components/timeline/timelineViewModel.js`
- Create: `src/components/timeline/timelineViewModel.test.js`
- Create: `src/components/timeline/TimelineControls.jsx`
- Create: `src/components/timeline/TimelineOverview.jsx`
- Create: `src/components/timeline/TimelineDetailChart.jsx`
- Create: `src/components/timeline/TimelineWorkspace.jsx`
- Create: `src/components/timeline/TimelineWorkspace.test.jsx`

**Interfaces:**
- Consumes: validated `TimelineOverviewV1`, where each series owns `segmentId`, `sensorId`, `sourceKind`, `metric`, `aggregation` and reduced `points`; every reduced point is exactly `{pointId,eventAt,value}` and the reduction method is `series.aggregation.method`.
- Produces: `buildTimelineViewModel(overview, { sensor, metric, focusedSegmentId })` and synchronized overview/detail controls. Detailed provenance, timestamp quality and public flags are never synthesized from a reduced point; they enter the UI only through validated `/timeline/samples` rows or the selected `/timeline/context`.

- [ ] **Step 1: Write failing view-model tests**

```js
it("keeps archive and live in proportional calendar coordinates", () => {
  const model = buildTimelineViewModel(overview, {
    sensor: "all", metric: "temperature", focusedSegmentId: "archive-segment",
  });
  expect(model.domain).toEqual([
    parseCanonicalUtcMillis(overview.effectiveRange.from),
    parseCanonicalUtcMillis(overview.effectiveRange.to),
  ]);
  expect(model.requestedRange).toEqual(overview.requestedRange);
  expect(model.availableRange).toEqual(overview.availableRange);
  expect(model.aggregationSummary).toEqual(overview.aggregationSummary);
  expect(model.series).toHaveLength(4);
  expect(model.series.every(({ segmentId }) => typeof segmentId === "string")).toBe(true);
  expect(new Set(model.series.map(({ segmentId, sourceKind, sensorId }) => `${segmentId}|${sourceKind}|${sensorId}`)).size)
    .toBe(model.series.length);
  expect(model.series.map(({ aggregation }) => aggregation.method))
    .toEqual(overview.series.map(({ aggregation }) => aggregation.method));
  for (const series of overview.series) {
    for (const point of series.points) {
      expect(Object.keys(point).sort()).toEqual(["eventAt", "pointId", "value"]);
      expect(point).not.toHaveProperty("provenance");
      expect(point).not.toHaveProperty("flags");
    }
  }
  expect(model.gaps[0].gapType).toBe(overview.gaps[0].gapType);
  expect(model.gaps[0].durationMs).toBe(
    parseCanonicalUtcMillis(model.gaps[0].to) - parseCanonicalUtcMillis(model.gaps[0].from),
  );
});

it("preserves a single visible point", () => {
  const model = buildTimelineViewModel(singlePointOverview, {
    sensor: "s1", metric: "temperature", focusedSegmentId: "live-segment",
  });
  expect(model.series[0].showSinglePointMarker).toBe(true);
});

it("preserves a contracted zero-point series without inventing a point or marker", () => {
  const model = buildTimelineViewModel(overviewWithEmptySeries, {
    sensor: "all", metric: "temperature", focusedSegmentId: "archive-empty-segment",
  });
  const empty = model.series.find(({ segmentId }) => segmentId === "archive-empty-segment");
  expect(empty).toBeDefined();
  expect(empty.points).toEqual([]);
  expect(empty.showSinglePointMarker).toBe(false);
  expect(empty).not.toHaveProperty("placeholderPoint");
  expect(model.candidates.some(({ anchorPointId }) => anchorPointId === "synthetic-empty-point"))
    .toBe(false);
});

it("preserves distinct reduced points and candidates at the same millisecond", () => {
  const model = buildTimelineViewModel(sameMillisecondOverview, {
    sensor: "all", metric: "temperature", focusedSegmentId: "live-segment",
  });
  expect(model.series.flatMap(({ points }) => points).filter(({ eventAt }) => eventAt === SAME_MILLISECOND))
    .toHaveLength(2);
  expect(model.candidates.filter(({ eventAt }) => eventAt === SAME_MILLISECOND))
    .toHaveLength(2);
});
```

- [ ] **Step 2: Run tests to verify RED**

Checked RED Run: capture output from `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/timeline/timelineViewModel.test.js src/components/timeline/TimelineWorkspace.test.jsx`; immediately run `Assert-NativeExit $LASTEXITCODE 'C9 expected-red tests' @(1)`, then require the captured failure to name the missing timeline view model/workspace.

Expected: FAIL because timeline components do not exist.

- [ ] **Step 3: Implement segment-safe transformation**

Consume each contracted series' root `segmentId + sensorId + sourceKind + metric` identity; never expect `segmentId` inside a point and never emit one line that crosses a source or gap. Preserve **every** contracted series, including `points: []`, with its original identity and aggregation metadata. An empty series remains `points: []`, has `showSinglePointMarker=false`, and creates neither placeholder point, fallback timestamp/value nor candidate/marker; only a series with exactly one contracted original reduced point receives the single-point marker. A reduced point supplies exactly its original `pointId`, canonical `eventAt` and finite metric `value`; retain those IDs when multiple points share a millisecond, but never read or fabricate point-level provenance, timestamp quality or flags from the overview. Those detailed fields come only from validated `/timeline/samples` rows or the selected `/timeline/context`. Convert every range, gap and `eventAt` with `parseCanonicalUtcMillis`, never permissive `Date.parse` or lexical ordering. Preserve each gap's contracted `gapType`; do not rename it to `type`. Copy `requestedRange`, nullable `effectiveRange`, nullable `availableRange` and `aggregationSummary` without renaming. Use `effectiveRange{from,to}` as the proportional overview domain; when it is null, emit an empty model/domain rather than synthesizing bounds. Use `availableRange` only for availability/preset affordances and `requestedRange` only to show what the caller requested. Focused segment bounds remain the detail domain. Expose root aggregation text from `aggregationSummary` as `“{returnedPointCount} de {originalPointCount} pontos · {reducedSeriesCount} séries reduzidas”`; per-series `aggregation.method` remains a technical detail and never replaces the root totals.

- [ ] **Step 4: Implement accessible controls**

Use fieldsets/radios for S1/S2/Ambos and three metrics; buttons for “Histórico de maio”, “Dados recentes”, “Ver período completo” and “Voltar para agora”. Buttons call provider actions and maintain `aria-pressed`. Zoom/pan changes `[from,to)` and triggers a new overview GET; it never transforms reduced points into context locally.

- [ ] **Step 5: Render overview and detail without hidden gaps**

Use Recharts numeric X axes with `type="number"`, `scale="time"`, and explicit domains. Render one `<Line>` per model series, `connectNulls={false}`, distinct dash/pattern plus textual legend, source/gap `ReferenceArea`s, candidate markers and a custom dot when `showSinglePointMarker`. A plotted reduced point may show only timestamp/value plus its stable selection identity; richer evidence waits for the samples/context response. Candidate markers retain the closed candidate object separately from reduced series; selecting one calls `selectTimelinePoint(candidate.anchorPointId)` and no other candidate member supplies a point selector. Selecting a candidate in the live segment still opens historical inspection. Continuous cursor release calls `selectTimelineAt({ at, segmentId })`.

- [ ] **Step 6: Compose error and empty states**

`TimelineWorkspace` keeps controls and last valid overview visible on a refetch error, labels gaps as missing coverage rather than asset state, and never replaces the live decision surface. A live-only overview disables “Histórico de maio” with explanatory text rather than throwing.

- [ ] **Step 7: Run tests to verify GREEN**

Checked Run: `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/timeline/timelineViewModel.test.js src/components/timeline/TimelineWorkspace.test.jsx`; immediately run `Assert-NativeExit $LASTEXITCODE 'C9 green tests'`.

Expected: PASS for proportional `gapType`, no cross-source line, exact `{pointId,eventAt,value}` reduced-point consumption, preservation of a contracted `points: []` series without invented point/marker, `series.aggregation.method`, no reduced-point provenance/flags dependency, candidate omitted from reduced series but still selectable, single point, zero, loading/error/live-only and keyboard controls.

- [ ] **Step 8: Commit**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c9CodePaths=@(
  'src/components/timeline/TimelineControls.jsx',
  'src/components/timeline/TimelineDetailChart.jsx',
  'src/components/timeline/TimelineOverview.jsx',
  'src/components/timeline/TimelineWorkspace.jsx',
  'src/components/timeline/TimelineWorkspace.test.jsx',
  'src/components/timeline/timelineViewModel.js',
  'src/components/timeline/timelineViewModel.test.js'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'C9 timeline UI' -Message 'feat: add proportional unified timeline' -Paths $c9CodePaths
```

---

### Task 10: Candidate Queue, Cycle Navigator, Original-Point Table and Evidence Panel

**Files:**
- Create: `src/components/timeline/CandidateQueue.jsx`
- Create: `src/components/timeline/CandidateQueue.test.jsx`
- Create: `src/components/timeline/OperatingCycleNavigator.jsx`
- Create: `src/components/timeline/TimelineDataTable.jsx`
- Create: `src/components/timeline/TimelineDataTable.test.jsx`
- Create: `src/components/timeline/EventEvidencePanel.jsx`
- Create: `src/components/timeline/EventEvidencePanel.test.jsx`
- Modify: `src/components/timeline/TimelineWorkspace.jsx:1-end`
- Modify: `src/components/timeline/TimelineWorkspace.test.jsx:1-end`

**Interfaces:**
- Consumes: Task 4 `buildCandidateReviewScopesV1` + per-scope ranking, overview candidates/cycles, provider selection and sample pagination.
- Produces: keyboard-accessible investigation workflow and sanitized evidence copy.

- [ ] **Step 1: Write failing candidate and pagination tests**

```jsx
const scopes = buildCandidateReviewScopesV1({
  overview, viewMode: "now", inspectedSourceKind: null, inspectedBatchId: null,
  inspectedSensorId: null, focusedOperatingCycleIds: [],
});
const [{ scope, candidates: ranked }] = scopes.map((scope) => ({
  scope,
  candidates: rankCandidatesV1(overview.eventCandidates, scope),
}));
render(<CandidateQueue scope={scope} candidates={ranked} onInvestigate={onInvestigate} />);
expect(screen.getByText(reviewPriorityRulesetV1.queueDisclaimer)).toBeVisible();
expect(screen.getByText(reviewPriorityRulesetV1.candidateRankingVersion)).toBeVisible();
expect(screen.getAllByRole("button", { name: "Investigar" })).toHaveLength(ranked.length);
fireEvent.click(screen.getAllByRole("button", { name: "Investigar" })[0]);
expect(onInvestigate).toHaveBeenCalledWith(ranked[0].candidateId);
expect(screen.queryByText(/criticidade|ordem de serviço|risco físico/i)).not.toBeInTheDocument();
```

```jsx
render(<TimelineDataTable page={page1} onLoadMore={onLoadMore} />);
expect(screen.getByRole("table", { name: "Pontos originais do intervalo" })).toBeVisible();
fireEvent.click(screen.getByRole("button", { name: "Carregar mais pontos" }));
expect(onLoadMore).toHaveBeenCalledWith(page1.nextCursor);
```

```jsx
render(<EventEvidencePanel candidate={candidateWithEpisodeStart} displayContext={context} />);
expect(screen.getByText("Início do episódio").nextSibling)
  .toHaveTextContent(candidateWithEpisodeStart.episodeStartedAt);
rerender(<EventEvidencePanel candidate={candidateWithoutEpisodeStart} displayContext={contextWithoutEpisodeStart} />);
expect(screen.getByText("Início do episódio").nextSibling)
  .toHaveTextContent("Indisponível no contrato");
```

- [ ] **Step 2: Run tests to verify RED**

Checked RED Run: capture output from `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/timeline/CandidateQueue.test.jsx src/components/timeline/TimelineDataTable.test.jsx src/components/timeline/EventEvidencePanel.test.jsx`; immediately run `Assert-NativeExit $LASTEXITCODE 'C10 expected-red tests' @(1)`, then require the captured failure to name the missing investigation UI.

Expected: FAIL because components do not exist.

- [ ] **Step 3: Implement the review queue**

`TimelineWorkspace` must call `buildCandidateReviewScopesV1` from the committed overview/current inspection **before** rendering any queue, rank each returned scope independently, and render one labelled `CandidateQueue` per exact group. It never passes `overview.eventCandidates` directly to a single global queue. For now mode this yields live-only groups even when `overview.activeHistoricalBatchId` is non-null; historical inspection of a live point/candidate remains live-source/null-batch groups. Archive groups must match the active batch and selected cycles. A test feeds mixed archive/live, sensor, fold and model candidates and asserts no DOM list interleaves group keys.

Within one scope, render an ordered list with timestamp, sensor, metric or “Métrica causadora não determinada”, cycle, `persistenceCount` formatted only through `reviewPriorityRulesetV1.persistenceTemplate`, trust and “Investigar”. Never convert the count to seconds from a nominal cadence. Show `reviewPriorityRulesetV1.candidateRankingVersion` and render `reviewPriorityRulesetV1.queueDisclaimer` directly; do not duplicate either phrase in a component map. Never show anomaly/deterioration scores in the queue.

- [ ] **Step 4: Implement cycle navigation from contract data**

Use a labelled `<select>` populated from `overview.operatingCycles`; its count comes from `operatingCycles.length`, not `204`. Each option consumes exactly `operatingCycleId`, `startAt`, inclusive `endAt`, `durationSeconds`, `candidateCount`, nullable `gapBeforeSeconds` and nullable `previousOperatingCycleId`: show the gap anterior in seconds or “sem gap anterior”, never uma contagem derivada. The provider receives the selected cycle through `cycleToHalfOpenRange`, so `to = addOneMillisecondUtc(endAt)` and terminal point/candidate fixtures remain visible. “Comparar com ciclo anterior” is enabled only when the selected cycle's `previousOperatingCycleId` is non-null; it calls `selectOperatingCycle(previousOperatingCycleId)`. The A/B validator already guarantees same active batch/source and immediate chronology; the UI does not invent another alias nem recalcula comparabilidade.

- [ ] **Step 5: Implement visible original-point table**

Place the table inside a `<details>` labelled “Tabela dos pontos originais”. Its rows come exclusively from validated `/timeline/samples`, never from reduced `TimelineOverviewV1.series[].points`. Columns are timestamp, sensor, metric, value, unit, source, timestamp quality and public flags. Rows use original `pointId` as key and a “Ver contexto” button. Pagination appends only when the response fingerprint matches; 409 clears pages and asks the provider to reload the active overview.

- [ ] **Step 6: Implement event evidence panel**

Render “Início do episódio” exclusively from `resolveContractedEpisodeStartedAt({ candidate, assessment, evidence: { conditionEpisodeStartedAt: displayContext.conditionEpisodeStartedAt } })`, followed by persistence, sensor, metric, value, baseline, deviation, direction, quality, source, model/fold, causal window and limitations. This compares the candidate field, the backend decision fact, and historical-assessment persistence only for the validated historical discriminant; it never dereferences persistence on a live v2 assessment. When all contracted episode-start sources are absent, render “Indisponível no contrato”; conflicting values fail closed. Never infer start from persistence, nominal cadence, `eventAt`, the first plotted point or the visible range. Missing dominant metric remains explicit. Use `EvidenceExportButton`. State permanently that mechanical origin and S1/S2 position are not determined. Do not show physical inspection instructions.

- [ ] **Step 7: Integrate and run GREEN**

Checked Run: `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/timeline/CandidateQueue.test.jsx src/components/timeline/TimelineDataTable.test.jsx src/components/timeline/EventEvidencePanel.test.jsx src/components/timeline/TimelineWorkspace.test.jsx`; immediately run `Assert-NativeExit $LASTEXITCODE 'C10 green tests'`.

Expected: PASS for ranking label, keyboard investigation, inclusive cycle terminal records, causal previous-cycle guard, page append/reset, accessible table, contracted episode start/no-inference state and sanitized export.

- [ ] **Step 8: Commit**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c10CodePaths=@(
  'src/components/timeline/CandidateQueue.jsx',
  'src/components/timeline/CandidateQueue.test.jsx',
  'src/components/timeline/EventEvidencePanel.jsx',
  'src/components/timeline/EventEvidencePanel.test.jsx',
  'src/components/timeline/OperatingCycleNavigator.jsx',
  'src/components/timeline/TimelineDataTable.jsx',
  'src/components/timeline/TimelineDataTable.test.jsx',
  'src/components/timeline/TimelineWorkspace.jsx',
  'src/components/timeline/TimelineWorkspace.test.jsx'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'C10 investigation UI' -Message 'feat: add timeline investigation workflow' -Paths $c10CodePaths
```

---

### Task 11: Decision-First Dashboard and Shared 3D Context Seam

**Files:**
- Modify: `src/components/operations/OperationsDashboard.jsx:1-end`
- Delete after replacement: `src/components/operations/TelemetryTrend.jsx`
- Delete after replacement: `src/components/operations/IntegrationHealth.jsx`
- Modify: `src/App.jsx:1-end`
- Modify: `src/App.test.jsx:1-176`
- Reuse unchanged: `src/components/Twin3D.jsx`
- Reuse unchanged: `src/components/Twin3D.test.jsx`
- Reuse unchanged: `src/components/twin3d/**`
- Modify: `src/styles.css:1-end`
- Modify from independent review: `docs/verification/phase-c-findings.json` (preserve cumulative C1 finding lineage)
- Create after review: `docs/verification/checkpoints/c11-dashboard-integration-handoff.json`
- Modify through verifier only: `docs/verification/unified-twin-acceptance-v1.json`
- Regenerate through verifier only: `docs/verification/unified-twin-acceptance-v1.md`

**Interfaces:**
- Consumes: provider state/actions, Tasks 8-10 components, and the plan-D public seam `Twin3DComponent({ displayContext, selectedGroup, onSelectGroup, selectedSensor, onSelectSensor })`; D internally owns the sole context-aware fallback.
- Produces: final dashboard hierarchy and App/Dashboard prop wiring only; no implementation inside `Twin3D.jsx` or `src/components/twin3d/**`, plus the exact reviewed C11 code/evidence SHAs required by D8.

- [ ] **Step 0: Accept the exact D7 public-seam handoff before changing C11 files**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$d7PublicSeamCommit = $env:D7_PUBLIC_SEAM_COMMIT
if ($d7PublicSeamCommit -notmatch '^[0-9a-f]{40}$') { throw 'exact D7 public seam SHA is required' }
git merge-base --is-ancestor $d7PublicSeamCommit HEAD
Assert-NativeExit $LASTEXITCODE 'D7 public seam ancestry before C11'
$expectedD7Scope = @('src/components/Twin3D.jsx','src/components/Twin3D.test.jsx') | Sort-Object
$rawD7Scope = @(git diff-tree --no-commit-id --name-only -r $d7PublicSeamCommit)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read D7 public seam scope'
$actualD7Scope = @($rawD7Scope | Sort-Object)
if (Compare-Object $expectedD7Scope $actualD7Scope) { throw 'D7 seam commit scope mismatch' }
$rawC11StartStatus = @(git status --porcelain=v1 --untracked-files=all)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read C11 starting status'
if ($rawC11StartStatus.Count -ne 0) { throw 'C11 must start from a clean D7-integrated tree' }
$rawC11BaseCommit = git rev-parse HEAD
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'freeze C11 base commit'
$c11BaseCommit = ($rawC11BaseCommit -join "`n").Trim()
if ($c11BaseCommit -notmatch '^[0-9a-f]{40}$') { throw 'invalid C11 base SHA' }
```

Record `$d7PublicSeamCommit` and `$c11BaseCommit` in the C11 execution handoff. The base may contain completed C2-C10 work, but D7 must be its ancestor. No C11 scope check uses the global phase base.

- [ ] **Step 1: Rewrite App tests for hierarchy and shared instant**

```jsx
const Twin3DProbe = vi.fn(({ displayContext, selectedGroup, selectedSensor }) => (
  <output data-testid="twin3d-probe">
    {displayContext.decisionAsOf}:{selectedGroup ?? "all"}:{selectedSensor}
  </output>
));
render(<App dataSource={sourceWithTimeline()} Twin3DComponent={Twin3DProbe} />);
await flush();

const decision = screen.getByTestId("decision-guidance");
const timeline = screen.getByTestId("timeline-workspace");
const twin = screen.getByTestId("twin-panel");
expect(decision.compareDocumentPosition(timeline) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
expect(timeline.compareDocumentPosition(twin) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
expect(Twin3DProbe.mock.calls.at(-1)[0].displayContext.viewMode).toBe("now");
expect(Object.keys(Twin3DProbe.mock.calls.at(-1)[0]).sort()).toEqual([
  "displayContext", "onSelectGroup", "onSelectSensor", "selectedGroup", "selectedSensor",
]);
```

After selecting a historical point, assert DecisionSummary, both sensor cards, AssessmentPanel, timeline cursor and Twin3D probe all show the same `decisionAsOf`/`samplePairId`. Add one integration test with the default plan-D component (no injected fallback prop), force WebGL/asset failure through D's documented test seam, and assert `[data-twin-fallback="true"]` stays visible with the same historical `decisionAsOf`, sensor facts and controls. Assert neither App nor Dashboard imports/renders `TwinFallback` and the five-prop probe never receives `fallback`.

- [ ] **Step 2: Run integration tests to verify RED**

Checked RED Run: capture output from `npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/App.test.jsx src/components/operations/OperationsPanels.test.jsx`; immediately run `Assert-NativeExit $LASTEXITCODE 'C11 expected-red tests' @(1)`, then require the captured failure to name only the missing hierarchy/five-prop seam wiring.

Expected: FAIL because App/Dashboard still render 3D first and do not pass the plan-D public seam props to the injected mock.

- [ ] **Step 3: Recompose OperationsDashboard in fixed order**

```jsx
<AssetHeader displayContext={displayContext} decision={decisionSupport} />
<DecisionSummary decision={decisionSupport} displayContext={displayContext} {...decisionActions} />
<section className="sensor-grid" aria-label="Sensores no contexto exibido">...</section>
<TimelineWorkspace {...timelineProps} />
<AssessmentPanel assessment={displayContext.assessment} decision={decisionSupport} />
<section className="panel twin-panel" data-testid="twin-panel">
  <Twin3DComponent
    displayContext={displayContext}
    selectedGroup={state.controls.selectedGroup}
    onSelectGroup={selectGroup}
    selectedSensor={state.controls.sensor}
    onSelectSensor={setSensorFilter}
  />
  <p>S1/S2 sem posição física validada; o grupo selecionado não identifica a origem do desvio.</p>
</section>
<DataReliabilityPanel displayContext={displayContext} />
```

Loading decision hashes uses an honest compact skeleton in the first fold; it never falls back to raw status text. Timeline failure renders an inline warning while the decision and live cards remain.

- [ ] **Step 4: Wire the plan-D public 3D seam without touching its implementation**

Modify only `App.jsx`, `App.test.jsx` and `OperationsDashboard.jsx`: forward exactly `displayContext`, `selectedGroup`, `onSelectGroup`, `selectedSensor` and `onSelectSensor` to the injected `Twin3DComponent`. Do not create/import a legacy `TwinFallback`, do not pass `fallback`, and do not patch/stage `Twin3D.jsx`, `Twin3D.test.jsx` or any `src/components/twin3d/**` file. Use `Twin3DProbe` for prop/hierarchy tests and the unchanged default D component only for the public `data-twin-fallback` integration assertion. Keep the non-localization sentence adjacent to the seam so the single D-owned context-aware fallback inherits the same safety context.

- [ ] **Step 5: Implement first-fold and accessibility CSS**

```css
.operations-shell { width: min(100% - 2rem, 1280px); padding-block: 1rem 3rem; }
.decision-first-grid { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(18rem, 0.8fr); gap: 1rem; }
.decision-summary { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1rem; padding: 1rem 1.25rem; }
.timeline-source--historical { stroke-dasharray: 7 4; }
.timeline-source--live { stroke-dasharray: none; }
.timeline-gap { background: repeating-linear-gradient(135deg, transparent 0 8px, rgb(251 191 36 / 18%) 8px 16px); }
.timeline-control[aria-pressed="true"] { outline: 2px solid var(--teal); outline-offset: 2px; }
@media (max-width: 900px) { .decision-first-grid, .decision-summary { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { .timeline-cursor, .twin-selection-ring { transition: none; animation: none; } }
```

Retain the existing visible `:focus-visible` outline. Sensor/source/state distinctions require text or line pattern as well as color.

- [ ] **Step 6: Remove obsolete components and run full frontend tests**

Remove the two obsolete imports, migrate their remaining assertions, then run `rg "TelemetryTrend|IntegrationHealth" src`, capture `$nativeExit=$LASTEXITCODE` immediately, require `Assert-NativeExit $nativeExit 'obsolete component consumer scan' @(1)`, and only then delete `TelemetryTrend.jsx` and `IntegrationHealth.jsx`. Exit `0` means consumers remain and blocks deletion; any exit other than `1` is a scan failure.

Checked Run: `npm.cmd run test:run -- --exclude "**/.pytest_cache/**"`; immediately run `Assert-NativeExit $LASTEXITCODE 'C11 full tests'`.

Expected: all Vitest suites PASS; no test depends on `snapshot.history` as the main timeline.

- [ ] **Step 7: Build production bundle**

Checked Run: `npm.cmd run build`; immediately run `Assert-NativeExit $LASTEXITCODE 'C11 build'`.

Expected: Vite exits 0; lazy 3D chunk and main assets are emitted with no unresolved imports.

- [ ] **Step 8: Commit**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c11CodePaths=@(
  'src/App.jsx',
  'src/App.test.jsx',
  'src/components/operations/IntegrationHealth.jsx',
  'src/components/operations/OperationsDashboard.jsx',
  'src/components/operations/TelemetryTrend.jsx',
  'src/styles.css'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'C11 dashboard integration' -Message 'feat: integrate decision-first timeline dashboard' -Paths $c11CodePaths
$rawC11DashboardIntegrationCommit = git rev-parse HEAD
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'freeze C11 dashboard integration commit'
$c11DashboardIntegrationCommit = ($rawC11DashboardIntegrationCommit -join "`n").Trim()
```

- [ ] **Step 9: Independently review the exact C11 code SHA and D7 ancestry**

The reviewer starts from `$c11DashboardIntegrationCommit`, not a moving HEAD. Prove D7 ancestry, exact C11 range scope and the integration gates before review:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
if ($c11DashboardIntegrationCommit -notmatch '^[0-9a-f]{40}$') { throw 'invalid C11 code SHA' }
git merge-base --is-ancestor $d7PublicSeamCommit $c11DashboardIntegrationCommit
Assert-NativeExit $LASTEXITCODE 'D7 to reviewed C11 ancestry'
$expectedC11Scope = @(
  'src/App.jsx',
  'src/App.test.jsx',
  'src/components/operations/IntegrationHealth.jsx',
  'src/components/operations/OperationsDashboard.jsx',
  'src/components/operations/TelemetryTrend.jsx',
  'src/styles.css'
) | Sort-Object
$rawC11Scope = @(git diff --name-only $c11BaseCommit $c11DashboardIntegrationCommit)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read C11 reviewed scope'
$actualC11Scope = @($rawC11Scope | Sort-Object)
if (Compare-Object $expectedC11Scope $actualC11Scope) { throw 'C11 reviewed range has out-of-scope or missing paths' }
git diff --check $c11BaseCommit $c11DashboardIntegrationCommit
Assert-NativeExit $LASTEXITCODE 'C11 diff check'
& $python -m unittest scripts.tests.test_phase_c_evidence
Assert-NativeExit $LASTEXITCODE 'reviewed C11 Python helper tests'
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File scripts/tests/phase_c_plan_gates.tests.ps1
Assert-NativeExit $LASTEXITCODE 'reviewed C11 PowerShell helper tests'
npm.cmd run test:run -- --exclude "**/.pytest_cache/**"
Assert-NativeExit $LASTEXITCODE 'C11 full tests'
npm.cmd run build
Assert-NativeExit $LASTEXITCODE 'C11 production build'
```

The independent reviewer updates the same cumulative `docs/verification/phase-c-findings.json` in strict `finding-review-v1` shape with `plan="C"` and `reviewedSha=$c11DashboardIntegrationCommit`. It carries every C1 finding ID/lineage forward and reviews both the C11 range and the five-prop D7 seam integration. Preserve all finding IDs across re-reviews; fix/recommit only the declared C11 paths and update the exact SHA until the verdict has `0 Critical / 0 Important` and no unaccepted Minor. After every new code SHA, repeat D7 ancestry, the exact range/scope check, both helper suites, the complete frontend Vitest suite and the production build above. No executor may self-author the review verdict.

- [ ] **Step 10: Materialize the C11→D8 handoff in a separate evidence commit without closing C**

Validate the independent report, require the ledger still records only the C1 reviewed SHA with every C-owned criterion pending, then ingest the cumulative C11 review. Prove C remains `in_progress` with no criterion closed. Create `docs/verification/checkpoints/c11-dashboard-integration-handoff.json` with the same exact closed keys as the C1 handoff. Set `schemaVersion="phase-checkpoint-handoff-v1"`, `checkpoint="C11"`, `producerPlan="C"`, `consumerTask="D8"`, `baseCommit=$c11BaseCommit`, `reviewedCodeCommit=$c11DashboardIntegrationCommit`, `reviewReport="docs/verification/phase-c-findings.json"`, the exact report digest/verdict, and `environment` with exactly `D7_PUBLIC_SEAM_COMMIT` and `C11_DASHBOARD_INTEGRATION_COMMIT` bound to their reviewed SHAs.

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c11Review = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/phase-c-findings.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
Assert-FindingVerdictObject $c11Review.verdict 'C11 review verdict'
if ($c11Review.schemaVersion -cne 'finding-review-v1' -or $c11Review.plan -cne 'C' -or [string]$c11Review.reviewedSha -cne $c11DashboardIntegrationCommit -or $c11Review.verdict.critical -ne 0 -or $c11Review.verdict.important -ne 0) { throw 'C11 review is absent, stale or blocking' }
$c11UnacceptedMinor = @($c11Review.findings | Where-Object { $_.severity -eq 'minor' -and $_.status -notin @('fixed','accepted') })
if ($c11UnacceptedMinor.Count -ne 0) { throw 'C11 has an unaccepted Minor finding' }
$c1Handoff = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/checkpoints/c1-display-contract-handoff.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
if ($c1Handoff.schemaVersion -cne 'phase-checkpoint-handoff-v1' -or $c1Handoff.checkpoint -cne 'C1' -or [string]$c1Handoff.reviewedCodeCommit -notmatch '^[0-9a-f]{40}$') { throw 'committed C1 handoff is invalid' }
$ledgerBeforeC11Handoff = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/unified-twin-acceptance-v1.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
Assert-FindingVerdictObject $c1Handoff.verdict 'C1 handoff verdict before C11'
Assert-ReviewVerdictArray $ledgerBeforeC11Handoff.plans.C.reviewVerdict @($c1Handoff.verdict.critical,$c1Handoff.verdict.important,$c1Handoff.verdict.minor) 'pre-C11 ledger review verdict'
$prematureC11Criteria = @($ledgerBeforeC11Handoff.criteria | Where-Object { $_.ownerPlan -eq 'C' -and $_.status -ne 'pending' })
if ($ledgerBeforeC11Handoff.plans.C.status -ne 'in_progress' -or [string]$ledgerBeforeC11Handoff.plans.C.verifiedCodeCommit -cne [string]$c1Handoff.reviewedCodeCommit -or $prematureC11Criteria.Count -ne 0) { throw 'C11 must begin from the in-progress C1 ledger checkpoint' }
$python = (Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe" -ErrorAction Stop).Path
& $python scripts/verify_unified_acceptance.py ingest-review --ledger docs/verification/unified-twin-acceptance-v1.json --review-report docs/verification/phase-c-findings.json
Assert-NativeExit $LASTEXITCODE 'ingest C11 independent review'
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
Assert-NativeExit $LASTEXITCODE 'render ledger after C11 review'
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
Assert-NativeExit $LASTEXITCODE 'verify ledger after C11 review'
$ledgerAfterC11Review = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/unified-twin-acceptance-v1.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
Assert-ReviewVerdictArray $ledgerAfterC11Review.plans.C.reviewVerdict @($c11Review.verdict.critical,$c11Review.verdict.important,$c11Review.verdict.minor) 'C11 ledger review verdict'
$closedC11Criteria = @($ledgerAfterC11Review.criteria | Where-Object { $_.ownerPlan -eq 'C' -and $_.status -ne 'pending' })
$ac15AfterC11 = @($ledgerAfterC11Review.criteria | Where-Object criterionId -eq 'AC-15')
if ($ledgerAfterC11Review.plans.C.status -ne 'in_progress' -or [string]$ledgerAfterC11Review.plans.C.verifiedCodeCommit -cne $c11DashboardIntegrationCommit -or $closedC11Criteria.Count -ne 0 -or $ac15AfterC11.Count -ne 1 -or $ac15AfterC11[0].ownerPlan -ne 'E' -or $ac15AfterC11[0].status -ne 'pending') { throw 'C11 review ingestion closed or reassigned acceptance criteria' }
$c11ReviewSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath 'docs/verification/phase-c-findings.json' -ErrorAction Stop).Hash.ToLowerInvariant()
$c11Handoff = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/checkpoints/c11-dashboard-integration-handoff.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$expectedC11HandoffKeys = @('baseCommit','checkpoint','consumerTask','environment','producerPlan','reviewedCodeCommit','reviewReport','reviewReportSha256','schemaVersion','verdict') | Sort-Object
$actualC11HandoffKeys = @($c11Handoff.PSObject.Properties.Name) | Sort-Object
if (Compare-Object $expectedC11HandoffKeys $actualC11HandoffKeys) { throw 'C11 handoff shape mismatch' }
$c11EnvironmentKeys = @($c11Handoff.environment.PSObject.Properties.Name) | Sort-Object
$c11VerdictKeys = @($c11Handoff.verdict.PSObject.Properties.Name) | Sort-Object
Assert-FindingVerdictObject $c11Handoff.verdict 'C11 handoff verdict'
if (Compare-Object @('C11_DASHBOARD_INTEGRATION_COMMIT','D7_PUBLIC_SEAM_COMMIT') $c11EnvironmentKeys -CaseSensitive -SyncWindow 0) { throw 'C11 handoff environment shape mismatch' }
if (Compare-Object @('critical','important','minor') $c11VerdictKeys -CaseSensitive -SyncWindow 0) { throw 'C11 handoff verdict shape mismatch' }
if ($c11Handoff.schemaVersion -cne 'phase-checkpoint-handoff-v1' -or $c11Handoff.checkpoint -cne 'C11' -or $c11Handoff.producerPlan -cne 'C' -or $c11Handoff.consumerTask -cne 'D8' -or [string]$c11Handoff.baseCommit -cne $c11BaseCommit -or [string]$c11Handoff.reviewedCodeCommit -cne $c11DashboardIntegrationCommit -or [string]$c11Handoff.reviewReport -cne 'docs/verification/phase-c-findings.json' -or [string]$c11Handoff.environment.D7_PUBLIC_SEAM_COMMIT -cne $d7PublicSeamCommit -or [string]$c11Handoff.environment.C11_DASHBOARD_INTEGRATION_COMMIT -cne $c11DashboardIntegrationCommit -or [string]$c11Handoff.reviewReportSha256 -cne $c11ReviewSha256 -or $c11Handoff.verdict.critical -ne 0 -or $c11Handoff.verdict.important -ne 0 -or $c11Handoff.verdict.minor -ne $c11Review.verdict.minor) { throw 'C11 handoff binding mismatch' }
$c11EvidencePaths=@(
  'docs/verification/checkpoints/c11-dashboard-integration-handoff.json',
  'docs/verification/phase-c-findings.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'C11 handoff evidence' -Message 'docs: record reviewed C11 dashboard handoff' -Paths $c11EvidencePaths
$rawC11HandoffEvidenceCommit = git rev-parse HEAD
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'freeze C11 handoff evidence commit'
$c11HandoffEvidenceCommit = ($rawC11HandoffEvidenceCommit -join "`n").Trim()
if ($c11HandoffEvidenceCommit -notmatch '^[0-9a-f]{40}$') { throw 'invalid C11 evidence SHA' }
$rawC11EvidenceParent=git rev-parse "$c11HandoffEvidenceCommit^"
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read C11 evidence parent'
if ((($rawC11EvidenceParent -join "`n").Trim()) -cne $c11DashboardIntegrationCommit) { throw 'C11 evidence commit is not immediately after reviewed C11 code' }
$rawC11EvidenceScope=@(git diff-tree --no-commit-id --name-only -r $c11HandoffEvidenceCommit)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read C11 evidence diff'
if (Compare-Object $c11EvidencePaths @($rawC11EvidenceScope | Sort-Object)) { throw 'C11 evidence commit scope mismatch' }
$c11ProjectionJson=@(& $python scripts/phase_c_evidence.py checkpoint-projection --commit $c11HandoffEvidenceCommit --handoff-path 'docs/verification/checkpoints/c11-dashboard-integration-handoff.json')
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'reparse committed C11 evidence blobs'
$c11Projection=(($c11ProjectionJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
Assert-FindingVerdictObject $c11Projection.review.verdict 'committed C11 review verdict'
Assert-FindingVerdictObject $c11Projection.handoff.verdict 'committed C11 handoff verdict'
Assert-ReviewVerdictArray $c11Projection.planC.reviewVerdict @($c11Projection.review.verdict.critical,$c11Projection.review.verdict.important,$c11Projection.review.verdict.minor) 'committed C11 ledger review verdict'
if ($c11Projection.reviewHash -cne ('sha256:' + $c11ReviewSha256) -or $c11Projection.handoff.reviewReportSha256 -cne $c11ReviewSha256 -or $c11Projection.review.schemaVersion -cne 'finding-review-v1' -or $c11Projection.review.plan -cne 'C' -or [string]$c11Projection.review.reviewedSha -cne $c11DashboardIntegrationCommit -or $c11Projection.handoff.schemaVersion -cne 'phase-checkpoint-handoff-v1' -or $c11Projection.handoff.checkpoint -cne 'C11' -or [string]$c11Projection.handoff.baseCommit -cne $c11BaseCommit -or [string]$c11Projection.handoff.reviewedCodeCommit -cne $c11DashboardIntegrationCommit -or [string]$c11Projection.handoff.environment.D7_PUBLIC_SEAM_COMMIT -cne $d7PublicSeamCommit -or [string]$c11Projection.handoff.environment.C11_DASHBOARD_INTEGRATION_COMMIT -cne $c11DashboardIntegrationCommit -or $c11Projection.planC.status -cne 'in_progress' -or [string]$c11Projection.planC.verifiedCodeCommit -cne $c11DashboardIntegrationCommit) { throw 'committed C11 evidence blobs or bindings mismatch' }
git diff --exit-code $c11HandoffEvidenceCommit -- $c11EvidencePaths
Assert-NativeExit $LASTEXITCODE 'working C11 evidence equals committed evidence'
$env:D7_PUBLIC_SEAM_COMMIT = $d7PublicSeamCommit
$env:C11_DASHBOARD_INTEGRATION_COMMIT = $c11DashboardIntegrationCommit
$env:C11_HANDOFF_EVIDENCE_COMMIT = $c11HandoffEvidenceCommit
```

Do **not** call `update-criterion` here; the cumulative `ingest-review` is the sole checkpoint ledger mutation, and `render`/`verify` must immediately follow it. Record all three exact SHAs in the execution handoff. D8 may start only after reading the committed C11 handoff, reproducing its report blob/hash from `$c11HandoffEvidenceCommit` and proving `D7_PUBLIC_SEAM_COMMIT → C11_DASHBOARD_INTEGRATION_COMMIT → current HEAD`; C1 was already independently gated before D1. The final C review in Task 12 must carry forward every finding ID/status already stored by the shared ledger.

---

### Task 12: Author Browser Scenarios, Usability Contract and Phase-C Evidence

**Files:**
- Reuse unchanged: `playwright.config.js` (owned by plan E)
- Create: `tests/e2e/operational-scenarios.spec.js`
- Create: `tests/e2e/operational-accessibility.spec.js`
- Reuse unchanged: `tests/e2e/real-history-live.spec.js` (replaced by plan E)
- Reuse unchanged: `tests/e2e/deployed-real.spec.js` (extended by plan E)
- Create: `docs/usability/operational-triage-usability-v1.md`
- Create: `docs/usability/operational-triage-usability-v1-result-template.md`
- Reuse unchanged: `docs/verification/checkpoints/c1-display-contract-handoff.json` and `docs/verification/checkpoints/c11-dashboard-integration-handoff.json`
- Modify from independent review: `docs/verification/phase-c-findings.json` (preserve cumulative C1/C11 lineage)
- Create after the final reviewed code SHA: `docs/verification/phase-c-gate-manifest.json`
- Modify through verifier only: `docs/verification/unified-twin-acceptance-v1.json`
- Regenerate through verifier only: `docs/verification/unified-twin-acceptance-v1.md`
- Reuse unchanged: `scripts/verify_unified_acceptance.py`

**Interfaces:**
- Consumes: final C UI, shared contract fixtures, plan-D public fallback marker and the acceptance ledger bootstrapped by plan E Task 1.
- Produces: C-owned deterministic scenario definitions/locators, a manual human rubric and reviewed phase-C ledger evidence for C's non-browser criteria. Plan E owns executable Chromium configuration, real-backend/deployed composition, browser result capture and the final AC-15 ledger transition.

- [ ] **Step 1: Lock browser ownership before authoring tests**

Do not edit `playwright.config.js`. The plan-E integration task must remove `channel: "chrome"`, use only the Chromium bundled for the pinned `@playwright/test`/lockfile, set `1366×768`, configure all backend `webServer` arguments, propagate the current-worktree `PYTHONPATH`, require the absolute Python 3.12 executable and wait on `/api/v2/integration/health`. C-owned specs never call `chromium.launch`, never set `channel`/`executablePath` and never fall back to a system browser. If the bundled executable is missing, E stops for explicit authorization before `npx playwright install chromium`.

- [ ] **Step 2: Write seven deterministic scenario definitions**

Create explicit route-fixture tests for:

1. live normal/fresh: backend-owned time/trust, safe no-deviation phrase and next sample;
2. persistent candidate: `anchorPointId`, exact contracted `episodeStartedAt`, sensor, metric, direction, persistence, trust and safe review check;
3. upstream unavailable: “condição não avaliável” and acquisition check, without asset alert;
4. historical archive candidate: selected candidate marker, exact contracted `episodeStartedAt`, CSV/walk-forward provenance supplied by validated context/sample detail, evidence copy and no current escalation; the reduced overview point itself exposes no provenance or flags;
5. selected live timeline point: after selecting a `live_collection` marker, every panel says historical, facts remain `conditionSource=live_assessment` plus `conditionTemporalScope=historical`, and no current escalation appears; only “Voltar para agora” restores now;
6. gap: a successful null-anchor context replaces the previous historical bundle with null cards/context, broken line, missing-coverage copy and no carry-forward, while an unrelated context error preserves the prior bundle;
7. 3D group: selectable CAD group plus persistent non-localization statement.

Use route fixtures only in `operational-scenarios.spec.js`; product runtime remains real-data-only. Scope forbidden-copy checks to `[data-testid="decision-guidance"]` and next-check controls so the legitimate limitation “não é probabilidade de falha” is not a false positive. Candidate interactions call the backend context route with `pointId=<anchorPointId>`; candidate fixtures expose `anchorPointId` and no competing point-selector field. The persistent/historical panels must display the exact fixture `episodeStartedAt`; an absent value displays the explicit unavailable state and no test accepts an inferred timestamp. Include same-millisecond reduced-point/candidate route fixtures and a cycle terminal record to exercise the public millisecond contract. Assert every overview point has exactly `{pointId,eventAt,value}`, every reduction method is read from `series.aggregation.method`, and provenance/flags visible in detail originate only in the samples/context fixture.

- [ ] **Step 3: Add first-fold and atomic-render assertions**

```js
test("@ac15-first-fold keeps every required answer in the initial viewport", async ({ page }) => {
  await installPersistentCandidateNowRoutes(page);
  await page.goto("/");
  const assetMode = page.getByTestId("asset-mode");
  const trust = page.getByTestId("data-trust");
  const lastObservation = page.getByTestId("last-observation");
  const persistence = page.getByTestId("decision-persistence");
  const dominantEvidence = page.getByTestId("decision-dominant-evidence");
  const summary = page.getByTestId("decision-summary");
  const nextCheck = page.getByTestId("next-check").first();
  for (const locator of [
    assetMode, trust, lastObservation, persistence, dominantEvidence, summary, nextCheck,
  ]) {
    await expect(locator).toBeVisible();
    const box = await locator.boundingBox();
    expect(box).not.toBeNull();
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(768);
  }
  await expect(persistence).toHaveAttribute("data-evidence-state", "available");
  await expect(persistence).toContainText("3 leituras");
  await expect(dominantEvidence).toHaveAttribute("data-evidence-state", "available");
  await expect(dominantEvidence).toContainText(/S1.*vibração/i);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test("@ac15-first-fold keeps explicit evidence absence in the initial viewport", async ({ page }) => {
  await installNoEvidenceNowRoutes(page);
  await page.goto("/");
  for (const [locator, text] of [
    [page.getByTestId("decision-persistence"), "Persistência indisponível no contrato"],
    [page.getByTestId("decision-dominant-evidence"), "Evidência dominante não determinada"],
  ]) {
    await expect(locator).toBeVisible();
    await expect(locator).toHaveAttribute("data-evidence-state", "unavailable");
    await expect(locator).toHaveText(text);
    const box = await locator.boundingBox();
    expect(box).not.toBeNull();
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(768);
  }
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});
```

`installPersistentCandidateNowRoutes` and `installNoEvidenceNowRoutes` are local test helpers in the same spec. The first serves the exact contracted persistence plus dominant S1 vibration evidence used in the assertions; the second serves a contract-valid `now` response with empty `driverEvidenceIds/exportableEvidence`. Neither changes product runtime. Both named tests start with a clean page in now mode, viewport `1366×768` and details closed. Instrument every DOM commit during now→historical and historical→now: `[data-display-mode]`, decision heading, sensor timestamps, timeline cursor and twin `data-decision-as-of` must describe one mode/instant in every observation; a transient mixed frame fails. Repeat the observation for a live-source selected point and for a valid gap response; the former remains historical with `historical/live_assessment`, and the latter contains no prior point/channel/assessment text in any committed gap render.

- [ ] **Step 4: Add keyboard/accessibility tests**

Tab through mode, filters, candidate, cycle, table and 3D controls; activate with Enter and Space; assert visible focus, `aria-pressed`, heading order, labelled fields, table headers, status announcements, image fallback alt text and reduced-motion interaction. Verify candidate/source/state remain understandable after forcing grayscale in a test stylesheet.

- [ ] **Step 5: Exercise the single D-owned fallback contract**

Use the documented plan-D fixture/helper to make the viewport unavailable without injecting a component or `fallback` prop. Assert `[data-twin-fallback="true"]`, the immutable STEP-derived PNG, HTML group/sensor controls, selected historical timestamp and non-localization text remain visible. Add a source scan that C-owned App/Dashboard/E2E files contain neither `TwinFallback` nor a `fallback=` prop.

- [ ] **Step 6: Declare the real/deployed handoff to plan E**

Do not edit `real-history-live.spec.js`, `deployed-real.spec.js` or `playwright.config.js` here. Plan E replaces/extends them and runs these C-owned specs beside its real-history, deployed and interactive-twin specs using the bundled Chromium. Its real journey must assert `requestedRange/effectiveRange/availableRange`, `aggregationSummary`, source gap, active batch, candidate `anchorPointId`, paired context, atomic panels and no browser POST. Its deployed probe owns timeline/asset 503 isolation and cannot claim production approval from preview success. C authors the two `@ac15-first-fold` tests and their seven stable locators only; E executes both on the exact integrated `verifiedCodeCommit`, captures the browser evidence and is the sole phase allowed to move AC-15 from pending to passed.

- [ ] **Step 7: Create the exact manual usability rubric**

`operational-triage-usability-v1.md` records: clean session, now mode, 1366×768, details closed, declared fixture, definitions of primary interaction, required answers, 30/60-second limits, three-interaction limit, failure conditions and two participant profiles. The result template contains checkboxes for availability/trust, safe condition phrase, dominant sensor/metric when known, start/persistence, allowed next check, one limitation, elapsed seconds, primary interactions, observed ambiguity and pass/fail. It states that Playwright cannot complete this gate and leaves human criteria pending.

- [ ] **Step 8: Run C-owned deterministic gates and commit scenario definitions**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
npm.cmd run test:run -- --exclude "**/.pytest_cache/**"
$c12VitestExit=$LASTEXITCODE
Assert-NativeExit $c12VitestExit 'C12 deterministic Vitest gate'
npm.cmd run build
$c12BuildExit=$LASTEXITCODE
Assert-NativeExit $c12BuildExit 'C12 deterministic build gate'
npm.cmd run test:e2e -- tests/e2e/operational-scenarios.spec.js tests/e2e/operational-accessibility.spec.js --list
$c12PlaywrightListExit=$LASTEXITCODE
Assert-NativeExit $c12PlaywrightListExit 'C12 Playwright discovery gate'
$prohibited = rg -n 'channel\s*:|executablePath|chromium\.launch|TwinFallback|fallback=' tests/e2e/operational-scenarios.spec.js tests/e2e/operational-accessibility.spec.js src/App.jsx src/components/operations/OperationsDashboard.jsx 2>$null
$c12OwnershipExit=$LASTEXITCODE
Assert-NativeExit $c12OwnershipExit 'C12 prohibited ownership scan' @(1)
$c12Status = @(git status --short --branch)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read C12 intended status'
$c12Status
```

Expected: Vitest/build pass; Playwright discovers every C-owned test without launching the current system-channel project; the prohibited scan returns no matches; status contains only intended C files. Executing the real Chromium matrix remains explicitly pending for plan E after its config task.

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$c12CodePaths=@(
  'docs/usability/operational-triage-usability-v1-result-template.md',
  'docs/usability/operational-triage-usability-v1.md',
  'tests/e2e/operational-accessibility.spec.js',
  'tests/e2e/operational-scenarios.spec.js'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'C12 scenario definitions' -Message 'test: define operational timeline usability gates' -Paths $c12CodePaths
```

- [ ] **Step 9: Obtain independent review of the exact phase-C SHA**

Freeze `git rev-parse HEAD`, run the focused/full frontend gates again, and request an independent spec-compliance/code-quality review. Before sending that SHA to the reviewer, reauthenticate the frozen B handoff rather than trusting the earlier process state:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$rawVerifiedCodeCommit = git rev-parse HEAD
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'freeze final Phase C code SHA'
$verifiedCodeCommit = ($rawVerifiedCodeCommit -join "`n").Trim()
if ($verifiedCodeCommit -notmatch '^[0-9a-f]{40}$') { throw 'invalid final Phase C code SHA' }
$bToCPath='docs/verification/checkpoints/b-to-c-contract-handoff.json'
$bToCCommit=[string]$env:B_TO_C_CONTRACT_HANDOFF_COMMIT
$phaseBCodeCommit=[string]$env:PHASE_B_VERIFIED_CODE_COMMIT
$phaseBEvidenceCommit=[string]$env:PHASE_B_EVIDENCE_COMMIT
$bToC=Get-Content -Raw -Encoding utf8 -LiteralPath $bToCPath -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$expectedBToCKeys=@('contractSha256','evidencePaths','phaseBCodeCommit','phaseBEvidenceCommit','phaseBLedgerSha256','phaseBReviewSha256','reviewVerdict','schemaVersion') | Sort-Object
$expectedBEvidencePaths=@(
  'docs/verification/phase-b-findings.json',
  'docs/verification/phase-b-local-causal-manifest.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) | Sort-Object
$bContractPaths=@(
  'contracts/timeline/v1/fixtures/live-decision-facts-v1-cases.json',
  'contracts/timeline/v1/timeline-context.schema.json',
  'contracts/timeline/v1/timeline-decision-facts.schema.json',
  'contracts/timeline/v1/timeline-overview.schema.json',
  'contracts/timeline/v1/timeline-page.schema.json',
  'contracts/v2/digital-twin-snapshot.schema.json',
  'contracts/v2/fixtures/snapshot-last-known.valid.json',
  'contracts/v2/fixtures/snapshot-received-now.valid.json',
  'src/contracts/timelineV1.js',
  'src/contracts/twinV2.js'
) | Sort-Object
if ($bToCCommit -notmatch '^[0-9a-f]{40}$' -or $phaseBCodeCommit -notmatch '^[0-9a-f]{40}$' -or $phaseBEvidenceCommit -notmatch '^[0-9a-f]{40}$' -or (Compare-Object $expectedBToCKeys @($bToC.PSObject.Properties.Name | Sort-Object)) -or $bToC.schemaVersion -cne 'phase-b-to-c-contract-handoff-v1' -or [string]$bToC.phaseBCodeCommit -cne $phaseBCodeCommit -or [string]$bToC.phaseBEvidenceCommit -cne $phaseBEvidenceCommit -or $bToC.reviewVerdict -cne 'PASS' -or (Compare-Object $expectedBEvidencePaths @($bToC.evidencePaths | Sort-Object)) -or (Compare-Object $bContractPaths @($bToC.contractSha256.PSObject.Properties.Name | Sort-Object))) { throw 'final B-to-C shape or identity mismatch' }
foreach($edge in @(@($phaseBCodeCommit,$phaseBEvidenceCommit),@($phaseBEvidenceCommit,$bToCCommit),@($bToCCommit,$verifiedCodeCommit))) {
  git merge-base --is-ancestor $edge[0] $edge[1]
  Assert-NativeExit $LASTEXITCODE "final B-to-C ancestry $($edge[0]) -> $($edge[1])"
}
$authBlobRaw=git rev-parse "$bToCCommit`:$bToCPath"
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read final committed B-to-C handoff blob'
$authBlob=($authBlobRaw -join "`n").Trim()
$workingAuthBlobRaw=git hash-object -- $bToCPath
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'hash final working B-to-C handoff'
if ((($workingAuthBlobRaw -join "`n").Trim()) -cne $authBlob) { throw 'B-to-C handoff drifted before final C review' }
$committedBToCJson=@(git show "${bToCCommit}:$bToCPath")
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'parse final committed B-to-C handoff'
$committedBToC=(($committedBToCJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
if ((Compare-Object $expectedBToCKeys @($committedBToC.PSObject.Properties.Name | Sort-Object)) -or $committedBToC.schemaVersion -cne 'phase-b-to-c-contract-handoff-v1' -or [string]$committedBToC.phaseBCodeCommit -cne $phaseBCodeCommit -or [string]$committedBToC.phaseBEvidenceCommit -cne $phaseBEvidenceCommit -or $committedBToC.reviewVerdict -cne 'PASS' -or (Compare-Object $expectedBEvidencePaths @($committedBToC.evidencePaths | Sort-Object)) -or (Compare-Object $bContractPaths @($committedBToC.contractSha256.PSObject.Properties.Name | Sort-Object))) { throw 'final committed B-to-C handoff shape or binding mismatch' }
$rawBEvidencePaths=@(git diff --name-only "$phaseBCodeCommit..$phaseBEvidenceCommit")
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 're-read final Phase B evidence scope'
if ((Compare-Object $expectedBEvidencePaths @($rawBEvidencePaths | Sort-Object)) -or (Compare-Object $expectedBEvidencePaths @($bToC.evidencePaths | Sort-Object))) { throw 'Phase B evidence scope drifted before final C review' }
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe" -ErrorAction Stop).Path
$contractHashJson=@(& $python scripts/phase_c_evidence.py hash-paths --commit $phaseBCodeCommit --paths $bContractPaths)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'final raw git-show B contract hashes'
$actualContractHashes=(($contractHashJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
foreach($path in $bContractPaths) {
  $expected=[string]$bToC.contractSha256.PSObject.Properties[$path].Value
  $committed=[string]$actualContractHashes.PSObject.Properties[$path].Value
  $working='sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath $path -ErrorAction Stop).Hash.ToLowerInvariant()
  if ($expected -cne $committed -or $expected -cne $working) { throw "B contract drift before final C review: $path" }
}
$bEvidenceProjectionJson=@(& $python scripts/phase_c_evidence.py b-evidence-projection --commit $phaseBEvidenceCommit)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'final git-show and parse B review plus ledger'
$bEvidenceProjection=(($bEvidenceProjectionJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
Assert-FindingVerdictObject $bEvidenceProjection.review.verdict 'final committed Phase B finding review verdict'
$bVerdictCounts=@($bEvidenceProjection.review.verdict.critical,$bEvidenceProjection.review.verdict.important,$bEvidenceProjection.review.verdict.minor)
Assert-ReviewVerdictArray $bEvidenceProjection.planB.reviewVerdict $bVerdictCounts 'final committed Phase B ledger review verdict'
if ($bEvidenceProjection.reviewHash -cne $bToC.phaseBReviewSha256 -or $bEvidenceProjection.ledgerHash -cne $bToC.phaseBLedgerSha256 -or $bEvidenceProjection.review.schemaVersion -cne 'finding-review-v1' -or $bEvidenceProjection.review.plan -cne 'B' -or [string]$bEvidenceProjection.review.reviewedSha -cne $phaseBCodeCommit -or $bEvidenceProjection.review.verdict.critical -ne 0 -or $bEvidenceProjection.review.verdict.important -ne 0 -or $bEvidenceProjection.planB.status -cne 'passed' -or [string]$bEvidenceProjection.planB.verifiedCodeCommit -cne $phaseBCodeCommit -or $bEvidenceProjection.criteria.'AC-13'.status -cne 'passed' -or $bEvidenceProjection.criteria.'AC-14'.status -cne 'passed') { throw 'final committed Phase B attestation is not closed' }
if (@($bEvidenceProjection.review.findings | Where-Object { $_.severity -eq 'minor' -and $_.status -notin @('fixed','accepted') }).Count -ne 0) { throw 'final committed Phase B review has an unaccepted Minor' }
$currentBReviewHash='sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath 'docs/verification/phase-b-findings.json' -ErrorAction Stop).Hash.ToLowerInvariant()
if ($currentBReviewHash -cne [string]$bToC.phaseBReviewSha256) { throw 'working Phase B review drifted before final C review' }
$currentLedgerBeforeFinalReview=Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/unified-twin-acceptance-v1.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
Assert-ReviewVerdictArray $currentLedgerBeforeFinalReview.plans.B.reviewVerdict $bVerdictCounts 'final current Phase B ledger review verdict'
if ($currentLedgerBeforeFinalReview.plans.B.status -cne 'passed' -or [string]$currentLedgerBeforeFinalReview.plans.B.verifiedCodeCommit -cne $phaseBCodeCommit -or @($currentLedgerBeforeFinalReview.criteria | Where-Object criterionId -eq 'AC-13').Count -ne 1 -or @($currentLedgerBeforeFinalReview.criteria | Where-Object criterionId -eq 'AC-13')[0].status -cne 'passed' -or @($currentLedgerBeforeFinalReview.criteria | Where-Object criterionId -eq 'AC-14').Count -ne 1 -or @($currentLedgerBeforeFinalReview.criteria | Where-Object criterionId -eq 'AC-14')[0].status -cne 'passed') { throw 'current cumulative ledger regressed B before final C review' }
& $python -m unittest scripts.tests.test_phase_c_evidence
Assert-NativeExit $LASTEXITCODE 'final Phase C Python helper tests'
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File scripts/tests/phase_c_plan_gates.tests.ps1
Assert-NativeExit $LASTEXITCODE 'final Phase C PowerShell helper tests'
npm.cmd run test:run -- --exclude "**/.pytest_cache/**"
$finalVitestExit=$LASTEXITCODE
Assert-NativeExit $finalVitestExit 'final Phase C full Vitest gate'
npm.cmd run build
$finalBuildExit=$LASTEXITCODE
Assert-NativeExit $finalBuildExit 'final Phase C production build gate'
npm.cmd run test:e2e -- tests/e2e/operational-scenarios.spec.js tests/e2e/operational-accessibility.spec.js --list
$finalPlaywrightListExit=$LASTEXITCODE
Assert-NativeExit $finalPlaywrightListExit 'final Phase C Playwright discovery gate'
$finalProhibited=rg -n 'channel\s*:|executablePath|chromium\.launch|TwinFallback|fallback=' tests/e2e/operational-scenarios.spec.js tests/e2e/operational-accessibility.spec.js src/App.jsx src/components/operations/OperationsDashboard.jsx 2>$null
$finalOwnershipExit=$LASTEXITCODE
Assert-NativeExit $finalOwnershipExit 'final Phase C prohibited ownership scan' @(1)
$phaseCGateManifestPath='docs/verification/phase-c-gate-manifest.json'
& $python scripts/phase_c_evidence.py write-gate-manifest --output $phaseCGateManifestPath --verified-code-commit $verifiedCodeCommit --phase-b-code-commit $phaseBCodeCommit --phase-b-evidence-commit $phaseBEvidenceCommit --b-to-c-handoff-commit $bToCCommit --vitest-exit $finalVitestExit --build-exit $finalBuildExit --playwright-list-exit $finalPlaywrightListExit --ownership-scan-exit $finalOwnershipExit
Assert-NativeExit $LASTEXITCODE 'write final Phase C gate manifest'
& $python scripts/phase_c_evidence.py validate-gate-manifest --path $phaseCGateManifestPath --verified-code-commit $verifiedCodeCommit --phase-b-code-commit $phaseBCodeCommit --phase-b-evidence-commit $phaseBEvidenceCommit --b-to-c-handoff-commit $bToCCommit
Assert-NativeExit $LASTEXITCODE 'validate working final Phase C gate manifest'
```

Any failed identity, ancestry, evidence-scope, raw-byte hash, PASS report or ledger check blocks final review and requires a new reviewed B handoff followed by restarting C3. Run the focused/full frontend gates with immediate `Assert-NativeExit` checks. The independent reviewer writes `docs/verification/phase-c-findings.json` in E's common closed `finding-review-v1` schema, with the exact reviewed SHA:

```json
{
  "schemaVersion": "finding-review-v1",
  "plan": "C",
  "reviewedSha": "0000000000000000000000000000000000000000",
  "verdict": { "critical": 0, "important": 0, "minor": 0 },
  "findings": []
}
```

When findings exist, each item contains exactly `findingId`, `severity`, `status`, `title`, `evidenceRefs` and nullable `resolvedSha`; status `accepted` is legal only for a Minor finding explicitly accepted by the user. Before reviewing new C work, the reviewer starts from the already-ingested cumulative C11 version of this same report and carries every C1/C11 `findingId`, severity, title and latest legal disposition forward; no checkpoint finding may disappear. Its evidence refs retain the applicable checkpoint handoff/reviewed code SHA. The reviewer replaces `reviewedSha` with the frozen final C code SHA and preserves cumulative IDs/status across re-reviews. After every finding fix/new code SHA, rerun the entire Step 9 B→C authentication, both helper suites, full Vitest, build, Playwright discovery and fail-closed ownership scan against that new `$verifiedCodeCommit`, then atomically replace and revalidate the manifest; the report may bind only the last SHA that passed them. Do not self-author a `pass`; continue fixing/re-reviewing until the report has zero open Critical/Important and no unaccepted Minor. Browser/preview/human criteria owned by E remain pending rather than being waived.

- [ ] **Step 10: Update only the non-browser phase-C ledger criteria, regenerate Markdown and commit evidence**

C never mutates AC-15. `--list`, Vitest, build, code review and screenshots prove only that C authored the tests/locators; they are not AC-15 evidence. Leave that criterion pending for E's final integrated bundled-Chromium run on E's exact `verifiedCodeCommit`.

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$phaseCGates=(Resolve-Path 'scripts/phase_c_plan_gates.ps1' -ErrorAction Stop).Path
. $phaseCGates
Assert-PhaseCCheckedSession
$phaseCReview = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/phase-c-findings.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
Assert-FindingVerdictObject $phaseCReview.verdict 'final Phase C review verdict'
$verifiedCodeCommit = [string]$phaseCReview.reviewedSha
if ($verifiedCodeCommit -notmatch '^[0-9a-f]{40}$') { throw 'final Phase C review has invalid code SHA' }
$phaseBCodeCommit=[string]$env:PHASE_B_VERIFIED_CODE_COMMIT
$phaseBEvidenceCommit=[string]$env:PHASE_B_EVIDENCE_COMMIT
$bToCCommit=[string]$env:B_TO_C_CONTRACT_HANDOFF_COMMIT
$phaseCGateManifestPath='docs/verification/phase-c-gate-manifest.json'
$python = (Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe" -ErrorAction Stop).Path
& $python scripts/phase_c_evidence.py validate-gate-manifest --path $phaseCGateManifestPath --verified-code-commit $verifiedCodeCommit --phase-b-code-commit $phaseBCodeCommit --phase-b-evidence-commit $phaseBEvidenceCommit --b-to-c-handoff-commit $bToCCommit
Assert-NativeExit $LASTEXITCODE 'revalidate final Phase C gate manifest before ledger mutation'
git merge-base --is-ancestor $verifiedCodeCommit HEAD
Assert-NativeExit $LASTEXITCODE 'final reviewed C code ancestry'
$ledgerBeforeFinalCReview = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/unified-twin-acceptance-v1.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$checkpointFindingIds = @($ledgerBeforeFinalCReview.plans.C.findingIds | Sort-Object -Unique)
$finalFindingIds = @($phaseCReview.findings.findingId | Sort-Object -Unique)
$missingCheckpointFindings = @(Compare-Object $checkpointFindingIds $finalFindingIds | Where-Object SideIndicator -eq '<=')
if ($missingCheckpointFindings.Count -ne 0) { throw 'final C review erased a C1/C11 finding ID' }
$c1Handoff = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/checkpoints/c1-display-contract-handoff.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$c11Handoff = Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/checkpoints/c11-dashboard-integration-handoff.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
Assert-FindingVerdictObject $c11Handoff.verdict 'C11 handoff verdict before final C evidence'
Assert-ReviewVerdictArray $ledgerBeforeFinalCReview.plans.C.reviewVerdict @($c11Handoff.verdict.critical,$c11Handoff.verdict.important,$c11Handoff.verdict.minor) 'pre-final Phase C ledger review verdict'
git merge-base --is-ancestor $c1Handoff.reviewedCodeCommit $c11Handoff.reviewedCodeCommit
Assert-NativeExit $LASTEXITCODE 'C1 to C11 reviewed-code ancestry'
git merge-base --is-ancestor $c11Handoff.reviewedCodeCommit $verifiedCodeCommit
Assert-NativeExit $LASTEXITCODE 'C11 to final reviewed-code ancestry'
git merge-base --is-ancestor $env:B_TO_C_CONTRACT_HANDOFF_COMMIT $verifiedCodeCommit
Assert-NativeExit $LASTEXITCODE 'authenticated B-to-C handoff to final reviewed C code ancestry'
if ($ledgerBeforeFinalCReview.plans.C.status -ne 'in_progress' -or [string]$ledgerBeforeFinalCReview.plans.C.verifiedCodeCommit -cne [string]$c11Handoff.reviewedCodeCommit) { throw 'final C review did not start from the ingested C11 checkpoint' }
$ac15BeforeFinal=@($ledgerBeforeFinalCReview.criteria | Where-Object criterionId -eq 'AC-15')
if ($ac15BeforeFinal.Count -ne 1 -or $ac15BeforeFinal[0].ownerPlan -cne 'E' -or $ac15BeforeFinal[0].status -cne 'pending') { throw 'AC-15 was not E-owned/pending before final C evidence' }
$ac15BeforeFinalJson=($ac15BeforeFinal[0] | ConvertTo-Json -Compress -Depth 20)
$env:PYTHONPATH="$PWD\services\twinops\src;$PWD"
if ($phaseCReview.schemaVersion -cne 'finding-review-v1' -or $phaseCReview.plan -cne 'C' -or $phaseCReview.verdict.critical -ne 0 -or $phaseCReview.verdict.important -ne 0 -or @($phaseCReview.findings | Where-Object { $_.severity -eq 'minor' -and $_.status -notin @('fixed','accepted') }).Count -ne 0) { throw 'phase C review is not a clean closed report' }
& $python scripts/verify_unified_acceptance.py ingest-review --ledger docs/verification/unified-twin-acceptance-v1.json --review-report docs/verification/phase-c-findings.json
Assert-NativeExit $LASTEXITCODE 'ingest final Phase C review'
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
Assert-NativeExit $LASTEXITCODE 'render ledger after final C review ingestion'
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
Assert-NativeExit $LASTEXITCODE 'verify ledger after final C review ingestion'
$phaseCCriteria=@('AC-01','AC-02','AC-03','AC-04','AC-05','AC-07','AC-11','AC-16','AC-17','AC-19','AC-21','AC-22','AC-25','AC-26','AC-27')
foreach($criterion in $phaseCCriteria) {
  & $python scripts/verify_unified_acceptance.py update-criterion --ledger docs/verification/unified-twin-acceptance-v1.json --criterion $criterion --status passed --evidence-kind automated --evidence-ref $phaseCGateManifestPath --verified-code-commit $verifiedCodeCommit
  Assert-NativeExit $LASTEXITCODE "update final C criterion $criterion"
  & $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
  Assert-NativeExit $LASTEXITCODE "render ledger after $criterion"
  & $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
  Assert-NativeExit $LASTEXITCODE "verify ledger after $criterion"
}
$ledgerBeforeEvidenceCommit=Get-Content -Raw -Encoding utf8 -LiteralPath 'docs/verification/unified-twin-acceptance-v1.json' -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$ac15BeforeEvidence=@($ledgerBeforeEvidenceCommit.criteria | Where-Object criterionId -eq 'AC-15')
if ($ac15BeforeEvidence.Count -ne 1) { throw 'AC-15 missing or duplicated before final evidence commit' }
$ac15BeforeEvidenceJson=($ac15BeforeEvidence[0] | ConvertTo-Json -Compress -Depth 20)
if ($ac15BeforeEvidenceJson -cne $ac15BeforeFinalJson -or $ac15BeforeEvidence[0].ownerPlan -cne 'E' -or $ac15BeforeEvidence[0].status -cne 'pending') { throw 'C changed E-owned AC-15' }
Assert-ReviewVerdictArray $ledgerBeforeEvidenceCommit.plans.C.reviewVerdict @($phaseCReview.verdict.critical,$phaseCReview.verdict.important,$phaseCReview.verdict.minor) 'final Phase C ledger review verdict'
if ($ledgerBeforeEvidenceCommit.plans.C.status -cne 'passed' -or [string]$ledgerBeforeEvidenceCommit.plans.C.verifiedCodeCommit -cne $verifiedCodeCommit) { throw 'final C ledger plan record is not closed on reviewed code' }
foreach($criterion in $phaseCCriteria) {
  $entry=@($ledgerBeforeEvidenceCommit.criteria | Where-Object criterionId -eq $criterion)
  $entryEvidenceRefs=@($entry[0].evidenceRefs)
  if ($entry.Count -ne 1 -or $entry[0].status -cne 'passed' -or [string]$entry[0].verifiedCodeCommit -cne $verifiedCodeCommit -or $entryEvidenceRefs.Count -ne 1 -or [string]$entryEvidenceRefs[0] -cne $phaseCGateManifestPath) { throw "final C criterion is not bound to reviewed code and gate manifest: $criterion" }
}
git diff --check
Assert-NativeExit $LASTEXITCODE 'final Phase C evidence diff check'
$phaseCEvidencePaths=@(
  'docs/verification/phase-c-findings.json',
  'docs/verification/phase-c-gate-manifest.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) | Sort-Object
Invoke-PhaseCExactCommit -Label 'final Phase C evidence' -Message 'docs: record phase C acceptance evidence' -Paths $phaseCEvidencePaths
$rawPhaseCEvidenceCommit=git rev-parse HEAD
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'freeze final Phase C evidence commit'
$phaseCEvidenceCommit=($rawPhaseCEvidenceCommit -join "`n").Trim()
if ($phaseCEvidenceCommit -notmatch '^[0-9a-f]{40}$') { throw 'invalid final Phase C evidence SHA' }
$rawPhaseCEvidenceParent=git rev-parse "$phaseCEvidenceCommit^"
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read final Phase C evidence parent'
if ((($rawPhaseCEvidenceParent -join "`n").Trim()) -cne $verifiedCodeCommit) { throw 'final C evidence commit is not immediately after reviewed code' }
git merge-base --is-ancestor $verifiedCodeCommit $phaseCEvidenceCommit
Assert-NativeExit $LASTEXITCODE 'reviewed C code to evidence ancestry'
$rawPhaseCEvidenceScope=@(git diff-tree --no-commit-id --name-only -r $phaseCEvidenceCommit)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read final Phase C evidence diff'
$expectedPhaseCEvidenceScope=$phaseCEvidencePaths
if (Compare-Object $expectedPhaseCEvidenceScope @($rawPhaseCEvidenceScope | Sort-Object)) { throw 'final Phase C evidence commit scope mismatch' }
$finalLedgerProjectionJson=@(& $python scripts/phase_c_evidence.py final-ledger-projection --commit $phaseCEvidenceCommit --criteria $phaseCCriteria)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'reparse committed final Phase C ledger'
$finalLedgerProjection=(($finalLedgerProjectionJson -join "`n") | ConvertFrom-Json -ErrorAction Stop)
Assert-FindingVerdictObject $finalLedgerProjection.review.verdict 'committed final C review verdict'
Assert-ReviewVerdictArray $finalLedgerProjection.planC.reviewVerdict @($finalLedgerProjection.review.verdict.critical,$finalLedgerProjection.review.verdict.important,$finalLedgerProjection.review.verdict.minor) 'committed final C ledger review verdict'
if ($finalLedgerProjection.planC.status -cne 'passed' -or [string]$finalLedgerProjection.planC.verifiedCodeCommit -cne $verifiedCodeCommit) { throw 'committed final C plan record mismatch' }
if ($finalLedgerProjection.review.schemaVersion -cne 'finding-review-v1' -or $finalLedgerProjection.review.plan -cne 'C' -or [string]$finalLedgerProjection.review.reviewedSha -cne $verifiedCodeCommit -or $finalLedgerProjection.review.verdict.critical -ne 0 -or $finalLedgerProjection.review.verdict.important -ne 0 -or @($finalLedgerProjection.review.findings | Where-Object { $_.severity -eq 'minor' -and $_.status -notin @('fixed','accepted') }).Count -ne 0) { throw 'committed final C review mismatch' }
foreach($criterion in $phaseCCriteria) {
  $entry=@($finalLedgerProjection.criteria | Where-Object criterionId -eq $criterion)
  $entryEvidenceRefs=@($entry[0].evidenceRefs)
  if ($entry.Count -ne 1 -or $entry[0].status -cne 'passed' -or [string]$entry[0].verifiedCodeCommit -cne $verifiedCodeCommit -or $entryEvidenceRefs.Count -ne 1 -or [string]$entryEvidenceRefs[0] -cne $phaseCGateManifestPath) { throw "committed C criterion/manifest binding mismatch: $criterion" }
}
$committedAc15=@($finalLedgerProjection.criteria | Where-Object criterionId -eq 'AC-15')
if ($committedAc15.Count -ne 1 -or $committedAc15[0].ownerPlan -cne 'E' -or $committedAc15[0].status -cne 'pending') { throw 'committed evidence changed E-owned AC-15' }
& $python scripts/phase_c_evidence.py validate-gate-manifest --path $phaseCGateManifestPath --commit $phaseCEvidenceCommit --verified-code-commit $verifiedCodeCommit --phase-b-code-commit $phaseBCodeCommit --phase-b-evidence-commit $phaseBEvidenceCommit --b-to-c-handoff-commit $bToCCommit
Assert-NativeExit $LASTEXITCODE 'validate committed Phase C gate manifest from raw git-show bytes'
if ($finalLedgerProjection.gateManifest.schemaVersion -cne 'phase-c-gate-manifest-v1' -or $finalLedgerProjection.gateManifest.plan -cne 'C' -or [string]$finalLedgerProjection.gateManifest.verifiedCodeCommit -cne $verifiedCodeCommit -or $finalLedgerProjection.gateManifestHash -notmatch '^sha256:[0-9a-f]{64}$' -or $finalLedgerProjection.reviewHash -notmatch '^sha256:[0-9a-f]{64}$' -or $finalLedgerProjection.ledgerHash -notmatch '^sha256:[0-9a-f]{64}$') { throw 'committed final C raw evidence digest or manifest mismatch' }
git diff --exit-code $phaseCEvidenceCommit -- $phaseCEvidencePaths
Assert-NativeExit $LASTEXITCODE 'working final evidence equals committed evidence'
$finalStatus=@(git status --porcelain=v1 --untracked-files=all)
$nativeExit=$LASTEXITCODE
Assert-NativeExit $nativeExit 'read final Phase C status'
if ($finalStatus.Count -ne 0) { throw 'final Phase C tree is not clean after evidence commit' }
$env:PHASE_C_EVIDENCE_COMMIT=$phaseCEvidenceCommit
```

Expected: `ingest-review` accepts only the shared `finding-review-v1` report, writes plan C's `verifiedCodeCommit` as `$verifiedCodeCommit`, preserves all earlier findings, and each of the 15 frozen non-browser C-owned criteria closes only through `update-criterion` on that same SHA with `docs/verification/phase-c-gate-manifest.json` as its evidence reference. AC-15 remains byte-for-byte pending in the ledger. Plan E later checks out/freezes its exact integrated `verifiedCodeCommit`, executes both C-authored `@ac15-first-fold` tests in bundled Chromium, verifies all seven required locators (including contracted persistence/evidence and both explicit unavailable states) at or above pixel 768, captures the result, and only then updates AC-15 with that same exact commit. The verifier leaves all other remote/human/E-owned criteria pending. Every ledger mutation is followed immediately by `render` and `verify`. The generated Markdown exactly matches the JSON SSoT; no hand edit is permitted. The later evidence commit contains exactly the cumulative review, durable gate manifest, ledger JSON and generated Markdown; it is captured as exact `$phaseCEvidenceCommit`, reparsed and validated from raw `git show` blobs, proven immediately after `$verifiedCodeCommit`, and recorded separately in the execution handoff. Neither evidence commit is self-referenced inside the JSON.

---

## Final Review Checklist

- [ ] Every card and panel reads from the same committed `{ displayContext, decisionSupport }` bundle, and an all-render observation proves their canonical hashes always match.
- [ ] Background refresh, async hashing and stale request races cannot replace or partially mix the historical bundle; return-to-now is equally atomic.
- [ ] Timeline consumes reduced overview points as exactly `{pointId,eventAt,value}`, preserves contracted `points: []` series without an invented point/marker, reads reduction only from `series.aggregation.method`, retains stable real IDs for plotted markers, and uses backend at-or-before selection for cursor context.
- [ ] Overview consumes `requestedRange`, `effectiveRange`, `availableRange` and `aggregationSummary` literally, remains calendar-proportional and breaks the plotted line at every source/gap.
- [ ] Overview preserves `gapType` without a `type` alias; point-level provenance, timestamp quality and flags appear only from validated samples/context detail, never from a reduced overview point.
- [ ] Candidate navigation uses only `anchorPointId`; `activeHistoricalBatchId` remains global context while candidate source is discriminated by `sourceKind + batchId`; the scope builder partitions sensor/fold/model groups before every queue, supports now-live and historical inspection of live points with an active archive, rejects crossed range/cycle scope and ignores raw scores.
- [ ] Cycle UI consumes only `previousOperatingCycleId` and `gapBeforeSeconds`, without aliases or derived gap counts.
- [ ] Decision matrix produces exactly one row or fails closed.
- [ ] `displayContextHash` is SHA-256 of the complete canonical validated `DisplayContextV1`, `decisionId` binds that same canonical context plus schema/ruleset hash, the V1 exclusion set is exactly empty, and matching-only projections never become hash preimages.
- [ ] The display contract enforces the exact full Forzy asset object; historical projection requires context/live-asset equality. Live and historical adapters require backend-owned `decisionFacts.schemaVersion="1.0"` and never recompute policy, expectation, freshness or trust.
- [ ] A retrospectively selected `live_collection` point commits only as `viewMode="historical"`, preserving backend `historical/live_assessment`; only explicit return-to-now restores `now`.
- [ ] A valid null-anchor `historical_gap` replaces the full prior bundle with historical freshness and no carry-forward, while unrelated/stale errors preserve the previous bundle.
- [ ] Every public timestamp passes the canonical UTC-millisecond parser; event ordering is numeric, cycle `endAt` becomes `to=endAt+1ms`, and same-millisecond/terminal fixtures remain addressable.
- [ ] “Início do episódio” is the exact agreed contracted candidate/assessment/decision-evidence timestamp or an explicit unavailable state, never an inference from cadence/persistence/chart bounds.
- [ ] Summary/check/limitation copy renders directly from the validated canonical ruleset bundle, with no duplicate local phrase map.
- [ ] Free recommendation and arbitrary upstream text are absent from UI/export.
- [ ] Only the strict live trusted alert includes engineering escalation.
- [ ] C authors stable first-fold tests/locators; E alone executes and closes AC-15 on its exact integrated `verifiedCodeCommit` at 1366×768 with visible mode, trust, last observation, persistence, dominant evidence, summary and next check; persistence/evidence absence is explicit in the same viewport, and 3D remains below investigation.
- [ ] Keyboard, focus, non-color distinctions, visible table and live announcements pass.
- [ ] 3D selection remains navigational, C passes only the five-prop seam, and D's single `data-twin-fallback` path preserves context without localizing S1/S2 or mechanical cause.
- [ ] C does not edit Playwright config/real/deployed specs; plan E uses pinned bundled Chromium and keeps real integration/deployed smoke read-only.
- [ ] The independent phase-C report and generated shared ledger entry point to the exact `verifiedCodeCommit`, with zero open Critical/Important and no Minor accepted without explicit user approval; the later evidence commit is recorded only in the handoff.
- [ ] Human usability remains a separate recorded gate with both required profiles.

## Execution Handoff

Plan complete at `docs/superpowers/plans/2026-08-22-decision-oriented-timeline-ui-plan.md`.

1. **Subagent-Driven (recommended):** use `superpowers:subagent-driven-development`, one fresh worker per task, with spec-compliance and code-quality review after each task.
2. **Inline Execution:** use `superpowers:executing-plans`, execute in ordered batches, but stop at the mandatory cross-plan gates C1→D1 and D7→C11→D8 in addition to the local checkpoints after Tasks 4, 7, 10 and 12.
3. **C1 handoff:** publish exact `C1_DISPLAY_CONTRACT_COMMIT` and `C1_HANDOFF_EVIDENCE_COMMIT`; D1 verifies the report hash/verdict, ancestry and clean integration before consuming the C1 fixtures/validator.
4. **C11 handoff:** receive exact `D7_PUBLIC_SEAM_COMMIT`, then publish exact reviewed `C11_DASHBOARD_INTEGRATION_COMMIT` and `C11_HANDOFF_EVIDENCE_COMMIT`; D8 verifies `D7 → C11 → HEAD` before proceeding.
5. **B→C contract identity:** retain exact `PHASE_B_VERIFIED_CODE_COMMIT`, `PHASE_B_EVIDENCE_COMMIT` and `B_TO_C_CONTRACT_HANDOFF_COMMIT`; C3, C5 and final C review each reauthenticate ancestry, scope, PASS ledger/report and every recorded raw-byte contract hash.
6. **Final C identity:** publish the independently reviewed `$verifiedCodeCommit` and distinct `$phaseCEvidenceCommit`/`PHASE_C_EVIDENCE_COMMIT`; the latter must be the immediate evidence-only child whose committed ledger is reparsed and binds all 15 C criteria to the former.
7. **Ledger state:** C1 and C11 may update only the cumulative plan-C review record through `ingest-review`, leaving C `in_progress` and every criterion pending. Task 12 alone updates the 15 C-owned non-browser criteria; AC-15 remains E-owned and pending until E executes it on its exact integrated `verifiedCodeCommit`.
