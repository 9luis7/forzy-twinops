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

**Status:** planejado.

**Hipótese:** tendências e mudanças de regime em velocidade de vibração RMS,
aceleração de vibração e temperatura conseguem indicar deterioração antes de
um limite crítico.

**Variantes iniciais:**

- regras de tendência e mudança abrupta;
- detecção de change point;
- Isolation Forest ou método equivalente de anomalia multivariada.

**Métricas:**

- antecedência do alerta;
- taxa de falsos alertas;
- eventos não detectados;
- latência da inferência;
- estabilidade diante de gaps e leituras duplicadas.

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

**Status:** planejado.

**Pergunta:** os eventos encontrados continuam investigáveis quando
`Velocidade` é interpretada como velocidade de vibração RMS em `mm/s`?

**Hipótese:** mudanças conjuntas entre velocidade RMS, aceleração e temperatura
conseguem separar partidas, paradas e regimes anômalos sem usar RPM.

**Procedimento:** reconstruir os ciclos, revisar as unidades, comparar S1 com
S2, analisar a defasagem térmica e reavaliar os eventos de 13:48:10 e 13:56:10.

**Métricas:** magnitude e duração da mudança, diferença entre sensores,
repetição em outros ciclos, qualidade da aquisição e distância do baseline.

**Critério de sucesso:** produzir uma interpretação compatível com a física do
sensor e classificar cada evento como comportamento normal, anomalia candidata
ou inconclusivo.

**Limitação conhecida:** o arquivo atual não contém RPM, setpoint, carga nem
rótulo de falha confirmado.

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
