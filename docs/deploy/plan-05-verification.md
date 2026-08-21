# Evidência de fechamento do plano 05

Data local: 2026-08-21. Branch: `luis/real-twinops-deploy`.

Este relatório cobre somente build e testes locais. Não houve deploy de preview
ou produção, push, nova migration Neon, leitura de env ou contato com upstream.

## TDD dos seis findings

- Env/origens/upload: RED com 20 falhas e 29 passes; GREEN focado com 77 passes.
  O contrato rejeita `sslmode` ausente/duplicado nos dois ordenamentos e com
  percent-encoding, valida origem HTTPS limpa e exclui metadata local do upload.
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
