# Demonstração do TwinOps com replay real

## Entrega

A rota `/demo` conecta o histórico normalizado, avaliações causais por sensor, o conjunto CAD e orientações documentais do corpus WEG. O roteiro guiado reproduz 300 pares, linhas de dados 141 a 440, com aquecimento anterior identificado. O modo livre oferece os 7.183 pares completos.

S1 representa o canal 1 na carcaça do motor, junto ao acoplamento; S2 representa o canal 2 na bomba, também junto ao acoplamento. As posições são assumidas para demonstração e não participam dos cálculos. Não há simulação mecânica nem alegação de probabilidade de falha.

## Como apresentar

1. Abrir `/demo`, manter **Guiado · 300 pares** e escolher **Preparar replay**.
2. Mostrar as duas posições assumidas, os valores e a distinção entre relógio histórico e horário de chegada.
3. Usar **Continuar** a 1 par/s. O cenário dura aproximadamente cinco minutos, além da latência de rede e das pausas do apresentador.
4. Acompanhar 3D, avaliações S1/S2 e os três gráficos. Cada revisão é compartilhada por todas as visualizações. Repetições contam como chegadas, sem gerar desvios artificiais.
5. No primeiro episódio de atenção sustentada, abrir **Ver recomendação e fontes do evento** quando a resposta estiver pronta. O contexto da resposta continua sendo o do evento enquanto a telemetria avança.
6. Pausar, selecionar S1 ou S2, focar/isolar o componente, avançar um par e enviar uma pergunta sobre a revisão pausada.
7. Retomar; demonstrar os ritmos de 2 e 5 pares/s. Reiniciar restaura somente esta sessão. Uma segunda aba cria uma sessão independente.
8. No modo livre, explorar o histórico completo e as lacunas. Ocultar a aba suspende a reprodução; voltar exige **Continuar**.

## Fonte e integridade

- Dataset: `forzy-history-debbd57af9b90b8a`.
- Fonte SHA-256: `debbd57af9b90b8aa70f5794c48fa759afd0ec291d8b56c0c80ed63bfc670c5e`.
- Formato real: ZIP/OOXML, apesar da extensão CSV. Três linhas de cabeçalho e 7.183 linhas de dados, duas leituras por linha.
- O arquivo bruto e os campos PDI permanecem fora do repositório, bundle, respostas HTTP e logs.
- `observedAt` preserva o horário original; `receivedAt` registra a chegada da reprodução. Janelas, persistência e lacunas usam somente o relógio original e o prefixo já recebido.
- O modelo fixado foi treinado até 2026-05-19T17:40:14.229Z. Este replay é retrospectivo; não constitui teste de antecipação fora da amostra.

## Operação e recuperação

`DEMO_ENABLED=true` habilita as rotas. `DEMO_DATABASE_URL` seleciona opcionalmente um PostgreSQL dedicado para replay e corpus RAG da demonstração. Sem essa variável, o comportamento compartilhado anterior usa `DATABASE_URL`. A decisão de 05/09 é usar Supabase Free dedicado, mantendo `DATABASE_URL` no Neon e a entrega hospedada no projeto Vercel existente, conforme a [meta atualizada](../superpowers/plans/2026-09-05-hosted-zero-cost-goal.md).

Para Supabase, usar o **session pooler na porta 5432**, com TLS explícito. A variável fornecida pela integração como `DEMO_SUPABASE_POSTGRES_URL_NON_POOLING` utiliza esse endpoint; conferir host, usuário vinculado ao projeto, porta e `sslmode` antes de configurar `DEMO_DATABASE_URL`. Não usar o transaction pooler 6543 com os drivers atuais. A integração deve ser conectada com prefixo próprio e escopo Preview primeiro, preservando a conexão live; nenhuma variável de conexão pode usar prefixo `VITE_`.

No destino dedicado, aplicar `003_rag_asset_aware_v1.sql`, `004_demo_replay_v1.sql` e `005_demo_private_access.sql` na mesma transação antes de importar. A terceira migração habilita RLS e revoga privilégios de `PUBLIC`, `anon` e `authenticated` apenas nas oito tabelas demo/RAG: o acesso ocorre pelo backend e pelos tokens de sessão, sem disponibilizar o corpus ou o histórico completo pela Data API do Supabase. O usuário proprietário PostgreSQL usado pelo backend conserva seu acesso. Não aplicar esse procedimento ao Neon ou a outro projeto Supabase.

