# Real TwinOps Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar a fronteira server-side v2 com refresh sob demanda, persistência Postgres, histórico curto, health e inferência do baseline Forzy.

**Architecture:** Um `RefreshService` orquestra agenda, upstream, adapter v2 e repositório sem depender de FastAPI. PostgreSQL e SQLite implementam um protocolo v2; rotas somente compõem refresh, snapshot e scorer, permitindo testes determinísticos sem rede.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, httpx, psycopg 3, PostgreSQL/Neon, SQLite para testes locais, scikit-learn e pytest.

**Spec:** `docs/superpowers/specs/2026-08-13-forzy-twinops-real-vercel-zero-cost-design.md`

## Global Constraints

- Começar após integrar o plano 01.
- Asset único: `forzy-motor-01`; rotas rejeitam outro ID com 404.
- POST refresh consulta Forzy apenas dentro da janela; fora dela retorna `refreshAttempted:false`.
- S1 e S2 são concorrentes e isolados; timeout 2 s, no máximo um retry curto.
- `observedAt=receivedAt` com qualidade assumida; não usar `scheduledAt` como horário observado.
- Payload repetido continua em raw/attempts, mas não duplica `telemetry_samples_v2`.
- `DATABASE_URL` é obrigatório em deploy; `TWINOPS_DATABASE_PATH` permanece apenas local.
- O backend nunca retorna raw, hostname upstream ou stack trace.
- O artefato operacional permanece nos hashes congelados pelo índice.
- Não tocar frontend, `contracts/v2/**`, 3D, deploy ou laboratório público.

## Mapa de arquivos

- `config_v2.py`: env e invariantes de deploy.
- `storage/v2_repository.py`: protocolo e tipos.
- `storage/postgres_repository.py`: implementação Postgres.
- `storage/sqlite_v2_repository.py`: implementação local equivalente.
- `migrations/002_real_twin_v2.sql`: schema versionado.
- `ingestion/live_adapter_v2.py`: payload Forzy para reading v2.
- `ingestion/refresh_service.py`: agenda, dedupe e concorrência.
- `api/v2_routes.py`: quatro rotas públicas.
- `main_v2.py`: composition root sem side effects em import.

---

### Task 1: Configuração v2 e adapter temporal

**Files:**
- Create: `services/twinops/src/twinops/config_v2.py`
- Create: `services/twinops/src/twinops/ingestion/live_adapter_v2.py`
- Test: `services/twinops/tests/ingestion/test_live_adapter_v2.py`

**Interfaces:**
- Produces: `SettingsV2.from_env(env: Mapping[str,str]) -> SettingsV2`.
- Produces: `adapt_live_payload_v2(*, sensor_id, payload, scheduled_at, received_at, asset_id="forzy-motor-01") -> CanonicalSensorReadingV2`.

- [ ] **Step 1: Escrever testes RED**

```python
from datetime import datetime, timezone
from twinops.ingestion.live_adapter_v2 import adapt_live_payload_v2

def test_retrieval_time_becomes_explicit_assumed_observation():
    received = datetime(2026, 8, 12, 15, 0, 1, tzinfo=timezone.utc)
    sample = adapt_live_payload_v2(
        sensor_id="s1",
        payload={"dados1":{"Velocidade":0.04,"Aceleração":0.0,"Temperatura":34}},
        scheduled_at=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
        received_at=received,
    )
    assert sample.asset_id == "forzy-motor-01"
    assert sample.observed_at == sample.received_at
    assert sample.timestamp_quality == "assumed_from_retrieval"
    assert sample.provenance.source_timestamp_provided is False
```

Adicione parametrização para string, `None`, bool, NaN, infinito e chave `Aceleração` ausente.

- [ ] **Step 2: Rodar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/ingestion/test_live_adapter_v2.py -v`

Expected: FAIL por módulo ausente.

- [ ] **Step 3: Implementar configuração e adapter mínimo**

`SettingsV2` contém `upstream_base_url`, `database_url`, `database_path`, `asset_id`, `poll_interval_seconds=5`, `request_timeout_seconds=2`, `timezone_name`, e os três campos do artefato ML. `database_url` pode ser nulo localmente; `for_deploy()` falha se nulo.

O hash do payload é somente o JSON canônico do upstream. `readingId` usa UUID v4; dedupe não depende dele.

- [ ] **Step 4: Rodar GREEN**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/ingestion/test_live_adapter_v2.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/twinops/src/twinops/config_v2.py services/twinops/src/twinops/ingestion/live_adapter_v2.py services/twinops/tests/ingestion/test_live_adapter_v2.py
git commit -m "feat: adapt Forzy telemetry to contract v2"
```

### Task 2: Protocolo v2, migração e SQLite de referência

**Files:**
- Create: `services/twinops/src/twinops/storage/v2_repository.py`
- Create: `services/twinops/src/twinops/storage/sqlite_v2_repository.py`
- Create: `services/twinops/migrations/002_real_twin_v2.sql`
- Test: `services/twinops/tests/storage/test_sqlite_v2_repository.py`

