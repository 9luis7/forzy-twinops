# Real TwinOps Single Asset UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir a demo multipĺanta fictícia por uma interface operacional enxuta para o único conjunto real.

**Architecture:** `TwinOpsProvider` lê snapshot v2 e executa refresh quando página e janela permitem. Um único `OperationsDashboard` apresenta identidade, canais, tendência, ML, integração e 3D; não existe adapter para o domínio fictício anterior.

**Tech Stack:** React 18, JavaScript ESM, Vite 5, Recharts, Vitest, Testing Library e contrato v2.

**Spec:** `docs/superpowers/specs/2026-08-13-forzy-twinops-real-vercel-zero-cost-design.md`

## Global Constraints

- Começar após integrar o plano 01; integrar com plano 02 pelo HTTP v2.
- O runtime publicável tem um ativo, dois sensores e nenhuma TAG oficial.
- `VITE_TWINOPS_DATA_MODE`, replay e `useLiveTelemetry` deixam de controlar a aplicação.
- Não importar `src/data/mock.js`; não copiar seus dados para outro arquivo.
- Falha nunca produz snapshot normal ou dados sintéticos.
- Polling padrão 5 s, sem sobreposição; pausa quando `document.visibilityState !== "visible"` ou agenda fechada.
- Fora da janela, apenas GET snapshot; POST refresh não é agendado.
- A UI escreve “capturado pelo TwinOps às” para `observedAt/receivedAt` assumidos.
- Não reintroduzir chatbot, documentos, ordens, alertas fictícios, planta ou tour.
- Não tocar backend, schemas, GLB ou ferramentas de conversão 3D.

## Mapa de arquivos

- `GatewayTwinDataSourceV2.js`: GET/POST same-origin.
- `TwinOpsContext.jsx`: estado, visibilidade e agenda.
- `components/operations/*`: componentes focados do dashboard.
- `App.jsx`: shell de uma página.
- `styles.css`: layout responsivo.
- Arquivos fictícios: removidos somente após scan provar ausência de imports.

---

### Task 1: Gateway v2 com GET, POST e cancelamento

**Files:**
- Create: `src/dataSources/GatewayTwinDataSourceV2.js`
- Test: `src/dataSources/GatewayTwinDataSourceV2.test.js`

**Interfaces:**
- Produces: `createGatewayTwinDataSourceV2({baseUrl="",fetchImpl=fetch})`.
- Produces: `getSnapshot(assetId,{signal})`, `refresh(assetId,{signal})`, `getHistory(assetId,{sensorId,limit,signal})`.

- [ ] **Step 1: Escrever testes RED**

```js
it("separates read-only snapshot from refresh", async () => {
  const fetchImpl = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => snapshot })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ refreshAttempted: true, outcomes: {s1:"stored",s2:"stored"}, snapshot }) });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });
  await source.getSnapshot("forzy-motor-01", {});
  await source.refresh("forzy-motor-01", {});
  expect(fetchImpl.mock.calls[0][1].method).toBe("GET");
  expect(fetchImpl.mock.calls[1][1].method).toBe("POST");
});
```

Adicione casos para base URL externa, newline/backslash, resposta inválida v2, status não-ok e AbortSignal.

- [ ] **Step 2: Rodar RED**

Run: `npm.cmd run test:run -- src/dataSources/GatewayTwinDataSourceV2.test.js`

Expected: FAIL por módulo ausente.

- [ ] **Step 3: Implementar cliente mínimo**

Use `assertDigitalTwinSnapshotV2`; paths exatos `/api/v2/assets/${encodeURIComponent(assetId)}/snapshot|refresh|history`. Não implemente timer no gateway.

- [ ] **Step 4: Rodar GREEN**

