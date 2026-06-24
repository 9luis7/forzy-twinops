// PlantSynoptic.jsx — sinótico AO VIVO da planta (mímico SCADA, vista de cima com profundidade 2.5D).
//
// Centro visual da visão geral: o gêmeo digital no nível da planta. Desenha o "chão de fábrica"
// visto de cima — as 4 áreas como zonas num arranjo 2x2 (A Produção, B Utilidades, C Manutenção,
// D Expedição), cada zona tingida pelo PIOR estado dos seus motores. Os motores conectados
// (assetsByArea) aparecem como pequenos glifos de equipamento (cilindro + eixo) dentro da zona,
// cada um com um LED de estado (pulsando em alerta/crítico), tooltip e clique -> nav.goAsset.
// Clicar na área vazia -> nav.goArea. Tubulações/esteiras ligam as zonas para dar sensação
// industrial; um fundo .scada-grid + uma legenda completam o painel. SVG com viewBox p/ escalar.

import React from "react";
import {
  PLANT,
  areas,
  assetsByArea,
  assetStatus,
  alerts,
  latestReading,
  statusLabel,
} from "../data/mock.js";

// ---- Paleta de estado (mapeada às variáveis de design) -------------------------------
const STATUS_COLOR = {
  normal: "var(--ok)",
  alerta: "var(--alerta)",
  critico: "var(--critico)",
  desconhecido: "var(--texto-fraco)",
};

// Prioridade para apurar o "pior" estado de uma zona.
const STATUS_RANK = { critico: 3, alerta: 2, normal: 1, desconhecido: 0 };

function worstStatus(statuses) {
  let worst = "desconhecido";
  for (const s of statuses) {
    if ((STATUS_RANK[s] ?? 0) > (STATUS_RANK[worst] ?? 0)) worst = s;
  }
  return worst;
}

// ---- Geometria do viewBox -------------------------------------------------------------
const VB_W = 1000;
const VB_H = 620;

// Cada zona ocupa uma célula da grade 2x2. Folga externa + canaleta central.
const PAD = 56; // margem externa
const GAP = 46; // canaleta entre zonas (onde correm os tubos)
const ZONE_W = (VB_W - PAD * 2 - GAP) / 2;
const ZONE_H = (VB_H - PAD * 2 - GAP) / 2 - 8;

// Posições (canto superior-esquerdo) de cada célula no arranjo 2x2.
const CELLS = [
  { col: 0, row: 0 }, // A
  { col: 1, row: 0 }, // B
  { col: 0, row: 1 }, // C
  { col: 1, row: 1 }, // D
];

function cellRect(index) {
  const { col, row } = CELLS[index];
  const x = PAD + col * (ZONE_W + GAP);
  const y = PAD + row * (ZONE_H + GAP) + 8;
  return { x, y, w: ZONE_W, h: ZONE_H };
}

