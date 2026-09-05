# Forzy TwinOps: replay real, 3D e copiloto

Status: execução autorizada pelo goal. Base: d29ea706969bd39ab92ca9d03acee05f35a66ca6. Branch: luis/twin-3d-replay-demo.

Atualização aprovada em 05/09: seguir a [meta de entrega hospedada com custo zero](2026-09-05-hosted-zero-cost-goal.md). Supabase Free dedicado à demonstração, Neon/live preservados, inicialização e corpus demo independentes, entrega e congelamento até 08/09 para o pitch de 10/09. Essa decisão substitui abaixo a exigência de usar o mesmo PostgreSQL/corpus físico; contratos e critérios de aceite permanecem.

## Objetivo e aceite

Publicar `/demo` no projeto Vercel existente com histórico real chegando pelo backend, avaliações causais por sensor, 3D e gráficos na mesma revisão, e resposta real do RAG a um evento real com citações. O fluxo live permanece compatível. O usuário autorizou implementação, dependências, subagentes independentes, migrations aditivas, importação, Git/PR e publicação. Coleta semanal, ordens de serviço e simulação mecânica não fazem parte deste objetivo.

## Global Constraints

- Fonte: 7.183 pares e 14.366 leituras, arquivo OOXML com extensão .csv; preservar valores, ordem, timestamps, repetições e lacunas. Nunca incluir arquivo original, PDI, credenciais ou caminhos privados nas respostas HTTP, logs, Git ou bundle.
- S1 = canal 1 / motor junto ao acoplamento; S2 = canal 2 / bomba junto ao acoplamento. Posições assumidas para demonstração, não validadas fisicamente.
- PostgreSQL Supabase Free dedicado à demonstração; tabelas `demo_*` e estruturas RAG aditivas apenas nesse destino. Preservar Neon/live e permitir sua indisponibilidade sem abortar a demo. SQLite permitido somente como implementação local/testes. Sessões com token opaco, validade de 24 h, isolamento, comandos idempotentes e concorrência atômica.
- Roteiro guiado: linhas de dados 141..440 (sem as três linhas de cabeçalho), 300 pares. Modo livre: todo o conjunto. Ritmos 1, 2 e 5 pares por segundo; processar cada par mesmo em lote.
- `observedAt` original e `receivedAt` atual separados. Cálculos, persistência de condição e gap usam relógio original; atividade de transporte usa chegada atual. Sem dados futuros. Lacunas >15 s aparecem nos gráficos e invalidam continuidade; não precisam esperar o tempo real no replay.
- Repetições continuam no histórico/progresso. Avaliar prefixo bruto, incluindo repetições, quando a tupla de medidas muda; reaproveitar última avaliação no máximo 30 s de relógio original, invalidando na lacuna. Não remover duplicados antes de calcular cadência.
- Warmup guiado: prefixo de até 60 s antes da primeira linha e predecessor necessário para detectar gap. Mostrar quantidade precarregada. Modo livre começa sem histórico.
- ML existente com artefatos e hashes fixados. Aceleração é exibida, não usada no score. Score relativo ao baseline, não probabilidade de falha ou validação de antecipação fora da amostra.
- Uma revisão atômica alimenta modelo 3D, gráficos, avaliações e contexto manual. Eventos guardam contexto imutável; resposta atrasada nunca assume ser avaliação atual.
- RAG automático: watch sustentado >=5 s originais e >=3 observações novas; escalada a alert respeita persistência do scorer (30 s); recuperação normal >=10 s originais e >=3 observações novas. Dados insuficientes não significam recuperação. Deduplicar por episódio, não por recibo.
- RAG tem requisição independente de telemetria, um processamento automático por sessão, lease e recuperação após interrupção. Orçamento demo total 40 s / geração até 30 s; preservar orçamento live. Mesmo provedor Gemini, com plano gratuito confirmado, e conteúdo WEG existente, reindexado no destino demo com nova identidade verificável; não afirmar cobertura documental de bomba.
- Estados terminais de recomendação imutáveis; falhas transitórias recuperáveis antes da finalização, sem respostas duplicadas. Geração real com citação válida é necessária ao aceite; fallback isolado não basta.

## Contrato compartilhado demo v1

Este contrato é novo; não alterar invariantes dos contratos v1/v2 existentes. Todos os IDs de sensores são `s1` e `s2`. Timestamps são UTC ISO 8601. Quantidades são JSON numéricas finitas. Respostas não incluem raw/PDI. Campos opcionais abaixo devem ser presentes com null quando indisponíveis.

### HTTP

