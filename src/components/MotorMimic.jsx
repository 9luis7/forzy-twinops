// MotorMimic.jsx — "gêmeo digital" 2.5D do motor de indução trifásico (SVG puro).
// Desenha um motor horizontal reconhecível com profundidade (gradientes + sombra suave):
// carcaça cilíndrica com aletas de refrigeração, lado acoplamento (eixo + flange), tampa
// defletora/grelha do ventilador no lado oposto, caixa de ligação no topo, rolamentos nas
// duas pontas, e pés/base. Os sensores ficam ancorados em pontos de montagem fisicamente
// plausíveis e rotulados por TAG (Vibração no rolamento do lado acoplamento, Temperatura na
// carcaça, Corrente como garra no cabo da caixa de ligação). Regiões clicáveis mapeiam para
// componentes por tipo (Rolamento→rolamento, Estator→carcaça, Eixo→eixo). Quando o estado do
// motor é diferente de "normal", o(s) componente(s) sob suspeita (status !== "normal") brilham/
// pulsam (âmbar p/ alerta, vermelho p/ crítico). O componente ativo recebe contorno de seleção.
// Callouts ao vivo: temperatura junto à carcaça, vibração junto ao rolamento.
// Puramente apresentacional — todos os dados chegam via props.

import React from "react";

// Cor de status -> token CSS.
const statusColor = (s) =>
  s === "critico" ? "var(--critico)" : s === "alerta" ? "var(--alerta)" : "var(--ok)";

// Localiza o componente que mapeia para uma região, por tipo.
const componentByType = (components, type) =>
  (components || []).find((c) => c.type === type) || null;

// Localiza o sensor de um tipo no ativo.
const sensorByType = (asset, type) =>
  (asset?.sensors || []).find((s) => s.type === type) || null;

