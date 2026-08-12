# Frontend Twin 3D Real com Replay e Fallback SVG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exibir o conjunto motor-bomba real como GLB lazy-loaded a partir do `TwinSnapshot` v1, preservando replay determinístico e retornando ao `MotorMimic` SVG em qualquer falha de WebGL, arquivo ou manifesto.

**Architecture:** O pacote consome `useLiveTwin().snapshot`, produzido pelo Pacote 00, e o projeta em um view model puro; nenhum score, severidade ou associação física é inferido no frontend. Um shell React pequeno decide entre SVG e um chunk 3D carregado sob demanda; o STEP é convertido offline e gera GLB, manifesto e relatório reproduzíveis antes de entrar em `public/models`.

**Tech Stack:** React 18.3.1, Vite 5.4.2, JavaScript ESM, Vitest 2.1.9, Testing Library, Three.js 0.169.0, React Three Fiber 8.17.10, Drei 9.117.3, Playwright 1.47.2, FreeCAD 0.21.2 e Blender 4.2 LTS.

## Global Constraints

- Basear o trabalho no commit `1f21f264f88d7a64fecc37e3b3e620eb46d35587`, no commit das specs e no commit concluído do Pacote 00.
- O worker consome `TwinSnapshot` v1 e `useLiveTwin().snapshot`; não altera schemas, fixtures compartilhadas, `TwinDataSource`, `LiveTwinContext.jsx`, `useLiveTelemetry.js`, mocks, backend ou `package.json`.
- Nunca usar o campo ambíguo `vibration` em código novo do Twin 3D; usar exclusivamente `channels[].measurements.vibrationVelocityRms` e `vibrationAcceleration`.
- `receivedAt` nunca é exibido como horário real da medição; `observedAt` live permanece nulo enquanto a origem não fornecer timestamp.
- S1 e S2 permanecem canais separados; nenhuma média implícita entre sensores.
- Status, evidências e destaque vêm exclusivamente de `TwinSnapshot.status` e `TwinSnapshot.assessment`; o frontend não calcula score, severidade, risco ou componente culpado.
- `componentTag` nulo não produz destaque. Uma associação só existe quando o manifesto contém o mesmo `componentTag`; nomes desconhecidos geram warning e nunca associação silenciosa.
- Nenhum texto, marcador ou posição 3D afirma ponto, eixo ou método de montagem de S1/S2; ambos aparecem como `Posição não validada` até confirmação da Forzy.
- Corrente e RPM ausentes em live aparecem como `Indisponível`; dados do mock não completam um snapshot live.
- O navegador nunca carrega STEP/DWG nem chama `trycloudflare.com`; o único asset 3D servido é o GLB otimizado.
- O modo replay continua funcional offline, incluindo iniciar, pausar, reset e próximo cenário; o Twin 3D não implementa nem oculta esses controles.
- `MotorMimic` permanece fallback para WebGL indisponível, lazy import pendente, erro de GLB, manifesto inválido e acessibilidade/redução de movimento.
- Não redesenhar navegação, sidebar, ficha técnica, gauges, gráfico, alertas, Copilot ou design system.
- Não implementar FEA, colisão, animação física de vibração, deformação ou localização inventada de sensores.
- O chunk de entrada existente pode crescer no máximo `15 KiB gzip`; Three/R3F/Drei devem permanecer em chunk lazy separado de no máximo `250 KiB gzip`.
- `public/models/conjunto-motor-bomba.glb` deve ter no máximo `5 MiB`; a conversão deve manter a razão entre dimensões X/Y/Z dentro de `0,5%` do STEP triangulado.
- Na máquina de referência do coordenador, Chrome em `1280x720`, o modelo deve sustentar mediana de pelo menos `30 FPS` por 10 segundos depois do carregamento.
- Cada tarefa usa uma fatia vertical RED → GREEN, executa somente testes da interface pública, roda a regressão relevante e termina em commit pequeno.

## Pré-condição bloqueante

O commit do Pacote 00 deve expor exatamente:

```js
const twin = useLiveTwin();
const snapshot = twin.snapshot;
```

`snapshot` é `null` durante a primeira carga ou um `TwinSnapshot` v1 com:

```js
{
  schemaVersion: "1.0",
  assetTag: "MTR-BMB-042",
  mode: "replay" | "live",
  generatedAt: "ISO-8601 UTC",
  status: "normal" | "watch" | "alert" | "unknown" | "insufficient_data",
  freshness: "fresh" | "delayed" | "expected_idle" | "unavailable" | "unknown",
  channels: TelemetrySample[],
  history: TelemetrySample[],
  assessment: DetectionAssessment | null,
  capabilities: {
    replayControls: boolean,
    liveUpdates: boolean,
    copilot: boolean,
    twin3d: boolean
  }
}
```

Se essa interface não existir, o worker interrompe o pacote e solicita ao integrador o commit faltante; não cria adapter paralelo nem edita o contexto.

## Mapa de arquivos e ownership

Arquivos do integrador, consumidos mas nunca editados por este worker:

- `package.json` e `package-lock.json`: dependências/runtime/testes aprovados na Task 1.
- `contracts/v1/**`: schemas e fixtures normativas.
- `src/contracts/twin.js`: validação de `TwinSnapshot`.
- `src/dataSources/**`: replay e gateway.
- `src/LiveTwinContext.jsx`: expõe `snapshot` e preserva selectors legados.
- `src/useLiveTelemetry.js` e `src/data/mock.js`: motor do replay legado.

Arquivos de ownership exclusivo do worker Twin 3D:

- Create: `src/components/Twin3D.jsx` — shell lazy, gates de WebGL/acessibilidade e error boundary.
- Create: `src/components/Twin3D.test.jsx` — comportamento público de fallback/lazy loading.
- Create: `src/components/twin3d/Twin3DCanvas.jsx` — Canvas, câmera, luz e controles orbitais.
- Create: `src/components/twin3d/Twin3DScene.jsx` — carga do GLB e aplicação visual do view model.
- Create: `src/components/twin3d/twinViewModel.js` — projeção pura de snapshot + manifesto.
- Create: `src/components/twin3d/twinViewModel.test.js` — normal, alert, associação e métricas ausentes.
- Create: `src/components/twin3d/modelManifest.js` — validação fechada do manifesto.
- Create: `src/components/twin3d/modelManifest.test.js` — grupos obrigatórios e nomes desconhecidos.
- Create: `src/components/twin3d/Twin3DScene.test.js` — bindings sobre objetos Three reais, sem WebGL.
- Create: `src/components/twin3d/testFixtures.js` — snapshots/manifestos mínimos específicos do pacote.
- Modify: `src/components/MotorMimic.jsx` — fallback honesto sem posição física afirmada.
- Create: `src/components/MotorMimic.test.jsx` — fallback e rótulo de posição não validada.
- Modify: `src/components/AssetProfile.jsx:17,176-199,299-313` — único ponto de montagem.
- Create: `scripts/twin3d/export_step_meshes.py` — STEP → STLs nomeados via FreeCAD.
- Create: `scripts/twin3d/build_glb.py` — STLs → GLB/manifesto/relatório via Blender.
- Create: `scripts/twin3d/group-rules.json` — classificação explícita e auditável dos sólidos.
- Create: `scripts/twin3d/validate-artifacts.mjs` — invariantes do relatório/manifesto/GLB.
- Create: `scripts/twin3d/validate-artifacts.test.js` — falhas de arquivo, grupo e orçamento.
- Create: `scripts/twin3d/check-bundle-budget.mjs` — compara manifestos Vite antes/depois.
- Create: `scripts/twin3d/check-bundle-budget.test.js` — orçamento de entry/chunk lazy.
- Create: `public/models/conjunto-motor-bomba.glb` — artefato browser-ready.
- Create: `public/models/conjunto-motor-bomba.manifest.json` — grupos e associações aprovadas.
- Create: `artifacts/twin3d/conversion-report.json` — hashes, versões, bounds, sólidos e bytes.
- Create: `artifacts/twin3d/bundle-baseline.json` — baseline do Gate 1.
- Create: `artifacts/twin3d/bundle-report.json` — impacto final de bundle.
- Create: `artifacts/twin3d/runtime-report.md` — FPS, máquina e fallbacks executados.
- Create: `tests/e2e/twin3d.spec.js` — normal, alert, GLB ausente e SVG.

