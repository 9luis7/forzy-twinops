# Evidência de fechamento do plano 05

Data local: 2026-08-21. Branch: `luis/real-twinops-deploy`.

Este relatório cobre somente build e testes locais. Não houve deploy de preview
ou produção, push, nova migration Neon, leitura de env ou contato com upstream.

> Nota histórica: a afirmação acima descreve o fechamento original da branch
> `luis/real-twinops-deploy`. A seção **Fechamento integrado do Preview** ao
> final deste documento registra e substitui o status de deploy depois da
> integração local com a trilha de dados reais.

## TDD dos seis findings

- Env/origens/upload: RED com 20 falhas e 29 passes; GREEN focado com 77 passes.
  O contrato rejeita `sslmode` ausente/duplicado nos dois ordenamentos e com
  percent-encoding, valida origem HTTPS limpa e exclui metadata local do upload.
- Self-review de delimitadores vazios: RED com 5 falhas; GREEN combinado com 82
  passes. Origens com `?`/`#` vazios e DSN com fragmento vazio também falham.
- Scorer/smokes: RED com 8 falhas e 33 passes; GREEN com 41 passes. Artefato ML
  configurado e inválido aborta startup com erro sanitizado. Refresh S1/S2
  bem-sucedido exige assessment estruturado, aceitando `insufficient_data`.
  GLB/PNG usam GET, MIME e magic bytes; manifesto exige JSON.
- Migration/cold start: RED com 7 falhas, 2 passes e 1 skip; GREEN com 9 passes e
  1 skip. O teste concorrente sem banco inicia duas threads, serializa no mesmo
  advisory lock e observa uma única execução do SQL exato.
- Exclusões finais: RED com 2 falhas; GREEN com os 7 testes do entrypoint. O
  `excludeFiles` final tem 213 caracteres, abaixo do limite Vercel de 256.

## Gates amplos

- Python: `338 passed, 2 skipped` em 50,74 s. Os skips são integrações que
  requerem `TEST_DATABASE_URL`; esse banco não foi configurado nem acessado.
- Vitest: 15 arquivos, `147 passed, 1 skipped`.
- Playwright discovery: 2 testes no smoke de deploy.
- Vite: build verde com 1.440 módulos.
- Vercel CLI 59.3.0: `vercel build --target=preview` verde, Python 3.12, sem
  Large Functions e sem deploy. O Windows exigiu um preload temporário que
  apenas resolveu `cmd.exe` e PATH; ele não integra o bundle nem o Git.

## Trace do bundle

A Function tem 4.862 entradas e 135,264 MiB. Cada item requerido aparece uma
vez: entrypoint, source TwinOps, migration 002 e os cinco arquivos ML fixados.
Manifesto 3D, GLB e PNG aparecem uma vez no output estático.

Arquivos controlados pelo repositório ausentes da Function: env, `.agents`,
`skills-lock.json`, `.superpowers`, testes do projeto, docs, notebooks, data,
`source-summary.json`, SciPy, scikit-learn e o preload temporário.

Concern residual: o builder Python adiciona 1.594 arquivos sob `test/tests` de
wheels e 7 documentos `.agents` distribuídos pelo FastAPI. `excludeFiles` é
aplicado antes dessa vendorização e não os remove. Não foi criado postinstall
nem refatorado o grafo de dependências para maquiar metadata upstream.

## Warnings não tratados

- `npm install` reportou 12 advisories existentes: 6 moderados, 5 altos e 1
  crítico. Não houve `npm audit fix`, pois isso ampliaria o escopo e poderia
  introduzir breaking changes.
- Vite reportou chunks acima de 500 kB. O build permaneceu verde; otimização de
  bundle frontend não pertence a este plano.

## Finding pós-fechamento 5R1 — firewall do probe read-only

- Classificação: Important. O primeiro teste Playwright era descrito como
  read-only, mas `page.goto("/")` podia acionar o auto-refresh legítimo da UI e
  emitir `POST` quando o relógio do browser estivesse na janela Forzy.
- RED na base `3ab10fb`: o invariant check terminou com exit 1 porque havia
  navegação sem `page.route` protegendo `/api/**`.
- Fix: antes da navegação, o teste instala um firewall que continua somente
  `GET`, `HEAD` e `OPTIONS`, aborta os demais métodos com `blockedbyclient`, fixa
  o relógio em quarta-feira, 12:30 de São Paulo, e exige pelo menos uma mutação
  interceptada. Os `GET` via `request` e todas as asserções de UI/assets foram
  preservados; o segundo teste continua sendo o único caminho autorizado a
  emitir `POST` e mantém seus dois gates explícitos.
- GREEN local: invariant check verde; `node --check` verde; Playwright discovery
  listou 2 testes; Vitest passou 147 testes com 1 skip; Vite transformou 1.440
  módulos e concluiu o build. A primeira varredura Vitest foi impedida pelo ACL
  de `services/twinops/.pytest_cache`; a repetição excluiu apenas caches
  `.pytest_cache` pela CLI, sem alterar configuração ou apagar dados.
