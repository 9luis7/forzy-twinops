# Interactive Engineering Twin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o GLB real do conjunto motor-bomba em um twin de engenharia investigável, sincronizado com o mesmo `displayContext.viewMode` `now|historical` dos demais painéis, com seleção exata dos quatro grupos CAD, inspetor dimensional do VIM32 e fallback que preserva dados e controles HTML.

**Architecture:** O contrato visual fica separado do manifesto técnico imutável: uma projeção de apresentação validada associa presets ilustrativos aos quatro grupos já comprovados, enquanto a cena resolve cliques apenas por ancestral com nome exato do manifesto. O provider da experiência histórica continua dono de `displayContext`, `selectedGroup` e `selectedSensor`; o 3D apenas apresenta esse estado, mantém o GLB lazy-loaded e conserva controles/inspeção em HTML quando WebGL ou assets falharem.

**Tech Stack:** React 18.3, Vite 5.4, Three.js 0.169, React Three Fiber 8.17, Drei 9.117, Vitest 2.1, Testing Library 16 e Playwright 1.47.

**Spec:** `docs/superpowers/specs/2026-08-22-unified-history-interactive-twin-design.md`

## Global Constraints

- Base de planejamento exata: `4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e` na branch `luis/real-twinops-integration`.
- O modo público é exatamente `viewMode: "now" | "historical"`; não reutilizar `replay`, `live` ou `capabilities.replayControls` como estado de navegação.
- `displayContext` é a única fonte de identidade do ativo, instante de decisão, condição, dimensões de coleta/dados, canais, avaliação, âncora, proveniência e ênfase de sensor apresentados pelo twin. O seam público não recebe snapshot live.
- O 3D não calcula score, threshold, causalidade, tendência, carry-forward, nearest-neighbor ou diagnóstico. Combinação ausente ou incoerente falha fechada em estado neutro/insuficiente.
- Os quatro grupos selecionáveis são somente `motor`, `pump`, `coupling` e `base`; o resolvedor aceita apenas ancestral cujo `name` seja igualdade exata com um item de `manifest.nodes`.
- Seleção CAD responde “qual volume estou inspecionando”; ela nunca atribui S1/S2, alerta, falha ou causa ao grupo.
- `public/models/conjunto-motor-bomba.glb`, `public/models/conjunto-motor-bomba.manifest.json` e `artifacts/twin3d/conversion-report.json` permanecem byte a byte imutáveis neste plano. A Fase D possui explicitamente a regeneração e o versionamento de `public/models/conjunto-motor-bomba-preview.png` a partir do GLB imutável, em renderer local determinístico.
- Hashes congelados: GLB `fc313dd651c904115767d67992285b6213a4e7bc1c3d0ab8ad7f2742d7629296` e STEP-fonte no manifesto `7af8e745df756787282cfec2f5b6fe6a73650ba0937c542181f9d614324386f3`. O hash atual da PNG `cad9599ceaa6f7bd6ca9699232a8eb88ef7975668e0dc8d91a15a0a6708ee221` é baseline de entrada, não hash esperado de saída; o novo hash é calculado e registrado pelo renderer, nunca antecipado no plano.
- O inventário técnico continua com 17 nós: motor 7, pump 3, coupling 5 e base 2. Nenhum node pode ser removido, renomeado, mesclado ou associado por fuzzy match.
- Materiais PBR são presets de legibilidade com `presentationConfidence: "illustrative"`; não afirmar cor real, pintura, aço, ferro fundido, liga, acabamento ou tolerância de fabricação.
- O status do ativo aparece como halo/contorno global e texto. Sem `componentTag` validado, nenhuma parte recebe cor causal de `watch` ou `alert`.
- S1/S2 permanecem fora da geometria do conjunto. O inspetor do VIM32 é separado e sempre exibe que a posição física não foi validada.
- A representação do VIM32 usa apenas comprimento `72.5 mm`, diâmetro `23.8 mm`, massa aproximada `100 g`, conector `M12`, IO-Link 1.1 e faixas documentadas. Passo de rosca, contatos, logotipo, acabamento e dimensões não cotadas não são desenhados.
- Nenhum asset, textura, HDR, fonte ou recurso visual depende de CDN ou URL externa. O plano não lê nem copia STEP, DWG ou PDFs fora do Git.
- Three.js permanece em chunk lazy. Atualizar `displayContext`, `selectedGroup` ou `selectedSensor` não pode refazer fetch do manifesto/GLB, remontar o canvas ou resetar a câmera sem comando explícito.
- O renderer usa `frameloop="demand"`, DPR limitado a `[1, 1.5]`, sombras com orçamento fixo e descarte explícito de materiais/geometrias auxiliares.
- `prefers-reduced-motion` remove pulsos e transições de câmera, mas preserva seleção, foco instantâneo, isolamento e navegação HTML.
- Canvas nunca é a única interface: grupo, seleção, isolamento, sólidos, dimensões, sensor, contexto e limitações possuem controles HTML com foco visível e labels.
- Existe um único `Twin3DStaticFallback`, interno e context-aware, que usa a PNG regenerada e preserva `displayContext`, rails S1/S2, seleção, inspetores e controles aplicáveis. O seam público não aceita fallback legado; C e E não injetam outro fallback. Falha 3D não pode esconder histórico, valor, qualidade ou alerta.
- O twin permanece abaixo da hierarquia Situação → Entenda → Investigue e não ocupa sozinho o primeiro viewport em `1366x768`.
- A Fase D não edita backend, contratos de timeline, importador, migrações, provider histórico ou regras de decisão. A integração depende da interface de contexto descrita abaixo.
- Migração, importação, deploy e promoção pertencem à Fase E. A Fase D encerra com artefatos locais e handoff; não instala CLI, não cria ambiente/deployment preview e não escreve em serviços preview/produção.
- No fluxo integrado, o bootstrap da Task 1 da Fase E/index roda antes da Fase A e cria o SSoT compartilhado `docs/verification/unified-twin-acceptance-v1.json`, seu Markdown renderizado, `scripts/verify_unified_acceptance.py` e `playwright.twin.config.js`. Esse config é frontend-only, sobe somente o Vite local e usa exclusivamente o Chromium bundled do Playwright pinado; D o reutiliza sem editar. A Fase D trata esses arquivos como dependências existentes e somente atualiza sua própria entrada após verificar o SHA de código.
- O runner Vitest deve excluir explicitamente `**/.pytest_cache/**`; caches Python não são testes JavaScript nem evidência versionável.
- Depois que o checkpoint C1 estiver integrado, testado e aprovado por reviewer independente com `0 Critical / 0 Important`, registrar o HEAD limpo como `$phaseDStartCommit`. O código D pertence a dois intervalos disjuntos: `$phaseDStartCommit..$d7PublicSeamCommit` e `$phaseD8StartCommit..$verifiedCodeCommit`. O intervalo intermediário contém a integração C11 e possivelmente outros commits C válidos; ele é autenticado, mas nunca atribuído ou revisado como código D.
- A ordem de integração é obrigatoriamente **D7 → C11 → D8**: D publica o seam, C Task 11 o conecta ao dashboard e somente então D executa browser/performance/preview contra a aplicação integrada. Se o commit C11 não estiver integrado ou `playwright.twin.config.js` de E1 estiver ausente, D8 para como dependency gate.
- Os checkpoints C1 e C11 são autenticados pelo par `reviewedCodeCommit` + `evidenceCommit`: D lê o handoff e o report diretamente do evidence commit com `git show`, confere shape/digest/verdict/escopo e ancestry e nunca confia somente em variável de ambiente ou arquivo do working tree.
- Em Windows PowerShell 5.1, todo processo nativo (`git`, `npm.cmd`, `node`, Python) é seguido **imediatamente** por `Assert-NativeSuccess` antes da próxima instrução. O helper deve ser redefinido após qualquer reinício de shell; omitir o check é falha do protocolo, mesmo quando o snippet mostra apenas um comando. Servidores locais long-running não são exceção silenciosa: rodam em sessão dedicada/controlada, possuem readiness probe, PID/porta vinculados e teardown verificado pelo controller; nenhum passo posterior depende de um `npm run dev` manual sem supervisão.
- Um gate RED Vitest captura stdout/stderr, exige exclusivamente exit code `1` e uma assinatura específica da falha contratada. Erro de npm, PATH, ACL, OOM, coleta alheia ou qualquer exit diferente bloqueia a tarefa; nunca conta como RED válido.

## Required upstream interface

Antes da Task 1, a Fase C deve ter entregue o checkpoint C1 revisado com o contrato completo em `src/displayContext/displayContextV1.js`, o validador `assertDisplayContextV1(value)` e as fixtures de teste completas em `src/displayContext/displayContextV1.fixtures.js`. D importa esses artefatos sem copiar lista de campos, enums ou invariantes. O helper de fixtures nunca entra no runtime/bundle; somente testes D o reutilizam.

O seam integrado continua entregando `displayContext`, `selectedGroup`, `selectGroup`, `selectedSensor` e `selectSensor`. Todo entry point público de D chama primeiro `assertDisplayContextV1(displayContext)`, exige depois `displayContext.asset.assetId === "forzy-motor-01"` e somente então constrói view model ou passa props aos filhos. Contexto incompleto, campo extra ou asset diferente falha antes de montar canvas/inspetores; D nunca completa um contexto a partir de snapshot, fixture ou objeto de outro ativo.

Regras da integração:

- `selectedGroup: "motor" | "pump" | "coupling" | "base" | null` e `selectedSensor: "s1" | "s2" | "all"` pertencem ao provider e persistem ao alternar `now/historical`.
- Em `viewMode="now"`, `displayContext` já contém a projeção canônica live. Em `viewMode="historical"`, contém somente a projeção de `TimelineContextV1`; nenhum campo visual consulta snapshot live como fallback silencioso.
- A fixture C1 `historical_gap` já congela a representação estrutural de gap e é validada integralmente antes do uso; D verifica neutralidade/ausência sem possuir o resumo textual canônico de gap, que permanece exclusivo da Fase C.
- `driverEvidenceIds` e `emphasizedSensorIds` vêm da evidência contratada e derivada pela Fase C. O twin não tenta inferir o sensor dominante pela maior oscilação.
- Se a interface upstream divergir, o integrador adapta no provider da Fase C; não cria um segundo contexto local dentro de `Twin3D`.

## File Structure

### Create

- `src/components/twin3d/twinPresentation.js` — manifesto de apresentação textual, presets PBR ilustrativos e mapeamento exato node → source name.
- `src/components/twin3d/twinPresentation.test.js` — valida schema fechado, hashes, grupos, confiança e inventário.
- `src/components/twin3d/Twin3DScene.jsx` — clone da cena, materiais por grupo, contornos, raycast exato, isolamento, bounds e descarte.
- `src/components/twin3d/Twin3DScene.test.js` — testes Three sem WebGL para seleção, materiais, bounds, overlays e cleanup.
- `src/components/twin3d/TwinCameraRig.jsx` — foco por bounds e restauração isométrica via `useBounds`.
- `src/components/twin3d/TwinCameraRig.test.jsx` — comandos de foco/restauração e reduced motion.
- `src/components/twin3d/TwinGroupControls.jsx` — lista HTML, foco, isolamento, sólidos, dimensões e restaurar vista.
- `src/components/twin3d/TwinGroupControls.test.jsx` — teclado, estado e callbacks.
- `src/components/twin3d/TwinGroupInspector.jsx` — fatos CAD do grupo, nomes fonte, envelope e limitações.
- `src/components/twin3d/TwinGroupInspector.test.jsx` — copy fail-closed e modo avançado.
- `src/components/twin3d/vim32Evidence.js` — constantes documentadas e validação fechada do envelope VIM32.
- `src/components/twin3d/vim32Evidence.test.js` — dimensões/faixas e campos proibidos.
- `src/components/twin3d/Vim32EnvelopeDiagram.jsx` — diagrama dimensional acessível, sem detalhe não cotado.
- `src/components/twin3d/Vim32EnvelopeDiagram.test.jsx` — proporção, dimensões e copy.
- `src/components/twin3d/TwinSensorInspector.jsx` — rails S1/S2, leitura do contexto e dock do VIM32.
- `src/components/twin3d/TwinSensorInspector.test.jsx` — now/historical/gap, zero, ausência e posição não validada.
- `src/components/twin3d/twin3d.css` — estilos isolados da experiência 3D, importados somente pelo shell `Twin3D.jsx`.
- `scripts/twin3d/check-interactive-twin-assets.mjs` — hashes e inventário dos assets imutáveis.
- `scripts/twin3d/check-interactive-twin-assets.test.mjs` — rejeição de hash/node drift.
- `scripts/twin3d/check-lazy-twin-build.mjs` — prova de chunk lazy e ausência de URL externa.
- `scripts/twin3d/check-lazy-twin-build.test.mjs` — fixtures de manifest Vite válido/inválido.
- `scripts/twin3d/check-twin-production-claims.mjs` — scanner allowlist-aware dos outputs de produção.
- `scripts/twin3d/check-twin-production-claims.test.mjs` — aceita negações aprovadas e rejeita claims positivos/comandos.
- `scripts/twin3d/render-interactive-twin-preview.mjs` — regenera a PNG context-free a partir do GLB imutável em câmera/viewport fixos.
- `scripts/twin3d/render-interactive-twin-preview.test.mjs` — valida argumentos, readiness, dimensões e relatório de proveniência.
- `scripts/twin3d/profile-interactive-twin.mjs` — perfil reproduzível de FPS, long tasks e ambiente.
- `scripts/twin3d/profile-interactive-twin.test.mjs` — cálculo de mediana, pior run e gate.
- `tests/e2e/fixtures/interactive-twin.js` — respostas same-origin determinísticas para estados visuais.
- `tests/e2e/interactive-twin.spec.js` — navegador real, seleção, contexto, fallback, teclado e screenshots.

### Modify

- `src/components/twin3d/twinViewModel.js`
- `src/components/twin3d/twinViewModel.test.js`
- `src/components/twin3d/Twin3DCanvas.jsx`
- `src/components/twin3d/Twin3DCanvas.test.jsx`
- `src/components/Twin3D.jsx`
- `src/components/Twin3D.test.jsx`
- `public/models/conjunto-motor-bomba-preview.png`
- `vitest.config.js`
- `package.json`
- `docs/verification/unified-twin-acceptance-v1.json` — somente a entrada D, depois do SHA de código verificado.
- `docs/verification/unified-twin-acceptance-v1.md` — regenerado pelo script compartilhado, nunca editado manualmente.

### Reuse unchanged from upstream checkpoints

- `src/displayContext/displayContextV1.js` — contrato/validador completo de C1; D importa `assertDisplayContextV1` no runtime e não redefine o shape.
- `src/displayContext/displayContextV1.fixtures.js` — fixtures completas de C1, importadas somente nos testes D.
- `playwright.twin.config.js` — config frontend-only de E1, com Vite local e Chromium bundled; D não altera ownership/configuração.

### Generated and versioned only after measurement or independent review

- `artifacts/twin3d/performance-profile.json` — produzido pela Task 8 com valores medidos, nunca preenchido manualmente.
- `artifacts/twin3d/preview-render-report.json` — hash/renderer/viewport/GLB observados ao regenerar a PNG.
- `artifacts/twin3d/production-claims-report.json` — output allowlist-aware do bundle verificado.
- `artifacts/twin3d/interactive-twin-verification.json` — produzido pela Task 9 a partir de resultados e hashes reais.
- `docs/verification/phase-d-findings.json` — review independente no schema comum `finding-review-v1`.

---

## Phase D start checkpoint

Antes da Task 1, receber do handoff C1 o SHA exato revisado em `C1_DISPLAY_CONTRACT_COMMIT` e o evidence commit em `C1_HANDOFF_EVIDENCE_COMMIT`. Não aceitar apenas branch name, working-tree HEAD ou dois SHAs sem verificar os blobs que eles nomeiam. Executar em árvore limpa:

