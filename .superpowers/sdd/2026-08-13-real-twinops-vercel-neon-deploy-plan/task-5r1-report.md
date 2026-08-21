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
contra um deployment. O próximo preview autorizado deve rodar o Playwright real
para provar a interceptação no browser implantado; nenhum bypass de proteção ou
mudança de scheduler é necessário para isso.
