# Real TwinOps Contract V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Congelar contratos v2 honestos para identidade, telemetria, avaliação e snapshot do único ativo real.

**Architecture:** JSON Schema permanece a autoridade neutra. Modelos Pydantic e validator JS projetam a mesma estrutura, sem alterar v1 durante a migração; consumidores novos usam somente v2.

**Tech Stack:** JSON Schema draft-07, Ajv 8, JavaScript ESM, Pydantic 2, Vitest e pytest.

**Spec:** `docs/superpowers/specs/2026-08-13-forzy-twinops-real-vercel-zero-cost-design.md`

## Global Constraints

- Base: `d1e919f0fab40b2d504ae00d2ad719899e26b7a2`.
- `schemaVersion` público é exatamente `2.0`.
- `assetId="forzy-motor-01"`, `displayName="Conjunto motor-bomba monitorado"`, `officialTag=null`.
- Não renomear nem apagar `contracts/v1/**`; v1 permanece para testes históricos até o plano 03 remover seus consumidores.
- Live exige exatamente um canal `s1` e um `s2`.
- `observedAt=receivedAt`, `timestampQuality="assumed_from_retrieval"`, `sourceTimestampProvided=false` para Forzy live.
- `operationalState` é `received_now|last_known|expected_idle|unavailable`; `freshnessBasis` é `retrieval_time|last_received|schedule|none`.
- Zero é válido; NaN/infinito/string numérica não são válidos.
- Snapshot não contém raw, hostname upstream, segredo ou campo chamado `assetTag`.

## Mapa de arquivos

- `contracts/v2/*.schema.json`: quatro schemas normativos.
- `contracts/v2/fixtures/*.json`: fixtures partilhadas por Python e JS.
- `services/twinops/src/twinops/contracts/v2_models.py`: modelos estritos.
- `services/twinops/src/twinops/contracts/v2_projections.py`: audit reading para frame público.
- `src/contracts/twinV2.js`: validação estrutural runtime sem Ajv no bundle.
- `src/contracts/*V2.test.*`: paridade e casos negativos.

---

### Task 1: Schemas e fixtures normativos v2

**Files:**
- Create: `contracts/v2/canonical-sensor-reading.schema.json`
- Create: `contracts/v2/sensor-telemetry-frame.schema.json`
- Create: `contracts/v2/asset-condition-assessment.schema.json`
- Create: `contracts/v2/digital-twin-snapshot.schema.json`
- Create: `contracts/v2/fixtures/canonical-live-s1.valid.json`
- Create: `contracts/v2/fixtures/snapshot-received-now.valid.json`
- Create: `contracts/v2/fixtures/snapshot-last-known.valid.json`
- Create: `contracts/v2/fixtures/snapshot-asset-tag.invalid.json`
- Create: `contracts/v2/fixtures/canonical-source-time.invalid.json`
- Test: `src/contracts/schemaV2.test.js`

**Interfaces:**
- Produces: `$id` `forzy://contracts/v2/{canonical-sensor-reading|sensor-telemetry-frame|asset-condition-assessment|digital-twin-snapshot}`.
- Produces: fixture UUIDs estáveis e timestamps UTC usados por todos os planos.

- [ ] **Step 1: Escrever o teste Ajv antes dos schemas**

```js
import { readFileSync } from "node:fs";
import Ajv from "ajv";
import { expect, it } from "vitest";

const json = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));

it("accepts v2 and rejects the invented assetTag boundary", () => {
  const ajv = new Ajv({ allErrors: true, strict: true, schemas: [
    json("../../contracts/v2/canonical-sensor-reading.schema.json"),
    json("../../contracts/v2/sensor-telemetry-frame.schema.json"),
    json("../../contracts/v2/asset-condition-assessment.schema.json"),
  ]});
  const validate = ajv.compile(json("../../contracts/v2/digital-twin-snapshot.schema.json"));
  expect(validate(json("../../contracts/v2/fixtures/snapshot-received-now.valid.json"))).toBe(true);
  expect(validate(json("../../contracts/v2/fixtures/snapshot-asset-tag.invalid.json"))).toBe(false);
});
```

