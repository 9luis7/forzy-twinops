# Registro de experimentos

Este documento acompanha testes concluídos e planejados. Cada experimento deve
definir uma hipótese, um procedimento reproduzível e critérios de avaliação
antes da execução.

## EXP-001: análise exploratória da planilha real

**Status:** concluído, com interpretação pendente de revisão.

**Pergunta:** a coleta contém padrões ou momentos investigáveis que possam
orientar o demonstrador?

**Resultado:** a EDA encontrou seis ativações, problemas de aquisição e dois
eventos candidatos com mudanças em degraus no canal `Velocidade`.

**Correção posterior:** a ficha técnica define `Velocidade` como velocidade de
vibração RMS em `mm/s`, não como rotação do eixo. A explicação inicial por
mudança de carga ou setpoint precisa ser descartada até a reanálise.

**Conclusão:** velocidade de vibração e temperatura são sinais úteis, mas os
dados não confirmam falha mecânica nem sua causa. Os eventos servem para nova
investigação e backtesting inicial.

## EXP-002: disponibilidade e contrato dos endpoints

**Status:** concluído em 12 de agosto de 2026.

**Hipótese:** os endpoints podem fornecer a leitura atual dos dois sensores ao
demonstrador.

**Procedimento:** executar chamadas GET repetidas aos endpoints S1 e S2,
registrar status HTTP, payload, headers e latência, e testar CORS.

**Resultado:** ambos responderam com HTTP 200 e baixa latência. O contrato é
mínimo, não contém timestamp e não permite acesso direto pelo navegador.

**Conclusão:** a API é adequada como origem experimental, desde que um backend
faça a coleta, acrescente o horário de recebimento, valide o schema e mantenha
um histórico próprio.

## EXP-003: alerta antecipado com ML clássico

**Status:** concluído no CSV real para validação do pipeline e latência; eficácia
preditiva permanece inconclusiva por ausência de rótulos de falha.

**Hipótese:** tendências e mudanças de regime em velocidade de vibração RMS,
aceleração de vibração e temperatura conseguem indicar deterioração antes de
um limite crítico.

**Variantes iniciais:**

- regras de tendência e mudança abrupta;
- detecção de change point;
- Isolation Forest ou método equivalente de anomalia multivariada.

**Métricas congeladas antes do holdout:**

- score por ciclo e regime;
- episódios `watch`/`alert` por ativação e tempo steady em alerta;
- estabilidade de limiares entre folds;
- ranking de eventos candidatos, sem tratá-los como verdadeiros positivos;
- antecedência relativa ao evento candidato, nunca lead time de falha;
- latência da inferência;
- estabilidade diante de gaps e leituras duplicadas.

**Resultado disponível:** o baseline robusto, o replay cronológico por ciclo e
o challenger Isolation Forest foram validados por testes determinísticos. No
CSV real, 7.183 linhas originaram 14.366 leituras canônicas, 204 ciclos e
8.562 repetições consecutivas foram marcadas como sem nova informação, restando
5.804 observações novas e 5.066 linhas com features válidas. O walk-forward executou 200 folds; os dois
últimos ciclos ficaram congelados como holdout. A latência do score por fold
em lote foi de 4,69 ms no p50, 7,47 ms no p95 e 126,78 ms no p99 neste computador. O
challenger nunca é promovido automaticamente.

**Correções de revisão independente:** os folds agora são derivados dos
intervalos `event_at` de cada ciclo e rejeitam IDs fora da ordem cronológica,
sobreposição e qualquer treino cujo último evento alcance o primeiro evento de
teste. Baselines são ajustados separadamente por sensor; a fronteira de uma
única avaliação rejeita entrada multissensor. Recorrência A→B→A é preservada e
somente repetição consecutiva é marcada como duplicata. Tempo steady em alerta
soma apenas pares consecutivos de alerta, sem atravessar normal, gap ou quebra
de cadência.

**Segurança dos artefatos:** o bundle não se autentica sozinho. A carga do
`joblib` exige os hashes esperados do manifesto e do modelo, previamente
ancorados pelo chamador em configuração confiável fora do diretório do bundle.
Hashes declarados apenas pelo sidecar co-local servem para consistência, não
para autenticação. Os hashes do artefato de demonstração devem ser capturados
da saída do comando de build e fixados pelo ambiente de execução.

**Critério de honestidade:** enquanto não houver falhas confirmadas, o sistema
deve comunicar risco de anomalia ou deterioração, não previsão confirmada de
falha.

## EXP-004: Qwen3-4B local contra API de LLM

