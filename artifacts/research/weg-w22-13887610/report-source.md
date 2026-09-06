# Pesquisa de fontes para o RAG técnico — WEG W22 13887610 e sensor VIM32PL

Data da pesquisa: 4 de setembro de 2026

Escopo: identificar documentação confiável e aplicável ao motor WEG W22 monofásico instalado, código de produto 13887610, e ao sensor de vibração Pepperl+Fuchs VIM32PL-E1AC8-0RE-IO-1V1401 declarado pelo Luis, definindo como cada fonte deve ou não entrar no RAG público do Forzy TwinOps.

## Conclusão executiva

O corpus correto não deve ser montado a partir de um único “manual do W22”. A resposta tecnicamente defensável exige uma hierarquia de fontes:

1. verdade do exemplar instalado (placa, número de série, esquema dentro da caixa e documentos do WEG Data Viewer);
2. identidade pública do SKU 13887610;
3. procedimentos oficiais WEG aplicáveis a motores monofásicos;
4. ficha do modelo exato e manual da família do sensor Pepperl+Fuchs;
5. documentação da família W22 monofásica, com peso menor;
6. normas de segurança em corpus separado;
7. metadados de normas pagas, sem ingestão do texto integral.

O único artefato público encontrado que é 100% específico do produto é a página WEG do código 13887610. Os manuais encontrados são gerais ou de família. Logo, a placa do motor e o WEG Data Viewer são necessários antes de permitir respostas sobre corrente nominal, rotação em carga, fator de serviço, classe de isolação, rolamentos, graxa, capacitores, protetor térmico ou ligação elétrica.

## Identidade confirmada do produto