- GET `/api/demo/v1/datasets` -> `{datasets:[{datasetId,label,pairCount,readingCount,startAt,endAt,sourceHash,sourceFormat,guided:{startRow:141,endRow:440}}]}`.
- POST `/api/demo/v1/runs` body `{datasetId,scenario:"guided"|"full",speed:1|2|5}` -> `{runId,token,context}`. Token somente nesta resposta; guardar no sessionStorage do navegador.
- GET `/api/demo/v1/runs/{id}/context` -> contexto. Rotas de sessão requerem `Authorization: Bearer <token>`.
- POST `/api/demo/v1/runs/{id}/control` body `{commandId,expectedRevision,action:"play"|"pause"|"resume"|"step"|"restart"|"speed",speed?:1|2|5}` -> contexto.
- POST `/api/demo/v1/runs/{id}/advance` body `{commandId,expectedRevision}` -> contexto. Avança o ritmo atual só quando running. Início cria paused; play começa; passo só paused. Restart aumenta geração e volta ao cursor inicial. Alteração de velocidade não altera cursor.
- Conflito de revisão -> HTTP 409 `{detail:"revision_conflict"}`; UI recarrega contexto e não repete ação automaticamente. As oito respostas mais recentes são retidas integralmente: repetir o mesmo commandId e conteúdo retorna aquela resposta, sem avançar. Identidades e fingerprints de todos os comandos permanecem durante a sessão; retry mais antigo retorna 409 `command_response_expired`, nunca reexecuta, e exige recarregar contexto. Token errado retorna 404 sem vazamento. Sessão expirada ainda retida -> 410 `run_expired`; depois da limpeza limitada -> 404 `run_not_found`. Ambos exigem nova sessão. Dataset indisponível -> 503. Todas as respostas têm Cache-Control no-store.
- POST `/api/demo/v1/runs/{id}/assistant/query` body `{question,conversationId?,history?,contextRevision}` -> `{contextRevision,sourceRow,observedAt,response:<AssistantQueryResponse existente>}`. Revisão ausente/antiga: 409, nunca carregar live como substituto.
- POST `/api/demo/v1/runs/{id}/events/{eventId}/recommendation` body `{}` -> evento público atualizado. Executa a geração fora da transação de avanço. Evento de outra geração/run rejeitado. Resposta pronta não recalcula.

### Contexto público

```
{
  schemaVersion:"demo-1.0", assetId:"forzy-motor-01", mode:"replay",
  revision:0, generatedAt:"...", status:"normal|watch|alert|insufficient_data|unknown",
  replay:{runId,generation:0,state:"paused|running|completed",scenario:"guided|full",
    speed:1,cursor:0,totalPairs:300,startRow:141,endRow:440,sourceRow:null,
    sourceTime:null,arrivalTime:null,expiresAt:"...",warmupPairs:0},
  dataset:{datasetId,label,pairCount,readingCount,startAt,endAt,sourceHash,sourceFormat},
  sensors:{s1:{latest:null,assessment:null,assessmentState:"unavailable|computed|reused",newInformation:false},
           s2:{latest:null,assessment:null,assessmentState:"unavailable|computed|reused",newInformation:false}},
  history:[], events:[],
  pipeline:{receivedPairs:0,receivedReadings:0,newInformationReadings:0,repeatedReadings:0,
    gapCount:0,assessmentsComputed:0,eventsCreated:0,lastAdvanceMs:null},
  capabilities:{copilot:true,twin3d:true,replayControls:true}
}
```

`latest` e cada item de `history`:
`{frameId,sensorId,sourceRow,observedAt,receivedAt,measurements:<shape existente FrameMeasurements>,qualityFlags:[],gapBefore:false,preloaded:false}`.
History é intercalado por sourceRow e sensorId, limitado aos últimos 300 pares (warmup identificado). `assessment` = AssetConditionAssessment v1 serializada por aliases, ou null. Nunca transformar posição física assumida em evidência de diagnóstico. Status global preserva o maior watch/alert válido e exibe insuficiência separada por sensor.

Evento público:
`{eventId,generation,kind:"sustained_watch|escalation|recovery",sourceRow,observedAt,receivedAt,contextRevision,sensorIds:[],status:"pending|processing|ready|degraded",attempts:0,retryable:false,recommendation:null,errorCode:null}`.
`recommendation` = AssistantQueryResponse existente quando disponível. Contexto congelado fica apenas no armazenamento privado, acessível por serviço confiável. Eventos e métricas vêm do backend, nunca contadores simulados no frontend.

### Interfaces Python entre replay e RAG

- `demo.repository.DemoRepository`: persistência transacional local/PostgreSQL, métodos finais documentados pelo implementador backend antes de integrar RAG.
- `demo.service.DemoService(repository, scorer, clock)` com `datasets()`, `create_run(dataset_id, scenario, speed)`, `context(run_id, token)`, `control(run_id, token, body)`, `advance(run_id, token, body)`; retornam dicionários públicos do contrato.
- `demo.routes.create_demo_router()` lê `app.state.demo_service`; o parent monta router/config/lifespan. Backend não altera main_v2/config_v2.
- `rag.demo_service` e `rag.demo_routes`: projeção de contexto confiável, execução e rotas RAG demo; parent monta com service/repository. Os agentes backend e RAG devem comunicar o contrato do repositório por mensagem antes de implementar dependências, mantendo HTTP acima estável.
- Contexto live novo `/api/v2/assets/{assetId}/twin-context`: parent implementa projeção atômica das duas avaliações sem mudar snapshot/refresh existentes.