**Status:** planejado.

**Hipótese:** o Qwen3-4B `Q4_K_M` executado na RTX 3060 Ti pode produzir
explicações técnicas úteis com latência e qualidade suficientes para o
demonstrador.

**Variantes:**

- Qwen3-4B `Q4_K_M` local, com contexto curto e modo sem raciocínio longo;
- API de LLM usada como baseline e fallback.

**Conjunto de avaliação:** criar entre 30 e 50 situações representativas com
telemetria, alertas, perguntas e critérios de resposta revisados.

**Métricas:**

- tempo até o primeiro token;
- duração total e tokens por segundo;
- aderência aos dados fornecidos;
- utilidade técnica em português;
- alucinações e afirmações sem evidência;
- consumo de VRAM;
- custo por consulta.

**Decisão posterior:** habilitar o modelo local por padrão somente se ele
atingir os critérios de qualidade e latência definidos pelo conjunto de
avaliação.

## EXP-005: necessidade de fine-tuning

**Status:** bloqueado pelos resultados do EXP-004.

**Hipótese:** um ajuste QLoRA pode melhorar terminologia, formato e disciplina
de evidências quando prompt, ferramentas e RAG não forem suficientes.

**Condição de início:** identificar erros recorrentes e reunir exemplos
revisados que representem esses erros.

**Não usar fine-tuning para:** memorizar telemetria, atualizar manuais ou
substituir o acesso às fontes reais.

## EXP-006: reinterpretar a EDA com a semântica correta do sensor

**Status:** pipeline reproduzível executado no CSV real de 7.183 registros.

**Pergunta:** os eventos encontrados continuam investigáveis quando
`Velocidade` é interpretada como velocidade de vibração RMS em `mm/s`?

**Hipótese:** mudanças em velocidade RMS e temperatura separada por fase podem
identificar regimes e eventos candidatos sem usar RPM. Aceleração permanece
fora do score enquanto sua estatística for desconhecida.

**Procedimento:** reconstruir ciclos cronológicos, revisar unidades, segmentar
fases estimadas, analisar temperatura dentro da mesma fase e reavaliar os
eventos de 13:48:10 e 13:56:10. Não comparar S1 com S2 fisicamente antes de
confirmar montagem e eixo.

**Métricas:** magnitude e duração da mudança, persistência, repetição em outros
ciclos, qualidade da aquisição e distância do baseline.

**Critério de sucesso:** produzir uma interpretação compatível com a física do
sensor e classificar cada evento como comportamento normal, anomalia candidata
ou inconclusivo.

**Limitação conhecida:** o arquivo atual não contém RPM, setpoint, carga nem
rótulo de falha confirmado.

**Resultado atual:** o ranking encontrou dez ocorrências de score máximo em
três janelas iniciais do histórico. Todas foram registradas como
`candidate_not_ground_truth`; algumas aparecem duas vezes por ocorrerem no
mesmo instante em S1 e S2. A saturação do score e a pouca maturidade dos
primeiros folds impedem classificá-las como falhas. Os eventos anteriormente
citados às 13:48:10 e 13:56:10 não foram promovidos a falha confirmada.

## EXP-007: backtest cronológico no histórico Forzy

**Status:** concluído em 13 de agosto de 2026.

**Hipótese:** o histórico real é suficiente para validar o fluxo causal de
features, treino, score e artefatos, ainda que não seja suficiente para medir
previsão de falhas.

**Dados e versões:** `data/raw/forzy-history-2026-05-19.csv`, SHA-256
`f09a6613bf6ba3416555a15de6b381bd842474f5f3f33c20660416c7164f0be4`;
modelo `robust-baseline` 1.0.1. O arquivo cobre 19 de maio de 2026, de 11:46:10
a 15:43:14 no horário de São Paulo. O timezone é uma hipótese explícita porque
o CSV não o informa.

**Procedimento:** converter cada linha em leituras canônicas S1 e S2, preservar
o payload original, segmentar ciclos por gaps de 15 segundos, calcular apenas
features causais e executar walk-forward sem misturar eventos futuros no
treino. Os dois ciclos finais ficaram congelados como holdout.

**Resultado:** 14.366 leituras canônicas, 204 ciclos, 8.562 repetições
consecutivas, 5.804 novas informações e 5.066 linhas válidas. Foram executados
200 folds e 287 resultados por ciclo/regime. Latência do scoring em lote por
fold: p50 4,69 ms, p95 7,47 ms e p99 126,78 ms. Dez ocorrências foram ranqueadas como candidatas; não
existem rótulos para calcular precisão, recall, falso alerta ou antecedência de
falha.