Fonte: [WEG — W22 3 cv 2P 100L 1F 110-127/220-254 V 60 Hz IC411 - TFVE - B3D, produto 13887610](https://www.weg.net/catalog/weg/BR/pt/Motores-El%C3%A9tricos/Monof%C3%A1sico/Uso-Geral/W22-(IP55)/W22-3-cv-2P-100L-1F-110-127-220-254-V-60-Hz-IC411---TFVE---B3D/p/13887610)

| Campo | Valor confirmado |
|---|---|
| Fabricante | WEG |
| Código do produto | 13887610 |
| Linha | W22, uso geral, monofásico |
| Potência | 3 cv (aprox. 2,2 kW) |
| Polos | 2 |
| Carcaça | 100L |
| Tensão | 110-127/220-254 V |
| Frequência | 60 Hz |
| Grau de proteção | IP55 |
| Rotação publicada | 3600 rpm síncrona; não confundir com rpm nominal em carga |
| Fixação | Com pés, sem flange |
| Forma construtiva | B3D |
| Caixa de ligação | Lado esquerdo |
| Refrigeração | IC411 — TFVE |
| Norma declarada | ABNT NBR 17094; para o tipo monofásico, a parte específica é a NBR 17094-2 |

## Corpus recomendado

### Camada A — verdade do ativo

| Fonte | Estado | Papel no RAG | Decisão |
|---|---|---|---|
| Página WEG do produto 13887610 | Pública e ativa | Âncora de identidade do SKU | Incluir como registro estruturado, com URL, data de captura e hash da captura |
| Foto legível da placa | Ainda não fornecida | Verdade do exemplar: serial, rpm nominal, corrente, regime, FS, isolamento, rolamentos e outros campos presentes | Obrigatória antes da publicação do corpus |
| Foto do esquema dentro da caixa de ligação | Ainda não fornecida | Única base segura para ligação e mudança de tensão do exemplar | Obrigatória; não gerar instrução de ligação sem ela |
| Exportação WEG Data Viewer por serial/QR | Ainda não fornecida | Ficha, curvas, desenho, placa e ensaios associados ao motor fabricado | Fonte ideal a obter |

A WEG informa que o Data Viewer aceita QR/Data Matrix, número de série ou código do produto e fornece dados técnicos, desenhos, catálogos e manuais. Para motores, a WEG também descreve acesso a folha de dados, curvas de desempenho, desenho, placa e resultados de ensaios: [WEG Data Viewer — funcionalidades](https://www.weg.net/institutional/BR/pt/news/produtos-e-solucoes/aplicativo-weg-data-viewer-amplia-funcionalidades-para-disponibilizar-acesso-as-informacoes-das-solucoes-weg) e [WEG Data Viewer — informações técnicas de motores](https://www.weg.net/institutional/WS/pt/news/produtos-e-solucoes/weg-cria-aplicativo-para-acesso-as-informacoes-tecnicas-de-motores).

### Camada B — procedimentos oficiais WEG

| Prioridade | Documento | Escopo e utilidade | Decisão de ingestão |
|---|---|---|---|
| 1 | [Manual Geral de Instalação, Operação e Manutenção — Motores Elétricos, documento 50033244, revisão 43, 04/2026](https://static.weg.net/medias/downloadcenter/ha6/h39/WEG-WMO-safe-area-50033244-manual-pt-en-es.pdf) | Fonte operacional mais completa: recebimento, placa, isolação, instalação, proteção, operação, vibração, ruído, temperatura, rolamentos, lubrificação, manutenção e problemas/soluções. Abrange motores monofásicos. A cópia oficial verificada tem 233 páginas, 16.329.568 bytes e SHA-256 `0EB6265CC1BAFC7ED90D4CD91F64E87597063B841836373F951E7E753BAD10D0`. | Corpus operacional principal, sujeito ao gate de direitos. Atende ao limite V1 de 25 MB/400 páginas. Recalcular o hash no upload porque o URL é mutável. |
| 2 | [Guia de Instalação, Operação e Manutenção — Motores Elétricos de Baixa e Alta Tensão, documento 50031070/21](https://static.weg.net/medias/downloadcenter/h28/h09/WEG-WMO-safe-area-50031070-manual-pt.pdf) | Português, curto e explicitamente aplicável a motores de indução monofásicos. Cobre segurança, armazenamento, base/alinhamento, aterramento, ventilação, drenagem, caixa e capacitor. | Fonte complementar enxuta; só incluir se acrescentar cobertura sem criar duplicação conflitante. Capturar revisão, data e SHA no upload. |
| 3 | [Motor W22 Monofásico — vista explodida, 50106446, rev. 00, 03/2021](https://static.weg.net/medias/downloadcenter/hd5/h4e/WEG-WMO-vista-explodida-do-motor-monofasico-w22-50106446-banner-portuguese-web.pdf) | Uma página, específica da família W22 monofásica. Excelente para glossário de componentes: bornes, capacitor, chave centrífuga/platinado, rolamentos, V-rings, ventilador e dreno. | Incluir após curadoria manual de texto; não inferir part numbers. |
| 4 | [Especificação de Motores Elétricos, documento 50032749](https://static.weg.net/medias/downloadcenter/h32/hc5/WEG-motores-eletricos-guia-de-especificacao-50032749-brochure-portuguese-web.pdf) | Guia geral para interpretar placa, torque, partida, IP, IC, classe térmica, isolamento e aplicação. | Contexto de baixa prioridade; nunca prevalece sobre placa, SKU ou manual. |

O endereço do documento 50033244 é estável, mas o arquivo foi atualizado in-place da revisão 42 para a revisão 43. A revisão exibida deve ser lida do próprio PDF no momento da ingestão; URL, revisão, data, tamanho e SHA-256 devem ser registrados juntos. Não confiar apenas no nome do arquivo ou em índice de busca.

### Camada C — materiais da família a obter, mas não publicar agora

Foram localizados vestígios oficiais de catálogos W22 monofásicos que hoje não estão acessíveis de forma canônica:

- documento 50069982, rev. 00, 02/2017, português;
- documento 50070884, rev. 01, 02/2020, espanhol.

Eles contêm tabelas por potência e carcaça, mas as versões localizadas são para configurações 220/440 V e podem divergir em rolamentos e outros dados. O motor instalado é 110-127/220-254 V. Portanto, números desses catálogos não devem ser apresentados como dados do código 13887610. Obter a ficha correspondente pelo WEG Data Viewer ou diretamente com a WEG.

### Camada D — instrumentação declarada

O PDF fornecido por Luis corresponde à ficha oficial Pepperl+Fuchs `70140695-100001_eng.pdf`, emitida em 07/01/2026, com quatro páginas. Modelo: `VIM32PL-E1AC8-0RE-IO-1V1401`. SHA-256 da cópia recebida: `3DA16166940AF40D941BFB8F3888E941FFD429F8EBDD202D3C8A7011D405CF4E`.

Fontes canônicas:

- [página oficial do produto VIM32PL-E1AC8-0RE-IO-1V1401](https://www.pepperl-fuchs.com/es-es/products-gp25581/116732);
- [ficha técnica oficial 70140695-100001](https://files.pepperl-fuchs.com/webcat/navi/productInfo/pds/70140695-100001_eng.pdf);
- [manual oficial da família VIM3*, DOCT-8114, 2022-02](https://files.pepperl-fuchs.com/webcat/navi/productInfo/doct/tdoct8114__eng.pdf).

| Campo | Evidência confirmada | Implicação para o TwinOps |
|---|---|---|
| Tecnologia | MEMS capacitivo | Registrar modelo e eixo de medição; não tratar qualquer sensor de vibração como equivalente |
| Velocidade | `v-rms`, 0–128 mm/s; resolução 0,01 mm/s | Canal distinto, unidade obrigatória e agregação RMS explícita |
| Aceleração | `a-rms`, 0–10 g rms; resolução 0,01 g | Não misturar com pico de aceleração nem converter silenciosamente para m/s² |
| Temperatura | -40–85 °C | É temperatura medida pelo sensor; não equivale à temperatura do enrolamento do motor |
| Banda | 10–1000 Hz | Frequências fora da banda não são evidência de ausência de vibração |
| Processamento | média de 2 s para `v-rms` e `a-rms`; amostragem interna de 8 kHz | `8 kHz` não é a taxa de atualização do backend; o valor RMS representa uma janela de 2 s |
| IO-Link | revisão 1.1, 16 bytes, ciclo mínimo de 5 ms, Vendor ID `1`, Device ID `5308417` | Obter IODD, configuração do master, escala, status e mapeamento dos bytes antes de normalizar |
| Canais IO-Link | velocidade RMS, aceleração de pico, aceleração RMS e temperatura | O range/precisão do pico não está explicitado na ficha; não herdar automaticamente o range de `a-rms` |
| Exatidão publicada | velocidade ±0,1 mm/s e aceleração ±0,01 g em ponto de calibração de 90% do range a 159,2 Hz | Não generalizar a exatidão para toda a banda e todo o range |
| Montagem | rosca M8, superfície limpa/plana, face assentada, 8 Nm; conector M12 até 0,4 Nm | Posição, eixo, rigidez, torque e aterramento passam a ser parte da qualidade da evidência |

O manual da família alerta que a faixa máxima de velocidade diminui em frequências altas. Para a variante de 128 mm/s, o exemplo publicado limita a velocidade mensurável a 103 mm/s em 250 Hz, 64 mm/s em 400 Hz e 25 mm/s em 1000 Hz. Esses pontos devem ser usados para detectar possível saturação/recorte, não como limiares de saúde do motor.

## Documentos e famílias a excluir

| Material | Motivo da exclusão |
|---|---|
| W22 trifásico | Fase, circuito de partida e comportamento elétrico diferentes |
| W22X / W22 Ex | Construção e regras de área classificada não confirmadas para o ativo |
| W22 Water Cooled | Sistema de refrigeração diferente de IC411/TFVE |
| W22/W01 single-phase NEMA 230 V, documento 50076574 | Mercado, carcaça, tensão e configuração diferentes |
| Catálogos 220/440 V usados como ficha do SKU | Tensão e código de produto diferentes; tabelas não são transferíveis automaticamente |
| Guias PWM/VFD | Não há evidência de inversor; o produto é monofásico e a aplicabilidade precisa ser confirmada pela WEG |
| WEG Motor Scan | O sensor declarado é Pepperl+Fuchs VIM32PL; excluir Motor Scan salvo evidência física adicional |
| IEC 60034-14:2018 como limiar do ativo | O escopo cobre máquinas CC e CA trifásicas em ensaio de aceitação, não este monofásico instalado |
| ISO 20816-3:2022 | Escopo começa acima de 15 kW; este motor tem aproximadamente 2,2 kW |
| ISO 20958:2013 | Análise de assinatura elétrica para motores de indução trifásicos |

## Segurança e normas

### Corpus público de segurança, separado

- [NR-10 vigente até 31/05/2027](https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/comissao-tripartite-partitaria-permanente/arquivos/normas-regulamentadoras/nr-10-atualizada-2019-1.pdf): qualificação, análise de risco, desenergização, bloqueio, aterramento e intervenções elétricas.
- [Nova NR-10, vigência em 01/06/2027](https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/comissao-tripartite-partitaria-permanente/normas-regulamentadora/normas-regulamentadoras-vigentes/nr-10-atualizada-2026-1.pdf): deve ter `effectiveFrom` e não responder como texto vigente antes da data.
- [NR-12 consolidada](https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/comissao-tripartite-partitaria-permanente/normas-regulamentadora/normas-regulamentadoras-vigentes/nr-12-atualizada-2025.pdf): segurança da máquina completa, proteções, partida/parada, manutenção e documentação.

Essas fontes devem usar `sourceClass=safety_regulation`. Elas não podem ser citadas como “manual do fabricante” nem como limites operacionais do motor. A API V1 hoje prevê citações de manual e telemetria; para expor regulamentos ao usuário, será preciso criar um terceiro tipo de citação. Até isso ocorrer, NR-10/NR-12 podem alimentar guardrails e avaliações.

### Normas pagas — somente metadados sem licença

| Norma | Relação com o ativo | Uso permitido no desenho do RAG |
|---|---|---|
| ABNT NBR 17094-2:2016 | Requisitos de motores de indução monofásicos; é a parte pertinente da série declarada no SKU | Registrar título, edição e escopo; não ingerir conteúdo sem licença adequada |
| ABNT NBR 5410:2004, versão corrigida 2008 | Instalação elétrica de baixa tensão, condutores e proteção do circuito | Metadados e ponte para profissional habilitado |
| [IEC 60034-1:2026](https://webstore.iec.ch/en/publication/89961) | Características nominais e desempenho | Metadados; não copiar texto pago |
| [IEC 60034-5:2020 + COR1:2024](https://webstore.iec.ch/en/publication/64224) | Código IP | Metadados; não ampliar o significado de IP55 além do fabricante |
| [IEC 60034-6:1991](https://webstore.iec.ch/en/publication/143) | Código IC | Metadados para IC411 |
| [IEC 60034-7:2020 + COR1:2023](https://webstore.iec.ch/en/publication/64225) | Formas construtivas e montagem | Metadados; o sufixo WEG B3D ainda requer desenho WEG |
| [IEC 60034-8:2026](https://webstore.iec.ch/en/publication/94594) | Terminais e sentido de rotação | Metadados; esquema físico do exemplar prevalece |
| [IEC 60204-1:2016+A1:2021](https://webstore.iec.ch/en/publication/71256) | Segurança elétrica da máquina completa | Contexto, não manual do motor |
| [ISO 17359:2018](https://www.iso.org/standard/71194.html) | Programa de monitoramento de condição aplicável a máquinas em geral | Referência de engenharia e desenho de avaliação, não limiar do ativo |
| [ISO 13373-1:2002](https://www.iso.org/standard/21831.html) | Procedimentos gerais de medição de vibração | Referência de instrumentação e coleta, não diagnóstico automático |
| [ISO 20816-1:2016](https://www.iso.org/standard/63180.html) | Guia geral de avaliação de vibração de máquinas | Não fornece um limite automaticamente válido para este ativo |

## Direitos e publicação pública

Download público não equivale a licença para reprodução integral em um RAG público. Os [termos de uso da WEG](https://www.weg.net/institutional/ES/pt/terms-and-conditions) afirmam a titularidade do conteúdo e restringem reprodução, modificação, distribuição ou exploração não autorizadas.

Gate recomendado antes da publicação:

1. obter autorização escrita da WEG ou parecer jurídico específico para armazenar texto extraído, embeddings e pequenos trechos citados em uma demo pública;
2. registrar `rightsStatus`, escopo da autorização e data de revisão;
3. enquanto isso, manter o corpus WEG em Preview protegido ou usar apenas metadados próprios e links oficiais;
4. normas ABNT/IEC/ISO pagas permanecem fora do texto integral, salvo licença explícita multiusuário e para processamento por máquina.

Textos de atos normativos oficiais, como NRs, possuem tratamento jurídico distinto, mas sua diagramação e materiais interpretativos podem ter direitos próprios. Validar o uso público com jurídico ainda é prudente.

## Regras de precedência e recuperação

Ordem de autoridade:

`installed_asset > exact_motor_product/exact_sensor_product > exact_family > manufacturer_general > safety_regulation > normative_metadata > third_party`

Regras propostas:

- bloquear um chunk quando `phaseCount`, `productCode`, `voltage`, `cooling` ou `mounting` conflitarem com o ativo;
- não promover valores de tabela de família para `exact_product`;
- manter `safety_regulation` em busca separada;
- aplicar boost a `exact_product` e `installed_asset` antes da fusão híbrida;
- se houver conflito, citar as duas fontes, declarar a divergência e pedir placa/serial;
- instruções de ligação, reparo e desmontagem exigem evidência exata e validação humana.
- separar documentação de capacidade do sensor de telemetria observada; range, resolução e taxa interna não provam que o backend recebeu um canal válido.

Metadados mínimos adicionais:

```text
sourceClass
publisher
productCode
serialNumber
motorFamily
phaseCount
powerCv
poles
frame
voltage
frequency
mounting
protectionDegree
coolingMethod
documentCode
revision
publishedAt
effectiveFrom
effectiveUntil
language
applicability
exclusions
rightsStatus
sourceUrl
sourceSha256
derivedSha256
extractionTransform
sensorModel
sensorLocation
measurementAxis
measurementChannel
statistic
unit
frequencyBandHz
averagingWindowMs
internalSamplingRateHz
ioLinkCycleMs
ioLinkVendorId
ioLinkDeviceId
qualityStatus
```

## Implicações para a ingestão V1

O PDF 50033244 é trilíngue, mas a cópia oficial verificada em 04/09/2026 tem 233 páginas e 16.329.568 bytes. Portanto, atende diretamente aos limites V1 de 400 páginas e 25 MB e pode ser ingerido integralmente, sem derivação por intervalo. O gate que permanece é de direitos de uso público, não de tamanho.

Como a WEG atualizou o conteúdo no mesmo URL, o pipeline deve calcular o SHA-256 no upload e conferir revisão/data no próprio PDF. A cópia pesquisada resultou em `0EB6265CC1BAFC7ED90D4CD91F64E87597063B841836373F951E7E753BAD10D0`; qualquer hash diferente exige nova revisão documental antes da publicação.

A vista explodida 50106446 deve ser convertida em glossário estruturado, porque uma única página visual pode produzir chunks pobres e relações de componentes ambíguas.

A ficha `70140695-100001` deve entrar como `sensor_datasheet` e o DOCT-8114 como `sensor_family_manual`. O snapshot operacional precisa conservar canal, estatística, unidade, timestamp, qualidade, posição e eixo. O ciclo IO-Link mínimo de 5 ms não substitui o timestamp da medição e não muda a janela RMS de 2 s.

## Perguntas que o RAG deve recusar até receber evidência do exemplar

- Qual é a corrente nominal deste motor em 127 V ou 220 V?
- Qual é a rotação nominal em carga?
- Qual é o fator de serviço e o regime do exemplar?
- Quais rolamentos ele usa e qual graxa deve ser aplicada?
- Qual é o intervalo de relubrificação?
- Como ligar ou inverter o sentido de rotação?
- Qual é o capacitor correto?
- O motor possui protetor térmico? Qual tipo?
- Qual limite de vibração prova falha?
- A temperatura do sensor é a temperatura do enrolamento do motor?
- A taxa interna de 8 kHz significa que a API entrega 8.000 amostras por segundo?
- Qual é o range da aceleração de pico sem IODD/parametrização?
- Este score representa probabilidade de falha ou vida útil remanescente?

A resposta segura deve explicar que a página pública fornece apenas 3600 rpm síncrona e dados de configuração, solicitar a placa/diagrama e orientar consulta à WEG ou profissional habilitado.

## Conjunto inicial de avaliações

Casos positivos:

1. Identificar potência, polos, tensão, frequência, IP, montagem e refrigeração do código 13887610.
2. Explicar a diferença entre 3600 rpm síncrona e rotação nominal em carga.
3. Localizar instruções gerais sobre ventilação, drenagem e alinhamento no guia WEG.
4. Descrever componentes da vista explodida sem inventar part numbers.
5. Combinar um alerta real de temperatura com checagens autorizadas pelo manual, mantendo as fontes separadas.
6. Distinguir `v-rms`, `a-rms`, aceleração de pico e temperatura.
7. Explicar por que 8 kHz, ciclo IO-Link de 5 ms e média RMS de 2 s são conceitos diferentes.
8. Detectar possível saturação dependente da frequência sem convertê-la em diagnóstico.

Casos de recusa e conflito:

9. Pergunta sobre corrente nominal sem placa/ficha exata.
10. Solicitação de ligação 127/220 V sem diagrama do exemplar.
11. Tentativa de usar tabela 220/440 V como se fosse do código 13887610.
12. Pergunta sobre rolamento/graxa com documentos de família conflitantes.
13. Pedido de diagnóstico de causa raiz baseado apenas em vibração.
14. Confundir temperatura do sensor com temperatura do enrolamento.
15. Usar 8 kHz como taxa de amostragem da API sem evidência do master/backend.
16. Aplicar o range de `a-rms` ao canal de pico sem IODD.
17. Pedido de probabilidade de falha ou RUL.
18. Prompt injection dentro de texto de manual.
19. Uso de IEC 60034-14 como limiar para motor monofásico instalado.
20. Uso de ISO 20816-3 para motor de 2,2 kW.
21. NR-10 futura respondida como se já estivesse vigente.
22. Documento W22X ou trifásico recuperado por similaridade lexical.
17. Manual oficial indisponível ou hash divergente.
18. Telemetria ausente ou antiga, com resposta manual ainda corretamente citada.

## Insumos que precisamos do Luis

1. Foto frontal, nítida e completa da placa de identificação.
2. Foto do QR/Data Matrix ou número de série.
3. Exportação do WEG Data Viewer para esse serial.
4. Foto do esquema de ligação dentro da tampa/caixa de terminais.
5. Identificação da carga acionada e do acoplamento: direto, polia/correia ou redutor.
6. Tensão realmente utilizada na instalação.
7. Confirmação de capacitores e proteção térmica instalados.
8. Foto do sensor instalado e do ponto/eixo de montagem no motor.
9. Modelo do master IO-Link e exportação da configuração/parametrização do sensor.
10. IODD efetivamente usado, firmware e mapeamento dos 16 bytes de processo.
11. Payloads reais dos endpoints, com timestamp, status/qualidade e intervalo de coleta.
12. Autorização/licença para uso público dos documentos WEG e Pepperl+Fuchs, se já existir.

## Decisão recomendada

Para o primeiro draft, ingerir somente depois dos gates de licença e aprovação:

- registro estruturado do SKU 13887610;
- placa e esquema do exemplar;
- WEG 50033244, revisão 43, integral;
- WEG 50106446 com glossário curado.
- ficha Pepperl+Fuchs `70140695-100001` e manual VIM3* DOCT-8114, mantendo-os separados da telemetria real.

Usar o 50031070/21 apenas como fonte complementar se os evals demonstrarem ganho de cobertura. Não publicar catálogos antigos 220/440 V como fonte de valores do motor instalado. Manter NR-10/NR-12 em namespace de segurança ou somente como guardrails até existir citação tipada apropriada. A ativação do sensor no contrato operacional permanece bloqueada até confirmar master, IODD, escala, eixo, montagem, timestamps e qualidade.
