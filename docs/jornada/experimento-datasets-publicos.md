# Experimento com datasets públicos de falhas

## Objetivo e fronteira

Este laboratório mede quanto conhecimento de falhas de rolamentos sobrevive à
redução do sinal completo para estatísticas agregadas e, finalmente, para o
subconjunto semanticamente compatível com a API Forzy. Ele é científico e
separado do modelo operacional: não altera `artifacts/ml/real-forzy`, não
calibra o ativo `forzy-motor-01` e não alimenta a UI.

As três vistas congeladas são:

1. **Full:** estatísticas do waveform, energia espectral e envelope em bandas
   normalizadas por Nyquist.
2. **Aggregate:** estatísticas da janela e apenas contexto realmente medido.
3. **Forzy-compatible:** aceleração RMS e temperatura somente quando medidas
   com semântica reproduzível. Velocidade RMS não é derivada da aceleração sem
   filtro e integrador validados; RPM e temperatura ausentes não são inventados.

## Evidência

O código de contrato, adapters, integridade SHA-256, features, splits por
rolamento, baselines, métricas e bootstrap por rolamento foi executado contra
fixtures numéricas pequenas. Essas fixtures testam o pipeline; elas **não** são
evidência científica e não entram nas métricas do relatório versionado.

As fontes registradas são as páginas dos autores do XJTU-SY e o portal NASA
para IMS. Nesta execução, a autorização explícita para baixar os arquivos
originais e aceitar/verificar seus termos ainda estava pendente. Por isso não
há URL exata de arquivo, data de acesso nem hash do archive realmente usado.

## Resultado

Status: `not_run_external_data_gate`.

Nenhum arquivo bruto XJTU-SY ou NASA IMS foi usado. Consequentemente:

- delta `full -> aggregate -> Forzy-compatible`: **não calculado**;
- XJTU-SY → NASA IMS: **não executado**;
- NASA IMS → XJTU-SY: **não executado**;
- comparação com baseline majoritário: **não calculada**;
- métricas diagnósticas, prognósticas e intervalos de confiança: **ausentes**.

Não existe, portanto, base para dizer que “o modelo Forzy prevê falha”. O
resultado desta entrega é um protocolo reproduzível e com gates, não uma
alegação de desempenho.

## Limitação

Os adapters exigem um `metadata.json` curado junto ao raw extraído. Labels,
identidade de canais, frequência de amostragem e unidade vêm desse mapa; não
são adivinhados por nome de arquivo. Uma retomada deve confrontar esse mapa com
a documentação da versão exata baixada.

Mesmo após a execução, resultados públicos continuarão limitados por diferenças
de bancada, montagem, carga, rotação, posição do sensor, banda e estatística
interna. A vista Forzy-compatible não prova equivalência física com S1/S2 e não
é calibrada para o conjunto motor-bomba real.

## Próximo experimento

Após autorização explícita de rede e termos:

1. registrar a URL exata de cada archive, termos/licença e `accessedAt`;
2. baixar para a árvore ignorada sem sobrescrever arquivo existente;
3. calcular e fixar SHA-256 antes de extrair em diretório vazio;
4. curar os mapas de bearings/canais contra a documentação original;
5. executar o comando abaixo, que falha em hash divergente, overlap de bearing,
   labels não mapeáveis ou fronteira operacional inválida;
6. revisar os deltas das três vistas e exigir cross-bench acima do baseline
   majoritário antes de qualquer claim de transferência.

```powershell
services\twinops\.venv\Scripts\python.exe scripts/run_public_fault_lab.py `
  --datasets xjtu ims `
  --output artifacts/ml-public `
  --seed 42
```

O preflight sem escrita pode ser repetido com `--dry-run`. Quando os dados
verificados existirem, o CLI produzirá contagens, hashes, splits, tempos,
métricas das três vistas e intervalos de confiança por bootstrap de bearings.
