# Pacote 03 — Fonte de dados frontend e twin 3D real

## Missão

Consumir `DigitalTwinSnapshot`, preservar o modo replay e substituir o desenho principal
por um GLB otimizado do conjunto real, mantendo o SVG como fallback.

## Pré-condição

O integrador entrega a interface `TwinDataSource`, o adapter de replay e as
fixtures do pacote 00. O worker não altera contratos compartilhados.

## Ownership exclusivo sugerido

- `src/components/Twin3D.jsx`
- `src/components/twin3d/**`
- `src/components/MotorMimic.jsx` como fallback
- ponto de integração do twin em `src/components/AssetProfile.jsx`
- `public/models/conjunto-motor-bomba.glb`
- `public/models/conjunto-motor-bomba.manifest.json`
- testes do twin 3D

Não editar Copilot, `LiveTwinContext`, mocks, `App.jsx`, contrato, backend ou
`package.json`. Dependência 3D é solicitada ao integrador; default recomendado:
Three.js via React Three Fiber apenas se o orçamento do bundle for aceitável.

## Comportamento

- Converter STEP para GLB offline; o navegador não carrega STEP/DWG.
- Otimizar geometria, materiais e tamanho sem alterar proporções.
- Manifesto mapeia nomes dos sólidos para `motor`, `bomba` e `base`.
- Telemetria não recarrega o modelo; apenas atualiza overlays/highlights.
- Estado e evidências vêm exclusivamente de `DigitalTwinSnapshot.assessment`.
- S1/S2 podem aparecer como marcadores “posição não validada”, visualmente
  distintos de sensores posicionados com confirmação.
- Métricas ausentes mostram `indisponível`; corrente/RPM não usam mock em live.
- `MotorMimic` permanece fallback de arquivo, WebGL e acessibilidade.
- Replay mantém iniciar, pausar, reset e próximo cenário. Live não exibe
  controles incompatíveis.

## Critérios de aceite

- Escala e orientação permanecem consistentes após reload.
- Manifesto resolve motor, bomba e base; nome desconhecido gera warning, nunca
  associação silenciosa.
- Destaque reage a `componentTag` somente quando essa associação existir.
- Nenhum texto afirma ponto/eixo de S1/S2.
- Normal, watch/alert, arquivo ausente e fallback SVG possuem teste visual/E2E.
- O mesmo snapshot produz status coerente em gráfico, badges, alertas e twin.
- Build passa e não contém hostname S1/S2.

## Fora do escopo

- FEA, animação física de vibração ou colisão.
- Modelar o sensor no CAD com posição inventada.
- Redesenhar navegação, sidebar ou design system.

## Entrega do worker

Relatar ferramenta/parâmetros de conversão, tamanho do GLB, nomes mapeados,
fallbacks testados, impacto de bundle/FPS e screenshots dos estados principais.

