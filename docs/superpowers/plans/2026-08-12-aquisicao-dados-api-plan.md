# Aquisição de Dados e API Canônica Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir a trilha real de aquisição do Forzy TwinOps, com coleta isolada de S1/S2, importação CSV idempotente, persistência auditável em SQLite e API canônica sem expor o upstream.

**Architecture:** Um único serviço Python modular usa adapters puros para converter live/CSV em `CanonicalSensorReading`, um repositório SQLite append-only atrás de um `Protocol`, e um coletor assíncrono que consulta os sensores em paralelo apenas na janela configurada. FastAPI expõe snapshot, histórico e health; o React nunca acessa o hostname upstream nem os registros raw.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLite 3 em modo WAL, `httpx`, `pytest`, `pytest-asyncio`, SQL parametrizado, sem ORM e sem infraestrutura cloud.

## Global Constraints

- Trabalhar em clone/worktree do repositório `9luis7/forzy-twinops`, branch-base `main`, SHA-base `1f21f264f88d7a64fecc37e3b3e620eb46d35587`; confirmar conscientemente qualquer avanço da `main` antes de integrar.
- Python 3.11+ e serviço HTTP modular; FastAPI é o default.
- SQLite em modo WAL no demonstrador, com interface de repositório que permita Postgres depois.
- Não adicionar infraestrutura cloud, Redis, fila, TimescaleDB, Kafka, Kubernetes ou ORM.
- Polling padrão de 5 segundos, configurável por `TWINOPS_POLL_INTERVAL_SECONDS`.
- Timeout padrão de 2 segundos e no máximo um retry curto com jitter.
- Janela padrão `America/Sao_Paulo`, seg/ter/qua, `[12:00, 14:00)`.
- O hostname upstream existe somente em `TWINOPS_UPSTREAM_BASE_URL`; nunca aparece no bundle frontend, resposta pública ou mensagem de erro sanitizada.
- `observedAt` permanece nulo no live; `receivedAt` nunca é descrito como horário real da medição.
- Zero é válido; campo ausente, string, `null`, `NaN` ou infinito invalida somente a amostra daquele sensor.
- Aceleração usa `statistic="unknown"` e `semanticConfidence="unconfirmed"`; não entra no score oficial.
- S1 e S2 permanecem canais separados; não calcular média implícita nem afirmar posição física.
- Cada payload recebido é preservado em `raw_readings`, inclusive duplicatas; retry do mesmo slot não cria segunda amostra canônica e retorna `duplicate`.
- O frontend não recebe o objeto `raw`; live e CSV usam a mesma consulta sem perder `source`.
- Smoke contra endpoints reais é opt-in e separado dos testes determinísticos.
- Não editar `src/**`, scoring/ML, prompt/LLM, artefatos 3D nem `services/twinops/contracts/**`; contratos e fixtures pertencem ao pacote 00.

---

## Mapa de arquivos

| Arquivo | Responsabilidade |
| --- | --- |
| `services/twinops/pyproject.toml` | Bootstrap e dependências fornecidos pelo pacote 00; somente consumido. |
| `services/twinops/src/twinops/config.py` | Configuração server-side validada a partir de env. |
| `services/twinops/src/twinops/ingestion/live_adapter.py` | Validar payload `dados1`/`dados2` e produzir contrato canônico. |
| `services/twinops/src/twinops/ingestion/schedule.py` | Determinar slots e `expected_idle` em `America/Sao_Paulo`. |
| `services/twinops/src/twinops/ingestion/upstream.py` | GET assíncrono, timeout e erro interno sanitizável. |
| `services/twinops/src/twinops/ingestion/collector.py` | Consultar S1/S2 em paralelo, retry limitado e persistência isolada. |
| `services/twinops/src/twinops/ingestion/csv_importer.py` | Importar CSV por hash/linha/sensor sem duplicar. |
| `services/twinops/src/twinops/storage/repository.py` | `Protocol` estável e tipos de query/health. |
| `services/twinops/src/twinops/storage/sqlite_repository.py` | Schema, WAL, gravação append-only e consultas parametrizadas. |
| `services/twinops/src/twinops/api/telemetry_routes.py` | Snapshot e histórico canônicos. |
| `services/twinops/src/twinops/api/health_routes.py` | Health sanitizado por sensor. |
| `services/twinops/src/twinops/main.py` | Compor dependências e ciclo de vida FastAPI/collector. |
| `services/twinops/src/twinops/cli.py` | Comandos `serve`, `collect` e `import-csv`. |
| `services/twinops/tests/ingestion/**` | Testes de adapters, agenda, upstream, collector e CSV. |
| `services/twinops/tests/storage/**` | Testes de schema, idempotência, WAL e queries. |
| `services/twinops/tests/api/**` | Testes HTTP de histórico, snapshot, health e sanitização. |
| `services/twinops/tests/smoke/test_forzy_live.py` | Smoke real desabilitado por padrão. |

## Interfaces compartilhadas exatas

O pacote 00 deve fornecer, e este plano somente consome:

```python
from twinops.contracts.models import CanonicalSensorReading, SensorTelemetryFrame, DigitalTwinSnapshot
from twinops.contracts.projections import to_sensor_telemetry_frame

CanonicalSensorReading.model_validate(data: dict[str, object]) -> CanonicalSensorReading
CanonicalSensorReading.model_dump(mode="json", by_alias=True) -> dict[str, object]
SensorTelemetryFrame.model_validate(data: dict[str, object]) -> SensorTelemetryFrame
DigitalTwinSnapshot.model_validate(data: dict[str, object]) -> DigitalTwinSnapshot
to_sensor_telemetry_frame(reading: CanonicalSensorReading) -> SensorTelemetryFrame
```

`CanonicalSensorReading` usa os aliases JSON normativos `schemaVersion`, `readingId`,
`assetTag`, `sensorId`, `scheduledAt`, `receivedAt`, `observedAt`, `measurements`,
`qualityFlags`, `payloadHash`, `raw` e `provenance`. `SensorTelemetryFrame` é a
projeção consumer-safe do endpoint: não contém `raw` e usa métricas `null` quando
indisponíveis. Essa projeção deve ser criada exclusivamente por
`to_sensor_telemetry_frame`; não se remove apenas `raw` de um dump canônico. Se o pacote 00 entregar
outro caminho de import, o integrador deve alinhar o import antes da execução;
o worker do pacote 01 não duplica nem altera o modelo.

### Task 1: Adapter live puro sobre o bootstrap do pacote 00

**Files:**
- Create: `services/twinops/src/twinops/config.py`
- Create: `services/twinops/src/twinops/ingestion/__init__.py`
- Create: `services/twinops/src/twinops/ingestion/live_adapter.py`
- Test: `services/twinops/tests/ingestion/test_live_adapter.py`

**Interfaces:**
- Consumes: `CanonicalSensorReading.model_validate(data)` do pacote 00.
- Produces: `Settings.from_env(env: Mapping[str, str]) -> Settings`; `adapt_live_payload(*, sensor_id: Literal["s1", "s2"], payload: Mapping[str, object], scheduled_at: datetime, received_at: datetime, asset_tag: str) -> CanonicalSensorReading`; `InvalidSensorPayload(sensor_id: str, reason: str)`.

