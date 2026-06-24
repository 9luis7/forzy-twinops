// Provenance.jsx — "Confiança do dado". Cada seção lidera com um veredito em
// linguagem simples (de onde veio, se está íntegro, por onde passou, quem assinou).
// Os campos técnicos (hash, trace, tópico, versões) ficam num bloco secundário, discreto.

import {
  getAsset,
  getArea,
  getComponent,
  statusLabel,
  auditMeta,
  kpis,
} from "../data/mock.js";
import { useLiveTwin } from "../LiveTwinContext.jsx";

// Faixa válida por métrica (clamp físico do pipeline). Os limites superiores
// acomodam os picos dos cenários ao vivo (ex.: superaquecimento até ~96 °C) —
// são limites de PLAUSIBILIDADE FÍSICA (anti-adulteração), não de alerta.
const RANGES = {
  temperature: { label: "Temperatura", unit: "°C", type: "Temperatura", range: [35, 96] },
  vibration: { label: "Vibração", unit: "m/s²", type: "Vibração", range: [0.4, 9] },
  current: { label: "Corrente", unit: "A", type: "Corrente", range: [0, 60] },
  rotation: { label: "Rotação", unit: "RPM", type: "Controlador", range: [0, 4000] },
};
const ORDER = ["temperature", "vibration", "current", "rotation"];

const VALIDATION = {
  critico: { label: "Pendente — aguarda parecer do técnico", color: "var(--critico)", cls: "critico" },
  alerta: { label: "Em análise pela equipe de manutenção", color: "var(--alerta)", cls: "alerta" },
  normal: { label: "Confirmado automaticamente (dentro da faixa)", color: "var(--ok)", cls: "ok" },
  desconhecido: { label: "Sem validação", color: "var(--texto-fraco)", cls: "neutro" },
};

const inRange = (v, [lo, hi]) => v >= lo && v <= hi;

// ---------------------------------------------------------------- subcomponentes

