# ML de anomalia e deterioração — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reanalisar o CSV com semântica correta e entregar um scorer determinístico de anomalia e deterioração relativa, sem classificar falhas não rotuladas.

**Architecture:** Um pipeline offline transforma amostras canônicas em ciclos e features exclusivamente trailing. Um baseline robusto é obrigatório; Isolation Forest é apenas challenger. O replay walk-forward congela configuração antes do holdout e o scorer publica `AssetConditionAssessment` v1.

**Tech Stack:** Python 3.11+, NumPy, pandas, scikit-learn, Pydantic 2, pytest, joblib.

## Global Constraints

- Não modificar `services/twinops/pyproject.toml` nem `services/twinops/src/twinops/contracts/**`.
- Importar `CanonicalSensorReading` e `AssetConditionAssessment` de `twinops.contracts.models`.
- Produzir somente evidências `AssessmentEvidence` fechadas: `id`, `feature`,
  `value` finito e `unit` obrigatórios; comparativos opcionais/nullables e
  `direction` restrita a `up|down|stable|unknown`.
- Fronteira pública: `AssessmentScorer.assess(samples: Sequence[CanonicalSensorReading], *, now: datetime) -> AssetConditionAssessment`.
- Proibido random split por linha, feature centrada ou ajuste com dados futuros.
- Aceleração não entra no score oficial enquanto `statistic="unknown"`.
- Não comparar S1–S2 fisicamente antes de confirmar montagem/eixo.
- Score significa distância do baseline histórico, não probabilidade de falha.
- Sem deep learning, RUL, aprendizado online automático ou diagnóstico mecânico.
- Entrada stale, inválida ou com janela incompleta retorna `degraded`/`insufficient_data`, não alerta.

## Mapa de arquivos

- `services/twinops/src/twinops/ml/curation.py`: qualidade, cadência e ciclos.
- `services/twinops/src/twinops/ml/features.py`: features causais.
- `services/twinops/src/twinops/ml/baseline.py`: regras robustas e persistência.
- `services/twinops/src/twinops/ml/challenger.py`: Isolation Forest opcional.
- `services/twinops/src/twinops/ml/scorer.py`: fronteira online/stateful.
- `services/twinops/src/twinops/ml/backtest.py`: walk-forward e métricas.
- `services/twinops/src/twinops/ml/artifacts.py`: manifesto, hashes e carga.
- `services/twinops/tests/ml/**`: invariantes e regressão.
- `artifacts/ml/**`: configuração/model card/resultados versionados.
- `notebooks/forzy_eda_corrected.ipynb`: relatório reproduzível, sem lógica exclusiva.

---

### Task 1: Curadoria, qualidade e segmentação de ciclos

**Files:**
- Create: `services/twinops/src/twinops/ml/__init__.py`
- Create: `services/twinops/src/twinops/ml/curation.py`
- Test: `services/twinops/tests/ml/test_curation.py`

**Interfaces:**
- Produces: `CuratedFrame` com colunas `received_at`, `sensor_id`, valores, `quality_flags`, `cycle_id`, `operating_state`, `state_estimated`.
- Produces: `curate_samples(samples: Sequence[CanonicalSensorReading], *, gap_seconds: float) -> CuratedFrame`.

- [ ] **Step 1: Escrever testes de ordem, duplicata, gap e ciclos**

```python
def test_gap_closes_cycle_and_resets_operating_state(sample_factory):
    samples = [sample_factory(second=0, velocity=0.01), sample_factory(second=2, velocity=0.20), sample_factory(second=120, velocity=0.01)]
    frame = curate_samples(samples, gap_seconds=10)
    assert frame["cycle_id"].tolist() == [0, 0, 1]
    assert "gap_before" in frame.iloc[2].quality_flags

def test_duplicate_payload_is_flagged_not_counted_as_new_information(sample_factory):
    frame = curate_samples([sample_factory(second=0, payload_hash="same"), sample_factory(second=5, payload_hash="same")], gap_seconds=10)
    assert "duplicate_payload" in frame.iloc[1].quality_flags
```

- [ ] **Step 2: Confirmar falha inicial**

Run: `services/twinops/.venv/Scripts/python -m pytest services/twinops/tests/ml/test_curation.py -v`

