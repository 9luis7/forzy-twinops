# Contrato da Fase 0 — RAG técnico e copiloto proativo

> Status: aprovado para implementação local
> Responsável e aprovador: Luis
> Escopo autorizado: instrumentação, fallback, contratos e testes locais

## Evidência atual e hipótese aberta

O Preview comprovou que o orçamento síncrono de 10 segundos se esgota antes de
a geração terminar. Na captura diagnóstica, a chamada de geração foi cancelada
depois de aproximadamente 2,1 segundos. Isso não comprova que a geração Gemini
com o modelo, schema e chave atuais funciona ponta a ponta.

O `200 OK` observado pertence ao endpoint de embeddings. Ele valida a chave e o
modelo somente para embeddings. A geração permanece uma hipótese aberta. Um
gate futuro de Preview deve executar uma chamada controlada com prompt mínimo,
schema atual e orçamento suficiente, sem corpus ou snapshot, antes de qualquer
conclusão sobre a integração de geração.

## Objetivos da Fase 0

- Medir cada estágio do fluxo sem registrar conteúdo técnico ou segredos.
- Distinguir internamente as classes de falha e manter a API pública sanitizada.
- Substituir o truncamento ingênuo do fallback por seleção extrativa segura.
- Melhorar a degradação sem aumentar o timeout público.
- Preservar APIs v1/v2, corpus, alerta preditivo e comportamento operacional.

Não fazem parte deste gate: migration, alteração ou publicação de corpus,
executor assíncrono, novo Preview, Produção, commit ou push.

## Contrato de observabilidade

Cada evento interno usa o formato lógico abaixo:

```json
{
  "event": "rag_stage",
  "stage": "query_embedding",
  "outcome": "ok",
  "durationMs": 12.3,
  "remainingBudgetMs": 8450.0,
  "assetId": "forzy-motor-01",
  "corpusId": "uuid",
  "model": "model-id",
  "count": 6,
  "httpStatus": 200,
  "traceId": "uuid"
}
```

Campos são emitidos somente quando aplicáveis. Valores permitidos são IDs
validados, modelo configurado, contagens, status HTTP, resultado categórico e
durações. Nunca registrar pergunta, histórico, chunks, trechos, evidências
brutas, resposta do modelo, prompt, token, DSN ou credencial.

Estágios obrigatórios:

- `corpus_lookup`
- `snapshot`
- `query_embedding`
- `vector_search`
- `lexical_search`
- `fusion`
- `prompt_assembly`
- `generation` (`firstByteMs` apenas quando observável; no cliente atual não é)
- `validation`
- `remaining_budget`
- `total`

Taxonomia interna de geração:

- `timeout`: timeout próprio do transporte/provedor.
- `cancelled`: cancelamento pelo orçamento externo da rota.
- `http_status`: resposta HTTP não bem-sucedida, registrando apenas o status.
- `transport`: erro de rede sem resposta HTTP.
- `invalid_response`: payload/schema do provedor inválido.
- `invalid_citation`: referência fora dos chunks recuperados ou trecho inexato.

A API pública continua retornando somente os estados e fallbacks sanitizados já
contratados.

## Contrato do fallback extrativo

O fallback recebe a pergunta e os hits recuperados e pode somente copiar
substrings exatas dos chunks. Ele deve:

1. segmentar por parágrafo ou sentença preservando offsets no texto original;
2. priorizar spans que contenham termos da pergunta ou aliases técnicos
   conservadores;
3. rejeitar spans predominantemente numéricos, tabulares, curtos ou sem prosa;
4. preferir um único idioma compatível com a pergunta quando houver opção;
5. não misturar idiomas entre os trechos selecionados;
6. remover duplicatas e spans com sobreposição lexical excessiva;
7. limitar quantidade e comprimento sem cortar no meio de uma sentença;
8. provar que cada trecho é substring exata do chunk e manter a citação/hash do
   chunk de origem;
9. nunca criar procedimento, tradução, diagnóstico ou paráfrase;
10. retornar `manual_insufficient` quando nenhum trecho seguro for encontrado.

## Contrato arquitetural futuro

### Trigger

Triggers futuros usam campos canônicos, nunca texto livre. Devem incluir
histerese, debounce e minimum dwell para evitar flapping. `recommendationKind`
separa `maintenance`, `recovery` e `data_quality`.

### `assessmentHash`

O hash canônico incluirá:

- asset ID;
- versão, status e semântica da policy do assessment;
- evidence IDs ordenados e valores normalizados;
- fim da janela;
- classe de qualidade e classe de frescor;
- locale e template version, diretamente ou cobertos explicitamente por
  `policyVersion`.

Campos voláteis sem significado material, como tempo de serialização e ordem de
mapas, ficam excluídos.

### Imutabilidade

Uma recomendação pode transicionar somente de `pending` para `ready` ou
`degraded`. Após estado terminal, torna-se imutável. Novo assessment, corpus,
policy ou modelo cria novo ID com `supersedesId`. `stale` será derivado pela
existência de versão mais nova, não uma mutação do registro terminal.

### Executor assíncrono

Antes de uma migration futura, o contrato deve especificar criação atômica,
claim e lease (`lockedAt`, `leaseUntil`), limite de tentativas, backoff,
idempotência, recuperação de worker interrompido e concorrência. Nenhuma
infraestrutura externa será escolhida ou provisionada nesta fase.

### Base de cada item

Cada item futuro do cartão carrega `basisType=manual|operational|policy` e seus
`citationIds` ou `evidenceIds`. Procedimentos de equipamento exigem base
`manual`. Avisos como atualização de telemetria podem ter base `policy`, sempre
identificada. O LLM não pode converter checagem possível em diagnóstico ou
ordem de manutenção.

## Critérios futuros adicionais

- latência `alert-to-pending` e `alert-to-ready`;
- concorrência e deduplicação;
- eventos fora de ordem e flapping;
- retry após interrupção e lease expirado;
- corpus alterado durante job;
- recomendação superseded;
- `recommendationId` do chat restrito ao mesmo asset;
- citações 100% válidas e nenhuma ação sem fonte;
- RAGAS apenas complementar, nunca gate único.

## Riscos fora da Fase 0

Os achados de `npm audit` continuam visíveis. Correções de dependências exigem
triagem separada entre alcance runtime e dev e não serão misturadas a esta fase.
