# Contratos e base de integração — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Congelar schemas e fixtures v1, adaptar o replay atual a `TwinSnapshot` e criar a fronteira de data source consumida pelos workers paralelos.

**Architecture:** JSON Schemas em uma pasta neutra são a fonte normativa. O frontend usa adapters puros para converter o loop existente e respostas do gateway ao mesmo snapshot; `LiveTwinContext` preserva a API antiga durante a migração, mas passa a expor `snapshot` como nova fonte de integração.

**Tech Stack:** React 18, JavaScript ESM, Vitest, Ajv, Vite 5; Python 3.11+, Pydantic 2, FastAPI, httpx, NumPy, pandas, scikit-learn e pytest.

## Global Constraints

- Basear o trabalho no commit `1f21f264f88d7a64fecc37e3b3e620eb46d35587` mais o commit das specs.
- Nunca usar o campo ambíguo `vibration` nos contratos v1.
- `receivedAt` não representa horário de aquisição; `observedAt` live permanece nulo.
- S1 e S2 permanecem canais separados; nenhuma média implícita.
- Replay deve continuar determinístico e funcional offline.
- Nenhum endpoint upstream ou segredo pode entrar no bundle.
- Alteração incompatível exige novo `schemaVersion`; não alterar v1 silenciosamente.

## Mapa de arquivos

- `contracts/v1/*.schema.json`: schemas normativos.
- `contracts/v1/fixtures/*.json`: exemplos válidos e inválidos comuns.
- `src/contracts/twin.js`: constantes e validação de fronteira.
- `src/dataSources/TwinDataSource.js`: protocolo documentado dos providers.
- `src/dataSources/ReplayTwinDataSource.js`: tradução do mock/live atual.
- `src/dataSources/GatewayTwinDataSource.js`: acesso same-origin à API v1.
- `src/LiveTwinContext.jsx`: compatibilidade e exposição do snapshot.
- `src/**/*.test.js`: testes de contrato/adapters.

---

### Task 1: Infraestrutura de testes e schemas normativos

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json`
- Create: `vitest.config.js`
- Create: `contracts/v1/telemetry-sample.schema.json`
- Create: `contracts/v1/detection-assessment.schema.json`
- Create: `contracts/v1/twin-snapshot.schema.json`
- Create: `contracts/v1/fixtures/telemetry-live-s1.valid.json`
- Create: `contracts/v1/fixtures/twin-snapshot-replay.valid.json`
- Create: `contracts/v1/fixtures/twin-snapshot-live.valid.json`
- Create: `contracts/v1/fixtures/telemetry-string.invalid.json`
- Test: `src/contracts/schema.test.js`

**Interfaces:**
- Produces: JSON Schemas com `$id` `forzy://contracts/v1/{name}` e fixtures usadas por todos os pacotes.
- Produces: scripts `test` e `test:run` em `package.json`.

- [ ] **Step 1: Instalar somente o necessário para validar contratos**

Run: `npm.cmd install ajv@^8.17.1`

Run: `npm.cmd install --save-dev vitest@^2.1.9`

Run: `npm.cmd install --save-dev @testing-library/react@^16.1.0 jsdom@^25.0.1`

Expected: lockfile atualizado sem upgrade deliberado de React, Vite ou Recharts;
`vitest.config.js` usa ambiente `jsdom` apenas para testes `*.test.jsx`.

- [ ] **Step 2: Escrever o teste de schema antes dos schemas**

```js
import { readFileSync } from "node:fs";
import Ajv from "ajv";
import { describe, expect, it } from "vitest";

const json = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));

describe("contracts/v1", () => {
  it("accepts canonical live telemetry and rejects numeric strings", () => {
    const ajv = new Ajv({ allErrors: true, strict: true });
    const validate = ajv.compile(json("../../contracts/v1/telemetry-sample.schema.json"));
    expect(validate(json("../../contracts/v1/fixtures/telemetry-live-s1.valid.json"))).toBe(true);
    expect(validate(json("../../contracts/v1/fixtures/telemetry-string.invalid.json"))).toBe(false);
  });
});
```

- [ ] **Step 3: Confirmar falha inicial**

Run: `npm.cmd run test:run -- src/contracts/schema.test.js`

Expected: FAIL porque schemas/fixtures ainda não existem.

- [ ] **Step 4: Criar schemas fechados e fixtures exatas da spec**

Use `additionalProperties: false`; números usam `type: "number"`; `observedAt`
aceita string ISO ou null; enums e nomes de propriedades devem coincidir com o
pacote 00. O snapshot live válido deve conter dois itens em `channels` e não
deve conter `currentA`, `rotationRpm` nem o campo `vibration`.

- [ ] **Step 5: Rodar teste e build**

Run: `npm.cmd run test:run -- src/contracts/schema.test.js`

