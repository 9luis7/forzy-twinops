# Laboratório de datasets públicos de rolamentos

Esta árvore é uma fronteira científica separada do artefato operacional
`artifacts/ml/real-forzy`. Nenhum resultado daqui substitui automaticamente o
baseline Forzy nem aparece na interface operacional.

## Fontes e termos

| Dataset | Fonte numérica primária | Termos/licença antes do download | Uso nesta entrega |
| --- | --- | --- | --- |
| XJTU-SY | [Página mantida pelos autores](https://biaowang.tech/xjtu-sy-bearing-datasets/) | A página fornece citação e links de download; não declara uma licença de software/dados inequívoca. Confirmar os termos da fonte no momento do acesso. | Obrigatório quando a fonte estiver acessível e autorizada. |
| NASA IMS | [NASA Open Data Portal](https://data.nasa.gov/dataset/ims-bearings) | Dataset governamental dos EUA; confirmar os termos exibidos pelo portal e a proveniência do arquivo antes do uso. | Obrigatório quando a fonte estiver acessível e autorizada. |
| PRONOSTIA/FEMTO-ST | [FEMTO-ST — IEEE PHM 2012](https://publiweb.femto-st.fr/tntnet/entries/1528/documents/author/data) | Confirmar os termos exibidos pela fonte original antes do download. | Condicional à acessibilidade da fonte original. |
| Paderborn | [KAt Bearing Data Center](https://mb.uni-paderborn.de/en/kat/research/bearing-datacenter/data-sets-and-download) | **CC BY-NC 4.0**; uso somente após aceite explícito da restrição não comercial. | Fora desta primeira execução. |
| CWRU | [Case Western Reserve University Bearing Data Center](https://engineering.case.edu/bearingdatacenter/welcome) | Confirmar os termos da página de origem. | Sanity check opcional; falhas artificiais. |

Imagens, espectrogramas prontos e derivações hospedadas no Hugging Face não
substituem o sinal numérico original. O manifesto versionado deve registrar
URL de landing page, URL exata de download, citação, licença/termos, SHA-256 e
data de acesso. Um hash só pode ser preenchido depois de baixar e verificar o
arquivo efetivamente usado.

## Layout local ignorado

Downloads e extrações grandes nunca entram no Git:

```text
data/public/
  xjtu-sy/downloads/
  xjtu-sy/raw/
  nasa-ims/downloads/
  nasa-ims/raw/
  pronostia/raw/
```

Cada adapter produz `SignalWindow` sem concatenar os brutos. As unidades da
fonte são preservadas e qualquer conversão precisa ser explícita e documentada.
Os splits são feitos por `bearing_id`, e toda alegação de transferência exige
validação entre bancadas.

## Cadeia de proveniência obrigatória

O manifesto `sources.json` usa `schemaVersion: 2`. Uma fonte só atravessa o
gate quando tem status `approved_for_research`, URLs HTTPS exatas, citação,
termos/licença, data de acesso RFC 3339 e hashes SHA-256 independentes do
archive e da metadata curada. O archive é inspecionado antes da escrita e
extraído em destino vazio; traversal, caminhos absolutos, symlinks, colisões e
overwrite são rejeitados. O manifesto final liga a fonte ao hash do archive,
ao inventário SHA-256 de cada raw extraído e ao hash/schema/id da metadata.

A metadata `schemaVersion: 1` é deliberadamente explícita: `files` mapeia cada
`relativePath` do inventário, `bearingId`/`runId`, `sequenceIndex`,
`timestampQuality`/`startedAt`, estado daquela janela e colunas/canais para
eixos. Unidade e frequência de amostragem vêm da metadata hash-pinned. Nomes de
pastas, filenames, posição implícita de coluna e timestamps aparentes nunca são
usados como fallback. `terminalFailureMode` descreve apenas o desfecho do
rolamento; não substitui `windowStateLabel`.

## Políticas experimentais e retomada

`experimentConfig` versiona duas decisões auditáveis:

- `featurePolicy` seleciona um eixo e só libera RMS/temperatura na vista
  Forzy-compatible quando a semântica foi confirmada; caso contrário a feature
  fica marcada como `unconfirmed_semantics` e fora dessa vista;
- `labelMapping` converte estados de janela para labels canônicos ou os exclui
  explicitamente, com cobertura de janelas, bearings e labels no relatório.

Os arquivos versionados em `artifacts/ml-public` são placeholders honestos com
status `not_run_external_data_gate` e métricas nulas. Fixtures sintéticas
provam o pipeline apenas em diretórios temporários e nunca são publicadas como
resultado científico. Quando archives reais autorizados e metadata auditada
existirem, use `--dry-run` para o preflight e `--overwrite` para substituir
explicitamente apenas os dois JSON conhecidos do laboratório. Nada neste fluxo
promove ou altera `artifacts/ml/real-forzy`.