export default function MotorMimic({
  asset,
  reading,
  components = [],
  status = "normal",
  activeComponent = null,
  onSelectComponent,
}) {
  const motorAlert = status !== "normal" && status !== "desconhecido";

  // Mapeamento região física -> componente.
  const cmpRolamento = componentByType(components, "Rolamento"); // -> rolamento (lado acoplamento)
  const cmpEstator = componentByType(components, "Estator"); // -> carcaça/estator
  const cmpEixo = componentByType(components, "Eixo"); // -> eixo/acoplamento

  // Uma região é "sob suspeita" (glow/pulse) quando o motor não está normal
  // E o componente correspondente está fora do normal.
  const suspect = (cmp) =>
    motorAlert && cmp && cmp.status && cmp.status !== "normal";

  const isActive = (cmp) => cmp && activeComponent === cmp.tag;

  const handleSelect = (cmp) => {
    if (cmp && typeof onSelectComponent === "function") onSelectComponent(cmp.tag);
  };

  // Sensores ancorados.
  const snsVib = sensorByType(asset, "Vibração");
  const snsTemp = sensorByType(asset, "Temperatura");
  const snsCor = sensorByType(asset, "Corrente");

  // Leituras ao vivo.
  const tempVal = reading?.temperature;
  const vibVal = reading?.vibration;

  // Halo (filtro de brilho) por estado para regiões suspeitas/ativas.
  const haloColor = (cmp) => {
    if (isActive(cmp)) return "var(--roxo-claro)";
    if (suspect(cmp)) return statusColor(cmp.status);
    return null;
  };

  // Estilo de uma região clicável: contorno de seleção e/ou halo pulsante.
  const regionStyle = (cmp, baseColor) => {
    const halo = haloColor(cmp);
    return {
      cursor: cmp ? "pointer" : "default",
      filter: halo ? `drop-shadow(0 0 6px ${halo}) drop-shadow(0 0 14px ${halo})` : undefined,
      transition: "filter .25s ease",
    };
  };

  // Classe de animação de pulso (definida no <style> local).
  const pulseClass = (cmp) => (suspect(cmp) && !isActive(cmp) ? "mm-pulse" : "");

  // Geometria base do desenho (viewBox 0 0 720 420).
  // O motor é desenhado deitado: ventilador à esquerda, acoplamento/eixo à direita.

  return (
    <div data-tour="motor-mimic" className="card mm-root" style={{ position: "relative" }}>
      {/* Estilos locais (animações + tipografia dos callouts) — sem tocar styles.css. */}
      <style>{`
        .mm-root h3 { margin: 0 0 4px; }
        .mm-svg { width: 100%; height: auto; display: block; overflow: visible; }
        @keyframes mm-pulseKey {
          0%, 100% { opacity: .55; }
          50%      { opacity: 1; }
        }
        .mm-pulse { animation: mm-pulseKey 1.4s ease-in-out infinite; }
        .mm-hot { transition: filter .25s ease; }
        .mm-hot:hover { filter: drop-shadow(0 0 5px var(--roxo-claro)); }
        .mm-callout-box {
          fill: var(--panel-2, rgba(36,26,69,.66));
          stroke: var(--stroke, rgba(154,108,255,.18));
          stroke-width: 1;
        }
        .mm-callout-val { font-variant-numeric: tabular-nums; font-weight: 700; }
        .mm-tag { font-size: 11px; fill: var(--texto-fraco); font-variant-numeric: tabular-nums; }
        .mm-pin { fill: var(--cyan); }
      `}</style>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <h3>
          Gêmeo digital do motor{" "}
          <span className="muted small" style={{ fontWeight: 400 }}>
            · representação 2.5D · clique numa parte
          </span>
        </h3>
        <span className="muted small">
          {motorAlert ? "Parte sob suspeita destacada" : "Operação normal"}
        </span>
      </div>

      <svg
        className="mm-svg"
        viewBox="0 0 720 420"
        role="img"
        aria-label="Desenho do motor com sensores e componentes"
      >
        <defs>
          {/* Volume cilíndrico da carcaça (gradiente vertical -> sensação 3D). */}
          <linearGradient id="mmHousing" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3a2c63" />
            <stop offset="22%" stopColor="#4a3884" />
            <stop offset="50%" stopColor="#2c2055" />
            <stop offset="82%" stopColor="#1c1538" />
            <stop offset="100%" stopColor="#140f2a" />
          </linearGradient>
          {/* Realce especular superior da carcaça. */}
          <linearGradient id="mmHousingHi" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#a78bfa" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#a78bfa" stopOpacity="0" />
          </linearGradient>
          {/* Tampas/flanges (cinza metálico). */}
          <linearGradient id="mmCap" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5a5275" />
            <stop offset="45%" stopColor="#3a3358" />
            <stop offset="100%" stopColor="#231d3e" />
          </linearGradient>
          {/* Eixo metálico (aço). */}
          <linearGradient id="mmShaft" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#cfd2e0" />
            <stop offset="45%" stopColor="#9aa0bd" />
            <stop offset="55%" stopColor="#7f86a8" />
            <stop offset="100%" stopColor="#4c5274" />
          </linearGradient>
          {/* Base/pés. */}
          <linearGradient id="mmBase" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2a2348" />
            <stop offset="100%" stopColor="#15102a" />
          </linearGradient>
          {/* Sombra de contato sob o motor. */}
          <radialGradient id="mmShadow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#000" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#000" stopOpacity="0" />
          </radialGradient>
          {/* Sombra suave (profundidade) para os corpos. */}
          <filter id="mmSoft" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="10" stdDeviation="10" floodColor="#000" floodOpacity="0.45" />
          </filter>
        </defs>

        {/* Piso / grade SCADA sutil. */}
        <rect x="0" y="0" width="720" height="420" fill="none" />
        {/* Sombra de contato no chão. */}
        <ellipse cx="360" cy="360" rx="290" ry="34" fill="url(#mmShadow)" />

        {/* ====================== BASE / PÉS ====================== */}
        <g filter="url(#mmSoft)">
          {/* Trilho da base. */}
          <rect x="150" y="318" width="430" height="26" rx="6" fill="url(#mmBase)" stroke="var(--borda)" strokeWidth="1" />
          {/* Pés (quatro apoios). */}
          {[180, 300, 420, 540].map((x) => (
            <rect key={x} x={x} y="300" width="34" height="26" rx="4" fill="url(#mmCap)" stroke="var(--borda)" strokeWidth="1" />
          ))}
        </g>

        {/* ====================== TAMPA DEFLETORA / VENTILADOR (lado não-acoplamento, esquerda) ====================== */}
        <g filter="url(#mmSoft)">
          {/* Capa do ventilador (grelha). */}
          <ellipse cx="170" cy="210" rx="34" ry="88" fill="url(#mmCap)" stroke="var(--borda)" strokeWidth="1.5" />
          {/* Grelha radial. */}
          <g stroke="#15102a" strokeWidth="2" opacity="0.8">
            {Array.from({ length: 9 }).map((_, i) => {
              const a = (i / 9) * Math.PI * 2;
              return (
                <line
                  key={i}
                  x1={170}
                  y1={210}
                  x2={170 + Math.cos(a) * 30}
                  y2={210 + Math.sin(a) * 80}
                />
              );
            })}
            <ellipse cx="170" cy="210" rx="20" ry="52" fill="none" />
            <ellipse cx="170" cy="210" rx="10" ry="26" fill="none" />
          </g>
        </g>

        {/* ====================== CARCAÇA / ESTATOR (corpo cilíndrico aletado) — REGIÃO CLICÁVEL ====================== */}
        <g
          className={`mm-hot ${pulseClass(cmpEstator)}`}
          style={regionStyle(cmpEstator)}
          onClick={() => handleSelect(cmpEstator)}
          filter="url(#mmSoft)"
        >
          {/* Corpo principal da carcaça. */}
          <rect x="200" y="122" width="300" height="176" rx="26" fill="url(#mmHousing)" stroke="var(--borda)" strokeWidth="1.5" />
          {/* Aletas de refrigeração (ribs verticais). */}
          <g stroke="#0f0b22" strokeWidth="3" opacity="0.55">
            {Array.from({ length: 13 }).map((_, i) => {
              const x = 216 + i * 21;
              return <line key={i} x1={x} y1="128" x2={x} y2="292" />;
            })}
          </g>
          {/* Realce especular no topo (volume cilíndrico). */}
          <rect x="208" y="126" width="284" height="40" rx="20" fill="url(#mmHousingHi)" />
          {/* Anéis das extremidades (dão volume de tubo). */}
          <ellipse cx="200" cy="210" rx="14" ry="88" fill="#241a45" stroke="var(--borda)" strokeWidth="1.5" />
          <ellipse cx="500" cy="210" rx="14" ry="88" fill="#2c2055" stroke="var(--borda)" strokeWidth="1.5" />

          {/* Contorno de seleção do componente ativo (Estator). */}
          {isActive(cmpEstator) && (
            <rect x="196" y="118" width="308" height="184" rx="28" fill="none"
              stroke="var(--roxo-claro)" strokeWidth="2.5" strokeDasharray="6 5" />
          )}
        </g>

        {/* ====================== CAIXA DE LIGAÇÃO (terminal box, no topo) ====================== */}
        <g filter="url(#mmSoft)">
          <rect x="312" y="86" width="96" height="48" rx="7" fill="url(#mmCap)" stroke="var(--borda)" strokeWidth="1.5" />
          <rect x="320" y="92" width="80" height="14" rx="3" fill="#15102a" opacity="0.7" />
          {/* Parafusos. */}
          {[322, 398].map((x) => (
            <circle key={x} cx={x} cy="128" r="3" fill="#15102a" />
          ))}
        </g>

        {/* ====================== TAMPA DO LADO ACOPLAMENTO (drive-end, direita) ====================== */}
        <g filter="url(#mmSoft)">
          <ellipse cx="506" cy="210" rx="22" ry="92" fill="url(#mmCap)" stroke="var(--borda)" strokeWidth="1.5" />
          {/* Flange de acoplamento. */}
          <ellipse cx="524" cy="210" rx="12" ry="58" fill="url(#mmCap)" stroke="var(--borda)" strokeWidth="1.5" />
          {/* Parafusos da flange. */}
          {Array.from({ length: 6 }).map((_, i) => {
            const a = (i / 6) * Math.PI * 2;
            return <circle key={i} cx={524 + Math.cos(a) * 7} cy={210 + Math.sin(a) * 42} r="2.6" fill="#15102a" />;
          })}
        </g>

        {/* ====================== EIXO + ACOPLAMENTO — REGIÃO CLICÁVEL (Eixo) ====================== */}
        <g
          className={`mm-hot ${pulseClass(cmpEixo)}`}
          style={regionStyle(cmpEixo)}
          onClick={() => handleSelect(cmpEixo)}
        >
          {/* Eixo de saída. */}
          <rect x="536" y="198" width="78" height="24" rx="6" fill="url(#mmShaft)" stroke="var(--borda)" strokeWidth="1" />
          {/* Chaveta (rasgo) no eixo. */}
          <rect x="552" y="201" width="22" height="5" rx="2" fill="#2a2f47" />
          {/* Luva de acoplamento. */}
          <rect x="600" y="186" width="40" height="48" rx="8" fill="url(#mmCap)" stroke="var(--borda)" strokeWidth="1.5" />
          <line x1="620" y1="186" x2="620" y2="234" stroke="#15102a" strokeWidth="2" />

          {/* Contorno de seleção do componente ativo (Eixo). */}
          {isActive(cmpEixo) && (
            <rect x="532" y="180" width="112" height="60" rx="10" fill="none"
              stroke="var(--roxo-claro)" strokeWidth="2.5" strokeDasharray="6 5" />
          )}
        </g>

        {/* ====================== ROLAMENTO LADO ACOPLAMENTO — REGIÃO CLICÁVEL (Rolamento) ====================== */}
        <g
          className={`mm-hot ${pulseClass(cmpRolamento)}`}
          style={regionStyle(cmpRolamento)}
          onClick={() => handleSelect(cmpRolamento)}
        >
          {/* Anel do rolamento (na junção carcaça/tampa do lado acoplamento). */}
          <ellipse cx="500" cy="210" rx="18" ry="46" fill="none" stroke={suspect(cmpRolamento) ? statusColor(cmpRolamento.status) : "var(--roxo-claro)"} strokeWidth="4" opacity="0.9" />
          <ellipse cx="500" cy="210" rx="11" ry="30" fill="none" stroke="#15102a" strokeWidth="2" opacity="0.7" />
          {/* Esferas do rolamento (sugestão). */}
          {Array.from({ length: 6 }).map((_, i) => {
            const a = (i / 6) * Math.PI * 2;
            return <circle key={i} cx={500 + Math.cos(a) * 14.5} cy={210 + Math.sin(a) * 38} r="3" fill="#cfd2e0" opacity="0.85" />;
          })}

          {/* Contorno de seleção do componente ativo (Rolamento). */}
          {isActive(cmpRolamento) && (
            <ellipse cx="500" cy="210" rx="24" ry="54" fill="none"
              stroke="var(--roxo-claro)" strokeWidth="2.5" strokeDasharray="6 5" />
          )}
        </g>

        {/* ====================== ROLAMENTO LADO NÃO-ACOPLAMENTO (apenas visual) ====================== */}
        <ellipse cx="200" cy="210" rx="9" ry="30" fill="none" stroke="#5a5275" strokeWidth="2.5" opacity="0.6" />

        {/* ====================== SENSORES (ancorados nos pontos de montagem) ====================== */}

        {/* Sensor de TEMPERATURA — na carcaça (topo do corpo). */}
        {snsTemp && (
          <g>
            <line x1="270" y1="150" x2="270" y2="122" stroke="var(--cyan)" strokeWidth="2" />
            <rect x="258" y="138" width="24" height="16" rx="3" fill="#15102a" stroke="var(--cyan)" strokeWidth="1.5" />
            <circle cx="270" cy="146" r="3.2" className="mm-pin" />
          </g>
        )}

        {/* Sensor de VIBRAÇÃO — no rolamento do lado acoplamento. */}
        {snsVib && (
          <g>
            <line x1="500" y1="172" x2="500" y2="150" stroke="var(--cyan)" strokeWidth="2" />
            <rect x="488" y="138" width="24" height="16" rx="3" fill="#15102a" stroke="var(--cyan)" strokeWidth="1.5" />
            <circle cx="500" cy="146" r="3.2" className="mm-pin" />
          </g>
        )}

        {/* Sensor de CORRENTE — garra (clamp) no cabo que sai da caixa de ligação. */}
        {snsCor && (
          <g>
            {/* Cabo descendo da caixa de ligação. */}
            <path d="M 360 86 C 360 60, 408 56, 408 40" fill="none" stroke="#15102a" strokeWidth="5" strokeLinecap="round" />
            <path d="M 360 86 C 360 60, 408 56, 408 40" fill="none" stroke="#3a3358" strokeWidth="2" strokeLinecap="round" />
            {/* Garra amperimétrica. */}
            <g transform="translate(408 52)">
              <ellipse cx="0" cy="0" rx="13" ry="15" fill="none" stroke="var(--cyan)" strokeWidth="3.5" />
              <circle cx="0" cy="0" r="3" className="mm-pin" />
            </g>
          </g>
        )}

        {/* ====================== RÓTULOS DE TAG DOS SENSORES ====================== */}
        {snsTemp && (
          <text x="270" y="116" textAnchor="middle" className="mm-tag">{snsTemp.tag}</text>
        )}
        {snsVib && (
          <text x="500" y="116" textAnchor="middle" className="mm-tag">{snsVib.tag}</text>
        )}
        {snsCor && (
          <text x="430" y="40" textAnchor="start" className="mm-tag">{snsCor.tag}</text>
        )}

        {/* ====================== CALLOUTS AO VIVO ====================== */}

        {/* Temperatura junto à carcaça. */}
        {tempVal != null && (
          <g>
            <line x1="270" y1="146" x2="150" y2="92" stroke="var(--stroke)" strokeWidth="1" />
            <rect x="40" y="70" width="116" height="40" rx="8" className="mm-callout-box" />
            <text x="52" y="86" className="mm-tag" textAnchor="start">Temperatura</text>
            <text x="52" y="103" className="mm-callout-val" fontSize="16"
              fill={tempVal >= 90 ? "var(--critico)" : tempVal >= 70 ? "var(--alerta)" : "var(--ok)"}>
              {tempVal}
              <tspan fontSize="11" dx="3" fill="var(--texto-fraco)">°C</tspan>
            </text>
          </g>
        )}

        {/* Vibração junto ao rolamento. */}
        {vibVal != null && (
          <g>
            <line x1="500" y1="180" x2="612" y2="116" stroke="var(--stroke)" strokeWidth="1" />
            <rect x="564" y="92" width="120" height="40" rx="8" className="mm-callout-box" />
            <text x="576" y="108" className="mm-tag" textAnchor="start">Vibração</text>
            <text x="576" y="125" className="mm-callout-val" fontSize="16"
              fill={vibVal >= 7.5 ? "var(--critico)" : vibVal >= 4.5 ? "var(--alerta)" : "var(--ok)"}>
              {vibVal}
              <tspan fontSize="11" dx="3" fill="var(--texto-fraco)">m/s²</tspan>
            </text>
          </g>
        )}
      </svg>

      {/* ====================== LEGENDA / REGIÕES ====================== */}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
        <span className="muted small" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span className="mm-pin" style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--cyan)", display: "inline-block" }} />
          Sensores
        </span>
        {[cmpRolamento, cmpEstator, cmpEixo].filter(Boolean).map((c) => {
          const active = isActive(c);
          const flag = suspect(c);
          return (
            <button
              key={c.tag}
              onClick={() => handleSelect(c)}
              className="pill"
              style={{
                cursor: "pointer",
                borderColor: active ? "var(--roxo-claro)" : undefined,
                boxShadow: active ? "0 0 0 1px var(--roxo-claro)" : undefined,
              }}
              title={`${c.tag} · ${c.name}`}
            >
              <span
                className={`led ${c.status} ${flag ? "pulse" : ""}`}
                style={{ display: "inline-block", marginRight: 6, verticalAlign: "middle" }}
              />
              {c.type}
            </button>
          );
        })}
      </div>
    </div>
  );
}
