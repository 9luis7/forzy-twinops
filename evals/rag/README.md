# Protocolos de avaliação

`score.py` valida exclusivamente as capturas históricas **legacy-extractive-v1**.
O protocolo exige respostas determinísticas/extrativas e conserva sua política
original em `legacy_v1.py`. Capturas antigas sem `captureProtocol` continuam
pertencendo a essa versão. O avaliador rejeita capturas do protocolo novo e
respostas com geração confirmada; suas métricas não validam prosa generativa.

`capture_synthetic.py` produz **generative-service-fixture-v2**: exercícios do
serviço atual com provedor simulado, incluindo geração sem documentação e
falhas explícitas. Reutiliza as perguntas do manifesto V1, mas aplica as regras
atuais do serviço; os antigos rótulos de recusa não governam esse protocolo.
Essas capturas não comprovam chamadas reais ao Gemini e não recebem métricas
de segurança, qualidade da prosa ou latência do provedor.

A aceitação generativa requer evidências de chamadas reais, contexto e fontes
verificados, além de revisão das afirmações e limitações da resposta. Não usar
os zeros do avaliador extrativo como medida de segurança do novo copiloto.
