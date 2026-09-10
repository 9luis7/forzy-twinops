# Forzy TwinOps

Protótipo navegável de **Digital Twin** para manutenção preditiva de motores elétricos industriais.
Challenge FIAP × Forzy.

> Status: **demonstrador preditivo em evolução**. O front preserva o replay
> determinístico, enquanto o backend já normaliza CSV/API, persiste telemetria,
> executa ML clássico com artefato verificado e fornece o contrato canônico ao
> copiloto. Parte dos cards legados ainda é ilustrativa.
>
> **Copiloto de replay e histórico:** Gemini recebe o contexto calculado no servidor
> e gera explicações de S1/S2, com fontes documentais quando pertinentes. O replay
> continua durante perguntas e análises de eventos. A interface distingue geração
> confirmada de contingência. [Configuração e verificação](docs/deploy/generative-copilot.md).
>
> **Novidades v0.4:** **loop de cenários ao vivo** no motor-estrela — a telemetria
> determinística (1/seg) cicla sozinha por `estável → falha → detecção → normalização`
> e percorre vários tipos de falha (superaquecimento, sobrecarga elétrica, desbalanceamento).
>
> Essa leitura ao vivo é a **fonte única da verdade de TODO o app** (`LiveTwinContext`):
> gauges, gêmeo ilustrativo (a hipótese do cenário acende), árvore de TAGs, cards, sinótico da planta,
> KPIs, central de alertas, copiloto e auditoria refletem o **mesmo estado, no mesmo instante**.
> O alerta do motor é dinâmico — aparece quando um cenário é detectado e some quando normaliza.
> O histórico curado (OS, documentos) permanece. Controles: Iniciar/Pausar · Reset · Próximo cenário.
>
> **v0.3:** nível de **Componente** na hierarquia de TAGs (Motor → Componente → Sensor) e
> trilha de **procedência/auditoria** reforçada (traceId, inputHash, pipelineVersion,
> scoringModel, validação humana).

---

## O problema

Plantas industriais carecem de uma camada de inteligência operacional onde cada ativo tem
identidade, histórico e uma trilha auditável de decisões. Hoje o conhecimento sobre o estado
de um motor fica disperso e só aparece **depois** da falha.

## A solução

Uma camada de inteligência operacional onde cada ativo tem **identidade por TAG**, seu histórico,
seus documentos, seus dados de sensores e uma trilha auditável de recomendações. O motor é o
primeiro caso prático — a janela para a fábrica inteira, não o limite da solução.

O coração do protótipo é o **ciclo de vida do dado**: mostrar o dado se transformando de leitura
de sensor até virar decisão, com origem rastreável.

## Arquitetura (ciclo de vida do dado)

```
[1] SENSOR     ESP32 + DHT22 / MPU6050 / potenciômetro lê o motor
      ↓ MQTT
[2] BROKER     HiveMQ recebe o payload raw (1 leitura/seg)
      ↓
[3] INGESTÃO   n8n valida + faz lookup + insere
      ↓
[4] SUPABASE   assets + readings
      ↓
[5] INTERFACE  navega TAG → leitura atual + gráfico temporal + ficha
      ↓
[6] DECISÃO    alerta + recomendação + procedência auditável
```

## Stack

- **Front-end:** React + Vite
- **Gráficos:** Recharts
- **Dados:** replay determinístico, histórico Forzy real e coleta server-side dos endpoints S1/S2
- **Backend:** FastAPI/Python com SQLite no demonstrador
- **ML:** baseline robusto causal, backtest walk-forward e artefatos com hashes externos

## Schema de referência

```sql
CREATE TABLE public.assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tag text NOT NULL UNIQUE,
  name text NOT NULL,
  motor_type text NOT NULL,
  sector text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.readings (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  asset_tag text NOT NULL REFERENCES public.assets(tag),
  ts timestamptz NOT NULL,
  temperature numeric NOT NULL,   -- °C
  current numeric NOT NULL,       -- A
  vibration numeric NOT NULL,     -- m/s²
  rotation integer,               -- RPM
  created_at timestamptz NOT NULL DEFAULT now()
);
```

## Rodando localmente

```bash
npm install
npm run dev
```

O backend pode ser instalado e validado separadamente:

```powershell
python -m venv services/twinops/.venv
services/twinops/.venv/Scripts/python -m pip install -e "services/twinops[dev]"
services/twinops/.venv/Scripts/python -m pytest services/twinops/tests
```

Com as variáveis `TWINOPS_*` configuradas, o histórico nativo pode ser
importado de forma idempotente:

```powershell
services/twinops/.venv/Scripts/python -m twinops.cli import-forzy-history data/raw/forzy-history-2026-05-19.csv
```

