export function assistantScope(endRow = 4) {
  const observedAt = `2026-08-12T15:00:${String(endRow).padStart(2, "0")}Z`;
  return { assetId: "forzy-motor-01", mode: "historical", revision: String(endRow).repeat(64), dataset: { datasetId: "history-test" },
    selection: { from: null, to: null, endRow, limit: 300, observedAt, totalPairs: 20, returnedPairs: endRow, hasPrevious: false, previousEndRow: null, hasNext: true, nextEndRow: 20 },
    capabilities: { twin3d: true, copilot: true, replayControls: false } };
}

export function historicalAnswer(scope = assistantScope()) {
  return {
    schemaVersion: "historical-assistant-1.0", contextRevision: scope.revision, datasetId: scope.dataset.datasetId, selection: scope.selection,
    response: {
      answer: { manual: "O manual orienta verificar a lubrificação do motor.", currentState: `Registro histórico ${scope.selection.endRow}: atenção relativa no motor.` },
      groundingStatus: "grounded",
      citations: [{ type: "manual", chunkId: "chunk-1", documentId: "document-1", manufacturer: "WEG", equipmentModel: "W22", revision: "2026-01", sourceUrl: "https://manufacturer.example/manual.pdf", pageStart: 4, pageEnd: 5, section: "Manutenção", excerpt: "Verifique a lubrificação.", contentHash: "a".repeat(64) }],
      corpus: { corpusId: "corpus-1", manufacturer: "WEG", equipmentModel: "W22", embeddingModel: "embedding-test", embeddingDimensions: 768, minRelevanceScore: 0.25 },
      models: { embedding: "embedding-test", generation: "generation-test" }, fallbackUsed: false,
      limitations: ["Avaliação retrospectiva; não representa probabilidade de falha."], humanValidationRequired: true,
      conversationId: "00000000-0000-4000-8000-000000000001", traceId: "00000000-0000-4000-8000-000000000002", latencyMs: 10,
    },
    historicalEvidence: ["s1", "s2"].map((sensorId) => ({ sensorId, component: sensorId === "s1" ? "motor" : "bomba", positionAssumed: true, observedAt: scope.selection.observedAt, sourceRow: scope.selection.endRow,
      assessmentId: `assessment-${sensorId}`, status: "watch", qualityStatus: "ok", qualityFlags: [], windowStart: "2026-08-12T15:00:01Z", windowEnd: scope.selection.observedAt, trainedUntil: null,
      scoreSemantics: "relative_to_historical_baseline_not_failure_probability", evidence: [{ id: `${sensorId}:velocity_ewma`, feature: "velocity_ewma", value: 0.4, unit: "mm/s", windowSeconds: 3 }] })),
  };
}
