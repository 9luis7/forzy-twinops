const STATUS_MATERIAL = Object.freeze({
  normal: Object.freeze({ materialColor: "#4f86a8", emissiveColor: "#16384b", emissiveIntensity: 0.06 }),
  watch: Object.freeze({ materialColor: "#d9952f", emissiveColor: "#6b3f0d", emissiveIntensity: 0.16 }),
  alert: Object.freeze({ materialColor: "#d95757", emissiveColor: "#6f1717", emissiveIntensity: 0.28 }),
  unknown: Object.freeze({ materialColor: "#718096", emissiveColor: "#1f2937", emissiveIntensity: 0 }),
  insufficient_data: Object.freeze({ materialColor: "#718096", emissiveColor: "#1f2937", emissiveIntensity: 0 }),
});


export function buildTwinViewModel({ snapshot }) {
  const status = STATUS_MATERIAL[snapshot?.status] ? snapshot.status : "unknown";
  return {
    status,
    ...STATUS_MATERIAL[status],
  };
}
