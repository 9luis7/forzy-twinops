# Índice de execução paralela — Forzy TwinOps

## Contrato canônico v2

A fronteira de migração para o contrato canônico está em
[`contracts/v2/README.md`](../../../contracts/v2/README.md). Os JSON Schemas
em `contracts/v2/` são a autoridade do contrato: a documentação orienta a
migração, mas não altera nem flexibiliza a validação definida pelos schemas.

Durante a migração, `contracts/v1/` permanece preservado. Integrações que
ainda produzem v1 devem converter na fronteira antes de entregar v2. Para
Forzy live, a equivalência `observedAt = receivedAt` tem semântica assumida de
recuperação, nunca de horário real da medição, e exige
`timestampQuality: "assumed_from_retrieval"`.

## Base congelada

- Repositório: `https://github.com/9luis7/forzy-twinops`
- Branch: `main`
- SHA analisado: `1f21f264f88d7a64fecc37e3b3e620eb46d35587`
- TDD: [demonstrador preditivo](2026-08-12-forzy-twinops-demonstrador-preditivo-design.md)

O coordenador deve conferir se `main` avançou antes de criar worktrees. Cada
worker recebe uma branch/worktree própria e não reverte mudanças alheias.

## Sequência

### Gate 0 — coordenador

Executar [contratos e integração](work-packages/00-contratos-e-integracao.md),
com fixtures e adapters mínimos. Esse commit é a base comum dos workers.

### Onda paralela 1

1. [Aquisição, histórico e API](work-packages/01-aquisicao-dados-api.md)
2. [ML de anomalia e deterioração](work-packages/02-ml-anomalia-deterioracao.md)
3. [Frontend e twin 3D](work-packages/03-frontend-twin-3d.md)

Os três pacotes têm ownership não sobreposto. O worker de ML pode trabalhar com
o CSV e fixtures sem esperar a coleta live. O frontend usa fixtures do contrato
sem depender do backend pronto.

### Onda paralela 2

4. [Copiloto explicável](work-packages/04-copiloto-explicavel.md)

O copiloto pode começar em paralelo caso haja um quarto slot de worker. Com três
slots, entra na segunda onda para reduzir custo de coordenação.

### Gate final — coordenador

Executar [integração e verificação](work-packages/05-integracao-verificacao.md)
no SHA composto. Nenhum worker declara o projeto completo isoladamente.

## Prompt-base para cada worker

> Você é responsável exclusivamente pelo pacote indicado e pelos arquivos de
> ownership listados nele. Você não está sozinho no repositório: não reverta
> mudanças de outros workers e ajuste sua implementação aos contratos da base.
> Leia o TDD-mãe, o pacote 00 e sua spec completa antes de editar. Implemente,
> teste e relate arquivos alterados, comandos/resultados, desvios e riscos.
> Não amplie escopo, não altere schemas compartilhados e não faça deploy, compra
> de infraestrutura, envio de dados a LLM externo ou afirmação de falha sem gate
> do coordenador.

## Regras de coordenação

- Mudança em contrato ou `package.json`: solicitar ao coordenador.
- Descoberta que invalide premissa física ou estatística: parar o pacote e
  registrar evidência.
- Falha local do endpoint não bloqueia testes com stubs/fixtures.
- Dependência entre workers é resolvida pelo contrato, não por edição cruzada.
- Cada branch deve produzir commits pequenos e revisáveis.
- O merge só ocorre após revisão independente e suíte integrada.

