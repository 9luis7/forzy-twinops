# Meta atualizada: demonstração hospedada do Forzy TwinOps

Atualização autorizada pelo usuário em 05/09/2026: “vamos seguir então, atualize a meta para continuar”. Esta decisão encerra a pausa para comparar alternativas de hospedagem. Este documento complementa e, nas decisões de infraestrutura e prazo abaixo, substitui o objetivo inicial e o plano de 04/09/2026.

## Objetivo

Concluir e publicar, até terça-feira, **08/09/2026**, a demonstração integrada do Forzy TwinOps por uma URL utilizável no computador da Forzy: histórico real chegando pelo backend, avaliações por sensor, modelo 3D e gráficos sincronizados, e copiloto RAG respondendo a eventos e perguntas com citações verificadas. Quarta-feira, 09/09, fica reservada ao ensaio; o pitch ocorre quinta-feira, 10/09.

## Decisão e restrições aprovadas

- Custo adicional máximo: **R$ 0**. Não contratar planos pagos, ativar faturamento, comprar créditos nem usar um projeto de IA potencialmente cobrado. Confirmar o plano gratuito da conta/recurso exato antes das chamadas. Atingir uma cota gratuita deve interromper o uso, sem upgrade automático ou fallback pago.
- Manter o projeto Vercel existente e a aplicação atual. Criar um **Supabase Free dedicado exclusivamente à demonstração**, preferencialmente pela integração nativa do projeto/equipe TwinOps. Confirmar plano de custo zero e ausência de exigência de pagamento antes de provisionar.
- Preservar o Neon original e seus dados live. Não transferir a base principal, substituir sua conexão ou alterar projetos/organizações Supabase de terceiros. A nova base recebe somente estruturas e dados necessários à demonstração.
- Separar a configuração e a inicialização do replay/RAG demonstrativos da conexão live bloqueada. A indisponibilidade do Neon deve ser comunicada pelas rotas afetadas, sem impedir a demonstração independente. Preservar os contratos e o comportamento live quando disponível.
- Entrega hospedada, sem instalação no computador do apresentador e sem túnel ou servidor dependente do computador de Luis. Testes locais são auxiliares.
- O cache imutável do histórico implementado em `a46060dd67a4cd4c5f13a06dc16a7f99952845cb` é parte obrigatória da solução. Trocar de provedor não substitui a correção do consumo excessivo.
- Reusar Gemini direto e o conteúdo do manual WEG existente. A autorização anterior para enviar trechos recuperados ao provedor permanece válida, subordinada ao custo zero. Como não há backup integral dos vetores, a nova indexação terá identidade e versão honestas; não alegar restauração exata dos antigos IDs. Verificar hash, páginas, cobertura e citações do corpus reconstruído.
- Coleta semanal, ordens de serviço, simulação mecânica e funcionalidades novas para além do fluxo aprovado ficam fora deste objetivo.

## Autonomia

Conduzir a execução até o aceite final, resolvendo escolhas técnicas rotineiras sem nova confirmação. A autorização abrange investigação, correções, dependências necessárias, worktree/branch existentes, implementação, testes, revisão, commits, push, PR, integração, configuração do ambiente demonstrativo, provisionamento gratuito acima, migrations aditivas no destino dedicado, importação, Preview e publicação final no projeto Vercel existente.

Usar subagentes em trabalhos independentes de backend, RAG e revisão, com responsabilidade explícita por arquivos. Todos devem preservar as alterações dos demais; o integrador controla commits e publicação. Pedir intervenção somente por acesso indispensável, aceite de conta/termos reservado ao usuário ou mudança material de escopo. Não confundir ausência de acesso com autorização para usar outra organização ou um serviço cobrado.

## Entrega funcional preservada

