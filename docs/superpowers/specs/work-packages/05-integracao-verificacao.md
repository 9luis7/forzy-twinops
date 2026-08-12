# Pacote 05 — Integração, verificação e narrativa

## Missão

Integrar os pacotes no SHA-base atualizado, verificar o fluxo ponta a ponta e
garantir que interface e pitch não ultrapassem as evidências.

Este pacote pertence ao coordenador/integrador depois dos workers 01–04.

## Ordem de integração

1. Contratos, fixtures e adapters de replay.
2. Aquisição/storage/API.
3. Scorer e artefatos congelados.
4. Frontend/twin 3D.
5. Copiloto.
6. Testes E2E e documentação da jornada.

## Cenários E2E

- Replay offline completo continua funcionando.
- Live válido de S1 e S2 chega ao snapshot e à UI.
- S1 falha e S2 continua.
- Payload repetido é sinalizado sem inflar a narrativa de amostras.
- Stale/fora de janela aparece como tal, não como normal/zero.
- Gap força `insufficient_data` até recompor janela.
- Evento candidato é exibido como anomalia candidata.
- Twin GLB indisponível cai para SVG.
- Qwen indisponível usa fallback permitido; falha total usa explicação
  determinística.
- Nenhuma tela contradiz o snapshot corrente.

## Verificação estatística e de claims

- Confirmar split cronológico por ciclo.
- Confirmar que limiar foi congelado antes do holdout.
- Procurar e remover termos indevidos: “probabilidade de falha”, “causa raiz”,
  “falha evitada”, “RUL” e “tempo até falha”, salvo quando marcados como
  capacidade futura.
- Distinguir evidência, hipótese, decisão, resultado e limitação nos documentos.

## Gates antes de merge

- Testes unitários, contrato, integração e E2E verdes.
- Build frontend verde.
- Model card e relatório de backtest presentes.
- Smoke dos endpoints documentado, mas não obrigatório para a suíte.
- Nenhum segredo/hostname temporário no bundle.
- Review independente do SHA integrado.
- Diff sem mudanças fora do ownership ou justificativa registrada.

## Atualização da jornada

Registrar em `docs/jornada/experimentos.md`:

- versões dos dados/modelos;
- procedimento reproduzível;
- resultados numéricos;
- falhas de experimentos;
- decisão seguinte;
- limitações que permanecem.

O storytelling só incorpora resultados após este gate.