**Interfaces:**
- Produces: `TelemetryRepositoryV2.initialize`, `append_raw`, `insert_distinct_sample`, `record_attempt`, `latest`, `history`, `health`.
- Produces: `InsertResult(stored: bool, duplicate_of: str | None)`.

- [ ] **Step 1: Escrever o teste de dedupe por informação**

```python
def test_identical_payload_is_audited_but_not_a_second_sample(repo, sample_factory):
    first = sample_factory(reading_id="11111111-1111-4111-8111-111111111111")
    second = sample_factory(reading_id="22222222-2222-4222-8222-222222222222", seconds=5)
    assert repo.insert_distinct_sample(first).stored is True
    assert repo.insert_distinct_sample(second).stored is False
    assert len(repo.history(HistoryQueryV2(asset_id="forzy-motor-01", sensor_id="s1"))) == 1
```

Adicione testes para valor que muda e volta ao anterior: deve armazenar três pontos `A,B,A`; dedupe é apenas consecutivo por sensor.

- [ ] **Step 2: Rodar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/storage/test_sqlite_v2_repository.py -v`

Expected: FAIL por protocolo ausente.

- [ ] **Step 3: Implementar schema e repositório**

Crie tabelas `telemetry_samples_v2`, `raw_readings_v2`, `collection_attempts_v2`. `telemetry_samples_v2` guarda `canonical_json`, `payload_hash`, `asset_id`, `sensor_id`, `observed_at`, `received_at`; índice `(asset_id,sensor_id,observed_at desc)`. O algoritmo transacional consulta o último `payload_hash` do sensor e insere apenas se diferente.

- [ ] **Step 4: Rodar GREEN e regressão SQLite v1**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/storage -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/twinops/src/twinops/storage/v2_repository.py services/twinops/src/twinops/storage/sqlite_v2_repository.py services/twinops/migrations/002_real_twin_v2.sql services/twinops/tests/storage/test_sqlite_v2_repository.py
git commit -m "feat: persist distinct real telemetry v2"
```

### Task 3: PostgreSQL equivalente e dependência psycopg

**Files:**
- Modify: `services/twinops/pyproject.toml`
- Create: `services/twinops/src/twinops/storage/postgres_repository.py`
- Test: `services/twinops/tests/storage/test_postgres_repository.py`

**Interfaces:**
- Produces: `PostgresTelemetryRepository(database_url: str)` implementando `TelemetryRepositoryV2`.

- [ ] **Step 1: Adicionar teste de contrato com factory**

```python
@pytest.mark.postgres
def test_postgres_repository_satisfies_shared_contract(postgres_repo, repository_contract):
    repository_contract(postgres_repo)
```

Mova os cenários de Task 2 para uma função `repository_contract(repo)` reutilizada por SQLite e Postgres. O fixture Postgres lê `TEST_DATABASE_URL`; sem variável, usa `pytest.skip("TEST_DATABASE_URL not configured")`.

- [ ] **Step 2: Rodar RED do teste Postgres**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/storage/test_postgres_repository.py -v`

Expected: FAIL por import ausente quando `TEST_DATABASE_URL` está configurado; SKIP explícito caso contrário.

- [ ] **Step 3: Adicionar psycopg e implementação parametrizada**

Em `pyproject.toml`, adicione `"psycopg[binary]>=3.2,<4"`. Use transações e `%s`; não interpolar SQL. A deduplicação seleciona a última amostra daquele sensor com bloqueio `FOR UPDATE` antes da inserção.

- [ ] **Step 4: Reinstalar e validar**

Run: `services\twinops\.venv\Scripts\python.exe -m pip install -e "services/twinops[dev]"`

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/storage -q`

Expected: SQLite PASS; Postgres PASS quando configurado ou um único SKIP documentado.

- [ ] **Step 5: Commit**

```powershell
git add services/twinops/pyproject.toml services/twinops/src/twinops/storage/postgres_repository.py services/twinops/tests/storage
git commit -m "feat: add Postgres telemetry repository"
```

### Task 4: RefreshService com agenda e isolamento

**Files:**
- Create: `services/twinops/src/twinops/ingestion/refresh_service.py`
- Test: `services/twinops/tests/ingestion/test_refresh_service.py`

**Interfaces:**
- Produces: `RefreshResult(refresh_attempted: bool, outcomes: dict[str, Literal["stored","unchanged","failed"]])`.
- Produces: `await RefreshService.refresh(now: datetime) -> RefreshResult`.

- [ ] **Step 1: Escrever testes de janela, parcial e repetição**

```python
@pytest.mark.asyncio
async def test_outside_window_does_not_call_upstream(service, upstream):
    result = await service.refresh(datetime(2026, 8, 13, 16, tzinfo=timezone.utc))
    assert result.refresh_attempted is False
    upstream.fetch.assert_not_called()

@pytest.mark.asyncio
async def test_s1_failure_does_not_discard_s2(service_with_partial_failure, repo):
    result = await service_with_partial_failure.refresh(WEDNESDAY_WINDOW)
    assert result.outcomes == {"s1":"failed", "s2":"stored"}
    assert [x.sensor_id for x in repo.latest("forzy-motor-01")] == ["s2"]
```

