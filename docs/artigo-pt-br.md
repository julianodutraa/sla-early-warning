# Prever o estouro de SLA antes do job começar

*Um modelo pequeno, um dataset aberto e uma lição sobre onde está o valor de verdade*

Quase todo time de dados descobre que perdeu um SLA do mesmo jeito. Alguém abre o dashboard de manhã, o número está velho, e começa a investigação de trás para frente: qual job atrasou, por que atrasou, quem precisa ser avisado. Quando a pergunta chega ao time de plataforma, o prazo já passou e a única coisa que resta é explicar.

Este artigo descreve um experimento que publiquei de forma aberta para atacar esse problema pelo outro lado: em vez de detectar o estouro depois do prazo, estimar a probabilidade de estouro no instante em que o orquestrador libera o job. Nesse momento a folga inteira ainda está disponível, e isso muda o que o engenheiro de plantão consegue fazer.

O modelo, o dataset e o código estão públicos:

* Modelo: https://huggingface.co/julianoxdd/sla-breach-early-warning
* Dataset: https://huggingface.co/datasets/julianoxdd/batch-sla-runs
* Código, testes e avaliação: https://github.com/julianodutraa/sla-early-warning

## A regra que todo mundo escreve

A proteção mais comum contra estouro de SLA em pipelines batch é uma regra estática, geralmente escrita em uma tarde e nunca mais revisitada. Ela soma o atraso das dependências upstream ao p95 histórico do runtime do job e compara o resultado com a folga até o prazo. Se passar, dispara o alerta.

A regra parece sensata e tem uma virtude real: é fácil de explicar. O problema é o comportamento dela em produção. O p95 é, por construção, um cenário pessimista, e somá-lo ao atraso atual faz a regra disparar em muitas execuções que terminariam a tempo. No experimento, aplicada ao pé da letra sobre um mês de execuções, ela dispara 1.319 alertas e só 29% deles correspondem a estouros reais.

Esse número explica um fenômeno que qualquer time de plantão conhece. Quando sete em cada dez alertas são falsos, as pessoas aprendem a ignorá-los, e o alerta verdadeiro se perde no ruído. Um alerta que ninguém lê tem custo operacional e nenhum benefício.

## A pergunta certa

A reformulação que guia o projeto é simples: no instante em que o job é liberado, qual a probabilidade de ele terminar depois do prazo, usando apenas informação que o orquestrador já tem?

Essa restrição é o coração do problema. Tudo o que só se sabe depois da execução, como o runtime real, o tempo efetivo de fila ou a causa do atraso, está proibido como entrada. O que sobra são sinais disponíveis antes do job começar: o volume de entrada e a razão dele contra a mediana dos últimos sete dias, o atraso das dependências upstream, a pressão do cluster compartilhado medida por CPU, profundidade de fila e jobs concorrentes, o histórico recente do próprio job e a folga definida pelo SLA.

Enquadrar assim tem uma consequência prática importante. O alerta chega com a folga inteira pela frente. Há tempo para adicionar executores, reordenar a fila, acionar o dono do upstream ou avisar o consumidor do dado antes que ele descubra sozinho.

## Um dataset com mecanismo conhecido

Logs reais de orquestrador raramente saem das empresas e, quando saem, não trazem a causa de cada atraso rotulada. Por isso construí um dataset sintético com processo gerador documentado e semente fixa, o que permite comparar métodos sob mecanismos conhecidos e reproduzir cada número.

São 19.440 execuções de 60 jobs ao longo de 180 dias. Cada job tem uma família, um runtime base lognormal, de uma a quatro execuções por dia, uma elasticidade própria em relação ao volume e uma folga de SLA entre 1,5 e 2,8 vezes o runtime típico.

O runtime de cada execução é multiplicativo: o runtime base, multiplicado pelo volume elevado à elasticidade do job, por um fator de contenção que cresce quando a CPU do cluster passa de 70% e com a profundidade da fila, e por ruído lognormal. Sobre isso entram eventos injetados e rotulados. Picos de volume aparecem em 4% das execuções e multiplicam o volume de 1,8 a 4 vezes. Atraso upstream aparece em 12%, com cauda longa. Skew de dados é raro, mais provável em jobs propensos e logo depois de uma mudança de schema no upstream. Preempção de instâncias spot é mais provável sob CPU alta e soma tempo de reexecução.

Há sazonalidade semanal e de fim de mês no volume, um ciclo diário na carga do cluster e uma erosão lenta de capacidade ao longo do semestre. Essa erosão faz a taxa de estouro subir com o tempo, o que transforma o período de teste em um pequeno teste de mudança de distribuição. No total, 19,5% das execuções estouram o SLA, e cada estouro traz a causa dominante rotulada.

## Avaliar sem se enganar

Modelos de operação costumam parecer ótimos em validação e decepcionar em produção. Quase sempre o motivo é vazamento de informação. Por isso a metodologia recebeu tanta atenção quanto o modelo.

A divisão é temporal: 70% da linha do tempo para treino, os 15% seguintes para validação e os 15% finais para teste, sempre estritamente no futuro. As features de histórico são calculadas só com execuções anteriores do mesmo job, e há um teste automatizado que confere isso. As colunas que só existem depois da execução ficam fora da matriz de entrada, com outro teste garantindo.

