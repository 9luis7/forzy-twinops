import React from "react";
import { formatDateTime } from "../../lib/displayTime.js";

const statuses = { normal: "Sem desvio relevante", watch: "Atenção", alert: "Alerta relativo", insufficient_data: "Dados insuficientes" };

export default function OperationalSummary({ snapshot }) {
  const status = snapshot.assessment?.assessment.status;
  const byTime = (a, b) => Date.parse(a) - Date.parse(b);
  const observed = snapshot.channels.map((channel) => channel.observedAt).filter(Boolean).sort(byTime).at(-1);
  const received = snapshot.channels.map((channel) => channel.receivedAt).filter(Boolean).sort(byTime).at(-1);
  const timestamp = observed ?? received;
  return (
    <section className="product-overview-summary" aria-label="Resumo do equipamento">
      <dl>
        <div><dt>Condição avaliada</dt><dd data-condition={status}>{statuses[status] ?? "Sem avaliação disponível"}</dd></div>
        <div><dt>{observed ? "Última medição informada" : "Último recebimento"}</dt><dd>{timestamp ? `${formatDateTime(timestamp, "Horário indisponível")} · São Paulo` : "Horário indisponível"}</dd></div>
      </dl>
      <a href="/history">Consultar histórico →</a>
    </section>
  );
}