- [ ] **Step 2: Rodar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/ingestion/test_refresh_service.py -v`

Expected: FAIL por módulo ausente.

- [ ] **Step 3: Implementar orquestração**

Use `asyncio.gather(self._refresh_one("s1", slot), self._refresh_one("s2", slot), return_exceptions=False)` sobre dois métodos que capturam `UpstreamFailure`/`InvalidSensorPayloadV2` individualmente. Grave raw antes do adapter quando o JSON for objeto. Registre attempt em todos os caminhos. O slot continua idempotente, mas o dedupe de informação decide `unchanged`.

- [ ] **Step 4: Rodar GREEN e regressão ingestion**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/ingestion -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/twinops/src/twinops/ingestion/refresh_service.py services/twinops/tests/ingestion/test_refresh_service.py
git commit -m "feat: refresh real sensors on demand"
```

### Task 5: Snapshot v2, health e scorer

**Files:**
- Create: `services/twinops/src/twinops/api/v2_snapshot.py`
- Create: `services/twinops/tests/api/test_v2_snapshot.py`

**Interfaces:**
- Produces: `build_snapshot_v2(*, repository, scorer, now, operational_state, freshness_basis, twin3d_enabled) -> DigitalTwinSnapshotV2`.

- [ ] **Step 1: Escrever testes para ausência, parcial e assessment**

```python
def test_partial_channels_never_report_normal(snapshot_factory):
    snapshot = snapshot_factory(available=("s2",), scorer_status="normal")
    assert snapshot.status == "insufficient_data"
    assert snapshot.channels[0].sensor_id == "s1"
    assert "unavailable" in snapshot.channels[0].quality_flags

def test_assessment_semantics_remain_relative(snapshot_factory):
    snapshot = snapshot_factory(available=("s1","s2"), scorer_status="watch")
    assert snapshot.assessment.assessment.score_semantics == "relative_to_historical_baseline_not_failure_probability"
```

- [ ] **Step 2: Rodar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/api/test_v2_snapshot.py -v`

Expected: FAIL por builder ausente.

- [ ] **Step 3: Implementar builder puro**

Busque no máximo 1000 pontos distintos por sensor. Scoring continua por sensor; escolha pior avaliação com ranking `insufficient_data` acima de `normal`, depois `watch`, `alert`. Se um canal faltar ou qualquer scorer não produzir assessment, status global é `insufficient_data`. Integration health vem do repositório.

- [ ] **Step 4: Rodar GREEN**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/api/test_v2_snapshot.py services/twinops/tests/ml/test_scorer.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/twinops/src/twinops/api/v2_snapshot.py services/twinops/tests/api/test_v2_snapshot.py
git commit -m "feat: build honest twin snapshots v2"
```

### Task 6: Rotas v2 e composition root deployável

**Files:**
- Create: `services/twinops/src/twinops/api/v2_routes.py`
- Create: `services/twinops/src/twinops/main_v2.py`
- Test: `services/twinops/tests/api/test_v2_routes.py`

**Interfaces:**
- Produces: `create_app_v2(*, repository, settings, refresh_service, assessment_scorer, clock) -> FastAPI`.
- Produces: `POST /api/v2/assets/{asset_id}/refresh`, `GET /api/v2/assets/{asset_id}/snapshot`, `GET /api/v2/assets/{asset_id}/history`, `GET /api/v2/integration/health`.

- [ ] **Step 1: Escrever testes HTTP de efeitos**

```python
def test_get_snapshot_never_refreshes(client, refresh_service):
    response = client.get("/api/v2/assets/forzy-motor-01/snapshot")
    assert response.status_code == 200
    refresh_service.refresh.assert_not_called()

def test_post_refresh_returns_schedule_skip(client, clock_outside_window):
    response = client.post("/api/v2/assets/forzy-motor-01/refresh")
    assert response.status_code == 200
    assert response.json()["refreshAttempted"] is False
    assert response.json()["snapshot"]["operationalState"] == "expected_idle"

def test_unknown_asset_is_404(client):
    assert client.get("/api/v2/assets/fake/snapshot").status_code == 404
```

- [ ] **Step 2: Rodar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/api/test_v2_routes.py -v`

Expected: FAIL por rotas ausentes.

- [ ] **Step 3: Implementar rotas e composition root**

`POST refresh` retorna `{refreshAttempted,outcomes,snapshot}`. `GET history` aceita apenas `sensorId=s1|s2` e `limit 1..500`. `main_v2` seleciona Postgres se `database_url`, senão SQLite v2; inicializa repositório no lifespan; carrega scorer somente com os três anchors ML.

- [ ] **Step 4: Rodar backend completo**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests -q`

Expected: todos PASS, com somente skips explicitamente configurados.

- [ ] **Step 5: Commit**

```powershell
git add services/twinops/src/twinops/api/v2_routes.py services/twinops/src/twinops/main_v2.py services/twinops/tests/api/test_v2_routes.py
git commit -m "feat: expose real twin API v2"
```