`DEMO_RAG_EQUIPMENT_MODEL` seleciona opcionalmente a identidade do equipamento usada apenas na busca e geração documental da demo. Para o corpus WEG reconstruído, definir `DEMO_RAG_EQUIPMENT_MODEL=W22`, correspondente à família identificada no manual. Preservar `TWINOPS_RAG_EQUIPMENT_MODEL=W22 13887610` para o live. Sem o override, a demo herda o modelo live; a identidade precisa corresponder exatamente à do corpus publicado. Esse vínculo documental não valida a posição dos sensores nem amplia a cobertura do manual à bomba.

Com uma conexão demo distinta e a demo habilitada, o startup não inicializa o Neon. Uma rota live tenta inicializá-lo sob demanda; falha retorna `503 live_unavailable`, `Cache-Control: no-store` e `Retry-After: 30`. Depois desse intervalo uma nova solicitação pode tentar recuperar o live. O replay e a busca no corpus dedicado permanecem independentes, sem substituir um corpus ausente pelo corpus live.

Gemini direto e os modelos existentes continuam em uso. Confirmar que o projeto exato da chave está no plano gratuito antes de embeddings ou geração. Enquanto essa confirmação/credencial faltar, manter `TWINOPS_RAG_ENABLED=false` e `RAG_ADMIN_ENABLED=false` na branch do novo Preview. A disponibilidade de um modelo Free não comprova o plano da conta; uma chave Sensitive já salva na Vercel pode não ser recuperável por `env pull`. Não colocar chaves no Git ou em mensagens.

O orçamento específico do RAG demo é 40 s no total, até 30 s na geração, dentro do limite da função de 60 s; o orçamento live permanece preservado. A reconstrução do índice WEG no destino dedicado utiliza IDs novos, com verificação do mesmo PDF, páginas e hashes. Integridade da indexação e testes com provedor simulado não substituem o aceite publicado com geração real.

Na demo, se o modelo copiar uma citação literal mas vinculá-la ao ID de outro trecho conhecido, o servidor pode corrigir apenas essa referência: a mesma citação deve aparecer em exatamente um dos trechos recuperados e autorizados. O texto não é alterado; páginas, documento e link vêm do trecho encontrado. IDs desconhecidos, texto sem correspondência, ambiguidade e duplicatas continuam sujeitos à recusa pelo validador. A resolução não busca documentos adicionais nem modifica a validação live.

O CLI de indexação espaça os lotes em 65 segundos após cada resposta bem-sucedida. Os quatro lotes do manual exigem pelo menos 195 segundos de intervalos, além da extração, rede e gravação. Isso limita a rajada de ingestão no plano Free; não garante disponibilidade da cota. Uma resposta 429 interrompe a execução sem repetição automática ou persistência parcial de documento. A retomada conserva o UUID do corpus e reutiliza um documento já concluído. O limiar de busca aceita somente a diferença de arredondamento do PostgreSQL, com tolerância absoluta de `1e-15`; valores materialmente distintos continuam bloqueados.

A função usa `gru1` (São Paulo), próxima ao PostgreSQL existente em `sa-east-1`. Cada avanço confirma várias operações na mesma transação; manter função e banco próximos evita acumular latência entre regiões. A região está versionada em `vercel.json` e só passa a valer em um novo deployment. Validar a duração HTTP e o roteiro completo no Preview antes de promover a versão final.

O dataset é imutável e fica em cache na instância do repositório, limitado a duas entradas e 16 MiB de JSON UTF-8. Cada consumidor recebe uma cópia isolada; sessões, tokens, revisões, comandos e eventos continuam dependendo do banco. Isso evita transferir novamente os aproximadamente 5,33 MB do histórico em cada avanço de uma instância aquecida. Instâncias novas e datasets removidos do cache fazem uma nova leitura; o limite não inclui objetos temporários decodificados nem o overhead do interpretador.

Uma cota esgotada no Neon impede o live, mas não deve impedir o cenário demonstrativo configurado no banco dedicado. Cache e rollback de código não liberam cotas. Se o banco demo recusar conexões por cota, suspender os testes e verificar consumo/limites sem contratar upgrades ou autorizar cobrança. Evidências de execuções anteriores não comprovam a disponibilidade atual. O custo adicional máximo aprovado é zero.

Sessões duram 24 h e usam token separado por aba. Uma única requisição de avanço pode ficar pendente por sessão. Conflitos de revisão exigem leitura do contexto; não repetir automaticamente um avanço ambíguo. Todos os IDs de comandos ficam registrados durante a sessão, com respostas completas dos oito mais recentes. Repetir um ID antigo retorna `command_response_expired` sem reexecutar.

