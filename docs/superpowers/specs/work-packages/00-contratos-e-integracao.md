# Pacote 00 — Contratos compartilhados e base de integração

## Missão

Congelar os tipos, JSON Schemas, fixtures e a fronteira entre backend, ML,
frontend e copiloto antes dos workers paralelos. Este pacote pertence ao
integrador; nenhum outro worker altera esses contratos sem aprovação.

## Entregáveis

- JSON Schema versionado de `CanonicalSensorReading`, `SensorTelemetryFrame`,
  `AssetConditionAssessment` e `DigitalTwinSnapshot`.
- Fixtures mínimas: live válido S1/S2, CSV válido, zero válido, stale, gap,
  duplicado, schema inválido, `insufficient_data`, alerta com evidências.
- Adapter do replay atual para `DigitalTwinSnapshot`.
- Documento de compatibilidade e política de versionamento.
- Testes de contrato executáveis no backend e no frontend.

## Contrato normativo

### `CanonicalSensorReading`

```json
{
  "schemaVersion": "1.0",
  "readingId": "uuid",
  "source": "forzy-live|forzy-csv",
  "assetTag": "MTR-BMB-042",
  "sensorId": "s1|s2",
  "observedAt": "ISO-8601 UTC",
  "receivedAt": "ISO-8601 UTC",
  "measurements": {
    "vibrationVelocityRms": {
      "value": 0.04,
      "unit": "mm/s",
      "semanticConfidence": "inferred_from_datasheet"
    },
    "vibrationAcceleration": {
      "value": 0.0,
      "unit": "g",
      "statistic": "unknown",
      "semanticConfidence": "unconfirmed"
    },
    "temperature": {
      "value": 34,
      "unit": "degC",
      "semanticConfidence": "inferred_from_datasheet"
    }
  },
  "qualityFlags": [],
  "payloadHash": "sha256",
  "raw": {},
  "provenance": { "sourceSystem": "forzy-live", "importedAt": "ISO-8601 UTC" }
}
```

Regras:

- `observedAt` permanece nulo no live enquanto a origem não fornecer timestamp;
  no CSV, recebe o timestamp original quando ele for válido.
- `receivedAt` nunca é descrito como horário real da medição.
- `scheduledAt` identifica o slot de polling; a chave idempotente é
  `(source, sensorId, scheduledAt)`.
- Para CSV, a idempotência usa o hash do arquivo, o número da linha e o sensor;
  `scheduledAt` permanece nulo.
- Zero é válido. Campo ausente, string, `null`, `NaN` ou infinito invalida a
  amostra daquele sensor.
- `raw` é imutável.
- Aceleração com `statistic=unknown` não entra no score oficial.
- Unidades inferidas devem permanecer marcadas até confirmação da Forzy.

### `SensorTelemetryFrame`

Consumer-safe projection for snapshot channels and history. It never exposes
`raw` or `provenance`; the explicitly named measurements may be `null` when
unavailable, as may timestamps, with `timestampQuality` explaining the value.

### `AssetConditionAssessment`

```json
{
  "schemaVersion": "1.0",
  "assessmentId": "uuid",
  "assetTag": "MTR-BMB-042",
  "sensorId": "s1",
  "window": {
    "start": "ISO-8601 UTC",
    "end": "ISO-8601 UTC",
    "receivedAt": "ISO-8601 UTC",
    "freshnessMs": 0
  },
  "quality": {
    "status": "ok|degraded|insufficient_data",
    "flags": []
  },
  "operatingContext": {
    "state": "steady|startup|shutdown|stopped|unknown",
    "estimated": true
  },
  "assessment": {
    "status": "normal|watch|alert|insufficient_data",
    "anomalyScore": 0,
    "deteriorationScore": 0,
    "scoreSemantics": "relative_to_historical_baseline_not_failure_probability",
    "episodeId": null,
    "persistenceSeconds": 0
  },
  "componentTag": null,
  "recommendation": null,
  "humanValidationRequired": true,
  "evidence": [],
  "model": {
    "name": "robust-baseline",
    "version": "1.0.0",
    "configHash": "sha256",
    "trainedUntil": "ISO-8601 UTC"
  },
  "limitations": []
}
```

### `DigitalTwinSnapshot`

```json
{
  "schemaVersion": "1.0",
  "assetTag": "MTR-BMB-042",
  "mode": "replay|live",
  "generatedAt": "ISO-8601 UTC",
  "status": "normal|watch|alert|unknown|insufficient_data",
  "freshness": "fresh|delayed|expected_idle|unavailable|unknown",
  "channels": [],
  "history": [],
  "assessment": null,
  "capabilities": {
    "replayControls": true,
    "liveUpdates": false,
    "copilot": false,
    "twin3d": true
  }
}
```

`channels` contém amostras separadas para S1 e S2. Não existe média implícita
entre sensores. `history` pode ser paginado ou limitado; não deve carregar todo
o banco no snapshot padrão.

`componentTag` e `recommendation` permanecem nulos quando os dados não sustentam
uma associação física ou operacional. O frontend e o copiloto não podem
preenchê-los por conta própria.

## API estável para consumidores

- `GET /api/v1/twin/assets/{assetTag}/snapshot`
- `GET /api/v1/twin/assets/{assetTag}/history?sensorId=&from=&to=&limit=`
- `GET /api/v1/system/health`
- `POST /api/v1/copilot/explain`

## Ownership

O integrador possui schemas, fixtures, arquivos de configuração compartilhados,
`LiveTwinContext.jsx`, adapters de data source e alterações em `package.json`.
Workers não editam esses arquivos.

## Critérios de aceite

- Todos os schemas rejeitam versões maiores desconhecidas.
- Backend e frontend validam as mesmas fixtures.
- Replay atual continua determinístico depois da adaptação.
- Nenhum componente recebe o objeto raw do endpoint.
- Nenhum contrato usa o campo ambíguo `vibration`.
- Alteração incompatível exige nova versão de schema e nota de migração.