---

### Task 1: Gate do integrador — contrato, dependências e baseline de bundle

**Owner:** Integrador. O worker Twin 3D não executa `npm install`, não edita `package.json` e começa a Task 2 apenas depois deste commit.

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json`
- Create: `artifacts/twin3d/bundle-baseline.json`

**Interfaces:**
- Consumes: `useLiveTwin().snapshot: TwinSnapshot | null` do Pacote 00.
- Produces: `three@0.169.0`, `@react-three/fiber@8.17.10`, `@react-three/drei@9.117.3` como dependências runtime.
- Produces: `@testing-library/react@16.1.0`, `@testing-library/jest-dom@6.6.3`, `jsdom@25.0.1`, `@playwright/test@1.47.2` como dependências de desenvolvimento, além do Vitest já instalado pelo Pacote 00.
- Produces: scripts `test:run`, `test:e2e` e `build:manifest`.

- [ ] **Step 1: Verificar base e contrato compartilhado antes de instalar**

Run:

```powershell
git status --short --branch
git merge-base --is-ancestor 1f21f264f88d7a64fecc37e3b3e620eb46d35587 HEAD
rg -n "snapshot" src/LiveTwinContext.jsx
npm.cmd run test:run
npm.cmd run build
```

Expected: worktree limpo; `merge-base` retorna exit code 0; o contexto expõe `snapshot`; todos os testes e o build passam. Em Windows gerenciado, erro `Acesso negado` do esbuild é bloqueio ambiental e deve ser registrado sem alterar código.

- [ ] **Step 2: Gerar o baseline antes do runtime 3D**

Run:

```powershell
npm.cmd run build -- --manifest
node -e "const fs=require('fs'),cp=require('child_process');const m=JSON.parse(fs.readFileSync('dist/.vite/manifest.json','utf8'));const e=Object.entries(m).find(([,v])=>v.isEntry);if(!e)process.exit(2);fs.mkdirSync('artifacts/twin3d',{recursive:true});fs.writeFileSync('artifacts/twin3d/bundle-baseline.json',JSON.stringify({entry:e[1].file,entryBytes:fs.statSync('dist/'+e[1].file).size,recordedFrom:cp.execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim()},null,2)+'\n')"
```

Expected: `artifacts/twin3d/bundle-baseline.json` contém `entry`, `entryBytes` maior que zero e `recordedFrom`; não existe chunk contendo `three`, `fiber` ou `drei`.

- [ ] **Step 3: Instalar versões compatíveis com React 18 e scripts exatos**

Run:

```powershell
npm.cmd install --save-exact three@0.169.0 @react-three/fiber@8.17.10 @react-three/drei@9.117.3
npm.cmd install --save-dev --save-exact @testing-library/react@16.1.0 @testing-library/jest-dom@6.6.3 jsdom@25.0.1 @playwright/test@1.47.2
```

Adicionar ao objeto `scripts` de `package.json`:

```json
{
  "test:run": "vitest run",
  "test:e2e": "playwright test",
  "build:manifest": "vite build --manifest"
}
```

Expected: `npm.cmd ls react three @react-three/fiber @react-three/drei` não reporta peer dependency inválida; React/Vite/Recharts não são atualizados deliberadamente.

- [ ] **Step 4: Verificar que apenas instalar não inclui Three no entry**

Run:

```powershell
npm.cmd run test:run
npm.cmd run build:manifest
rg -n "three|react-three" dist/.vite/manifest.json
```

Expected: testes e build PASS; `rg` retorna exit code 1 porque nenhum módulo 3D foi importado ainda.

- [ ] **Step 5: Commit do integrador**

```bash
git add package.json package-lock.json artifacts/twin3d/bundle-baseline.json
git commit -m "build: approve lazy twin 3d runtime"
```

Expected: commit contém somente dependências/scripts e baseline; o worker recebe esse SHA como nova base.

### Task 2: Manifesto fechado e view model derivado somente do snapshot

**Files:**
- Create: `src/components/twin3d/modelManifest.js`
- Create: `src/components/twin3d/modelManifest.test.js`
- Create: `src/components/twin3d/twinViewModel.js`
- Create: `src/components/twin3d/twinViewModel.test.js`
- Create: `src/components/twin3d/testFixtures.js`

**Interfaces:**
- Consumes: `TwinSnapshot` v1 e o JSON de `public/models/conjunto-motor-bomba.manifest.json`.
- Produces: `parseModelManifest(value): ModelManifest`; lança `Error("Invalid twin model manifest: ...")` em erro.
- Produces: `componentTagForNode(manifest, nodeName): string | null`; retorna associação somente quando o node está listado em um grupo com `componentTag` não nulo.
- Produces: `buildTwinViewModel({ snapshot, manifest, activeComponent }): TwinViewModel`.
- `ModelManifest` exato:

```js
{
  schemaVersion: "1.0",
  modelUrl: "/models/conjunto-motor-bomba.glb",
  sourceSha256: /^[a-f0-9]{64}$/,
  units: "m",
  upAxis: "Y",
  groups: {
    motor: { nodeNames: string[], componentTag: string | null },
    pump: { nodeNames: string[], componentTag: string | null },
    base: { nodeNames: string[], componentTag: string | null }
  },
  sensors: [
    { sensorId: "s1", placement: "unvalidated" },
    { sensorId: "s2", placement: "unvalidated" }
  ]
}
```

- `TwinViewModel` exato:

```js
{
  status: "normal" | "watch" | "alert" | "unknown" | "insufficient_data",
  freshness: "fresh" | "delayed" | "expected_idle" | "unavailable" | "unknown",
  highlightedNodeNames: string[],
  activeNodeNames: string[],
  channels: [{
    sensorId: "s1" | "s2",
    temperature: { value: number | null, unit: "degC" },
    vibrationVelocityRms: { value: number | null, unit: "mm/s" },
    vibrationAcceleration: { value: number | null, unit: "g", statistic: "unknown" | "rms" | "peak" },
    placementLabel: "Posição não validada"
  }],
  warning: string | null
}
```

Conteúdo mínimo exato de `testFixtures.js` (datas fixas; não usar `Date.now()`):

```js
const measurements = {
  vibrationVelocityRms: { value: 0.04, unit: "mm/s", semanticConfidence: "inferred_from_datasheet" },
  vibrationAcceleration: { value: 0, unit: "g", statistic: "unknown", semanticConfidence: "unconfirmed" },
  temperature: { value: 34, unit: "degC", semanticConfidence: "inferred_from_datasheet" }
};

