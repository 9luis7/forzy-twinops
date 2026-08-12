# Copiloto explicável — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Explicar avaliações estruturadas com rastreabilidade, usando fallback determinístico e deixando Qwen/API atrás de uma interface server-side configurável.

**Architecture:** O frontend envia pergunta e projeção mínima do `AssetConditionAssessment` ao gateway. O backend valida referências, tenta providers autorizados e sempre pode retornar uma explicação determinística; nenhum provider recalcula score, status ou causa.

**Tech Stack:** React 18, Vitest, Python 3.11+, FastAPI, pytest, httpx; adapter OpenAI-compatible opcional para Qwen/API.

## Global Constraints

- O LLM fica fora do caminho crítico de coleta e alerta.
- Nenhuma chave, URL de Qwen ou provedor externo entra no bundle.
- Sem fine-tuning nesta versão.
- API externa fica desabilitada por padrão até autorização de privacidade.
- Score nunca é apresentado como probabilidade de falha, RUL ou causa raiz.
- Toda afirmação sobre estado atual deve citar `evidenceRefs` válidas ou declarar dados insuficientes.
- Falha total de providers deve manter resposta determinística e não afetar o alerta.

## Mapa de arquivos

- `services/twinops/src/twinops/copilot/context.py`: projeção e validação de referências.
- `services/twinops/src/twinops/copilot/providers.py`: protocolo e adapters configuráveis.
- `services/twinops/src/twinops/copilot/deterministic.py`: fallback sem LLM.
- `services/twinops/src/twinops/api/copilot_routes.py`: endpoint HTTP.
- `services/twinops/tests/copilot/**`: testes backend.
- `src/copilot/**`: client, contexto, fallback visual e testes.
- `src/components/Copilot.jsx`: apresentação da conversa.
- `evals/copilot/*.jsonl`: casos e resultados versionados.

---

### Task 1: Contexto mínimo e explicação determinística backend

**Files:**
- Create: `services/twinops/src/twinops/copilot/__init__.py`
- Create: `services/twinops/src/twinops/copilot/context.py`
- Create: `services/twinops/src/twinops/copilot/deterministic.py`
- Test: `services/twinops/tests/copilot/test_deterministic.py`

**Interfaces:**
- Produces: `build_explanation_context(question: str, assessment: AssetConditionAssessment) -> ExplanationContext`.
- Produces: `deterministic_explanation(context: ExplanationContext) -> ExplanationResponse`.

- [ ] **Step 1: Escrever teste que proíbe evidência inventada**

```python
def test_deterministic_response_only_cites_known_evidence():
    assessment = assessment_fixture(evidence=[{"id": "ev-1", "feature": "velocity_rms_ewma", "value": 0.08, "unit": "mm/s"}])
    context = build_explanation_context("O que mudou?", assessment)
    response = deterministic_explanation(context)
    assert response.evidence_refs == ["ev-1"]
    assert response.provider == "deterministic"
    assert "probabilidade de falha" not in response.answer.lower()
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `python -m pytest services/twinops/tests/copilot/test_deterministic.py -v`

Expected: FAIL por módulos ausentes.

- [ ] **Step 3: Implementar dataclasses/modelos Pydantic e fallback**

A resposta deve descrever status, qualidade, evidências e limitações. Para
`insufficient_data`, não recomendar intervenção mecânica; solicitar recomposição
da janela e validação da aquisição.

- [ ] **Step 4: Rodar testes e commit**

Run: `python -m pytest services/twinops/tests/copilot/test_deterministic.py -v`

Expected: PASS.

```bash
git add services/twinops/src/twinops/copilot services/twinops/tests/copilot
git commit -m "feat: add deterministic copilot explanation"
```

### Task 2: Providers configuráveis e fallback ordenado

**Files:**
- Create: `services/twinops/src/twinops/copilot/providers.py`
- Create: `services/twinops/src/twinops/copilot/service.py`
- Test: `services/twinops/tests/copilot/test_service.py`

**Interfaces:**
- Produces: protocolo async `ExplanationProvider.explain(context) -> ExplanationResponse`.
- Produces: `CopilotService(providers, deterministic).explain(context)`.
- Provider local default: endpoint OpenAI-compatible configurado por `LOCAL_LLM_BASE_URL` e model id por `LOCAL_LLM_MODEL`.
- Provider externo só é criado quando `EXTERNAL_LLM_ENABLED=true`.

- [ ] **Step 1: Escrever testes de ordem e falha total**

```python
async def test_local_failure_uses_enabled_external_provider():
    local = StubProvider(error=TimeoutError())
    external = StubProvider(response=response_fixture(provider="external"))
    result = await CopilotService([local, external], deterministic_explanation).explain(context_fixture())
    assert result.provider == "external"
    assert result.fallback_used is True

async def test_all_provider_failures_use_deterministic():
    result = await CopilotService([StubProvider(error=TimeoutError())], deterministic_explanation).explain(context_fixture())
    assert result.provider == "deterministic"