## Task 1: Backend e fonte histórica

Responsável por `services/twinops/src/twinops/demo/**`, `services/twinops/migrations/004_demo_replay_v1.sql`, novos testes `services/twinops/tests/demo/**`, e `scripts/import_demo_history.py`. Implementar leitura por assinatura textual CSV/ZIP-OOXML sem instalar pacote pesado, hash, normalização, importação idempotente, store SQLite/Postgres, sessão/control/advance/snapshot e máquina de episódios. Preservar repetições/ties com índice original e modelo fixado. Processar lote atomicamente com rollback em falha; não armazenar resposta gigante por tick sem retenção limitada; não manter lock durante geração RAG. Datasets contêm medidas normalizadas, sem raw. Oferecer bridge e armazenamento evento/lease para Task 3. Testar formatos, isolamento, concorrência, idempotência, autorização, expirado, gaps, repetidos, velocidades e prefixo causal. Relatório contém API final, comandos e resultados.

## Task 2: Interface, gráficos e 3D

Responsável por `src/demo/**`, `src/dataSources/GatewayDemoDataSource*`, `src/components/Twin3D*`, `src/components/twin3d/**`, `public/models/*.manifest.json`, testes JS correspondentes e CSS demo próprio. Expor `DemoDashboard` default em `src/demo/DemoDashboard.jsx` para parent ligar App. Data source e hook usam contrato acima. Um timer de 1 s com no máximo um advance pendente; batch não pula eventos. sessionStorage run/token por aba, stale-response generation guard e revisão monotônica. Visibilidade pausa, volta com ação continuar. Controles teclado, mensagem de rede recuperável, sincronização atômica, 3 gráficos com selector e gaps, procedência/clocks/pipeline reais. RAG automático independente (uma requisição pendente), manual contextRevision fixado, mensagens vinculadas ao evento. Materiais individuais motor/bomba/base/acoplamento, anchors assumidos em unidades/model coordinates com inspeção GLB, seleção/foco/isolate/reset, marcadores/valor/pulso/status, fallback sem WebGL. Props live existentes seguem funcionando. Testar retries, inflight reset, timer, revisão, UI teclado, fallback, cores/materiais e parser contrato. Não alterar App.jsx nem TwinOpsContext.jsx (parent).

## Task 3: Copiloto demo

Responsável por `services/twinops/src/twinops/rag/demo_*`, alterações necessárias em `rag/operational.py`, `rag/public_service.py`, `rag/generation.py` (preservar live defaults), e testes `services/twinops/tests/rag/test_demo_*`. Implementar construção confiável usando contexto demo/evento congelado, nunca live; orçamento 40/30 e processamento independente; lease atômica, retry, dedupe/corpus/model, uma geração por run, status terminais imutáveis. Identificar cobertura WEG motor e limitação bomba; manual continua e impede contexto futuro. Proteger request size sem requerer mudar middleware live. Testar evento tardio/restart, retrytimeout, stale revision, fontes/citações, RAG lento enquanto replay continua. Coordene persistência e interfaces com backend. Não alterar main_v2/config_v2.

## Task 4: Integração, revisão, publicação e aceite

Parent responsável por App.jsx, main_v2.py, config_v2.py, live twin-context, .env.example, vercel.json, scripts de verificação, documentação e integração entre trabalhos. Reutilizar PostgreSQL/Gemini e corpus existentes; provisionamento novo só se indispensável. Instalar CLI Vercel e conferir projeto/acesso sem expor segredos. Feature flag `DEMO_ENABLED` desliga demo para rollback. Verificar baseline e novos testes + build, testes Postgres reais isolados, execução real ponta a ponta no Preview, revisão independente do SHA e correções; então versão final no projeto existente e roteiro completo com resposta real citada. Registrar URL, deployment, commit e evidência sanitizada. Não chamar goal complete antes do aceite.

## Ordem e responsabilidades

Tarefas 1, 2 e 3 têm ownership disjunto e podem avançar independentemente após contrato. Task 4 integra à medida que interfaces ficam disponíveis; publicação depende de todas e revisão. Agentes não criam subagentes, não alteram arquivos de outros nem revertem alterações alheias. Parent faz commits para evitar disputa no índice compartilhado. Qualquer ajuste de interface é documentado e comunicado aos consumidores.

## Demonstração e rollback

Abrir /demo, selecionar roteiro guiado e iniciar a 1 par/s. Mostrar S1/S2, chegada separada da medição, gráficos, condição e comentário citado; pausar, avançar, retomar; alterar 2/5; reiniciar uma sessão sem afetar outra. Modo livre mostra lacunas naturais e warmup. Falha do RAG fica visível e não interrompe ingestão. Rollback: desabilitar DEMO_ENABLED e voltar ao deployment anterior; tabelas demo aditivas não alteram live.