Expected: FAIL por módulo ausente.

- [ ] **Step 3: Implementar curadoria sem interpolar gaps**

Ordenar por timestamp, preservar origem, medir cadência, marcar duplicatas e
segmentar proxies `stopped/startup/steady/shutdown/unknown`. Documentar que o
estado é estimado por vibração; não calibrar baseline com transições.

- [ ] **Step 4: Rodar testes e commit**

Run: `services/twinops/.venv/Scripts/python -m pytest services/twinops/tests/ml/test_curation.py -v`

Expected: PASS.

```bash
git add services/twinops/src/twinops/ml services/twinops/tests/ml/test_curation.py
git commit -m "feat(ml): curate telemetry into operating cycles"
```

### Task 2: Features exclusivamente causais

**Files:**
- Create: `services/twinops/src/twinops/ml/features.py`
- Test: `services/twinops/tests/ml/test_features.py`

**Interfaces:**
- Produces: `FeatureConfig(short_window_seconds, long_window_seconds, min_points)`.
- Produces: `compute_trailing_features(frame, config) -> pandas.DataFrame`.

- [ ] **Step 1: Testar ausência de vazamento temporal**

```python
def test_future_mutation_does_not_change_prior_features(curated_frame):
    first = compute_trailing_features(curated_frame, CONFIG)
    mutated = curated_frame.copy()
    mutated.loc[mutated.index[-1], "velocity_rms"] *= 100
    second = compute_trailing_features(mutated, CONFIG)
    pd.testing.assert_frame_equal(first.iloc[:-1], second.iloc[:-1])
```

Adicionar testes para reset após gap, MAD zero, `min_points` e temperatura
pós-parada separada de steady.

- [ ] **Step 2: Confirmar falha e implementar**

Run: `services/twinops/.venv/Scripts/python -m pytest services/twinops/tests/ml/test_features.py -v`

Expected antes: FAIL. Depois: PASS para mediana/MAD, robust z-score, EWMA,
inclinação, persistência e magnitude de change point.

- [ ] **Step 3: Commit**

```bash
git add services/twinops/src/twinops/ml/features.py services/twinops/tests/ml/test_features.py
git commit -m "feat(ml): compute causal vibration features"
```

### Task 3: Baseline robusto, persistência e scorer

**Files:**
- Create: `services/twinops/src/twinops/ml/baseline.py`
- Create: `services/twinops/src/twinops/ml/scorer.py`
- Test: `services/twinops/tests/ml/test_baseline.py`
- Test: `services/twinops/tests/ml/test_scorer.py`

**Interfaces:**
- Produces: `RobustBaseline.fit(features) -> RobustBaseline` e `score(features) -> ScoreFrame`.
- Produces: `AssessmentScorer.assess(samples: Sequence[CanonicalSensorReading], *, now: datetime) -> AssetConditionAssessment`.

- [ ] **Step 1: Testar monotonicidade, persistência e qualidade**

```python
def test_persistent_deviation_scores_above_single_spike(baseline, feature_factory):
    spike = baseline.score(feature_factory([0, 0, 8, 0, 0]))
    persistent = baseline.score(feature_factory([0, 0, 5, 5, 5]))
    assert persistent.deterioration_score.iloc[-1] > spike.deterioration_score.iloc[-1]

def test_gap_returns_insufficient_data(scorer, samples_with_gap, now):
    result = scorer.assess(samples_with_gap, now=now)
    assert result.quality.status == "insufficient_data"
    assert result.assessment.status == "insufficient_data"
```

- [ ] **Step 2: Confirmar falha e implementar baseline mínimo**

Usar estatística robusta, EWMA e CUSUM/Page-Hinkley configuráveis. Scores são
normalizados em `[0, 100]`; limiares e duração de persistência vêm de config
versionada, nunca de constantes espalhadas.

Run: `services/twinops/.venv/Scripts/python -m pytest services/twinops/tests/ml/test_baseline.py services/twinops/tests/ml/test_scorer.py -v`

Expected: PASS e `AssetConditionAssessment` validado pelo modelo compartilhado.

- [ ] **Step 3: Testar determinismo e latência**

