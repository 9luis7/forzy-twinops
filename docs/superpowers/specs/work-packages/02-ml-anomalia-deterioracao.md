# Pacote 02 — ML clássico para anomalia e deterioração

## Missão

Reinterpretar o CSV com a semântica correta e entregar um scorer versionado de
anomalia/deterioração. Não prometer classificação de falha.

## Ownership exclusivo sugerido

- `services/twinops/ml/data/**`
- `services/twinops/ml/features/**`
- `services/twinops/ml/models/**`
- `services/twinops/ml/replay/**`
- `services/twinops/ml/artifacts/**`
- `services/twinops/tests/ml/**`
- relatórios gerados de EDA/backtest

Não editar collector, storage base, frontend, 3D ou copiloto.

## Pipeline mínimo

1. Validar contrato, marcar gaps/duplicatas/stale e medir cadência real.
2. Segmentar proxy de `stopped`, `startup`, `steady`, `shutdown` e `unknown`.
3. Excluir transições da calibração do regime steady.
4. Criar apenas features trailing: mediana/MAD, robust z-score, EWMA,
   inclinação, persistência e change point.
5. Tratar temperatura por fase; não comparar pico pós-parada com steady.
6. Não usar aceleração no score oficial enquanto `statistic=unknown`.
7. Não usar diferença S1–S2 até montagem/eixo serem confirmados.
8. Baseline obrigatório: regras robustas + EWMA/CUSUM ou Page-Hinkley.
9. Challenger opcional: Isolation Forest treinado somente em baseline.
10. Sem deep learning e sem aprendizado online automático.

## Split e replay

- É proibido random split por linha.
- Usar replay cronológico e agrupado por acionamento.
- Desenvolvimento em expanding walk-forward; por exemplo, ciclos `1–2 -> 3` e
  `1–3 -> 4`.
- Congelar features, limiares e persistência antes do holdout final.
- Manter ciclos `5–6` como holdout se a segmentação confirmar seis ciclos
  utilizáveis.
- O ciclo dos eventos 13:48:10 e 13:56:10 fica inteiro em um único lado.
- Reiniciar estado entre ciclos e após gaps relevantes.
- Cada fold ajusta baseline, scaler, modelo e limiar apenas no passado.

## Saída

Produzir `DetectionAssessment` conforme o pacote 00. Evidências devem informar
feature, valor, unidade, baseline, desvio, direção e janela. O score significa
distância do baseline histórico, não probabilidade de falha.

Artefatos:

- dataset curado e dicionário;
- manifesto de features/janelas;
- pipeline serializado;
- limiares/persistência;
- model card com dados de treino e limitações;
- relatório congelado de backtest;
- hash de configuração e versão do modelo.

## Métricas válidas

- gaps, duplicatas, stale e cobertura;
- score por ciclo/regime;
- episódios `watch/alert` por ativação e tempo steady em alerta;
- estabilidade dos limiares entre folds;
- ranking dos eventos candidatos;
- “antecedência relativa ao evento candidato”, nunca lead time de falha;
- p50/p95/p99 de features + inferência;
- determinismo de replay.

Não publicar precision, recall, F1, falhas evitadas ou RUL.

## Critérios de aceite

- Zero vazamento temporal.
- Replay idêntico gera saída idêntica.
- Entrada inválida, stale ou gap retorna `degraded`/`insufficient_data`, nunca
  alerta mecânico por fallback.
- p95 de features + inferência menor ou igual a 100 ms no PC-alvo; pipeline
  local completo menor ou igual a 250 ms, excluindo polling e LLM.
- Toda avaliação contém modelo, versão, janela, qualidade e evidências.
- Challenger só substitui baseline se melhorar estabilidade entre ciclos sem
  aumentar carga de alertas nos trechos revisados como normais.

## Entrega do worker

Relatar resultado por ciclo, limitações, artefatos, latência e decisão explícita
sobre baseline versus challenger. Eventos candidatos não contam como verdadeiros
positivos.

