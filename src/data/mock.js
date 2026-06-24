// mock.js — fonte única de verdade do protótipo (dados sintéticos, sem backend).
//
// Hierarquia de TAGs (do macro ao micro — o aprendizado do feedback):
//   PLT-FORZY-001                      planta
//     └── AREA-PROD-01                 área
//           └── BMB-SUC-004            equipamento (bomba)
//                 └── MTR-BMB-042      ativo monitorado (motor) ← estrela da demo
//                       ├── SNS-TEMP-042A   sensor de temperatura
//                       ├── SNS-VIB-042B    sensor de vibração
//                       ├── SNS-COR-042C    sensor de corrente
//                       └── PLC-042         controlador
//
// O motor é o PRIMEIRO ativo escolhido para demonstrar a lógica — a janela para a
// fábrica inteira, não o limite da solução.
//
// Schema de referência (Supabase / PostgreSQL):
//   assets(tag, name, motor_type, area, ...)
//   readings(asset_tag, ts, temperature [°C], current [A], vibration [m/s²], rotation [RPM])
//
// Janela das séries: 24h, 1 ponto a cada 5 min (~288 pontos/motor).

// ---------- PRNG determinístico (mulberry32) — mesma série a cada load ----------
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedFromTag(tag) {
  let h = 2166136261;
  for (let i = 0; i < tag.length; i++) {
    h ^= tag.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

// ============================================================================
//  PLANTA · ÁREAS
// ============================================================================
export const PLANT = {
  tag: "PLT-FORZY-001",
  name: "Planta Forzy 01",
  location: "Unidade Industrial — Forzy",
};

// assetsCount soma 128 (bate com o KPI "Ativos monitorados").
export const areas = [
  { tag: "AREA-PROD-01", letter: "A", name: "Produção", assetsCount: 42, icon: "🏭" },
  { tag: "AREA-UTIL-01", letter: "B", name: "Utilidades", assetsCount: 36, icon: "⚙️" },
  { tag: "AREA-MANUT-01", letter: "C", name: "Manutenção", assetsCount: 28, icon: "🔧" },
  { tag: "AREA-EXP-01", letter: "D", name: "Expedição", assetsCount: 22, icon: "📦" },
];

export const getArea = (tag) => areas.find((a) => a.tag === tag) || null;

// ============================================================================
//  ATIVOS (motores) — subconjunto detalhado e navegável
// ============================================================================
// Cada motor tem TAG, equipamento pai, sensores filhos, datas de manutenção e
// um perfil de baseline usado pela geração de leituras. `degrading: true` ativa
// a rampa de degradação (só o MTR-BMB-042 — a estrela).
export const assets = [
  {
    tag: "MTR-BMB-042",
    name: "Motor Bomba de Sucção 042",
    area: "AREA-PROD-01",
    parent: "BMB-SUC-004",
    motor_type: "Indução trifásico · 7,5 kW · 220 V",
    manufacturer: "WEG W22 IR3 Premium",
    installDate: "2021-03-12",
    lastMaintenance: "2026-05-14",
    nextInspection: "2026-06-26",
    operatingHours: 38420,
    sensors: [
      { tag: "SNS-TEMP-042A", type: "Temperatura", model: "DHT22" },
      { tag: "SNS-VIB-042B", type: "Vibração", model: "MPU6050" },
      { tag: "SNS-COR-042C", type: "Corrente", model: "ACS712" },
      { tag: "PLC-042", type: "Controlador", model: "PLC Siemens S7-1200" },
    ],
    profile: { temp: 59, current: 17, vib: 2.2, rot: 1760, degrading: true },
    note: "Primeiro ativo conectado. Tendência de degradação em rolamento.",
  },
  {
    tag: "MTR-BMB-027",
    name: "Motor Bomba de Recalque 027",
    area: "AREA-PROD-01",
    parent: "BMB-REC-002",
    motor_type: "Indução trifásico · 5,5 kW · 220 V",
    manufacturer: "WEG W22",
    installDate: "2020-08-01",
    lastMaintenance: "2026-04-22",
    nextInspection: "2026-07-22",
    operatingHours: 45110,
    sensors: [
      { tag: "SNS-TEMP-027A", type: "Temperatura", model: "DHT22" },
      { tag: "SNS-VIB-027B", type: "Vibração", model: "MPU6050" },
      { tag: "SNS-COR-027C", type: "Corrente", model: "ACS712" },
    ],
    profile: { temp: 50, current: 18, vib: 1.5, rot: 1750, degrading: false },
    note: "Operação dentro do esperado.",
  },
  {
    tag: "MTR-CMP-018",
    name: "Motor Compressor de Ar 018",
    area: "AREA-UTIL-01",
    parent: "CMP-AR-001",
    motor_type: "Indução trifásico · 11 kW · 380 V",
    manufacturer: "WEG W22 IR3",
    installDate: "2019-11-19",
    lastMaintenance: "2026-05-30",
    nextInspection: "2026-08-30",
    operatingHours: 52300,
    sensors: [
      { tag: "SNS-TEMP-018A", type: "Temperatura", model: "DHT22" },
      { tag: "SNS-VIB-018B", type: "Vibração", model: "MPU6050" },
      { tag: "SNS-COR-018C", type: "Corrente", model: "ACS712" },
    ],
    profile: { temp: 58, current: 24, vib: 1.8, rot: 1770, degrading: false },
    note: "Operação normal.",
  },
  {
    tag: "MTR-VNT-007",
    name: "Motor Ventilador de Exaustão 007",
    area: "AREA-UTIL-01",
    parent: "VNT-EXA-003",
    motor_type: "Indução trifásico · 4 kW · 220 V",
    manufacturer: "WEG W21",
    installDate: "2022-02-10",
    lastMaintenance: "2026-06-01",
    nextInspection: "2026-07-12",
    operatingHours: 21750,
    sensors: [
      { tag: "SNS-TEMP-007A", type: "Temperatura", model: "DHT22" },
      { tag: "SNS-VIB-007B", type: "Vibração", model: "MPU6050" },
      { tag: "SNS-COR-007C", type: "Corrente", model: "ACS712" },
    ],
    profile: { temp: 48, current: 12, vib: 2.4, rot: 3480, degrading: false },
    note: "Vibração de baseline um pouco mais alta (rotação 3500 RPM).",
  },
  {
    tag: "MTR-EST-031",
    name: "Motor Esteira Transportadora 031",
    area: "AREA-EXP-01",
    parent: "EST-TRA-009",
    motor_type: "Indução trifásico · 3 kW · 220 V",
    manufacturer: "WEG W21",
    installDate: "2021-09-05",
    lastMaintenance: "2026-05-08",
    nextInspection: "2026-08-08",
    operatingHours: 33980,
    sensors: [
      { tag: "SNS-TEMP-031A", type: "Temperatura", model: "DHT22" },
      { tag: "SNS-VIB-031B", type: "Vibração", model: "MPU6050" },
      { tag: "SNS-COR-031C", type: "Corrente", model: "ACS712" },
    ],
    profile: { temp: 44, current: 10, vib: 1.2, rot: 1760, degrading: false },
    note: "Operação normal.",
  },
  {
    tag: "MTR-PNT-012",
    name: "Motor Ponte Rolante 012",
    area: "AREA-MANUT-01",
    parent: "PNT-ROL-001",
    motor_type: "Indução trifásico · 6 kW · 380 V",
    manufacturer: "WEG W22",
    installDate: "2018-06-30",
    lastMaintenance: "2026-03-15",
    nextInspection: "2026-09-15",
    operatingHours: 61240,
    sensors: [
      { tag: "SNS-TEMP-012A", type: "Temperatura", model: "DHT22" },
      { tag: "SNS-VIB-012B", type: "Vibração", model: "MPU6050" },
      { tag: "SNS-COR-012C", type: "Corrente", model: "ACS712" },
    ],
    profile: { temp: 46, current: 14, vib: 1.6, rot: 1755, degrading: false },
    note: "Operação intermitente (uso sob demanda).",
  },
];

export const getAsset = (tag) => assets.find((a) => a.tag === tag) || null;
export const assetsByArea = (areaTag) => assets.filter((a) => a.area === areaTag);

// ============================================================================
//  LEITURAS (séries temporais sintéticas)
// ============================================================================
const POINTS = 288; // 24h a cada 5 min
const STEP_MS = 5 * 60 * 1000;
const WINDOW_MS = (POINTS - 1) * STEP_MS;
// Âncora temporal fixa => séries reprodutíveis (não usa Date.now em runtime).
const END_TS = Date.parse("2026-06-24T14:32:00-03:00");

const round = (v, d = 2) => {
  const f = 10 ** d;
  return Math.round(v * f) / f;
};

// Gera a série de um motor (ordem cronológica, termina em END_TS).
function generateReadings(asset) {
  const p = asset.profile;
  const rnd = mulberry32(seedFromTag(asset.tag));
  const start = END_TS - WINDOW_MS;
  const out = [];

  for (let i = 0; i < POINTS; i++) {
    const ts = start + i * STEP_MS;
    const frac = i / (POINTS - 1); // 0 → 1 ao longo da janela
    const diurnal = Math.sin(frac * Math.PI * 2 - Math.PI / 2); // ciclo de turno
    const ramp = p.degrading ? frac : 0; // rampa só na estrela

    const temperature = p.temp + diurnal * 3 + (rnd() - 0.5) * 1.6 + ramp * 26; // ~+26 °C
    const vibration = p.vib + diurnal * 0.15 + (rnd() - 0.5) * 0.25 + ramp * 3.6; // ~+3.6 m/s²
    const current = p.current + diurnal * 0.8 + (rnd() - 0.5) * 0.6 + ramp * 2.4;
    const rotation = p.rot - ramp * 30 + (rnd() - 0.5) * 8;

    out.push({
      asset_tag: asset.tag,
      ts: new Date(ts).toISOString(),
      temperature: round(Math.min(temperature, 92), 1),
      current: round(current, 1),
      vibration: round(Math.max(vibration, 0.4), 2),
      rotation: Math.round(rotation),
    });
  }
  return out;
}

export const readings = Object.fromEntries(
  assets.map((a) => [a.tag, generateReadings(a)])
);

export const latestReading = (tag) => {
  const arr = readings[tag];
  return arr ? arr[arr.length - 1] : null;
};

// ============================================================================
//  ESTADO OPERACIONAL · RISCO
// ============================================================================
// Limiares de realce (espelhados pela UI). Calibrados para o MTR-BMB-042 cair
// em "alerta" (Atenção) — sintoma claro, mas ainda não parada crítica.
export const THRESHOLDS = {
  temp: { warn: 70, crit: 90 },
  vib: { warn: 4.5, crit: 7.5 },
  current: { warn: 26, crit: 32 },
};

const STATUS_LABEL = {
  normal: "Normal",
  alerta: "Atenção",
  critico: "Crítico",
  desconhecido: "Desconhecido",
};

export function assetStatus(tag) {
  const r = latestReading(tag);
  if (!r) return "desconhecido";
  if (r.temperature >= THRESHOLDS.temp.crit || r.vibration >= THRESHOLDS.vib.crit)
    return "critico";
  if (r.temperature >= THRESHOLDS.temp.warn || r.vibration >= THRESHOLDS.vib.warn)
    return "alerta";
  return "normal";
}

export const statusLabel = (status) => STATUS_LABEL[status] ?? STATUS_LABEL.desconhecido;

// Risco preditivo. A estrela tem um diagnóstico curado (evidências/narrativa);
// os demais são derivados do estado atual.
const RISK_CURATED = {
  "MTR-BMB-042": {
    level: "Médio/Alto",
    score: 72,
    confidence: 87,
    component: "Rolamento — lado acoplamento",
    windowHours: 72,
    headline:
      "Risco de falha em rolamento detectado. Recomenda-se inspeção em até 72h para evitar parada não planejada.",
    origin: "SNS-VIB-042B",
    bases: ["Histórico de falhas", "Manual WEG W22", "OS anteriores"],
    evidence: [
      "Vibração aumentou 23% nos últimos 5 dias",
      "Temperatura média subiu de 68 °C para 82 °C",
      "Falha semelhante registrada na OS-2025-118",
      "Manual técnico recomenda inspeção acima de 80 °C em operação contínua",
    ],
  },
};

export function assetRisk(tag) {
  if (RISK_CURATED[tag]) return RISK_CURATED[tag];
  const status = assetStatus(tag);
  if (status === "critico")
    return { level: "Alto", score: 80, confidence: 84, component: "—", windowHours: 24 };
  if (status === "alerta")
    return { level: "Médio", score: 55, confidence: 80, component: "—", windowHours: 120 };
  return { level: "Baixo", score: 12, confidence: 95, component: "—", windowHours: null };
}

// ============================================================================
//  ALERTAS
// ============================================================================
export const alerts = [
  {
    id: "ALR-2026-0312",
    tag: "MTR-BMB-042",
    severity: "critico",
    title: "Risco de falha em rolamento",
    message:
      "Risco de falha em rolamento detectado. Recomenda-se inspeção em até 72h para evitar parada não planejada.",
    confidence: 87,
    origin: "SNS-VIB-042B",
    bases: ["Histórico de falhas", "Manual WEG W22", "OS anteriores"],
    ts: "2026-06-24T14:32:00-03:00",
    status: "Aberto",
  },
  {
    id: "ALR-2026-0309",
    tag: "MTR-VNT-007",
    severity: "alerta",
    title: "Vibração acima do baseline",
    message:
      "Vibração média 12% acima do baseline histórico do ventilador. Monitorar evolução na próxima janela.",
    confidence: 74,
    origin: "SNS-VIB-007B",
    bases: ["Baseline histórico", "ISO 10816-3"],
    ts: "2026-06-24T11:05:00-03:00",
    status: "Em análise",
  },
  {
    id: "ALR-2026-0301",
    tag: "MTR-CMP-018",
    severity: "alerta",
    title: "Temperatura sazonal elevada",
    message:
      "Temperatura do compressor 6% acima do esperado para a carga atual. Verificar ventilação do ambiente.",
    confidence: 69,
    origin: "SNS-TEMP-018A",
    bases: ["Curva de carga", "Manual WEG W22"],
    ts: "2026-06-23T16:48:00-03:00",
    status: "Em análise",
  },
];

export const alertsForTag = (tag) => alerts.filter((a) => a.tag === tag);

// ============================================================================
//  ORDENS DE MANUTENÇÃO (OS)
// ============================================================================
export const maintenanceOrders = [
  {
    id: "OS-2026-204",
    tag: "MTR-BMB-042",
    type: "Preditiva",
    title: "Inspeção de rolamento — gerada por alerta preditivo",
    priority: "Alta",
    status: "Aberta",
    openedAt: "2026-06-24",
    dueAt: "2026-06-26",
    assignee: "Equipe de Manutenção Mecânica",
    origin: "ALR-2026-0312",
  },
  {
    id: "OS-2025-118",
    tag: "MTR-BMB-027",
    type: "Corretiva",
    title: "Substituição de rolamento após falha — motor de bomba",
    priority: "Alta",
    status: "Concluída",
    openedAt: "2025-11-08",
    dueAt: "2025-11-09",
    assignee: "Leandro M. (Manutenção)",
    origin: "Falha em campo",
  },
  {
    id: "OS-2026-187",
    tag: "MTR-BMB-042",
    type: "Preventiva",
    title: "Lubrificação e alinhamento — janela programada",
    priority: "Média",
    status: "Concluída",
    openedAt: "2026-05-14",
    dueAt: "2026-05-14",
    assignee: "Equipe de Manutenção Mecânica",
    origin: "Plano de manutenção",
  },
  {
    id: "OS-2026-192",
    tag: "MTR-CMP-018",
    type: "Preventiva",
    title: "Troca de filtro e verificação de correias",
    priority: "Baixa",
    status: "Programada",
    openedAt: "2026-06-18",
    dueAt: "2026-08-30",
    assignee: "Equipe de Utilidades",
    origin: "Plano de manutenção",
  },
];

export const ordersForTag = (tag) => maintenanceOrders.filter((o) => o.tag === tag);

// ============================================================================
//  DOCUMENTOS TÉCNICOS (conhecimento vinculado)
// ============================================================================
export const documents = [
  {
    id: "DOC-001",
    label: "Manual técnico WEG W22 IR3 Premium",
    kind: "Manual do fabricante",
    meta: "PDF · 184 págs · rev. 2023",
    tags: ["MTR-BMB-042", "MTR-CMP-018", "MTR-BMB-027"],
  },
  {
    id: "DOC-002",
    label: "ISO 10816-3 — severidade de vibração",
    kind: "Norma técnica",
    meta: "Limites de vibração para máquinas industriais",
    tags: ["MTR-BMB-042", "MTR-VNT-007"],
  },
  {
    id: "DOC-003",
    label: "Datasheet sensor MPU6050",
    kind: "Datasheet de sensor",
    meta: "Faixa, resolução e ruído do acelerômetro",
    tags: ["SNS-VIB-042B"],
  },
  {
    id: "DOC-004",
    label: "Plano de manutenção — Bombas (Produção)",
    kind: "Plano interno",
    meta: "Periodicidade e checklist por ativo",
    tags: ["MTR-BMB-042", "MTR-BMB-027"],
  },
  {
    id: "DOC-005",
    label: "OS-2025-118 — relatório de falha em rolamento",
    kind: "Histórico de OS",
    meta: "Causa raiz, peças trocadas e tempo de parada",
    tags: ["MTR-BMB-042", "MTR-BMB-027"],
  },
  {
    id: "DOC-006",
    label: "Ficha de inspeção — Motor Bomba de Sucção 042",
    kind: "Ficha de inspeção",
    meta: "Checklist preenchido na última ronda · 14/05/2026",
    tags: ["MTR-BMB-042"],
  },
  {
    id: "DOC-007",
    label: "Registro fotográfico — rolamento (lado acoplamento)",
    kind: "Registro fotográfico de manutenção",
    meta: "Termografia + inspeção visual · 3 imagens",
    tags: ["MTR-BMB-042"],
  },
  {
    id: "DOC-008",
    label: "Evidência de intervenção — lubrificação e alinhamento",
    kind: "Evidência de intervenção",
    meta: "Anexo da OS-2026-187 · executado em campo",
    tags: ["MTR-BMB-042"],
  },
];

export const docsForTag = (tag) =>
  documents.filter((d) => d.tags.includes(tag));

// ============================================================================
//  KPIs do dashboard (visão da planta)
// ============================================================================
export const kpis = {
  monitoredAssets: 128,
  criticalAlerts: 3,
  plannedMaintenance: 7,
  dataReliability: 94, // %
};

// ============================================================================
//  COMPONENTES (nível entre Motor e Sensor da hierarquia de TAGs)
// ============================================================================
// Plant → Area → Motor → Component → Sensor. O componente dá corpo físico à
// recomendação: o sensor de vibração está montado NO rolamento sob suspeita —
// não é "o motor", é o componente específico que degrada. Só a estrela tem
// detalhamento de componentes nesta fase.
export const components = [
  {
    tag: "CMP-BRG-042A",
    asset: "MTR-BMB-042",
    name: "Rolamento — lado acoplamento",
    type: "Rolamento",
    status: "alerta",
    sensors: ["SNS-VIB-042B"],
    risk: { level: "Médio/Alto", score: 72 },
    evidence: [
      "Vibração aumentou 23% nos últimos 5 dias",
      "Assinatura espectral compatível com defeito de pista externa (BPFO)",
      "Falha semelhante registrada na OS-2025-118",
    ],
    note: "Componente sob suspeita primária da recomendação.",
  },
  {
    tag: "CMP-STA-042B",
    asset: "MTR-BMB-042",
    name: "Estator / carcaça",
    type: "Estator",
    status: "alerta",
    sensors: ["SNS-TEMP-042A"],
    risk: { level: "Médio", score: 46 },
    evidence: [
      "Temperatura média subiu de 68 °C para 82 °C",
      "Aquecimento secundário ao atrito do rolamento",
    ],
    note: "Monitorar — sintoma térmico associado ao rolamento.",
  },
  {
    tag: "CMP-SHF-042C",
    asset: "MTR-BMB-042",
    name: "Eixo / acoplamento",
    type: "Eixo",
    status: "normal",
    sensors: ["SNS-COR-042C"],
    risk: { level: "Baixo", score: 14 },
    evidence: [
      "Corrente dentro da faixa esperada para a carga atual",
      "Sem assinatura de desalinhamento no consumo do motor/drive",
    ],
    note: "Sem desvio relevante.",
  },
];

export const componentsForAsset = (tag) => components.filter((c) => c.asset === tag);
export const getComponent = (tag) => components.find((c) => c.tag === tag) || null;
export const componentForSensor = (sensorTag) =>
  components.find((c) => c.sensors.includes(sensorTag)) || null;

// ============================================================================
//  HEARTBEAT · TELEMETRIA AO VIVO (determinística) — só a estrela
// ============================================================================
// Cada "tick" (1/seg) produz 1 ponto derivado de um seed fixo + índice do tick,
// então a série é reprodutível (Pause/Start/Reset repetem a mesma sequência).
// A rampa leva o motor de "Normal" para "Atenção" em ~30s; "Trigger Incident"
// acelera a degradação rumo ao limiar crítico. Não usa Date.now no valor.
export const HEARTBEAT = {
  tag: "MTR-BMB-042",
  windowPoints: 45, // janela do gráfico ao vivo (limita o crescimento)
  seedPoints: 12, // pontos de baseline pré-carregados antes do Start
  baseline: { temp: 62, vib: 2.6, current: 17.2, rot: 1760 },
};

export function heartbeatPoint(i, { incidentTick = null } = {}) {
  const rnd = mulberry32((0x9e3779b9 ^ ((i + 1) * 0x85ebca6b)) >>> 0);
  const b = HEARTBEAT.baseline;
  const ramp = Math.min(i / 35, 1); // 0 → 1 ao longo de ~35 ticks
  let incident = 0;
  if (incidentTick != null && i >= incidentTick)
    incident = Math.min((i - incidentTick) / 8, 1); // degrau rápido (~8 ticks)
  const wobble = Math.sin(i / 6); // micro-oscilação suave

  const temperature = b.temp + ramp * 12 + incident * 16 + wobble * 0.6 + (rnd() - 0.5) * 0.8;
  const vibration = b.vib + ramp * 2.3 + incident * 3.2 + wobble * 0.12 + (rnd() - 0.5) * 0.18;
  const current = b.current + ramp * 1.4 + incident * 2.2 + wobble * 0.3 + (rnd() - 0.5) * 0.4;
  const rotation = b.rot - ramp * 18 - incident * 30 + (rnd() - 0.5) * 6;

  return {
    t: i,
    temperature: round(Math.min(temperature, 95), 1),
    vibration: round(Math.max(vibration, 0.4), 2),
    current: round(current, 1),
    rotation: Math.round(rotation),
  };
}

// ============================================================================
//  CENÁRIOS DE FALHA AO VIVO (loop determinístico) — só a estrela
// ============================================================================
// O painel ao vivo cicla por estes cenários: cada ciclo nasce de uma operação
// ESTÁVEL, SOBE até cruzar o limiar (DETECÇÃO no painel inteiro), SEGURA no pico
// e então NORMALIZA — antes de passar ao próximo cenário. A forma é um envelope
// por fase (estável → subida → pico → recuperação) e o valor de cada métrica é
// baseline + intensidade*efeito (determinístico por tick). Cada cenário aponta o
// COMPONENTE culpado, o SENSOR de origem e o diagnóstico — é isso que faz o
// gêmeo digital, os gauges e o banner reagirem em sincronia.
export const LIVE_PHASES = { stable: 7, onset: 10, peak: 8, recovery: 11 };
export const LIVE_CYCLE_LEN =
  LIVE_PHASES.stable + LIVE_PHASES.onset + LIVE_PHASES.peak + LIVE_PHASES.recovery;

export const SCENARIOS = [
  {
    id: "overheat",
    name: "Superaquecimento do estator",
    short: "Superaquecimento",
    component: "CMP-STA-042B",
    sensor: "SNS-TEMP-042A",
    primaryMetric: "temperature",
    severity: "critico",
    effect: { temp: 31, vib: 0.5, current: 0.8, rot: -22 },
    confidence: 91,
    bases: ["Curva de carga", "Manual WEG W22", "ISO 10816-3"],
    diagnosis:
      "Temperatura do estator subindo acima do limite crítico (90 °C). Padrão compatível com refrigeração insuficiente ou sobrecarga térmica contínua.",
    recommendation:
      "Verificar ventilação/defletor e a carga do motor. Inspeção térmica recomendada antes de retomar regime contínuo.",
    evidence: [
      "Temperatura cruzou 90 °C com corrente ainda dentro da faixa",
      "Subida térmica sem pico de corrente aponta refrigeração, não sobrecarga elétrica",
      "Manual técnico recomenda inspeção acima de 80 °C em operação contínua",
    ],
  },
  {
    id: "overload",
    name: "Sobrecarga elétrica",
    short: "Sobrecarga elétrica",
    component: "CMP-SHF-042C",
    sensor: "SNS-COR-042C",
    primaryMetric: "current",
    severity: "critico",
    effect: { temp: 6, vib: 0.7, current: 16, rot: -34 },
    confidence: 88,
    bases: ["Curva de carga", "Histórico de falhas", "Manual WEG W22"],
    diagnosis:
      "Corrente acima da faixa operacional com queda de rotação. Assinatura de sobrecarga mecânica no acoplamento/eixo.",
    recommendation:
      "Reduzir carga e inspecionar acoplamento e alinhamento do eixo. Avaliar travamento parcial na carga acionada.",
    evidence: [
      "Corrente cruzou 32 A acompanhada de queda de rotação",
      "Temperatura sobe de forma secundária ao esforço elétrico",
      "Sem assinatura de defeito localizado de rolamento",
    ],
  },
  {
    id: "imbalance",
    name: "Desbalanceamento mecânico",
    short: "Desbalanceamento",
    component: "CMP-BRG-042A",
    sensor: "SNS-VIB-042B",
    primaryMetric: "vibration",
    severity: "critico",
    effect: { temp: 7, vib: 5.6, current: 1.0, rot: -16 },
    confidence: 86,
    bases: ["ISO 10816-3", "Baseline histórico", "OS anteriores"],
    diagnosis:
      "Vibração acima do limite crítico com oscilação de rotação. Assinatura típica de desbalanceamento/folga mecânica no conjunto girante.",
    recommendation:
      "Programar balanceamento e verificar fixação e folgas. Reinspecionar rolamento do lado acoplamento.",
    evidence: [
      "Vibração cruzou 7,5 m/s² com rotação instável",
      "Padrão difere de defeito localizado de pista (rolamento puro)",
      "Oscilação de rotação acompanha o pico de vibração",
    ],
  },
];

export const getScenario = (id) => SCENARIOS.find((s) => s.id === id) || null;

// Estado do loop num tick global: cenário ativo, fase e intensidade 0..1.
export function liveCycleState(globalTick) {
  const cyc = Math.floor(globalTick / LIVE_CYCLE_LEN);
  const scenario = SCENARIOS[((cyc % SCENARIOS.length) + SCENARIOS.length) % SCENARIOS.length];
  const local = ((globalTick % LIVE_CYCLE_LEN) + LIVE_CYCLE_LEN) % LIVE_CYCLE_LEN;
  const { stable, onset, peak, recovery } = LIVE_PHASES;
  let phase, intensity;
  if (local < stable) {
    phase = "stable";
    intensity = 0;
  } else if (local < stable + onset) {
    phase = "onset";
    intensity = (local - stable) / onset;
  } else if (local < stable + onset + peak) {
    phase = "peak";
    intensity = 1;
  } else {
    phase = "recovery";
    intensity = 1 - (local - stable - onset - peak) / recovery;
  }
  return { scenario, phase, intensity: Math.max(0, Math.min(1, intensity)), cycleIndex: cyc };
}

// Status derivado do envelope — mantém a detecção visual coerente em todo o painel.
export function liveStatusFor(intensity, severity = "critico") {
  if (intensity <= 0.04) return "normal";
  if (intensity >= 0.6) return severity; // pico → severidade do cenário
  return "alerta"; // subida/descida → atenção
}

// Rótulo amigável da fase (narra a demo sozinho).
export function livePhaseLabel(phase, scenario) {
  switch (phase) {
    case "onset":
      return `Detectando: ${scenario.short}`;
    case "peak":
      return scenario.short;
    case "recovery":
      return "Normalizando";
    default:
      return "Operação estável";
  }
}

// Ponto ao vivo determinístico para o loop de cenários (1/seg).
export function liveScenarioPoint(globalTick) {
  const { scenario, phase, intensity, cycleIndex } = liveCycleState(globalTick);
  const rnd = mulberry32((0x9e3779b9 ^ ((globalTick + 1) * 0x85ebca6b)) >>> 0);
  const b = HEARTBEAT.baseline;
  const e = scenario.effect;
  const wobble = Math.sin(globalTick / 6); // micro-oscilação suave

  const temperature = b.temp + intensity * e.temp + wobble * 0.6 + (rnd() - 0.5) * 0.8;
  const vibration = b.vib + intensity * e.vib + wobble * 0.12 + (rnd() - 0.5) * 0.18;
  const current = b.current + intensity * e.current + wobble * 0.3 + (rnd() - 0.5) * 0.4;
  const rotation = b.rot + intensity * e.rot + (rnd() - 0.5) * 6;

  return {
    t: globalTick,
    temperature: round(Math.min(temperature, 96), 1),
    vibration: round(Math.max(vibration, 0.4), 2),
    current: round(Math.max(current, 0), 1),
    rotation: Math.round(rotation),
    scenarioId: scenario.id,
    phase,
    intensity: round(intensity, 2),
    cycleIndex,
  };
}

// ============================================================================
//  PROCEDÊNCIA / TRILHA DE AUDITORIA da recomendação (metadados de integridade)
// ============================================================================
// Responde às perguntas de auditoria: de onde veio o dado (procedência), se foi
// adulterado (integridade), por onde passou (rastreabilidade) e quem assinou
// (trilha de auditoria). Valores fixos => reprodutíveis na demo.
const AUDIT_CURATED = {
  "MTR-BMB-042": {
    traceId: "trace-8baf9a1",
    inputHash: "sha256:demo-fixed-seed-42",
    pipelineVersion: "demo-0.3.0",
    scoringModel: "rules+zscore-v1",
    sourceSensorTags: ["SNS-VIB-042B", "SNS-TEMP-042A"],
    parentAssetTag: "BMB-SUC-004",
    componentTag: "CMP-BRG-042A",
    signedBy: "Forzy TwinOps Demo Engine",
    humanValidation: "Supervisor de turno pendente",
  },
};

export function auditMeta(tag) {
  if (AUDIT_CURATED[tag]) return AUDIT_CURATED[tag];
  const asset = getAsset(tag);
  const seed = seedFromTag(tag).toString(16).padStart(8, "0").slice(0, 7);
  const sourceSensorTags = asset
    ? asset.sensors.filter((s) => s.type !== "Controlador").map((s) => s.tag)
    : [];
  const normal = assetStatus(tag) === "normal";
  return {
    traceId: `trace-${seed}`,
    inputHash: `sha256:demo-${seed}`,
    pipelineVersion: "demo-0.3.0",
    scoringModel: "rules+zscore-v1",
    sourceSensorTags,
    parentAssetTag: asset ? asset.parent : "—",
    componentTag: null,
    signedBy: "Forzy TwinOps Demo Engine",
    humanValidation: normal
      ? "Não requer validação (dentro da faixa)"
      : "Supervisor de turno pendente",
  };
}