```powershell
$globalBaseCommit = "4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e"
function Assert-NativeSuccess([string]$label) {
  if ($LASTEXITCODE -ne 0) { throw "$label failed with exit code $LASTEXITCODE" }
}
$c1DisplayContractCommit = $env:C1_DISPLAY_CONTRACT_COMMIT
$c1HandoffEvidenceCommit = $env:C1_HANDOFF_EVIDENCE_COMMIT
if ($c1DisplayContractCommit -notmatch '^[0-9a-f]{40}$' -or $c1HandoffEvidenceCommit -notmatch '^[0-9a-f]{40}$') { throw 'C1 reviewed and evidence commits are required' }
git merge-base --is-ancestor $globalBaseCommit $c1DisplayContractCommit
Assert-NativeSuccess 'C1 global ancestry'
git merge-base --is-ancestor $c1DisplayContractCommit $c1HandoffEvidenceCommit
Assert-NativeSuccess 'C1 evidence ancestry'
git merge-base --is-ancestor $c1HandoffEvidenceCommit HEAD
Assert-NativeSuccess 'C1 evidence integration'
git merge-base --is-ancestor $c1DisplayContractCommit HEAD
Assert-NativeSuccess 'C1 code integration'
$phaseDInitialStatus = @(git status --porcelain)
Assert-NativeSuccess 'Phase D initial status'
if ($phaseDInitialStatus.Count -ne 0) { throw 'Phase D must start from a clean tree' }
$actualC1EvidencePaths = @(git diff --name-only "$c1DisplayContractCommit..$c1HandoffEvidenceCommit")
Assert-NativeSuccess 'C1 evidence scope read'
$expectedC1EvidencePaths = @(
  'docs/verification/checkpoints/c1-display-contract-handoff.json',
  'docs/verification/phase-c-findings.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
)
if (Compare-Object ($expectedC1EvidencePaths | Sort-Object) ($actualC1EvidencePaths | Sort-Object) -CaseSensitive -SyncWindow 0) { throw 'C1 evidence commit scope mismatch' }
$phaseCheckpointValidator = @'
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const [evidence, code, handoffPath, checkpoint, consumer, expectedEnvironmentCsv] = process.argv.slice(1);
const show = (path) => execFileSync('git', ['show', evidence + ':' + path]);
const handoff = JSON.parse(show(handoffPath).toString('utf8'));
const exact = ['baseCommit','checkpoint','consumerTask','environment','producerPlan','reviewedCodeCommit','reviewReport','reviewReportSha256','schemaVersion','verdict'];
const keys = Object.keys(handoff).sort();
const expectedEnvironment = expectedEnvironmentCsv.split(',').sort();
const environmentKeys = Object.keys(handoff.environment || {}).sort();
const verdictKeys = Object.keys(handoff.verdict || {}).sort();
const reportBytes = show(handoff.reviewReport);
const report = JSON.parse(reportBytes.toString('utf8'));
const digest = crypto.createHash('sha256').update(reportBytes).digest('hex');
const fail = keys.join('|') !== exact.sort().join('|') || environmentKeys.join('|') !== expectedEnvironment.join('|') || verdictKeys.join('|') !== 'critical|important|minor' || handoff.schemaVersion !== 'phase-checkpoint-handoff-v1' || handoff.checkpoint !== checkpoint || handoff.producerPlan !== 'C' || handoff.consumerTask !== consumer || !/^[0-9a-f]{40}$/.test(handoff.baseCommit) || handoff.reviewedCodeCommit !== code || handoff.reviewReport !== 'docs/verification/phase-c-findings.json' || handoff.reviewReportSha256 !== digest || report.schemaVersion !== 'finding-review-v1' || report.plan !== 'C' || report.reviewedSha !== code || report.verdict.critical !== 0 || report.verdict.important !== 0 || handoff.verdict.critical !== report.verdict.critical || handoff.verdict.important !== report.verdict.important || handoff.verdict.minor !== report.verdict.minor || expectedEnvironment.some((key) => handoff.environment[key] !== (key === 'D7_PUBLIC_SEAM_COMMIT' ? process.argv[7] : code));
if (fail) process.exit(1);
execFileSync('git', ['merge-base','--is-ancestor', handoff.baseCommit, code]);
'@
node -e $phaseCheckpointValidator $c1HandoffEvidenceCommit $c1DisplayContractCommit 'docs/verification/checkpoints/c1-display-contract-handoff.json' 'C1' 'D1' 'C1_DISPLAY_CONTRACT_COMMIT'
Assert-NativeSuccess 'C1 handoff blob validation'
$rawC1Handoff = @(git show "$c1HandoffEvidenceCommit`:docs/verification/checkpoints/c1-display-contract-handoff.json")
Assert-NativeSuccess 'read C1 handoff blob'
$c1Handoff = (($rawC1Handoff -join "`n") | ConvertFrom-Json)
$expectedC1CodePaths = @(
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
)
$actualC1CodePaths = @(git diff --name-only $c1Handoff.baseCommit $c1DisplayContractCommit)
Assert-NativeSuccess 'read C1 code scope'
if (Compare-Object ($expectedC1CodePaths | Sort-Object) ($actualC1CodePaths | Sort-Object) -CaseSensitive -SyncWindow 0) { throw 'C1 code scope mismatch' }
git diff --check $c1Handoff.baseCommit $c1DisplayContractCommit
Assert-NativeSuccess 'C1 code diff hygiene'
foreach ($path in @('src/displayContext/displayContextV1.js','src/displayContext/displayContextV1.fixtures.js','playwright.twin.config.js')) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "missing upstream dependency: $path" }
}
git diff --exit-code $c1DisplayContractCommit HEAD -- src/displayContext/displayContextV1.js src/displayContext/displayContextV1.fixtures.js
Assert-NativeSuccess 'C1 display contract drift check'
$phaseDStartCommit = (git rev-parse HEAD).Trim()
Assert-NativeSuccess 'Phase D start SHA'
git merge-base --is-ancestor $globalBaseCommit $phaseDStartCommit
Assert-NativeSuccess 'Phase D start ancestry'
$env:PHASE_D_START_COMMIT = $phaseDStartCommit
```

Registrar `$phaseDStartCommit` no handoff de execução e preservá-lo até a Task 9. Upstream integrado antes desse SHA pertence ao respectivo plano; nenhum scope check de D usa `globalBaseCommit..HEAD`.

### Task 1: Freeze the evidence-safe presentation contract

**Files:**
- Create: `src/components/twin3d/twinPresentation.js`
- Create: `src/components/twin3d/twinPresentation.test.js`
- Modify: `src/components/twin3d/twinViewModel.js`
- Modify: `src/components/twin3d/twinViewModel.test.js`

**Interfaces:**
- Consumes: `parseModelManifest(value)`, `assertDisplayContextV1(value)`, as fixtures completas de C1 e o manifesto técnico existente, sem alterá-los.
- Produces: `TWIN_PRESENTATION_V1`, `validateTwinPresentation(value, manifest)`, `presentationForGroup(groupName)`, `sourceNameForNode(nodeName)`.
- Produces: `assertForzyTwinDisplayContext(value)`, que delega o shape/invariantes completos a `assertDisplayContextV1` e acrescenta somente o binding `asset.assetId === "forzy-motor-01"`.
- Produces: `buildTwinViewModel({ displayContext, manifest, selectedGroup, hoveredGroup, isolateSelected, showDimensions, selectedSolidNode }): TwinViewModel`.

- [ ] **Step 1: Write the failing presentation-contract tests**

```js
import manifest from "../../../public/models/conjunto-motor-bomba.manifest.json";
import {
  TWIN_PRESENTATION_V1,
  sourceNameForNode,
  validateTwinPresentation,
} from "./twinPresentation.js";

it("covers the immutable manifest with four illustrative group presets", () => {
  const value = validateTwinPresentation(TWIN_PRESENTATION_V1, manifest);
  expect(Object.keys(value.groups).sort()).toEqual(["base", "coupling", "motor", "pump"]);
  expect(new Set(Object.values(value.groups).map((group) => group.baseColor)).size).toBe(4);
  for (const group of Object.values(value.groups)) {
    expect(group.presentationConfidence).toBe("illustrative");
    expect(group.semanticConfidence).toBe("inferred_from_source_name");
  }
  expect(value.modelSourceSha256).toBe(manifest.sourceSha256);
});

it("maps every node to an exact source name without fuzzy aliases", () => {
  expect(manifest.nodes.map(sourceNameForNode)).not.toContain(null);
  expect(sourceNameForNode("R11_06-2130-UNKNOWN")).toBeNull();
  expect(sourceNameForNode("ME22A")).toBeNull();
});
```

- [ ] **Step 2: Run the presentation tests and confirm RED**

Run:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/twinPresentation.test.js 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*twinPresentation)(?=.*(?:failed to resolve import|cannot find module|does not exist))') { throw 'twin presentation RED did not fail for the expected missing module' }
```

Expected: FAIL porque `twinPresentation.js` não existe.

- [ ] **Step 3: Implement the closed presentation manifest**

Use um objeto congelado com estas chaves e valores normativos:

```js
export const TWIN_PRESENTATION_V1 = deepFreeze({
  schemaVersion: "1.0",
  modelSourceSha256: "7af8e745df756787282cfec2f5b6fe6a73650ba0937c542181f9d614324386f3",
  groups: {
    motor: {
      label: "Grupo CAD do motor",
      baseColor: "#3d7895",
      metalness: 0.18,
      roughness: 0.52,
      semanticConfidence: "inferred_from_source_name",
      presentationConfidence: "illustrative",
      sourceRule: "Nomes fonte ME22A; não valida componentes internos",
    },
    pump: {
      label: "Grupo CAD da bomba",
      baseColor: "#334155",
      metalness: 0.12,
      roughness: 0.72,
      semanticConfidence: "inferred_from_source_name",
      presentationConfidence: "illustrative",
      sourceRule: "Nomes fonte B01A/BOMBA; não valida impulsor ou selo",
    },
    coupling: {
      label: "Grupo CAD do acoplamento",
      baseColor: "#b7c2cc",
      metalness: 0.5,
      roughness: 0.34,
      semanticConfidence: "inferred_from_source_name",
      presentationConfidence: "illustrative",
      sourceRule: "Regra do conversor sobre nomes B01A/A, B01A/B e B01A/C",
    },
    base: {
      label: "Grupo CAD da base",
      baseColor: "#1f2937",
      metalness: 0.08,
      roughness: 0.82,
      semanticConfidence: "inferred_from_source_name",
      presentationConfidence: "illustrative",
      sourceRule: "Nomes fonte B01A/BASE; não valida material real",
    },
  },
  sourceNamesByNode: {
    "R11_06-2130-ME22A_001": "R11.06-2130-ME22A_001",
    "R11_06-2130-ME22A_002": "R11.06-2130-ME22A_002",
    "R11_06-2130-ME22A_003": "R11.06-2130-ME22A_003",
    "R11_06-2130-ME22A_004": "R11.06-2130-ME22A_004",
    "R11_06-2130-ME22A_005": "R11.06-2130-ME22A_005",
    "R11_06-2130-ME22A_006": "R11.06-2130-ME22A_006",
    "R11_06-2130-ME22A_007": "R11.06-2130-ME22A_007",
    "R11_06-2130-B01A_BOMBA_008": "R11.06-2130-B01A/BOMBA_008",
    "R11_06-2130-B01A_BOMBA_009": "R11.06-2130-B01A/BOMBA_009",
    "R11_06-2130-B01A_BOMBA_010": "R11.06-2130-B01A/BOMBA_010",
    "R11_06-2130-B01A_A": "R11.06-2130-B01A/A",
    "R11_06-2130-B01A_A__02": "R11.06-2130-B01A/A",
    "R11_06-2130-B01A_B": "R11.06-2130-B01A/B",
    "R11_06-2130-B01A_B__02": "R11.06-2130-B01A/B",
    "R11_06-2130-B01A_C": "R11.06-2130-B01A/C",
    "R11_06-2130-B01A_BASE_011": "R11.06-2130-B01A/BASE_011",
    "R11_06-2130-B01A_BASE_012": "R11.06-2130-B01A/BASE_012",
  },
});
```

`validateTwinPresentation` deve rejeitar campo extra, preset ausente, número não finito, confiança diferente, hash divergente, node ausente ou alias não pertencente a `manifest.nodes`.

- [ ] **Step 4: Write RED tests for display-context projection**

```js
import { assertDisplayContextV1 } from "../../displayContext/displayContextV1.js";
import { DISPLAY_CONTEXT_V1_FIXTURES } from "../../displayContext/displayContextV1.fixtures.js";
import { assertForzyTwinDisplayContext } from "./twinViewModel.js";

const historicalAlert = assertForzyTwinDisplayContext(
  structuredClone(DISPLAY_CONTEXT_V1_FIXTURES.historicalAlert),
);
const historicalGap = assertForzyTwinDisplayContext(
  structuredClone(DISPLAY_CONTEXT_V1_FIXTURES.historicalGap),
);

expect(assertDisplayContextV1(historicalAlert)).toBe(historicalAlert);
expect(historicalAlert.asset.assetId).toBe("forzy-motor-01");

it("preserves group colors and applies alert only as a global accent", () => {
  const value = buildTwinViewModel({
    displayContext: historicalAlert,
    manifest,
    selectedGroup: "pump",
    hoveredGroup: null,
    isolateSelected: false,
    showDimensions: true,
    selectedSolidNode: "R11_06-2130-B01A_BOMBA_008",
  });
  expect(value.viewMode).toBe("historical");
  expect(value.conditionState).toBe("alert");
  expect(new Set(Object.values(value.groups).map((group) => group.baseColor)).size).toBe(4);
  expect(new Set(Object.values(value.groups).map((group) => group.conditionEmissive)).size).toBe(1);
  expect(value.causalGroup).toBeNull();
  expect(value.emphasizedSensorIds).toEqual(["s1"]);
  expect(value.showDimensions).toBe(true);
  expect(value.selectedSolidNode).toBe("R11_06-2130-B01A_BOMBA_008");
});

it("fails a gap closed without carrying the live snapshot", () => {
  const value = buildTwinViewModel({
    displayContext: historicalGap,
    manifest,
    selectedGroup: null,
    hoveredGroup: null,
    isolateSelected: false,
    showDimensions: false,
    selectedSolidNode: null,
  });
  expect(value.conditionState).toBe("unknown");
  expect(value.isNeutral).toBe(true);
  expect(value.causalGroup).toBeNull();
});

it("rejects an incomplete or cross-asset context before projection", () => {
  const incomplete = structuredClone(historicalAlert);
  delete incomplete.publicAcquisition;
  const crossAsset = structuredClone(historicalAlert);
  crossAsset.asset = { assetId: "other-asset" };
  const args = {
    manifest, selectedGroup: null, hoveredGroup: null, isolateSelected: false,
    showDimensions: false, selectedSolidNode: null,
  };
  expect(() => buildTwinViewModel({ ...args, displayContext: incomplete }))
    .toThrow(/displayContext\.publicAcquisition/);
  expect(() => buildTwinViewModel({ ...args, displayContext: crossAsset }))
    .toThrow(/forzy-motor-01/);
});
```

- [ ] **Step 5: Run the view-model tests and confirm RED**

Run:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/twinViewModel.test.js 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*twinViewModel)(?=.*(?:assertionerror|expected|is not a function|typeerror|referenceerror))') { throw 'twin view-model RED did not fail for the expected projection mismatch' }
```

Expected: FAIL porque a função atual aceita `{snapshot}` e produz um único material global.

- [ ] **Step 6: Implement the pure view model**

`buildTwinViewModel` deve:

1. aceitar somente os sete argumentos nomeados;
2. chamar `assertForzyTwinDisplayContext(displayContext)` antes de ler qualquer campo; essa função chama o `assertDisplayContextV1` de C1, preserva a mesma referência e rejeita asset diferente de `forzy-motor-01`, sem repetir lista de campos/enums/invariantes;
3. obter nodes apenas de `manifest.groups[groupName].nodeNames`;
4. manter `baseColor`, `metalness` e `roughness` por grupo;
5. aplicar o mesmo `conditionEmissive` global a todos os grupos;
6. projetar `hoveredGroup`, `showDimensions` e `selectedSolidNode` sem inferência; `selectedSolidNode` divergente do grupo selecionado ou ausente de `manifest.nodes` falha fechado para `null`;
7. usar opacidade `0.14` somente nos grupos não selecionados durante isolamento;
8. retornar `causalGroup: null` incondicionalmente nesta versão;
9. forçar `isNeutral=true` quando `conditionState` for `unknown|insufficient_data`, `conditionTemporalScope` for `none` ou disponibilidade for `gap|unavailable`.

`Twin3D.jsx` reutiliza o mesmo `assertForzyTwinDisplayContext`; nenhum componente D constrói `displayContext`, corrige campos ausentes ou combina contexto com objeto de outro ativo. As fixtures C1 são importadas apenas pelos arquivos `*.test.*`.

Mapa de acento:

```js
const CONDITION_ACCENT = Object.freeze({
  normal: { color: "#2dd4bf", intensity: 0.04 },
  watch: { color: "#f59e0b", intensity: 0.12 },
  alert: { color: "#ef4444", intensity: 0.2 },
  unknown: { color: "#64748b", intensity: 0 },
  insufficient_data: { color: "#64748b", intensity: 0 },
});
```

- [ ] **Step 7: Run GREEN and the immutable-manifest regression**

Run:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/twinPresentation.test.js src/components/twin3d/twinViewModel.test.js src/components/twin3d/modelManifest.test.js
Assert-NativeSuccess 'focused twin presentation regression'
```

Expected: PASS; manifesto continua rejeitando `position`, `componentTag`, wildcard e `assetTag` fictício.

- [ ] **Step 8: Commit the presentation contract**

```powershell
git add src/components/twin3d/twinPresentation.js src/components/twin3d/twinPresentation.test.js src/components/twin3d/twinViewModel.js src/components/twin3d/twinViewModel.test.js
Assert-NativeSuccess 'stage twin presentation contract'
git diff --cached --check
Assert-NativeSuccess 'check staged twin presentation contract'
git commit -m "feat: define evidence-safe twin presentation"
Assert-NativeSuccess 'commit twin presentation contract'
```

---

### Task 2: Prepare the scene for exact picking and per-group materials

**Files:**
- Create: `src/components/twin3d/Twin3DScene.jsx`
- Create: `src/components/twin3d/Twin3DScene.test.js`
- Modify: `src/components/twin3d/Twin3DCanvas.jsx`
- Modify: `src/components/twin3d/Twin3DCanvas.test.jsx`

**Interfaces:**
- Consumes: validated technical manifest and `TwinViewModel` from Task 1.
- Produces: `resolveTraceableNode(object, manifest): string | null`.
- Produces: `resolveTwinSelection(object, manifest): { nodeName, groupName } | null`.
- Produces: `prepareTwinScene(sourceScene, manifest): PreparedTwinScene`.
- Produces: `applyTwinAppearance(prepared, viewModel, { showCadSolids, showDimensions, selectedSolidNode, hoveredGroup }): void`.
- Produces: `disposePreparedTwinScene(prepared): void`.
- Produces: `Twin3DScene({ modelUrl, manifest, viewModel, showCadSolids, showDimensions, selectedSolidNode, hoveredGroup, onHoverGroup, onSelectGroup, onGeometryMetadata, onReady })`.

- [ ] **Step 1: Write RED tests for exact ancestor selection**

```js
it("resolves a primitive through an exact traceable ancestor", () => {
  const root = new Group();
  const solid = new Group();
  solid.name = "R11_06-2130-B01A_BOMBA_008";
  const primitive = new Mesh(new BoxGeometry(), new MeshStandardMaterial());
  primitive.name = "primitive_0";
  solid.add(primitive);
  root.add(solid);

  expect(resolveTraceableNode(primitive, manifest)).toBe(solid.name);
  expect(resolveTwinSelection(primitive, manifest)).toEqual({
    nodeName: solid.name,
    groupName: "pump",
  });
});

it.each(["ME22A", "BOMBA", "R11_06-2130-B01A_BOMBA_008-extra"])(
  "rejects non-exact node %s",
  (name) => {
    const node = new Object3D();
    node.name = name;
    expect(resolveTwinSelection(node, manifest)).toBeNull();
  },
);
```

- [ ] **Step 2: Run the scene test and confirm RED**

Run:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/Twin3DScene.test.js 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*Twin3DScene)(?=.*(?:failed to resolve import|cannot find module|does not exist))') { throw 'exact scene RED did not fail for the expected missing module' }
```

Expected: FAIL porque o módulo não existe.

- [ ] **Step 3: Implement exact traversal and sanitized diagnostics**

Implementar literalmente:

```js
export function resolveTraceableNode(object, manifest) {
  for (let current = object; current; current = current.parent) {
    if (manifest.nodes.includes(current.name)) return current.name;
  }
  return null;
}