Para trocar o replay pelo snapshot canônico do backend no front, defina
`VITE_TWINOPS_DATA_MODE=live`. Se a API falhar, o contexto preserva o replay
como fallback explícito. O comando `python -m twinops.ml.real_history` imprime
os hashes de manifesto e modelo que devem ser copiados para as variáveis
`TWINOPS_ML_*`; o CSV industrial bruto permanece ignorado pelo Git.

O gate ponta a ponta cria uma base temporária a partir do CSV original, inicia
API e frontend locais e navega pelo modo canônico no Chrome:

```powershell
npm.cmd run test:e2e
```

Ele espera o arquivo `docs/History_32026-05-19T11-46-10-920.csv` localmente e
não acessa os endpoints externos da Forzy.

## As 4 cenas da demo

1. **Visão da Planta** — KPIs + mapa macro das áreas (A Produção · B Utilidades · C Manutenção · D Expedição). Partimos do macro para o micro.
2. **Drill-down por TAG** — `PLT-FORZY-001 → AREA-PROD-01 → MTR-BMB-042 → CMP-BRG-042A → SNS-VIB-042B`. Perfil do ativo ("LinkedIn da máquina"): leituras, risco, **componentes**, sensores, documentos e OS vinculadas. A associação do sensor ao rolamento é um cenário ilustrativo do replay; a montagem real de S1/S2 ainda precisa ser confirmada.
3. **Alertas + timeline** — fluxo de alerta, origem (`SNS-VIB-042B`) e base consultada; a confiança de 87% do cenário legado é ilustrativa e não representa probabilidade produzida pelo modelo real.
4. **Assistente técnico (copiloto)** — Q&A asset-aware: possíveis causas, ação recomendada e evidências rastreáveis.

### Caminho ensaiado
`Visão da Planta → Área de Produção → MTR-BMB-042 → Componentes → Telemetria ao vivo → Alerta → Evidências → Recomendação → Copiloto → Auditoria`

## Estrutura

```
forzy-twinops/
├── src/
│   ├── data/mock.js              # planta, áreas, ativos, sensores, leituras, alertas, OS, docs, risco, KPIs, cenários ao vivo
│   ├── useLiveTelemetry.js       # motor do loop de cenários ao vivo (1/seg, determinístico)
│   ├── LiveTwinContext.jsx       # provider global: fonte única do estado do motor-estrela
│   ├── components/
│   │   ├── Sidebar.jsx           # navegação principal
│   │   ├── Breadcrumb.jsx        # trilha PLT → AREA → MTR
│   │   ├── TagTree.jsx           # árvore Planta → Área → Motor → Sensores
│   │   ├── AssetProfile.jsx      # perfil do ativo (cena 2)
│   │   ├── Copilot.jsx           # assistente técnico (cena 4)
│   │   ├── TimeChart.jsx         # série temporal (Recharts) + barra do loop ao vivo
│   │   ├── Gauge.jsx             # medidor radial SCADA (SVG)
│   │   ├── MotorMimic.jsx        # gêmeo digital 2.5D do motor (SVG)
│   │   ├── DataPipeline.jsx      # as 6 etapas do ciclo de vida do dado
│   │   ├── Provenance.jsx        # procedência por leitura
│   │   └── ui.jsx                # badges / barra de confiança
│   ├── views/
│   │   ├── PlantOverview.jsx     # cena 1 — KPIs + mapa de áreas
│   │   ├── AssetsView.jsx        # cena 2 — drill-down por TAG
│   │   ├── AlertsView.jsx        # cena 3 — central de alertas
│   │   ├── OrdersView.jsx        # ordens de manutenção
│   │   ├── DocumentsView.jsx     # documentos técnicos
│   │   └── AuditView.jsx         # auditoria (pipeline + procedência)
│   └── App.jsx                   # shell + roteamento por estado
├── public/
├── README.md
└── package.json
```

## Escopo

**Dentro (demo):** sidebar + roteamento · visão macro da planta com KPIs · drill-down por TAG ·
perfil do ativo + gráfico temporal · alerta preditivo com confiança · assistente técnico (copiloto) ·
ordens de manutenção · documentos técnicos · auditoria/procedência do dado.

**Fora (evolução):** API de produção com URL estável/SLA · autenticação e permissões ·
rótulos de falha e validação longitudinal do ML · RAG sobre documentos · visão computacional (leitura de placa).

> Teatro honesto: o caminho da demo é navegável e coerente; números de planta (128 ativos etc.)
> são sintéticos e alguns cards são ilustrativos. O objetivo é mostrar a **visão** e a lógica.

## Segurança

Chaves `service_role` do Supabase **não** vão para o repositório. O mock não contém credenciais.
Ver `.env.example`.
