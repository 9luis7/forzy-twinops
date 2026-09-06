import React from "react";

const statusLabels = {
  normal: "Sem desvio relevante",
  watch: "Atenção",
  alert: "Alerta relativo",
  insufficient_data: "Dados insuficientes",
};

export function markerReceipt(data) {
  const frame = data.latest;
  const arriving = Boolean(frame?.receivedAt && !frame.preloaded);
  return { arriving, key: arriving ? `${frame.frameId}:${frame.receivedAt}` : "preloaded-or-empty" };
}

export default function DemoSensorMarker({ sensor, data, onSelect }) {
  const receipt = markerReceipt(data);
  const value = data.latest?.measurements.vibrationVelocityRms?.value;
  return <span className={`demo-marker-anchor ${sensor.sensorId}`}>
    <span className="demo-marker-point" aria-hidden="true" />
    <svg className="demo-marker-leader" width="140" height="100" viewBox="0 0 140 100" aria-hidden="true"><path d={sensor.sensorId === "s1" ? "M70 50 L28 10 L0 10" : "M70 50 L110 82 L140 82"} fill="none" stroke="currentColor" strokeWidth="1" /></svg>
    <button key={receipt.key} className="demo-marker" data-arrival={String(receipt.arriving)}
    data-new={String(data.newInformation)} data-status={data.assessment?.assessment.status ?? "unknown"}
    onClick={() => onSelect(sensor.sensorId)} aria-label={`Sensor ${sensor.sensorId.toUpperCase()} · ${sensor.label}`}>
    <strong>{sensor.sensorId.toUpperCase()} · {value == null ? "—" : value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} mm/s</strong>
    <span>Posição assumida · {statusLabels[data.assessment?.assessment.status] ?? "Sem avaliação"}</span>
  </button></span>;
}
