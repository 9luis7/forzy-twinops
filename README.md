# Forzy TwinOps

Fatia vertical de um **Digital Twin para manutenção preditiva de motores
elétricos**, construída para o Challenge FIAP × Forzy.

**Demonstração pública:**
[forzy-twinops.vercel.app](https://forzy-twinops.vercel.app/)

> Estado da demonstração em 26 de agosto de 2026: histórico real ativado,
> avaliações históricas materializadas e console de decisão publicado. Este é
> um recorte demonstrável do produto, não a declaração de conclusão de todas as
> fases planejadas.

## O que entregamos

O demonstrador mantém dois trilhos reais, unidos pela mesma API e pelo mesmo
console de decisão:

```text
leituras S1/S2 disponibilizadas pela Forzy
      ├─ arquivo histórico → lote imutável → robust-baseline 1.0.1
      │                    → scores causais persistidos
      └─ API operacional   → coleta e persistência idempotentes
                           → coletas recentes sem score inventado
                                      ↓
             API canônica + gráfico + contexto do ponto
                                      ↓
             confirmação ou rejeição humana antes da ação
```

A aplicação integra React e Vite no front-end, FastAPI no backend e PostgreSQL
no ambiente publicado. O front-end consome somente rotas de mesma origem em
`/api/v2`; credenciais, DSN e payloads brutos não são enviados ao navegador.

## Evidência disponível para a apresentação

O lote histórico ativo validado em produção em 26 de agosto de 2026 contém:

| Evidência | Quantidade | Interpretação |
| --- | ---: | --- |
| Leituras históricas canônicas | 14.366 | 7.183 leituras de S1 e 7.183 de S2 |
| Ciclos operacionais | 204 | Séries separadas por interrupções maiores que 15 s |
| Avaliações persistidas | 4.209 | Resultado causal e imutável do lote histórico ativo |
| Avaliações candidatas | 1.968 | Desvios que exigem confirmação ou rejeição humana |
| Violações de âncora ou episódio | 0 | Invariantes causais verificadas na materialização |

Uma segunda execução da materialização inseriu zero registros e preservou as
4.209 avaliações existentes. Esse no-op comprova idempotência; não representa
um novo treinamento.

## Modelo e semântica dos scores

O `robust-baseline 1.0.1` usa o conjunto `curated-features.csv`, com 14.366
amostras distribuídas em 204 ciclos. Ele combina quatro atributos causais:

- `velocity_ewma`;
- `velocity_slope`;
- `velocity_change_point`;
- `temperature_deviation`.

O artefato registra que o modelo foi treinado até
`2026-05-19T17:40:14.229Z`. Na avaliação walk-forward, cada corte causal de
treinamento termina antes do ponto que ele avalia.

Os resultados medem **anomalia relativa** e **deterioração relativa** contra o
baseline histórico. A escala 0–100 serve para priorizar inspeção dentro desse
contexto.

Os scores **não são**:

- probabilidade de falha;
- confiança calibrada;
- vida útil remanescente (RUL);
- diagnóstico de causa ou componente;
- falha confirmada.

O conjunto não contém rótulos de falha confirmada. Por isso,
`candidate_not_ground_truth` significa somente **candidato não confirmado**.
O ciclo correto de evolução é:

```text
candidato → confirmação/rejeição humana → evento rotulado
          → novo treinamento/backtest → nova versão → ativação explícita
```

Não existe aprendizado online automático nesta versão.

## Como ler o console

### Histórico avaliado

É o caminho principal da demonstração. Mostra o lote histórico ativo, a
telemetria S1/S2 e os scores persistidos no mesmo eixo temporal. O gráfico usa
pontos representativos para manter a interação fluida; os totais exibidos na
interface informam quantas leituras originais sustentam o recorte.

Selecione um ponto para abrir o inspetor lateral. O contexto preserva a leitura
original, o sensor, o horário, a origem, o status, a versão do modelo, o corte
causal de treinamento e os identificadores de proveniência disponíveis.

### Coletas recentes

Mostra somente leituras recuperadas da API e persistidas. As linhas oferecem
uma ligação visual entre pontos reais do mesmo sensor e dia de coleta; elas não
criam novos pontos, não unem dias diferentes e não provam coleta contínua nos
intervalos entre observações.

O upstream não fornece um timestamp físico de aquisição. O TwinOps registra o
horário de recuperação como `receivedAt` e declara essa qualidade temporal na
evidência, em vez de apresentá-la como horário medido pelo sensor.

As coletas recentes ainda não têm scores materializados. A cadência e a
cobertura S1/S2 persistidas não satisfazem o gate de atributos do modelo atual:
no mínimo três pontos, janela causal de 60 s, intervalo máximo de 15 s e
frescor máximo de 30 s. A interface mostra “indisponível” em vez de inferir um
score ou preencher o valor com zero.

### Visão completa

Combina o lote histórico e as coletas recentes no tempo civil. Os intervalos
longos sem coleta permanecem vazios de propósito. Use esta visão para provar a
separação entre fontes e a ausência de continuidade inventada; para analisar
uma tendência durante a apresentação, volte a **Histórico avaliado**.

### Controles do gráfico

- Arraste horizontalmente para navegar.
- Use `Ctrl` + roda do mouse ou trackpad para aplicar zoom no gráfico sem
  competir com o scroll da página.
- Use **Reenquadrar** para restaurar a janela inicial.
- Ative ou oculte S1 e S2 pelos controles acima do gráfico.
- Selecione um ponto para sincronizar o gráfico, os scores e o inspetor.

## O que a interface prova

- O histórico original chega à aplicação como lote imutável e identificável.
- O modelo e cada avaliação permanecem ligados a versão, configuração,
  manifesto, relatório e hashes de origem.
- A API entrega telemetria, avaliações e contexto ao front-end sem usar dados
  sintéticos como fallback.
- O usuário navega da tendência agregada até a evidência do ponto original.
- Lacunas, canal ausente e score indisponível continuam explícitos.
- Candidatos permanecem separados de falhas confirmadas e exigem revisão
  humana.

O demonstrador não comprova SLA industrial, captura contínua garantida,
probabilidade de falha, RUL, diagnóstico automático ou eficácia em falhas reais
rotuladas.

## Roteiro de demonstração em 5 minutos

1. **0:00–0:30 — Abra o produto.** Acesse a URL pública e apresente o objetivo:
   transformar telemetria real em evidência rastreável para priorizar uma
   inspeção humana.
2. **0:30–1:30 — Mostre o histórico.** Entre em **Histórico avaliado** e destaque
   as 14.366 leituras, os 204 ciclos e a separação entre S1 e S2.
3. **1:30–3:00 — Demonstre a decisão.** Navegue e aplique zoom, selecione um
   candidato e mostre no inspetor o valor original, o score relativo, a versão
   do modelo e a procedência. Diga explicitamente: “candidato não confirmado;
   não é probabilidade de falha”.
4. **3:00–4:00 — Mostre o dado novo.** Abra **Coletas recentes**. Explique que os
   pontos vieram da API, foram persistidos e não receberam score porque o gate
   causal não foi satisfeito. Isso prova que o sistema não inventa evidência.
5. **4:00–5:00 — Feche o ciclo.** Abra **Visão completa** brevemente para mostrar
   os intervalos sem coleta. Termine com o fluxo humano: candidato, validação,
   rótulo, novo treinamento, backtest, nova versão e ativação controlada.

Para reduzir risco durante a apresentação, abra a URL alguns minutos antes,
faça um refresh e deixe **Histórico avaliado** selecionado. Não comece pela
**Visão completa**, pois ela preserva deliberadamente os grandes intervalos sem
coleta.

## Executar e validar localmente

### Front-end

```powershell
npm install
npm run dev
```

O front-end usa a API de mesma origem. Sem um backend local configurado, o shell
abre, mas os dados reais ficam indisponíveis.

Execute os testes e o build de produção:

```powershell
npm run test:run
npm run build
```

### Backend

Crie o ambiente Python e instale as dependências:

```powershell
python -m venv services/twinops/.venv
.\services\twinops\.venv\Scripts\python.exe -m pip install -e "services/twinops[dev]"
.\services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests
```

O backend publicado depende das variáveis server-side descritas em
`.env.example`. Nunca use o prefixo `VITE_` para banco, upstream ou hashes ML,
pois variáveis Vite podem entrar no bundle do navegador.

O smoke read-only do deployment é:

```powershell
$env:DEPLOYMENT_URL="https://forzy-twinops.vercel.app"
.\services\twinops\.venv\Scripts\python.exe scripts\verify_deployment.py `
  --url $env:DEPLOYMENT_URL
```

O teste ponta a ponta local requer o arquivo histórico original fora do Git:

```powershell
npm run test:e2e
```

O CSV industrial bruto, bancos locais, resultados administrativos, variáveis de
ambiente e credenciais permanecem fora do repositório e dos logs públicos.

## Proveniência e gates operacionais

Cada lote e avaliação preserva os vínculos necessários para reprodução:

- identidade do ativo e do lote;
- hash da fonte e do manifesto histórico;
- família, versão e hash do modelo;
- hashes da configuração, dos atributos e do relatório;
- hash do manifesto de avaliações;
- janela de treinamento, janela avaliada, âncora temporal e sensor.

Os gates continuam separados mesmo após esta demonstração:

1. executar migration;
2. importar ou preparar um novo lote imutável;
3. materializar avaliações;
4. ativar o lote;
5. publicar ou promover um deployment.

Uma autorização para um gate não autoriza os seguintes. Rollback de aplicação
também não autoriza apagar histórico, avaliações ou tabelas.

## Estrutura principal

```text
api/                         entrada ASGI para o ambiente Vercel
artifacts/ml/real-forzy/     artefato, configuração e evidência do modelo
contracts/                   contratos JSON versionados
services/twinops/            API, ingestão, persistência, ML e testes Python
src/components/timeline/     console, gráficos, scores e inspetor de decisão
src/dataSources/             cliente same-origin da API v2
tests/e2e/                   validação ponta a ponta
docs/deploy/                 runbooks de publicação e verificação
```

## Segurança

- Não versione `.env`, DSN, credenciais ou payloads brutos.
- Valide os hashes externos antes de carregar `pipeline.joblib`.
- Trate o ambiente publicado como demonstrador, sem SLA industrial.
- Use somente endpoints sanitizados para saúde e observabilidade.
- Exija validação humana antes de converter um candidato em ação operacional.