Expected: PASS.

Run: `npm.cmd run build`

Expected: PASS; warning preexistente de chunk maior que 500 kB pode permanecer.

- [ ] **Step 6: Commit**

```bash
git add package.json package-lock.json vitest.config.js contracts src/contracts/schema.test.js
git commit -m "test: freeze twin contract v1"
```

### Task 2: Modelos Pydantic compartilhados

**Files:**
- Create: `services/twinops/pyproject.toml`
- Create: `services/twinops/src/twinops/__init__.py`
- Create: `services/twinops/src/twinops/contracts/__init__.py`
- Create: `services/twinops/src/twinops/contracts/models.py`
- Test: `services/twinops/tests/contracts/test_models.py`

**Interfaces:**
- Produces: `TelemetrySample`, `DetectionAssessment`, `TwinSnapshot` como modelos Pydantic.
- Produces: serialização pública `model_dump(mode="json", by_alias=True)` compatível com os schemas v1.
- Produces: dependências compartilhadas Pydantic 2, FastAPI, Uvicorn, httpx,
  NumPy, pandas e scikit-learn; extra `dev` com pytest e pytest-asyncio. Os
  workers 01, 02 e 04 não modificam `pyproject.toml` em paralelo.

- [ ] **Step 1: Criar teste parametrizado sobre as fixtures JSON**

```python
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from twinops.contracts.models import TelemetrySample, TwinSnapshot

FIXTURES = Path("contracts/v1/fixtures")

def test_valid_live_sample_round_trips_with_aliases():
    payload = json.loads((FIXTURES / "telemetry-live-s1.valid.json").read_text(encoding="utf-8"))
    model = TelemetrySample.model_validate(payload)
    assert model.model_dump(mode="json", by_alias=True) == payload

def test_numeric_string_is_rejected():
    payload = json.loads((FIXTURES / "telemetry-string.invalid.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        TelemetrySample.model_validate(payload)
```

- [ ] **Step 2: Confirmar falha inicial**

Run: `python -m pytest services/twinops/tests/contracts/test_models.py -v`

Expected: FAIL porque pacote/modelos ainda não existem.

- [ ] **Step 3: Criar bootstrap Python e modelos estritos**

Use aliases camelCase, `ConfigDict(extra="forbid", strict=True,
populate_by_name=True)` e enums literais compatíveis com os JSON Schemas. Não
duplicar regras com conversões permissivas.

- [ ] **Step 4: Instalar editável e rodar testes**

Run: `python -m venv services/twinops/.venv`

Run: `services/twinops/.venv/Scripts/python -m pip install -e "services/twinops[dev]"`

Run: `services/twinops/.venv/Scripts/python -m pytest services/twinops/tests/contracts/test_models.py -v`

Expected: PASS para fixtures válidas e inválidas.

- [ ] **Step 5: Commit**

```bash
git add services/twinops contracts
git commit -m "feat: add shared Python twin contracts"
```

### Task 3: Validadores frontend e protocolo `TwinDataSource`

**Files:**
- Create: `src/contracts/twin.js`
- Create: `src/contracts/twin.test.js`
- Create: `src/dataSources/TwinDataSource.js`
- Test: `src/dataSources/TwinDataSource.test.js`

**Interfaces:**
- Produces: `SCHEMA_VERSION`, `assertTwinSnapshot(value)`, `isTwinSnapshot(value)`.
- Produces: `createTwinDataSource({ getSnapshot, subscribe, capabilities })`.
- Produces: data source com `getSnapshot(assetTag): Promise<TwinSnapshot>`, `subscribe(assetTag, listener): () => void` e `capabilities` imutável.

- [ ] **Step 1: Escrever testes da fronteira pública**

```js
import { expect, it, vi } from "vitest";
import { assertTwinSnapshot } from "./twin.js";
import { createTwinDataSource } from "../dataSources/TwinDataSource.js";

it("rejects an unknown schema version", () => {
  expect(() => assertTwinSnapshot({ schemaVersion: "2.0" })).toThrow(/schemaVersion/);
});

it("delegates getSnapshot without exposing mutable capabilities", async () => {
  const getSnapshot = vi.fn().mockResolvedValue({ schemaVersion: "1.0" });
  const source = createTwinDataSource({ getSnapshot, subscribe: () => () => {}, capabilities: { liveUpdates: true } });
  await source.getSnapshot("MTR-BMB-042");
  expect(getSnapshot).toHaveBeenCalledWith("MTR-BMB-042");
  expect(Object.isFrozen(source.capabilities)).toBe(true);
});
```

- [ ] **Step 2: Confirmar falha inicial**

Run: `npm.cmd run test:run -- src/contracts/twin.test.js src/dataSources/TwinDataSource.test.js`

Expected: FAIL por módulos ausentes.