export function resolveTwinSelection(object, manifest) {
  const nodeName = resolveTraceableNode(object, manifest);
  if (nodeName === null) return null;
  const groupName = nodeGroup(manifest, nodeName);
  return groupName === null ? null : { nodeName, groupName };
}
```

Warnings não podem incluir URL, stack, path ou nome arbitrário completo. Usar somente `console.warn("Twin3D ignored an untraceable scene node")`, uma vez por cena.

- [ ] **Step 4: Write RED tests for materials, isolation, edges, bounds and cleanup**

Os testes devem construir uma `Scene` com um nó por grupo e provar:

```js
expect(materials.motor.color.getHexString()).not.toBe(materials.pump.color.getHexString());
expect(materials.pump.opacity).toBe(1);
expect(materials.motor.opacity).toBe(0.14);
expect(prepared.groupBounds.pump.isEmpty()).toBe(false);
expect(prepared.assemblyBounds.isEmpty()).toBe(false);
expect(prepared.edgeOverlays.every((line) => line.userData.twinOverlay === true)).toBe(true);
expect(resolveTwinSelection(prepared.edgeOverlays[0], manifest)).toBeNull();
applyTwinAppearance(prepared, viewModel, {
  showCadSolids: true,
  showDimensions: true,
  selectedSolidNode: "R11_06-2130-B01A_BOMBA_008",
  hoveredGroup: "pump",
});
expect(prepared.dimensionOverlays.pump.visible).toBe(true);
expect(prepared.dimensionOverlays.motor.visible).toBe(false);
expect(prepared.edgeOverlaysByNode["R11_06-2130-B01A_BOMBA_008"].userData.highlightKind).toBe("solid");
expect(prepared.groupOverlays.pump.userData.highlightKind).toBe("hover");
```

Adicionar RED cases para `showDimensions=false`, `selectedSolidNode` fora do grupo, hover sobre nó desconhecido e troca repetida de sólido/grupo sem acumular helpers. Após `disposePreparedTwinScene`, spies devem provar descarte de todo material clonado, toda `EdgesGeometry` e toda geometria/material dos helpers `Box3`, sem descartar geometria/material do `sourceScene` retornado pelo cache `useGLTF`.

- [ ] **Step 5: Implement scene preparation**

`prepareTwinScene` deve:

- clonar a hierarquia;
- clonar cada material por mesh;
- localizar o ancestral exato e gravar em `mesh.userData.twinNodeName` e `twinGroupName`;
- criar `Box3` do conjunto, recentrar X/Z e mover o menor Y para zero apenas no clone;
- atualizar matrices e recalcular bounds após a translação;
- calcular `assemblyBounds` e um `Box3` por grupo;
- criar `EdgesGeometry(mesh.geometry, 30)` e `LineSegments` não-raycastable para cada mesh;
- criar `dimensionOverlays[groupName]` como `Box3Helper` do `groupBounds` já recalculado; helpers são não-raycastable, ocultos por padrão e nunca inventam dimensão a partir da preview;
- manter `edgeOverlaysByNode` e `groupOverlays` separados: sólido exato selecionado usa contorno forte, grupo hovered usa contorno médio e seleção de grupo usa contorno estável;
- marcar todos os overlays com `userData.twinOverlay=true`, `raycast=() => null` e ocultá-los por padrão;
- retornar metadata com `solidCount`, node names e dimensões em milímetros.

`applyTwinAppearance` recebe explicitamente `showCadSolids`, `showDimensions`, `selectedSolidNode` e `hoveredGroup` propagados do view model. Deve definir determinísticamente `color`, `metalness`, `roughness`, `emissive`, `emissiveIntensity`, `transparent`, `opacity`, `depthWrite`, helper `Box3` e visibilidade/intensidade dos contornos a cada atualização; primeiro limpa todos os estados transitórios, depois aplica sólido, seleção e hover, sem acumular a renderização anterior. Dimensões aparecem somente para o grupo selecionado; sem grupo selecionado, o toggle conserva o estado mas nenhum helper aparece.

- [ ] **Step 6: Move scene ownership out of Twin3DCanvas**

Remover de `Twin3DCanvas.jsx` as implementações atuais de `cloneSceneWithIndependentMaterials`, `visitMaterials`, `applyViewModelToSceneMaterials` e `disposeSceneMaterials`. O canvas passa a renderizar `Twin3DScene`; testes existentes de clone/disposal migram para `Twin3DScene.test.js`.

Eventos na `<primitive>`:

```jsx
<primitive
  object={prepared.scene}
  onPointerMove={(event) => {
    event.stopPropagation();
    const selection = resolveTwinSelection(event.object, manifest);
    onHoverGroup(selection?.groupName ?? null);
    event.nativeEvent.target.style.cursor = selection ? "pointer" : "default";
  }}
  onPointerOut={(event) => {
    onHoverGroup(null);
    event.nativeEvent.target.style.cursor = "default";
  }}
  onClick={(event) => {
    event.stopPropagation();
    const selection = resolveTwinSelection(event.object, manifest);
    if (selection) onSelectGroup(selection.groupName);
  }}
/>
```

Passar `showDimensions`, `selectedSolidNode` e `hoveredGroup` de `Twin3DCanvas` para `buildTwinViewModel`, de lá para `Twin3DScene` e finalmente para `applyTwinAppearance`. `onPointerMissed` também limpa hover/cursor. Testes de canvas devem provar essa cadeia completa e que overlay nunca captura clique.

- [ ] **Step 7: Run GREEN scene and canvas tests**

Run:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/Twin3DScene.test.js src/components/twin3d/Twin3DCanvas.test.jsx
Assert-NativeSuccess 'GREEN exact scene tests'
```

Expected: PASS, incluindo node desconhecido sem seleção e sem vazamento de material/edge geometry.

- [ ] **Step 8: Commit the exact interactive scene**

```powershell
git add src/components/twin3d/Twin3DScene.jsx src/components/twin3d/Twin3DScene.test.js src/components/twin3d/Twin3DCanvas.jsx src/components/twin3d/Twin3DCanvas.test.jsx
Assert-NativeSuccess 'stage interactive twin scene'
git diff --cached --check
Assert-NativeSuccess 'check staged interactive twin scene'
git commit -m "feat: add exact interactive twin scene"
Assert-NativeSuccess 'commit interactive twin scene'
```

---

### Task 3: Add studio composition, camera focus and demand rendering

**Files:**
- Create: `src/components/twin3d/TwinCameraRig.jsx`
- Create: `src/components/twin3d/TwinCameraRig.test.jsx`
- Modify: `src/components/twin3d/Twin3DCanvas.jsx`
- Modify: `src/components/twin3d/Twin3DCanvas.test.jsx`
- Create: `src/components/twin3d/twin3d.css`
- Modify: `src/components/Twin3D.jsx`

**Interfaces:**
- Consumes: `PreparedTwinScene.groupBounds`, `assemblyBounds` and `cameraRequest`.
- Produces: `cameraRequest = { kind: "assembly" | "group", groupName: GroupName | null, requestId: number }`.
- Produces: `TwinCameraRig({ cameraRequest, assemblyBounds, groupBounds, reducedMotion })`.
- Produces: `Twin3DCanvas({ displayContext, selectedGroup, hoveredGroup, isolateSelected, showCadSolids, showDimensions, selectedSolidNode, cameraRequest, onHoverGroup, onSelectGroup, onGeometryMetadata })`.

- [ ] **Step 1: Write RED tests for camera commands**

Mockar `useBounds()` e provar:

```jsx
it("focuses the exact selected group bounds", () => {
  render(
    <TwinCameraRig
      cameraRequest={{ kind: "group", groupName: "pump", requestId: 2 }}
      assemblyBounds={assemblyBox}
      groupBounds={{ pump: pumpBox }}
      reducedMotion={false}
    />,
  );
  expect(bounds.refresh).toHaveBeenCalledWith(pumpBox);
  expect(bounds.fit).toHaveBeenCalled();
  expect(bounds.clip).toHaveBeenCalled();
});

it("restores an isometric assembly view", () => {
  render(<TwinCameraRig cameraRequest={{ kind: "assembly", groupName: null, requestId: 3 }} {...boxes} />);
  expect(bounds.refresh).toHaveBeenCalledWith(assemblyBox);
  expect(bounds.to).toHaveBeenCalledWith(expect.objectContaining({ target: expect.any(Array) }));
});
```

- [ ] **Step 2: Run the camera test and confirm RED**

Run:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/TwinCameraRig.test.jsx 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*TwinCameraRig)(?=.*(?:failed to resolve import|cannot find module|does not exist))') { throw 'camera rig RED did not fail for the expected missing module' }
```

Expected: FAIL porque o módulo não existe.

- [ ] **Step 3: Implement camera focus through useBounds**

`TwinCameraRig` deve ficar dentro de `<Bounds>`. Para `group`, chamar `refresh(groupBox).fit().clip()`. Para `assembly`, chamar `refresh(assemblyBox)`, obter `{center,distance}` e executar:

```js
bounds.to({
  position: [center.x + distance * 0.85, center.y + distance * 0.55, center.z + distance * 0.85],
  target: center.toArray(),
}).clip();
```

Configurar `<Bounds maxDuration={reducedMotion ? 0.01 : 0.6}>`. Um `requestId` repetido não repete movimento; uma mudança de `displayContext` sem novo `requestId` não chama `useBounds`.

- [ ] **Step 4: Write RED tests for the complete canvas composition**

Atualizar mocks de Drei para `Bounds`, `ContactShadows`, `OrbitControls` e `useBounds`. Exigir:

- `<Canvas frameloop="demand" dpr={[1,1.5]} shadows>`;
- câmera `fov=38`, `near=0.01`, `far=100`;
- luz ambiente/hemisférica, key e fill locais;
- `ContactShadows` com `resolution=512`, `frames=1`, `blur=2`, `opacity<=0.3`;
- plano de solo discreto sem texture URL;
- `data-model-ready`, `data-rendered-node-count="17"`, `data-view-mode` e `data-decision-as-of`;
- atualização de `displayContext` não remonta `Twin3DScene`.

- [ ] **Step 5: Implement the studio scene without remote resources**

Estrutura normativa:

```jsx
<Canvas
  camera={{ fov: 38, near: 0.01, far: 100, position: [2.4, 1.6, 2.4] }}
  dpr={[1, 1.5]}
  frameloop="demand"
  shadows
>
  <color attach="background" args={["#081421"]} />
  <hemisphereLight args={["#dbeafe", "#111827", 1.2]} />
  <directionalLight position={[3, 5, 4]} intensity={2.1} castShadow />
  <directionalLight position={[-4, 2, -3]} intensity={0.65} />
  <Bounds fit clip margin={1.2} maxDuration={reducedMotion ? 0.01 : 0.6}>
    <Twin3DScene {...sceneProps} />
    <TwinCameraRig {...cameraProps} />
  </Bounds>
  <ContactShadows position={[0, -0.002, 0]} opacity={0.28} scale={3} blur={2} far={1.5} resolution={512} frames={1} />
  <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.004, 0]} receiveShadow>
    <planeGeometry args={[3, 3]} />
    <meshStandardMaterial color="#0d1b2a" metalness={0} roughness={0.95} />
  </mesh>
  <OrbitControls makeDefault enableDamping={false} enablePan={false} />
</Canvas>
```

O plano/ContactShadows só é exibido depois que a cena foi recentrada no piso pela Task 2.

- [ ] **Step 6: Add twin-only responsive styling**

Criar `src/components/twin3d/twin3d.css` com as classes `.twin-engineering-shell`, `.twin-viewport`, `.twin-canvas-frame` e estado de foco. Importar o arquivo exclusivamente no shell com `import "./twin3d/twin3d.css";` em `Twin3D.jsx`; não adicionar regras a `src/styles.css`. O viewport terá `height: clamp(22rem, 52vw, 34rem)` e nunca excederá a largura do painel. Em `max-width: 600px`, altura mínima `20rem`; nenhum controle usa hover como único affordance.

- [ ] **Step 7: Run GREEN canvas and camera tests**

Run:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/TwinCameraRig.test.jsx src/components/twin3d/Twin3DCanvas.test.jsx src/components/twin3d/Twin3DScene.test.js
Assert-NativeSuccess 'GREEN camera and scene tests'
```

Expected: PASS; rerender de contexto mantém a mesma instância marcada por `data-testid="twin3d-canvas"` e não repete o loader.

- [ ] **Step 8: Commit the visual composition**

```powershell
git add src/components/twin3d/TwinCameraRig.jsx src/components/twin3d/TwinCameraRig.test.jsx src/components/twin3d/Twin3DCanvas.jsx src/components/twin3d/Twin3DCanvas.test.jsx src/components/twin3d/twin3d.css src/components/Twin3D.jsx
Assert-NativeSuccess 'stage twin visual composition'
git diff --cached --check
Assert-NativeSuccess 'check staged twin visual composition'
git commit -m "feat: add studio lighting and twin camera focus"
Assert-NativeSuccess 'commit twin visual composition'
```

---

### Task 4: Add accessible CAD navigation and the group inspector

**Files:**
- Create: `src/components/twin3d/TwinGroupControls.jsx`
- Create: `src/components/twin3d/TwinGroupControls.test.jsx`
- Create: `src/components/twin3d/TwinGroupInspector.jsx`
- Create: `src/components/twin3d/TwinGroupInspector.test.jsx`
- Modify: `src/components/twin3d/Twin3DCanvas.jsx`
- Modify: `src/components/twin3d/Twin3DCanvas.test.jsx`
- Modify: `src/components/twin3d/twin3d.css`

**Interfaces:**
- Consumes: `selectedGroup`, exact manifest, presentation contract and `GeometryMetadata` from Task 2.
- Produces: `TwinGroupControls({ selectedGroup, isolateSelected, showCadSolids, showDimensions, onSelectGroup, onToggleIsolation, onToggleCadSolids, onToggleDimensions, onFocusGroup, onRestoreView })`.
- Produces: `TwinGroupInspector({ selectedGroup, manifest, geometryMetadata, showCadSolids, selectedSolidNode, onSelectSolid })`.
- Produces: `GeometryMetadata = { assembly: { solidCount, sizeMm }, groups: Record<GroupName,{ solidCount,nodeNames,sourceNames,sizeMm|null }> }`.

- [ ] **Step 1: Write failing keyboard/navigation tests**

```jsx
it("offers the four exact groups as keyboard-operable buttons", async () => {
  const onSelectGroup = vi.fn();
  render(<TwinGroupControls {...defaultProps} selectedGroup={null} onSelectGroup={onSelectGroup} />);
  const pump = screen.getByRole("button", { name: "Selecionar grupo CAD da bomba" });
  pump.focus();
  await userEvent.keyboard("{Enter}");
  expect(onSelectGroup).toHaveBeenCalledWith("pump");
  expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(4);
});

it("does not enable isolation before a group is selected", () => {
  render(<TwinGroupControls {...defaultProps} selectedGroup={null} />);
  expect(screen.getByRole("checkbox", { name: "Isolar grupo selecionado" })).toBeDisabled();
});
```

- [ ] **Step 2: Run controls tests and confirm RED**

Run:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/TwinGroupControls.test.jsx 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*TwinGroupControls)(?=.*(?:failed to resolve import|cannot find module|does not exist))') { throw 'twin group controls RED did not fail for the expected missing module' }
```

Expected: FAIL porque o componente não existe.

- [ ] **Step 3: Implement the HTML-equivalent controls**

Os quatro botões usam labels públicos `Motor`, `Bomba`, `Acoplamento` e `Base`, mas o texto auxiliar usa “grupo CAD”. Cada botão possui `aria-pressed`. Adicionar:

- checkbox `Isolar grupo selecionado`;
- checkbox `Mostrar sólidos CAD`;
- checkbox `Mostrar dimensões do CAD`;
- botão `Focar grupo selecionado`, desabilitado sem seleção;
- botão `Restaurar vista isométrica`;
- status `aria-live="polite"` com `Grupo CAD selecionado: {label}`.

`onFocusGroup` emite `{kind:"group",groupName:selectedGroup}`. `onRestoreView` emite `{kind:"assembly",groupName:null}`. O container tem `role="toolbar"` e `aria-label="Navegação do conjunto CAD"`.

- [ ] **Step 4: Write failing group-inspector tests**

```jsx
it("shows CAD facts and the physical-mapping limitation", () => {
  render(
    <TwinGroupInspector
      selectedGroup="pump"
      manifest={manifest}
      geometryMetadata={metadata}
      showCadSolids={false}
      selectedSolidNode={null}
      onSelectSolid={vi.fn()}
    />,
  );
  expect(screen.getByRole("heading", { name: "Grupo CAD da bomba" })).toBeVisible();
  expect(screen.getByText("3 sólidos CAD")).toBeVisible();
  expect(screen.getByText(/Nenhum sensor está fisicamente mapeado a este grupo/i)).toBeVisible();
  expect(screen.queryByText(/impulsor|selo|falha na bomba/i)).not.toBeInTheDocument();
});

it("labels individual solids as mechanically unvalidated", () => {
  render(<TwinGroupInspector {...props} showCadSolids />);
  expect(screen.getAllByText("Sem semântica mecânica validada")).toHaveLength(3);
});
```

- [ ] **Step 5: Run inspector tests and confirm RED**

Run:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/TwinGroupInspector.test.jsx 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*TwinGroupInspector)(?=.*(?:failed to resolve import|cannot find module|does not exist))') { throw 'twin group inspector RED did not fail for the expected missing module' }
```

Expected: FAIL porque o componente não existe.

- [ ] **Step 6: Implement the fail-closed group inspector**

Com seleção:

- heading do preset validado;
- `solidCount` e `sourceNames` exatos;
- `semanticConfidence` traduzida como “Grupo inferido pelos nomes do CAD”;
- `presentationConfidence` traduzida como “Cores e acabamento ilustrativos”;
- `sourceRule`;
- `sizeMm` como `L × A × P do envelope CAD`, seguido de “Medida geométrica; não é tolerância de fabricação”;
- mensagem fixa “Nenhum sensor está fisicamente mapeado a este grupo”.

Sem seleção, mostrar resumo do conjunto com 17 sólidos e orientar a escolher um dos quatro grupos. Se `geometryMetadata` estiver nulo por fallback, mostrar “Envelope por grupo indisponível sem a malha 3D”; não usar dimensões hardcoded da preview como bounds por grupo.

