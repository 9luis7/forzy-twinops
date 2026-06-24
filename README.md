# Forzy TwinOps

Protótipo navegável de **Digital Twin** para manutenção preditiva de motores elétricos industriais.
Challenge FIAP × Forzy.

> Status: **protótipo navegável** (v0.3). App com sidebar e 4 cenas de demonstração — dados sintéticos, sem backend.
>
> **Novidades v0.3:** telemetria **ao vivo** determinística no motor-estrela (heartbeat 1/seg com
> Start/Pause/Reset/Trigger Incident), nível de **Componente** na hierarquia de TAGs
> (Motor → Componente → Sensor) e trilha de **procedência/auditoria** reforçada
> (traceId, inputHash, pipelineVersion, scoringModel, validação humana).

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
- **Dados:** mock total gerado a partir do schema Supabase (sem coleta real nesta fase)
- **Banco de referência:** Supabase (PostgreSQL) — tabelas `assets` e `readings`

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

## As 4 cenas da demo

1. **Visão da Planta** — KPIs + mapa macro das áreas (A Produção · B Utilidades · C Manutenção · D Expedição). Partimos do macro para o micro.
2. **Drill-down por TAG** — `PLT-FORZY-001 → AREA-PROD-01 → MTR-BMB-042 → CMP-BRG-042A → SNS-VIB-042B`. Perfil do ativo ("LinkedIn da máquina"): leituras, risco, **componentes**, sensores, documentos e OS vinculadas. O sensor de vibração está fisicamente ligado ao **rolamento** sob suspeita.
3. **Alertas + timeline** — alerta preditivo com **confiança 87%**, origem (`SNS-VIB-042B`) e base consultada; gráfico temporal com a degradação visível.
4. **Assistente técnico (copiloto)** — Q&A asset-aware: possíveis causas, ação recomendada e evidências rastreáveis.

### Caminho ensaiado
`Visão da Planta → Área de Produção → MTR-BMB-042 → Componentes → Telemetria ao vivo → Alerta → Evidências → Recomendação → Copiloto → Auditoria`

## Estrutura

```
forzy-twinops/
├── src/
│   ├── data/mock.js              # planta, áreas, ativos, sensores, leituras, alertas, OS, docs, risco, KPIs
│   ├── components/
│   │   ├── Sidebar.jsx           # navegação principal
│   │   ├── Breadcrumb.jsx        # trilha PLT → AREA → MTR
│   │   ├── TagTree.jsx           # árvore Planta → Área → Motor → Sensores
│   │   ├── AssetProfile.jsx      # perfil do ativo (cena 2)
│   │   ├── Copilot.jsx           # assistente técnico (cena 4)
│   │   ├── TimeChart.jsx         # série temporal (Recharts)
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

**Fora (evolução):** coleta real de sensor / API de produção · autenticação e permissões ·
ML funcional · RAG sobre documentos · visão computacional (leitura de placa).

> Teatro honesto: o caminho da demo é navegável e coerente; números de planta (128 ativos etc.)
> são sintéticos e alguns cards são ilustrativos. O objetivo é mostrar a **visão** e a lógica.

## Segurança

Chaves `service_role` do Supabase **não** vão para o repositório. O mock não contém credenciais.
Ver `.env.example`.