Um benchmark separado da fronteira online, com cálculo de features e inferência
sobre uma janela determinística de 1.000 leituras, mediu 48,84 ms no p50 e
49,31 ms no p95 neste computador. Nenhuma dessas métricas inclui rede, banco ou
renderização do navegador; a latência ponta a ponta ainda precisa ser medida.

**Conclusão:** a hipótese foi aceita apenas para viabilidade técnica e baixa
latência. O conjunto não sustenta a afirmação de que o modelo prevê falhas: ele
representa menos de quatro horas de um único dia, sem falhas confirmadas,
manutenções, carga, RPM ou contexto operacional rotulado. A próxima coleta deve
ser longitudinal e sincronizada com eventos de operação e manutenção.

**Artefatos:** `artifacts/ml/real-forzy/source-summary.json`,
`backtest-report.json`, `model-card.md`, `feature-manifest.json` e o pipeline
versionado. O CSV de features é derivado e pode ser regenerado. Para esta
execução, os anchors externos são manifesto
`sha256:3319936da354fe9bb1ec37755940688abacd57876a44bfeda3e1d78fef39aed5`
e modelo
`sha256:68d00121edbf8c4c01cf7cd231cd57c4c8eff25661135494e3c791ca78e562ba`.
Em deploy, esses valores devem ser fixados no ambiente confiável.

## EXP-008: fluxo ponta a ponta com o histórico real

**Status:** concluído em 13 de agosto de 2026.

**Pergunta:** o histórico original consegue atravessar importação, persistência,
scoring, API canônica e interface live sem recorrer aos dados sintéticos do
replay?

**Hipótese:** uma base SQLite descartável construída a partir do CSV original
deve produzir um snapshot canônico S1/S2 que a aplicação consiga apresentar no
perfil do motor, preservando as limitações do modelo.

**Dados e versões:** `docs/History_32026-05-19T11-46-10-920.csv`, SHA-256
`f09a6613bf6ba3416555a15de6b381bd842474f5f3f33c20660416c7164f0be4`;
artefatos `robust-baseline` 1.0.1 com os mesmos anchors do EXP-007; Chrome do
sistema controlado por Playwright 1.47.2.

**Procedimento:** apagar a base temporária, importar o arquivo original pelo
adaptador Forzy, carregar o artefato de ML com verificação de hashes, iniciar a
API e o Vite localmente, aguardar o snapshot usado pelo próprio navegador e
navegar até `MTR-BMB-042`. Nenhum endpoint externo é chamado e nenhuma base de
demonstração é alterada.

**Resultado:** 7.183 linhas foram convertidas em 14.366 amostras canônicas, sem
duplicatas de identidade. O teste confirmou 7.183 amostras em S1 e 7.183 em S2,
canais históricos, score com semântica
`relative_to_historical_baseline_not_failure_probability`, estado
`Indeterminado`, gauges S1/S2 e ausência de traçado sintético no modo canônico.
Três execuções limpas completas levaram 121,9 s, 107,6 s e 98,9 s; as etapas
de navegador levaram 15,8 s, 17,4 s e 12,2 s. A maior parte do tempo está na
importação SQLite linha a linha, não na inferência isolada.

**Falha encontrada e corrigida:** o polling iniciava novas avaliações a cada
cinco segundos mesmo quando a anterior ainda estava em andamento. Em cargas
lentas isso cancelava respostas úteis e duplicava trabalho. Agora o próximo
ciclo só é agendado depois que o atual termina, e uma assinatura cancelada no
mesmo turno não inicia requisição.

**Conclusão:** a hipótese foi aceita para o demonstrador. O fluxo técnico real
está integrado de ponta a ponta, mas o resultado continua sendo um score de
desvio relativo ao histórico, não previsão ou probabilidade de falha. A
importação deve ser otimizada antes de ser tratada como rotina operacional.

## Template de novo experimento

### EXP-XXX: título

**Status:** planejado, em execução, concluído ou cancelado.

**Pergunta:** descreva a decisão que depende deste experimento.

**Hipótese:** escreva uma afirmação que possa ser refutada.

**Dados e versões:** identifique datasets, modelos, código e configuração.

**Procedimento:** descreva passos reproduzíveis.

**Métricas:** defina medidas antes da execução.

**Critério de sucesso:** defina o resultado mínimo aceitável.

**Resultado:** registre números, artefatos e falhas observadas.

**Conclusão:** aceite ou rejeite a hipótese e registre a próxima decisão.
