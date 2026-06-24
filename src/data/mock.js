// mock.js — dados sintéticos gerados a partir do schema Supabase (assets + readings).
// Geração em RUNTIME com seed fixa por TAG => mesma série a cada carregamento (reprodutível).
//
// Schema de referência:
//   assets(tag, name, motor_type, sector)
//   readings(asset_tag, ts, temperature [°C], current [A], vibration [m/s²], rotation [RPM])
//
// Janela: 24h, 1 ponto a cada 5 min (~288 pontos/motor).
// Faixas físicas plausíveis: temp 35–85 °C | vibração 0.5–8 m/s² | rotação ~1750–3500 RPM.

// ---------- PRNG determinístico (mulberry32) ----------
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

// ---------- assets ----------
export const assets = [
  {
    tag: "MOT-001",
    name: "WEG W22-IR3 Premium",
    motor_type: "Indução trifásico 7.5kW 220V",
    sector: "Compressores",
    note: "Ativo real — primeiro a falar. Baseline normal.",
  },
  {
    tag: "MOT-002",
    name: "Motor Bomba B2",
    motor_type: "Indução trifásico 5.5kW",
    sector: "Bombas",
    note: "Operação normal.",
  },
  {
    tag: "MOT-003",
    name: "Motor Ventilação V1",
    motor_type: "Indução trifásico 4kW",
    sector: "Ventilação",
    note: "Tendência de degradação (temperatura e vibração subindo).",
  },
  {
    tag: "MOT-004",
    name: "Motor Esteira E4",
    motor_type: "Indução trifásico 3kW",
    sector: "Esteiras",
    note: "Operação normal.",
  },
];

// Perfil de baseline por motor (valores médios + amplitude de ruído).
const PROFILE = {
  "MOT-001": { temp: 55, current: 24, vib: 1.8, rot: 1760, degrading: false },
  "MOT-002": { temp: 50, current: 18, vib: 1.5, rot: 1750, degrading: false },
  "MOT-003": { temp: 52, current: 15, vib: 2.0, rot: 3500, degrading: true },
  "MOT-004": { temp: 45, current: 12, vib: 1.2, rot: 1760, degrading: false },
};

// ---------- parâmetros da série ----------
const POINTS = 288; // 24h a cada 5 min
const STEP_MS = 5 * 60 * 1000; // 5 minutos
const WINDOW_MS = (POINTS - 1) * STEP_MS;

const round = (v, d = 2) => {
  const f = 10 ** d;
  return Math.round(v * f) / f;
};

// Gera a série de leituras de um motor (ordem cronológica, termina "agora").
function generateReadings(tag, endTs = Date.now()) {
  const p = PROFILE[tag];
  const rnd = mulberry32(seedFromTag(tag));
  const start = endTs - WINDOW_MS;
  const out = [];

  for (let i = 0; i < POINTS; i++) {
    const ts = start + i * STEP_MS;
    const frac = i / (POINTS - 1); // 0 -> 1 ao longo da janela
    // Ciclo diário suave (turno) + ruído.
    const diurnal = Math.sin(frac * Math.PI * 2 - Math.PI / 2);

    // Rampa de degradação só no MOT-003 (cresce ao longo do tempo).
    const ramp = p.degrading ? frac : 0;

    const temperature =
      p.temp + diurnal * 3 + (rnd() - 0.5) * 1.5 + ramp * 26; // sobe ~26°C no fim
    const vibration =
      p.vib + diurnal * 0.15 + (rnd() - 0.5) * 0.25 + ramp * 4.5; // sobe ~4.5 m/s²
    const current =
      p.current + diurnal * 0.8 + (rnd() - 0.5) * 0.6 + ramp * 3; // leve aumento de carga
    const rotation =
      p.rot - ramp * 40 + (rnd() - 0.5) * 8; // leve queda de RPM sob esforço

    out.push({
      asset_tag: tag,
      ts: new Date(ts).toISOString(),
      temperature: round(Math.min(temperature, 85), 1),
      current: round(current, 1),
      vibration: round(Math.max(vibration, 0.5), 2),
      rotation: Math.round(rotation),
    });
  }
  return out;
}

// readings: { "MOT-001": [...], ... }
export const readings = Object.fromEntries(
  assets.map((a) => [a.tag, generateReadings(a.tag)])
);

// ---------- helpers de conveniência ----------
export const latestReading = (tag) => {
  const arr = readings[tag];
  return arr ? arr[arr.length - 1] : null;
};

// Limiares simples para estado operacional (mock visual).
const THRESHOLDS = { temp: { warn: 65, crit: 75 }, vib: { warn: 4.5, crit: 6 } };

export function assetStatus(tag) {
  const r = latestReading(tag);
  if (!r) return "desconhecido";
  if (r.temperature >= THRESHOLDS.temp.crit || r.vibration >= THRESHOLDS.vib.crit)
    return "critico";
  if (r.temperature >= THRESHOLDS.temp.warn || r.vibration >= THRESHOLDS.vib.warn)
    return "alerta";
  return "normal";
}

export const getAsset = (tag) => assets.find((a) => a.tag === tag) || null;