// ---- Glifo de motor (cilindro + eixo, com leve profundidade) --------------------------
function MotorGlyph({ x, y, asset, status, scale = 1 }) {
  const color = STATUS_COLOR[status] || STATUS_COLOR.desconhecido;
  const r = latestReading(asset.tag);
  const temp = r ? `${r.temperature.toFixed(1)}°C` : "—";
  const vib = r ? `${r.vibration.toFixed(2)} m/s²` : "—";
  const tip = `${asset.tag} · ${asset.name} · ${temp} · ${vib}`;
  const pulsing = status === "alerta" || status === "critico";

  // Corpo do motor em coordenadas locais (origem no centro).
  const bodyW = 44 * scale;
  const bodyH = 26 * scale;
  const id = asset.tag.replace(/[^a-zA-Z0-9]/g, "");

  return (
    <g
      transform={`translate(${x},${y})`}
      style={{ cursor: "pointer" }}
      onClick={(e) => {
        e.stopPropagation();
      }}
    >
      <title>{tip}</title>
      {/* Sombra de contato (profundidade). */}
      <ellipse
        cx={0}
        cy={bodyH / 2 + 5 * scale}
        rx={bodyW / 2 + 4 * scale}
        ry={6 * scale}
        fill="#000"
        opacity={0.32}
      />
      {/* Base / pés. */}
      <rect
        x={-bodyW / 2}
        y={bodyH / 2 - 2 * scale}
        width={bodyW}
        height={6 * scale}
        rx={2 * scale}
        fill="var(--surface)"
        stroke="var(--borda)"
        strokeWidth={1}
      />
      {/* Eixo + acoplamento (lado direito). */}
      <rect
        x={bodyW / 2}
        y={-2.4 * scale}
        width={14 * scale}
        height={4.8 * scale}
        rx={2 * scale}
        fill="url(#mm-shaft)"
      />
      <rect
        x={bodyW / 2 + 9 * scale}
        y={-6 * scale}
        width={5 * scale}
        height={12 * scale}
        rx={1.5 * scale}
        fill="var(--surface-3)"
        stroke="var(--borda)"
        strokeWidth={0.8}
      />
      {/* Carcaça cilíndrica com gradiente de volume. */}
      <rect
        x={-bodyW / 2}
        y={-bodyH / 2}
        width={bodyW}
        height={bodyH}
        rx={6 * scale}
        fill={`url(#mm-body)`}
        stroke={color}
        strokeWidth={1.6}
      />
      {/* Aletas de refrigeração (ranhuras). */}
      {[-0.55, -0.28, 0, 0.28, 0.55].map((f, i) => (
        <line
          key={i}
          x1={f * bodyW}
          y1={-bodyH / 2 + 4 * scale}
          x2={f * bodyW}
          y2={bodyH / 2 - 4 * scale}
          stroke="#000"
          strokeOpacity={0.22}
          strokeWidth={1}
        />
      ))}
      {/* Caixa de terminais (topo). */}
      <rect
        x={-7 * scale}
        y={-bodyH / 2 - 8 * scale}
        width={14 * scale}
        height={8 * scale}
        rx={1.6 * scale}
        fill="var(--surface-2)"
        stroke="var(--borda)"
        strokeWidth={0.8}
      />
      {/* Realce superior (luz). */}
      <rect
        x={-bodyW / 2 + 3 * scale}
        y={-bodyH / 2 + 2 * scale}
        width={bodyW - 6 * scale}
        height={4 * scale}
        rx={2 * scale}
        fill="#fff"
        opacity={0.07}
      />
      {/* LED de estado. */}
      {pulsing && (
        <circle cx={0} cy={-bodyH / 2 - 13 * scale} r={5.5 * scale} fill={color} opacity={0.28}>
          <animate
            attributeName="r"
            values={`${4 * scale};${9 * scale};${4 * scale}`}
            dur="1.6s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0.4;0;0.4"
            dur="1.6s"
            repeatCount="indefinite"
          />
        </circle>
      )}
      <circle
        cx={0}
        cy={-bodyH / 2 - 13 * scale}
        r={3.4 * scale}
        fill={color}
        style={{ filter: `drop-shadow(0 0 4px ${color})` }}
      />
    </g>
  );
}

