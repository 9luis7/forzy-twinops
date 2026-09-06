# Recuperar o TwinOps em outro computador

O aplicativo publicado roda na Vercel. O banco operacional permanece no Neon; o histórico e o corpus documental usam o Supabase dedicado existente. Formatar o computador não remove esses recursos.

## Código e documentação

Clone `https://github.com/9luis7/forzy-twinops.git` e use a branch `main` após a integração da PR 10. As branches de trabalho preservam o histórico anterior. O acabamento escolhido e suas evidências estão em [design-qa.md](../../design-qa.md); as instruções de uso estão em [saas-usage.md](saas-usage.md).

O Git contém código, lockfiles, modelo 3D convertido, conversor STEP, manifests, modelos ML e documentação. Instale as dependências conforme o README e os workflows de CI. Arquivos temporários de QA e suas fixtures não são entradas do aplicativo publicado.

## Configuração hospedada

Entre nas contas existentes de GitHub, Vercel, Neon, Supabase e do projeto Google usado pelo Gemini. A Vercel mantém a configuração do runtime, incluindo as conexões dos bancos e a chave Gemini. As variáveis necessárias são documentadas em `.env.example` e nos runbooks; jamais copie valores secretos para o Git.

Preserve a escolha dos recursos gratuitos e o projeto Gemini Free confirmado pelo usuário. O nome do modelo ou uma chave, isoladamente, não comprovam a situação de faturamento. Não crie recursos, migre bancos nem troque de provedor para restaurar o aplicativo.

## Originais privados fora do Git

Antes de formatar, confirme uma cópia privada fora do disco que será apagado dos seguintes originais recebidos para o projeto:

- CSV histórico original da Forzy, usado na importação.
- Desenhos CAD originais `.stp` e `.dwg`.
- Datasheet PDF do sensor.

O histórico normalizado hospedado e o GLB versionado permitem executar a aplicação, mas não substituem a preservação dos arquivos originais. O manual WEG tem URL oficial registrada nos scripts de ingestão; conservar a cópia exata utilizada também é útil. Registros privados de configuração, aceites e evidências podem ser mantidos em armazenamento privado conforme a necessidade do usuário.

Não publique `.env`, chaves, DSNs, bases privadas, CSVs sensíveis, pastas temporárias ou caches. Um ZIP que continue no mesmo computador ainda não é uma cópia protegida contra a formatação. A existência de uma pasta de nuvem local, por si só, não comprova sincronização concluída.

## Conferência após a restauração

Abra a aplicação publicada e confira Visão geral, Histórico, 3D e Demonstração. A indisponibilidade da coleta operacional deve continuar identificada, com acesso ao histórico preservado. Uma consulta ao copiloto deve manter o instante selecionado e distinguir orientação validada de contingência. Consulte a última execução do CI e a origem Git do deploy antes de atribuir qualquer falha à nova máquina.