- [ ] **Step 2: Executar RED**

Run: `npm.cmd run test:run -- src/contracts/schemaV2.test.js`

Expected: FAIL com `ENOENT` para `contracts/v2`.

- [ ] **Step 3: Criar os schemas fechados**

Use `additionalProperties:false` em todos os objetos. O reading canônico deve exigir:

```json
{
  "schemaVersion": "2.0",
  "readingId": "uuid",
  "source": "forzy-live",
  "assetId": "forzy-motor-01",
  "sensorId": "s1",
  "scheduledAt": "date-time",
  "observedAt": "date-time",
  "receivedAt": "date-time",
  "timestampQuality": "assumed_from_retrieval",
  "measurements": {},
  "qualityFlags": [],
  "payloadHash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "raw": {},
  "provenance": {"sourceSystem":"forzy-api","ingestedAt":"date-time","sourceTimestampProvided":false}
}
```

O snapshot exige `asset`, `generatedAt`, `status`, `operationalState`, `freshnessBasis`, `channels`, `history`, `assessment`, `integration` e `capabilities`. `integration.sensors` possui health de s1/s2. `capabilities` fixa `liveUpdates:true`, `replayControls:false`, `copilot:false` e `twin3d:boolean`.

- [ ] **Step 4: Executar GREEN**

Run: `npm.cmd run test:run -- src/contracts/schemaV2.test.js`

Expected: PASS; as duas fixtures inválidas retornam false.

- [ ] **Step 5: Commit**

```powershell
git add contracts/v2 src/contracts/schemaV2.test.js
git commit -m "test: freeze real twin contract v2"
```

### Task 2: Modelos Pydantic v2 e invariantes temporais

**Files:**
- Create: `services/twinops/src/twinops/contracts/v2_models.py`
- Test: `services/twinops/tests/contracts/test_v2_models.py`

**Interfaces:**
- Produces: `AssetIdentityV2`, `CanonicalSensorReadingV2`, `SensorTelemetryFrameV2`, `AssetConditionAssessmentV2`, `DigitalTwinSnapshotV2`.
- Produces: `model_dump(mode="json", by_alias=True)` idêntico às fixtures.

- [ ] **Step 1: Escrever testes de round-trip e coerência**

```python
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from twinops.contracts.v2_models import CanonicalSensorReadingV2, DigitalTwinSnapshotV2

FIXTURES = Path("contracts/v2/fixtures")

def payload(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

def test_live_round_trip_preserves_assumed_retrieval_time():
    body = payload("canonical-live-s1.valid.json")
    model = CanonicalSensorReadingV2.model_validate(body)
    assert model.observed_at == model.received_at
    assert model.model_dump(mode="json", by_alias=True) == body

def test_source_timestamp_claim_is_rejected():
    with pytest.raises(ValidationError):
        CanonicalSensorReadingV2.model_validate(payload("canonical-source-time.invalid.json"))

def test_snapshot_rejects_asset_tag():
    with pytest.raises(ValidationError):
        DigitalTwinSnapshotV2.model_validate(payload("snapshot-asset-tag.invalid.json"))
```

- [ ] **Step 2: Executar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/contracts/test_v2_models.py -v`

Expected: FAIL com `ModuleNotFoundError: twinops.contracts.v2_models`.

- [ ] **Step 3: Implementar modelos estritos**

Use `ConfigDict(extra="forbid", strict=True, populate_by_name=True, allow_inf_nan=False)`. Em `CanonicalSensorReadingV2`, aplique:

```python
@model_validator(mode="after")
def live_time_is_explicitly_assumed(self) -> Self:
    if self.source == "forzy-live":
        if self.observed_at != self.received_at:
            raise ValueError("Forzy live observedAt must equal receivedAt")
        if self.timestamp_quality != "assumed_from_retrieval":
            raise ValueError("Forzy live timestampQuality must be assumed_from_retrieval")
        if self.provenance.source_timestamp_provided:
            raise ValueError("Forzy live source timestamp was not provided")
    return self
```

Em `DigitalTwinSnapshotV2`, valide identidade única e exatamente s1/s2 sem duplicatas.

- [ ] **Step 4: Executar GREEN e regressão v1**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/contracts -v`

