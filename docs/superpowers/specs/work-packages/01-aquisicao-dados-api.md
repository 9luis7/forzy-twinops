# Pacote 01 — Aquisição, histórico e API canônica

## Missão

Implementar a trilha de dados real sem tocar em frontend, ML ou copiloto.

## Ownership exclusivo sugerido

- `services/twinops/ingestion/**`
- `services/twinops/storage/**`
- `services/twinops/api/telemetry_routes.*`
- `services/twinops/tests/ingestion/**`
- migrations/schema do storage
- importador do CSV e comando do collector

Não editar `src/**`, módulos de scoring, prompt/LLM ou artefatos 3D.
Os schemas e fixtures em `services/twinops/contracts/**` pertencem ao
integrador do pacote 00 e são apenas consumidos por este worker.

## Comportamento

- Python 3.11+ e serviço HTTP modular; FastAPI é o default.
- SQLite em modo WAL no demonstrador, com interface de repositório que permita
  Postgres depois.
- Tabela append-only para amostras canônicas e registro separado de tentativas
  de coleta com erro.
- S1 e S2 consultados em paralelo; timeout padrão de 2 segundos e no máximo um
  retry curto com jitter.
- Polling padrão de 5 segundos, configurável por env.
- Janela padrão `America/Sao_Paulo`, seg/ter/qua, `[12:00, 14:00)`.
- Fora da janela: não gravar amostra live; health retorna `expected_idle`.
- Hostname upstream somente por env.
- Importação CSV é um job idempotente, separado do collector, usando o mesmo
  contrato com `source=forzy-csv`.

## Persistência mínima

Campos indexados: `reading_id`, `source`, `asset_tag`, `sensor_id`,
`scheduled_at`, `received_at`, `observed_at`, valores, semântica/unidades,
`quality_flags`, `payload_hash`, `raw`.

Índices mínimos:

- unique `(source, sensor_id, scheduled_at)` para live;
- `(asset_tag, sensor_id, received_at desc)` para histórico.

Não adicionar Redis, fila, TimescaleDB ou ORM se SQL parametrizado e migrations
simples satisfizerem os testes.

## Testes obrigatórios

- Adapters com `dados1`/`dados2`, casing e acentos exatos.
- Zero preservado; campo ausente/string/null/infinito rejeitado.
- Raw e hash preservados; `observedAt=null` para live.
- Agenda nas bordas: seg 11:59 off, 12:00 on; qua 13:59 on, 14:00 off;
  quinta off.
- Retry do mesmo slot não duplica.
- Timeout/500/JSON inválido em S1 não impede persistência válida de S2.
- Histórico ordenado, limitado e filtrado.
- URL upstream e stack trace não vazam nas respostas públicas.

## Critérios de aceite

- Durante a janela, amostra válida aparece na API em até dois ciclos de polling.
- Restart retoma no próximo slot sem inventar backfill.
- Ausência nunca é convertida em zero.
- Health expõe último intento, último sucesso, latência, erro sanitizado e
  contagem por sensor.
- Smoke real é separado dos testes determinísticos e pode ser desativado.
- CSV importado e live são consultáveis pelo mesmo endpoint sem perder a origem.

## Entrega do worker

Relatar schema aplicado, comandos de execução/teste, amostras importadas,
resultado do smoke opcional, arquivos alterados e qualquer desvio da spec. Não
publicar infraestrutura nem migrar para Postgres sem decisão do integrador.