Em `showCadSolids`, renderizar uma lista de buttons com `nodeName`, source name e “Sem semântica mecânica validada”. Selecionar sólido apenas realça o node dentro do grupo já selecionado; não altera `displayContext`, sensor ou condição.

- [ ] **Step 7: Connect controls and geometry metadata to the canvas**

`Twin3DCanvas` chama `onGeometryMetadata` uma única vez por GLB/manifest carregado. `hoveredGroup`, `showDimensions` e `selectedSolidNode` entram no view model e percorrem a cadeia Task 2 somente para cursor/contorno/helper visual; nenhum deles altera condição ou causalidade. Acrescentar `data-selected-group`, `data-selected-solid`, `data-hovered-group`, `data-show-dimensions` e `data-isolated` no wrapper DOM para E2E, sem expor dados sensíveis.

- [ ] **Step 8: Add responsive control/inspector styles**

Usar grid de duas colunas `minmax(0, 1fr) minmax(18rem, 0.42fr)` acima de 980 px e uma coluna abaixo. Buttons têm target mínimo de 44 px, `:focus-visible` de alto contraste e estado selecionado por ícone/texto além de cor. A lista de sólidos fica em `<details>` fechado por padrão.

- [ ] **Step 9: Run GREEN interaction tests**

Run:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/TwinGroupControls.test.jsx src/components/twin3d/TwinGroupInspector.test.jsx src/components/twin3d/Twin3DCanvas.test.jsx
Assert-NativeSuccess 'GREEN twin group investigation tests'
```

Expected: PASS; teclado e canvas chamam o mesmo `onSelectGroup` exato.

- [ ] **Step 10: Commit CAD navigation**

```powershell
git add src/components/twin3d/TwinGroupControls.jsx src/components/twin3d/TwinGroupControls.test.jsx src/components/twin3d/TwinGroupInspector.jsx src/components/twin3d/TwinGroupInspector.test.jsx src/components/twin3d/Twin3DCanvas.jsx src/components/twin3d/Twin3DCanvas.test.jsx src/components/twin3d/twin3d.css
Assert-NativeSuccess 'stage CAD group investigation'
git diff --cached --check
Assert-NativeSuccess 'check staged CAD group investigation'
git commit -m "feat: add accessible cad group investigation"
Assert-NativeSuccess 'commit CAD group investigation'
```

---

### Task 5: Build the evidence-bounded VIM32 sensor inspector

**Files:**
- Create: `src/components/twin3d/vim32Evidence.js`
- Create: `src/components/twin3d/vim32Evidence.test.js`
- Create: `src/components/twin3d/Vim32EnvelopeDiagram.jsx`
- Create: `src/components/twin3d/Vim32EnvelopeDiagram.test.jsx`
- Create: `src/components/twin3d/TwinSensorInspector.jsx`
- Create: `src/components/twin3d/TwinSensorInspector.test.jsx`
- Modify: `src/components/twin3d/twin3d.css`

**Interfaces:**
- Consumes: `displayContext.channels.s1/s2`, `displayContext.emphasizedSensorIds` e `selectedSensor` do provider.
- Produces: `VIM32_EVIDENCE_V1`, `validateVim32Evidence(value)`.
- Produces: `Vim32EnvelopeDiagram({ evidence=VIM32_EVIDENCE_V1 })`.
- Produces: `TwinSensorInspector({ displayContext, selectedSensor, onSelectSensor })`.

- [ ] **Step 1: Write RED evidence-contract tests**

```js
it("contains only documented VIM32 facts", () => {
  const value = validateVim32Evidence(VIM32_EVIDENCE_V1);
  expect(value.model).toBe("VIM32PL-E1AC8-0RE-IO-1V1401");
  expect(value.envelope).toEqual({ lengthMm: 72.5, diameterMm: 23.8 });
  expect(value.connector).toEqual({ type: "M12", dimensions: null });
  expect(value.massApproxG).toBe(100);
  expect(value).not.toHaveProperty("threadPitch");
  expect(value).not.toHaveProperty("mountingPosition");
  expect(value).not.toHaveProperty("logo");
});

it.each(["threadPitch", "contacts", "finish", "mountingPosition"])(
  "rejects unsupported field %s",
  (field) => expect(() => validateVim32Evidence({ ...VIM32_EVIDENCE_V1, [field]: "invented" })).toThrow(field),
);
```

- [ ] **Step 2: Run evidence tests and confirm RED**

Run:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/vim32Evidence.test.js 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*vim32Evidence)(?=.*(?:failed to resolve import|cannot find module|does not exist))') { throw 'VIM32 evidence RED did not fail for the expected missing module' }
```

Expected: FAIL porque o módulo não existe.

- [ ] **Step 3: Implement the closed sensor evidence object**

Campos normativos:

```js
export const VIM32_EVIDENCE_V1 = Object.freeze({
  schemaVersion: "1.0",
  manufacturer: "Pepperl+Fuchs",
  model: "VIM32PL-E1AC8-0RE-IO-1V1401",
  interface: "IO-Link 1.1",
  envelope: Object.freeze({ lengthMm: 72.5, diameterMm: 23.8 }),
  connector: Object.freeze({ type: "M12", dimensions: null }),
  massApproxG: 100,
  ranges: Object.freeze({
    vibrationVelocityRms: Object.freeze({ min: 0, max: 128, unit: "mm/s" }),
    vibrationAcceleration: Object.freeze({ min: 0, max: 10, unit: "g" }),
    temperature: Object.freeze({ min: -40, max: 85, unit: "degC" }),
    measuredFrequency: Object.freeze({ min: 10, max: 1000, unit: "Hz" }),
  }),
  internalSamplingHz: 8000,
  rmsAveragingSeconds: 2,
});
```

O contrato não contém `technology`: a tecnologia interna do sensor não faz parte da evidência aprovada e permanece não validada até entrar documentação rastreável no Git.

O validador usa allowlist fechada e números finitos; `connector.dimensions` deve permanecer `null`.

- [ ] **Step 4: Write RED diagram tests**

```jsx
it("renders the documented envelope and refuses connector dimensions", () => {
  render(<Vim32EnvelopeDiagram />);
  expect(screen.getByRole("img", { name: /Envelope dimensional do sensor VIM32/i })).toBeVisible();
  expect(screen.getByText("72,5 mm")).toBeVisible();
  expect(screen.getByText("Ø 23,8 mm")).toBeVisible();
  expect(screen.getByText("Conector M12 — dimensões não fornecidas")).toBeVisible();
  expect(screen.queryByText(/passo de rosca|contatos internos/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 5: Implement an accessible proportional envelope diagram**

Usar SVG local com `viewBox="0 0 174 72"`. O corpo cilíndrico projetado terá largura 145 e altura 47.6, preservando a razão `72.5 / 23.8`; linhas de cota ficam fora do corpo. Não desenhar pinos, rosca, logotipo ou forma dimensional do conector. Indicar o M12 apenas por texto e uma área tracejada “volume do conector não cotado”, sem escala declarada.

O `<title>` e `<desc>` devem declarar que é envelope dimensional, não réplica visual.

- [ ] **Step 6: Write RED inspector tests for now, historical and gap**

```jsx
import { DISPLAY_CONTEXT_V1_FIXTURES } from "../../displayContext/displayContextV1.fixtures.js";
import { assertForzyTwinDisplayContext } from "./twinViewModel.js";

const historicalDisplayContext = assertForzyTwinDisplayContext(
  structuredClone(DISPLAY_CONTEXT_V1_FIXTURES.historicalAlert),
);
const zeroDisplayContext = assertForzyTwinDisplayContext(
  structuredClone(DISPLAY_CONTEXT_V1_FIXTURES.nowZero),
);
const gapDisplayContext = assertForzyTwinDisplayContext(
  structuredClone(DISPLAY_CONTEXT_V1_FIXTURES.historicalGap),
);

it("uses historical channels even when a conflicting live snapshot exists elsewhere", () => {
  render(
    <TwinSensorInspector
      displayContext={historicalDisplayContext}
      selectedSensor="s1"
      onSelectSensor={vi.fn()}
    />,
  );
  expect(screen.getByText("9,25")).toBeVisible();
  expect(screen.getByText("Histórico Forzy — CSV")).toBeVisible();
  expect(screen.getByText(/Posição de S1\/S2 no conjunto ainda não validada/i)).toBeVisible();
});

it("keeps zero distinct from unavailable", () => {
  render(<TwinSensorInspector displayContext={zeroDisplayContext} selectedSensor="all" onSelectSensor={vi.fn()} />);
  expect(screen.getByText("0,00")).toBeVisible();
  expect(screen.getAllByText("Indisponível").length).toBeGreaterThan(0);
});

it("does not carry a channel across a gap", () => {
  render(<TwinSensorInspector displayContext={gapDisplayContext} selectedSensor="all" onSelectSensor={vi.fn()} />);
  expect(screen.getByTestId("twin-sensor-inspector")).toHaveAttribute("data-context-neutral", "true");
  expect(screen.getByTestId("sensor-rail-s1")).toHaveAttribute("data-channel-available", "false");
  expect(screen.getByTestId("sensor-rail-s2")).toHaveAttribute("data-channel-available", "false");
  expect(screen.queryByTestId("physical-sensor-anchor")).not.toBeInTheDocument();
});
```

- [ ] **Step 7: Implement sensor rails and the inspector dock**

Regras:

- tabs HTML `Todos`, `S1` e `S2`, com `aria-selected` e arrow-key navigation;
- cada rail mostra sensor, estado de ênfase textual, `eventAt`, `sourceKind`, `provenance.sourceSystem`, timestamp quality e flags;
- as três medições mostram valor, unidade e confiança semântica; null mostra `Indisponível`, zero mostra `0,00`;
- `historical_archive` vira “Histórico Forzy — CSV”; `live_collection` vira “Coleta recente — API Forzy”; valores desconhecidos falham em “Origem indisponível”;
- highlight de rail depende exclusivamente de `displayContext.emphasizedSensorIds` e nunca destaca geometria do conjunto;
- `TwinSensorInspector` chama `assertForzyTwinDisplayContext` antes de ler canais; para gap, expõe somente neutralidade e indisponibilidade estrutural nos atributos testáveis acima. O resumo/copy canônico do gap pertence exclusivamente ao ruleset e componentes da Fase C;
- o dock sempre exibe o diagrama e a mensagem canônica:

> Representação dimensional do modelo de sensor. Posição de S1/S2 no conjunto ainda não validada.

- não renderizar `assessment.recommendation` nem texto livre de ação.

- [ ] **Step 8: Add responsive and non-color-only sensor styles**

Rails usam ícone, texto e border pattern além de cor. O dock cabe em uma coluna a 390 px, mantém tabela de medições legível e tem foco visível. `watch`/`alert` usam texto “Evidência associada ao contexto” e nunca “Alerta no motor/bomba”.

- [ ] **Step 9: Run GREEN sensor tests**

Run:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/twin3d/vim32Evidence.test.js src/components/twin3d/Vim32EnvelopeDiagram.test.jsx src/components/twin3d/TwinSensorInspector.test.jsx
Assert-NativeSuccess 'GREEN VIM32 inspector tests'
```

Expected: PASS; nenhum teste depende de WebGL ou asset externo.

- [ ] **Step 10: Commit the sensor inspector**

```powershell
git add src/components/twin3d/vim32Evidence.js src/components/twin3d/vim32Evidence.test.js src/components/twin3d/Vim32EnvelopeDiagram.jsx src/components/twin3d/Vim32EnvelopeDiagram.test.jsx src/components/twin3d/TwinSensorInspector.jsx src/components/twin3d/TwinSensorInspector.test.jsx src/components/twin3d/twin3d.css
Assert-NativeSuccess 'stage VIM32 evidence inspector'
git diff --cached --check
Assert-NativeSuccess 'check staged VIM32 evidence inspector'
git commit -m "feat: add traceable vim32 sensor inspector"
Assert-NativeSuccess 'commit VIM32 evidence inspector'
```

---

### Task 6: Make the twin shell and fallback preserve the engineering context

**Files:**
- Modify: `src/components/Twin3D.jsx`
- Modify: `src/components/Twin3D.test.jsx`
- Modify: `src/components/twin3d/Twin3DCanvas.jsx`
- Modify: `src/components/twin3d/Twin3DCanvas.test.jsx`
- Modify: `src/components/twin3d/twin3d.css`

**Interfaces:**
- Consumes: all Task 1–5 components, `assertForzyTwinDisplayContext`, complete C1 fixtures in tests and provider-owned selection callbacks.
- Produces: `Twin3D({ displayContext, selectedGroup, onSelectGroup, selectedSensor, onSelectSensor })`.
- Produces: `Twin3DStaticFallback({ displayContext })`.
- Preserves: `createTwin3DComponent(loadCanvas)` injection seam for tests and lazy loading.

- [ ] **Step 1: Write RED shell tests for data-preserving fallbacks**

```jsx
const historicalAlertContext = assertForzyTwinDisplayContext(
  structuredClone(DISPLAY_CONTEXT_V1_FIXTURES.historicalAlert),
);

it("keeps controls and historical sensor facts in the WebGL fallback", async () => {
  HTMLCanvasElement.prototype.getContext.mockReturnValue(null);
  render(
    <Twin3D
      displayContext={historicalAlertContext}
      selectedGroup="pump"
      onSelectGroup={vi.fn()}
      selectedSensor="s1"
      onSelectSensor={vi.fn()}
    />,
  );
  expect(screen.getByTestId("twin3d-static-fallback")).toHaveAttribute("data-twin-fallback", "true");
  expect(screen.getByText("Visualização 3D indisponível")).toBeVisible();
  expect(screen.getByRole("toolbar", { name: "Navegação do conjunto CAD" })).toBeVisible();
  expect(screen.getByText("9,25")).toBeVisible();
  expect(screen.getByText(/Histórico Forzy/i)).toBeVisible();
});

it("rejects a malformed or cross-asset public context before child props", () => {
  const loadCanvas = vi.fn(() => Promise.resolve({ default: () => <div data-testid="loaded-canvas" /> }));
  const TestTwin = createTwin3DComponent(loadCanvas);
  const selectionProps = {
    selectedGroup: null, onSelectGroup: vi.fn(), selectedSensor: "all", onSelectSensor: vi.fn(),
  };
  const incomplete = structuredClone(historicalAlertContext);
  delete incomplete.capabilities;
  const crossAsset = structuredClone(historicalAlertContext);
  crossAsset.asset = { assetId: "other-asset" };
  expect(() => render(<TestTwin displayContext={incomplete} {...selectionProps} />))
    .toThrow(/displayContext\.capabilities/);
  expect(() => render(<TestTwin displayContext={crossAsset} {...selectionProps} />))
    .toThrow(/forzy-motor-01/);
  expect(loadCanvas).not.toHaveBeenCalled();
});
```

Adicionar casos para lazy chunk rejection, manifest rejection e GLB rejection. O warning deve ocorrer uma vez e ser sanitizado.

- [ ] **Step 2: Write RED viewport-boundary isolation tests**

```jsx
it("replaces only the viewport after a lazy chunk rejection", async () => {
  const TestTwin = createTwin3DComponent(() => Promise.reject(new Error("chunk unavailable")));
  render(
    <TestTwin
      displayContext={historicalAlertContext}
      selectedGroup="pump"
      onSelectGroup={vi.fn()}
      selectedSensor="s1"
      onSelectSensor={vi.fn()}
    />,
  );
  expect(await screen.findByText("Visualização 3D indisponível")).toBeVisible();
  expect(screen.getByRole("button", { name: "Selecionar grupo CAD da bomba" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("tab", { name: "S1" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("9,25")).toBeVisible();
});
```

Repetir a mesma fronteira para erro do manifesto e do GLB: somente `.twin-viewport` muda; toolbar, inspetores e contexto permanecem montados.

- [ ] **Step 3: Run shell tests and confirm RED**

Run:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/Twin3D.test.jsx 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*Twin3D)(?=.*(?:assertionerror|expected|received|typeerror|referenceerror|unable to find|tohaveattribute|tobevisible))') { throw 'twin fallback RED did not fail for the expected shell mismatch' }
```

Expected: FAIL porque o shell baseline aceita somente o snapshot antigo/fallback e retorna cedo sem controls/inspector.

- [ ] **Step 4: Restructure the shell around a viewport-only boundary**

No início do componente retornado por `createTwin3DComponent`, executar `const canonicalDisplayContext = assertForzyTwinDisplayContext(displayContext)`. Somente essa referência validada pode chegar a `buildTwinViewModel`, atributos DOM, fallback, controls, inspector ou lazy canvas. O asset binding acontece antes de `loadCanvas`; contexto inválido/cross-asset não monta filhos nem é reparado com outra prop.

Estrutura:

```jsx
<section
  className="twin-engineering-shell"
  data-view-mode={canonicalDisplayContext.viewMode}
  data-decision-as-of={canonicalDisplayContext.decisionAsOf}
  data-condition-state={canonicalDisplayContext.conditionState}
>
  <TwinGroupControls {...controlProps} />
  <div className="twin-engineering-layout">
    <Twin3DErrorBoundary fallback={fallbackView} resetSignal={assetResetSignal}>
      {viewport}
    </Twin3DErrorBoundary>
    <TwinGroupInspector {...groupInspectorProps} />
  </div>
  <TwinSensorInspector {...sensorInspectorProps} />
