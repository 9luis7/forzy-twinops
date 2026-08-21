# Neon Free no TwinOps demonstrativo

## Estado provisionado

- Integração Vercel Marketplace: `neon`.
- Recurso: `forzy-twinops-db`, conectado ao projeto `forzy-twinops`.
- Plano: Free (`free_v3`), sem upgrade ou cobrança automática autorizada.
- Região: São Paulo (`gru1`).
- Auth da Neon: desabilitado; esta entrega usa somente Postgres.
- Runtime: `DATABASE_URL` pooled, apropriada para Functions concorrentes.
- Transporte: TLS é obrigatório e verificado no socket libpq.

O Marketplace injeta referências de ambiente nos escopos Production, Preview e
Development. O backend usa somente `DATABASE_URL`; nenhuma variável de banco
pode receber prefixo `VITE_`. A integração também pode expor nomes auxiliares,
como `DATABASE_URL_UNPOOLED`, mas o verificador deste projeto deliberadamente
não os lê.

## Aplicar e verificar o schema v2

Execute a partir da raiz ligada ao projeto, sem copiar a DSN para argumentos ou
logs:

```powershell
vercel env run -- services\twinops\.venv\Scripts\python.exe scripts\check_postgres.py --migrate services\twinops\migrations\002_real_twin_v2.sql
```

O script aceita exclusivamente a migration versionada
`002_real_twin_v2.sql`. Antes de ler ou executar o SQL, runtime e script fazem
um check read-only dos catálogos. Se o schema estiver incompleto, ambos usam a
mesma chave fixa de `pg_advisory_xact_lock`, repetem o check dentro da transação
e só então executam a migration exata. Assim, banco atual não repete DDL ou
backfill e cold starts concorrentes ficam serializados. O script também valida:

- as cinco tabelas v2;
- os dois índices operacionais;
- TLS na conexão aberta pelo cliente;
- insert, leitura e remoção de um registro-probe.

Sucesso produz apenas:

```text
postgres_check_ok tables=5 indexes=2 ssl=true probe=passed
```

Falhas informam somente o tipo e, quando seguro, a etapa. A DSN, hostname,
usuário e mensagem original da exceção nunca são impressos.

## Operação e desconexão

Liste o recurso pelo projeto antes de qualquer mudança:

```powershell
vercel integration list forzy-twinops
```

Desconectar remove as variáveis do projeto, mas preserva o banco no provedor:

```powershell
vercel ir disconnect forzy-twinops-db forzy-twinops
```

Excluir o recurso é destrutivo e exige uma autorização separada; não faz
parte deste plano. Para evitar custo inesperado, mantenha o plano Free e trate
qualquer pedido de upgrade, threshold de cobrança ou remoção como gate humano.
