# Real TwinOps 3D Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converter o STEP fornecido em um GLB web verificável e renderizá-lo interativamente, sem inventar sensores ou geometria.

**Architecture:** Uma ferramenta offline reproduzível importa o STEP via CadQuery/OpenCascade, preserva nomes de sólidos, converte unidades e exporta GLB + manifesto. O frontend carrega o manifesto validado e o GLB com R3F/Drei; qualquer falha cai para a imagem real do mesmo conjunto.

**Tech Stack:** Python 3.11, CadQuery 2.x/OpenCascade, glTF/GLB 2.0, Three.js 0.169, React Three Fiber, Drei, Vitest e Vite.

**Spec:** `docs/superpowers/specs/2026-08-13-forzy-twinops-real-vercel-zero-cost-design.md`

## Global Constraints

- Fonte exata: `C:\Users\Luis\Downloads\ChallengeForzy-bomba-teste.stp`.
- Não versionar o STEP/DWG original sem autorização; versionar hash e artefato derivado.
- O STEP contém 17 sólidos e nomes `ME22A`, `B01A/BOMBA`, `B01A/A|B|C` e `B01A/BASE`.
- Nenhuma geometria de sensor ou posição S1/S2 será criada.
- Manifesto `sensors` contém somente `{sensorId, placement:"unvalidated"}`.
- GLB usa metros, eixo Y-up e nomes de nós rastreáveis.
- O modelo deve caber no limite de static asset da Vercel e no orçamento local definido após a primeira conversão; limite inicial de aceite: 20 MB.
- Se CadQuery não conseguir preservar os 17 sólidos, parar a Task 1 e registrar evidência; não fundir silenciosamente.
- Não tocar backend, dashboard operacional ou contratos além de usar `assetId`.

## Mapa de arquivos

- `tools/twin3d/requirements.txt`: runtime isolado da conversão.
- `tools/twin3d/convert_step.py`: conversão determinística.
- `tools/twin3d/inspect_glb.mjs`: verificação de scene graph.
- `public/models/conjunto-motor-bomba.glb`: artefato derivado.
- `public/models/conjunto-motor-bomba.manifest.json`: proveniência e grupos.
- `src/components/twin3d/Twin3DCanvas.jsx`: cena real.

---

### Task 1: Conversor STEP→GLB reproduzível

**Files:**
- Create: `tools/twin3d/requirements.txt`
- Create: `tools/twin3d/convert_step.py`
- Create: `tools/twin3d/test_convert_step.py`

**Interfaces:**
- Produces: `convert_step(source: Path, glb: Path, manifest: Path) -> ConversionReport`.
- Produces: CLI `python tools/twin3d/convert_step.py --source <step-path> --glb <glb-path> --manifest <manifest-path>`.

- [ ] **Step 1: Escrever teste sobre um STEP sintético mínimo**

```python
def test_conversion_preserves_named_solids_and_source_hash(tmp_path):
    source = write_two_body_step(tmp_path, names=("ME22A_001", "BOMBA_008"))
    report = convert_step(source, tmp_path / "out.glb", tmp_path / "out.json")
    assert report.solid_count == 2
    assert report.node_names == ("ME22A_001", "BOMBA_008")
    assert report.source_sha256.startswith("sha256:")
```

- [ ] **Step 2: Criar env isolado e executar RED**

Run: `python -m venv tools/twin3d/.venv`

Run: `tools\twin3d\.venv\Scripts\python.exe -m pip install "cadquery>=2.5,<3" pytest`

Run: `tools\twin3d\.venv\Scripts\python.exe -m pytest tools/twin3d/test_convert_step.py -v`

Expected: FAIL por conversor ausente. Se instalação exigir rede, solicitar aprovação; não substituir por arquivo falso.

- [ ] **Step 3: Implementar conversor**

Use `cq.Assembly.load(source, importType="STEP", unit="MM")`, percorra filhos nomeados, normalize nomes somente removendo separadores inseguros e exporte `.glb` com unidade de saída em metros. Gere manifesto com `schemaVersion:"1.0"`, `assetId`, `modelUrl`, `sourceSha256` sem prefixo no campo legado, `generatedBy`, `solidCount`, `units:"m"`, `upAxis:"Y"`, `groups` e sensors unvalidated.

- [ ] **Step 4: Executar GREEN**

Run: `tools\twin3d\.venv\Scripts\python.exe -m pytest tools/twin3d/test_convert_step.py -v`

Expected: PASS.

- [ ] **Step 5: Commit da ferramenta, sem artefato real ainda**

```powershell
git add tools/twin3d/requirements.txt tools/twin3d/convert_step.py tools/twin3d/test_convert_step.py
git commit -m "feat: add reproducible step to glb converter"
```

### Task 2: Converter e auditar o modelo fornecido

**Files:**
- Create: `public/models/conjunto-motor-bomba.glb`
- Create: `public/models/conjunto-motor-bomba.manifest.json`
- Create: `public/models/conjunto-motor-bomba-preview.png`
- Create: `artifacts/twin3d/conversion-report.json`
- Create: `tools/twin3d/inspect_glb.mjs`

**Interfaces:**
- Produces: GLB referenciado pelo manifesto; relatório com SHA-256, bytes, sólidos, nós e bounds.

- [ ] **Step 1: Converter a fonte real**

Run: `tools\twin3d\.venv\Scripts\python.exe tools/twin3d/convert_step.py --source "C:\Users\Luis\Downloads\ChallengeForzy-bomba-teste.stp" --glb public/models/conjunto-motor-bomba.glb --manifest public/models/conjunto-motor-bomba.manifest.json --report artifacts/twin3d/conversion-report.json`