const channel = (sensorId) => ({
  schemaVersion: "1.0",
  sampleId: `sample-${sensorId}`,
  source: "forzy-live",
  assetTag: "MTR-BMB-042",
  sensorId,
  scheduledAt: "2026-08-12T15:00:00.000Z",
  receivedAt: "2026-08-12T15:00:00.080Z",
  observedAt: null,
  measurements,
  qualityFlags: [],
  payloadHash: `sha256-${sensorId}`,
  raw: {}
});

export const normalSnapshot = {
  schemaVersion: "1.0",
  assetTag: "MTR-BMB-042",
  mode: "replay",
  generatedAt: "2026-08-12T15:00:00.100Z",
  status: "normal",
  freshness: "fresh",
  channels: [channel("s1"), channel("s2")],
  history: [],
  assessment: null,
  capabilities: { replayControls: true, liveUpdates: false, copilot: false, twin3d: true }
};

export const liveSnapshot = {
  ...normalSnapshot,
  mode: "live",
  capabilities: { replayControls: false, liveUpdates: true, copilot: false, twin3d: true }
};

export const alertSnapshot = {
  ...normalSnapshot,
  status: "alert",
  assessment: {
    schemaVersion: "1.0",
    inferenceId: "inference-alert-001",
    assetTag: "MTR-BMB-042",
    sensorId: "s1",
    window: {
      start: "2026-08-12T14:55:00.000Z",
      end: "2026-08-12T15:00:00.000Z",
      receivedAt: "2026-08-12T15:00:00.080Z",
      freshnessMs: 80
    },
    quality: { status: "ok", flags: [] },
    operatingContext: { state: "steady", estimated: true },
    assessment: {
      status: "alert",
      anomalyScore: 0.8,
      deteriorationScore: 0.7,
      scoreSemantics: "relative_to_historical_baseline_not_failure_probability",
      episodeId: "episode-001",
      persistenceSeconds: 60
    },
    componentTag: "CMP-MOTOR-VALIDATED",
    recommendation: "Inspecionar o conjunto com validação humana.",
    humanValidationRequired: true,
    evidence: [],
    model: {
      name: "robust-baseline",
      version: "1.0.0",
      configHash: "sha256-config",
      trainedUntil: "2026-08-11T23:59:59.000Z"
    },
    limitations: []
  }
};

export const manifestWithApprovedMotorBinding = {
  schemaVersion: "1.0",
  modelUrl: "/models/conjunto-motor-bomba.glb",
  sourceSha256: "a".repeat(64),
  units: "m",
  upAxis: "Y",
  groups: {
    motor: { nodeNames: ["ME22A_CORPO", "ME22A_EIXO"], componentTag: "CMP-MOTOR-VALIDATED" },
    pump: { nodeNames: ["BOMBA_CORPO"], componentTag: null },
    base: { nodeNames: ["BASE_01"], componentTag: null }
  },
  sensors: [
    { sensorId: "s1", placement: "unvalidated" },
    { sensorId: "s2", placement: "unvalidated" }
  ]
};
```

- [ ] **Step 1: Escrever o primeiro teste de associação explícita**

```js
import { describe, expect, it } from "vitest";
import { buildTwinViewModel } from "./twinViewModel.js";
import { alertSnapshot, manifestWithApprovedMotorBinding } from "./testFixtures.js";

describe("buildTwinViewModel", () => {
  it("highlights only nodes explicitly bound to assessment.componentTag", () => {
    const vm = buildTwinViewModel({
      snapshot: alertSnapshot,
      manifest: manifestWithApprovedMotorBinding,
      activeComponent: null
    });
    expect(vm.highlightedNodeNames).toEqual(["ME22A_CORPO", "ME22A_EIXO"]);
    expect(vm.status).toBe("alert");
  });
});
```

`alertSnapshot.assessment.componentTag` deve ser `CMP-MOTOR-VALIDATED`; o manifesto associa exatamente esse valor ao grupo `motor`.

- [ ] **Step 2: Rodar RED**

Run:

```powershell
npm.cmd run test:run -- src/components/twin3d/twinViewModel.test.js
```

Expected: FAIL com `Failed to resolve import "./twinViewModel.js"`.

- [ ] **Step 3: Implementar a projeção mínima para passar**

```js
const reading = (measurement, unit, statistic) => ({
  value: measurement?.value ?? null,
  unit,
  ...(statistic ? { statistic: measurement?.statistic ?? statistic } : {})
});

function channelView(channel) {
  const m = channel.measurements || {};
  return {
    sensorId: channel.sensorId,
    temperature: reading(m.temperature, "degC"),
    vibrationVelocityRms: reading(m.vibrationVelocityRms, "mm/s"),
    vibrationAcceleration: reading(m.vibrationAcceleration, "g", "unknown"),
    placementLabel: "Posição não validada"
  };
}

const nodesForComponent = (manifest, componentTag) =>
  componentTag
    ? Object.values(manifest.groups)
        .filter((group) => group.componentTag === componentTag)
        .flatMap((group) => group.nodeNames)
    : [];

export function buildTwinViewModel({ snapshot, manifest, activeComponent = null }) {
  const assessmentTag = snapshot.assessment?.componentTag ?? null;
  return {
    status: snapshot.status,
    freshness: snapshot.freshness,
    highlightedNodeNames: nodesForComponent(manifest, assessmentTag),
    activeNodeNames: nodesForComponent(manifest, activeComponent),
    channels: snapshot.channels.map(channelView),
    warning:
      assessmentTag && nodesForComponent(manifest, assessmentTag).length === 0
        ? `Sem associação 3D aprovada para ${assessmentTag}`
        : null
  };
}
```

- [ ] **Step 4: Rodar GREEN e adicionar uma fatia para `componentTag=null`**

Run:

```powershell
npm.cmd run test:run -- src/components/twin3d/twinViewModel.test.js
```

Expected: PASS.

Adicionar um teste, rodá-lo RED antes de ajustar código, que exige:

```js
expect(buildTwinViewModel({
  snapshot: { ...alertSnapshot, assessment: { ...alertSnapshot.assessment, componentTag: null } },
  manifest: manifestWithApprovedMotorBinding,
  activeComponent: null
}).highlightedNodeNames).toEqual([]);
```

Expected após a implementação já mostrada: PASS sem inferir grupo por status, sensor ou nome.

- [ ] **Step 5: Testar e implementar validação fechada do manifesto**

```js
import { expect, it } from "vitest";
import { parseModelManifest } from "./modelManifest.js";
import { manifestWithApprovedMotorBinding } from "./testFixtures.js";

it("rejects a manifest without all physical groups", () => {
  const { base, ...incomplete } = manifestWithApprovedMotorBinding.groups;
  expect(() => parseModelManifest({
    ...manifestWithApprovedMotorBinding,
    groups: incomplete
  })).toThrow(/base/);
});