Replay idêntico deve produzir JSON idêntico exceto `inferenceId`; teste de
performance processa 1.000 amostras e exige p95 medido menor ou igual a 100 ms
no PC-alvo, marcado `performance` para relatório separado.

- [ ] **Step 4: Commit**

```bash
git add services/twinops/src/twinops/ml services/twinops/tests/ml
git commit -m "feat(ml): score anomaly and deterioration"
```

### Task 4: Walk-forward, holdout e challenger opcional

**Files:**
- Create: `services/twinops/src/twinops/ml/backtest.py`
- Create: `services/twinops/src/twinops/ml/challenger.py`
- Test: `services/twinops/tests/ml/test_backtest.py`
- Test: `services/twinops/tests/ml/test_challenger.py`

**Interfaces:**
- Produces: `build_walk_forward_folds(cycles, *, holdout_count=2)`.
- Produces: `run_backtest(frame, pipeline, folds) -> BacktestReport`.

- [ ] **Step 1: Testar separação por ciclo e freeze**

```python
def test_folds_never_split_cycles_or_use_future_training_rows(six_cycles):
    folds = build_walk_forward_folds(six_cycles, holdout_count=2)
    assert set(folds[-1].train_cycle_ids).isdisjoint(folds[-1].test_cycle_ids)
    assert max(folds[-1].train_cycle_ids) < min(folds[-1].test_cycle_ids)
    assert folds[-1].test_cycle_ids == (4, 5)
```

- [ ] **Step 2: Confirmar falha e implementar métricas válidas**

Relatar score por ciclo/regime, episódios/ativação, tempo steady em alerta,
estabilidade de limiar, ranking dos eventos candidatos e latência. Não calcular
precision/recall/F1.

- [ ] **Step 3: Implementar Isolation Forest como challenger isolado**

Treinar somente em janelas baseline de cada fold. A função de decisão compara
estabilidade e carga de alertas; não promove automaticamente o challenger.

- [ ] **Step 4: Rodar testes e commit**

Run: `services/twinops/.venv/Scripts/python -m pytest services/twinops/tests/ml/test_backtest.py services/twinops/tests/ml/test_challenger.py -v`

Expected: PASS.

```bash
git add services/twinops/src/twinops/ml services/twinops/tests/ml
git commit -m "test(ml): add chronological walk forward evaluation"
```

### Task 5: EDA corrigida e artefatos versionados

**Files:**
- Create: `services/twinops/src/twinops/ml/artifacts.py`
- Test: `services/twinops/tests/ml/test_artifacts.py`
- Create: `notebooks/forzy_eda_corrected.ipynb`
- Create: `artifacts/ml/feature-manifest.json`
- Create: `artifacts/ml/model-card.md`
- Create: `artifacts/ml/backtest-report.json`
- Modify: `docs/jornada/experimentos.md`

**Interfaces:**
- Produces: `save_artifact_bundle(path, pipeline, config, report)` e `load_artifact_bundle(path)` com hash verificado.

- [ ] **Step 1: Testar round-trip e rejeição de hash alterado**

Run: `services/twinops/.venv/Scripts/python -m pytest services/twinops/tests/ml/test_artifacts.py -v`

Expected antes: FAIL. Depois: PASS, incluindo rejeição de bundle modificado.

- [ ] **Step 2: Executar EDA e backtest no CSV real**

O notebook importa funções do pacote; não contém lógica exclusiva. Reavaliar
13:48:10 e 13:56:10 como eventos candidatos, produzir resultados por ciclo e
registrar aceleração como excluída do score oficial.

Run: `services/twinops/.venv/Scripts/python -m twinops.ml.backtest --input <csv-curado> --output artifacts/ml`

Expected: manifesto, model card e relatório com hashes e seis ciclos, ou relatório
explícito explicando por que o número de ciclos utilizáveis difere.

- [ ] **Step 3: Rodar suíte ML completa**

Run: `services/twinops/.venv/Scripts/python -m pytest services/twinops/tests/ml -v`

Expected: PASS; teste de performance relata p50/p95/p99.

- [ ] **Step 4: Commit**

```bash
git add services/twinops/src/twinops/ml/artifacts.py services/twinops/tests/ml/test_artifacts.py notebooks artifacts/ml docs/jornada/experimentos.md
git commit -m "docs(ml): record corrected EDA and model evidence"
```

