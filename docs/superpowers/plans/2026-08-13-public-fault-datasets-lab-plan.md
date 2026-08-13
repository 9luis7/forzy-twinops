# Public Fault Datasets Laboratory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Medir quanto conhecimento de falhas de rolamentos públicos sobrevive quando os sinais são reduzidos às grandezas disponíveis na API Forzy.

**Architecture:** Adapters específicos produzem um contrato experimental comum de janelas, sem concatenar arquivos brutos. Um pipeline extrai três vistas — sinal completo, agregada e Forzy-compatible — e executa splits por rolamento e validação cross-bench; resultados ficam fora do artefato operacional.

**Tech Stack:** Python 3.11+, NumPy, pandas, SciPy, scikit-learn, joblib, pytest e datasets públicos originais.

**Spec:** `docs/superpowers/specs/2026-08-13-forzy-twinops-real-vercel-zero-cost-design.md`

## Global Constraints

- Este plano não bloqueia o deploy e não altera `artifacts/ml/real-forzy/**`.
- Downloads ficam em `data/public/<dataset>/raw/`, ignorados por Git.
- Cada fonte exige URL, citação, licença/termos, hash e data de acesso no manifesto.
- Primeira entrega executa XJTU-SY + NASA IMS; PRONOSTIA entra se a fonte original estiver acessível; Paderborn só após aceite explícito do uso CC BY-NC; CWRU é sanity check opcional.
- Nenhuma imagem/espectrograma derivado do Hugging Face substitui o sinal original.
- Split por `bearing_id`; o mesmo rolamento nunca cruza train/validation/test.
- Cross-bench é obrigatório antes de qualquer claim de generalização.
- “Forzy-compatible” significa somente features reproduzíveis com semântica confirmada; não fabricar temperatura ausente nem inferir RPM.
- Resultado não é calibrado para o ativo Forzy e não pode aparecer na UI operacional.
- Datasets grandes não são commitados; somente manifests, configs, relatórios e pequenas fixtures sintéticas.

## Mapa de arquivos

- `research/contracts.py`: janela experimental comum.
- `research/datasets/{xjtu,ims,pronostia}.py`: adapters.
- `research/features.py`: três vistas.
- `research/splits.py`: GroupKFold/holdout por rolamento.
- `research/experiments.py`: treino, métricas e cross-bench.
- `data/public/README.md`: aquisição e licenças.
- `artifacts/ml-public/*`: relatórios, não modelo operacional.

---

### Task 1: Contrato experimental e matriz de compatibilidade

**Files:**
- Create: `services/twinops/src/twinops/research/__init__.py`
- Create: `services/twinops/src/twinops/research/contracts.py`
- Create: `services/twinops/src/twinops/research/compatibility.py`
- Create: `services/twinops/tests/research/test_contracts.py`
- Create: `data/public/README.md`

**Interfaces:**
- Produces: `SignalWindow(dataset_id,bearing_id,run_id,started_at,sampling_hz,acceleration,temperature_c,rpm,load,fault_label,life_fraction)`.
- Produces: `CompatibilityReport(full_features,aggregate_features,forzy_features,missing_semantics)`.

- [ ] **Step 1: Escrever testes de coerência**

```python
def test_window_rejects_missing_identity_and_non_finite_signal():
    with pytest.raises(ValueError):
        SignalWindow(dataset_id="xjtu", bearing_id="", run_id="1", sampling_hz=25600,
                     acceleration=np.array([0.0, np.nan]), fault_label="normal")

def test_forzy_view_does_not_invent_temperature_or_rpm():
    report = compatibility(window_without_temperature_or_rpm())
    assert "temperature" not in report.forzy_features
    assert "rpm" in report.missing_semantics
```

- [ ] **Step 2: Rodar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/research/test_contracts.py -v`

Expected: FAIL por pacote ausente.

- [ ] **Step 3: Implementar dataclasses e documentação de fontes**

`acceleration` é array 1D ou mapping de eixo→array; não converter unidade silenciosamente. `fault_label` usa `normal|inner_race|outer_race|rolling_element|cage|compound|unknown`. README registra URLs oficiais e que Paderborn é CC BY-NC 4.0.

- [ ] **Step 4: Rodar GREEN**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/research/test_contracts.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/twinops/src/twinops/research services/twinops/tests/research data/public/README.md
git commit -m "feat: define public fault research contract"
```

