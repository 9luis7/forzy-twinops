// Gauge.jsx — medidor radial (estilo instrumento SCADA) em SVG puro, sem dependências.
// Arco de ~240° com zonas verde/âmbar/vermelho derivadas de warn/crit na escala [min,max].
// Um ponteiro/arco-indicador aponta para o valor; leitura central grande colorida pela zona.
// Se warn/crit forem nulos, usa um único arco --cyan e leitura neutra.

import React from "react";

// Geometria do arco: varredura de 240°, indo de 150° (esquerda-baixo) a -30° (direita-baixo).
const START_ANGLE = 150; // graus
const SWEEP = 240; // graus de varredura total
const END_ANGLE = START_ANGLE - SWEEP; // -90 ... na prática usamos START..START-SWEEP

// Converte um ângulo (graus, sentido horário a partir do eixo X positivo) em ponto no círculo.
// Usamos coordenadas SVG (y cresce para baixo), então invertemos o seno.
function polar(cx, cy, r, angleDeg) {
  const a = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
}

// Descreve um arco SVG entre dois ângulos (em graus), do maior para o menor (sentido horário).
function arcPath(cx, cy, r, a0, a1) {
  const start = polar(cx, cy, r, a0);
  const end = polar(cx, cy, r, a1);
  const largeArc = Math.abs(a0 - a1) > 180 ? 1 : 0;
  // sweep-flag 1 = sentido horário no sistema de tela (y para baixo)
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

// Mapeia um valor em [min,max] para o ângulo correspondente no arco.
function valueToAngle(v, min, max) {
  const t = max === min ? 0 : (v - min) / (max - min);
  return START_ANGLE - t * SWEEP;
}

export default function Gauge({
  label,
  value,
  unit = "",
  min = 0,
  max = 100,
  warn = null,
  crit = null,
  size = 160,
}) {
  // Clamp do valor à faixa.
  const safeMin = Number(min);
  const safeMax = Number(max);
  const raw = Number.isFinite(Number(value)) ? Number(value) : safeMin;
  const v = Math.max(safeMin, Math.min(safeMax, raw));

  const hasZones = warn != null && crit != null;

  // Determina a zona atual do valor.
  let zone = "ok"; // ok | warn | crit | neutral
  if (hasZones) {
    if (raw >= crit) zone = "crit";
    else if (raw >= warn) zone = "warn";
    else zone = "ok";
  } else {
    zone = "neutral";
  }

  const zoneColor = {
    ok: "var(--ok)",
    warn: "var(--alerta)",
    crit: "var(--critico)",
    neutral: "var(--cyan)",
  }[zone];

  const zoneReadoutCls = {
    ok: "readout ok",
    warn: "readout warn",
    crit: "readout crit",
    neutral: "readout",
  }[zone];

  // Geometria do desenho.
  const cx = size / 2;
  const cy = size / 2;
  const stroke = Math.max(8, size * 0.07);
  const r = size / 2 - stroke / 2 - size * 0.04;

  // Ângulos das fronteiras de zona (clamp dentro da faixa para evitar arcos inválidos).
  const clampToRange = (x) => Math.max(safeMin, Math.min(safeMax, x));
  const aStart = START_ANGLE;
  const aEnd = END_ANGLE;

  // Constrói os segmentos de arco coloridos.
  const segments = [];
  if (hasZones) {
    const wClamped = clampToRange(warn);
    const cClamped = clampToRange(crit);
    const aWarn = valueToAngle(wClamped, safeMin, safeMax);
    const aCrit = valueToAngle(cClamped, safeMin, safeMax);
    // Zona OK: de início até warn.
    if (aStart > aWarn) segments.push({ a0: aStart, a1: aWarn, color: "var(--ok)" });
    // Zona alerta: de warn até crit.
    if (aWarn > aCrit) segments.push({ a0: aWarn, a1: aCrit, color: "var(--alerta)" });
    // Zona crítica: de crit até o fim.
    if (aCrit > aEnd) segments.push({ a0: aCrit, a1: aEnd, color: "var(--critico)" });
  }

  // Ângulo do indicador.
  const aValue = valueToAngle(v, safeMin, safeMax);
  const needleOuter = polar(cx, cy, r + stroke * 0.15, aValue);
  const needleInner = polar(cx, cy, r - stroke * 0.95, aValue);
  const tip = polar(cx, cy, r + stroke * 0.5, aValue);

  // Marcadores de extremidade (min/max).
  const minPt = polar(cx, cy, r - stroke - size * 0.04, aStart);
  const maxPt = polar(cx, cy, r - stroke - size * 0.04, aEnd);

  // Formatação numérica.
  const display =
    Math.abs(raw) >= 100 ? Math.round(raw).toString() : raw.toFixed(1);

  const fontMain = size * 0.2;
  const fontUnit = size * 0.1;
  const fontLabel = size * 0.085;

  return (
    <div
      style={{
        display: "inline-flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 2,
      }}
    >
      <svg
        width={size}
        height={size * 0.86}
        viewBox={`0 0 ${size} ${size * 0.86}`}
        role="img"
        aria-label={`${label}: ${display} ${unit}`}
        style={{ overflow: "visible" }}
      >
        {/* Trilho de fundo (sempre presente). */}
        <path
          d={arcPath(cx, cy, r, aStart, aEnd)}
          fill="none"
          stroke="var(--borda)"
          strokeWidth={stroke}
          strokeLinecap="round"
          opacity={0.55}
        />

        {/* Arco neutro (--cyan) quando não há zonas. */}
        {!hasZones && (
          <path
            d={arcPath(cx, cy, r, aStart, aValue)}
            fill="none"
            stroke="var(--cyan)"
            strokeWidth={stroke}
            strokeLinecap="round"
            style={{ filter: "drop-shadow(0 0 4px var(--cyan))" }}
          />
        )}

        {/* Zonas coloridas (quando há warn/crit). */}
        {hasZones &&
          segments.map((s, i) => (
            <path
              key={i}
              d={arcPath(cx, cy, r, s.a0, s.a1)}
              fill="none"
              stroke={s.color}
              strokeWidth={stroke}
              strokeLinecap={
                i === 0 || i === segments.length - 1 ? "round" : "butt"
              }
              opacity={0.85}
            />
          ))}

        {/* Indicador (ponteiro fino) apontando para o valor. */}
        <line
          x1={needleInner.x}
          y1={needleInner.y}
          x2={needleOuter.x}
          y2={needleOuter.y}
          stroke="var(--texto)"
          strokeWidth={Math.max(2, size * 0.018)}
          strokeLinecap="round"
        />
        {/* Ponta brilhante na cor da zona. */}
        <circle
          cx={tip.x}
          cy={tip.y}
          r={Math.max(3, size * 0.028)}
          fill={zoneColor}
          style={{ filter: `drop-shadow(0 0 5px ${zoneColor})` }}
        />
        {/* Cubo central do ponteiro. */}
        <circle
          cx={cx}
          cy={cy}
          r={Math.max(3, size * 0.03)}
          fill="var(--surface-3)"
          stroke="var(--stroke)"
          strokeWidth={1}
        />

        {/* Marcadores min/max. */}
        <text
          x={minPt.x}
          y={minPt.y}
          fill="var(--texto-fraco)"
          fontSize={size * 0.07}
          textAnchor="middle"
          dominantBaseline="middle"
        >
          {safeMin}
        </text>
        <text
          x={maxPt.x}
          y={maxPt.y}
          fill="var(--texto-fraco)"
          fontSize={size * 0.07}
          textAnchor="middle"
          dominantBaseline="middle"
        >
          {safeMax}
        </text>

        {/* Leitura central grande. */}
        <text
          x={cx}
          y={cy + fontMain * 0.18}
          textAnchor="middle"
          className={zoneReadoutCls}
          fill={zoneColor}
          style={{
            fontSize: fontMain,
            fontWeight: 700,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {display}
          {unit ? (
            <tspan fontSize={fontUnit} dx={size * 0.02} fill={zoneColor}>
              {unit}
            </tspan>
          ) : null}
        </text>
      </svg>

      {label ? (
        <div
          style={{
            fontSize: fontLabel,
            color: "var(--texto-fraco)",
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            textAlign: "center",
            marginTop: -4,
          }}
        >
          {label}
        </div>
      ) : null}
    </div>
  );
}