</section>
```

Somente `viewport` muda para fallback. `assetResetSignal` usa apenas `canonicalDisplayContext.asset.assetId`; refresh live ou mudança de `decisionAsOf` não remonta o boundary. Recuperação transitória ocorre por um botão HTML explícito “Tentar carregar o 3D novamente”, que incrementa um contador local de tentativa sem alterar o contexto operacional.

`Twin3D.jsx` importa `./twin3d/twin3d.css`, mas não importa `three`, `@react-three/fiber` nem `@react-three/drei`; todos os componentes HTML seguem a mesma regra. Somente o módulo lazy `Twin3DCanvas.jsx` importa runtime 3D. `src/styles.css` não é editado nem staged pela Fase D.

- [ ] **Step 5: Implement the single context-aware static fallback**

`Twin3DStaticFallback` é criado apenas dentro de `Twin3D.jsx`, recebe a mesma referência `canonicalDisplayContext` e usa `/models/conjunto-motor-bomba-preview.png`, que a Task 8 regenerará e versionará. A raiz tem `data-testid="twin3d-static-fallback"` e `data-twin-fallback="true"`. Sobre/abaixo da imagem, mostrar:

- “Visualização 3D indisponível”;
- `viewMode` e `decisionAsOf` do `displayContext`;
- `conditionState`, escopo e `conditionAsOf` em texto seguro;
- “Prévia derivada do mesmo STEP; materiais da experiência interativa são ilustrativos”;
- ausência de seleção por imagem, mantendo a lista HTML como caminho de navegação.

Não desenhar sensor sobre a PNG e não sobrepor hotspot fictício.

Remover o prop público `fallback` e qualquer branch que aceite JSX injetado. O integrador C/E apenas monta `<Twin3D ... />`; WebGL, lazy chunk, manifesto e GLB convergem para esta mesma implementação interna.

- [ ] **Step 6: Pass every public prop through the lazy seam**

O lazy canvas recebe somente:

```js
{
  displayContext: canonicalDisplayContext,
  selectedGroup,
  onSelectGroup,
  hoveredGroup,
  onHoverGroup,
  isolateSelected,
  showCadSolids,
  showDimensions,
  selectedSolidNode,
  cameraRequest,
  onGeometryMetadata,
}
```

Não aceitar nem passar snapshot live, histórico paralelo ou avaliação fora de `displayContext` ao canvas.

- [ ] **Step 7: Preserve reduced-motion behavior**

Usar `matchMedia("(prefers-reduced-motion: reduce)")` para enviar `reducedMotion`. O modelo continua carregado; `Bounds.maxDuration` vira `0.01`; não criar pulse, rotação automática ou vibração.

- [ ] **Step 8: Run GREEN shell/canvas regressions**

Run:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/Twin3D.test.jsx src/components/twin3d
Assert-NativeSuccess 'GREEN twin fallback tests'
```

Expected: PASS para WebGL, chunk, manifest, GLB, preservação do contexto e reduced motion.

- [ ] **Step 9: Commit the resilient shell**

```powershell
git add src/components/Twin3D.jsx src/components/Twin3D.test.jsx src/components/twin3d/Twin3DCanvas.jsx src/components/twin3d/Twin3DCanvas.test.jsx src/components/twin3d/twin3d.css
Assert-NativeSuccess 'stage twin fallback context'
git diff --cached --check
Assert-NativeSuccess 'check staged twin fallback context'
git commit -m "feat: preserve engineering context in twin fallbacks"
Assert-NativeSuccess 'commit twin fallback context'
```

### Task 7: Lock the public twin seam without owning dashboard state

**Files:**

- Modify: `src/components/Twin3D.jsx`
- Modify: `src/components/Twin3D.test.jsx`

**Interface under test:**

```jsx
<Twin3D
  displayContext={displayContext}
  selectedGroup={selectedGroup}
  onSelectGroup={onSelectGroup}
  selectedSensor={selectedSensor}
  onSelectSensor={onSelectSensor}
/>
```

The Phase C integrator owns `OperationsDashboard.jsx`, `App.jsx`, their tests and `src/styles.css`. Phase D publishes and tests this prop contract only in `Twin3D.jsx`/`Twin3D.test.jsx`; it must not create provider state, import `useTwinOps`, accept a legacy fallback prop or edit dashboard wiring.

- [ ] **Step 1: Add a failing canonical-name contract test**

Render the public component with the complete historical C1 fixture. Validate it before render; do not derive it by spreading a live snapshot, another asset or a partial D-owned object:

```jsx
const historical = assertForzyTwinDisplayContext(
  structuredClone(DISPLAY_CONTEXT_V1_FIXTURES.historicalAlert),
);
expect(historical.asset.assetId).toBe("forzy-motor-01");

render(
  <Twin3D
    displayContext={historical}
    selectedGroup="pump"
    onSelectGroup={vi.fn()}
    selectedSensor="s1"
    onSelectSensor={vi.fn()}
  />,
);

expect(screen.getByTestId("twin3d-root")).toHaveAttribute("data-view-mode", "historical");
expect(screen.getByTestId("twin3d-root")).toHaveAttribute("data-decision-as-of", historical.decisionAsOf);
expect(screen.getByTestId("twin3d-root")).toHaveAttribute("data-condition-state", "alert");
```

Pass an independently constructed extra `snapshot={conflictingCrossAssetLiveSnapshot}` only as an adversarial test prop, with `assetId="other-asset"`, current/normal values and a later timestamp. Ele nunca serve de base para construir `historical`. Assert the root and sensor rail still show only the complete validated historical context, the lazy canvas never receives a `snapshot` key, S1 is emphasized and Pump remains selected. Search the rendered DOM for `data-physical-sensor-anchor`; it must not exist.

- [ ] **Step 2: Run RED**

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/Twin3D.test.jsx 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*Twin3D)(?=.*(?:assertionerror|expected|received|typeerror|referenceerror|unable to find|tohaveattribute|tobevisible))') { throw 'public twin seam RED did not fail for the expected contract mismatch' }
```

Expected: FAIL until the Task 6 shell exposes the canonical root attributes and preserves the exact context fields through its public seam.

- [ ] **Step 3: Complete the seam only inside Phase D files**

Modify only `Twin3D.jsx`: destructure exactly the five public props shown above, call `assertForzyTwinDisplayContext(displayContext)` before creating view model, fallback or child props, and pass the returned original reference unchanged. Ignore extra React props; never use them to repair/substitute `displayContext`. Do not patch `OperationsDashboard`, `App`, `TwinOpsContext` or the provider. The root reads `viewMode`, `decisionAsOf`, `conditionState`, `conditionTemporalScope`, `conditionAsOf`, collection/data dimensions and `emphasizedSensorIds`; obsolete aliases, contexto parcial, asset diferente ou um decision object embutido são inválidos.

- [ ] **Step 4: Add rerender stability**

Rerender with a newer adversarial cross-asset live snapshot prop while retaining the same historical `displayContext`. Para `T1 -> T2`, clone somente a mesma fixture C1 historical de `forzy-motor-01`, altere o `decisionAsOf` para um UTC-millisecond posterior que preserve as invariantes temporais e passe novamente por `assertForzyTwinDisplayContext`; não espalhe o snapshot adversarial. Assert the same canvas/model DOM node remains connected, the manifest/GLB loaders retain one call each, Pump/S1 remain selected, canonical root attributes update only on the second context rerender and no loading state remounts.

- [ ] **Step 5: Run GREEN**

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/components/Twin3D.test.jsx src/components/twin3d
Assert-NativeSuccess 'GREEN public twin seam tests'
```

Expected: PASS with canonical names, no split-brain data, no reload and no physical sensor anchor.

- [ ] **Step 6: Commit the contract lock**

```powershell
git add src/components/Twin3D.jsx src/components/Twin3D.test.jsx
Assert-NativeSuccess 'stage public twin seam'
git diff --cached --check
Assert-NativeSuccess 'check staged public twin seam'
git commit -m "test: lock engineering twin display context seam"
Assert-NativeSuccess 'commit public twin seam'
$d7PublicSeamCommit = (git rev-parse HEAD).Trim()
Assert-NativeSuccess 'read D7 public seam SHA'
$env:D7_PUBLIC_SEAM_COMMIT = $d7PublicSeamCommit
```

Entregar `$d7PublicSeamCommit` à Fase C. Não iniciar D8 ainda: C Task 11 deve integrar exatamente esse seam, executar seus testes e devolver `$c11DashboardIntegrationCommit`.

### Task 8: Automate asset, lazy-load, performance, E2E and visual gates

**Dependency gate (D7 → C11 → D8):** receber os dois SHAs de código e `C11_HANDOFF_EVIDENCE_COMMIT`, autenticar os blobs do handoff/review, provar que D7 é ancestral de C11 e que o evidence commit é ancestral do HEAD atual. Confirmar também o config E1. Ausência, SHA inválido, blob/escopo divergente ou ancestry falha interrompe a Task 8 sem criar fixture, PNG ou relatório:

```powershell
function Assert-NativeSuccess([string]$label) {
  if ($LASTEXITCODE -ne 0) { throw "$label failed with exit code $LASTEXITCODE" }
}
$d7PublicSeamCommit = $env:D7_PUBLIC_SEAM_COMMIT
$c11DashboardIntegrationCommit = $env:C11_DASHBOARD_INTEGRATION_COMMIT
$c11HandoffEvidenceCommit = $env:C11_HANDOFF_EVIDENCE_COMMIT
if ($d7PublicSeamCommit -notmatch '^[0-9a-f]{40}$' -or $c11DashboardIntegrationCommit -notmatch '^[0-9a-f]{40}$' -or $c11HandoffEvidenceCommit -notmatch '^[0-9a-f]{40}$') { throw 'D7, C11 reviewed and C11 evidence commits are required' }
git merge-base --is-ancestor $d7PublicSeamCommit $c11DashboardIntegrationCommit
Assert-NativeSuccess 'D7 to C11 ancestry'
git merge-base --is-ancestor $c11DashboardIntegrationCommit $c11HandoffEvidenceCommit
Assert-NativeSuccess 'C11 evidence ancestry'
git merge-base --is-ancestor $c11HandoffEvidenceCommit HEAD
Assert-NativeSuccess 'C11 evidence integration'
$actualC11EvidencePaths = @(git diff --name-only "$c11DashboardIntegrationCommit..$c11HandoffEvidenceCommit")
Assert-NativeSuccess 'C11 evidence scope read'
$expectedC11EvidencePaths = @(
  'docs/verification/checkpoints/c11-dashboard-integration-handoff.json',
  'docs/verification/phase-c-findings.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
)
if (Compare-Object ($expectedC11EvidencePaths | Sort-Object) ($actualC11EvidencePaths | Sort-Object) -CaseSensitive -SyncWindow 0) { throw 'C11 evidence commit scope mismatch' }
$phaseCheckpointValidator = @'
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const [evidence, code, handoffPath, checkpoint, consumer, expectedEnvironmentCsv, d7] = process.argv.slice(1);
const show = (path) => execFileSync('git', ['show', evidence + ':' + path]);
const handoff = JSON.parse(show(handoffPath).toString('utf8'));
const exact = ['baseCommit','checkpoint','consumerTask','environment','producerPlan','reviewedCodeCommit','reviewReport','reviewReportSha256','schemaVersion','verdict'];
const reportBytes = show(handoff.reviewReport);
const report = JSON.parse(reportBytes.toString('utf8'));
const digest = crypto.createHash('sha256').update(reportBytes).digest('hex');
const environmentKeys = Object.keys(handoff.environment || {}).sort();
const fail = Object.keys(handoff).sort().join('|') !== exact.sort().join('|') || environmentKeys.join('|') !== expectedEnvironmentCsv.split(',').sort().join('|') || Object.keys(handoff.verdict || {}).sort().join('|') !== 'critical|important|minor' || handoff.schemaVersion !== 'phase-checkpoint-handoff-v1' || handoff.checkpoint !== checkpoint || handoff.producerPlan !== 'C' || handoff.consumerTask !== consumer || !/^[0-9a-f]{40}$/.test(handoff.baseCommit) || handoff.reviewedCodeCommit !== code || handoff.reviewReport !== 'docs/verification/phase-c-findings.json' || handoff.reviewReportSha256 !== digest || report.schemaVersion !== 'finding-review-v1' || report.plan !== 'C' || report.reviewedSha !== code || report.verdict.critical !== 0 || report.verdict.important !== 0 || handoff.verdict.critical !== report.verdict.critical || handoff.verdict.important !== report.verdict.important || handoff.verdict.minor !== report.verdict.minor || handoff.environment.D7_PUBLIC_SEAM_COMMIT !== d7 || handoff.environment.C11_DASHBOARD_INTEGRATION_COMMIT !== code;
if (fail) process.exit(1);
execFileSync('git', ['merge-base','--is-ancestor', handoff.baseCommit, code]);
'@
node -e $phaseCheckpointValidator $c11HandoffEvidenceCommit $c11DashboardIntegrationCommit 'docs/verification/checkpoints/c11-dashboard-integration-handoff.json' 'C11' 'D8' 'C11_DASHBOARD_INTEGRATION_COMMIT,D7_PUBLIC_SEAM_COMMIT' $d7PublicSeamCommit
Assert-NativeSuccess 'C11 handoff blob validation'
$rawC11Handoff = @(git show "$c11HandoffEvidenceCommit`:docs/verification/checkpoints/c11-dashboard-integration-handoff.json")
Assert-NativeSuccess 'read C11 handoff blob'
$c11Handoff = (($rawC11Handoff -join "`n") | ConvertFrom-Json)
$expectedC11CodePaths = @(
  'src/App.jsx',
  'src/App.test.jsx',
  'src/components/operations/IntegrationHealth.jsx',
  'src/components/operations/OperationsDashboard.jsx',
  'src/components/operations/TelemetryTrend.jsx',
  'src/styles.css'
)
$actualC11CodePaths = @(git diff --name-only $c11Handoff.baseCommit $c11DashboardIntegrationCommit)
Assert-NativeSuccess 'read C11 code scope'
if (Compare-Object ($expectedC11CodePaths | Sort-Object) ($actualC11CodePaths | Sort-Object) -CaseSensitive -SyncWindow 0) { throw 'C11 code scope mismatch' }
git diff --check $c11Handoff.baseCommit $c11DashboardIntegrationCommit
Assert-NativeSuccess 'C11 code diff hygiene'
if (-not (Test-Path -LiteralPath 'playwright.twin.config.js' -PathType Leaf)) { throw 'E1 playwright.twin.config.js is required' }
$phaseD8StartCommit = (git rev-parse HEAD).Trim()
Assert-NativeSuccess 'read Phase D8 start SHA'
if ($phaseD8StartCommit -cne $c11HandoffEvidenceCommit) { throw 'D8 must start at the authenticated C11 evidence commit' }
$unexpectedD8StartStatus = @(git status --porcelain=v1)
Assert-NativeSuccess 'read D8 start status'
if ($unexpectedD8StartStatus.Count -ne 0) { throw 'D8 requires a clean worktree at the authenticated boundary' }
$env:PHASE_D8_START_COMMIT = $phaseD8StartCommit
$env:D7_PUBLIC_SEAM_COMMIT = $d7PublicSeamCommit
```

**Files:**

- Create: `scripts/twin3d/check-interactive-twin-assets.mjs`
- Create: `scripts/twin3d/check-interactive-twin-assets.test.mjs`
- Create: `scripts/twin3d/check-lazy-twin-build.mjs`
- Create: `scripts/twin3d/check-lazy-twin-build.test.mjs`
- Create: `scripts/twin3d/check-twin-production-claims.mjs`
- Create: `scripts/twin3d/check-twin-production-claims.test.mjs`
- Create: `scripts/twin3d/render-interactive-twin-preview.mjs`
- Create: `scripts/twin3d/render-interactive-twin-preview.test.mjs`
- Create: `scripts/twin3d/with-local-twin-server.mjs`
- Create: `scripts/twin3d/with-local-twin-server.test.mjs`
- Create: `scripts/twin3d/profile-interactive-twin.mjs`
- Create: `scripts/twin3d/profile-interactive-twin.test.mjs`
- Create: `tests/e2e/fixtures/interactive-twin.js`
- Create: `tests/e2e/interactive-twin.spec.js`
- Modify: `src/components/twin3d/Twin3DCanvas.jsx`
- Modify: `src/components/twin3d/Twin3DCanvas.test.jsx`
- Modify: `src/components/twin3d/TwinCameraRig.jsx`
- Modify: `src/components/twin3d/TwinCameraRig.test.jsx`
- Modify: `public/models/conjunto-motor-bomba-preview.png`
- Modify: `vitest.config.js`
- Modify: `package.json`
- Reuse unchanged: `playwright.twin.config.js` (owned by E1)
- Create after a real render: `artifacts/twin3d/preview-render-report.json`
- Create after a real run: `artifacts/twin3d/performance-profile.json`
- Create after the production scan: `artifacts/twin3d/production-claims-report.json`

**Command interfaces:**

```text
node scripts/twin3d/check-interactive-twin-assets.mjs [--report <json-path>]
node scripts/twin3d/check-lazy-twin-build.mjs <vite-manifest-path> <dist-root> [--report <json-path>]
node scripts/twin3d/check-twin-production-claims.mjs <dist-root> [--report <json-path>]
node scripts/twin3d/render-interactive-twin-preview.mjs --url <local-url> --output <png-path> --report <json-path>
node scripts/twin3d/profile-interactive-twin.mjs --url <local-url> --output <json-path>
node scripts/twin3d/with-local-twin-server.mjs --action render-preview
node scripts/twin3d/with-local-twin-server.mjs --action profile
```

Todos retornam exit code `0` somente com gate aprovado e `1` para violação contratual. Relatórios incluem `schemaVersion`, `generatedAt`, `baseCommit`, `phaseDStartCommit`, `d7PublicSeamCommit`, `phaseD8StartCommit` e os valores efetivamente observados; nunca incluem resultado inventado. O profiler inclui adicionalmente `verifiedCodeCommit`, resolvido com `git rev-parse HEAD` no início de cada processo. Uma execução preliminar com mudanças D8 ainda não commitadas pode servir ao RED/GREEN local, mas não é evidência final; a Task 9 obrigatoriamente a sobrescreve em árvore limpa após congelar o commit de código e exige igualdade exata. O preview report é deliberadamente pré-commit: ele não se apresenta como revisado e sua prova final é `previewSha256 == SHA-256(git show $verifiedCodeCommit:public/models/conjunto-motor-bomba-preview.png)`. `baseCommit` prova lineage global; os três checkpoints delimitam os dois intervalos de ownership D sem absorver o intervalo C11.

- [ ] **Step 1: Write RED asset-integrity tests**

Criar fixtures temporárias dentro do próprio runner para cobrir:

- hash correto versus GLB alterado;
- PNG cujo hash coincide com `preview-render-report.json` versus PNG alterada após a renderização;
- `manifest.nodes` com 17 itens versus remoção, duplicação e renomeação;
- contagens exatas `{motor:7,pump:3,coupling:5,base:2}`;
- source hash exato versus drift;
- presença de URI externa em GLB/manifest versus assets apenas locais.

O teste não edita `public/models` nem `artifacts/twin3d/conversion-report.json`; suas cópias mutáveis vivem no diretório temporário do teste.

- [ ] **Step 2: Run the asset checker test and confirm RED**

Run:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" scripts/twin3d/check-interactive-twin-assets.test.mjs 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*check-interactive-twin-assets)(?=.*(?:failed to resolve import|cannot find module|does not exist))') { throw 'interactive twin asset checker RED did not fail for the expected missing module' }
```