- [ ] **Step 3: Implementar validação mínima e protocolo**

`assertTwinSnapshot` valida versão, `assetTag`, `mode`, `status`, `freshness`,
arrays `channels/history` e objeto `capabilities`, retornando o próprio objeto.
Não duplicar Ajv no bundle: Ajv permanece nos testes; a validação runtime é uma
fronteira pequena e explícita.

- [ ] **Step 4: Rodar testes**

Run: `npm.cmd run test:run -- src/contracts/twin.test.js src/dataSources/TwinDataSource.test.js`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contracts src/dataSources
git commit -m "feat: add twin data source contract"
```

### Task 4: Adapter determinístico de replay

**Files:**
- Create: `src/dataSources/ReplayTwinDataSource.js`
- Test: `src/dataSources/ReplayTwinDataSource.test.js`

**Interfaces:**
- Consumes: estado retornado por `useLiveTelemetry` e selectors existentes do mock.
- Produces: `buildReplaySnapshot({ assetTag, live, reading, status, scenario, risk }): TwinSnapshot`.

- [ ] **Step 1: Criar teste com um tick fixo**

```js
import { expect, it } from "vitest";
import { buildReplaySnapshot } from "./ReplayTwinDataSource.js";

it("maps the legacy vibration acceleration without calling it RMS velocity", () => {
  const snapshot = buildReplaySnapshot({
    assetTag: "MTR-BMB-042",
    live: { points: [], running: true },
    reading: { ts: "2026-08-12T15:00:00.000Z", temperature: 34, vibration: 2.1, current: 17, rotation: 1760 },
    status: "normal",
    scenario: null,
    risk: { level: "Baixo", score: 12 }
  });
  expect(snapshot.mode).toBe("replay");
  expect(snapshot.channels[0].measurements.vibrationAcceleration.value).toBe(2.1);
  expect(snapshot.channels[0].measurements.vibrationVelocityRms).toBeNull();
});
```

- [ ] **Step 2: Confirmar falha, implementar e retestar**

Run: `npm.cmd run test:run -- src/dataSources/ReplayTwinDataSource.test.js`

Expected before implementation: FAIL por módulo ausente. Expected after:
PASS com timestamps e status determinísticos para a fixture.

- [ ] **Step 3: Cobrir alert, campos ausentes e controles**

Adicionar testes para `capabilities.replayControls=true`, avaliação relativa de
replay explicitamente marcada `demo_scenario_not_model_inference`, e valores
ausentes preservados como null.

- [ ] **Step 4: Commit**

```bash
git add src/dataSources/ReplayTwinDataSource.js src/dataSources/ReplayTwinDataSource.test.js
git commit -m "feat: adapt deterministic replay to twin snapshot"
```

### Task 5: Gateway data source e integração compatível no contexto

**Files:**
- Create: `src/dataSources/GatewayTwinDataSource.js`
- Test: `src/dataSources/GatewayTwinDataSource.test.js`
- Modify: `src/LiveTwinContext.jsx`
- Test: `src/LiveTwinContext.test.jsx`

**Interfaces:**
- Produces: `createGatewayTwinDataSource({ baseUrl = "", fetchImpl = fetch, pollMs = 5000 })`.
- Produces: `snapshot` e `dataMode` no valor de `useLiveTwin()`.
- Preserves: `statusOf`, `readingOf`, `riskOf`, `alertOf`, `alertsList` durante a migração.

- [ ] **Step 1: Testar same-origin, validação e cancelamento**

O teste deve exigir URL `/api/v1/twin/assets/MTR-BMB-042/snapshot`, rejeitar
schema inválido, provar que `unsubscribe()` interrompe o timer e usar fake timers
do Vitest.

- [ ] **Step 2: Confirmar falha inicial**

Run: `npm.cmd run test:run -- src/dataSources/GatewayTwinDataSource.test.js`

Expected: FAIL por módulo ausente.

- [ ] **Step 3: Implementar polling sem endpoint externo hardcoded**

Use `AbortController` por request; uma falha chama o listener com erro sem criar
snapshot normal falso; `baseUrl` vazio mantém same-origin.

- [ ] **Step 4: Integrar replay no `LiveTwinContext`**

Gerar `snapshot` com `buildReplaySnapshot` a partir do estado já calculado. Não
remover selectors legados neste commit. O modo gateway será selecionado em tarefa
de integração posterior quando o backend estiver presente.

- [ ] **Step 5: Rodar testes e build**

Run: `npm.cmd run test:run`

Expected: todos os testes PASS.

Run: `npm.cmd run build`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dataSources/GatewayTwinDataSource.js src/dataSources/GatewayTwinDataSource.test.js src/LiveTwinContext.jsx src/LiveTwinContext.test.jsx
git commit -m "feat: expose canonical twin snapshot"
```