Eventos mantêm contexto congelado e resultados terminais imutáveis. A geração ocorre fora da transação de avanço. Falhas transitórias e respostas do modelo recusadas pela validação de citações têm no máximo três tentativas, com lease de 60 s. Cada tentativa exige uma resposta nova e citações literais válidas; texto recusado não é publicado. A interface indica a consulta em andamento enquanto a requisição está pendente e exibe a limitação se as tentativas não concluírem. O painel permanece funcional sem WebGL, exibindo prévia estática e sensores.

Depois de 24 h, uma sessão ainda retida responde 410; depois da limpeza limitada, 404. Em ambos os casos, preparar uma nova sessão.

## Verificação reproduzível

Executar na raiz do checkout, com as dependências Python/Node instaladas e `PYTHONPATH=services/twinops/src;.` no Windows:

```text
python -m pytest services/twinops/tests -q
npm.cmd run test:run
npm.cmd run build
python scripts/verify_demo_import.py --source <arquivo-original> --env-file <env-local> --environment preview --demo-project-ref <projeto-Supabase-dedicado> --output <evidencia-importacao.json>
python scripts/verify_demo_postgres.py --env-file <env-local> --demo-project-ref <mesmo-projeto> --output <evidencia-sessoes.json>
python scripts/prepare_demo_rag.py <manual-original.pdf> --output <novo-preflight-offline.json>
```

No modo dedicado, os verificadores exigem `DEMO_DATABASE_URL` compatível com o projeto informado e nunca abrem a conexão live. A evidência declara explicitamente que o fingerprint live não foi reconsultado; conferir separadamente a preservação da configuração Neon. Sem `--demo-project-ref`, os scripts mantêm o modo legado compartilhado e suas verificações de fingerprint.

Usar `--initialize` no importador apenas em destinos cujo esquema demo ainda precise ser aplicado; no Supabase dedicado, aplicar primeiro o conjunto 003/004/005 para preservar o acesso privado desde o início. Os scripts não imprimem DSNs, chaves ou conteúdo bruto. A verificação PostgreSQL cria somente sessões demo próprias. O teste de RLS roda exclusivamente no PostgreSQL descartável do CI; nunca apontar fixtures destrutivas ao banco hospedado.

Depois de confirmar a conta Free e disponibilizar a credencial pelo canal privado, executar a indexação e a publicação separadamente, mantendo o mesmo UUID novo nas repetições:

```text
python scripts/prepare_demo_rag.py <manual-original.pdf> --execute --expected-project-ref <projeto-Supabase-dedicado> --corpus-id <novo-UUID4> --gemini-free-tier-verified --output <nova-evidencia-indexacao.json>
python scripts/prepare_demo_rag.py <manual-original.pdf> --execute --publish --expected-project-ref <mesmo-projeto> --corpus-id <mesmo-UUID4> --gemini-free-tier-verified --output <nova-evidencia-publicacao.json>
```

`--gemini-free-tier-verified` registra uma atestação do operador; não consulta nem altera o faturamento. O script exige conta verificada antes desse parâmetro, usa Gemini direto sem fallback pago e não faz retry automático de cota. O preflight padrão é offline. A receita não aplica migrations e exige arquivo de evidência novo, para preservar resultados anteriores.

Evidências anteriores ao bloqueio Neon: `demo-replay-import-evidence.json` registra leitura exata e importação idempotente, com fingerprint live idêntico antes/depois; `demo-replay-postgres-evidence.json` registra três sessões simultâneas, 30 posições comparáveis em 1/2/5 pares/s e comando concorrente aplicado uma única vez. As novas evidências operacionais da base dedicada ficam em arquivos privados ignorados pelo Git, com prefixo `demo-replay-supabase-`, sem reinterpretar a evidência histórica como leitura live atual. Não incluir esses artefatos no repositório público. O aceite publicado deve registrar privadamente URL, SHA, resposta real sem fallback e citações documentais válidas.

## Rollback

Deployment anterior preservado: `dpl_Hyb5X1iSfwRvmiUDYX1sudBFpLmB`, URL `https://forzy-twinops-4w9ptjani-9luis7s-projects.vercel.app`.

```text
vercel rollback https://forzy-twinops-4w9ptjani-9luis7s-projects.vercel.app --yes
```

Alternativamente, configurar `DEMO_ENABLED=false` e publicar um novo deployment. Alterar a variável sozinha não modifica deployments imutáveis já publicados. Desabilitar a demo ou voltar ao deployment anterior restaura a dependência original do Neon; isso não recupera uma conexão ainda bloqueada por cota. As tabelas dedicadas podem permanecer e o rollback não precisa apagar dados ou alterar tabelas live. A correção da coleta semanal e integrações com ordens de serviço ficam fora desta entrega.
