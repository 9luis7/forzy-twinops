# Pacote 04 — Copiloto explicável com modelo local e fallback

## Missão

Substituir respostas mockadas por explicações ancoradas em
`AssetConditionAssessment`, sem permitir que o modelo de linguagem crie ou altere o
alerta.

## Ownership exclusivo sugerido

Frontend:

- `src/components/Copilot.jsx`
- `src/copilot/CopilotClient.js`
- `src/copilot/buildExplanationContext.js`
- `src/copilot/DeterministicExplanation.jsx`
- fixtures/testes do copiloto

Backend:

- `services/twinops/copilot/**`
- rota `POST /api/v1/copilot/explain`
- harness de avaliação e resultados

Não editar ML, collector, twin 3D, contratos, `LiveTwinContext`, mocks ou
`package.json`.

## Política de execução

1. O alerta e as evidências já chegam prontos do ML.
2. O gateway tenta o candidato local Qwen3-4B `Q4_K_M` quando configurado.
3. A API externa é baseline/fallback apenas se houver autorização para envio do
   contexto industrial.
4. Se ambos falharem, produzir explicação determinística sem alterar a operação.
5. Fine-tuning permanece fora de escopo até a avaliação mostrar erro recorrente
   não resolvido por contexto, ferramentas ou prompt.

## Request/response

Request contém pergunta, asset, avaliação atual, referências de evidência e
limitações. Não envia a store completa nem histórico bruto desnecessário.
As referências apontam somente para `AssessmentEvidence.id`; cada evidência
recebida segue o contrato fechado do pacote 00, com feature/valor/unidade
obrigatórios e campos comparativos tipados opcionais/nullables.

Response contém:

- `answer`;
- `evidenceRefs` válidas;
- `provider` e `model`;
- latência/TTFT quando disponível;
- `fallbackUsed`;
- `humanValidationRequired`;
- limitações propagadas.

O servidor valida que referências citadas existem no request. Causa não presente
nas evidências só pode ser descrita como hipótese a verificar.

## Avaliação mínima

Criar 30–50 casos com estado normal, watch/alert, dado stale, gap,
`insufficient_data`, evidência contraditória e pergunta fora do escopo.

Medir:

- aderência às evidências;
- utilidade técnica em português;
- afirmações sem suporte;
- TTFT e duração total;
- VRAM e tokens/s do local;
- custo da API;
- taxa de fallback.

Qwen só vira default após comparação registrada. Até lá, a seleção é por
configuração, não por hardcode.

## Critérios de aceite

- Falha do copiloto não altera alerta, score ou coleta.
- Toda resposta sobre estado atual cita pelo menos uma referência ou declara
  dados insuficientes.
- Não converte score em probabilidade de falha, RUL ou causa raiz.
- Mudança de `inferenceId` atualiza o contexto; leituras do mesmo episódio não
  deixam conversa presa em um scenario mockado.
- Bundle não contém chave/URL de modelo.
- Falha local aciona fallback permitido; falha total usa explicação
  determinística visível.
- Testes cobrem prompt injection no texto do usuário e evidência inexistente.

## Entrega do worker

Relatar modelos/provedores testados, configuração, métricas, casos reprovados,
taxa de fallback e recomendação. Não baixar modelo grande nem enviar dados para
API sem gate de infraestrutura/privacidade do integrador.

