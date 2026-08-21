# Laboratório de datasets públicos de rolamentos

Esta árvore é uma fronteira científica separada do artefato operacional
`artifacts/ml/real-forzy`. Nenhum resultado daqui substitui automaticamente o
baseline Forzy nem aparece na interface operacional.

## Fontes e termos

| Dataset | Fonte numérica primária | Termos/licença antes do download | Uso nesta entrega |
| --- | --- | --- | --- |
| XJTU-SY | [Página mantida pelos autores](https://biaowang.tech/xjtu-sy-bearing-datasets/) | A página fornece citação e links de download; não declara uma licença de software/dados inequívoca. Os termos observados no acesso estão preservados no manifesto. | Preparado e auditado; retido em `prepared_semantically_gated`. |
| NASA IMS | [NASA Open Data Portal](https://data.nasa.gov/dataset/ims-bearings) | Registro hospedado no portal com `other-license-specified`; o payload foi fornecido pelo Center for Intelligent Maintenance Systems (IMS), University of Cincinnati. A página `government-works` vinculada pelo portal não determina sozinha a licença do payload. | Runs 1/2 preparados e auditados; run 3 em quarentena; retido em `prepared_semantically_gated`. |
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

## Estado real publicado

Os downloads e a preparação não estão mais pendentes. O `sources.json` liga
as fontes oficiais a duas gerações imutáveis e às attestations, metadatas e
inventários auditados:

- XJTU-SY:
  `xjtu-sy-v1-8c7e9d8b7c272002a4d44b021931aaf6500f013574db60839bae2af3aa0fee1a`,
  com 9.216 CSVs mais um PDF, 12.220.812.451 bytes e inventário SHA-256
  `42d68aa3fa65c28d0a15fd4bdb969ca7c9cc828827f4ab7a4dda62dfd42bd8db`;
- NASA IMS:
  `nasa-ims-v1-71cbedb9ec12f18af68eb175ba536c27df9c5de9a96fb4ac36d010f40e70ac0c`,
  com runs 1/2 preparados e o run 3 preservado em quarentena pela divergência
  de 4.448 arquivos documentados versus 6.324 observados.

Preparado não significa aprovado para pesquisa supervisionada. Unidade de
aceleração, labels por janela e semântica de medição compatível com Forzy não
foram auditados. Por isso ambas as fontes permanecem
`prepared_semantically_gated` e nenhuma métrica científica foi calculada.

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

A attestation XJTU-SY é imutável e conserva o campo histórico
`semanticGates.headerNames: "unknown"`. A metadata hash-pinned e a auditoria
independente posterior confirmam o header ordenado acima nas 9.216 janelas e
supersedem **somente** esse campo de nome do header. A reconciliação não altera
a attestation nem abre unidade, label por janela, semântica Forzy ou qualquer
gate de métrica.

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

O manifesto `sources.json` usa `schemaVersion: 2`. A preparação real registra
URLs HTTPS exatas, citação, termos/licença, data de acesso RFC 3339 e hashes
SHA-256 independentes das fontes, attestations, metadatas e inventários. Uma
fonte só atravessa o gate experimental quando, além dessa proveniência, recebe
status `approved_for_research` por uma política científica auditada. As duas
fontes atuais não atravessam esse gate.

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

Os arquivos versionados em `artifacts/ml-public` publicam o status
`not_run_semantic_gate`, `dataActuallyUsed: []` e `metrics: null`. Fixtures
sintéticas provam o pipeline apenas em diretórios temporários e nunca são
publicadas como resultado científico. Os sinais reais já existem em gerações
preparadas, mas o CLI legado aceita somente um ZIP/TAR por fonte e um destino
de extração vazio; ele não consome a geração XJTU multipart nem os dois runs
NASA preparados. A retomada exige um loader de gerações revisado e uma política
explícita para labels, unidade e semântica Forzy — ou a aprovação separada de
um estudo não supervisionado de drift. Nada neste fluxo promove ou altera
`artifacts/ml/real-forzy`.
