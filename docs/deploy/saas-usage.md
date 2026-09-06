# Uso do TwinOps

O produto abre em **Visão geral**. **Histórico** permite consultar os registros preservados; **Demonstração** é um recurso opcional para reproduzir a chegada de dados.

## Visão geral e histórico

A visão geral tenta consultar o último estado operacional disponível. Se a coleta estiver indisponível, mantém o acesso aos registros históricos reais, com fonte e data explícitas. Isso não representa uma coleta nova nem altera os dados operacionais.

Em **Histórico**, escolha o período e os sensores e pressione **Aplicar filtros**. Os campos de data usam o horário de Brasília. A tabela oferece **Anterior**, **Próximo** e **Analisar este instante**. A seleção aplicada atualiza sensores, gráficos e 3D em conjunto. Enquanto uma consulta está pendente ou falha, a última seleção válida permanece identificada na tela.

S1 corresponde ao motor e S2 à bomba. As associações e posições junto ao acoplamento são assumidas e não foram validadas fisicamente. Selecionar um componente permite focar ou isolar sua geometria. Os valores continuam disponíveis caso o navegador não consiga carregar o 3D.

## Copiloto

O botão **Copiloto** permanece no canto da tela. No computador, o painel abre ao lado dos gráficos; em telas estreitas, ocupa a tela. Fechar preserva a pergunta e a consulta em andamento. A tecla Escape fecha o painel e devolve o foco ao botão.

No histórico, cada pergunta fica vinculada ao conjunto, período e instante exibidos. Aplicar outra seleção encerra a conversa anterior e cancela a espera pela resposta antiga. Filtrar, navegar ou abrir o painel não chama a IA. Somente enviar a pergunta inicia a consulta documental.

A referência do manual e a condição calculada no instante histórico aparecem separadas. A condição e as evidências numéricas vêm do backend; o modelo de linguagem consulta os trechos do manual. O corpus WEG W22 cobre o motor, sem documentação da bomba. Fontes, limitações e respostas de contingência permanecem acessíveis. Uma indisponibilidade do provedor exige nova tentativa manual; não há repetição automática nem troca de provedor.

Na demonstração, **Ver orientação** abre no mesmo painel a resposta já produzida para um evento, sem gerar outra consulta. O contexto permanece vinculado ao evento enquanto a reprodução continua.

## Limites e configuração

As avaliações históricas são retrospectivas e relativas ao baseline. Não expressam probabilidade de falha, causa confirmada ou antecipação validada. Horários originais são preservados; recebimento e frescor desconhecidos não são inventados. Os gráficos indicam explicitamente seu fuso.

O histórico usa o banco dedicado existente, selecionado por `DEMO_DATABASE_URL`. A conexão operacional `DATABASE_URL` permanece no Neon. Não há migração, novo recurso ou dependência. A leitura histórica e o corpus dedicado podem funcionar com a reprodução desligada; `DEMO_ENABLED` continua controlando somente as rotas de demonstração. O corpus histórico usa a identidade `DEMO_RAG_EQUIPMENT_MODEL`, compartilhada com a demonstração existente.

As consultas históricas são `GET /api/history/v1/datasets` e `GET /api/history/v1/datasets/{id}/context`. A consulta manual é `POST /api/history/v1/datasets/{id}/assistant/query`, com seleção e revisão conferidas no servidor antes da IA. O navegador não fornece medições ou avaliações. Essas rotas não criam sessões de reprodução nem gravam leituras. Respostas usam `Cache-Control: no-store`.