O limiar de alerta é escolhido na validação para atingir 80% de precisão e depois aplicado sem nenhum ajuste no teste. Os intervalos de confiança vêm de um bootstrap que reamostra dias inteiros, não execuções isoladas, porque execuções do mesmo dia compartilham o estado do cluster e não são independentes. Por fim, o experimento inteiro é repetido em cinco mundos regenerados com outras sementes, com dados e modelos refeitos do zero, para separar resultado de sorte.

## O modelo

O modelo publicado é deliberadamente pequeno: um HistGradientBoostingClassifier do scikit-learn com 27 features. São 15 sinais brutos, a família do job e quatro razões construídas que carregam boa parte do sinal: a folga dividida pelo p50 histórico, o atraso upstream dividido pela folga, o término esperado usando o p50 multiplicado pela razão de volume, e o término pelo p95 sobre a folga.

O artefato tem cerca de 3 MB, é serializado com skops em vez de pickle e pontua milhares de execuções por segundo em uma única CPU. Treinar tudo, incluindo baselines e a varredura de robustez, leva menos de um minuto.

Comparei o modelo com dois baselines. O primeiro é a própria regra do p95, usada como pontuação contínua. O segundo é uma regressão logística sobre exatamente as mesmas features, que é o baseline honesto para qualquer modelo de árvore.

## Resultados

O conjunto de teste cobre 27 dias no futuro, com 2.920 execuções e 594 estouros.

Na métrica principal, a área sob a curva de precisão e recall, a regra do p95 fica em 0,384, com intervalo de 0,355 a 0,416. A regressão logística chega a 0,804, com intervalo de 0,768 a 0,835. O modelo publicado chega a 0,819, com intervalo de 0,781 a 0,850. Na área sob a curva ROC, os valores são 0,679, 0,914 e 0,918, respectivamente. O recall a 80% de precisão é 0,054 para a regra, 0,621 para a logística e 0,643 para o modelo.

Nos cinco mundos regenerados, o modelo fica em 0,826 de PR AUC com desvio padrão de 0,007, a logística em 0,811 com desvio de 0,017 e a regra em 0,442 com desvio de 0,030. A ordem dos três se mantém em todas as sementes.

A leitura operacional é a mais útil para quem decide. No limiar escolhido na validação, o modelo dispara 388 alertas no período de teste e antecipa 337 estouros, com 87% de precisão e 57% de recall. Se a regra recebesse o mesmo orçamento de 388 alertas, apontando para as 388 execuções que ela considera mais arriscadas, anteciparia 161. Com a mesma carga de trabalho para o plantão, o número de estouros evitáveis dobra.

## O que o modelo não resolve

O achado mais importante do experimento não está na tabela principal. A regressão logística, com as mesmas features, chega a 0,804 contra 0,819 do gradient boosting. O bootstrap pareado por dia coloca o ganho do modelo de árvore entre 0,002 e 0,026: positivo, real, mas pequeno.

Isso quer dizer que quase todo o valor vem de tratar o SLA como risco aprendido sobre sinais disponíveis na liberação do job, e muito pouco da capacidade do modelo. Para um time que precisa explicar alertas a auditores ou a outras equipes, uma logística bem construída entrega a maior parte do benefício com explicabilidade quase total. A escolha entre os dois é de engenharia e governança, não de ciência.

O segundo limite aparece quando se olha o recall por causa. Estouros causados por atraso upstream são antecipados em 89% dos casos e picos de volume em 65%. Contenção de cluster fica em 41%. Já skew de dados e preempção spot ficam em cerca de 15%. Esses dois eventos simplesmente não dão sinal antes de o job começar, e nenhum modelo que respeite a restrição de usar só informação prévia vai enxergá-los. Para eles, a resposta certa é outra camada: monitoramento durante a execução, com detecção de progresso anômalo.

## Limitações

Os dados são sintéticos. O gerador codifica mecanismos plausíveis, mas os números absolutos não dizem nada sobre uma plataforma específica, e a distância entre a regra e o modelo depende de quanto as premissas da regra falham em cada ambiente. As features de histórico assumem que a execução anterior do mesmo job já terminou, o que nem sempre é verdade para jobs que rodam quatro vezes por dia. O modelo pontua cada execução de forma independente e não raciocina sobre cascatas no DAG. E como a capacidade do cluster se degrada ao longo do tempo, a calibração das probabilidades também se degrada sem retreino, exatamente como aconteceria em produção.

## Como levar isso para produção

Para quem quiser aplicar a ideia, o caminho que eu seguiria tem quatro passos. Primeiro, extrair do orquestrador o histórico de execuções com horário de liberação, término, prazo e os sinais do cluster no momento da liberação. Segundo, recalcular as features de histórico estritamente com execuções anteriores e dividir os dados por tempo, nunca aleatoriamente. Terceiro, definir o orçamento de alertas com o time de plantão antes de escolher o limiar, porque precisão desejada é uma decisão operacional e não estatística. Quarto, começar pela regressão logística e só adotar o modelo de árvore se o ganho medido justificar a perda de explicabilidade.

O repositório tem o gerador, o treino, a avaliação, os testes e um exemplo de inferência que funciona direto a partir do Hugging Face. Se você trabalha com orquestração, observabilidade ou confiabilidade de plataformas de dados, adoraria saber como esse problema aparece no seu ambiente e quais sinais fariam diferença nele.

*Juliano Dutra de Almeida é Engenheiro de Dados Sênior e trabalha com confiabilidade de plataformas de dados em Kubernetes.*
