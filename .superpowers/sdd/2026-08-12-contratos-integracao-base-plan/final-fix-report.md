# Gate 0 final fix report

## Status

DONE. Os oito findings do final reviewer foram corrigidos sem implementar
coleta, ML ou copiloto além da projeção contratual pública.

## Findings -> changes

1. `CanonicalSensorReading`: adicionados `scheduledAt`, `observedAt` nullable,
   hash `sha256:<64hex>` e provenance fechado `sourceSystem`/`ingestedAt`.
   Semântica live validada (`observedAt=null`, slot obrigatório,
   `sourceSystem=forzy-api`, `ingestedAt=receivedAt`) e fixture CSV adicionada
   (`scheduledAt=null`, timestamp original preservado).
2. Projeção pública `to_sensor_telemetry_frame` adicionada em
   `twinops.contracts.projections`, exportada e testada contra vazamento de
   raw/hash/provenance. Plano de aquisição usa a projeção em snapshot/history.
3. `AssessmentEvidence` fechado e tipado alinhado entre JSON Schema, Pydantic,
   validator JS, fixture e planos de ML/copiloto.
4. `SensorTelemetryFrame` aceita aceleração em `g` ou `m/s²`; o canônico real
   permanece em `g`; replay preserva explicitamente `2.1 m/s²`.
5. Pydantic usa `allow_inf_nan=False`; testes cobrem NaN e infinitos em
   measurements, frames, assessment scores/janelas e evidências.
6. Gateway restringe `baseUrl` a vazio ou path `/...`, rejeitando URL absoluta,
   protocol-relative, backslash e path relativo.
7. Pacote 00, pacote 01 e planos base/aquisição/frontend/ML/copiloto foram
   atualizados para os contratos finais, incluindo o exemplo live exato.
8. Schemas, fixtures, Pydantic e validator JS permanecem fechados e coerentes.

## RED -> GREEN e validação

- RED Python: collection falhou com `ModuleNotFoundError` para
  `twinops.contracts.projections` antes da implementação.
- RED JS completo: JSON Schema estrito detectou `type: object` ausente no ramo
  condicional de provenance; corrigido e reexecutado.
- `npm.cmd run test:run`: 6 arquivos, 50 testes, PASS.
- `services/twinops/.venv/Scripts/python.exe -m pytest services/twinops/tests -v`:
  14 testes, PASS.
- `npm.cmd run build`: PASS; warning conhecido de chunk > 500 kB.
- `rg` ativo: nenhum `importedAt`; nenhum mapeamento replay `unit: "g"`;
  nenhum placeholder em contratos/data sources; hashes literais das fixtures
  permanecem no padrão `sha256:<64hex>`.
- `git diff --check`: PASS (somente avisos de normalização LF/CRLF do Windows).

## Arquivos

- Schemas/fixtures: `contracts/v1/**`.
- Pydantic/projeção/testes: `services/twinops/src/twinops/contracts/**` e
  `services/twinops/tests/contracts/test_models.py`.
- Runtime JS/adapters/testes: `src/contracts/**`,
  `src/dataSources/GatewayTwinDataSource*`, `src/dataSources/ReplayTwinDataSource*`.
- Planos/specs alinhados sob `docs/superpowers/{plans,specs}/**`.

## Commits

- `e2bf8b8 fix: close Gate 0 contract findings`
- O relatório é registrado em commit documental separado por viver sob a pasta
  de evidências `.superpowers`, ignorada por padrão.

## Concerns

- O build mantém apenas o warning preexistente de chunk principal > 500 kB.
- Os condicionais do JSON Schema garantem a semântica por origem; a igualdade
  `provenance.ingestedAt == receivedAt` é reforçada no modelo Pydantic, pois
  draft-07 não oferece comparação entre valores de propriedades.

## Residual same-origin hardening

- Re-review identificou que controles ASCII em `baseUrl`, por exemplo
  `"/\n/evil.example"`, podiam ser normalizados de forma perigosa.
- O guard agora rejeita `[\x00-\x1f\x7f]` antes das verificações existentes de
  backslash, URL absoluta, path relativo e prefixo protocol-relative.
- RED focado: 5 falhas para newline, carriage return, tab, NUL e DEL.
- GREEN focado: `GatewayTwinDataSource.test.js`, 17/17 PASS.
- Suíte JS completa: 6 arquivos, 56/56 PASS.
- Build de produção: PASS; permanece somente o warning conhecido de chunk
  principal > 500 kB.
- O commit residual separado contém exclusivamente o guard, seus testes e esta
  atualização de evidência.