1. Importar idempotentemente os **7.183 pares / 14.366 leituras S1/S2** do arquivo OOXML com extensão `.csv`, preservando ordem, valores, timestamps, repetições e lacunas. Manter o arquivo original e dados privados fora do Git, bundle, logs e respostas HTTP brutas.
2. Reusar sessões PostgreSQL persistidas e isoladas por token, validade de 24 horas, revisão atômica, comandos idempotentes, recuperação de interrupções e controles iniciar/pausar/continuar/passo/reiniciar em 1, 2 e 5 pares por segundo.
3. Processar apenas o prefixo já recebido. Separar horário original da medição do horário atual de chegada. Não inventar informação nova a partir de leituras repetidas.
4. Vincular S1/canal 1 ao motor e S2/canal 2 à bomba, próximos ao acoplamento, identificando as posições como assumidas para demonstração. Preservar seleção, foco, isolamento, materiais, valores, pulsos e condições do 3D.
5. Alimentar 3D, gráficos e avaliações com a mesma revisão. Manter gaps explícitos, procedência, progresso, indicadores reais do pipeline, acessibilidade e painel funcional sem WebGL.
6. Preservar acionamento RAG por atenção sustentada, agravamento e recuperação, deduplicação por episódio, contexto imutável do evento, perguntas manuais, orçamento de execução e recuperação de falhas. A telemetria deve avançar durante a geração. A cobertura do manual WEG não comprova documentação da bomba.
7. Entregar `/demo`, roteiro guiado com linhas 141 a 440 e modo livre com todo o histórico. Não substituir o aceite por respostas preparadas, contadores simulados ou estado efêmero em servidor.

## Marcos de entrega

| Data | Evidência desejada |
| --- | --- |
| Sábado, 05/09 | Infraestrutura gratuita acessível e primeiro evento com resposta real do RAG; esclarecer qualquer dependência de conta imediatamente. |
| Domingo, 06/09 | Cenário completo publicado, com replay, 3D, gráficos, evento e resposta citada; nenhuma dependência do Neon para esse cenário. |
| Segunda, 07/09 | Corrigir achados, testar outra sessão/computador e preparar uma gravação da execução real validada como reserva para o pitch. |
| Terça, 08/09 | Aceite final, URL estável, instruções de apresentação, rollback e versão congelada. |
| Quarta, 09/09 | Ensaio do pitch; evitar alterações funcionais salvo falha impeditiva. |

## Verificação e conclusão

Testar a inicialização com o banco live indisponível e o banco demo acessível, mantendo respostas live explícitas. Verificar TLS e conexão PostgreSQL agrupada compatível com o destino, migrations restritas, importação idempotente e corpus reconstruído.

Revalidar os casos relevantes de duas sessões simultâneas, velocidades diferentes, comandos repetidos, pausas/reinício durante processamento, falhas de rede, repetições, lacunas e RAG atrasado. A mesma posição deve produzir os mesmos resultados em velocidades diferentes. Fazer revisão independente antes da publicação final.

O aceite final exige executar o roteiro guiado completo pela URL publicada, com **geração real do provedor e citações válidas em pelo menos um evento real**, demonstrando que os dados continuam chegando durante a geração. Verificar perguntas manuais e reinício. Uma gravação é reserva de apresentação e não substitui esse aceite.

Só concluir a meta após implementação, testes, revisão, publicação e aceite. Entregar URL funcional, SHA publicado, resultados sanitizados das verificações, roteiro breve e procedimento de rollback. Registrar limitações residuais com precisão.

## Estado inicial desta retomada

Base de execução: worktree `replay-demo`, branch `luis/twin-3d-replay-demo`, commit `a46060dd67a4cd4c5f13a06dc16a7f99952845cb`, PR #9. Código principal implementado e CI aprovado; aceite final de RAG publicado e publicação final pendentes. Neon bloqueado por cota. Nenhum banco Supabase criado até a aprovação; tentativa anterior exigiu aceite de termos da integração. Plano exato do projeto Gemini ainda precisa ser confirmado.

O controle de meta do aplicativo retornou `blocked` nesta retomada. As ferramentas expostas apenas criam metas sem objetivo pendente ou marcam conclusão/bloqueio; não permitem editar objetivo ou reativar este controle. Este documento registra o novo escopo executável e a autorização de continuidade, sem alegar que o status automático do aplicativo foi alterado.