- [ ] **Step 1: Escrever o teste falhando para payload válido, zero e validação estrita**

```python
from datetime import datetime, timezone
import pytest
from twinops.ingestion.live_adapter import InvalidSensorPayload, adapt_live_payload

SLOT = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
RECEIVED = datetime(2026, 8, 12, 15, 0, 1, tzinfo=timezone.utc)

def test_adapts_exact_s1_payload_and_preserves_zero_and_raw():
    raw = {"dados1": {"Velocidade": 0.04, "Aceleração": 0.0, "Temperatura": 34}}
    sample = adapt_live_payload(sensor_id="s1", payload=raw, scheduled_at=SLOT,
                                received_at=RECEIVED, asset_tag="MTR-BMB-042")
    body = sample.model_dump(mode="json", by_alias=True)
    assert body["source"] == "forzy-live"
    assert body["scheduledAt"] == SLOT.isoformat().replace("+00:00", "Z")
    assert body["observedAt"] is None
    assert body["receivedAt"] == RECEIVED.isoformat().replace("+00:00", "Z")
    assert body["measurements"]["vibrationVelocityRms"]["value"] == 0.04
    assert body["measurements"]["vibrationAcceleration"]["value"] == 0.0
    assert body["measurements"]["vibrationAcceleration"]["statistic"] == "unknown"
    assert body["raw"] == raw
    assert body["payloadHash"].startswith("sha256:")
    assert len(body["payloadHash"]) == 71
    assert body["provenance"] == {
        "sourceSystem": "forzy-api",
        "ingestedAt": body["receivedAt"],
    }

@pytest.mark.parametrize("bad", [None, "0.04", float("inf"), float("nan")])
def test_rejects_non_finite_or_non_numeric_velocity(bad):
    with pytest.raises(InvalidSensorPayload, match="Velocidade"):
        adapt_live_payload(sensor_id="s2", payload={"dados2": {
            "Velocidade": bad, "Aceleração": 0.0, "Temperatura": 35}},
            scheduled_at=SLOT, received_at=RECEIVED, asset_tag="MTR-BMB-042")
```

- [ ] **Step 2: Instalar o bootstrap fornecido pelo pacote 00 e verificar a falha**

Run: `python -m venv .venv; .venv/Scripts/python -m pip install -e "services/twinops[dev]"; .venv/Scripts/python -m pytest services/twinops/tests/ingestion/test_live_adapter.py -v`

Expected: FAIL na coleta com `ModuleNotFoundError: No module named 'twinops.ingestion.live_adapter'`.

- [ ] **Step 3: Implementar configuração e adapter mínimos**

```python
# config.py
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

@dataclass(frozen=True)
class Settings:
    upstream_base_url: str
    database_path: Path = Path("var/twinops.sqlite3")
    asset_tag: str = "MTR-BMB-042"
    poll_interval_seconds: float = 5.0
    request_timeout_seconds: float = 2.0
    timezone_name: str = "America/Sao_Paulo"

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        url = env.get("TWINOPS_UPSTREAM_BASE_URL", "").rstrip("/")
        if not url.startswith("https://"):
            raise ValueError("TWINOPS_UPSTREAM_BASE_URL must use https")
        interval = float(env.get("TWINOPS_POLL_INTERVAL_SECONDS", "5"))
        timeout = float(env.get("TWINOPS_REQUEST_TIMEOUT_SECONDS", "2"))
        if interval <= 0 or timeout <= 0:
            raise ValueError("poll interval and timeout must be positive")
        return cls(url, Path(env.get("TWINOPS_DATABASE_PATH", "var/twinops.sqlite3")),
                   env.get("TWINOPS_ASSET_TAG", "MTR-BMB-042"), interval, timeout,
                   env.get("TWINOPS_TIMEZONE", "America/Sao_Paulo"))
```

```python
# live_adapter.py
from datetime import datetime
import hashlib, json, math, uuid
from typing import Literal, Mapping
from twinops.contracts.models import CanonicalSensorReading

class InvalidSensorPayload(ValueError):
    def __init__(self, sensor_id: str, reason: str):
        super().__init__(f"invalid payload for {sensor_id}: {reason}")
        self.sensor_id, self.reason = sensor_id, reason

def _number(data: Mapping[str, object], key: str, sensor_id: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InvalidSensorPayload(sensor_id, f"{key} must be a finite number")
    return float(value)

def adapt_live_payload(*, sensor_id: Literal["s1", "s2"], payload: Mapping[str, object],
                       scheduled_at: datetime, received_at: datetime,
                       asset_tag: str) -> CanonicalSensorReading:
    root = f"dados{sensor_id[-1]}"
    values = payload.get(root)
    if not isinstance(values, Mapping):
        raise InvalidSensorPayload(sensor_id, f"{root} must be an object")
    canonical_raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode()
    data = {"schemaVersion": "1.0", "readingId": str(uuid.uuid4()),
            "source": "forzy-live", "assetTag": asset_tag, "sensorId": sensor_id,
            "scheduledAt": scheduled_at.isoformat().replace("+00:00", "Z"),
            "receivedAt": received_at.isoformat().replace("+00:00", "Z"),
            "observedAt": None,
            "measurements": {
                "vibrationVelocityRms": {"value": _number(values, "Velocidade", sensor_id),
                    "unit": "mm/s", "semanticConfidence": "inferred_from_datasheet"},
                "vibrationAcceleration": {"value": _number(values, "Aceleração", sensor_id),
                    "unit": "g", "statistic": "unknown", "semanticConfidence": "unconfirmed"},
                "temperature": {"value": _number(values, "Temperatura", sensor_id),
                    "unit": "degC", "semanticConfidence": "inferred_from_datasheet"}},
            "qualityFlags": [],
            "payloadHash": f"sha256:{hashlib.sha256(canonical_raw).hexdigest()}",
            "raw": payload,
            "provenance": {"sourceSystem": "forzy-api",
                "ingestedAt": received_at.isoformat().replace("+00:00", "Z")}}
    return CanonicalSensorReading.model_validate(data)
```

- [ ] **Step 4: Rodar o teste do adapter**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/ingestion/test_live_adapter.py -v`

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add services/twinops/src/twinops/config.py services/twinops/src/twinops/ingestion services/twinops/tests/ingestion/test_live_adapter.py
git commit -m "feat(ingestion): add live telemetry adapter"
```

### Task 2: Repositório SQLite append-only e idempotente

**Files:**
- Create: `services/twinops/src/twinops/storage/__init__.py`
- Create: `services/twinops/src/twinops/storage/repository.py`
- Create: `services/twinops/src/twinops/storage/sqlite_repository.py`
- Test: `services/twinops/tests/storage/test_sqlite_repository.py`

**Interfaces:**
- Consumes: `CanonicalSensorReading` do pacote 00.
- Produces: `RawReading`, `CollectionAttempt`, `HistoryQuery`, `SensorHealth`; `TelemetryRepository.initialize() -> None`; `append_raw(reading) -> None`; `insert_sample(sample) -> bool`; `record_attempt(attempt) -> None`; `history(query) -> list[CanonicalSensorReading]`; `latest(asset_tag) -> list[CanonicalSensorReading]`; `health(sensor_id) -> SensorHealth | None`.