### Task 2: Manifesto de download e adapters XJTU/IMS

**Files:**
- Create: `services/twinops/src/twinops/research/downloads.py`
- Create: `services/twinops/src/twinops/research/datasets/xjtu.py`
- Create: `services/twinops/src/twinops/research/datasets/ims.py`
- Create: `services/twinops/tests/research/test_xjtu_adapter.py`
- Create: `services/twinops/tests/research/test_ims_adapter.py`
- Create: `data/public/sources.json`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `verify_archive(path, expected_sha256)`, `iter_xjtu(root)`, `iter_ims(root)`.

- [ ] **Step 1: Criar pequenas fixtures numéricas e testes**

Use `tmp_path` para CSV XJTU com colunas horizontal/vertical e arquivo IMS com linhas numéricas. Teste bearing ID, sampling 25600/20000 conforme metadata, ordenação cronológica e fault label vindo do mapa do dataset, nunca do nome adivinhado.

- [ ] **Step 2: Rodar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/research/test_xjtu_adapter.py services/twinops/tests/research/test_ims_adapter.py -v`

Expected: FAIL por adapters ausentes.

- [ ] **Step 3: Implementar adapters e manifesto**

`sources.json` contém `datasetId`, `landingPage`, `downloadUrl`, `citation`, `license`, `expectedSha256` e `accessedAt`. O executor preenche `expectedSha256` somente após baixar uma fonte oficial; se a URL for espelho, registra isso explicitamente e não chama de oficial.

- [ ] **Step 4: Baixar somente após aprovação de rede e termos**

Pergunta exata: “Posso baixar XJTU-SY e NASA IMS das fontes registradas para o diretório ignorado `data/public`?”

Após aprovação, baixe sem extrair sobre arquivos existentes; verifique hash; extraia em diretório vazio validado sob `data/public/<id>/raw`.

- [ ] **Step 5: Rodar GREEN**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/research/test_xjtu_adapter.py services/twinops/tests/research/test_ims_adapter.py -v`

Expected: PASS com fixtures locais; nenhum arquivo bruto aparece no Git.

- [ ] **Step 6: Commit sem dados brutos**

```powershell
git add services/twinops/src/twinops/research services/twinops/tests/research data/public/sources.json .gitignore
git commit -m "feat: adapt XJTU and IMS fault datasets"
```

### Task 3: Features completas, agregadas e Forzy-compatible

**Files:**
- Create: `services/twinops/src/twinops/research/features.py`
- Test: `services/twinops/tests/research/test_features.py`

**Interfaces:**
- Produces: `extract_views(window: SignalWindow) -> FeatureViews(full, aggregate, forzy)`.

- [ ] **Step 1: Escrever testes de ablação**

```python
def test_views_are_nested_without_semantic_invention(sine_window):
    views = extract_views(sine_window)
    assert {"rms_g","kurtosis","crest_factor","band_energy"} <= views.full.keys()
    assert {"acceleration_rms_g"} <= views.aggregate.keys()
    assert set(views.forzy) <= {"acceleration_rms_g","velocity_rms_mm_s","temperature_c"}
    assert "velocity_rms_mm_s" not in views.forzy  # waveform acceleration alone is insufficient without validated integration/filter
```

- [ ] **Step 2: Rodar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/research/test_features.py -v`

Expected: FAIL por extractor ausente.

- [ ] **Step 3: Adicionar SciPy serialmente e implementar**

Depois do plano 02 integrado, adicione `"scipy>=1.13,<2"` ao `pyproject.toml` e reinstale. Full: RMS, std, peak-to-peak, crest, skew, kurtosis, envelope/spectral bands normalizadas por Nyquist. Aggregate: apenas estatísticas de janela. Forzy: interseção semanticamente compatível; temperatura somente se medida; velocity RMS somente se dataset já a fornece ou se filtro/integrador é confirmado por configuração do experimento.

- [ ] **Step 4: Rodar GREEN**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/research/test_features.py -v`

