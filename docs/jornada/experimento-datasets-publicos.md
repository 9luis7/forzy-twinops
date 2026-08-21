# Experimento com datasets públicos de falhas

## Evidência

Este laboratório é uma fronteira científica separada do modelo operacional:
não altera `artifacts/ml/real-forzy`, não calibra o ativo `forzy-motor-01` e
não alimenta a UI. As fixtures sintéticas continuam provando apenas o pipeline;
nenhum número delas é publicado como resultado científico.

Os sinais originais XJTU-SY e NASA IMS foram baixados, fixados por hash,
preparados em gerações imutáveis e auditados. A geração XJTU-SY
`xjtu-sy-v1-8c7e9d8b7c272002a4d44b021931aaf6500f013574db60839bae2af3aa0fee1a`
contém 9.217 arquivos: 9.216 CSVs e um PDF, totalizando 12.220.812.451 bytes.
O inventário bruto tem SHA-256
`42d68aa3fa65c28d0a15fd4bdb969ca7c9cc828827f4ab7a4dda62dfd42bd8db`;
a metadata e a attestation têm, respectivamente,
`4876cc6540a8c972c63b890d111d1a4d60322f5addd2a317b0b058246020e8f8`
e `49de3ae74df4de489a966a77ccf6af647a58e60ceb2515934b9c62bf299277a5`.
O manifesto independente de publicação tem 9.239 entradas e SHA-256
`cdb2fa353e88bf9a9329b9c7fab4feb1ee19945f7b0604b5a7ad872dea2e75d9`.

Cada CSV XJTU-SY tem o header ASCII ordenado
`Horizontal_vibration_signals,Vertical_vibration_signals`, seguido por 32.768
linhas numéricas em dois eixos. A amostragem é 25,6 kHz e há uma observação por
minuto. São 15 rolamentos em três condições, com 616, 1.566 e 7.034 janelas por
condição. A preparação real terminou com exit 0 em 2.061,44 s; a auditoria
independente passou em 433,312 s. O fast path idempotente terminou com exit 0
em 1.065,401 s e foi observado externamente a 10 Hz por 7.205 amostras, sem
processo 7-Zip e sem novo staging; a auditoria posterior passou em 148,031 s.

A attestation imutável conserva o valor histórico
`semanticGates.headerNames: "unknown"`. A metadata ligada pelo SHA-256 acima e
a auditoria independente posterior confirmam o header exato nas 9.216 janelas
e supersedem somente esse campo de nome. A attestation não foi reescrita; a
reconciliação não confirma unidade, label por janela, semântica Forzy nem abre
qualquer métrica.

A geração NASA IMS
`nasa-ims-v1-71cbedb9ec12f18af68eb175ba536c27df9c5de9a96fb4ac36d010f40e70ac0c`
tem attestation SHA-256
`b0da8f95a9f877e8a04c7c247dd4cbdf9d3ffc4fd93ee43c3c9f01e026253eb6`.
O run 1 contém 2.156 arquivos e 2.477.767.237 bytes, com inventário
`347863ccf244fb88d6f89303183bfb5af3405fa93f88f0d2f596baf27bc9b42f`
e metadata
`21a12273c9575a57a8d816ddf3fd9f134867cfed5fd6af79a2b68138a401bfae`.
O run 2 contém 984 arquivos e 544.618.480 bytes, com inventário
`94bd9093c2301c16cbae27e2c1695207b91c3acfa6bf90187a2f88ae3070ebff`
e metadata
`3ff3ce76aee53f0aa57aa193ea6a609d7371100a5bef1db6cbaf4a1eef3b2958`.
O run 3 permanece em quarentena: a fonte documenta 4.448 arquivos, mas o
archive contém 6.324; ele não foi extraído nem incluído em métricas. O contrato
factual do NASA IMS confirma 20 kHz e 20.480 linhas por janela.

## Resultado

Status: `not_run_semantic_gate`.

Os dados foram preparados e auditados, mas não foram carregados em um
experimento: `dataActuallyUsed` permanece vazio e `metrics` permanece `null`.
Logo, não existem nesta entrega:

- deltas `full -> aggregate -> Forzy-compatible`;
- XJTU-SY → NASA IMS ou NASA IMS → XJTU-SY;
- comparação cross-bench com baseline majoritário;
- métricas diagnósticas, prognósticas, de transferência ou de RUL;
- evidência de que o modelo Forzy prevê falha.

O CLI de laboratório não foi executado em modo real. O resultado publicado é
o gate científico reproduzível, não uma alegação de desempenho.

## Limitação

Há dois bloqueios independentes. Primeiro, não existe política auditada comum
para labels por janela, unidade de aceleração e semântica da medição Forzy. Os
desfechos XJTU-SY são evidência terminal no escopo do rolamento; não rotulam
todas as janelas. Unidade de aceleração, instante físico de falha, estado,
onset, severidade, `lifeFraction` e RUL verdadeiro continuam desconhecidos. No
NASA IMS, os canais físicos e o timezone também permanecem opacos. Os endpoints
GET da Forzy expõem valores, mas ainda não documentam de forma auditada a
estatística de aceleração, o eixo ou a janela interna usados no payload.

Segundo, o loader atual do laboratório aceita um único ZIP/TAR íntegro por
fonte e exige um destino de extração vazio. Ele não consome a geração XJTU-SY
preparada a partir de RAR multipart nem a geração NASA com dois runs preparados
e um terceiro run em quarentena. Por isso o comando real legado não é uma rota
segura de retomada e não deve ser executado para contornar o gate.

Diferenças entre bancada, montagem, carga, rotação, sensor, banda e estatística
interna permanecem limitações mesmo após uma futura execução. A vista
Forzy-compatible nunca provará equivalência física apenas por compartilhar o
nome de uma feature.

## Próximo experimento

A retomada honesta exige primeiro um loader read-only revisado que consuma as
duas gerações preparadas e preserve seus hashes. Em seguida é preciso escolher
explicitamente uma das duas linhas científicas:

1. obter labels por janela, unidade e semântica Forzy autoritativos e auditados
   para executar a comparação supervisionada e cross-bench originalmente
   planejada; ou
2. aprovar e desenhar separadamente um estudo não supervisionado de drift ao
   longo do ciclo de vida, com hipóteses, métricas e limites próprios.

A segunda alternativa muda a pergunta científica e não pode ser tratada como
execução silenciosa deste plano. Até que loader e política sejam revisados, os
dois datasets permanecem `prepared_semantically_gated`, todas as métricas
continuam indisponíveis e nenhum artefato é promovido para produção.