Run: `npm.cmd run test:run -- src/dataSources/GatewayTwinDataSourceV2.test.js`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/dataSources/GatewayTwinDataSourceV2.js src/dataSources/GatewayTwinDataSourceV2.test.js
git commit -m "feat: add real twin gateway v2"
```

### Task 2: Provider com agenda, visibilidade e polling não sobreposto

**Files:**
- Create: `src/TwinOpsContext.jsx`
- Test: `src/TwinOpsContext.test.jsx`

**Interfaces:**
- Produces: `TwinOpsProvider({children,dataSource,clock,pollMs=5000,documentRef=document})`.
- Produces: `useTwinOps() -> {assetId,snapshot,error,refreshing,lastRefreshAttemptAt,refreshNow}`.

- [ ] **Step 1: Escrever testes com relógio injetável**

```jsx
it("refreshes only while visible and inside the Forzy window", async () => {
  vi.useFakeTimers();
  const source = sourceStub();
  const clock = () => new Date("2026-08-12T15:30:00.000Z"); // quarta 12:30 BRT
  render(<TwinOpsProvider dataSource={source} clock={clock}><Probe /></TwinOpsProvider>);
  await vi.runOnlyPendingTimersAsync();
  expect(source.refresh).toHaveBeenCalledTimes(1);
});
```

Adicione: quinta-feira não chama POST; hidden cancela request e timer; refresh lento não sobrepõe; erro mantém último snapshot; unmount aborta.

- [ ] **Step 2: Rodar RED**

Run: `npm.cmd run test:run -- src/TwinOpsContext.test.jsx`

Expected: FAIL por provider ausente.

- [ ] **Step 3: Implementar provider**

No mount faça GET snapshot. Depois, se `isForzyWindowOpen(clock()) && visible`, execute POST e agende o próximo somente no `finally`. `refreshNow` respeita a janela; fora dela apenas relê GET. Use `Intl.DateTimeFormat("en-US", {timeZone:"America/Sao_Paulo", weekday:"short", hour:"2-digit", minute:"2-digit", hourCycle:"h23"})` dentro de helper puro testado, sem depender do timezone do navegador.

- [ ] **Step 4: Rodar GREEN**

Run: `npm.cmd run test:run -- src/TwinOpsContext.test.jsx`

Expected: PASS sem timer pendente.

- [ ] **Step 5: Commit**

```powershell
git add src/TwinOpsContext.jsx src/TwinOpsContext.test.jsx
git commit -m "feat: orchestrate real twin refresh"
```

### Task 3: Componentes operacionais honestos

**Files:**
- Create: `src/components/operations/AssetHeader.jsx`
- Create: `src/components/operations/SensorCard.jsx`
- Create: `src/components/operations/TelemetryTrend.jsx`
- Create: `src/components/operations/AssessmentPanel.jsx`
- Create: `src/components/operations/IntegrationHealth.jsx`
- Test: `src/components/operations/OperationsPanels.test.jsx`

**Interfaces:**
- Consumes: somente `DigitalTwinSnapshotV2`.
- Produces: componentes presentes, sem chamadas de rede ou regra de severidade local.

- [ ] **Step 1: Escrever testes de copy e ausência**

```jsx
it("identifies the real assembly without inventing a tag", () => {
  render(<AssetHeader asset={snapshot.asset} operationalState={snapshot.operationalState} />);
  expect(screen.getByText("Conjunto motor-bomba monitorado")).toBeInTheDocument();
  expect(screen.getByText("TAG não fornecida")).toBeInTheDocument();
  expect(screen.queryByText(/MTR-BMB-042/)).not.toBeInTheDocument();
});

it("labels assumed retrieval time honestly", () => {
  render(<SensorCard channel={snapshot.channels[0]} />);
  expect(screen.getByText(/Capturado pelo TwinOps às/)).toBeInTheDocument();
});
```

Adicione teste para null→`Indisponível`, zero→`0,00`, `last_known`, assessment ausente e health com erro sanitizado.

- [ ] **Step 2: Rodar RED**

Run: `npm.cmd run test:run -- src/components/operations/OperationsPanels.test.jsx`

Expected: FAIL por componentes ausentes.

- [ ] **Step 3: Implementar componentes puros**

`TelemetryTrend` recebe `snapshot.history`, separa s1/s2 e não interpola lacunas. `AssessmentPanel` sempre mostra “Desvio relativo ao histórico — não é probabilidade de falha”. `SensorCard` mostra velocity, acceleration e temperature com semânticas/units do contrato.

- [ ] **Step 4: Rodar GREEN**

Run: `npm.cmd run test:run -- src/components/operations/OperationsPanels.test.jsx`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/components/operations
git commit -m "feat: add honest real asset panels"
```

### Task 4: Dashboard único e estado de erro

**Files:**
- Create: `src/components/operations/OperationsDashboard.jsx`
- Modify: `src/App.jsx`
- Modify: `src/main.jsx`
- Test: `src/App.test.jsx`

**Interfaces:**
- Produces: aplicação de uma página montada sob `TwinOpsProvider`.
- Consumes: `Twin3D` do plano 04 por props; até integração, fallback estático do conjunto.

- [ ] **Step 1: Escrever teste de jornada única**

