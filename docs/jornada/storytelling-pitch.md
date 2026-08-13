# Storytelling do pitch

Este documento transforma a jornada técnica em uma narrativa verificável. Ele
não substitui os resultados dos experimentos.

## Tese central

O Forzy TwinOps conecta medições de motores a decisões de manutenção. O
demonstrador mostra como dados reais, ML de baixa latência e assistência por
linguagem podem formar a base de um sistema preditivo confiável.

## Arco narrativo inicial

### 1. O problema

Uma leitura isolada mostra o estado atual. Ela não informa se o comportamento
está se deteriorando nem oferece antecedência para manutenção.

### 2. O primeiro protótipo

O protótipo navegável mostrou a visão do produto: identidade por TAG,
telemetria, alertas, recomendações e auditoria. Dados sintéticos permitiram
validar o fluxo, mas não provaram capacidade preditiva.

### 3. O contato com dados reais

A EDA revelou ciclos reais, eventos candidatos e problemas de aquisição. A
ficha técnica também corrigiu uma suposição: o canal `Velocidade` mede
velocidade de vibração RMS, não rotação do eixo. Essa descoberta mostra por que
um sistema confiável precisa preservar semântica, unidade e procedência, além
do valor numérico.

### 4. A fonte ao vivo

Os endpoints S1 e S2 tornam possível observar o motor durante a janela de
operação. O contrato atual também evidencia o investimento necessário:
timestamp de aquisição, unidades, identidade estável, frequência conhecida,
autenticação e disponibilidade operacional.

O sensor já faz aquisição interna a 8 kHz e entrega valores RMS com média de 2
segundos. O desafio do demonstrador não é tornar a inferência mais rápida que o
próprio sinal; é preservar a cadência, o timestamp e a qualidade das leituras
até o alerta.

### 5. A arquitetura de duas velocidades

O ML clássico acompanha os sinais e produz alertas rápidos, explicáveis e
independentes da internet. O SLM/LLM transforma evidências estruturadas em uma
explicação acessível, consulta conhecimento técnico e apoia a decisão humana.

### 6. O que o demonstrador prova

- integração com medições reais;
- construção de histórico a partir de snapshots;
- execução reproduzível de um ranking de anomalias em 7.183 registros reais;
- scoring clássico por fold abaixo de 8 ms no p95 do backtest local;
- features mais inferência em cerca de 49 ms no p95 de uma janela local de
  1.000 leituras, ainda sem incluir a latência ponta a ponta;
- explicação rastreável pelo copiloto;
- comparação entre modelo local e API;
- identificação objetiva das lacunas para escala industrial.

O resultado mais importante não é “já prevemos falhas”. É que o caminho
técnico completo existe e é rápido, enquanto o próprio experimento revela o
investimento que falta: histórico longitudinal, falhas confirmadas, contexto
operacional e melhor contrato de aquisição.

### 7. O investimento para escalar

- sensores e frequência de aquisição adequados ao fenômeno observado;
- timestamp e qualidade na origem;
- conectividade e endpoint com SLA;
- coleta de eventos de manutenção e falhas confirmadas;
- validação em diferentes motores e regimes;
- operação, monitoramento de drift e governança de modelos.

## Afirmações permitidas

- "Identificamos eventos candidatos que estão sendo reavaliados com a semântica
  correta do sensor."
- "O sistema mede risco de anomalia com evidências rastreáveis."
- "O demonstrador está instrumentado para medir antecedência e falso alerta
  quando houver eventos confirmados."
- "A arquitetura separa decisão rápida de explicação por linguagem."
- "Os experimentos mostram quais investimentos são necessários para escalar."

## Afirmações que exigem evidência futura

- "Prevemos falhas mecânicas específicas."
- "Evitamos uma parada de produção."
- "O sistema opera com confiabilidade industrial."
- "O modelo identifica a causa raiz sem validação técnica."
- "A solução funciona para qualquer motor ou regime operacional."

## Evidências visuais desejadas para o pitch

- linha temporal com sinal, alerta antecipado e evento observado;
- comparação entre comportamento normal e anômalo;
- painel com qualidade e frescor dos dados;
- explicação do copiloto vinculada às medições usadas;
- tabela de resultados dos modelos e latências;
- roadmap entre demonstrador e operação industrial.