Expected: FAIL porque o verificador ainda não existe.

- [ ] **Step 3: Implement the immutable-source and rendered-preview gate**

O verificador calcula SHA-256 do GLB e da PNG, lê o source hash já versionado, valida igualdade exata dos nomes/grupos do manifesto e rejeita `http:`, `https:` e protocol-relative URLs. GLB/source são comparados aos hashes congelados. A PNG é comparada ao hash observado em `artifacts/twin3d/preview-render-report.json`, que também precisa referenciar o hash congelado do GLB; o hash baseline antigo nunca é imposto ao output novo. Não reserializa nenhum asset.

Run:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" scripts/twin3d/check-interactive-twin-assets.test.mjs
Assert-NativeSuccess 'GREEN interactive twin asset checker tests'
```

Expected: PASS das fixtures. O gate contra os assets reais roda na Step 8, depois que a nova preview e seu relatório existirem.

- [ ] **Step 4: Write RED build-manifest tests for the lazy boundary**

Fixtures mínimas de manifest Vite devem provar:

- entrada do app não importa `three`, `@react-three/fiber`, `@react-three/drei` nem o chunk do canvas de forma estática;
- existe chunk dinâmico alcançável para `src/components/twin3d/Twin3DCanvas.jsx`;
- o chunk dinâmico contém as dependências 3D;
- nenhum JS/CSS/manifest emitido referencia asset visual externo;
- manifesto ausente, chunk ausente e import estático indevido falham com mensagem determinística.

- [ ] **Step 5: Run the lazy-build test RED, implement, then run GREEN against a real build**

Run RED:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" scripts/twin3d/check-lazy-twin-build.test.mjs 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*check-lazy-twin-build)(?=.*(?:failed to resolve import|cannot find module|does not exist))') { throw 'lazy twin build RED did not fail for the expected missing module' }
```

Implementar o leitor do manifest e adicionar em `package.json`:

```js
{
  "scripts": {
    "build:manifest": "vite build --manifest",
    "check:twin-assets": "node scripts/twin3d/check-interactive-twin-assets.mjs --preview-report artifacts/twin3d/preview-render-report.json",
    "check:twin-lazy": "node scripts/twin3d/check-lazy-twin-build.mjs dist/.vite/manifest.json dist",
    "check:twin-claims": "node scripts/twin3d/check-twin-production-claims.mjs dist",
    "render:twin-preview": "node scripts/twin3d/render-interactive-twin-preview.mjs --url http://127.0.0.1:4173 --output public/models/conjunto-motor-bomba-preview.png --report artifacts/twin3d/preview-render-report.json",
    "test:e2e:twin": "playwright test --config=playwright.twin.config.js tests/e2e/interactive-twin.spec.js"
  }
}
```

Em `vitest.config.js`, acrescentar `"**/.pytest_cache/**"` à lista `test.exclude`; preservar os excludes existentes. O teste completo deve ignorar qualquer arquivo JavaScript coletado por caches Python.

O script `test:e2e:twin` usa explicitamente o `playwright.twin.config.js` entregue por E1. D não edita esse config, não adiciona backend ao `webServer`, não define `channel`/`executablePath` e não cai para Chrome do sistema. Se o Chromium bundled pinado estiver ausente, parar e solicitar autorização para a instalação Playwright prevista por E1.

Run GREEN:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" scripts/twin3d/check-lazy-twin-build.test.mjs
Assert-NativeSuccess 'GREEN lazy twin build tests'
npm.cmd run build:manifest
Assert-NativeSuccess 'lazy twin manifest build'
npm.cmd run check:twin-lazy
Assert-NativeSuccess 'lazy twin bundle gate'
```

Expected: PASS; Three permanece fora do entry chunk e o canvas é carregável por import dinâmico.

- [ ] **Step 6: Write RED unit tests for the performance gate math**

Exportar funções puras:

```js
export function summarizePerformanceRuns(runs) {}
export function fpsFromRafTimestamps(timestamps) {}
export function assertPerformanceGate(summary, limits = {
  minimumEveryRunFps: 30,
  maximumWorstLongTaskMs: 200,
}) {}
```

Fixtures cobrem timestamps rAF conhecidos, deltas consecutivos, mediana ímpar/par, timestamps não crescentes, três runs, FPS mínimo exatamente `30`, FPS `29.99`, long task exatamente `200 ms`, long task `200.01 ms`, run ausente e métricas não finitas. `fpsFromRafTimestamps` calcula exclusivamente `1000 / median(diff(timestamps))`; não aceita contagem de eventos `useFrame` nem `frames/duration` como substituto. O resumo expõe `minimumRunFps = Math.min(...runs.map(run => run.fps))` e o pior long task observado; a mediana entre runs pode ser informativa, nunca decisória. Incluir obrigatoriamente:

```js
expect(() => assertPerformanceGate(summarizePerformanceRuns([
  { fps: 15, worstLongTaskMs: 20 },
  { fps: 60, worstLongTaskMs: 20 },
  { fps: 60, worstLongTaskMs: 20 },
]))).toThrow(/minimum run fps/i);
```

Run:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" scripts/twin3d/profile-interactive-twin.test.mjs 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*profile-interactive-twin)(?=.*(?:failed to resolve import|cannot find module|does not exist))') { throw 'interactive twin profiler RED did not fail for the expected missing module' }
```

Expected: FAIL antes da implementação; PASS depois.

- [ ] **Step 7: Implement the reproducible browser profiler**

Primeiro, tornar a invalidação do renderer observável e determinística. `Twin3DCanvas` usa `frameloop="demand"`, chama `invalidate()` em mudança de view model, helper dimensional, sólido, hover, isolamento e câmera, e liga `OrbitControls.onChange` a `invalidate`. `TwinCameraRig` invalida cada passo de uma transição ativa e encerra ao atingir o alvo; com reduced motion há exatamente uma invalidação. Testes com `invalidate=vi.fn()` cobrem cada causa, nenhum rerender ocioso e cleanup do listener de controles.

O profiler importa `installInteractiveTwinFixture`, instala o backend same-origin determinístico `now-normal` antes de navegar e abre o `chromium` exportado pela mesma dependência Playwright pinada usada em `playwright.twin.config.js`, em `1366x768`, device scale factor `1`; `channel`, `executablePath` e navegador do sistema são proibidos. Em cada run cria uma página nova, espera `[data-model-ready="true"]` e `[data-rendered-node-count="17"]`, restaura a vista e executa a mesma órbita Playwright: pointer down no mesmo ponto, 120 movimentos lineares pelos mesmos pontos normalizados durante `8 s`, pointer up, foco em Pump e restauração do conjunto. A medição dura `10 s` após aquecimento de `3 s` e repete exatamente três vezes.

Reexecutar GREEN antes de criar fixtures/render:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" scripts/twin3d/profile-interactive-twin.test.mjs
Assert-NativeSuccess 'interactive twin profiler GREEN tests'
```

Durante cada janela de 10 s, o contexto da página agenda uma cadeia contínua de `requestAnimationFrame`, registra cada timestamp fornecido pelo navegador e calcula o FPS por `fpsFromRafTimestamps` exatamente como a spec. A coleta começa e termina nos mesmos marcos da órbita em todos os runs. Um `TwinRenderProbe` interno, ativado somente por `?twinProfile=1`, pode emitir `twin3d:frame` a partir de `useFrame` apenas como diagnóstico de que as invalidações previstas ocorreram; sua contagem nunca substitui timestamps rAF nem entra na fórmula decisória. Long tasks vêm de `PerformanceObserver`. RED tests alimentam sequências de timestamps/deltas conhecidas e provam a fórmula, inclusive que contagens `useFrame` divergentes não alteram o FPS. A sequência de eventos, timestamps rAF, deltas, diagnóstico do renderer, fixture, câmera, viewport, DPR, warmup e duração são registradas no relatório.

O objeto final registra:

```js
{
  "schemaVersion": 1,
  "baseCommit": "4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e",
  "verifiedCodeCommit": verifiedCodeCommit,
  "phaseDStartCommit": phaseDStartCommit,
  "d7PublicSeamCommit": d7PublicSeamCommit,
  "phaseD8StartCommit": phaseD8StartCommit,
  "assetHashes": {
    "glb": "fc313dd651c904115767d67992285b6213a4e7bc1c3d0ab8ad7f2742d7629296",
    "preview": previewRenderReport.previewSha256,
    "sourceStep": "7af8e745df756787282cfec2f5b6fe6a73650ba0937c542181f9d614324386f3"
  },
  "viewport": { "width": 1366, "height": 768, "deviceScaleFactor": 1 },
  "warmupSeconds": 3,
  "measurementSeconds": 10,
  "runs": [],
  "summary": {},
  "environment": {}
}
```

O objeto ilustrativo nunca é serializado literalmente: `previewRenderReport.previewSha256`, `runs`, `summary`, `generatedAt`, navegador, SO, CPU, GPU/renderer e driver são resolvidos pelo script durante a medição. GPU/driver indisponível deve ser registrado como `unavailable`, não adivinhado. O processo falha se qualquer um dos três runs ficar abaixo de `30 FPS` ou se qualquer long task exceder `200 ms`.

- [ ] **Step 8: Create deterministic same-origin fixtures and regenerate the owned preview**

`tests/e2e/fixtures/interactive-twin.js` intercepta somente as rotas same-origin já usadas pelo app e oferece estados completos:

- `now-normal` com S1/S2 válidos;
- `now-watch` com ênfase contratada em S2;
- `now-alert` com ênfase contratada em S1;
- `historical-alert` com timestamp e valores diferentes do snapshot live;
- `historical-gap` sem canais, avaliação ou `conditionAsOf`, preservando `decisionAsOf` como o cursor solicitado;
- `insufficient-data` sem causalidade;
- erro de asset/WebGL para fallback.

Cada fixture usa o schema real da Fase C. Não injeta props diretamente no componente nem intercepta CDN.

Escrever primeiro `render-interactive-twin-preview.test.mjs` com runner/funções injetáveis e fixtures temporárias. RED cases: URL ausente, readiness incompleto, contagem diferente de 17, hash GLB divergente, screenshot fora de `1200x675`, relatório sem ambiente e tentativa de escrever fora do path explicitamente recebido. `with-local-twin-server.test.mjs` cobre porta inicialmente ocupada, action desconhecida/argumento extra, timeout de readiness, PID/start-identity inesperado, falha da action, teardown em exceção/sinal, filho de processo restante e porta ainda aberta depois do teardown. Run RED:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" scripts/twin3d/render-interactive-twin-preview.test.mjs scripts/twin3d/with-local-twin-server.test.mjs 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch '(?is)(?=.*(?:render-interactive-twin-preview|with-local-twin-server))(?=.*(?:failed to resolve import|cannot find module|does not exist))') { throw 'preview renderer/server-controller RED did not fail for the expected missing module' }
```

Implementar o renderer para reutilizar `installInteractiveTwinFixture(page, "insufficient-data")` e o `chromium` bundled da dependência pinada, navegar com `?twinPreviewCapture=1`, esperar o GLB real e capturar somente `[data-testid="twin3d-canvas-frame"]` em câmera isométrica restaurada, materiais ilustrativos e condição neutra. A captura não contém valor, timestamp, alerta, sensor, controles ou copy operacional; é uma representação context-free para o fallback. O relatório registra `glbSha256`, `previewSha256`, source STEP hash, Chromium, SO, GPU/driver quando disponível, viewport `1200x675`, DPR `1`, câmera e `generatedAt`. O renderer também proíbe `channel`, `executablePath` e fallback para navegador do sistema.

Implementar `with-local-twin-server.mjs` como o único owner do processo Vite nessas medições. Não spawnar `npm.cmd`/`cmd.exe`: no Windows isso é shell-dependent e pode retornar `EINVAL`. O controller resolve como arquivos regulares, locais e não-reparse `process.execPath`, `node_modules/vite/bin/vite.js`, o renderer e o profiler; aceita somente `--action render-preview|profile`, sem argv livre. Confirmar que `127.0.0.1:4173` está livre, iniciar `process.execPath` com o Vite CLI e os argumentos fixos `--host 127.0.0.1 --port 4173 --strictPort`, guardar handle, PID, executable e start identity sem serializar path, aguardar GET de readiness com deadline e spawnar a action allowlisted também por `process.execPath` com argumentos fixos.

Propagar o exit code da action e encerrar toda a árvore **owned** no `finally`. Em Windows, usar `taskkill.exe /PID <pid-exato> /T /F` somente enquanto o handle original ainda está ativo e depois de revalidar PID/start identity; em outras plataformas, usar o process group criado pelo controller. Verificar exit do teardown, ausência dos child PIDs e porta fechada. Timeout, crash, Ctrl+C ou action falha entram no mesmo fluxo; jamais matar por nome/glob, aceitar PID reusado ou reutilizar servidor preexistente.

Reexecutar ambos os testes GREEN antes de iniciar o controller real:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" scripts/twin3d/render-interactive-twin-preview.test.mjs scripts/twin3d/with-local-twin-server.test.mjs
Assert-NativeSuccess 'preview renderer/server-controller GREEN tests'
```

Executar servidor, readiness, render e teardown no mesmo controller fail-closed:

```powershell
node scripts/twin3d/with-local-twin-server.mjs --action render-preview
Assert-NativeSuccess 'controlled interactive twin preview render'
npm.cmd run check:twin-assets
Assert-NativeSuccess 'validate rendered twin preview'
```

Expected: `public/models/conjunto-motor-bomba-preview.png` é substituída pela captura aprovada, `artifacts/twin3d/preview-render-report.json` contém seu hash real, GLB/manifest/conversion-report permanecem byte-idênticos e o inventário continua com 17 nós.

- [ ] **Step 9: Write RED real-browser acceptance tests**

Em `tests/e2e/interactive-twin.spec.js`, cobrir:

1. `now-normal`: esperar GLB real carregado, 17 nós, selecionar cada grupo por botão e por canvas, restaurar vista;
2. `historical-alert`: confirmar timestamp/valor históricos no twin enquanto o snapshot live conflitante não aparece;
3. `historical-gap`: confirmar estado neutro, canais indisponíveis e ausência de carry-forward;
4. alerta sem `componentTag`: halo global/texto, nenhum grupo com classe causal;
5. teclado: Tab, Enter/Space, foco visível, isolamento e saída de isolamento;
6. sensor: S1/S2/all abrem o VIM32 separado e exibem “posição física não validada”, sem anchor/hotspot no GLB;
7. WebGL/GLB indisponível: a PNG regenerada aparece no único `Twin3DStaticFallback`, e contexto, grupo, sensor, valor e histórico continuam acessíveis;
8. `prefers-reduced-motion`: foco instantâneo, nenhuma animação contínua;
9. layout em `1366x768` e `390x844`: twin abaixo do resumo operacional, sem overflow horizontal.

Antes de qualquer screenshot, exigir simultaneamente:

```js
await expect(page.locator('[data-model-ready="true"]')).toBeVisible();
await expect(page.locator('[data-rendered-node-count="17"]')).toBeVisible();
```

Para fallback, exigir `[data-testid="twin3d-static-fallback"][data-twin-fallback="true"]`, a imagem derivada do GLB/STEP e ausência de qualquer fallback legado injetado. Um canvas vazio nunca conta como evidência visual aprovada.

- [ ] **Step 10: Capture and review the visual matrix locally**

Capturar screenshots Playwright para `normal`, `watch`, `alert`, `insufficient-data`, `historical-alert`, `historical-gap` e `fallback`, em desktop e mobile. Usar nomes estáveis sob o output padrão do Playwright; não versionar screenshots automáticos.

Checklist manual por imagem:

- motor, bomba, acoplamento e base continuam distinguíveis;
- material está claramente apresentado como ilustrativo;
- nenhuma cor de alerta implica grupo culpado;
- sensor não aparece montado no equipamento;
- `viewMode`, `decisionAsOf`, condição e qualidade são legíveis;
- foco, hover e seleção são distinguíveis também sem depender apenas de cor;
- controles não encobrem o modelo nem saem do viewport;
- fallback mantém a investigação operacional.

Run:

```powershell
npm.cmd run test:e2e:twin
Assert-NativeSuccess 'local twin browser matrix'
```

Expected: PASS e matriz visual disponível para revisão humana.

- [ ] **Step 11: Measure the real local scene and apply the hard performance gate**

Executar a medição sob o mesmo controller de readiness/PID/porta/teardown:

```powershell
node scripts/twin3d/with-local-twin-server.mjs --action profile
Assert-NativeSuccess 'local interactive twin performance profile'
```

Expected: exit `0`, `minimumRunFps >= 30` entre os três runs e pior long task <= `200 ms`. O relatório prova que fixture, órbita e sequência de invalidação foram idênticas. Se falhar, reduzir custo de sombra/material/outline sem trocar assets ou relaxar limites; repetir todos os três runs e versionar somente o relatório da execução aprovada.

- [ ] **Step 12: Gate production claims and hand local evidence to Phase E**

Escrever RED tests para `check-twin-production-claims.mjs`. O scanner lê somente outputs de produção sob `dist` (`.js`, `.css`, `.html`, `.json`), normaliza whitespace/escapes e remove antes do denylist apenas estas frases completas allowlisted:

- “posição física não validada”;
- “não atribui causa ao grupo”;
- “não valida componentes internos”;
- “não valida impulsor ou selo”;
- “não valida material real”;
- “materiais da experiência interativa são ilustrativos”.

Fixtures provam que essas negações aprovadas passam, enquanto “sensor montado na bomba”, “falha na bomba”, “componente culpado”, “pare o equipamento”, “continue operando”, claim positivo de material real e URL visual externa falham. Substring parcial da allowlist também falha. O relatório guarda arquivos escaneados, allowlist versionada e matches sanitizados, sem reproduzir path absoluto.

Run:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" scripts/twin3d/check-twin-production-claims.test.mjs
Assert-NativeSuccess 'production claims checker tests'
npm.cmd run build:manifest
Assert-NativeSuccess 'production claims manifest build'
npm.cmd run check:twin-claims
Assert-NativeSuccess 'production claims bundle gate'
```