- [ ] **Step 1: Escrever testes falhando para WAL, idempotência e histórico**

```python
import sqlite3
from datetime import datetime, timedelta, timezone
from twinops.ingestion.live_adapter import adapt_live_payload
from twinops.storage.repository import HistoryQuery
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository

def sample(sensor_id="s1", seconds=0):
    slot = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    root = "dados1" if sensor_id == "s1" else "dados2"
    return adapt_live_payload(sensor_id=sensor_id, payload={root: {
        "Velocidade": 0.04, "Aceleração": 0.0, "Temperatura": 34}},
        scheduled_at=slot, received_at=slot, asset_tag="MTR-BMB-042")

def test_initializes_wal_and_live_slot_is_idempotent(tmp_path):
    db = tmp_path / "telemetry.db"
    repo = SQLiteTelemetryRepository(db); repo.initialize()
    live_sample = sample()
    assert repo.insert_sample(live_sample) is True
    assert repo.insert_sample(live_sample) is False
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("select count(*) from telemetry_samples").fetchone()[0] == 1

def test_history_filters_orders_and_limits(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db"); repo.initialize()
    samples_out_of_order = [sample(seconds=10), sample(seconds=0), sample(seconds=5)]
    for sample in samples_out_of_order: repo.insert_sample(sample)
    result = repo.history(HistoryQuery(asset_tag="MTR-BMB-042", sensor_id="s1", limit=2))
    assert [s.received_at for s in result] == sorted(
        [s.received_at for s in result], reverse=True)
    assert len(result) == 2
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/storage/test_sqlite_repository.py -v`

Expected: FAIL com `ModuleNotFoundError: No module named 'twinops.storage'`.

- [ ] **Step 3: Implementar tipos e schema SQLite**

```python
# repository.py
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from twinops.contracts.models import CanonicalSensorReading

@dataclass(frozen=True)
class HistoryQuery:
    asset_tag: str
    sensor_id: str | None = None
    source: str | None = None
    from_at: datetime | None = None
    to_at: datetime | None = None
    limit: int = 200

@dataclass(frozen=True)
class CollectionAttempt:
    sensor_id: str; scheduled_at: datetime; attempted_at: datetime
    succeeded: bool; latency_ms: int | None; error_code: str | None

@dataclass(frozen=True)
class RawReading:
    raw_id: str; sensor_id: str; scheduled_at: datetime; received_at: datetime
    payload_hash: str; payload: dict[str, object]

@dataclass(frozen=True)
class SensorHealth:
    sensor_id: str; last_attempt_at: datetime | None; last_success_at: datetime | None
    latency_ms: int | None; error_code: str | None; sample_count: int

class TelemetryRepository(Protocol):
    def initialize(self) -> None: raise NotImplementedError
    def append_raw(self, reading: RawReading) -> None: raise NotImplementedError
    def insert_sample(self, sample: CanonicalSensorReading) -> bool: raise NotImplementedError
    def record_attempt(self, attempt: CollectionAttempt) -> None: raise NotImplementedError
    def history(self, query: HistoryQuery) -> list[CanonicalSensorReading]: raise NotImplementedError
    def latest(self, asset_tag: str) -> list[CanonicalSensorReading]: raise NotImplementedError
    def health(self, sensor_id: str) -> SensorHealth | None: raise NotImplementedError
```

```sql
-- executar em initialize(), dentro de sqlite_repository.py
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS telemetry_samples (
  reading_id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, source TEXT NOT NULL,
  asset_tag TEXT NOT NULL, sensor_id TEXT NOT NULL, scheduled_at TEXT,
  received_at TEXT NOT NULL, observed_at TEXT, velocity REAL NOT NULL,
  acceleration REAL NOT NULL, temperature REAL NOT NULL,
  velocity_unit TEXT, acceleration_unit TEXT, temperature_unit TEXT,
  velocity_confidence TEXT NOT NULL, acceleration_statistic TEXT NOT NULL,
  acceleration_confidence TEXT NOT NULL, temperature_confidence TEXT NOT NULL,
  quality_flags_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
  raw_json TEXT NOT NULL, canonical_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_live_slot
ON telemetry_samples(source, sensor_id, scheduled_at)
WHERE source = 'forzy-live' AND scheduled_at IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_csv_row
ON telemetry_samples(source, sensor_id, payload_hash)
WHERE source = 'forzy-csv';
CREATE INDEX IF NOT EXISTS ix_history
ON telemetry_samples(asset_tag, sensor_id, received_at DESC);
CREATE TABLE IF NOT EXISTS raw_readings (
  raw_id TEXT PRIMARY KEY, sensor_id TEXT NOT NULL, scheduled_at TEXT NOT NULL,
  received_at TEXT NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_raw_slot
ON raw_readings(sensor_id, scheduled_at);
CREATE TABLE IF NOT EXISTS collection_attempts (
  attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, sensor_id TEXT NOT NULL,
  scheduled_at TEXT NOT NULL, attempted_at TEXT NOT NULL, succeeded INTEGER NOT NULL,
  latency_ms INTEGER, error_code TEXT
);
```

Criar a classe com conexão nova por método, SQL parametrizado e reconstrução
exclusiva a partir do JSON canônico:

```python
class SQLiteTelemetryRepository:
    def __init__(self, path: Path): self.path = path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def append_raw(self, reading: RawReading) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO raw_readings VALUES (?,?,?,?,?,?)", (
                reading.raw_id, reading.sensor_id, reading.scheduled_at.isoformat(),
                reading.received_at.isoformat(), reading.payload_hash,
                json.dumps(reading.payload, ensure_ascii=False, sort_keys=True)))

    def insert_sample(self, sample: CanonicalSensorReading) -> bool:
        body = sample.model_dump(mode="json", by_alias=True)
        measurements = body["measurements"]
        values = (body["readingId"], body["schemaVersion"], body["source"],
            body["assetTag"], body["sensorId"], body["scheduledAt"],
            body["receivedAt"], body["observedAt"],
            measurements["vibrationVelocityRms"]["value"],
            measurements["vibrationAcceleration"]["value"],
            measurements["temperature"]["value"],
            measurements["vibrationVelocityRms"].get("unit"),
            measurements["vibrationAcceleration"].get("unit"),
            measurements["temperature"].get("unit"),
            measurements["vibrationVelocityRms"]["semanticConfidence"],
            measurements["vibrationAcceleration"]["statistic"],
            measurements["vibrationAcceleration"]["semanticConfidence"],
            measurements["temperature"]["semanticConfidence"],
            json.dumps(body["qualityFlags"]), body["payloadHash"],
            json.dumps(body["raw"], ensure_ascii=False, sort_keys=True),
            json.dumps(body, ensure_ascii=False, sort_keys=True))
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO telemetry_samples VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT DO NOTHING", values)
            return cursor.rowcount == 1

    def record_attempt(self, attempt: CollectionAttempt) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO collection_attempts "
                "(sensor_id,scheduled_at,attempted_at,succeeded,latency_ms,error_code) "
                "VALUES (?,?,?,?,?,?)", (attempt.sensor_id, attempt.scheduled_at.isoformat(),
                attempt.attempted_at.isoformat(), int(attempt.succeeded),
                attempt.latency_ms, attempt.error_code))

    def history(self, query: HistoryQuery) -> list[CanonicalSensorReading]:
        if not 1 <= query.limit <= 1000: raise ValueError("limit must be between 1 and 1000")
        where, params = ["asset_tag = ?"], [query.asset_tag]
        for value, clause in ((query.sensor_id, "sensor_id = ?"),
                              (query.source, "source = ?"),
                              (query.from_at.isoformat() if query.from_at else None, "received_at >= ?"),
                              (query.to_at.isoformat() if query.to_at else None, "received_at <= ?")):
            if value is not None: where.append(clause); params.append(value)
        with self._connect() as conn:
            rows = conn.execute("SELECT canonical_json FROM telemetry_samples WHERE "
                + " AND ".join(where) + " ORDER BY received_at DESC LIMIT ?",
                (*params, query.limit)).fetchall()
        return [CanonicalSensorReading.model_validate(json.loads(row[0])) for row in rows]

    def latest(self, asset_tag: str) -> list[CanonicalSensorReading]:
        with self._connect() as conn:
            rows = conn.execute("SELECT canonical_json FROM telemetry_samples t WHERE "
                "asset_tag=? AND received_at=(SELECT MAX(received_at) FROM telemetry_samples "
                "WHERE asset_tag=t.asset_tag AND sensor_id=t.sensor_id)", (asset_tag,)).fetchall()
        return [CanonicalSensorReading.model_validate(json.loads(row[0])) for row in rows]
```

