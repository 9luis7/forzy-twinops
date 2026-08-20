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