// Faixa-veredito no topo de cada grupo: ícone + frase humana + selos.
function Verdict({ cls, icon, headline, sub, chips }) {
  return (
    <div className={`pv-verdict pv-${cls}`}>
      <span className="pv-icon" aria-hidden="true">{icon}</span>
      <div className="pv-vtext">
        <div className="pv-headline">{headline}</div>
        {sub ? <div className="pv-sub">{sub}</div> : null}
      </div>
      {chips && chips.length > 0 && (
        <div className="pv-chips">
          {chips.map((c, i) => (
            <span key={i} className={`pv-chip pv-chip-${c.tone || "neutro"}`}>{c.text}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function Group({ ico, title, hint, children }) {
  return (
    <div className="audit-group">
      <div className="ag-title">
        <span className="ag-ico">{ico}</span>
        {title}
        {hint ? <span className="ag-hint">{hint}</span> : null}
      </div>
      {children}
    </div>
  );
}

// Bloco recolhível de campos técnicos (mono, baixo contraste).
function TechDetails({ items }) {
  return (
    <details className="pv-tech">
      <summary>
        <span className="pv-tech-ico" aria-hidden="true">⚙</span>
        detalhes técnicos
      </summary>
      <div className="pv-tech-grid">
        {items.map((it, i) => (
          <div className="pv-tech-row" key={i}>
            <span className="pv-tech-k">{it.k}</span>
            <span className="pv-tech-v">{it.v}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

export default function Provenance({ tag }) {
  const twin = useLiveTwin();
  const asset = tag ? getAsset(tag) : null;
  const reading = tag ? twin.readingOf(tag) : null;

  if (!asset || !reading) {
    return (
      <section className="card">
        <h3>Confiança do dado</h3>
        <p className="muted small">Selecione um motor para ver a trilha de auditoria.</p>
      </section>
    );
  }

  const area = getArea(asset.area);
  const status = twin.statusOf(tag);
  const val = VALIDATION[status] ?? VALIDATION.desconhecido;
  const when = new Date(reading.ts).toLocaleString("pt-BR");
  const topic = `forzy/${(area?.name || "").toLowerCase()}/${asset.tag.toLowerCase()}`;
  const sensorFor = (type) => asset.sensors.find((s) => s.type === type)?.tag || "—";
  const meta = auditMeta(tag);
  // Validação humana coerente com o estado ATUAL (normal não exige parecer).
  const humanValidation =
    status === "normal" ? "Não requer validação (dentro da faixa)" : meta.humanValidation;
  const component = meta.componentTag ? getComponent(meta.componentTag) : null;
  const allInRange = ORDER.every((k) => inRange(reading[k], RANGES[k].range));
  const usedInRec = status !== "normal";

  // Selo global de confiança (cabeçalho da seção).
  const reliable = kpis.dataReliability;

  return (
    <section className="card" data-tour="audit-provenance">
      <style>{`
        .pv-head { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin:0 0 4px; }
        .pv-head h3 { margin:0; font-size:16px; }
        .pv-head .pv-when { color:var(--texto-fraco); font-size:12px; font-weight:400; }

        /* Faixa-veredito global */
        .pv-banner {
          display:flex; align-items:center; gap:12px; flex-wrap:wrap;
          margin:10px 0 4px; padding:12px 14px; border-radius:12px;
          background: linear-gradient(180deg, rgba(52,211,153,.10), rgba(52,211,153,.03));
          border:1px solid rgba(52,211,153,.35);
        }
        .pv-banner .pv-big {
          font-family: ui-monospace, Menlo, monospace; font-variant-numeric: tabular-nums;
          font-weight:700; font-size:26px; color:var(--ok); text-shadow:0 0 12px rgba(52,211,153,.35);
          line-height:1;
        }
        .pv-banner .pv-bmain { font-weight:700; color:var(--texto); font-size:14.5px; }
        .pv-banner .pv-bsub { color:var(--texto-fraco); font-size:12px; }

        /* Verdict strips por grupo */
        .pv-verdict {
          display:flex; align-items:center; gap:11px; flex-wrap:wrap;
          padding:9px 12px; border-radius:11px; margin:4px 0 8px;
          border:1px solid var(--stroke);
          background: linear-gradient(180deg, var(--panel-2), var(--panel));
        }
        .pv-verdict .pv-icon { font-size:18px; line-height:1; }
        .pv-vtext { flex:1 1 200px; }
        .pv-headline { font-weight:700; color:var(--texto); font-size:13.5px; line-height:1.3; }
        .pv-sub { color:var(--texto-fraco); font-size:12px; margin-top:1px; }
        .pv-ok   { border-color: rgba(52,211,153,.35); }
        .pv-ok   .pv-icon { color:var(--ok); }
        .pv-alerta { border-color: rgba(251,191,36,.35); }
        .pv-alerta .pv-icon { color:var(--alerta); }
        .pv-critico { border-color: rgba(251,106,106,.4); }
        .pv-critico .pv-icon { color:var(--critico); }
        .pv-neutro .pv-icon { color:var(--texto-fraco); }

        .pv-chips { display:flex; gap:6px; flex-wrap:wrap; }
        .pv-chip {
          font-size:11px; font-weight:600; padding:3px 9px; border-radius:999px;
          border:1px solid var(--stroke); color:var(--texto-fraco);
          white-space:nowrap;
        }
        .pv-chip-ok { color:var(--ok); border-color:rgba(52,211,153,.45); background:rgba(52,211,153,.08); }
        .pv-chip-alerta { color:var(--alerta); border-color:rgba(251,191,36,.45); background:rgba(251,191,36,.08); }
        .pv-chip-critico { color:var(--critico); border-color:rgba(251,106,106,.45); background:rgba(251,106,106,.08); }

        .ag-hint { font-weight:400; font-size:11.5px; color:var(--texto-fraco); margin-left:8px; }

        /* Tabela de faixas — SCADA */
        .pv-range { margin-top:6px; border:1px solid var(--stroke); border-radius:11px; overflow:hidden; }
        .pv-range table { width:100%; border-collapse:collapse; font-size:13px; }
        .pv-range thead th {
          text-align:left; font-weight:600; font-size:11px; letter-spacing:.04em; text-transform:uppercase;
          color:var(--texto-fraco); padding:8px 12px; background:rgba(124,58,237,.07);
          border-bottom:1px solid var(--stroke);
        }
        .pv-range tbody td {
          padding:9px 12px; border-bottom:1px solid var(--stroke);
          font-variant-numeric: tabular-nums;
        }
        .pv-range tbody tr:last-child td { border-bottom:none; }
        .pv-range .pv-metric { font-weight:600; color:var(--texto); }
        .pv-range .pv-tag { font-family:ui-monospace,Menlo,monospace; font-size:11.5px; color:var(--texto-fraco); }
        .pv-range .pv-val { font-family:ui-monospace,Menlo,monospace; font-weight:700; color:var(--texto); }
        .pv-range .pv-faixa { color:var(--texto-fraco); }
        .pv-range .pv-ok  { color:var(--ok); font-weight:700; }
        .pv-range .pv-bad { color:var(--critico); font-weight:700; }

        /* Detalhes técnicos — secundário, mono, baixo contraste */
        .pv-tech { margin-top:10px; }
        .pv-tech > summary {
          list-style:none; cursor:pointer; display:inline-flex; align-items:center; gap:6px;
          font-size:11.5px; color:var(--texto-fraco); font-family:ui-monospace,Menlo,monospace;
          padding:4px 10px; border:1px solid var(--stroke); border-radius:8px;
          background:rgba(10,8,19,.4); user-select:none;
        }
        .pv-tech > summary:hover { color:var(--texto); border-color:var(--roxo-claro); }
        .pv-tech > summary::-webkit-details-marker { display:none; }
        .pv-tech .pv-tech-ico { color:var(--roxo-claro); }
        .pv-tech-grid {
          margin-top:8px; padding:10px 12px; border:1px dashed var(--stroke); border-radius:9px;
          background:rgba(10,8,19,.45);
          display:grid; grid-template-columns:1fr 1fr; gap:4px 22px;
        }
        .pv-tech-row { display:flex; gap:8px; font-size:11.5px; align-items:baseline; }
        .pv-tech-k { color:var(--texto-fraco); min-width:118px; flex-shrink:0; }
        .pv-tech-v {
          font-family:ui-monospace,Menlo,monospace; color:var(--roxo-claro);
          opacity:.92; word-break:break-all; font-variant-numeric:tabular-nums;
        }
        @media (max-width:680px){ .pv-tech-grid{ grid-template-columns:1fr; } }
      `}</style>

      <div className="pv-head">
        <h3>Confiança do dado</h3>
        <span className="pv-when">· leitura de {when}</span>
      </div>

      {/* ----------------------------------------- VEREDITO GLOBAL (lidera o eixo) */}
      <div className="pv-banner">
        <span className="pv-big">{reliable}%</span>
        <div>
          <div className="pv-bmain">✓ Dado confiável</div>
          <div className="pv-bsub">validado na fonte · {allInRange ? "dentro da faixa" : "com desvio sinalizado"} · trilha completa</div>
        </div>
      </div>
      <p className="muted small" style={{ margin: "4px 0 6px" }}>
        Toda leitura tem origem rastreável e prova de que não foi alterada. Abaixo, o que isso
        significa em cada etapa — os campos técnicos ficam guardados em “detalhes técnicos”.
      </p>

      {/* -------------------------------------------------------- PROCEDÊNCIA */}
      <Group ico="📍" title="De onde veio" hint="origem da leitura">
        <Verdict
          cls="ok"
          icon="📍"
          headline={`Medido no motor ${asset.tag} — ${asset.name}`}
          sub={
            <>
              Setor {area?.name}
              {component ? <> · componente sob suspeita: {component.name}</> : null}
              {" · "}sensores: {meta.sourceSensorTags.join(" + ") || "—"}
            </>
          }
          chips={[{ text: `Setor ${area?.tag || "—"}`, tone: "neutro" }]}
        />
        <TechDetails
          items={[
            { k: "Planta / área", v: `${area?.name} (${area?.tag})` },
            { k: "Ativo monitorado", v: asset.tag },
            { k: "Equipamento pai", v: meta.parentAssetTag },
            { k: "Componente", v: component ? `${component.tag} · ${component.name}` : "—" },
            { k: "Sensores de origem", v: meta.sourceSensorTags.join(" + ") || "—" },
            { k: "Tópico MQTT", v: topic },
          ]}
        />
      </Group>

      {/* -------------------------------------------------------- INTEGRIDADE */}
      <Group ico="🔒" title="Está íntegro?" hint="o dado não foi adulterado">
        <Verdict
          cls={allInRange ? "ok" : "critico"}
          icon={allInRange ? "🔒" : "⚠️"}
          headline={
            allInRange
              ? "Nenhum sinal de adulteração — todas as leituras dentro da faixa física"
              : "Atenção — há leitura fora da faixa física esperada"
          }
          sub="Cada número tem uma assinatura digital. Conferimos também se o valor é fisicamente possível."
          chips={[
            { text: `Confiabilidade ${kpis.dataReliability}%`, tone: "ok" },
            { text: "Fonte validada", tone: "ok" },
            { text: allInRange ? "Todas na faixa ✓" : "Há desvio ✗", tone: allInRange ? "ok" : "critico" },
          ]}
        />

        <div className="pv-range">
          <table>
            <thead>
              <tr>
                <th>Métrica</th>
                <th>Sensor</th>
                <th>Valor</th>
                <th>Faixa válida</th>
                <th style={{ textAlign: "center" }}>OK</th>
              </tr>
            </thead>
            <tbody>
              {ORDER.map((key) => {
                const m = RANGES[key];
                const v = reading[key];
                const ok = inRange(v, m.range);
                return (
                  <tr key={key}>
                    <td className="pv-metric">{m.label}</td>
                    <td className="pv-tag">{sensorFor(m.type)}</td>
                    <td className="pv-val">{v} {m.unit}</td>
                    <td className="pv-faixa">{m.range[0]}–{m.range[1]} {m.unit}</td>
                    <td style={{ textAlign: "center" }} className={ok ? "pv-ok" : "pv-bad"}>
                      {ok ? "✓" : "✗"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <TechDetails
          items={[
            { k: "Input hash", v: meta.inputHash },
            { k: "Confiabilidade", v: `${kpis.dataReliability}%` },
            { k: "Fonte validada", v: "Sim" },
            { k: "Faixa física", v: allInRange ? "todas ok" : "há desvio" },
          ]}
        />
      </Group>

      {/* ----------------------------------------------------- RASTREABILIDADE */}
      <Group ico="🧭" title="Por onde passou" hint="caminho do dado até a decisão">
        <Verdict
          cls={usedInRec ? "alerta" : "ok"}
          icon="🧭"
          headline={
            usedInRec
              ? "Esta leitura entrou na recomendação atual do motor"
              : "Leitura registrada — dentro do normal, não gerou ação"
          }
          sub={`Avaliada e classificada como “${statusLabel(status)}”.`}
          chips={[{ text: usedInRec ? "Usada na decisão" : "Apenas histórico", tone: usedInRec ? "alerta" : "ok" }]}
        />
        <ol style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 13, color: "var(--texto-fraco)", lineHeight: 1.7 }}>
          <li>Lida no <strong style={{ color: "var(--texto)" }}>{asset.tag}</strong> ({area?.name}) pelo sensor</li>
          <li>Enviada com segurança para a nuvem</li>
          <li>Conferida e guardada no histórico</li>
          <li>Avaliada → estado <strong style={{ color: val.color }}>{statusLabel(status)}</strong></li>
        </ol>
        <TechDetails
          items={[
            { k: "Trace ID", v: meta.traceId },
            { k: "Pipeline", v: meta.pipelineVersion },
            { k: "Modelo de scoring", v: meta.scoringModel },
            { k: "Captura → broker", v: "ESP32 → HiveMQ (MQTT)" },
            { k: "Ingestão → banco", v: "n8n → Supabase (readings)" },
            { k: "Usado na recomendação", v: usedInRec ? "Sim" : "Não" },
          ]}
        />
      </Group>

      {/* ----------------------------------------------------- TRILHA DE AUDITORIA */}
      <Group ico="✍️" title="Quem responde por ele" hint="assinatura e validação">
        <Verdict
          cls={val.cls}
          icon="✍️"
          headline={`Estado avaliado: ${statusLabel(status)}`}
          sub={val.label}
          chips={[
            { text: meta.signedBy, tone: "neutro" },
            { text: status === "normal" ? "Validação automática" : "Validação humana pendente", tone: val.cls },
          ]}
        />
        <TechDetails
          items={[
            { k: "Coletado em", v: when },
            { k: "Assinado por", v: meta.signedBy },
            { k: "Estado avaliado", v: statusLabel(status) },
            { k: "Validação humana", v: humanValidation },
          ]}
        />
      </Group>
    </section>
  );
}