Expected: PASS sobre o bundle final. Encerrar D com servidor local desligado, matriz visual, preview render report, perfil e checks locais. Entregar esses caminhos e o SHA de código à Fase E; não instalar Vercel, não executar deploy e não testar URL remota neste plano.

- [ ] **Step 13: Commit the automated quality gates**

```powershell
git add package.json vitest.config.js scripts/twin3d/check-interactive-twin-assets.mjs scripts/twin3d/check-interactive-twin-assets.test.mjs scripts/twin3d/check-lazy-twin-build.mjs scripts/twin3d/check-lazy-twin-build.test.mjs scripts/twin3d/check-twin-production-claims.mjs scripts/twin3d/check-twin-production-claims.test.mjs scripts/twin3d/render-interactive-twin-preview.mjs scripts/twin3d/render-interactive-twin-preview.test.mjs scripts/twin3d/with-local-twin-server.mjs scripts/twin3d/with-local-twin-server.test.mjs scripts/twin3d/profile-interactive-twin.mjs scripts/twin3d/profile-interactive-twin.test.mjs tests/e2e/fixtures/interactive-twin.js tests/e2e/interactive-twin.spec.js src/components/twin3d/Twin3DCanvas.jsx src/components/twin3d/Twin3DCanvas.test.jsx src/components/twin3d/TwinCameraRig.jsx src/components/twin3d/TwinCameraRig.test.jsx public/models/conjunto-motor-bomba-preview.png
Assert-NativeSuccess 'stage twin quality gates'
git diff --cached --check
Assert-NativeSuccess 'check staged twin quality gates'
$expectedD8CodePaths = @(
  'package.json','vitest.config.js',
  'scripts/twin3d/check-interactive-twin-assets.mjs','scripts/twin3d/check-interactive-twin-assets.test.mjs',
  'scripts/twin3d/check-lazy-twin-build.mjs','scripts/twin3d/check-lazy-twin-build.test.mjs',
  'scripts/twin3d/check-twin-production-claims.mjs','scripts/twin3d/check-twin-production-claims.test.mjs',
  'scripts/twin3d/render-interactive-twin-preview.mjs','scripts/twin3d/render-interactive-twin-preview.test.mjs',
  'scripts/twin3d/with-local-twin-server.mjs','scripts/twin3d/with-local-twin-server.test.mjs',
  'scripts/twin3d/profile-interactive-twin.mjs','scripts/twin3d/profile-interactive-twin.test.mjs',
  'tests/e2e/fixtures/interactive-twin.js','tests/e2e/interactive-twin.spec.js',
  'src/components/twin3d/Twin3DCanvas.jsx','src/components/twin3d/Twin3DCanvas.test.jsx',
  'src/components/twin3d/TwinCameraRig.jsx','src/components/twin3d/TwinCameraRig.test.jsx',
  'public/models/conjunto-motor-bomba-preview.png'
)
$actualD8CodePaths = @(git diff --cached --name-only)
Assert-NativeSuccess 'read staged twin quality scope'
if (Compare-Object ($expectedD8CodePaths | Sort-Object) ($actualD8CodePaths | Sort-Object) -CaseSensitive -SyncWindow 0) { throw 'staged twin quality scope mismatch' }
git commit -m "test: gate interactive twin quality"
Assert-NativeSuccess 'commit twin quality gates'
```

### Task 9: Produce final verification evidence and close only on real results

**Files:**

- Create after all gates pass: `artifacts/twin3d/interactive-twin-verification.json`
- Create after independent review: `docs/verification/phase-d-findings.json`
- Modify after all gates pass: `docs/verification/unified-twin-acceptance-v1.json`
- Regenerate after all gates pass: `docs/verification/unified-twin-acceptance-v1.md`
- Reuse unchanged: `scripts/verify_unified_acceptance.py`

**Verification artifact contract:**

```js
{
  schemaVersion: 1,
  generatedAt: string,
  baseCommit: "4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e",
  phaseDStartCommit: string,
  d7PublicSeamCommit: string,
  phaseD8StartCommit: string,
  verifiedCodeCommit: string,
  assetIntegrity: { passed: true, report: object },
  previewRender: {
    passed: true,
    reportPath: "artifacts/twin3d/preview-render-report.json",
    reportSha256: string
  },
  lazyBuild: { passed: true, report: object },
  unitTests: { passed: true, command: "npm.cmd run test:run -- --exclude \"**/.pytest_cache/**\"" },
  e2e: { passed: true, command: "npm.cmd run test:e2e:twin" },
  performance: {
    passed: true,
    reportPath: "artifacts/twin3d/performance-profile.json",
    reportSha256: string
  },
  visualReview: {
    passed: true,
    viewports: ["1366x768", "390x844"],
    states: ["normal", "watch", "alert", "insufficient_data", "historical_alert", "historical_gap", "fallback"]
  },
  immutableFiles: { passed: true, paths: string[] },
  productionClaimsScan: {
    passed: true,
    reportPath: "artifacts/twin3d/production-claims-report.json",
    reportSha256: string,
    report: object
  },
  independentCodeReview: {
    passed: true,
    reportPath: "docs/verification/phase-d-findings.json",
    reportSha256: string,
    reviewedSha: string,
    verdict: { critical: 0, important: 0, minor: number }
  }
}
```

`phaseDStartCommit` é o checkpoint registrado depois do C1 revisado, `d7PublicSeamCommit` encerra o primeiro intervalo D e `phaseD8StartCommit` é exatamente o evidence commit C11 autenticado antes de qualquer escrita D8. `verifiedCodeCommit` é o SHA do commit de código/asset executável criado ao fim da Task 8. `evidenceCommit` é calculado somente depois que relatórios e ledger forem commitados, portanto não é autoinscrito dentro do próprio commit; ele é registrado no handoff e submetido a re-review independente. Não criar o JSON se qualquer valor seria `passed:false`; preservar a saída real do gate falho e corrigir antes de fechar.

- [ ] **Step 1: Freeze the code SHA and run the complete deterministic suite**

Run:

```powershell
$globalBaseCommit = "4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e"
function Assert-NativeSuccess([string]$label) {
  if ($LASTEXITCODE -ne 0) { throw "$label failed with exit code $LASTEXITCODE" }
}
$phaseDStartCommit = $env:PHASE_D_START_COMMIT
$d7PublicSeamCommit = $env:D7_PUBLIC_SEAM_COMMIT
$phaseD8StartCommit = $env:PHASE_D8_START_COMMIT
if ($phaseDStartCommit -notmatch '^[0-9a-f]{40}$' -or $d7PublicSeamCommit -notmatch '^[0-9a-f]{40}$' -or $phaseD8StartCommit -notmatch '^[0-9a-f]{40}$') { throw 'all Phase D ownership checkpoints are required' }
$verifiedCodeCommit = (git rev-parse HEAD).Trim()
Assert-NativeSuccess 'verified code SHA'
git merge-base --is-ancestor $globalBaseCommit $phaseDStartCommit
Assert-NativeSuccess 'global base to Phase D start ancestry'
git merge-base --is-ancestor $phaseDStartCommit $d7PublicSeamCommit
Assert-NativeSuccess 'Phase D start to D7 ancestry'
git merge-base --is-ancestor $d7PublicSeamCommit $phaseD8StartCommit
Assert-NativeSuccess 'D7 to authenticated D8 boundary ancestry'
git merge-base --is-ancestor $phaseD8StartCommit $verifiedCodeCommit
Assert-NativeSuccess 'D8 boundary to verified code ancestry'
git status --short
Assert-NativeSuccess 'pre-gate status'
npm.cmd run test:run -- --exclude "**/.pytest_cache/**"
Assert-NativeSuccess 'full frontend suite'
npm.cmd run build:manifest
Assert-NativeSuccess 'manifest build'
npm.cmd run check:twin-assets
Assert-NativeSuccess 'twin asset gate'
npm.cmd run check:twin-lazy
Assert-NativeSuccess 'twin lazy gate'
npm.cmd run check:twin-claims
Assert-NativeSuccess 'twin claims gate'
npm.cmd run test:e2e:twin
Assert-NativeSuccess 'twin browser gate'
```

Expected: o status contém no máximo os relatórios medidos ainda não commitados; nenhum arquivo de código está modificado. Todos os comandos retornam exit `0`. Registrar texto, duração, `$phaseDStartCommit`, `$d7PublicSeamCommit`, `$phaseD8StartCommit` e `$verifiedCodeCommit` no artefato final; não chamar o futuro commit de evidência de código verificado e não resumir falha como sucesso.

- [ ] **Step 2: Re-run the measured performance gate on the final HEAD**

Com o servidor local no mesmo comando/viewport da Task 8:

```powershell
node scripts/twin3d/with-local-twin-server.mjs --action profile
Assert-NativeSuccess 'controlled final interactive twin performance profile'
node -e "const fs=require('node:fs');const r=JSON.parse(fs.readFileSync('artifacts/twin3d/performance-profile.json','utf8'));const runs=r.runs;const valid=Array.isArray(runs)&&runs.length===3&&runs.every((x)=>Number.isFinite(x.fps)&&Number.isFinite(x.worstLongTaskMs));const min=valid?Math.min(...runs.map((x)=>x.fps)):NaN;const worst=valid?Math.max(...runs.map((x)=>x.worstLongTaskMs)):NaN;if(r.verifiedCodeCommit!==process.argv[1]||r.phaseDStartCommit!==process.argv[2]||r.d7PublicSeamCommit!==process.argv[3]||r.phaseD8StartCommit!==process.argv[4]||!valid||!Number.isFinite(r.summary?.minimumRunFps)||!Number.isFinite(r.summary?.worstLongTaskMs)||r.summary.minimumRunFps!==min||r.summary.worstLongTaskMs!==worst||min<30||worst>200)process.exit(1);" $verifiedCodeCommit $phaseDStartCommit $d7PublicSeamCommit $phaseD8StartCommit
Assert-NativeSuccess 'final performance report SHA and threshold bindings'
```

Expected: relatório declara `verifiedCodeCommit=$verifiedCodeCommit`, usa exatamente três runs, `minimumRunFps >= 30` e pior long task <= `200 ms`. O caso `[15,60,60]` permanece reprovado.

- [ ] **Step 3: Prove the source assets stayed byte-identical**

Run:

```powershell
git diff --exit-code $phaseDStartCommit $d7PublicSeamCommit -- public/models/conjunto-motor-bomba.glb public/models/conjunto-motor-bomba.manifest.json artifacts/twin3d/conversion-report.json
Assert-NativeSuccess 'immutable technical assets first D range'
git diff --exit-code $phaseD8StartCommit $verifiedCodeCommit -- public/models/conjunto-motor-bomba.glb public/models/conjunto-motor-bomba.manifest.json artifacts/twin3d/conversion-report.json
Assert-NativeSuccess 'immutable technical assets second D range'
npm.cmd run check:twin-assets
Assert-NativeSuccess 'final twin asset gate'
```

Expected: nenhum diff nos três assets técnicos imutáveis nos dois intervalos D. O checker ainda compara GLB/source aos hashes globais congelados, confirma 17 nós e prova que a PNG regenerada coincide com `preview-render-report.json`; a mudança da PNG no segundo intervalo D é esperada e versionada no `$verifiedCodeCommit`.

- [ ] **Step 4: Re-run the allowlist-aware production claims gate**

Run:

```powershell
npm.cmd run build:manifest
Assert-NativeSuccess 'final production build'
node scripts/twin3d/check-twin-production-claims.mjs dist --report artifacts/twin3d/production-claims-report.json
Assert-NativeSuccess 'production claims scan'
```

Expected: exit `0`, `matches=[]` depois da remoção exclusiva das frases completas allowlisted. O gate atua no output real de produção e aceita negações aprovadas sem permitir versão positiva, substring parcial ou comando operacional.

- [ ] **Step 5: Assemble verification JSON from machine outputs**

Antes de montar o JSON, um reviewer diferente do autor prova a ancestry global e revisa somente os commits/paths dos intervalos `$phaseDStartCommit..$d7PublicSeamCommit` e `$phaseD8StartCommit..$verifiedCodeCommit`. O intervalo `$d7PublicSeamCommit..$phaseD8StartCommit` é apenas a cadeia C11 autenticada no dependency gate e fica fora do verdict de código D. O reviewer grava `docs/verification/phase-d-findings.json` para exatamente `$verifiedCodeCommit`, com somente estas chaves e shape:

```powershell
$globalBaseCommit='4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e'
function Assert-NativeSuccess([string]$label) {
  if ($LASTEXITCODE -ne 0) { throw "$label failed with exit code $LASTEXITCODE" }
}
$phaseDStartCommit=[string]$env:PHASE_D_START_COMMIT
$d7PublicSeamCommit=[string]$env:D7_PUBLIC_SEAM_COMMIT
$phaseD8StartCommit=[string]$env:PHASE_D8_START_COMMIT
$verifiedCodeCommit=[string]$env:PHASE_D_VERIFIED_CODE_COMMIT
if (@(@($phaseDStartCommit,$d7PublicSeamCommit,$phaseD8StartCommit,$verifiedCodeCommit) | Where-Object { $_ -notmatch '^[0-9a-f]{40}$' }).Count -ne 0) { throw 'independent Phase D code review requires four exact SHAs' }
git merge-base --is-ancestor $globalBaseCommit $phaseDStartCommit
Assert-NativeSuccess 'review global lineage'
git merge-base --is-ancestor $phaseDStartCommit $d7PublicSeamCommit
Assert-NativeSuccess 'review first Phase D range ancestry'
git merge-base --is-ancestor $d7PublicSeamCommit $phaseD8StartCommit
Assert-NativeSuccess 'review authenticated upstream interval ancestry'
git merge-base --is-ancestor $phaseD8StartCommit $verifiedCodeCommit
Assert-NativeSuccess 'review second Phase D range ancestry'
git log --oneline "$phaseDStartCommit..$d7PublicSeamCommit"
Assert-NativeSuccess 'review first Phase D commit log'
git diff --check "$phaseDStartCommit..$d7PublicSeamCommit"
Assert-NativeSuccess 'review first Phase D diff hygiene'
git diff --name-only "$phaseDStartCommit..$d7PublicSeamCommit"
Assert-NativeSuccess 'review first Phase D scope listing'
git log --oneline "$phaseD8StartCommit..$verifiedCodeCommit"
Assert-NativeSuccess 'review second Phase D commit log'
git diff --check "$phaseD8StartCommit..$verifiedCodeCommit"
Assert-NativeSuccess 'review second Phase D diff hygiene'
git diff --name-only "$phaseD8StartCommit..$verifiedCodeCommit"
Assert-NativeSuccess 'review second Phase D scope listing'
```

```js
const phaseDReview = {
  schemaVersion: "finding-review-v1",
  plan: "D",
  reviewedSha: verifiedCodeCommit,
  verdict: {
    critical: reviewFindings.filter((item) => item.status === "open" && item.severity === "critical").length,
    important: reviewFindings.filter((item) => item.status === "open" && item.severity === "important").length,
    minor: reviewFindings.filter((item) => item.status === "open" && item.severity === "minor").length,
  },
  findings: reviewFindings.map(({
    findingId,
    severity,
    status,
    title,
    evidenceRefs,
    resolvedSha,
  }) => ({ findingId, severity, status, title, evidenceRefs, resolvedSha })),
};
```

Cada finding tem exatamente essas seis chaves; `severity` é `critical|important|minor`, `status` é `open|fixed|accepted`, e `resolvedSha` é `null` para aberto ou o SHA real para `fixed|accepted`. Qualquer Critical/Important aberto volta à implementação, gera novo commit e reinicia Steps 1–5.

Executar asset/lazy/claims com `--report`, ler os bytes de `preview-render-report.json`, `performance-profile.json` e `production-claims-report.json`, calcular o SHA-256 de cada um e gravar seus paths/hashes exatos no respectivo gate de `interactive-twin-verification.json`. Calcular também o SHA-256 dos bytes de `phase-d-findings.json` e criar a verificação somente com `verdict.critical=0`, `verdict.important=0` e `verdict.minor=0`. `independentCodeReview.reportPath`, `reportSha256`, `reviewedSha` e `verdict` referenciam esse arquivo exato. Registrar `$phaseDStartCommit`, `$d7PublicSeamCommit`, `$phaseD8StartCommit` e `$verifiedCodeCommit`; não usar o working-tree HEAD por conveniência. O JSON contém objetos retornados pelos scripts/reviewer, não cópias digitadas de hashes ou métricas.

Validar o artefato:

```powershell
node -e "const fs=require('node:fs'),crypto=require('node:crypto');const sha=(p)=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');const reviewPath='docs/verification/phase-d-findings.json',previewPath='artifacts/twin3d/preview-render-report.json',performancePath='artifacts/twin3d/performance-profile.json',claimsPath='artifacts/twin3d/production-claims-report.json';const bytes=fs.readFileSync(reviewPath);const q=JSON.parse(bytes);const r=JSON.parse(fs.readFileSync('artifacts/twin3d/interactive-twin-verification.json','utf8'));const gates=['assetIntegrity','previewRender','lazyBuild','unitTests','e2e','performance','visualReview','immutableFiles','productionClaimsScan','independentCodeReview'];const exact=['findings','plan','reviewedSha','schemaVersion','verdict'];if(gates.some((k)=>r[k]?.passed!==true)||JSON.stringify(Object.keys(q).sort())!==JSON.stringify(exact)||q.schemaVersion!=='finding-review-v1'||q.plan!=='D'||q.reviewedSha!==process.argv[1]||q.verdict.critical!==0||q.verdict.important!==0||q.verdict.minor!==0||r.previewRender.reportPath!==previewPath||r.previewRender.reportSha256!==sha(previewPath)||r.performance.reportPath!==performancePath||r.performance.reportSha256!==sha(performancePath)||r.productionClaimsScan.reportPath!==claimsPath||r.productionClaimsScan.reportSha256!==sha(claimsPath)||r.independentCodeReview.reportPath!==reviewPath||r.independentCodeReview.reportSha256!==crypto.createHash('sha256').update(bytes).digest('hex')||r.baseCommit!=='4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e'||r.phaseDStartCommit!==process.argv[2]||r.d7PublicSeamCommit!==process.argv[3]||r.phaseD8StartCommit!==process.argv[4]||r.verifiedCodeCommit!==process.argv[1])process.exit(1);" $verifiedCodeCommit $phaseDStartCommit $d7PublicSeamCommit $phaseD8StartCommit
Assert-NativeSuccess 'interactive verification artifact validation'
```