Adicionar o método health com query parametrizada:

```python
def health(self, sensor_id: str) -> SensorHealth | None:
    with self._connect() as conn:
        latest = conn.execute("SELECT attempted_at, latency_ms, error_code FROM "
            "collection_attempts WHERE sensor_id=? ORDER BY attempted_at DESC LIMIT 1",
            (sensor_id,)).fetchone()
        success = conn.execute("SELECT MAX(attempted_at) FROM collection_attempts "
            "WHERE sensor_id=? AND succeeded=1", (sensor_id,)).fetchone()[0]
        count = conn.execute("SELECT COUNT(*) FROM telemetry_samples WHERE sensor_id=?",
                             (sensor_id,)).fetchone()[0]
    if latest is None and count == 0: return None
    return SensorHealth(sensor_id,
        datetime.fromisoformat(latest["attempted_at"]) if latest else None,
        datetime.fromisoformat(success) if success else None,
        latest["latency_ms"] if latest else None,
        latest["error_code"] if latest else None, count)
```

- [ ] **Step 4: Rodar os testes do storage**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/storage/test_sqlite_repository.py -v`

Expected: PASS para WAL, uma linha após duplicate insert, ordem descendente, filtros e limite.

- [ ] **Step 5: Commit**

```bash
git add services/twinops/src/twinops/storage services/twinops/tests/storage
git commit -m "feat(storage): add append-only SQLite repository"
```

### Task 3: Agenda de coleta com slots determinísticos

**Files:**
- Create: `services/twinops/src/twinops/ingestion/schedule.py`
- Test: `services/twinops/tests/ingestion/test_schedule.py`

**Interfaces:**
- Consumes: `datetime` timezone-aware e intervalo positivo.
- Produces: `CollectionWindow(timezone_name: str = "America/Sao_Paulo", weekdays: frozenset[int] = frozenset({0,1,2}), start: time = time(12), end: time = time(14))`; `is_open(now: datetime) -> bool`; `slot_for(now: datetime, interval_seconds: float) -> datetime | None` em UTC.

- [ ] **Step 1: Escrever testes das bordas e alinhamento**

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from twinops.ingestion.schedule import CollectionWindow

SP = ZoneInfo("America/Sao_Paulo")

def test_schedule_boundaries():
    window = CollectionWindow()
    assert not window.is_open(datetime(2026, 8, 10, 11, 59, tzinfo=SP))
    assert window.is_open(datetime(2026, 8, 10, 12, 0, tzinfo=SP))
    assert window.is_open(datetime(2026, 8, 12, 13, 59, 59, tzinfo=SP))
    assert not window.is_open(datetime(2026, 8, 12, 14, 0, tzinfo=SP))
    assert not window.is_open(datetime(2026, 8, 13, 12, 0, tzinfo=SP))

def test_slot_is_utc_and_floor_aligned():
    slot = CollectionWindow().slot_for(datetime(2026, 8, 12, 12, 0, 7, tzinfo=SP), 5)
    assert slot.isoformat() == "2026-08-12T15:00:05+00:00"
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/ingestion/test_schedule.py -v`

Expected: FAIL com `ModuleNotFoundError` para `twinops.ingestion.schedule`.

- [ ] **Step 3: Implementar a janela sem depender do timezone da máquina**

```python
from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

@dataclass(frozen=True)
class CollectionWindow:
    timezone_name: str = "America/Sao_Paulo"
    weekdays: frozenset[int] = frozenset({0, 1, 2})
    start: time = time(12, 0)
    end: time = time(14, 0)

    def is_open(self, now: datetime) -> bool:
        if now.tzinfo is None: raise ValueError("now must be timezone-aware")
        local = now.astimezone(ZoneInfo(self.timezone_name))
        return local.weekday() in self.weekdays and self.start <= local.time() < self.end

    def slot_for(self, now: datetime, interval_seconds: float) -> datetime | None:
        if interval_seconds <= 0: raise ValueError("interval_seconds must be positive")
        if not self.is_open(now): return None
        utc = now.astimezone(timezone.utc)
        floored = int(utc.timestamp() // interval_seconds * interval_seconds)
        return datetime.fromtimestamp(floored, tz=timezone.utc)
```

- [ ] **Step 4: Rodar testes**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/ingestion/test_schedule.py -v`

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add services/twinops/src/twinops/ingestion/schedule.py services/twinops/tests/ingestion/test_schedule.py
git commit -m "feat(ingestion): add deterministic collection schedule"
```

### Task 4: Cliente upstream e coletor concorrente resiliente

**Files:**
- Create: `services/twinops/src/twinops/ingestion/upstream.py`
- Create: `services/twinops/src/twinops/ingestion/collector.py`
- Test: `services/twinops/tests/ingestion/test_collector.py`

**Interfaces:**
- Consumes: `Settings`, `CollectionWindow`, `TelemetryRepository`, `adapt_live_payload`.
- Produces: `UpstreamClient.fetch(sensor_id: Literal["s1","s2"]) -> FetchResult`; `Collector.collect_slot(slot: datetime) -> dict[str, Literal["stored","duplicate","failed"]]`; `Collector.tick(now: datetime) -> Literal["collected","expected_idle"]`.

- [ ] **Step 1: Escrever teste falhando de isolamento, retry e idempotência**

