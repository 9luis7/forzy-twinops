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

## Convivência de versões

Os contratos `contracts/v1/` permanecem preservados durante a migração. Novos
produtores e consumidores que aderirem a v2 devem usar exclusivamente os
schemas deste diretório; adaptadores de fronteira são responsáveis por
converter dados v1 quando a convivência for necessária.
