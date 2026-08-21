# Task 5R1 report — mutation-proof read-only browser probe

## Resultado

O primeiro teste de `tests/e2e/deployed-real.spec.js` agora mantém a navegação
read-only mesmo quando a UI acredita estar dentro da janela Forzy. O comportamento
da aplicação, o scheduler, o teste explícito de refresh e a configuração de
deploy não foram alterados.

Base verificada: `3ab10fb51dc3cf112c57886fc04314997fcd1812`.

## RED → GREEN

- RED: um invariant check na base encontrou `page.goto` sem qualquer
  `page.route` e terminou com exit 1: `RED expected: first browser test
  navigates without an API mutation firewall`.
- GREEN: o mesmo tipo de check confirmou que rota e relógio precedem a
  navegação, que apenas `GET`/`HEAD`/`OPTIONS` continuam, que outras mutações
  são abortadas e que a contagem bloqueada é assertada.
- Mutação protegida: remover ou mover o firewall depois de `page.goto`, liberar
  outro método, remover o abort ou remover a asserção faz o invariant falhar;
  permitir que o `POST` saia volta a ser detectado pelo teste em browser.

## Implementação

- `page.route("**/api/**")` é instalado antes da primeira navegação.
- O relógio é instalado em `2026-08-12T15:30:00Z`, quarta-feira às 12:30 em
  `America/Sao_Paulo`, para exercitar de modo determinístico o auto-refresh.
- Métodos read-only continuam; qualquer outro método é abortado localmente com
  `blockedbyclient` e incrementa `blockedMutationAttempts`.
- `expect.poll` exige ao menos uma tentativa interceptada.
- O segundo teste não mudou e continua exigindo
  `TWINOPS_E2E_ALLOW_STUB_REFRESH=1` e `health.integration.state=active`.
- O runbook agora deixa explícito que somente o primeiro teste tem firewall e
  que o spec inteiro deixa de ser side-effect-free quando o segundo teste é
  habilitado.

## Evidência local sem rede

- `node --check tests/e2e/deployed-real.spec.js`: exit 0.
- `npm.cmd run test:e2e -- --list tests/e2e/deployed-real.spec.js`: 2 testes em
  1 arquivo.
- `npm.cmd run test:run -- --exclude "**/.pytest_cache/**"`: 15 arquivos,
  147 testes passados e 1 skip.
- `npm.cmd run build`: 1.440 módulos transformados, exit 0. O warning já
  conhecido de chunks acima de 500 kB permanece.

A primeira tentativa de Vitest terminou antes da coleta por `EPERM` ao varrer o
cache Python ignorado `services/twinops/.pytest_cache`. O rerun excluiu somente
esse tipo de cache via argumento de CLI; nenhum cache foi removido e nenhuma
configuração foi editada.

## Escopo e concern residual

Os únicos paths de entrega são o spec, o runbook, a evidência append-only, este
relatório e o brief da task. `.agents/` e `skills-lock.json` permaneceram
untracked e fora do stage. Não houve rede, deploy, push, merge, env, Vercel,
Neon, upstream, backend/frontend de produção ou Plan06.

Concern residual: por proibição explícita de rede, esta task não executou o spec
contra um deployment. No próximo preview autorizado, o smoke autenticado via
`vercel curl` permanece disponível sem desabilitar Preview Protection. Se a
proteção bloquear a navegação direta do Playwright, preserve-a e interrompa o
browser E2E até existir um mecanismo suportado de autenticação ou bypass para o
runner; não enfraqueça a proteção para fazer o teste passar. O relógio fixo da
página não muda o scheduler nem o gate mantido pelo backend.

## Follow-up da revisão independente

- Resultado da revisão em `78e70f2`: PASS, 0 Critical e 0 Important.
- RED textual: o check na base terminou com exit 1 ao encontrar simultaneamente
  a instrução ambígua sobre relógio e a afirmação incompleta sobre proteção.
- Minor 1: o runbook agora distingue o relógio browser-only do primeiro teste
  do relógio e do gate de negócio controlados pelo backend no segundo teste.
- Minor 2: o concern residual agora reconhece Preview Protection, mantém
  `vercel curl` como smoke autenticado e exige parar o browser E2E quando não
  houver autenticação/bypass suportado, sem desabilitar a proteção.
- GREEN textual: o check confirmou as duas distinções e a ausência das frases
  antigas; `node --check`, Playwright discovery com 2 testes e
  `git diff --check` também passaram sem rede.