```jsx
it("renders one real asset and no fictional navigation", async () => {
  render(<App dataSource={sourceWithSnapshot(snapshot)} />);
  expect(await screen.findByText("Conjunto motor-bomba monitorado")).toBeInTheDocument();
  for (const label of ["Planta", "Ordens", "Documentos", "MTR-BMB-042", "Copiloto"]) {
    expect(screen.queryByText(label)).not.toBeInTheDocument();
  }
});
```

Adicione casos: loading, backend sem dado, falha com last-known e botão de atualizar fora da janela.

- [ ] **Step 2: Rodar RED**

Run: `npm.cmd run test:run -- src/App.test.jsx`

Expected: FAIL porque App ainda é multiplanta.

- [ ] **Step 3: Substituir o shell**

`App` aceita `dataSource` apenas para testes e compõe `TwinOpsProvider` + `OperationsDashboard`. Remova Sidebar/Tour/navegação. O fallback 3D usa `docs/jornada/assets/conjunto-motor-bomba-preview.png` copiado para `public/models/conjunto-motor-bomba-preview.png` no plano 04; até lá use um `<div role="img" aria-label="Representação do conjunto motor-bomba indisponível"/>` sem valores.

- [ ] **Step 4: Rodar GREEN e build**

Run: `npm.cmd run test:run -- src/App.test.jsx src/TwinOpsContext.test.jsx src/components/operations/OperationsPanels.test.jsx`

Run: `npm.cmd run build`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/App.jsx src/main.jsx src/App.test.jsx src/components/operations/OperationsDashboard.jsx
git commit -m "feat: replace demo with real asset dashboard"
```

### Task 5: Remover runtime fictício e simplificar estilo

**Files:**
- Delete: `src/data/mock.js`
- Delete: `src/useLiveTelemetry.js`
- Delete: `src/LiveTwinContext.jsx`
- Delete: `src/LiveTwinContext.test.jsx`
- Delete: `src/dataSources/ReplayTwinDataSource.js`
- Delete: `src/dataSources/ReplayTwinDataSource.test.js`
- Delete: `src/views/AlertsView.jsx`
- Delete: `src/views/AssetsView.jsx`
- Delete: `src/views/AuditView.jsx`
- Delete: `src/views/DocumentsView.jsx`
- Delete: `src/views/OrdersView.jsx`
- Delete: `src/views/PlantOverview.jsx`
- Delete: `src/components/Sidebar.jsx`
- Delete: `src/components/TagTree.jsx`
- Delete: `src/components/PlantSynoptic.jsx`
- Delete: `src/components/GuidedTour.jsx`
- Delete: `src/components/Copilot.jsx`
- Delete: `src/components/Copilot.test.jsx`
- Delete: `src/copilot/**`
- Delete: `src/tour.js`
- Modify: `src/styles.css`

**Interfaces:**
- Produces: bundle sem fontes sintéticas ou features adiadas.

- [ ] **Step 1: Provar que não há consumidores antes de apagar**

Run: `rg -n 'data/mock|useLiveTelemetry|LiveTwinContext|ReplayTwinDataSource|Copilot|PlantOverview|AlertsView|OrdersView|DocumentsView|AuditView' src --glob '!*.test.*'`

Expected: sem resultados depois da Task 4. Se houver import, removê-lo no consumidor; não criar shim.

- [ ] **Step 2: Apagar arquivos e limpar dependências de runtime**

Remova do código qualquer leitura de `VITE_SUPABASE_*`, `VITE_TWINOPS_DATA_MODE` e `VITE_TWINOPS_API_BASE_URL`. O plano de deploy será o único responsável por limpar `.env.example`; o frontend usa API same-origin.

- [ ] **Step 3: Reescrever estilos só para o dashboard**

Mantenha tokens de cor/tipografia existentes quando úteis. Garanta grid de 1 coluna abaixo de 900px, foco visível, contraste e `prefers-reduced-motion`.

- [ ] **Step 4: Executar scan, suíte e build**

Run: `rg -n 'MTR-BMB-042|MTR-CMP|MTR-VNT|mock|replay|Supabase|Copiloto|Ordens|Documentos' src`

Expected: zero resultados em runtime; menções em testes históricos v1 só podem permanecer fora de imports do app.

Run: `npm.cmd run test:run`

Run: `npm.cmd run build`

Expected: PASS; contagem menor é aceita apenas pelos arquivos removidos listados.

- [ ] **Step 5: Commit**

```powershell
git add -A src
git commit -m "refactor: remove fictional twin runtime"
```
