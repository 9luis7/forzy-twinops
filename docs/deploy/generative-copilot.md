# Copiloto generativo

O replay reproduz leituras históricas reais. ML, gráficos, gêmeo 3D e consultas
continuam funcionando durante a geração. Cada pergunta humana captura um novo
snapshot no servidor; o histórico de até quatro turnos resolve referências como
“e S1?”, sem substituir o recorte atual. Eventos automáticos usam o snapshot
imutável do evento e conservam a deduplicação por episódio.

Antes da primeira chamada, o Gemini recebe S1 e S2, últimas cinco leituras,
estatísticas das janelas de 10/60 segundos, qualidade e assessments disponíveis.
As evidências novas incluem baseline, distância normalizada e componentes do score;
o backend continua calculando os scores. O contexto declara quando não há sequência
de scores anteriores. Repetições e lacunas não comprovam tendência mecânica.

Se necessário, o modelo consulta uma ferramenta somente leitura para expandir o
histórico já autorizado: até duas chamadas, 300 leituras por consulta e 60 mil
caracteres, sem mudar ativo, sessão ou corte temporal. Reiniciar a sessão descarta
respostas antigas. Perguntas humanas têm prioridade sobre novos disparos automáticos.

Documentos pertinentes são recuperados pelo RAG existente. A ausência de manual
não bloqueia explicações operacionais; o manual WEG do motor não autoriza
procedimentos da bomba. Citações precisam corresponder literalmente a trechos
recuperados. O Gemini nativo seleciona no máximo uma passagem documental por
resposta, evitando referências duplicadas sem reduzir a validação literal.
Hipóteses técnicas são identificadas como hipóteses; o modelo não
confirma causa, altera score, estima probabilidade/RUL ou executa manutenção.

## Configuração

No backend da Vercel: `TWINOPS_RAG_ENABLED=true`, `TWINOPS_RAG_PROVIDER=gemini`,
`GEMINI_API_KEY` e `TWINOPS_RAG_GENERATION_MODEL=gemini-3.5-flash-lite`.
O replay também exige `DEMO_ENABLED=true`, o banco demo e os anchors do artefato ML
já utilizados pelo projeto. A consulta ao corpus exige identidade/modelo de
embedding compatíveis com o índice publicado; trocar o modelo generativo não
reindexa documentos. Flags administrativas permanecem desligadas em produção.

Gravar a chave somente como variável de servidor, sem prefixo `VITE_` e sem Git.
Alterações de ambiente exigem novo deployment. O smoke local lê `.env.local`:

```text
PYTHONPATH=services/twinops/src python scripts/smoke_gemini_copilot.py
PYTHONPATH=services/twinops/src python scripts/smoke_gemini_copilot.py --history-tool
```

No PowerShell, definir `$env:PYTHONPATH='services/twinops/src'` antes de executar
`python`. O script faz chamadas reais ao provedor usando uma fixture sintética
identificada, imprime apenas metadados sanitizados e não é prova do fluxo publicado.

## Procedência e falhas

`generation.status=generated` comprova resposta validada de uma invocação;
`model`, `invocationId`, `latencyMs` e `toolCalls` vêm do backend. `models` continua
descrevendo a configuração. Registros antigos sem prova são identificados na UI.
Falhas aparecem como “Resumo automático · IA indisponível”, preservando a pergunta
para nova tentativa. O replay não aguarda a IA. O orçamento demo/histórico é
40 segundos totais, com até 30 segundos de geração; o live conserva seu limite
configurado de até 11 segundos. A latência do provedor é variável.

Para aceite, verificar replay em andamento, pergunta sobre score de S2, distinção
entre pico e tendência, continuação “e S1?” com novo corte e citações documentais
válidas quando pertinentes. Conferir o resultado real e `generation`, não apenas
o nome do modelo. Testes com transportes simulados são separados dessas chamadas.