// ---- Componente principal -------------------------------------------------------------
export default function PlantSynoptic({ nav }) {
  // Pré-computa, por área: motores, estados e o pior estado da zona.
  const zones = areas.map((area, i) => {
    const motors = assetsByArea(area.tag);
    const statuses = motors.map((m) => assetStatus(m.tag));
    const worst = motors.length ? worstStatus(statuses) : "desconhecido";
    const counts = statuses.reduce(
      (acc, s) => {
        acc[s] = (acc[s] || 0) + 1;
        return acc;
      },
      { normal: 0, alerta: 0, critico: 0 }
    );
    return { area, motors, statuses, worst, counts, rect: cellRect(i) };
  });

  const totalAlerts = alerts.length;

  // Centro de cada zona (para roteamento dos tubos da canaleta).
  const center = (r) => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 });

  return (
    <div
      className="panel scada-grid"
      data-tour="plant-synoptic"
      style={{
        position: "relative",
        padding: 14,
        borderRadius: 14,
        overflow: "hidden",
      }}
    >
      {/* Cabeçalho do sinótico. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 10,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div
            style={{
              fontSize: 11,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--texto-fraco)",
            }}
          >
            Sinótico da planta · vista de cima
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--texto)" }}>
            {PLANT.name}{" "}
            <span style={{ fontSize: 12, fontWeight: 500, color: "var(--texto-fraco)" }}>
              {PLANT.tag}
            </span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="led ok pulse" />
          <span style={{ fontSize: 12, color: "var(--texto-fraco)" }}>
            {totalAlerts} alertas ativos · {areas.length} áreas
          </span>
        </div>
      </div>

      {/* Mímico SVG escalável. */}
      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        width="100%"
        role="img"
        aria-label="Mímico da planta com áreas e motores monitorados"
        style={{ display: "block" }}
      >
        <defs>
          {/* Gradiente de volume da carcaça do motor. */}
          <linearGradient id="mm-body" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--surface-3)" />
            <stop offset="48%" stopColor="var(--surface-2)" />
            <stop offset="100%" stopColor="var(--surface)" />
          </linearGradient>
          <linearGradient id="mm-shaft" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#cfc6ea" />
            <stop offset="50%" stopColor="#8a82a8" />
            <stop offset="100%" stopColor="#544d72" />
          </linearGradient>
          {/* Gradiente do "piso" da fábrica. */}
          <linearGradient id="mm-floor" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--bg-2)" />
            <stop offset="100%" stopColor="var(--bg)" />
          </linearGradient>
          <filter id="mm-soft" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="6" stdDeviation="10" floodColor="#000" floodOpacity="0.45" />
          </filter>
        </defs>

        {/* Piso da fábrica. */}
        <rect x={0} y={0} width={VB_W} height={VB_H} fill="url(#mm-floor)" />

        {/* Tubos/esteiras industriais na canaleta central (ligam as zonas). */}
        <g stroke="var(--stroke)" strokeWidth={10} fill="none" opacity={0.9}>
          {/* Tronco horizontal central. */}
          <line x1={PAD + 20} y1={VB_H / 2 + 4} x2={VB_W - PAD - 20} y2={VB_H / 2 + 4} />
          {/* Tronco vertical central. */}
          <line x1={VB_W / 2} y1={PAD + 20} x2={VB_W / 2} y2={VB_H - PAD - 20} />
        </g>
        <g stroke="var(--roxo)" strokeWidth={2} fill="none" opacity={0.5} strokeDasharray="6 8">
          <line x1={PAD + 20} y1={VB_H / 2 + 4} x2={VB_W - PAD - 20} y2={VB_H / 2 + 4} />
          <line x1={VB_W / 2} y1={PAD + 20} x2={VB_W / 2} y2={VB_H - PAD - 20} />
        </g>
        {/* Conexão / flange central. */}
        <circle
          cx={VB_W / 2}
          cy={VB_H / 2 + 4}
          r={14}
          fill="var(--surface-2)"
          stroke="var(--stroke)"
          strokeWidth={2}
        />

        {/* Zonas (áreas). */}
        {zones.map(({ area, motors, worst, counts, rect }) => {
          const color = STATUS_COLOR[worst];
          const c = center(rect);
          // Layout dos motores em grade dentro da zona (abaixo do cabeçalho da zona).
          const cols = Math.min(3, Math.max(1, motors.length));
          const innerTop = rect.y + 70;
          const innerH = rect.y + rect.h - 26 - innerTop;
          const colW = rect.w / (cols + 1);
          const rows = Math.max(1, Math.ceil(motors.length / cols));

          return (
            <g key={area.tag}>
              {/* Corpo da zona (clicável -> área). */}
              <g
                style={{ cursor: "pointer" }}
                onClick={() => nav.goArea(area.tag)}
                filter="url(#mm-soft)"
              >
                <title>{`${area.name} · ${area.tag} · ${statusLabel(worst)}`}</title>
                {/* Painel da zona com leve tinta do estado. */}
                <rect
                  x={rect.x}
                  y={rect.y}
                  width={rect.w}
                  height={rect.h}
                  rx={16}
                  fill="var(--panel)"
                  stroke={color}
                  strokeWidth={1.6}
                  strokeOpacity={0.55}
                />
                {/* Faixa de status à esquerda. */}
                <rect x={rect.x} y={rect.y} width={6} height={rect.h} rx={3} fill={color} />
                {/* Tinta sutil do estado no topo. */}
                <rect
                  x={rect.x}
                  y={rect.y}
                  width={rect.w}
                  height={rect.h}
                  rx={16}
                  fill={color}
                  opacity={0.05}
                />
                {/* Realce superior. */}
                <rect
                  x={rect.x + 8}
                  y={rect.y + 4}
                  width={rect.w - 16}
                  height={3}
                  rx={1.5}
                  fill="#fff"
                  opacity={0.06}
                />
              </g>

              {/* Cabeçalho da zona (letra + ícone + nome + LED + contagens). */}
              <g pointerEvents="none">
                {/* Selo da letra. */}
                <rect
                  x={rect.x + 18}
                  y={rect.y + 16}
                  width={34}
                  height={34}
                  rx={9}
                  fill="var(--surface-2)"
                  stroke={color}
                  strokeWidth={1.4}
                />
                <text
                  x={rect.x + 35}
                  y={rect.y + 33}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={18}
                  fontWeight={800}
                  fill={color}
                >
                  {area.letter}
                </text>
                {/* Ícone + nome. */}
                <text x={rect.x + 62} y={rect.y + 28} fontSize={16}>
                  {area.icon}
                </text>
                <text
                  x={rect.x + 86}
                  y={rect.y + 33}
                  fontSize={16}
                  fontWeight={700}
                  fill="var(--texto)"
                >
                  {area.name}
                </text>
                {/* LED de estado da zona. */}
                <circle
                  cx={rect.x + rect.w - 26}
                  cy={rect.y + 32}
                  r={5}
                  fill={color}
                  style={{ filter: `drop-shadow(0 0 5px ${color})` }}
                />
                {/* TAG + contagens (camada técnica secundária). */}
                <text
                  x={rect.x + 18}
                  y={rect.y + 60}
                  fontSize={11}
                  fill="var(--texto-fraco)"
                  letterSpacing="0.04em"
                >
                  {area.tag} · {motors.length} de {area.assetsCount} ativos · {statusLabel(worst)}
                </text>
                {/* Mini-contagens por estado. */}
                {counts.critico > 0 && (
                  <text
                    x={rect.x + rect.w - 18}
                    y={rect.y + 60}
                    textAnchor="end"
                    fontSize={11}
                    fontWeight={700}
                    fill="var(--critico)"
                  >
                    {counts.critico} crít.
                  </text>
                )}
                {counts.critico === 0 && counts.alerta > 0 && (
                  <text
                    x={rect.x + rect.w - 18}
                    y={rect.y + 60}
                    textAnchor="end"
                    fontSize={11}
                    fontWeight={700}
                    fill="var(--alerta)"
                  >
                    {counts.alerta} aten.
                  </text>
                )}
              </g>

              {/* Stub de tubo da zona até a canaleta central. */}
              <line
                x1={c.x}
                y1={c.y}
                x2={VB_W / 2}
                y2={VB_H / 2 + 4}
                stroke="var(--stroke)"
                strokeWidth={4}
                opacity={0.35}
                strokeLinecap="round"
              />

              {/* Glifos de motor dentro da zona. */}
              {motors.map((m, mi) => {
                const col = mi % cols;
                const row = Math.floor(mi / cols);
                const gx = rect.x + colW * (col + 1);
                const rowH = innerH / rows;
                const gy = innerTop + rowH * (row + 0.5);
                return (
                  <g key={m.tag} onClick={() => nav.goAsset(m.tag)} style={{ cursor: "pointer" }}>
                    <MotorGlyph
                      x={gx}
                      y={gy}
                      asset={m}
                      status={assetStatus(m.tag)}
                      scale={0.95}
                    />
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>

      {/* Legenda de estados. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 18,
          marginTop: 10,
          flexWrap: "wrap",
          fontSize: 12,
          color: "var(--texto-fraco)",
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
          <span className="led ok" /> Normal
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
          <span className="led alerta" /> Atenção
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
          <span className="led critico" /> Crítico
        </span>
        <span style={{ marginLeft: "auto", fontSize: 11 }}>
          Clique num motor para abrir o ativo · clique na zona para abrir a área
        </span>
      </div>
    </div>
  );
}