```python
import httpx, pytest
from datetime import datetime, timezone
from pathlib import Path
from twinops.config import Settings
from twinops.ingestion.collector import Collector
from twinops.ingestion.upstream import UpstreamClient
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository

async def _completed_sleep(_: float):
    return None

@pytest.mark.asyncio
async def test_s1_failure_does_not_block_s2_and_retry_is_limited(tmp_path):
    settings = Settings("https://upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path); repo.initialize()
    calls = {"s1": 0, "s2": 0}
    def handler(request: httpx.Request):
        sensor = request.url.path[-2:]; calls[sensor] += 1
        if sensor == "s1": return httpx.Response(500, json={"detail": "internal"})
        return httpx.Response(200, json={"dados2": {
            "Velocidade": 0.05, "Aceleração": 0.0, "Temperatura": 35}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = UpstreamClient(http, settings.upstream_base_url, 2.0,
                                sleep=_completed_sleep)
        result = await Collector(client, repo, settings.asset_tag).collect_slot(
            datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc))
    assert result == {"s1": "failed", "s2": "stored"}
    assert calls == {"s1": 2, "s2": 1}
    assert len(repo.latest(settings.asset_tag)) == 1
    with repo._connect() as conn:
        assert conn.execute("select count(*) from raw_readings where sensor_id='s2'").fetchone()[0] == 1

@pytest.mark.asyncio
async def test_duplicate_slot_keeps_both_raw_payloads_but_one_canonical(tmp_path):
    settings = Settings("https://upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path); repo.initialize()
    def handler(request: httpx.Request):
        sensor = request.url.path[-2:]
        return httpx.Response(200, json={f"dados{sensor[-1]}": {
            "Velocidade": 0.05, "Aceleração": 0.0, "Temperatura": 35}})
    slot = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = UpstreamClient(http, settings.upstream_base_url, 2.0,
                                sleep=_completed_sleep)
        collector = Collector(client, repo, settings.asset_tag)
        assert (await collector.collect_slot(slot))["s2"] == "stored"
        assert (await collector.collect_slot(slot))["s2"] == "duplicate"
    with repo._connect() as conn:
        assert conn.execute("select count(*) from raw_readings where sensor_id='s2'").fetchone()[0] == 2
        assert conn.execute("select count(*) from telemetry_samples where sensor_id='s2'").fetchone()[0] == 1
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/ingestion/test_collector.py -v`

Expected: FAIL nos imports de `collector` e `upstream`.

- [ ] **Step 3: Implementar cliente e coletor mínimos**

```python
# upstream.py
from dataclasses import dataclass
import asyncio, random, time
from typing import Awaitable, Callable, Literal, Mapping
import httpx

@dataclass(frozen=True)
class FetchResult:
    payload: Mapping[str, object]; latency_ms: int

class UpstreamFailure(RuntimeError):
    def __init__(self, code: str, latency_ms: int | None = None):
        super().__init__(code); self.code, self.latency_ms = code, latency_ms

class UpstreamClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str, timeout_seconds: float,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.http, self.base_url, self.timeout, self.sleep = http, base_url, timeout_seconds, sleep

    async def fetch(self, sensor_id: Literal["s1", "s2"]) -> FetchResult:
        last: UpstreamFailure | None = None
        for attempt in range(2):
            started = time.perf_counter()
            try:
                response = await self.http.get(f"{self.base_url}/get_{sensor_id}",
                                               headers={"accept": "application/json"},
                                               timeout=self.timeout)
                latency = round((time.perf_counter() - started) * 1000)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, Mapping): raise ValueError("root")
                return FetchResult(payload, latency)
            except (httpx.TimeoutException, httpx.HTTPError, ValueError):
                latency = round((time.perf_counter() - started) * 1000)
                last = UpstreamFailure("upstream_unavailable", latency)
                if attempt == 0: await self.sleep(0.1 + random.random() * 0.1)
        raise last or UpstreamFailure("upstream_unavailable")
```

```python
# collector.py (métodos centrais)
import asyncio, hashlib, json, uuid
from datetime import datetime, timezone
from twinops.ingestion.live_adapter import InvalidSensorPayload, adapt_live_payload
from twinops.ingestion.upstream import UpstreamClient, UpstreamFailure
from twinops.storage.repository import CollectionAttempt, RawReading, TelemetryRepository

class Collector:
    def __init__(self, upstream: UpstreamClient, repository: TelemetryRepository,
                 asset_tag: str):
        self.upstream, self.repository, self.asset_tag = upstream, repository, asset_tag

    async def _one(self, sensor_id: str, slot: datetime) -> str:
        attempted = datetime.now(timezone.utc)
        try:
            fetched = await self.upstream.fetch(sensor_id)
            received = datetime.now(timezone.utc)
            encoded = json.dumps(fetched.payload, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode()
            self.repository.append_raw(RawReading(str(uuid.uuid4()), sensor_id, slot,
                received, hashlib.sha256(encoded).hexdigest(), dict(fetched.payload)))
            sample = adapt_live_payload(sensor_id=sensor_id, payload=fetched.payload,
                scheduled_at=slot, received_at=received, asset_tag=self.asset_tag)
            stored = self.repository.insert_sample(sample)
            self.repository.record_attempt(CollectionAttempt(sensor_id, slot, attempted,
                True, fetched.latency_ms, None))
            return "stored" if stored else "duplicate"
        except (UpstreamFailure, InvalidSensorPayload) as exc:
            code = exc.code if isinstance(exc, UpstreamFailure) else "invalid_payload"
            latency = exc.latency_ms if isinstance(exc, UpstreamFailure) else None
            self.repository.record_attempt(CollectionAttempt(sensor_id, slot, attempted,
                False, latency, code))
            return "failed"

    async def collect_slot(self, slot: datetime) -> dict[str, str]:
        values = await asyncio.gather(self._one("s1", slot), self._one("s2", slot))
        return dict(zip(("s1", "s2"), values, strict=True))
```

Adicionar o método abaixo ao `Collector`:

```python
async def tick(self, now: datetime) -> str:
    slot = self.window.slot_for(now, self.poll_interval_seconds)
    if slot is None:
        return "expected_idle"
    await self.collect_slot(slot)
    return "collected"
```

Estender o construtor com `window: CollectionWindow = CollectionWindow()` e
`poll_interval_seconds: float = 5.0`, armazenando ambos nos atributos usados
acima.

- [ ] **Step 4: Rodar testes do coletor**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/ingestion/test_collector.py -v`

Expected: PASS para timeout/500/JSON inválido isolado, S2 persistido, duas chamadas máximas no sensor falho, dois raws do slot repetido e uma única linha canônica.

- [ ] **Step 5: Commit**

```bash
git add services/twinops/src/twinops/ingestion/upstream.py services/twinops/src/twinops/ingestion/collector.py services/twinops/tests/ingestion/test_collector.py
git commit -m "feat(ingestion): collect sensors concurrently with bounded retry"
```

### Task 5: Importador CSV idempotente pelo mesmo contrato

**Files:**
- Create: `services/twinops/src/twinops/ingestion/csv_importer.py`
- Test: `services/twinops/tests/ingestion/test_csv_importer.py`

**Interfaces:**
- Consumes: CSV UTF-8 com colunas aprovadas pelo pacote 00 e `TelemetryRepository`.
- Produces: `CsvImportReport(file_hash: str, rows_read: int, samples_inserted: int, duplicates: int, rejected: int)`; `import_csv(path: Path, repository: TelemetryRepository, asset_tag: str, received_at: datetime) -> CsvImportReport`.

- [ ] **Step 1: Escrever teste falhando com reimportação**

```python
from datetime import datetime, timezone
from twinops.storage.repository import HistoryQuery
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository
from twinops.ingestion.csv_importer import import_csv