Expected: PASS com tolerâncias numéricas explícitas.

- [ ] **Step 5: Commit**

```powershell
git add services/twinops/pyproject.toml services/twinops/src/twinops/research/features.py services/twinops/tests/research/test_features.py
git commit -m "feat: derive public fault feature views"
```

### Task 4: Splits por rolamento e avaliação cross-bench

**Files:**
- Create: `services/twinops/src/twinops/research/splits.py`
- Create: `services/twinops/src/twinops/research/experiments.py`
- Test: `services/twinops/tests/research/test_splits.py`
- Test: `services/twinops/tests/research/test_experiments.py`

**Interfaces:**
- Produces: `grouped_splits(rows, *, group="bearing_id")`.
- Produces: `run_ablation(train_dataset, test_dataset, *, seed=42) -> AblationReport`.

- [ ] **Step 1: Escrever teste que detecta vazamento**

```python
def test_no_bearing_crosses_split(rows):
    split = grouped_splits(rows)
    assert set(split.train_bearings).isdisjoint(split.validation_bearings)
    assert set(split.train_bearings).isdisjoint(split.test_bearings)
    assert set(split.validation_bearings).isdisjoint(split.test_bearings)
```

Adicione teste onde cada linha é embaralhada; split continua igual pelo seed e group.

- [ ] **Step 2: Rodar RED**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/research/test_splits.py services/twinops/tests/research/test_experiments.py -v`

Expected: FAIL por funções ausentes.

- [ ] **Step 3: Implementar baselines pequenos**

Use `StandardScaler + LogisticRegression(class_weight="balanced", max_iter=2000, random_state=42)` para diagnóstico e `HistGradientBoostingRegressor` apenas quando `life_fraction` verdadeiro existir. Métricas: macro F1, balanced accuracy, per-class recall, confusion matrix; para prognóstico MAE de life fraction e lead-time de detecção com regra documentada. Compare full/aggregate/Forzy dentro da bancada e XJTU→IMS/IMS→XJTU quando labels mapeáveis.

- [ ] **Step 4: Rodar GREEN**

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/research -q`

Expected: PASS; nenhum teste usa random row split.

- [ ] **Step 5: Commit**

```powershell
git add services/twinops/src/twinops/research/splits.py services/twinops/src/twinops/research/experiments.py services/twinops/tests/research
git commit -m "feat: evaluate public fault transfer"
```

### Task 5: Executar ablação e produzir relatório honesto

**Files:**
- Create: `scripts/run_public_fault_lab.py`
- Create: `artifacts/ml-public/ablation-report.json`
- Create: `artifacts/ml-public/dataset-manifest.json`
- Create: `docs/jornada/experimento-datasets-publicos.md`

**Interfaces:**
- Produces: relatório reproduzível com configs, hashes, splits e métricas.

- [ ] **Step 1: Implementar CLI com dry-run**

Run esperado: `services\twinops\.venv\Scripts\python.exe scripts/run_public_fault_lab.py --datasets xjtu ims --output artifacts/ml-public --seed 42`

O CLI falha se hash não bater, bearing overlap existir, label mapping ficar vazio ou diretório output contiver artefato operacional.

- [ ] **Step 2: Executar experimento completo**

Expected: três vistas por dataset, pelo menos uma avaliação cross-bench, tempos, contagens de bearings e intervalos de confiança por bootstrap de bearings, não de janelas.

- [ ] **Step 3: Escrever narrativa baseada nos resultados**

O documento separa Evidência, Resultado, Limitação e Próximo experimento. Não usar “modelo Forzy prevê falha”. A conclusão deve informar o delta full→aggregate→Forzy e se cross-bench ficou acima do baseline majoritário.

- [ ] **Step 4: Gate de independência operacional**

Run: `git diff -- artifacts/ml/real-forzy services/twinops/src/twinops/ml`

Expected: sem diff.

Run: `services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/research -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/run_public_fault_lab.py artifacts/ml-public docs/jornada/experimento-datasets-publicos.md
git commit -m "research: compare public fault signal fidelity"
```
