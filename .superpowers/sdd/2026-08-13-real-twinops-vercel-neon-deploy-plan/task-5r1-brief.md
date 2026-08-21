# Task 5R1: Make the deployed read-only browser probe mutation-proof

## Objective

Close the newly discovered operational gap in the deployed Playwright smoke: its
first test is documented as read-only, but `page.goto("/")` lets the production UI
auto-POST refresh whenever the browser clock is inside the Forzy window. Make that
test browser-level read-only under every clock without changing application behavior,
backend scheduling, the explicit refresh test, or deployment configuration.

## Base and ownership

- Worktree: `C:/Users/Luis/Documents/ChatGPT/forzy twinops/.worktrees/real-twinops-deploy`
- Required base: `3ab10fb51dc3cf112c57886fc04314997fcd1812`
- Owned files:
  - `tests/e2e/deployed-real.spec.js`
  - `docs/deploy/demo-runbook.md`
  - `docs/deploy/plan-05-verification.md` (append-only finding/fix evidence)
  - `.superpowers/sdd/2026-08-13-real-twinops-vercel-neon-deploy-plan/task-5r1-report.md`
  - this brief (force-add because `.superpowers/` is ignored)
- No-touch: production React/backend, Vercel config, envs, `.vercel`, Neon, upstream,
  Plan06, `.agents/`, and `skills-lock.json`.
- You are not alone in the repo. Preserve the existing two untracked marketplace
  files/directories and never stage or modify them.

## Reproduction and ruling

- `TwinOpsContext` intentionally auto-refreshes on mount when visible and the browser
  clock is Monday-Wednesday 12:00-14:00 `America/Sao_Paulo`.
- Therefore the first deployed Playwright test can contact the configured upstream
  and write Neon despite the runbook calling it read-only.
- This is an Important test/runbook safety defect, not an application defect.
- Fix only the test boundary. Do not disable or weaken the production scheduler.

## Required behavior

1. Before the first test calls `page.goto`, install a page route for `**/api/**`.
2. Continue only `GET`, `HEAD`, and `OPTIONS`; abort every other method with a
   browser-local reason such as `blockedbyclient`.
3. Force the page clock to a known open-window instant, e.g.
   `2026-08-12T15:30:00Z` (12:30 Sao Paulo), so the test exercises the mutation path
   rather than relying on today's weekday.
4. Count blocked mutation attempts and assert that at least one was intercepted.
   This proves the UI tried its intended active-window refresh while zero POST left
   the browser.
5. Preserve the independent Playwright `request` GETs, snapshot/UI assertions,
   health, manifest, GLB and PNG checks.
6. Leave the second test as the only path allowed to issue POST. It must still require
   `TWINOPS_E2E_ALLOW_STUB_REFRESH=1` and backend `health.integration.state=active`.
7. Correct the runbook: the first test enforces a browser mutation firewall even in
   an open window; the second test owns authorized POST. Do not claim the whole spec
   is side-effect-free when the explicit flag is set.

## Verification

- Establish RED on the base by a lightweight source/invariant check proving the first
  test has `page.goto` but no mutation route guard.
- After GREEN, run:
  - `npm.cmd run test:e2e -- --list tests/e2e/deployed-real.spec.js`
  - Vitest/full frontend regression and Vite build if available without network.
  - a syntax/import check of the spec.
- Do not deploy or contact any remote endpoint in this task.
- `git diff --check`; verify no changes to env/Vercel/production/Plan06 and neither
  untracked marketplace path is staged.

## Delivery

- Create one atomic commit: `test: make preview read-only probe mutation-proof`.
- Return RED/GREEN evidence, SHA, exact changed files and any residual concern.
- No push, merge, deploy, env mutation, Neon call, or upstream call.
