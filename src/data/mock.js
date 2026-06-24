// mock.js — dados sintéticos gerados a partir do schema Supabase (assets + readings).
// STUB — geração a construir. Faixas físicas plausíveis:
//   temperatura 35–85 °C | corrente conforme potência | vibração 0.5–8 m/s² | rotação ~1750–3500 RPM

export const assets = [
  { tag: "MOT-001", name: "WEG W22-IR3 Premium", motor_type: "Indução trifásico 7.5kW 220V", sector: "Compressores" },
  { tag: "MOT-002", name: "Motor Bomba B2", motor_type: "Indução", sector: "Bombas" },
  { tag: "MOT-003", name: "Motor Ventilação V1", motor_type: "Indução", sector: "Ventilação" }, // tendência de degradação
  { tag: "MOT-004", name: "Motor Esteira E4", motor_type: "Indução", sector: "Esteiras" },
];

// readings: série por motor (24–48h, downsampled). A gerar.
export const readings = {};