it("rejects sensor coordinates while placement is unvalidated", () => {
  expect(() => parseModelManifest({
    ...manifestWithApprovedMotorBinding,
    sensors: [{ sensorId: "s1", placement: "unvalidated", position: [1, 2, 3] }]
  })).toThrow(/position/);
});
```

Run antes: `npm.cmd run test:run -- src/components/twin3d/modelManifest.test.js`

Expected antes: FAIL por módulo ausente.

Implementar validação com allowlist exata de propriedades raiz, grupos, sensores e rejeição de `additionalProperties`; validar SHA-256, grupos não vazios, `units="m"`, `upAxis="Y"`, sensores somente `s1|s2` e `placement="unvalidated"` sem coordenadas.

Run depois: `npm.cmd run test:run -- src/components/twin3d/modelManifest.test.js src/components/twin3d/twinViewModel.test.js`

Expected depois: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/components/twin3d/modelManifest.js src/components/twin3d/modelManifest.test.js src/components/twin3d/twinViewModel.js src/components/twin3d/twinViewModel.test.js src/components/twin3d/testFixtures.js
git commit -m "feat: derive twin 3d view model from snapshot"
```

### Task 3: Conversão offline reproduzível STEP → GLB

**Files:**
- Create: `scripts/twin3d/export_step_meshes.py`
- Create: `scripts/twin3d/build_glb.py`
- Create: `scripts/twin3d/group-rules.json`
- Create: `scripts/twin3d/validate-artifacts.mjs`
- Create: `scripts/twin3d/validate-artifacts.test.js`
- Create: `public/models/conjunto-motor-bomba.glb`
- Create: `public/models/conjunto-motor-bomba.manifest.json`
- Create: `artifacts/twin3d/conversion-report.json`

**Interfaces:**
- Consumes: caminho local do STEP real em `FORZY_STEP_PATH`; o STEP não é copiado para `public`.
- Produces: diretório temporário `build/twin3d/meshes/*.stl` e `parts.json`.
- Produces: GLB com unidades em metros, eixo Y-up e objetos nomeados a partir dos labels do STEP.
- Produces: manifesto no schema fechado da Task 2; `componentTag` permanece `null` sem evidência aprovada.
- Produces: relatório com `sourceSha256`, `freecadVersion`, `blenderVersion`, `sourceSolidCount`, `exportedObjectCount`, `sourceBoundsMm`, `glbBoundsMm`, `dimensionRatioDeltaPct`, `nodeNames` e `glbBytes`.

- [ ] **Step 1: Escrever o validador como RED antes do artefato**

```js
import { readFileSync, statSync } from "node:fs";
import { parseModelManifest } from "../../src/components/twin3d/modelManifest.js";

export function validateArtifacts({ manifestPath, glbPath, reportPath }) {
  const manifest = parseModelManifest(JSON.parse(readFileSync(manifestPath, "utf8")));
  const report = JSON.parse(readFileSync(reportPath, "utf8"));
  const bytes = statSync(glbPath).size;
  if (readFileSync(glbPath).subarray(0, 4).toString("ascii") !== "glTF") {
    throw new Error("GLB magic header is invalid");
  }
  if (report.sourceSolidCount !== 17 || report.exportedObjectCount !== 17) {
    throw new Error("Expected exactly 17 source and exported solids");
  }
  if (bytes > 5 * 1024 * 1024 || report.glbBytes !== bytes) {
    throw new Error("GLB exceeds 5 MiB or report byte count is stale");
  }
  if (Math.max(...report.dimensionRatioDeltaPct) > 0.5) {
    throw new Error("GLB proportions differ from STEP by more than 0.5%");
  }
  for (const group of ["motor", "pump", "base"]) {
    if (manifest.groups[group].nodeNames.length === 0) throw new Error(`${group} has no nodes`);
    for (const node of manifest.groups[group].nodeNames) {
      if (!report.nodeNames.includes(node)) throw new Error(`${node} is absent from GLB report`);
    }
  }
  return { manifest, report, bytes };
}
```

Testar a função com arquivos temporários mínimos e casos de `sourceSolidCount=16`, grupo vazio, magic header inválido, `5 MiB + 1 byte` e delta `0.51`.

Run:

```powershell
npm.cmd run test:run -- scripts/twin3d/validate-artifacts.test.js
node scripts/twin3d/validate-artifacts.mjs public/models/conjunto-motor-bomba.manifest.json public/models/conjunto-motor-bomba.glb artifacts/twin3d/conversion-report.json
```

Expected: teste unitário PASS; validação real FAIL com `ENOENT` porque o GLB ainda não existe.

- [ ] **Step 2: Criar regras explícitas de agrupamento**

Conteúdo de `scripts/twin3d/group-rules.json`:

```json
{
  "schemaVersion": "1.0",
  "groups": {
    "motor": ["^ME22A"],
    "pump": ["^BOMBA"],
    "base": ["BASE", "CHASSI", "CHASSIS", "SKID", "ESTRUTURA"]
  },
  "rejectUnmatched": true
}
```

As expressões são case-insensitive. Se um label real não casar, a conversão para e imprime todos os labels não classificados; o worker registra o label observado e pede ao responsável pelo CAD a classificação factual. Não adicionar regex genérica nem mapear por posição geométrica.

- [ ] **Step 3: Implementar exportação FreeCAD determinística**

`export_step_meshes.py` deve:

1. exigir `--input`, `--output-dir` e `--linear-deflection-mm`;
2. calcular SHA-256 do STEP;
3. abrir via `Import.open`;
4. ordenar objetos por `(Label, Name)`;
5. tessellar cada sólido com `MeshPart.meshFromShape`, `LinearDeflection=0.5`, `AngularDeflection=0.349066`, `Relative=False`;
6. gravar um STL binário por sólido com nome sanitizado e índice de três dígitos;
7. falhar se o total for diferente de 17;
8. gravar `parts.json` com label original, arquivo, volume e bounds em mm.

Entrada CLI exata:

```python
parser.add_argument("--input", required=True)
parser.add_argument("--output-dir", required=True)
parser.add_argument("--linear-deflection-mm", type=float, default=0.5)
```

Sanitização exata:

```python
def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_") or "unnamed"
```

Run:

```powershell
if (-not $env:FORZY_STEP_PATH) { throw "Defina FORZY_STEP_PATH com o caminho absoluto do STEP fornecido pela Forzy" }
$env:FORZY_STEP_PATH = (Resolve-Path -LiteralPath $env:FORZY_STEP_PATH).Path
& "C:\Program Files\FreeCAD 0.21\bin\FreeCADCmd.exe" scripts\twin3d\export_step_meshes.py --input $env:FORZY_STEP_PATH --output-dir build\twin3d\meshes --linear-deflection-mm 0.5
```

Expected: exit code 0; `parts.json` registra `solidCount: 17`; há 17 STLs; SHA-256 tem 64 caracteres; nenhum arquivo é escrito fora de `build/twin3d`.

- [ ] **Step 4: Implementar montagem Blender e geração automática de manifesto/relatório**

`build_glb.py` deve:

