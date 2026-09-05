# Demonstração do TwinOps com replay real

## Entrega

A rota `/demo` conecta o histórico normalizado, avaliações causais por sensor, o conjunto CAD e orientações documentais do corpus WEG. O roteiro guiado reproduz 300 pares, linhas de dados 141 a 440, com aquecimento anterior identificado. O modo livre oferece os 7.183 pares completos.

S1 representa o canal 1 na carcaça do motor, junto ao acoplamento; S2 representa o canal 2 na bomba, também junto ao acoplamento. As posições são assumidas para demonstração e não participam dos cálculos. Não há simulação mecânica nem alegação de probabilidade de falha.

## Como apresentar

1. Abrir `/demo`, manter **Guiado · 300 pares** e escolher **Preparar replay**.
2. Mostrar as duas posições assumidas, os valores e a distinção entre relógio histórico e horário de chegada.
3. Usar **Continuar** a 1 par/s. O cenário dura aproximadamente cinco minutos, além da latência de rede e das pausas do apresentador.
4. Acompanhar 3D, avaliações S1/S2 e os três gráficos. Cada revisão é compartilhada por todas as visualizações. Repetições contam como chegadas, sem gerar desvios artificiais.
5. No primeiro episódio de atenção sustentada, abrir **Ver recomendação e fontes do evento** quando a resposta estiver pronta. O contexto da resposta continua sendo o do evento enquanto a telemetria avança.
6. Pausar, selecionar S1 ou S2, focar/isolar o componente, avançar um par e enviar uma pergunta sobre a revisão pausada.
7. Retomar; demonstrar os ritmos de 2 e 5 pares/s. Reiniciar restaura somente esta sessão. Uma segunda aba cria uma sessão independente.
8. No modo livre, explorar o histórico completo e as lacunas. Ocultar a aba suspende a reprodução; voltar exige **Continuar**.

## Fonte e integridade

- Dataset: `forzy-history-debbd57af9b90b8a`.
- Fonte SHA-256: `debbd57af9b90b8aa70f5794c48fa759afd0ec291d8b56c0c80ed63bfc670c5e`.
- Formato real: ZIP/OOXML, apesar da extensão CSV. Três linhas de cabeçalho e 7.183 linhas de dados, duas leituras por linha.
- O arquivo bruto e os campos PDI permanecem fora do repositório, bundle, respostas HTTP e logs.
- `observedAt` preserva o horário original; `receivedAt` registra a chegada da reprodução. Janelas, persistência e lacunas usam somente o relógio original e o prefixo já recebido.
- O modelo fixado foi treinado até 2026-05-19T17:40:14.229Z. Este replay é retrospectivo; não constitui teste de antecipação fora da amostra.

## Operação e recuperação

`DEMO_ENABLED=true` habilita as rotas. A migração aditiva `004_demo_replay_v1.sql` e a importação devem existir antes de habilitar uma instalação nova. O ambiente atual usa o PostgreSQL, Gemini e corpus já existentes. O orçamento específico do RAG demo é 40 s no total, até 30 s na geração, dentro do limite da função de 60 s; o orçamento live permanece preservado.

A função usa `gru1` (São Paulo), próxima ao PostgreSQL existente em `sa-east-1`. Cada avanço confirma várias operações na mesma transação; manter função e banco próximos evita acumular latência entre regiões. A região está versionada em `vercel.json` e só passa a valer em um novo deployment. Validar a duração HTTP e o roteiro completo no Preview antes de promover a versão final.

Sessões duram 24 h e usam token separado por aba. Uma única requisição de avanço pode ficar pendente por sessão. Conflitos de revisão exigem leitura do contexto; não repetir automaticamente um avanço ambíguo. Todos os IDs de comandos ficam registrados durante a sessão, com respostas completas dos oito mais recentes. Repetir um ID antigo retorna `command_response_expired` sem reexecutar.

Eventos mantêm contexto congelado e resultados terminais imutáveis. A geração ocorre fora da transação de avanço. Falhas transitórias têm no máximo três tentativas, com lease de 60 s; a interface exibe a limitação se a geração não puder concluir. O painel permanece funcional sem WebGL, exibindo prévia estática e sensores.

Depois de 24 h, uma sessão ainda retida responde 410; depois da limpeza limitada, 404. Em ambos os casos, preparar uma nova sessão.

## Verificação reproduzível

Executar na raiz do checkout, com as dependências Python/Node instaladas e `PYTHONPATH=services/twinops/src;.` no Windows:

```text
python -m pytest services/twinops/tests -q
npm.cmd run test:run
npm.cmd run build
python scripts/verify_demo_import.py --source <arquivo-original> --env-file <env-local> --environment preview --output <evidencia.json>
python scripts/verify_demo_postgres.py --env-file <env-local> --output <evidencia.json>
```

Usar `--initialize` no importador somente quando a migração demo ainda precisar ser aplicada. Os scripts não imprimem DSNs, chaves ou conteúdo bruto. A verificação PostgreSQL cria somente sessões demo próprias. Não apontar fixtures destrutivas de testes para o banco compartilhado.

Evidências versionadas: `demo-replay-import-evidence.json` comprova leitura exata e importação idempotente, com fingerprint live idêntico antes/depois. `demo-replay-postgres-evidence.json` comprova três sessões simultâneas, 30 posições comparáveis em 1/2/5 pares/s, scores/evidências/eventos iguais e comando concorrente aplicado uma única vez. O aceite publicado deve adicionar URL, SHA, resposta real sem fallback e citações documentais válidas.

## Rollback

Deployment anterior preservado: `dpl_Hyb5X1iSfwRvmiUDYX1sudBFpLmB`, URL `https://forzy-twinops-4w9ptjani-9luis7s-projects.vercel.app`.

```text
vercel rollback https://forzy-twinops-4w9ptjani-9luis7s-projects.vercel.app --yes
```

Alternativamente, configurar `DEMO_ENABLED=false` e publicar um novo deployment. Alterar a variável sozinha não modifica deployments imutáveis já publicados. As tabelas demo são aditivas e podem permanecer; rollback não precisa apagar dados nem alterar tabelas live. A correção da coleta semanal e integrações com ordens de serviço ficam fora desta entrega.
