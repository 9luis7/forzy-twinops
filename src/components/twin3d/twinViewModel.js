const reading = (measurement, unit, statistic) => ({
  value: measurement?.value ?? null,
  unit,
  ...(statistic ? { statistic: measurement?.statistic ?? statistic } : {}),
});

const nodesForComponent = (manifest, componentTag) =>
  componentTag
    ? Object.values(manifest.groups)
        .filter((group) => group.componentTag === componentTag)
        .flatMap((group) => group.nodeNames)
    : [];

function channelView(channel) {
  const measurements = channel.measurements ?? {};
  return {
    sensorId: channel.sensorId,
    temperature: reading(measurements.temperature, "degC"),
    vibrationVelocityRms: reading(measurements.vibrationVelocityRms, "mm/s"),
    vibrationAcceleration: reading(
      measurements.vibrationAcceleration,
      measurements.vibrationAcceleration?.unit ?? "g",
      "unknown",
    ),
    placementLabel: "Posição não validada",
  };
}

export function buildTwinViewModel({ snapshot, manifest, activeComponent = null }) {
  const assessmentTag = snapshot.assessment?.componentTag ?? null;
  const highlightedNodeNames = nodesForComponent(manifest, assessmentTag);

  return {
    status: snapshot.status,
    freshness: snapshot.freshness,
    highlightedNodeNames,
    activeNodeNames: nodesForComponent(manifest, activeComponent),
    channels: snapshot.channels.map(channelView),
    warning:
      assessmentTag && highlightedNodeNames.length === 0
        ? `Sem associação 3D aprovada para ${assessmentTag}`
        : null,
  };
}