def test_csv_import_is_idempotent_and_keeps_source(tmp_path):
    csv_fixture_path = tmp_path / "telemetry.csv"
    csv_fixture_path.write_text(
        "sensor_id,observed_at,vibration_velocity_rms,vibration_acceleration,temperature\n"
        "s1,2026-08-10T15:00:00Z,0.04,0.0,34\n"
        "s2,2026-08-10T15:00:00Z,0.05,0.0,35\n", encoding="utf-8")
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db"); repo.initialize()
    now = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
    first = import_csv(csv_fixture_path, repo, "MTR-BMB-042", now)
    second = import_csv(csv_fixture_path, repo, "MTR-BMB-042", now)
    assert (first.samples_inserted, first.rejected) == (2, 0)
    assert (second.samples_inserted, second.duplicates) == (0, 2)
    samples = repo.history(HistoryQuery(asset_tag="MTR-BMB-042", source="forzy-csv"))
    assert {s.source for s in samples} == {"forzy-csv"}
    assert all(s.scheduled_at is None for s in samples)
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/ingestion/test_csv_importer.py -v`

Expected: FAIL com import ausente.

- [ ] **Step 3: Implementar importação estrita**

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import csv, hashlib, json, math, uuid
from twinops.contracts.models import CanonicalSensorReading
from twinops.storage.repository import TelemetryRepository

@dataclass(frozen=True)
class CsvImportReport:
    file_hash: str; rows_read: int; samples_inserted: int; duplicates: int; rejected: int

def import_csv(path: Path, repository: TelemetryRepository, asset_tag: str,
               received_at: datetime) -> CsvImportReport:
    content = path.read_bytes(); file_hash = hashlib.sha256(content).hexdigest()
    inserted = duplicates = rejected = rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for line_number, row in enumerate(csv.DictReader(stream), start=2):
            rows += 1
            try:
                sensor = row["sensor_id"].lower()
                if sensor not in {"s1", "s2"}: raise ValueError("sensor_id")
                values = [float(row[k]) for k in
                          ("vibration_velocity_rms", "vibration_acceleration", "temperature")]
                if not all(math.isfinite(v) for v in values): raise ValueError("finite")
                observed = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
                row_hash = f"sha256:{hashlib.sha256(f'{file_hash}:{line_number}:{sensor}'.encode()).hexdigest()}"
                data = {"schemaVersion": "1.0", "readingId": str(uuid.uuid4()),
                    "source": "forzy-csv", "assetTag": asset_tag, "sensorId": sensor,
                    "scheduledAt": None,
                    "receivedAt": received_at.isoformat().replace("+00:00", "Z"),
                    "observedAt": observed.isoformat().replace("+00:00", "Z"),
                    "measurements": {
                    "vibrationVelocityRms": {"value": values[0], "unit": "mm/s",
                        "semanticConfidence": "inferred_from_datasheet"},
                    "vibrationAcceleration": {"value": values[1], "unit": "g",
                        "statistic": "unknown", "semanticConfidence": "unconfirmed"},
                    "temperature": {"value": values[2], "unit": "degC",
                        "semanticConfidence": "inferred_from_datasheet"}},
                    "qualityFlags": [], "payloadHash": row_hash, "raw": dict(row),
                    "provenance": {"sourceSystem": "forzy-csv-import",
                        "ingestedAt": received_at.isoformat().replace("+00:00", "Z")}}
                inserted_now = repository.insert_sample(CanonicalSensorReading.model_validate(data))
                inserted += int(inserted_now); duplicates += int(not inserted_now)
            except (KeyError, TypeError, ValueError): rejected += 1
    return CsvImportReport(file_hash, rows, inserted, duplicates, rejected)
```

- [ ] **Step 4: Rodar testes CSV**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/ingestion/test_csv_importer.py -v`

Expected: PASS para importação, reimportação, origem, timestamp original e linha inválida contabilizada sem virar zero.

- [ ] **Step 5: Commit**

```bash
git add services/twinops/src/twinops/ingestion/csv_importer.py services/twinops/tests/ingestion/test_csv_importer.py
git commit -m "feat(ingestion): add idempotent CSV import"
```

### Task 6: API de snapshot e histórico sem raw

**Files:**
- Create: `services/twinops/src/twinops/api/__init__.py`
- Create: `services/twinops/src/twinops/api/dependencies.py`
- Create: `services/twinops/src/twinops/api/telemetry_routes.py`
- Create: `services/twinops/src/twinops/main.py`
- Test: `services/twinops/tests/api/test_telemetry_routes.py`

**Interfaces:**
- Consumes: `TelemetryRepository.latest/history`, `DigitalTwinSnapshot` e dependency override FastAPI.
- Produces: `create_app(repository: TelemetryRepository, settings: Settings, collector: Collector | None = None) -> FastAPI`; endpoints normativos `GET /api/v1/twin/assets/{assetTag}/snapshot` e `GET /api/v1/twin/assets/{assetTag}/history?sensorId=&from=&to=&limit=`.

- [ ] **Step 1: Escrever testes HTTP falhando**

```python
from fastapi.testclient import TestClient
from datetime import datetime, timezone
from twinops.config import Settings
from twinops.ingestion.live_adapter import adapt_live_payload
from twinops.main import create_app
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository

def api_setup(tmp_path):
    settings = Settings("https://upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path); repo.initialize()
    slot = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
    sample = adapt_live_payload(sensor_id="s1", payload={"dados1": {
        "Velocidade": 0.04, "Aceleração": 0.0, "Temperatura": 34}},
        scheduled_at=slot, received_at=slot, asset_tag=settings.asset_tag)
    return repo, settings, sample

def test_history_is_filtered_and_never_exposes_raw(tmp_path):
    repo, settings, live_sample = api_setup(tmp_path)
    repo.insert_sample(live_sample)
    response = TestClient(create_app(repo, settings)).get(
        "/api/v1/twin/assets/MTR-BMB-042/history?sensorId=s1&limit=10")
    assert response.status_code == 200
    assert response.json()["items"][0]["sensorId"] == "s1"
    assert "raw" not in response.json()["items"][0]

def test_invalid_limit_is_422_and_does_not_leak_upstream(tmp_path):
    repo, settings, _ = api_setup(tmp_path)
    response = TestClient(create_app(repo, settings)).get(
        "/api/v1/twin/assets/MTR-BMB-042/history?limit=1001")
    assert response.status_code == 422
    assert settings.upstream_base_url not in response.text
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/api/test_telemetry_routes.py -v`

Expected: FAIL com `ModuleNotFoundError: No module named 'twinops.main'`.

- [ ] **Step 3: Implementar projeção pública e rotas**

```python
# telemetry_routes.py
from datetime import datetime, timezone
from fastapi import APIRouter, Query, Request
from twinops.contracts.projections import to_sensor_telemetry_frame
from twinops.storage.repository import HistoryQuery

router = APIRouter(prefix="/api/v1/twin/assets", tags=["telemetry"])

@router.get("/{asset_tag}/history")
def history(request: Request, asset_tag: str, sensorId: str | None = None,
            from_: datetime | None = Query(None, alias="from"),
            to: datetime | None = None, limit: int = Query(200, ge=1, le=1000)):
    query = HistoryQuery(asset_tag, sensorId, None, from_, to, limit)
    return {"items": [to_sensor_telemetry_frame(s).model_dump(mode="json", by_alias=True)
                      for s in request.app.state.repository.history(query)],
            "limit": limit}

@router.get("/{asset_tag}/snapshot")
def snapshot(request: Request, asset_tag: str):
    samples = request.app.state.repository.latest(asset_tag)
    now = datetime.now(timezone.utc)
    channels = [to_sensor_telemetry_frame(s).model_dump(mode="json", by_alias=True)
                for s in samples]
    return {"schemaVersion": "1.0", "assetTag": asset_tag, "mode": "live",
            "generatedAt": now.isoformat().replace("+00:00", "Z"),
            "status": "unknown" if not channels else "insufficient_data",
            "freshness": "unavailable" if not channels else "fresh",
            "channels": channels, "history": [], "assessment": None,
            "capabilities": {"replayControls": False, "liveUpdates": True,
                "copilot": False, "twin3d": True}}
```

```python
# main.py
from fastapi import FastAPI
from twinops.api.telemetry_routes import router as telemetry_router
from twinops.config import Settings
from twinops.storage.repository import TelemetryRepository

def create_app(repository: TelemetryRepository, settings: Settings, collector=None) -> FastAPI:
    app = FastAPI(title="Forzy TwinOps API", version="1.0.0")
    app.state.repository, app.state.settings, app.state.collector = repository, settings, collector
    app.include_router(telemetry_router)
    return app
```

Validar a resposta e registrar um handler fechado:

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from twinops.contracts.models import DigitalTwinSnapshot
import logging

snapshot_body = DigitalTwinSnapshot.model_validate(snapshot_body).model_dump(mode="json", by_alias=True)

@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logging.getLogger("twinops.api").error("request_failed error_type=%s path=%s",
        type(exc).__name__, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal_error"})
```

- [ ] **Step 4: Rodar testes API**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/api/test_telemetry_routes.py -v`

Expected: PASS para filtros, limites, origem live/CSV, snapshot válido, ausência de raw e ausência da URL upstream.

- [ ] **Step 5: Commit**

```bash
git add services/twinops/src/twinops/api services/twinops/src/twinops/main.py services/twinops/tests/api/test_telemetry_routes.py
git commit -m "feat(api): expose canonical telemetry snapshot and history"
```

### Task 7: Health por sensor e estado `expected_idle`

**Files:**
- Create: `services/twinops/src/twinops/api/health_routes.py`
- Modify: `services/twinops/src/twinops/main.py`
- Test: `services/twinops/tests/api/test_health_routes.py`

**Interfaces:**
- Consumes: `TelemetryRepository.health(sensor_id)`, `CollectionWindow.is_open(now)`.
- Produces: `GET /api/v1/system/health` com `{status, collector: {state, sensors: {s1, s2}}}`; erros restritos a `upstream_unavailable|invalid_payload|null`.

- [ ] **Step 1: Escrever teste falhando para idle e erro sanitizado**

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient
from twinops.config import Settings
from twinops.main import create_app
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository

def test_health_reports_expected_idle_outside_window(tmp_path):
    settings = Settings("https://upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path); repo.initialize()
    thursday = datetime(2026, 8, 13, 12, 0,
                        tzinfo=ZoneInfo("America/Sao_Paulo"))
    response = TestClient(create_app(repo, settings, clock=lambda: thursday)).get(
        "/api/v1/system/health")
    assert response.status_code == 200
    body = response.json()
    assert body["collector"]["state"] == "expected_idle"
    assert set(body["collector"]["sensors"]) == {"s1", "s2"}
    assert settings.upstream_base_url not in response.text
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/api/test_health_routes.py -v`

Expected: FAIL com `TypeError` para o argumento `clock` ainda inexistente (ou 404 se o integrador já tiver introduzido a injeção de relógio).

- [ ] **Step 3: Implementar rota e injeção de relógio**

```python
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from twinops.ingestion.schedule import CollectionWindow

router = APIRouter(prefix="/api/v1/system", tags=["system"])

@router.get("/health")
def health(request: Request):
    now = request.app.state.clock()
    open_now = CollectionWindow(request.app.state.settings.timezone_name).is_open(now)
    sensors = {}
    for sensor_id in ("s1", "s2"):
        item = request.app.state.repository.health(sensor_id)
        sensors[sensor_id] = {"lastAttemptAt": item.last_attempt_at if item else None,
            "lastSuccessAt": item.last_success_at if item else None,
            "latencyMs": item.latency_ms if item else None,
            "error": item.error_code if item else None,
            "sampleCount": item.sample_count if item else 0}
    return {"status": "ok", "collector": {
        "state": "active" if open_now else "expected_idle", "sensors": sensors}}
```

Alterar a assinatura/composição de `create_app` exatamente assim:

```python
from collections.abc import Callable
from datetime import datetime, timezone
from twinops.api.health_routes import router as health_router

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def create_app(repository: TelemetryRepository, settings: Settings, collector=None,
               clock: Callable[[], datetime] = utc_now) -> FastAPI:
    app = FastAPI(title="Forzy TwinOps API", version="1.0.0")
    app.state.repository, app.state.settings = repository, settings
    app.state.collector, app.state.clock = collector, clock
    app.include_router(telemetry_router); app.include_router(health_router)
    return app
```

- [ ] **Step 4: Rodar testes health**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/api/test_health_routes.py -v`

Expected: PASS para estado ativo/idle, timestamps, latência, contagem, erro sanitizado e independência S1/S2.

- [ ] **Step 5: Commit**

```bash
git add services/twinops/src/twinops/api/health_routes.py services/twinops/src/twinops/main.py services/twinops/tests/api/test_health_routes.py
git commit -m "feat(api): expose sanitized collector health"
```

### Task 8: Ciclo contínuo, CLI e smoke opt-in

**Files:**
- Modify: `services/twinops/src/twinops/ingestion/collector.py`
- Create: `services/twinops/src/twinops/cli.py`
- Create: `services/twinops/tests/ingestion/test_collector_loop.py`
- Create: `services/twinops/tests/smoke/test_forzy_live.py`

**Interfaces:**
- Consumes: `Settings.from_env`, `SQLiteTelemetryRepository`, `UpstreamClient`, `Collector.tick`.
- Produces: `Collector.run(stop: asyncio.Event, interval_seconds: float, clock: Callable[[], datetime], sleep: Callable[[float], Awaitable[None]]) -> None`; comandos `twinops serve`, `twinops collect`, `twinops import-csv PATH`.

- [ ] **Step 1: Escrever teste falhando para restart sem backfill**

```python
import asyncio, pytest
from datetime import datetime, timezone
from twinops.ingestion.collector import Collector

class RecordingCollector:
    def __init__(self): self.requested_slots = []
    async def tick(self, now):
        seconds = int(now.timestamp() // 5 * 5)
        self.requested_slots.append(datetime.fromtimestamp(seconds, tz=timezone.utc))
    run = Collector.run

@pytest.mark.asyncio
async def test_loop_collects_current_slot_only_and_stops():
    clean_collector = RecordingCollector()
    stop = asyncio.Event(); ticks = iter([
        datetime(2026, 8, 12, 15, 0, 7, tzinfo=timezone.utc),
        datetime(2026, 8, 12, 15, 0, 12, tzinfo=timezone.utc)])
    sleeps = 0
    async def sleep(_):
        nonlocal sleeps; sleeps += 1
        if sleeps == 2: stop.set()
    await clean_collector.run(stop=stop, interval_seconds=5,
                              clock=lambda: next(ticks), sleep=sleep)
    assert clean_collector.requested_slots == [
        datetime(2026, 8, 12, 15, 0, 5, tzinfo=timezone.utc),
        datetime(2026, 8, 12, 15, 0, 10, tzinfo=timezone.utc)]
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `.venv/Scripts/python -m pytest services/twinops/tests/ingestion/test_collector_loop.py -v`

Expected: FAIL com `AttributeError: 'Collector' object has no attribute 'run'`.

- [ ] **Step 3: Implementar loop e CLI**

```python
# adicionar em Collector
async def run(self, *, stop, interval_seconds, clock, sleep):
    while not stop.is_set():
        await self.tick(clock())
        await sleep(interval_seconds)
```

```python
# cli.py
import argparse, asyncio, os
from pathlib import Path
import httpx, uvicorn
from twinops.config import Settings
from twinops.ingestion.collector import Collector
from twinops.ingestion.csv_importer import import_csv
from twinops.ingestion.upstream import UpstreamClient
from twinops.main import create_app
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository

def main() -> None:
    parser = argparse.ArgumentParser(prog="twinops")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve"); sub.add_parser("collect")
    csv_parser = sub.add_parser("import-csv"); csv_parser.add_argument("path", type=Path)
    args = parser.parse_args(); settings = Settings.from_env(os.environ)
    repo = SQLiteTelemetryRepository(settings.database_path); repo.initialize()
    if args.command == "serve":
        uvicorn.run(create_app(repo, settings), host="127.0.0.1", port=8000)
    elif args.command == "import-csv":
        from datetime import datetime, timezone
        print(import_csv(args.path, repo, settings.asset_tag, datetime.now(timezone.utc)))
    else:
        async def collect() -> None:
            stop = asyncio.Event()
            async with httpx.AsyncClient() as http:
                client = UpstreamClient(http, settings.upstream_base_url,
                                        settings.request_timeout_seconds)
                collector = Collector(client, repo, settings.asset_tag)
                from datetime import datetime, timezone
                await collector.run(stop=stop,
                    interval_seconds=settings.poll_interval_seconds,
                    clock=lambda: datetime.now(timezone.utc), sleep=asyncio.sleep)
        asyncio.run(collect())
```

O modo `serve` não inicia implicitamente um segundo collector; para a demo,
executar `twinops serve` e `twinops collect` em dois processos contra o mesmo
SQLite WAL. Envolver `asyncio.run(collect())` em `try/except KeyboardInterrupt:
return`. Criar o smoke sem persistência:

```python
import os, pytest, httpx
from twinops.config import Settings
from twinops.ingestion.live_adapter import adapt_live_payload
from twinops.ingestion.upstream import UpstreamClient
from datetime import datetime, timezone

pytestmark = pytest.mark.skipif(os.getenv("TWINOPS_RUN_LIVE_SMOKE") != "1",
                                reason="live smoke requires explicit opt-in")

@pytest.mark.asyncio
async def test_live_endpoints_match_contract():
    settings = Settings.from_env(os.environ)
    async with httpx.AsyncClient() as http:
        client = UpstreamClient(http, settings.upstream_base_url,
                                settings.request_timeout_seconds)
        for sensor_id in ("s1", "s2"):
            result = await client.fetch(sensor_id)
            assert result.latency_ms >= 0
            adapt_live_payload(sensor_id=sensor_id, payload=result.payload,
                scheduled_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc), asset_tag=settings.asset_tag)
```

- [ ] **Step 4: Rodar suíte completa e smoke desabilitado**

Run: `.venv/Scripts/python -m pytest services/twinops/tests -v`

Expected: todos os testes determinísticos PASS e `tests/smoke/test_forzy_live.py` SKIPPED.

- [ ] **Step 5: Executar verificação funcional local**

Run: `$env:TWINOPS_UPSTREAM_BASE_URL='https://invalid.example'; .venv/Scripts/python -m twinops.cli import-csv services/twinops/tests/fixtures/telemetry.csv`

Expected: relatório com `rows_read`, `samples_inserted`, `duplicates` e `rejected`, sem stack trace nem acesso ao upstream.

Run: `$env:TWINOPS_UPSTREAM_BASE_URL='https://invalid.example'; .venv/Scripts/python -m twinops.cli serve`

Expected: API ouvindo em `127.0.0.1:8000`; `GET /api/v1/system/health` retorna 200 e `GET /api/v1/twin/assets/MTR-BMB-042/history?limit=10` retorna amostras CSV sem `raw`.

- [ ] **Step 6: Commit**

```bash
git add services/twinops/src/twinops/ingestion/collector.py services/twinops/src/twinops/cli.py services/twinops/tests/ingestion/test_collector_loop.py services/twinops/tests/smoke/test_forzy_live.py
git commit -m "feat(ingestion): add collector runtime and service CLI"
```

## Gate final de aceitação

- [ ] `.venv/Scripts/python -m pytest services/twinops/tests -v` termina sem falhas; smoke real permanece SKIPPED sem opt-in.
- [ ] Durante uma janela simulada, uma resposta válida de cada sensor aparece em snapshot/histórico em até dois ciclos de 5 segundos.
- [ ] Timeout, 500, JSON inválido ou schema inválido em S1 não impede S2.
- [ ] Reinício retoma no slot corrente, sem backfill e sem duplicar `(source, sensorId, scheduledAt)`.
- [ ] Fora da janela não há escrita live e health informa `expected_idle`.
- [ ] Histórico ordena, limita e filtra; live/CSV mantêm `source`; nenhuma resposta contém `raw`, URL upstream ou stack trace.
- [ ] `PRAGMA journal_mode` retorna `wal`; schema possui os dois índices de idempotência e o índice de histórico.
- [ ] A entrega registra schema aplicado, comandos, total de amostras CSV, resultado do smoke opt-in quando executado, arquivos alterados e desvios da spec.

## Decisões que devem ser escaladas

Somente interromper a execução para: escolher infraestrutura paga/publicar o
backend; mudar a promessa para previsão de falha; afirmar localização física
de S1/S2; enviar dados industriais a LLM externo; remover replay; ou incluir
autenticação/multi-planta. Unidades inferidas, estatística desconhecida da
aceleração, hostname temporário e cadência real desconhecida permanecem
limitações explícitas, não razões para inventar semântica.