```

- [ ] **Step 2: Confirmar falha, implementar timeout e validação de refs**

Run: `python -m pytest services/twinops/tests/copilot/test_service.py -v`

Expected antes: FAIL. Depois: PASS, com timeout por provider e rejeição de
`evidenceRefs` não presentes no contexto.

- [ ] **Step 3: Commit**

```bash
git add services/twinops/src/twinops/copilot services/twinops/tests/copilot/test_service.py
git commit -m "feat: orchestrate copilot provider fallbacks"
```

### Task 3: Endpoint `/api/v1/copilot/explain`

**Files:**
- Create: `services/twinops/src/twinops/api/copilot_routes.py`
- Modify: `services/twinops/src/twinops/api/app.py`
- Test: `services/twinops/tests/api/test_copilot_routes.py`

**Interfaces:**
- Consumes: `{ question, assetTag, assessment, conversationId? }`.
- Produces: `{ answer, evidenceRefs, provider, model, latencyMs, ttftMs, fallbackUsed, humanValidationRequired, limitations }`.

- [ ] **Step 1: Testar request válido, injection e schema inválido**

O teste de injection envia instrução para ignorar evidências e exige que a
resposta permaneça limitada às refs conhecidas. Request sem assessment retorna
422. Segredo/provider exception não aparece no body.

- [ ] **Step 2: Confirmar falha e implementar rota fina**

Run: `python -m pytest services/twinops/tests/api/test_copilot_routes.py -v`

Expected antes: FAIL. Depois: PASS com serviço injetável para testes.

- [ ] **Step 3: Commit**

```bash
git add services/twinops/src/twinops/api services/twinops/tests/api/test_copilot_routes.py
git commit -m "feat: expose explainable copilot endpoint"
```

### Task 4: Client e fallback React

**Files:**
- Create: `src/copilot/CopilotClient.js`
- Create: `src/copilot/buildExplanationContext.js`
- Create: `src/copilot/DeterministicExplanation.jsx`
- Test: `src/copilot/CopilotClient.test.js`
- Test: `src/copilot/buildExplanationContext.test.js`

**Interfaces:**
- Produces: `createCopilotClient({ fetchImpl, baseUrl = "" }).explain(request, { signal })`.
- Produces: `buildExplanationRequest({ question, snapshot })`.

- [ ] **Step 1: Escrever testes da projeção mínima e same-origin**

```js
it("does not send history or raw telemetry", () => {
  const request = buildExplanationRequest({ question: "O que mudou?", snapshot: snapshotFixture });
  expect(request).not.toHaveProperty("history");
  expect(JSON.stringify(request)).not.toContain("raw");
});
```

O client deve chamar `/api/v1/copilot/explain`, aceitar `AbortSignal` e lançar
erro tipado em timeout/HTTP inválido.

- [ ] **Step 2: Confirmar falha, implementar e retestar**

Run: `npm.cmd run test:run -- src/copilot`

Expected antes: FAIL. Depois: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/copilot
git commit -m "feat: add structured copilot client"
```

### Task 5: Migrar `Copilot.jsx` sem perder a demo

**Files:**
- Modify: `src/components/Copilot.jsx`
- Test: `src/components/Copilot.test.jsx`

**Interfaces:**
- Consumes: `snapshot` de `useLiveTwin()` e `CopilotClient`.
- Preserves: perguntas sugeridas e conversa contextual ao ativo.

- [ ] **Step 1: Testar sucesso, troca de inferenceId e fallback**

O teste exige: resposta com refs renderizadas; mudança de `inferenceId` reinicia
contexto; erro HTTP renderiza `DeterministicExplanation`; alerta existente não é
modificado.

- [ ] **Step 2: Confirmar falha e implementar estados de UI**

Run: `npm.cmd run test:run -- src/components/Copilot.test.jsx`

Expected antes: FAIL. Depois: PASS para loading, sucesso, abort e fallback.

- [ ] **Step 3: Rodar suíte/build e commit**

Run: `npm.cmd run test:run`

Expected: PASS.

Run: `npm.cmd run build`

Expected: PASS.

```bash
git add src/components/Copilot.jsx src/components/Copilot.test.jsx
git commit -m "feat: connect copilot to structured evidence"
```

### Task 6: Harness de avaliação local versus API

**Files:**
- Create: `evals/copilot/cases.jsonl`
- Create: `services/twinops/src/twinops/copilot/evaluate.py`
- Test: `services/twinops/tests/copilot/test_evaluate.py`
- Create: `docs/jornada/resultados-copiloto.md`

**Interfaces:**
- Produces: JSONL com `caseId`, scores de aderência/utilidade, refs inválidas,
  TTFT, duração, tokens/s, VRAM quando local e custo quando externo.

- [ ] **Step 1: Criar 30 casos determinísticos antes de executar modelos**

Distribuir casos entre normal, watch/alert, stale, gap, insufficient data,
pergunta fora de escopo e injection. Cada caso inclui refs permitidas e claims
proibidos.

- [ ] **Step 2: Testar agregação sem provider real**

Run: `python -m pytest services/twinops/tests/copilot/test_evaluate.py -v`

Expected antes da implementação: FAIL. Depois: PASS com stub provider.

- [ ] **Step 3: Implementar runner sem baixar modelo automaticamente**

O runner recebe base URL/model por env; ausência de provider marca caso como
`not_run`, não tenta download. API externa exige `EXTERNAL_LLM_ENABLED=true`.

- [ ] **Step 4: Executar deterministic baseline e documentar**

Run: `python -m services.twinops.copilot.evaluate --provider deterministic --cases evals/copilot/cases.jsonl`

Expected: 30 casos processados, zero refs inexistentes; resultado anexado ao
documento da jornada.

- [ ] **Step 5: Commit**

```bash
git add evals services/twinops/src/twinops/copilot/evaluate.py services/twinops/tests/copilot/test_evaluate.py docs/jornada/resultados-copiloto.md
git commit -m "test: add copilot evaluation harness"
```
