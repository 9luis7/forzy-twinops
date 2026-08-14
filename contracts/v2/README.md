# Contrato canônico TwinOps v2

Este diretório define o contrato canônico v2 para o ativo monitorado. Os JSON
Schemas são a autoridade para estrutura, obrigatoriedade, tipos, valores
permitidos e proibição de propriedades adicionais. Consumidores e produtores
devem validar contra os `$id` `forzy://contracts/v2/...`; este documento não
substitui os schemas.

## Migração de v1 para v2

| Campo ou conceito v1 | Regra v2 |
| --- | --- |
| `assetTag` | `asset.assetId` no snapshot e `assetId` nos demais contratos; para o ativo atual, `forzy-motor-01`. |
| `observedAt: null` | `observedAt = receivedAt` para leitura live canônica. |
| `timestampQuality: "collector"` | `timestampQuality: "assumed_from_retrieval"`. |
| `freshness` | `operationalState` + `freshnessBasis`. |
| `mode` | removido. |
| `raw` | somente contrato canônico; não transportar payload original do fornecedor. |

`assessment` é uma chave obrigatória no `digital-twin-snapshot`, mas aceita
`null`. Sua ausência não é equivalente a `null` e é inválida. Quando existir,
o objeto deve satisfazer `asset-condition-assessment`.

## Semântica temporal assumida

Para a origem Forzy live, a fonte não fornece o instante real da medição.
Assim, `receivedAt` representa o instante de recuperação/recebimento e
`observedAt` recebe o mesmo valor apenas como aproximação explicitamente
marcada por `assumed_from_retrieval`. Não interpretar esse valor como horário
real da observação. A proveniência declara `sourceTimestampProvided: false`.

Todos os timestamps v2 usam a forma canônica RFC 3339 UTC terminada em `Z`.
O calendário Gregoriano é validado inclusive para o ano `0000`; o segundo
intercalar `60` somente é aceito em `23:59:60Z`.

No `sensor-telemetry-frame`, `timestampQuality: "assumed_from_retrieval"`
exige `observedAt` e `receivedAt` como timestamps, enquanto
`timestampQuality: "unavailable"` exige ambos como `null`. O JSON Schema
draft-07 expressa essa nulabilidade condicional, mas não consegue expressar a
igualdade entre dois campos. Essa limitação vale tanto para a leitura canônica
quanto para o frame. Por isso, Pydantic (em ambos os contratos) e o validator
runtime JS (no frame público) também exigem igualdade textual entre
`observedAt` e `receivedAt` no estado `assumed_from_retrieval`.

## Serialização pública

Campos opcionais de `assessment.evidence` preservam a diferença semântica
entre ausência e `null`. Produtores Python devem usar `to_public_dict()`, que
aplica aliases JSON e `exclude_unset=True`: um campo omitido na entrada segue
omitido, enquanto um campo informado explicitamente como `null` continua
presente. O comportamento global de `model_dump()` não foi alterado.

## Convivência de versões

Os contratos `contracts/v1/` permanecem preservados durante a migração. Novos
produtores e consumidores que aderirem a v2 devem usar exclusivamente os
schemas deste diretório; adaptadores de fronteira são responsáveis por
converter dados v1 quando a convivência for necessária.