Expected: exit `0`.

- [ ] **Step 6: Update the shared acceptance SSoT for plan D**

Confirmar que a Task 1 da Fase E/index já criou o ledger e o verificador; se qualquer arquivo estiver ausente, parar como dependency gate, sem criar uma cópia local. Ingerir o reviewer report canônico da Step 5:

```powershell
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
$review=(Get-Content -Raw docs/verification/phase-d-findings.json | ConvertFrom-Json)
if ($review.reviewedSha -ne $verifiedCodeCommit) { throw 'phase D review SHA mismatch' }
& $python scripts/verify_unified_acceptance.py ingest-review --ledger docs/verification/unified-twin-acceptance-v1.json --review-report docs/verification/phase-d-findings.json
Assert-NativeSuccess 'ingest Phase D review'
foreach($criterion in @('AC-08','AC-09','AC-10','AC-20','AC-23')) {
  & $python scripts/verify_unified_acceptance.py update-criterion --ledger docs/verification/unified-twin-acceptance-v1.json --criterion $criterion --status passed --evidence-kind automated --evidence-ref docs/verification/phase-d-findings.json --verified-code-commit $verifiedCodeCommit
  Assert-NativeSuccess "update $criterion"
}
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
Assert-NativeSuccess 'render acceptance ledger'
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
Assert-NativeSuccess 'verify acceptance ledger'
node -e "const fs=require('node:fs');const q=JSON.parse(fs.readFileSync('docs/verification/unified-twin-acceptance-v1.json','utf8'));const ids=['AC-08','AC-09','AC-10','AC-20','AC-23'];if(!Array.isArray(q.criteria))process.exit(1);const byId=new Map(q.criteria.map((entry)=>[entry.criterionId,entry]));if(byId.size!==q.criteria.length||q.plans?.D?.status!=='passed'||q.plans.D.verifiedCodeCommit!==process.argv[1]||ids.some((id)=>byId.get(id)?.status!=='passed'||byId.get(id)?.verifiedCodeCommit!==process.argv[1]))process.exit(1);" $verifiedCodeCommit
Assert-NativeSuccess 'assert Phase D ledger state'
```

Expected: somente o subledger D e os cinco critérios congelados de D mudam; findings cumulativos A–C/E e critérios humanos/remotos permanecem intactos. Markdown é regenerado do JSON e nunca editado manualmente.

- [ ] **Step 7: Inspect final scope and diff hygiene**

Run:

```powershell
$phaseDEvidencePaths = @(git status --porcelain=v1 | ForEach-Object { if ($_.Length -lt 4) { throw 'malformed git status line' }; $_.Substring(3) })
Assert-NativeSuccess 'evidence working-tree status'
$expectedPhaseDEvidencePaths = @(
  'artifacts/twin3d/interactive-twin-verification.json',
  'artifacts/twin3d/performance-profile.json',
  'artifacts/twin3d/preview-render-report.json',
  'artifacts/twin3d/production-claims-report.json',
  'docs/verification/phase-d-findings.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
)
if (Compare-Object ($expectedPhaseDEvidencePaths | Sort-Object) ($phaseDEvidencePaths | Sort-Object) -CaseSensitive -SyncWindow 0) { throw 'Phase D evidence working-tree scope mismatch' }
git merge-base --is-ancestor $globalBaseCommit $phaseDStartCommit
Assert-NativeSuccess 'final global ancestry'
git merge-base --is-ancestor $phaseDStartCommit $d7PublicSeamCommit
Assert-NativeSuccess 'final first Phase D ancestry'
git merge-base --is-ancestor $d7PublicSeamCommit $phaseD8StartCommit
Assert-NativeSuccess 'final authenticated upstream ancestry'
git merge-base --is-ancestor $phaseD8StartCommit $verifiedCodeCommit
Assert-NativeSuccess 'final second Phase D ancestry'
git log --oneline "$phaseDStartCommit..$d7PublicSeamCommit"
Assert-NativeSuccess 'final first Phase D commit log'
git diff --check "$phaseDStartCommit..$d7PublicSeamCommit"
Assert-NativeSuccess 'final first committed diff hygiene'
git diff --name-only "$phaseDStartCommit..$d7PublicSeamCommit"
Assert-NativeSuccess 'final first committed scope listing'
git log --oneline "$phaseD8StartCommit..$verifiedCodeCommit"
Assert-NativeSuccess 'final second Phase D commit log'
git diff --check "$phaseD8StartCommit..$verifiedCodeCommit"
Assert-NativeSuccess 'final second committed diff hygiene'
git diff --name-only "$phaseD8StartCommit..$verifiedCodeCommit"
Assert-NativeSuccess 'final second committed scope listing'
git diff --check
Assert-NativeSuccess 'pending evidence diff hygiene'
```

Expected: os dois intervalos contêm somente commits/arquivos D declarados neste plano. O intervalo intermediário autenticado contém C-owned e não entra no scope D. Não há whitespace error, nenhum dos três assets técnicos imutáveis foi modificado e nenhum arquivo de backend, timeline/importação, migração ou deploy aparece. C1/E1 anteriores a `$phaseDStartCommit` também não são atribuídos a D.

- [ ] **Step 8: Commit measured evidence separately from verified code**

```powershell
git add artifacts/twin3d/preview-render-report.json artifacts/twin3d/performance-profile.json artifacts/twin3d/production-claims-report.json artifacts/twin3d/interactive-twin-verification.json docs/verification/phase-d-findings.json docs/verification/unified-twin-acceptance-v1.json docs/verification/unified-twin-acceptance-v1.md
Assert-NativeSuccess 'stage Phase D evidence'
git diff --cached --check
Assert-NativeSuccess 'staged Phase D evidence hygiene'
$stagedPhaseDEvidencePaths = @(git diff --cached --name-only)
Assert-NativeSuccess 'staged Phase D evidence scope read'
if (Compare-Object ($expectedPhaseDEvidencePaths | Sort-Object) ($stagedPhaseDEvidencePaths | Sort-Object) -CaseSensitive -SyncWindow 0) { throw 'staged Phase D evidence scope mismatch' }
git commit -m "docs: record interactive twin verification"
Assert-NativeSuccess 'commit Phase D evidence'
$evidenceCommit = (git rev-parse HEAD).Trim()
Assert-NativeSuccess 'read Phase D evidence SHA'
$evidenceParent = (git rev-parse "$evidenceCommit^").Trim()
Assert-NativeSuccess 'read Phase D evidence parent'
if ($evidenceParent -cne $verifiedCodeCommit) { throw 'Phase D evidence commit must directly follow verified code' }
```

- [ ] **Step 9: Re-review the exact evidence commit independently**

Um reviewer diferente do autor recebe `$verifiedCodeCommit` e `$evidenceCommit`, lê o ledger cumulativo e executa:

```powershell
$globalBaseCommit='4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e'
function Assert-NativeSuccess([string]$label) {
  if ($LASTEXITCODE -ne 0) { throw "$label failed with exit code $LASTEXITCODE" }
}
$phaseDStartCommit=[string]$env:PHASE_D_START_COMMIT
$d7PublicSeamCommit=[string]$env:D7_PUBLIC_SEAM_COMMIT
$phaseD8StartCommit=[string]$env:PHASE_D8_START_COMMIT
$verifiedCodeCommit=[string]$env:PHASE_D_VERIFIED_CODE_COMMIT
$evidenceCommit=[string]$env:PHASE_D_EVIDENCE_COMMIT
if (@(@($phaseDStartCommit,$d7PublicSeamCommit,$phaseD8StartCommit,$verifiedCodeCommit,$evidenceCommit) | Where-Object { $_ -notmatch '^[0-9a-f]{40}$' }).Count -ne 0) { throw 'independent Phase D evidence review requires five exact SHAs' }
$reviewStatus=@(git status --porcelain=v1 --untracked-files=all)
Assert-NativeSuccess 'read independent evidence-review status'
if ($reviewStatus.Count -ne 0) { throw 'independent Phase D evidence review requires a clean worktree' }
git show --check --stat $evidenceCommit
Assert-NativeSuccess 'show Phase D evidence commit'
$evidenceParent = (git rev-parse "$evidenceCommit^").Trim()
Assert-NativeSuccess 're-read Phase D evidence parent'
if ($evidenceParent -cne $verifiedCodeCommit) { throw 're-review requires evidence to directly follow verified code' }
$expectedPhaseDEvidencePaths = @(
  'artifacts/twin3d/interactive-twin-verification.json',
  'artifacts/twin3d/performance-profile.json',
  'artifacts/twin3d/preview-render-report.json',
  'artifacts/twin3d/production-claims-report.json',
  'docs/verification/phase-d-findings.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
)
$actualPhaseDEvidencePaths = @(git diff --name-only "$verifiedCodeCommit..$evidenceCommit")
Assert-NativeSuccess 'list Phase D evidence diff'
if (Compare-Object ($expectedPhaseDEvidencePaths | Sort-Object) ($actualPhaseDEvidencePaths | Sort-Object) -CaseSensitive -SyncWindow 0) { throw 're-review Phase D evidence scope mismatch' }
git diff --exit-code $verifiedCodeCommit $evidenceCommit -- src public/models/conjunto-motor-bomba.glb public/models/conjunto-motor-bomba.manifest.json public/models/conjunto-motor-bomba-preview.png artifacts/twin3d/conversion-report.json package.json vitest.config.js scripts tests
Assert-NativeSuccess 'prove no executable evidence diff'
git diff --exit-code $evidenceCommit -- $expectedPhaseDEvidencePaths
Assert-NativeSuccess 'prove working evidence equals reviewed commit blobs'
$python=(Resolve-Path "..\..\services\twinops\.venv\Scripts\python.exe").Path
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
Assert-NativeSuccess 're-review acceptance ledger'
$phaseDEvidenceValidator = @'
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const [evidence, verified, phaseStart, d7, phaseD8] = process.argv.slice(1);
const show = (path) => execFileSync('git', ['show', evidence + ':' + path]);
const reviewPath = 'docs/verification/phase-d-findings.json';
const reviewBytes = show(reviewPath);
const review = JSON.parse(reviewBytes.toString('utf8'));
const verification = JSON.parse(show('artifacts/twin3d/interactive-twin-verification.json').toString('utf8'));
const previewPath = 'artifacts/twin3d/preview-render-report.json';
const performancePath = 'artifacts/twin3d/performance-profile.json';
const claimsPath = 'artifacts/twin3d/production-claims-report.json';
const previewBytes = show(previewPath);
const performanceBytes = show(performancePath);
const claimsBytes = show(claimsPath);
const previewPngBytes = execFileSync('git', ['show', verified + ':public/models/conjunto-motor-bomba-preview.png']);
const preview = JSON.parse(previewBytes.toString('utf8'));
const performance = JSON.parse(performanceBytes.toString('utf8'));
const claims = JSON.parse(claimsBytes.toString('utf8'));
const ledgerBytes = show('docs/verification/unified-twin-acceptance-v1.json');
const markdownBytes = show('docs/verification/unified-twin-acceptance-v1.md');
const ledger = JSON.parse(ledgerBytes.toString('utf8'));
const sha256 = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const exactReviewKeys = ['findings','plan','reviewedSha','schemaVersion','verdict'];
const gates = ['assetIntegrity','previewRender','lazyBuild','unitTests','e2e','performance','visualReview','immutableFiles','productionClaimsScan','independentCodeReview'];
const criterionIds = ['AC-08','AC-09','AC-10','AC-20','AC-23'];
const criteria = Array.isArray(ledger.criteria) ? new Map(ledger.criteria.map((entry) => [entry.criterionId, entry])) : new Map();
const validRuns = Array.isArray(performance.runs) && performance.runs.length === 3 && performance.runs.every((run) => Number.isFinite(run.fps) && Number.isFinite(run.worstLongTaskMs));
const minimumRunFps = validRuns ? Math.min(...performance.runs.map((run) => run.fps)) : NaN;
const worstLongTaskMs = validRuns ? Math.max(...performance.runs.map((run) => run.worstLongTaskMs)) : NaN;
const fail = Object.keys(review).sort().join('|') !== exactReviewKeys.sort().join('|') || review.schemaVersion !== 'finding-review-v1' || review.plan !== 'D' || review.reviewedSha !== verified || review.verdict?.critical !== 0 || review.verdict?.important !== 0 || review.verdict?.minor !== 0 || gates.some((key) => verification[key]?.passed !== true) || verification.baseCommit !== '4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e' || verification.phaseDStartCommit !== phaseStart || verification.d7PublicSeamCommit !== d7 || verification.phaseD8StartCommit !== phaseD8 || verification.verifiedCodeCommit !== verified || verification.previewRender?.reportPath !== previewPath || verification.previewRender?.reportSha256 !== sha256(previewBytes) || verification.performance?.reportPath !== performancePath || verification.performance?.reportSha256 !== sha256(performanceBytes) || verification.productionClaimsScan?.reportPath !== claimsPath || verification.productionClaimsScan?.reportSha256 !== sha256(claimsBytes) || JSON.stringify(verification.productionClaimsScan?.report) !== JSON.stringify(claims) || preview.glbSha256 !== 'fc313dd651c904115767d67992285b6213a4e7bc1c3d0ab8ad7f2742d7629296' || preview.previewSha256 !== sha256(previewPngBytes) || performance.verifiedCodeCommit !== verified || performance.phaseDStartCommit !== phaseStart || performance.d7PublicSeamCommit !== d7 || performance.phaseD8StartCommit !== phaseD8 || !validRuns || !Number.isFinite(performance.summary?.minimumRunFps) || !Number.isFinite(performance.summary?.worstLongTaskMs) || performance.summary.minimumRunFps !== minimumRunFps || performance.summary.worstLongTaskMs !== worstLongTaskMs || minimumRunFps < 30 || worstLongTaskMs > 200 || !Array.isArray(claims.matches) || claims.matches.length !== 0 || markdownBytes.length === 0 || verification.independentCodeReview?.reportPath !== reviewPath || verification.independentCodeReview?.reportSha256 !== sha256(reviewBytes) || verification.independentCodeReview?.reviewedSha !== verified || verification.independentCodeReview?.verdict?.critical !== 0 || verification.independentCodeReview?.verdict?.important !== 0 || verification.independentCodeReview?.verdict?.minor !== 0 || !Array.isArray(ledger.criteria) || criteria.size !== ledger.criteria.length || ledger.plans?.D?.status !== 'passed' || ledger.plans?.D?.verifiedCodeCommit !== verified || criterionIds.some((id) => criteria.get(id)?.status !== 'passed' || criteria.get(id)?.verifiedCodeCommit !== verified);
if (fail) process.exit(1);
'@
node -e $phaseDEvidenceValidator $evidenceCommit $verifiedCodeCommit $phaseDStartCommit $d7PublicSeamCommit $phaseD8StartCommit
Assert-NativeSuccess 're-review Phase D evidence bindings'
```

Expected: o diff evidence contém exatamente os sete artefatos staged na Step 8; todos são lidos diretamente do blob de `$evidenceCommit`, nenhum código/asset executável mudou, ledger D aponta para `$verifiedCodeCommit`, os quatro checkpoints coincidem, o hash dos bytes do reviewer report coincide com a verificação interativa e o reviewer registra `0 Critical / 0 Important / 0 Minor`. Finding aberto impede conclusão mesmo com suíte verde.

- [ ] **Step 10: Perform the final human acceptance gate**

Demonstrar no mesmo build:

1. alternância `now` ↔ `historical` sem remontar o canvas;
2. seleção/foco/isolamento dos quatro grupos por mouse e teclado;
3. alerta global sem coloração causal de peça;
4. VIM32 dimensional separado e sem posição física inventada;
5. gap histórico sem carry-forward;
6. fallback com contexto, sensores e histórico ainda navegáveis;
7. matriz visual desktop/mobile aprovada;
8. relatório de performance do `$verifiedCodeCommit` aprovado.

Somente após esses oito itens, ledger validado e re-review do `$evidenceCommit`, declarar a Fase D concluída localmente. Entregar ambos os SHAs e os caminhos de evidência à Fase E; qualquer ambiente preview ou produção continua fora deste plano.

## Plan self-review

- Cobertura: Tasks 1–6 constroem contrato, picking/overlays, cena, navegação, sensor e resiliência; Task 7 publica e testa o seam sem possuir Dashboard/App; Task 8 mede comportamento real; Task 9 impede fechamento sem evidência cumulativa.
- Fonte única: D importa o `assertDisplayContextV1` e as fixtures completas de C1, acrescenta somente o binding `forzy-motor-01` e valida antes de view model/props; não existe shape parcial local, estado replay/live, snapshot paralelo, derivação cross-asset ou decision object embutido.
- Evidência física: nomes e bounds vêm do manifesto imutável; materiais são ilustrativos; o VIM32 não recebe posição, rosca, contatos ou detalhes não documentados.
- Fail-closed: gap, ausência, incoerência, erro de asset e WebGL indisponível mantêm contexto textual e nunca produzem causalidade ou dado substituto.
- Imutabilidade: GLB, manifesto e conversion report têm hash/diff gates; a preview PNG é deliberadamente regenerada do GLB e vinculada ao relatório de renderização.
- Usabilidade: canvas e HTML oferecem caminhos equivalentes para seleção; reduced motion, foco, teclado e fallback possuem testes explícitos.
- Qualidade: unit, build manifest, scanner de claims em output, E2E pelo `playwright.twin.config.js` frontend-only de E1, screenshots e três runs de performance com mínimo por run são gates separados e registram resultados medidos.
- Escopo: lineage usa a base global, enquanto commits/paths/diff D usam somente os intervalos disjuntos `$phaseDStartCommit..$d7PublicSeamCommit` e `$phaseD8StartCommit..$verifiedCodeCommit`; C11 é autenticado no intervalo intermediário e nunca atribuído a D. Nenhum passo escreve backend, timeline/importador, banco, migração ou ambiente remoto. A sequência D7 → C11 → D8 é um dependency gate e deploy pertence à Fase E.
- Fechamento: `$verifiedCodeCommit` contém código/PNG executável; `$evidenceCommit` contém somente relatórios e ledger, recebe re-review independente e nunca substitui o SHA verificado.
- Execução: Tasks 1–8 introduzem comportamento com RED/GREEN e commits explícitos; Task 9 congela SHAs, agrega outputs reais, atualiza o ledger e exige re-review sem alterar código.
