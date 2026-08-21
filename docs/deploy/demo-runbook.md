# Runbook do demonstrador TwinOps real

Este runbook cobre preview, apresentação e rollback do único ativo público
`forzy-motor-01`. Ele não autoriza deploy, promoção para produção ou acesso ao
upstream real. Cada uma dessas mudanças exige confirmação explícita no momento
da execução.

## Estado antes do preview

- O build Vercel local usa Python 3.12 e a closure estritamente de runtime.
- O bundle medido tem 135,264 MiB contra o limite padrão de 225 MiB; Large
  Functions não é necessário nem foi habilitado.
- O trace contém o entrypoint, a migration `002_real_twin_v2.sql`, os cinco
  arquivos ML fixados e as dependências NumPy/Pandas/joblib. Não contém env,
  testes do projeto, `.agents`/`skills-lock.json` do repositório, SciPy ou
  scikit-learn. Wheels de terceiros ainda carregam suites de teste e sete
  documentos `.agents` do FastAPI; são metadata criada pelo builder, não
  arquivos locais nem código importado pelo TwinOps.
- O output estático contém o manifesto 3D, o GLB e o preview PNG.
- A integração Neon Free está conectada e a migration idempotente passou duas
  vezes, com SSL e insert/read/delete sanitizado.
- Preview e produção permanecem pendentes enquanto não houver upstream HTTPS
  controlado e autorização específica.

## Pré-flight sanitizado

Puxe o ambiente para um arquivo ignorado e valide somente nomes/contratos:

```powershell
vercel env pull .env.local --yes
services\twinops\.venv\Scripts\python.exe scripts\verify_env.py --file .env.local
```

O resultado esperado é `deploy_env_ok required=5`. Nunca copie o conteúdo de
`.env.local` para logs, issues ou documentação. Os anchors obrigatórios são os
hashes versionados em `.env.example`; não os recalcule a partir do bundle no
startup.

`DATABASE_URL` deve apontar para host pooled e declarar exatamente um
`sslmode=require`, `verify-ca` ou `verify-full`; valores duplicados são
rejeitados independentemente da ordem ou percent-encoding. O upstream deve ser
uma origem HTTPS limpa: sem credenciais, query, fragmento ou path. Apenas `/`
final é aceito e normalizado.

Antes do preview, confirme no dashboard que as variáveis estão no escopo
`Preview`, especialmente `DATABASE_URL`, `TWINOPS_UPSTREAM_BASE_URL` e os três
anchors ML. O Quick Tunnel histórico citado em documentos de jornada é
temporário e não deve ser reutilizado como upstream autoritativo.

## Upstream stub controlado

O stub publica apenas `/get_s1` e `/get_s2`, com payloads determinísticos e sem
dados operacionais ou credenciais:

```powershell
services\twinops\.venv\Scripts\python.exe scripts\stub_forzy.py --host 127.0.0.1 --port 8765
```

Para uso pela Vercel, exponha-o somente por uma terminação HTTPS temporária e
autorizada ou inicie-o com `--certfile` e `--keyfile`. Cadastre a origem HTTPS
apenas no escopo Preview. O stub não implementa autenticação; encerre a
exposição assim que o E2E terminar. Não use esse fluxo como fallback de dados
na apresentação.

## Preview e E2E

Depois da autorização explícita para criar o preview:

```powershell
vercel deploy
$env:DEPLOYMENT_URL="https://<preview-autorizado>"
npm.cmd run test:e2e -- tests/e2e/deployed-real.spec.js
```

O primeiro teste é read-only: valida snapshot v2, ativo único, health,
manifesto, GLB e PNG. Para permitir o POST somente contra o stub controlado e
dentro da janela confirmada pelo backend. O manifesto exige JSON; GLB e PNG são
confirmados por GET, MIME e magic bytes:

```powershell
$env:TWINOPS_E2E_ALLOW_STUB_REFRESH="1"
npm.cmd run test:e2e -- tests/e2e/deployed-real.spec.js
```

Fora da janela de segunda a quarta, 12h–14h em `America/Sao_Paulo`, o teste de
refresh é pulado. Não altere o relógio ou a regra de negócio para fazê-lo
passar. Quando S1 e S2 retornam `stored`/`unchanged`, o E2E exige assessment
estruturado; `insufficient_data` é um resultado real válido, mas `null` não é.

O smoke padrão também é read-only:

```powershell
services\twinops\.venv\Scripts\python.exe scripts\verify_deployment.py --url $env:DEPLOYMENT_URL
```

Use `--allow-live-refresh` apenas com autorização para contatar o upstream
configurado. Mesmo com a flag, o script só envia POST após `/integration/health`
confirmar `state=active`. A saída contém apenas estágios e resultados
sanitizados.

## Roteiro de apresentação

1. Abra a página e confirme `Conjunto motor-bomba monitorado` e
   `TAG não fornecida`. Não apresente `MTR-BMB-042`, Área 01 ou ordens de
   serviço como fatos deste ativo.
2. Mostre S1 e S2. `Capturado pelo TwinOps às ...` é horário de recuperação;
   quando `timestampQuality=assumed_from_retrieval`, não é timestamp físico
   fornecido pelo sensor.
3. Explique os estados honestamente:
   - `received_now`: houve recuperação nesta janela;
   - `last_known`: continua visível a última leitura persistida;
   - `expected_idle`: a janela está fechada, não é prova de falha;
   - `unavailable`: nenhuma leitura real foi persistida.
4. Na avaliação, diga “desvio relativo ao histórico”. O score não é
   probabilidade de falha, RUL ou diagnóstico de componente. Flags de stale ou
   janela incompleta devem produzir dados insuficientes, nunca um normal
   sintético.
5. Mostre o gêmeo 3D e confirme manifesto, GLB e PNG. O PNG é apenas fallback
   visual; não substitui telemetry, avaliação ou validação do GLB.
6. Abra a saúde da integração. Exiba apenas status, latência, contagens e erros
   públicos; nunca payload raw, DSN ou hostname completo do upstream.

## Cotas e operação sem custo

Antes de cada apresentação, confira os painéis de uso do projeto Vercel Hobby
e do recurso Neon Free. Não confie em números copiados para este documento,
pois limites podem mudar. Confirme que não há upgrade, cobrança automática,
cron ou domínio pago. Hobby/Free é demonstrativo, sem SLA industrial.

No Windows, a Vercel CLI local pode falhar com `spawn cmd.exe ENOENT` mesmo com
`cmd.exe` presente. Isso é uma limitação do ambiente do builder local; use um
runner Vercel/Linux compatível ou corrija o PATH da sessão. Não commite preload
ou wrapper diagnóstico.

O build local de fechamento reportou 12 advisories no grafo npm existente (6
moderados, 5 altos e 1 crítico) e chunks Vite acima de 500 kB. Eles não foram
alterados neste plano; reavalie-os antes de qualquer promoção pública.

## Promoção e rollback

Somente depois de preview, E2E e smoke verdes, peça autorização explícita antes
de `vercel deploy --prod`. Registre a URL e o deployment anterior sem registrar
envs.

Para rollback, promova o deployment anterior pelo dashboard/CLI da Vercel e
rode novamente o smoke read-only. A migration 002 é aditiva e idempotente;
rollback de aplicação não autoriza apagar tabelas nem executar downgrade de
banco. Para encerrar o demonstrador, primeiro confirme que nenhum deployment
usa o Neon e só então desconecte a integração conforme `docs/deploy/neon.md`.