Expected: `solidCount=17`; GLB e manifesto criados; source hash registrado.

- [ ] **Step 2: Escrever o inspetor GLB**

Use `GLTFLoader.parseAsync` em Node ou pacote `@gltf-transform/core` apenas como dev tool. O script falha se: GLB >20 MB, zero meshes, node do manifesto ausente, bounds não finitos, sensors tiverem coordenadas ou source hash divergir do relatório.

- [ ] **Step 3: Executar auditoria e gerar preview**

Run: `node tools/twin3d/inspect_glb.mjs public/models/conjunto-motor-bomba.glb public/models/conjunto-motor-bomba.manifest.json`

Expected: PASS com 17 sólidos ou 17 grupos rastreáveis. Copie o preview já inspecionado de `docs/jornada/assets/conjunto-motor-bomba-preview.png` para o path público; ele deve ser identificado como fallback, não render 3D.

- [ ] **Step 4: Commit do artefato derivado**

```powershell
git add public/models artifacts/twin3d/conversion-report.json tools/twin3d/inspect_glb.mjs
git commit -m "feat: add verified real motor pump model"
```

### Task 3: Manifesto com identidade real e grupos verificáveis

**Files:**
- Modify: `src/components/twin3d/modelManifest.js`
- Modify: `src/components/twin3d/modelManifest.test.js`

**Interfaces:**
- Produces: `parseModelManifest(value)` exigindo `assetId="forzy-motor-01"`, `solidCount=17` e grupos sem `componentTag` fictício.
- Produces: `nodeGroup(manifest,nodeName) -> "motor"|"pump"|"base"|"coupling"|null`.

- [ ] **Step 1: Atualizar testes antes do parser**

```js
it("accepts the generated manifest without sensor placement", () => {
  const manifest = parseModelManifest(realManifestFixture);
  expect(manifest.assetId).toBe("forzy-motor-01");
  expect(manifest.solidCount).toBe(17);
  expect(manifest.sensors).toEqual([
    { sensorId: "s1", placement: "unvalidated" },
    { sensorId: "s2", placement: "unvalidated" },
  ]);
});
```

Adicione rejeição de `position`, `componentTag`, node ausente e `assetTag`.

- [ ] **Step 2: Rodar RED**

Run: `npm.cmd run test:run -- src/components/twin3d/modelManifest.test.js`

Expected: FAIL porque parser ainda espera formato v1 fictício.

- [ ] **Step 3: Implementar parser exato do manifesto gerado**

Grupos são informativos para cores/seleção visual, não diagnóstico. Compare nodes com o array `nodes` do manifesto; não aceitar wildcard.

- [ ] **Step 4: Rodar GREEN**

Run: `npm.cmd run test:run -- src/components/twin3d/modelManifest.test.js`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/components/twin3d/modelManifest.js src/components/twin3d/modelManifest.test.js
git commit -m "feat: validate real twin model manifest"
```

### Task 4: Canvas R3F com GLB, controles e fallback

**Files:**
- Modify: `src/components/Twin3D.jsx`
- Modify: `src/components/Twin3D.test.jsx`
- Modify: `src/components/twin3d/Twin3DCanvas.jsx`
- Modify: `src/components/twin3d/twinViewModel.js`
- Modify: `src/components/twin3d/twinViewModel.test.js`
- Create: `src/components/twin3d/Twin3DCanvas.test.jsx`

**Interfaces:**
- Produces: `Twin3D({snapshot,fallback})` sem `asset`/`activeComponent` fictícios.
- Produces: Canvas com `useGLTF(manifest.modelUrl)`, `Bounds fit clip observe` e `OrbitControls`.

- [ ] **Step 1: Escrever testes de carregamento e honestidade**

```jsx
it("renders the supplied glb without sensor markers", async () => {
  render(<Twin3DCanvas snapshot={snapshot} loadManifest={manifestStub} Model={ModelStub} />);
  expect(await screen.findByLabelText("Modelo 3D do conjunto motor-bomba")).toBeInTheDocument();
  expect(screen.queryByLabelText(/Sensor S1/)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/Sensor S2/)).not.toBeInTheDocument();
});
```

Adicione falha de manifesto, falha de GLB, WebGL indisponível, reduced motion e snapshot sem capability.

- [ ] **Step 2: Rodar RED**

Run: `npm.cmd run test:run -- src/components/Twin3D.test.jsx src/components/twin3d/Twin3DCanvas.test.jsx`

Expected: FAIL porque o canvas atual só mostra o estado visual provisório.

- [ ] **Step 3: Implementar cena real**

Use `<Canvas dpr={[1,1.5]}>`, luz ambiente/direcional, `<Bounds fit clip observe margin={1.2}>`, primitive clonado do GLB, `<OrbitControls makeDefault enablePan={false}/>` e cor de destaque global somente por `snapshot.status`. Não anime vibração ou rotação inexistente.

- [ ] **Step 4: Rodar GREEN, build e orçamento**

Run: `npm.cmd run test:run -- src/components/Twin3D.test.jsx src/components/twin3d`

Run: `npm.cmd run build:manifest`

Expected: PASS; Twin3D permanece lazy; GLB estático ≤20 MB; chunk 3D não entra no entry principal antes da abertura do componente.

- [ ] **Step 5: Commit**

```powershell
git add src/components/Twin3D.jsx src/components/Twin3D.test.jsx src/components/twin3d
git commit -m "feat: render supplied motor pump model"
```