Expected: PASS; testes v1 continuam verdes.

- [ ] **Step 5: Commit**

```powershell
git add services/twinops/src/twinops/contracts/v2_models.py services/twinops/tests/contracts/test_v2_models.py
git commit -m "feat: add real twin contract v2 models"
```

### Task 3: Projeção pública e validator runtime JS

**Files:**
- Create: `services/twinops/src/twinops/contracts/v2_projections.py`
- Create: `src/contracts/twinV2.js`
- Test: `services/twinops/tests/contracts/test_v2_projections.py`
- Test: `src/contracts/twinV2.test.js`

**Interfaces:**
- Produces: `to_sensor_telemetry_frame_v2(reading: CanonicalSensorReadingV2) -> SensorTelemetryFrameV2`.
- Produces: `SCHEMA_VERSION_V2`, `assertDigitalTwinSnapshotV2(value)`, `isDigitalTwinSnapshotV2(value)`.

- [ ] **Step 1: Escrever testes negativos antes das implementações**

```python
def test_projection_removes_audit_fields(valid_live_reading_v2):
    frame = to_sensor_telemetry_frame_v2(valid_live_reading_v2)
    body = frame.model_dump(mode="json", by_alias=True)
    assert body["observedAt"] == body["receivedAt"]
    assert body["timestampQuality"] == "assumed_from_retrieval"
    assert "raw" not in body and "payloadHash" not in body and "provenance" not in body
```

```js
it("rejects a plausible snapshot with a source timestamp claim", () => {
  const value = fixture();
  value.channels[0].timestampQuality = "source";
  expect(() => assertDigitalTwinSnapshotV2(value)).toThrow(/timestampQuality/);
});
```

- [ ] **Step 2: Executar RED em Python e JS**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/contracts/test_v2_projections.py -v`

Run: `npm.cmd run test:run -- src/contracts/twinV2.test.js`

Expected: ambos FAIL por imports ausentes.

- [ ] **Step 3: Implementar projeção e validator fechado**

A projeção copia somente os campos do frame. O validator JS deve verificar chaves extras, finitude, asset exato, timestamps iguais, dois canais, health s1/s2, a chave obrigatória `assessment` aceitando objeto válido ou `null`, e capabilities. Não importar Ajv ou JSON em produção.

- [ ] **Step 4: Executar GREEN e paridade**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/contracts -q`

Run: `npm.cmd run test:run -- src/contracts/schemaV2.test.js src/contracts/twinV2.test.js`

Expected: PASS; validator runtime aceita as duas fixtures válidas que Ajv aceita.

- [ ] **Step 5: Commit**

```powershell
git add services/twinops/src/twinops/contracts/v2_projections.py services/twinops/tests/contracts/test_v2_projections.py src/contracts/twinV2.js src/contracts/twinV2.test.js
git commit -m "feat: expose real twin v2 projections"
```

### Task 4: Gate final e documentação de migração

**Files:**
- Create: `contracts/v2/README.md`
- Modify: `docs/superpowers/specs/README.md`

**Interfaces:**
- Produces: regra de migração v1→v2 consumida pelos planos 02–05.

- [ ] **Step 1: Documentar a fronteira exata**

Inclua tabela: `assetTag→asset.assetId`, `observedAt:null→observedAt=receivedAt`, `timestampQuality:collector→assumed_from_retrieval`, `freshness→operationalState+freshnessBasis`, `mode→removido`, `raw→somente contrato canônico`.

- [ ] **Step 2: Rodar todos os gates de contrato**

Run: `npm.cmd run test:run -- src/contracts/schema.test.js src/contracts/schemaV2.test.js src/contracts/twin.test.js src/contracts/twinV2.test.js`

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/contracts -q`

Run: `rg -n 'TBD|TODO|FIXME' contracts/v2 docs/superpowers/specs/README.md`

Expected: testes PASS; busca sem resultados.

- [ ] **Step 3: Commit**

```powershell
git add contracts/v2/README.md docs/superpowers/specs/README.md
git commit -m "docs: define twin contract v2 migration"
```
