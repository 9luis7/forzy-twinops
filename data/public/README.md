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
  xjtu-sy/prepared/
  nasa-ims/downloads/
  nasa-ims/raw/
  nasa-ims/prepared/
  pronostia/raw/
```

Para inspecionar RAR3/RAR5, ative o venv isolado e, na raiz do repositório,
instale o extra com `python -m pip install -e "services/twinops[research]"`.
A extração também exige um executável 7-Zip confiável informado explicitamente
ao helper; ele é chamado sem shell e transmite um membro validado por vez para
um arquivo criado pelo Python. O smoke real opcional usa
`TWINOPS_NASA_RAR_PATH`; sem essa variável, o teste é ignorado explicitamente.

Para a preparação XJTU-SY, as seis partes RAR5 oficiais são inspecionadas
juntas antes de qualquer escrita e extraídas como um único conjunto. Uma
geração imutável tem o seguinte layout:

```text
xjtu-sy/prepared/<generation-id>/
  attestation.json
  metadata.json
  raw/XJTU-SY_Bearing_Datasets/
    Introduction_to_XJTU-SY_Bearing_Dataset.pdf
    <condition>/<bearing>/<sequence>.csv
```

O gate exige exatamente 9.216 CSVs e o PDF de origem, as 15 sequências
contíguas publicadas pelos autores e, em cada CSV, o header ASCII ordenado
`Horizontal_vibration_signals,Vertical_vibration_signals` seguido de 32.768
amostras com duas colunas numéricas finitas. O header não conta como amostra;
ele mapeia para os eixos `horizontal` e `vertical`. A amostragem é 25.600 Hz e
a cadência observacional é um minuto. A unidade numérica de aceleração,
timestamps/timezone, estado/onset/severidade por janela, vida física,
`lifeFraction` e RUL continuam desconhecidos. Carga radial aparece somente
como evidência de condição com unidade `kN`; nunca no campo float sem unidade.
Desfechos ficam como evidência terminal do bearing, inclusive os compostos, e
não viram label de todas as janelas. Métricas confirmatórias, supervisionadas,
de transferência e de RUL permanecem fechadas. O smoke 2R3 read-only requer
simultaneamente `TWINOPS_XJTU_RAR_DIRECTORY` e `TWINOPS_TRUSTED_7Z_PATH`; sem
ambos ele é ignorado e nenhum destino é criado. O smoke opcional de conteúdo
aceita apenas `TWINOPS_XJTU_SAMPLE_CSV_COPY`, apontando para uma cópia de um
CSV oficial fora de qualquer staging preparada, e também não escreve dados.

Para a preparação NASA IMS em camadas, `raw/IMS/` preserva o ZIP já
expandido, os três RARs internos e o PDF oficial sem modificação. Runs 1 e 2
são publicados juntos, nunca parcialmente, em uma geração imutável:

```text
nasa-ims/prepared/<generation-id>/
  attestation.json
  run-1/raw/1st_test/<source-timestamp>
  run-1/metadata.json
  run-2/raw/2nd_test/<source-timestamp>
  run-2/metadata.json
```

O terceiro RAR é somente inspecionado. Ele não é extraído nem recebe uma
árvore `run-3`: o prefixo documentado de 4.448 arquivos e a extensão não
documentada de 1.876 arquivos permanecem unidos em uma attestation de
quarentena e fora de métricas confirmatórias, supervisionadas e de RUL. O
smoke 2R2 read-only exige simultaneamente `TWINOPS_NASA_RAR_DIRECTORY` (a
pasta explicitamente autorizada com os três RARs) e
`TWINOPS_TRUSTED_7Z_PATH`; sem ambos ele é ignorado e nenhum caminho é
procurado no disco.

Mesmo depois da preparação, a unidade numérica de aceleração, o timezone, os
eixos físicos, o estado/fault onset/severidade de cada janela, `lifeFraction`
e RUL continuam desconhecidos. Os canais são apenas `source-channel-1/2`;
RPM e carga pertencem ao contexto da bancada, e os desfechos terminais ficam
em evidência de run/bearing fora dos labels. O conflito de descrição do
bearing 4 no run 1 é preservado como duas observações com proveniências
distintas, nunca colapsado em uma classe exclusiva. O `sourceRef`
`nasa-ims-internal-readme-cf46d37c` identifica
`IMS/Readme Document for IMS Bearing Data.pdf` (SHA-256
`cf46d37c21f7f292c11bbbdd4695d876c417ed1d6425e3d87c962ae2182ae6ed`);
`qiu-et-al-jsv-2006` identifica Qiu et al., *Journal of Sound and Vibration*,
DOI `10.1016/j.jsv.2005.03.007`.

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