- Não houve deploy, chamada remota, leitura/mutação de env, acesso ao Neon nem
  contato com upstream. A execução browser completa permanece para o preview
  autorizado, pois esta correção foi deliberadamente validada sem rede.

## Fechamento integrado do Preview

Data local: 2026-08-21. Branch: `luis/real-twinops-integration`. O build final
foi produzido em worktree limpo e destacado no SHA
`7e70b964d880b6469fcb0ecc7f5cb90d63263465`. Não houve push nem deploy de
produção.

### Runtime reproduzível

- `requirements.in` declara somente as oito dependências diretas do runtime de
  deploy. `requirements.txt` fixa 25 distribuições transitivas com 338 hashes
  SHA-256 para Python 3.12, Linux x86_64 e somente wheels binários.
- Uma segunda compilação do lock produziu os mesmos 30.227 bytes e SHA-256
  `135266337aedae8f8f4892ffaa6e2c5ab89af1ee9a2946fef18221e9166f0e51`.
- O contrato automatizado vincula nomes e intervalos PEP 508 do input aos pins,
  exige hash por distribuição e rejeita SciPy, scikit-learn, `sklearn` e
  `rarfile` também quando transitivos. `joblib` passou a ser dependência direta
  do pacote TwinOps.
- REDs reproduzidos: input ausente no lock, pacote sem hash mascarado por outros
  hashes, plataforma incorreta, dependência transitiva proibida e pins abaixo ou
  acima dos limites. GREEN focado final: 13 testes. Suíte Python integrada:
  `655 passed, 7 skipped, 2 warnings`. Revisão independente do SHA final:
  `PASS`, 0 Critical, 0 Important e 0 Minor.

### Build e trace finais

- `vercel build --target=preview` concluiu em Python 3.12. O `filePathMap` da
  Function tem 4.852 entradas, zero caminho físico ausente e 140.311.707 bytes
  (133,812 MiB). O output estático tem 8 arquivos e 1.683.944 bytes
  (1,606 MiB).
- Entrypoint, source TwinOps, migration 002 e os cinco artefatos ML fixados
  aparecem no bundle. Não aparecem `dist`, env, testes do projeto, docs, data,
  `.agents` do repositório, `.superpowers`, `skills-lock.json`, caches pytest,
  preload temporário, SciPy, scikit-learn ou `rarfile`.
- O Windows manteve um `.pytest_cache` local com ACL ilegível. O build final não
  reutilizou esse diretório: foi executado em worktree limpo do SHA exato. A
  regra versionada também ignora tanto a pasta `**/.pytest_cache` quanto seu
  conteúdo.

### Preview publicado e probes autenticados

- Deployment: `dpl_A2NSCgsKssFmLPYp9pNNSRk2WUzW`.
- URL: `https://forzy-twinops-bwspxzckq-9luis7s-projects.vercel.app`.
- Inspector:
  `https://vercel.com/9luis7s-projects/forzy-twinops/A2NSCgsKssFmLPYp9pNNSRk2WUzW`.
- A inspeção final retornou target `preview` e status `Ready`. Preview
  Protection permaneceu ativa; não foi criado bypass nem promovido alias de
  produção.
- Probes via `vercel curl`, todos com método GET: HTML raiz 200 com mount e JS
  versionado; health 200/JSON com estado `expected_idle` e sensores `s1`/`s2`;
  snapshot 200/JSON, schema 2.0, ativo `forzy-motor-01` e canais `s1`/`s2`;
  manifesto 200/JSON; GLB 206 `model/gltf-binary` com magic `glTF`; PNG 206
  `image/png` com assinatura `89504e470d0a1a0a`.
- O snapshot não tinha assessment, coerente com a janela de coleta fechada na
  sexta-feira. Nenhum POST ou refresh foi executado. O fluxo completo
  Preview -> Forzy -> Neon -> ML permanece condicionado à próxima janela
  operacional, segunda-feira 2026-08-24 entre 12:00 e 14:00 BRT.

### Fronteira Forzy e produção

- Os endpoints temporários `/get_s1` e `/get_s2` responderam 200 e foram aceitos
  pelo adaptador v2 para os sensores correspondentes. Como não fornecem
  timestamp de origem, a qualidade temporal permanece
  `assumed_from_retrieval`.
- Preflights CORS responderam 405 sem `Access-Control-Allow-Origin`; o desenho
  continua corretamente backend -> Forzy, nunca browser -> túnel.
- Development e Preview tinham os cinco nomes de ambiente exigidos. Produção
  permaneceu sem `TWINOPS_UPSTREAM_BASE_URL`. Nenhum valor secreto foi impresso
  ou persistido neste relatório.
- A promoção para produção continua sendo um gate separado e não autorizado.