1. exigir `--parts`, `--rules`, `--glb`, `--manifest` e `--report` depois de `--`;
2. limpar a cena vazia;
3. importar cada STL por `bpy.ops.wm.stl_import` na ordem de `parts.json`;
4. nomear o objeto com o label sanitizado, aplicar escala uniforme `0.001` e preservar transforms;
5. classificar por regex do `group-rules.json`, falhando em label não classificado ou grupo vazio;
6. aplicar um material PBR simples por grupo, sem textura externa;
7. exportar GLB Y-up sem câmera, luz ou animação;
8. calcular bounds do resultado em metros e delta relativo às razões do STEP;
9. gravar manifesto e relatório com JSON ordenado e newline final;
10. deixar todos os `componentTag` como `null`.

Export exato:

```python
bpy.ops.export_scene.gltf(
    filepath=str(glb_path),
    export_format="GLB",
    export_yup=True,
    export_apply=True,
    export_materials="EXPORT",
    export_cameras=False,
    export_lights=False,
    export_animations=False
)
```

Run:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" --background --factory-startup --python scripts\twin3d\build_glb.py -- --parts build\twin3d\meshes\parts.json --rules scripts\twin3d\group-rules.json --glb public\models\conjunto-motor-bomba.glb --manifest public\models\conjunto-motor-bomba.manifest.json --report artifacts\twin3d\conversion-report.json
```

Expected: exit code 0; GLB, manifesto e relatório são criados; manifesto contém grupos não vazios `motor`, `pump`, `base`; sensores são exatamente `s1` e `s2` com `placement: "unvalidated"` e sem coordenadas.

- [ ] **Step 5: Rodar GREEN sobre o artefato real e provar reprodutibilidade**

Run:

```powershell
node scripts/twin3d/validate-artifacts.mjs public/models/conjunto-motor-bomba.manifest.json public/models/conjunto-motor-bomba.glb artifacts/twin3d/conversion-report.json
Get-FileHash public\models\conjunto-motor-bomba.glb -Algorithm SHA256
```

Expected: `PASS: 17 solids, motor/pump/base resolved, GLB <= 5242880 bytes, proportions delta <= 0.5%`; o hash do GLB e o hash do STEP ficam registrados no relatório. Executar novamente com as mesmas versões e entrada deve reproduzir os mesmos `nodeNames`, bounds e contagem; diferença binária do GLB é permitida somente se `blenderVersion` mudar e deve ser registrada.

- [ ] **Step 6: Commit**

```bash
git add scripts/twin3d public/models artifacts/twin3d/conversion-report.json
git commit -m "feat: add reproducible motor pump glb"
```

Não adicionar o STEP sem autorização explícita sobre licença/confidencialidade.

### Task 4: Shell lazy com fallback SVG antes de tocar na cena WebGL

**Files:**
- Create: `src/components/Twin3D.jsx`
- Create: `src/components/Twin3D.test.jsx`

**Interfaces:**
- Consumes: `snapshot`, `asset`, `activeComponent`, `onSelectComponent` e um elemento React `fallback` já montado pelo `AssetProfile`.
- Produces:

```js
<Twin3D
  snapshot={snapshot}
  asset={asset}
  activeComponent={activeComponent}
  onSelectComponent={onSelectComponent}
  fallback={fallbackElement}
/>
```

- Produces: `canUseWebGL(): boolean` e `prefersReducedMotion(): boolean`.
- Lazy import exato: `lazy(() => import("./twin3d/Twin3DCanvas.jsx"))`.

- [ ] **Step 1: Escrever teste de WebGL indisponível**

```jsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import Twin3D from "./Twin3D.jsx";
import { normalSnapshot } from "./twin3d/testFixtures.js";

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});

it("renders the supplied SVG fallback when WebGL is unavailable", () => {
  render(
    <Twin3D
      snapshot={normalSnapshot}
      asset={{ tag: "MTR-BMB-042" }}
      activeComponent={null}
      onSelectComponent={() => {}}
      fallback={<div data-testid="svg-fallback">SVG fallback</div>}
    />
  );
  expect(screen.getByTestId("svg-fallback")).toBeVisible();
  expect(screen.queryByTestId("twin3d-canvas")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Rodar RED**

Run: `npm.cmd run test:run -- src/components/Twin3D.test.jsx`

Expected: FAIL com `Failed to resolve import "./Twin3D.jsx"`.

- [ ] **Step 3: Implementar o shell mínimo e error boundary**

Regras exatas:

- retornar `fallback` se `snapshot` for nulo, `snapshot.capabilities.twin3d !== true`, WebGL não existir ou `prefers-reduced-motion: reduce` estiver ativo;
- enquanto o chunk importa, `Suspense` mostra o mesmo fallback;
- qualquer erro descendente é capturado por `Twin3DErrorBoundary`, registra `console.warn("Twin3D fallback", error)` e mostra o fallback;
- o shell não faz fetch de manifesto, GLB ou endpoint.

```jsx
const LazyTwin3DCanvas = lazy(() => import("./twin3d/Twin3DCanvas.jsx"));

export function canUseWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}
```

- [ ] **Step 4: Rodar GREEN e adicionar a fatia de erro do chunk**

Run: `npm.cmd run test:run -- src/components/Twin3D.test.jsx`

Expected: PASS.

Adicionar teste que força o filho lazy a rejeitar e verifica o fallback após `await screen.findByTestId("svg-fallback")`; mockar somente `import("./twin3d/Twin3DCanvas.jsx")`, que é fronteira de chunk. Expected depois: dois testes PASS e warning capturado uma vez.

- [ ] **Step 5: Build e inspeção de lazy chunk**

Run:

```powershell
npm.cmd run build:manifest
node -e "const m=require('./dist/.vite/manifest.json');const t=Object.entries(m).find(([k])=>k.endsWith('Twin3DCanvas.jsx'));if(!t||t[1].isEntry)process.exit(1);console.log(t[1].file)"
```

Expected: build PASS; `Twin3DCanvas.jsx` aparece como import dinâmico e não como entry.

- [ ] **Step 6: Commit**

```bash
git add src/components/Twin3D.jsx src/components/Twin3D.test.jsx
git commit -m "feat: add lazy twin 3d fallback shell"
```

### Task 5: Cena 3D, câmera e destaque sem recarregar o GLB

**Files:**
- Create: `src/components/twin3d/Twin3DCanvas.jsx`
- Create: `src/components/twin3d/Twin3DScene.jsx`
- Create: `src/components/twin3d/Twin3DScene.test.js`

**Interfaces:**
- Consumes: `parseModelManifest`, `buildTwinViewModel` e `/models/conjunto-motor-bomba.manifest.json`.
- Produces: `prepareScene({ sourceScene, manifest, viewModel }): THREE.Group`.
- Produces: `loadModelManifest({ fetchImpl, url, signal }): Promise<ModelManifest>` com cache por URL e remoção do cache quando a promise rejeita.
- Produces: `useTwin3DResources({ snapshot, activeComponent }): { manifest: ModelManifest, viewModel: TwinViewModel }`.
- Produces: `Twin3DCanvas({ snapshot, asset, activeComponent, onSelectComponent })` com `data-testid="twin3d-canvas"`.
- GLB e manifesto são carregados uma vez por URL; atualização de snapshot só recalcula cores/overlays.

- [ ] **Step 1: Escrever teste sobre objetos Three reais**

```js
import * as THREE from "three";
import { expect, it } from "vitest";
import { prepareScene } from "./Twin3DScene.jsx";
import { manifestWithApprovedMotorBinding } from "./testFixtures.js";

it("changes highlight materials without mutating the cached source scene", () => {
  const source = new THREE.Group();
  for (const name of ["ME22A_CORPO", "ME22A_EIXO", "BOMBA_CORPO", "BASE_01"]) {
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(1, 1, 1),
      new THREE.MeshStandardMaterial({ color: "#4a3884" })
    );
    mesh.name = name;
    source.add(mesh);
  }
  const prepared = prepareScene({
    sourceScene: source,
    manifest: manifestWithApprovedMotorBinding,
    viewModel: { status: "alert", highlightedNodeNames: ["ME22A_CORPO", "ME22A_EIXO"], activeNodeNames: [] }
  });
  expect(prepared.getObjectByName("ME22A_CORPO").material.emissive.getHexString()).toBe("fb6a6a");
  expect(source.getObjectByName("ME22A_CORPO").material.emissive.getHexString()).toBe("000000");
});
```

- [ ] **Step 2: Rodar RED**

Run: `npm.cmd run test:run -- src/components/twin3d/Twin3DScene.test.js`

Expected: FAIL por módulo ausente.

- [ ] **Step 3: Implementar clone e materiais mínimos**

`prepareScene` deve clonar a hierarquia, clonar cada material, manter geometria compartilhada read-only, validar todos os `manifest.groups.*.nodeNames` contra `getObjectByName`, emitir um warning por nome ausente e aplicar:

- alerta: emissive `#fb6a6a`, intensidade `0.85`;
- watch: emissive `#fbbf24`, intensidade `0.65`;
- seleção ativa: emissive `#a78bfa`, intensidade `0.75`;
- normal: material original clonado, sem emissive adicional.

Passe `viewModel.status` para distinguir `watch` e `alert`; não derive status de cor nem de telemetria.

- [ ] **Step 4: Rodar GREEN e cobrir nome ausente**

Run: `npm.cmd run test:run -- src/components/twin3d/Twin3DScene.test.js`

Expected: PASS.

Adicionar teste que inclui `DESCONHECIDO_01` no manifesto, espiona `console.warn`, exige uma chamada contendo o nome e prova que nenhum outro mesh foi associado. Rodar RED antes do warning e GREEN depois.

- [ ] **Step 5: Implementar Canvas e carregamento por URL**

`Twin3DCanvas.jsx` carrega e valida o manifesto por `loadModelManifest({ fetchImpl, url, signal })`, calcula `viewModel = buildTwinViewModel({ snapshot, manifest, activeComponent })` fora do `<Canvas>` e passa ambos para a cena. Enquanto o manifesto está pendente, renderiza um card com `role="status"` e texto `Carregando gêmeo 3D…`; quando a promise rejeita, armazena o erro e o lança no render seguinte para o error boundary da Task 4.

Estrutura do Canvas depois de manifesto/view model estarem disponíveis:

```jsx
import { Canvas } from "@react-three/fiber";
import { Bounds, OrbitControls } from "@react-three/drei";
import { Suspense } from "react";
import Twin3DScene from "./Twin3DScene.jsx";

export default function Twin3DCanvas({ snapshot, asset, activeComponent, onSelectComponent }) {
  const { manifest, viewModel } = useTwin3DResources({ snapshot, activeComponent });
  return (
    <section
      className="card"
      data-testid="twin3d-canvas"
      data-status={viewModel.status}
      data-highlight-count={viewModel.highlightedNodeNames.length}
      aria-label="Gêmeo 3D do conjunto motor-bomba"
    >
      <div style={{ height: 420, minHeight: 320 }}>
        <Canvas dpr={[1, 1.5]} camera={{ fov: 38, near: 0.01, far: 100, position: [2.4, 1.5, 2.4] }}>
          <color attach="background" args={["#140f2a"]} />
          <ambientLight intensity={1.2} />
          <directionalLight position={[4, 6, 3]} intensity={2.2} />
          <Suspense fallback={null}>
            <Bounds fit clip observe margin={1.15}>
              <Twin3DScene
                manifest={manifest}
                viewModel={viewModel}
                onSelectComponent={onSelectComponent}
              />
            </Bounds>
          </Suspense>
          <OrbitControls makeDefault enablePan={false} minDistance={0.8} maxDistance={8} />
        </Canvas>
      </div>
    </section>
  );
}
```

`Twin3DScene.jsx` usa `useLoader(GLTFLoader, manifest.modelUrl)` para o GLB. O manifesto é carregado pelo hook de recursos com `fetch("/models/conjunto-motor-bomba.manifest.json", { signal })`, validado com `parseModelManifest` e armazenado por URL. Um erro de fetch, parse, GLB ou node obrigatório deve ser lançado para o error boundary da Task 4. Clique em mesh só chama `onSelectComponent(componentTag)` quando o grupo que contém o `node.name` possui `componentTag` não nulo; caso contrário o clique não tem efeito.

- [ ] **Step 6: Provar que telemetria não recarrega o modelo**

Adicionar teste na fronteira de loader com a função exportada `loadModelManifest({ fetchImpl, url, signal })`; chamar duas projeções com snapshots diferentes sobre o mesmo `sourceScene` e exigir que o fetch de manifesto seja chamado uma vez pelo cache, enquanto emissive muda. Mockar apenas `fetchImpl`, a fronteira de arquivo. Adicionar também `componentTagForNode(manifest, nodeName): string | null` e testá-la com `ME22A_CORPO` retornando `CMP-MOTOR-VALIDATED` e `BOMBA_CORPO` retornando `null`.

Run:

```powershell
npm.cmd run test:run -- src/components/twin3d
npm.cmd run build:manifest
```

Expected: todos os testes do diretório PASS; build PASS; GLB e runtime 3D aparecem apenas no caminho lazy.

- [ ] **Step 7: Commit**

```bash
git add src/components/twin3d/Twin3DCanvas.jsx src/components/twin3d/Twin3DScene.jsx src/components/twin3d/Twin3DScene.test.js
git commit -m "feat: render snapshot driven motor pump scene"
```

### Task 6: Integrar no perfil e tornar o SVG fisicamente honesto

**Files:**
- Modify: `src/components/AssetProfile.jsx:17,176-199,299-313`
- Modify: `src/components/MotorMimic.jsx:28-83,111-113,254-337`
- Create: `src/components/MotorMimic.test.jsx`
- Modify: `src/components/Twin3D.test.jsx`

**Interfaces:**
- Consumes: `twin.snapshot` sem alterar o contexto.
- Preserves: props públicas atuais de `MotorMimic`.
- Adds: prop opcional `sensorPlacementValidated = false` em `MotorMimic`.
- Produces: perfil usa 3D somente quando `snapshot.assetTag === asset.tag` e `snapshot.capabilities.twin3d === true`; qualquer outro ativo mantém SVG.

- [ ] **Step 1: Escrever teste RED para o fallback honesto**

```jsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import MotorMimic from "./MotorMimic.jsx";

it("does not draw physical sensor anchors when placement is unvalidated", () => {
  render(
    <MotorMimic
      asset={{ sensors: [{ tag: "s1", type: "Vibração" }, { tag: "s2", type: "Temperatura" }] }}
      reading={{ temperature: 34, vibration: 0.04 }}
      components={[]}
      status="normal"
    />
  );
  expect(screen.getByText("S1 · Posição não validada")).toBeVisible();
  expect(screen.getByText("S2 · Posição não validada")).toBeVisible();
  expect(screen.queryByTestId("physical-sensor-anchor")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Rodar RED e implementar o mínimo**

Run: `npm.cmd run test:run -- src/components/MotorMimic.test.jsx`

Expected antes: FAIL porque o texto não existe.

Quando `sensorPlacementValidated=false`:

- não renderizar linhas, pinos ou labels ancorados no corpo do SVG;
- renderizar fora do `<svg>` dois pills `S1 · Posição não validada` e `S2 · Posição não validada`;
- manter callouts de valores como painel lógico sem linha apontando para posição física;
- alterar subtítulo para `representação SVG de fallback`;
- manter seleção dos componentes do desenho somente para replay legado; ela não cria binding no GLB.

Run depois: `npm.cmd run test:run -- src/components/MotorMimic.test.jsx`

Expected depois: PASS.

- [ ] **Step 3: Integrar o shell no ponto existente**

Adicionar import:

```jsx
import Twin3D from "./Twin3D.jsx";
```

Dentro de `AssetProfile`, sem alterar selectors legados:

```jsx
const canonicalSnapshot =
  twin.snapshot?.assetTag === tag ? twin.snapshot : null;

const svgFallback = (
  <MotorMimic
    asset={asset}
    reading={effReading}
    components={effComps}
    status={effStatus}
    activeComponent={activeComp}
    onSelectComponent={setActiveComp}
    sensorPlacementValidated={false}
  />
);
```

Substituir somente o bloco atual do `MotorMimic` por:

```jsx
{canonicalSnapshot?.capabilities.twin3d ? (
  <Twin3D
    snapshot={canonicalSnapshot}
    asset={asset}
    activeComponent={activeComp}
    onSelectComponent={setActiveComp}
    fallback={svgFallback}
  />
) : (
  svgFallback
)}
```

Não alterar gauges, gráfico, alertas, componentes, Copilot ou replay controls.

- [ ] **Step 4: Adicionar teste de integração pública**

No teste de `Twin3D`, cobrir os dois snapshots:

```jsx
expect(normalSnapshot.capabilities.replayControls).toBe(true);
expect(liveSnapshot.capabilities.replayControls).toBe(false);
```

Renderizar o shell com ambos e provar que a escolha 3D depende somente de `capabilities.twin3d`, não de `mode`; os controles de replay não são renderizados nem removidos pelo Twin 3D.

Run: `npm.cmd run test:run -- src/components/MotorMimic.test.jsx src/components/Twin3D.test.jsx src/components/twin3d`

Expected: PASS.

- [ ] **Step 5: Regressão e busca de claims proibidos**

Run:

```powershell
npm.cmd run test:run
npm.cmd run build
rg -n -i "fisicamente ligado|montado no rolamento|eixo do sensor|posição confirmada|trycloudflare|VITE_SUPABASE" src/components/Twin3D.jsx src/components/twin3d src/components/MotorMimic.jsx
```

Expected: testes e build PASS; `rg` retorna exit code 1. Não remover texto alheio fora dos arquivos de ownership; registrar eventual claim preexistente para o Gate 05.

- [ ] **Step 6: Commit**

```bash
git add src/components/AssetProfile.jsx src/components/MotorMimic.jsx src/components/MotorMimic.test.jsx src/components/Twin3D.test.jsx
git commit -m "feat: mount real twin with svg fallback"
```

### Task 7: E2E visual, orçamento e relatório de entrega

**Files:**
- Create: `tests/e2e/twin3d.spec.js`
- Create: `scripts/twin3d/check-bundle-budget.mjs`
- Create: `scripts/twin3d/check-bundle-budget.test.js`
- Create: `artifacts/twin3d/bundle-report.json`
- Create: `artifacts/twin3d/runtime-report.md`

**Interfaces:**
- Consumes: app integrada com fixture replay do Pacote 00 e assets da Task 3.
- Produces: screenshots `test-results/twin3d-normal.png`, `twin3d-alert.png`, `twin3d-glb-fallback.png`.
- Produces: `checkBundleBudget({ baseline, manifest, distDir }): BundleReport`.

- [ ] **Step 1: Escrever teste RED do orçamento**

```js
import { expect, it } from "vitest";
import { checkBundleBudget } from "./check-bundle-budget.mjs";

it("rejects a 3d runtime merged into the main entry", () => {
  expect(() => checkBundleBudget({
    baseline: { entryBytes: 100000 },
    manifest: {
      "src/main.jsx": { file: "assets/index.js", isEntry: true, dynamicImports: [] }
    },
    sizes: { "assets/index.js": 400000 }
  })).toThrow(/lazy 3D chunk/);
});
```

Run: `npm.cmd run test:run -- scripts/twin3d/check-bundle-budget.test.js`

Expected: FAIL por módulo ausente.

- [ ] **Step 2: Implementar orçamento sobre gzip real**

O script deve usar `zlib.gzipSync` sobre cada arquivo de `dist`, localizar o entry por `isEntry`, seguir `dynamicImports` até o chunk de `Twin3DCanvas`, e falhar quando:

- crescimento gzip do entry for maior que `15 * 1024` bytes;
- chunk lazy 3D gzip for maior que `250 * 1024` bytes;
- não houver dynamic import 3D;
- `three`, `fiber` ou `drei` estiverem alcançáveis somente pelo entry estático.

Run:

```powershell
npm.cmd run test:run -- scripts/twin3d/check-bundle-budget.test.js
npm.cmd run build:manifest
node scripts/twin3d/check-bundle-budget.mjs artifacts/twin3d/bundle-baseline.json dist/.vite/manifest.json dist artifacts/twin3d/bundle-report.json
```

Expected: teste PASS; relatório registra `entryDeltaGzipBytes <= 15360` e `twin3dChunkGzipBytes <= 256000`.

- [ ] **Step 3: Escrever E2E antes de validar estados**

`tests/e2e/twin3d.spec.js` deve usar a rota navegável existente até `MTR-BMB-042`, sem chamar módulos internos, e conter quatro testes:

```js
import { expect, test } from "@playwright/test";

async function openStarAsset(page) {
  await page.goto("/");
  await page.getByRole("button", { name: /Produção/i }).click();
  await page.getByRole("button", { name: /Motor Bomba de Sucção 042/i }).click();
}

test("normal replay shows the real model and unvalidated sensor labels", async ({ page }) => {
  await openStarAsset(page);
  await expect(page.getByTestId("twin3d-canvas")).toBeVisible();
  await expect(page.getByText("S1 · Posição não validada")).toBeVisible();
  await page.screenshot({ path: "test-results/twin3d-normal.png", fullPage: true });
});

test("an alert updates status without remounting or inventing a binding", async ({ page }) => {
  await openStarAsset(page);
  const canvas = page.getByTestId("twin3d-canvas");
  await expect(canvas).toHaveCount(1);
  await page.getByRole("button", { name: /Próximo cenário/i }).click();
  await expect(canvas).toHaveAttribute("data-status", /watch|alert/);
  await expect(canvas).toHaveCount(1);
  await expect(canvas).toHaveAttribute("data-highlight-count", "0");
  await page.screenshot({ path: "test-results/twin3d-alert.png", fullPage: true });
});

test("missing GLB falls back to the existing SVG", async ({ page }) => {
  await page.route("**/models/conjunto-motor-bomba.glb", (route) => route.abort());
  await openStarAsset(page);
  await expect(page.getByRole("img", { name: /desenho do motor/i })).toBeVisible();
  await page.screenshot({ path: "test-results/twin3d-glb-fallback.png", fullPage: true });
});

test("unknown component binding does not highlight another group", async ({ page }) => {
  await openStarAsset(page);
  await expect(page.getByText(/Sem associação 3D aprovada/)).toBeVisible();
  await expect(page.getByTestId("twin3d-canvas")).toHaveAttribute("data-highlight-count", "0");
});
```

Adicionar `data-status` e `data-highlight-count` ao elemento raiz de `Twin3DCanvas`; eles refletem o view model público e não o estado interno do renderer.

Run inicial: `npm.cmd run test:e2e -- tests/e2e/twin3d.spec.js`

Expected inicial: pelo menos o teste de `data-status` ou binding falha até os atributos/aviso serem expostos.

- [ ] **Step 4: Implementar somente a observabilidade pública exigida e rodar GREEN**

No `Twin3DCanvas`, usar:

```jsx
<section
  className="card"
  data-testid="twin3d-canvas"
  data-status={viewModel.status}
  data-highlight-count={viewModel.highlightedNodeNames.length}
  aria-label="Gêmeo 3D do conjunto motor-bomba"
>
```

Exibir `viewModel.warning` como texto `role="status"`. Não expor IDs internos de mesh no DOM.

Run:

```powershell
npm.cmd run test:e2e -- tests/e2e/twin3d.spec.js
```

Expected: quatro testes PASS; três screenshots criadas; falha de GLB produz SVG sem erro não tratado no console.

- [ ] **Step 5: Medir FPS e registrar entrega**

No Chrome da máquina de referência, abrir DevTools Performance, navegar ao ativo, aguardar o GLB e orbitar continuamente por 10 segundos. Registrar a mediana observada em `$medianFps` e copiar renderer/driver de `chrome://gpu` para `$gpuDriver`; não estimar valores.

Run:

```powershell
$medianFps = [double](Read-Host "Mediana de FPS observada nos 10 segundos")
$gpuDriver = Read-Host "Renderer e driver copiados de chrome://gpu"
$conversion = Get-Content -Raw artifacts\twin3d\conversion-report.json | ConvertFrom-Json
$bundle = Get-Content -Raw artifacts\twin3d\bundle-report.json | ConvertFrom-Json
$baseSha = git rev-parse HEAD
$browserVersion = (Get-Item "C:\Program Files\Google\Chrome\Application\chrome.exe").VersionInfo.ProductVersion
$report = @"
# Twin 3D runtime report

- Base SHA: $baseSha
- Browser: Chrome $browserVersion
- GPU/driver: $gpuDriver
- Viewport: 1280x720
- Sample duration: 10 s
- Median FPS: $medianFps
- GLB bytes: $($conversion.glbBytes)
- Entry delta gzip bytes: $($bundle.entryDeltaGzipBytes)
- Twin 3D chunk gzip bytes: $($bundle.twin3dChunkGzipBytes)
- Fallbacks verified: WebGL unavailable; GLB abort; invalid manifest; reduced motion
- Sensor placement: S1/S2 unvalidated; no coordinates rendered
"@
$report | Set-Content -Encoding UTF8 artifacts\twin3d\runtime-report.md
if ($medianFps -lt 30) { throw "Twin 3D below 30 FPS gate" }
```

Expected: relatório contém somente valores medidos/gerados. Gate: mediana `>= 30 FPS`; se falhar, reduzir `dpr` máximo de `1.5` para `1.0` e repetir antes de considerar simplificação adicional do GLB.

- [ ] **Step 6: Rodar suíte final e scanner de escopo**

Run:

```powershell
npm.cmd run test:run
npm.cmd run test:e2e -- tests/e2e/twin3d.spec.js
npm.cmd run build:manifest
node scripts/twin3d/validate-artifacts.mjs public/models/conjunto-motor-bomba.manifest.json public/models/conjunto-motor-bomba.glb artifacts/twin3d/conversion-report.json
node scripts/twin3d/check-bundle-budget.mjs artifacts/twin3d/bundle-baseline.json dist/.vite/manifest.json dist artifacts/twin3d/bundle-report.json
rg -n -i "trycloudflare|VITE_SUPABASE|currentA|rotationRpm|physical.*sensor|sensor.*bearing" dist src/components/Twin3D.jsx src/components/twin3d
git diff --name-only $(git merge-base HEAD origin/main)..HEAD
```

Expected: unit/component/E2E/build/asset/bundle gates PASS; scanner não encontra hostname, segredo, preenchimento live de corrente/RPM ou claim físico; diff contém apenas os arquivos do mapa de ownership e os arquivos do integrador na Task 1.

- [ ] **Step 7: Commit**

```bash
git add tests/e2e/twin3d.spec.js scripts/twin3d/check-bundle-budget.mjs scripts/twin3d/check-bundle-budget.test.js artifacts/twin3d/bundle-report.json artifacts/twin3d/runtime-report.md src/components/twin3d/Twin3DCanvas.jsx
git commit -m "test: verify twin 3d fallbacks and budgets"
```

## Resultado esperado da branch

- O caminho atual da demo continua navegável e replay permanece determinístico/offline.
- O conjunto real aparece apenas no perfil do ativo compatível e é carregado em chunk lazy.
- A cena reage ao mesmo `TwinSnapshot` usado pelos demais consumidores, sem recalcular estado.
- S1/S2 são apresentados como canais separados e com posição não validada.
- Qualquer falha de WebGL, chunk, manifesto ou GLB exibe o `MotorMimic` SVG.
- GLB, manifesto, hashes, versões, bounds, bundle e FPS ficam auditáveis.
- Nenhum arquivo do Copilot, contrato, contexto, mock, backend, navegação ou design system é alterado pelo worker.

## Self-review executado

- **Cobertura da spec:** Tasks 2 e 5 cobrem snapshot/assessment e associação explícita; Task 3 cobre STEP→GLB reproduzível e grupos motor/bomba/base; Tasks 4 e 6 cobrem lazy loading, replay e fallback SVG; Task 7 cobre normal, watch/alert, arquivo ausente, fallback, bundle e FPS.
- **Ownership:** o único trabalho fora do ownership do worker é a Task 1, marcada explicitamente como gate do integrador; o worker não edita `package.json`, contratos, contexto ou mocks.
- **Claims físicos:** manifesto mantém `componentTag=null` e sensores sem coordenadas até evidência aprovada; nome desconhecido interrompe conversão ou gera warning sem associação.
- **Contrato:** todas as interfaces usam nomes v1 do Pacote 00; código novo não usa `vibration`, não funde S1/S2 e não trata `receivedAt` como aquisição.
- **TDD:** cada comportamento novo começa por teste/validação falhando, recebe implementação mínima, regressão e commit; mocks aparecem apenas em fronteiras de browser, chunk ou arquivo.
- **Scan de marcadores incompletos:** não há marcadores pendentes, campos manuais vazios ou função sem assinatura definida.
- **Escopo:** o plano não redesenha o app, não cria backend, não move replay controls e não inclui física/FEA.
