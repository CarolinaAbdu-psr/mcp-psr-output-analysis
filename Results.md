
# 5. Visualização e Análise dos Resultados

**Objetivo:** Processar, visualizar e entender os outputs do modelo.

Com a execução concluída, o próximo passo é processar e analisar os resultados para diagnosticar a qualidade da solução. Recomendamos seguir a sequência estruturada abaixo:

## 5.1 Dashboard Padrão do SDDP: Análise e Diagnóstico

O **Dashboard padrão do SDDP** oferece uma visão geral da qualidade da solução e dos principais resultados do caso. Ele é a principal ferramenta para entender as saídas do modelo e pode ser acessado de duas formas:

* Diretamente no PSRCloud, pela opção **"Dashboard"** no menu superior.
* Fazendo o download do arquivo `SDDP.html` na aba **Results** do caso. *(Para baixar qualquer arquivo do repositório da nuvem, acesse o caso no PSRCloud, vá até a aba "Results" e clique em "Download files").*

Abaixo, detalhamos as principais abas e métricas disponíveis neste painel para um diagnóstico completo.

### 5.1.1 Política
Nessa aba é possível verificar os resultados relacionados ao cálculo de política do caso, isto é, confirmar se o processo de otimização foi bem-sucedido e se a estratégia de custos futuros foi adequadamente construída.

**A. Análise de Convergência no SDDP**
O gráfico de convergência ilustra a evolução dos limites inferiores ($Z_{inf}$) e superiores ($Z_{sup}$) ao longo das iterações. O objetivo é reduzir a diferença entre esses valores até que se atinja um critério de parada pré-estabelecido:

* **Caso Determinístico:** A convergência é atingida quando o erro relativo entre os limites é menor ou igual à tolerância estipulada:
    $$\frac{Z_{sup} - Z_{inf}}{Z_{sup}} \le \text{Tolerância}$$
* **Caso Estocástico:** Devido à natureza aleatória das séries de vazões, a convergência é verificada quando o limite inferior ($Z_{inf}$) pertence ao intervalo de confiança (geralmente de 95%) do custo operativo médio calculado na etapa *forward*:
    $$Z_{inf} \in \left[ \bar{Z}_{sup} - 1,96 \frac{\sigma_{Z_{sup}}}{\sqrt{N}}; \bar{Z}_{sup} + 1,96 \frac{\sigma_{Z_{sup}}}{\sqrt{N}} \right]$$

> **Definições dos Parâmetros:**
> * **Limite Superior ($Z_{sup}$):** Representa o custo total da operação simulada. No contexto estocástico, utiliza-se a média aritmética dos custos de N séries (cenários) de vazões:
>     $$\bar{Z}_{sup} = \frac{1}{N} \sum_{n=1}^{N} CT(n)$$
> * **Limite Inferior ($Z_{inf}$):** É o valor da função objetivo na primeira etapa. Atua como limite inferior pois a Função de Custo Futuro (FCF) é aproximada por cortes de Benders. Como a FCF é convexa, seus cortes estão sempre abaixo ou no mesmo nível da função real:
>     $$FCF(x) \ge \sum (\text{Cortes de Benders})$$

**Causas para a Não Convergência:**
Quando o algoritmo não atinge a convergência, investigue os seguintes fatores:
1.  **Número Insuficiente de Iterações:** Se o $Z_{inf}$ apresenta tendência de aproximação nas etapas finais, mas não atinge o critério, o número máximo de iterações pode ser baixo para a complexidade do problema.
2.  **Estagnação da Convergência:** Se o $Z_{inf}$ parar de evoluir:
    * **Influência das Penalidades:** Valores excessivos de penalidades criam cortes que são dominados, ou seja, que não estão de fato aproximando a função de custo futuro, pois estão abaixo dos cortes dominantes.
    * **Dimensão da Amostra:** Um número reduzido de séries de *forward* limita a exploração de cenários, resultando em menos informações para a construção precisa da FCF.

**B. Função Objetivo: Política vs. Simulação Final**
Este gráfico compara o valor esperado da função objetivo da última iteração da política com os resultados da simulação final. Se a simulação final apresentar valores fora do intervalo de confiança da política, a solução pode ser subótima. Principais motivos:
* **Política Incompleta:** Se a fase de política não convergiu, a FCF fornecerá sinais de custo imprecisos na simulação.
* **Impacto da Não-Convexidade:** Em simulações horárias com variáveis binárias, surgem não-convexidades. *Solução: Ative em Configuração → Estratégia de Solução → Não-Convexidade da Política.*
* **Discrepância na Amostragem:** Se na rodada for feita uma simulação em que a FCF foi copiada de outro caso e cenários extremos como aumento súbito do preço de combustíveis forma modelados apenas na simulação, pode haver um descolmento entre política e simualção, pois não há cortes de Benders cobrindo essa região.

### 5.1.2 Simulação
Nesta seção, avalia-se a qualidade da operação, diagnosticando os custos , dispersão de resultados e o status de simulações horárias.

* **Porções do Custo Operativo Total:** Primeiro indicador de alerta. Recomenda-se que o Custo Operativo represente pelo menos 80% do Custo Total. Custos de penalidade excessivos indicam que o modelo está violando restrições para viabilizar o problema, gerando uma operação irreal.
* **Custo Operativo Médio por Etapa:** Permite identificar em quais etapas o sistema sofre maior estresse ao longo do horizonte planejado, além de apontar em quais estágios as violações estão acontecendo com mais frequência.
* **Dispersão de Custos Operativos por Etapa:** Mostra a correlação entre custos e incerteza hidrológica. O percentil **P10** representa os cenários mais favoráveis, enquanto o **P90** reflete os cenários críticos. Esse gráfico deve estar relacionado com o gráfico de Energia Afluente: o período úmido naturalmente apresenta maior variabilidade, enquanto o seco tende a ser mais previsível.
* **Estado da Solução por Etapa e Cenário (Simulação Horária):** Detalha a performance do solver em cada MIP:
    * **Ótima:** Solver atingiu o critério de parada.
    * **Factível:** Solução viável encontrada, mas sem garantia de ser a ótima dentro do tempo estipulado.
    * **Relaxada:** Ocorreu relaxamento das variáveis binárias (assumiram valores contínuos no intervalo [0, 1] ao invés de 0 ou 1). 
    * **Erro:** O solver não conseguiu satisfazer todas as restrições do MIP no tempo estipulado. 

  Recomendações: Para soluções viáveis e soluções relaxadas, recomenda-se aumentar gradualmente o tempo de solução do MIP. Outra possibilidade é diminuir a duração das sub-etapas, que por padrão tem 168h, para 24h, para que os MIP fiquem com menos variáveis e restrições. Para alguns casos de erro no MIP essas soluções podem funcionar, mas pode ser que o problema seja causado por restrições conflitantes (ex: geração mínima obrigatória superior ao combustível disponível), então deve-se rever essas restrições.


### 5.1.3 Tempo de Execução

* **Evolução dos Tempos por Iteração:** O tempo cresce gradualmente devido ao acúmulo de cortes. A fase *backward* é naturalmente mais lenta que a *forward*, pois resolve um volume massivo de x · y subproblemas para construir novos cortes de Benders.
* **Dispersão dos Tempos por Cenário:** Cenários muito lentos indicam ativação de restrições complexas, como decisões discretas (variáveis binárias), acoplamento intertemporal (ex: limites de rampa) ou rigidez do espaço de soluções (sem "folgas" operativas).

Aqui está uma proposta de redação para a seção 5.1.4, integrando o conteúdo original com as novas informações de forma técnica e estruturada:

### 5.1.4 Violações e Penalidades

Em problemas de otimização complexos, como os resolvidos via SDDP , a modelagem de restrições é fundamental. Estas garantem que as variáveis de decisão permaneçam dentro de intervalos operativos aceitáveis. No modelo, as restrições são divididas em duas categorias principais:

1.  **Restrições Rígidas (Hard Constraints):** São condições que devem ser obrigatoriamente cumpridas para que uma solução seja considerada viável (ex: $g \leq G_{max}$).
2.  **Restrições Flexíveis (Soft Constraints):** São restrições que permitem violação, desde que um custo associado seja pago na função objetivo. Essas **penalidades** funcionam como um artifício matemático para evitar a inviabilidade do problema.

**Calibração de Penalidades**
As penalidades devem estar muito bem calibradas para não "sujar" a função objetivo nem gerar cortes de Benders que prejudiquem a convergência do algoritmo. Embora o SDDP configure valores padrão, o usuário tem a flexibilidade de definir valores específicos conforme a necessidade do sistema (consulte a [documentação oficial da PSR](https://docs.psr-inc.com/knowledge/faq/sddp/penalty_summary.html?h=penalties) para detalhes técnicos).

**Análise de Resultados**
Sempre que uma restrição com penalidade associada é violada, o evento é registrado nas abas:

  1.  **Média:** Representa a média da violação entre todos os cenários, fornecendo uma visão da performance geral e do comportamento sistêmico.
  2.  **Máximo:** Identifica o cenário mais crítico (pior caso), essencial para análises de estresse e segurança operativa.

Interpretações:

* **Média vs. Máximo:** Se o valor médio estiver muito próximo do valor máximo, a violação não ocorre apenas em cenários extremos, mas de forma recorrente em quase todos os cenários, indicando um problema estrutural ou de calibração.
* **Ajuste de Modelo:** Violações frequentes que não impactam a operação real podem indicar que a restrição está excessivamente conservadora, podendo ser relaxada no modelo.
* **Sazonalidade e Comportamento:** Se a violação se concentra em períodos específicos (ex: volume mínimo atingido apenas em meses de seca), pode ser necessário aumentar a penalidade para forçar o modelo a tomar decisões antecipadas (como poupar água) para evitar o custo elevado no futuro.
* **Conflitos de Restrições:** É crucial verificar se existem regras contraditórias. O conflito entre duas restrições pode tornar o cumprimento de ambas impossível, forçando violações constantes independentemente do valor da penalidade.

### 5.1.5 Resultados Principais
Aqui está a redação aprimorada para a seção de Custos Marginais, integrando as definições técnicas e as nuances sobre custos negativos e análise estocástica:

---

### 5.1.5 Custos Marginais de Operação (CMO)

O **Custo Marginal de Operação (CMO)** representa o custo de se atender a um incremento unitário de demanda (1 MW adicional) em um determinado patamar de carga e etapa de tempo. Ele é o principal indicador econômico do despacho e reflete o equilíbrio entre oferta e demanda.

#### Comportamento do CMO:

* **CMO Zero:** Ocorre quando o sistema possui excesso de oferta. Atender a um incremento de carga é "indiferente" para o sistema, pois existe energia excedente sem custo variável de produção disponível.
* **CMO Negativo:** Este fenômeno ocorre quando a geração renovável ou hidrelétrica supera a demanda e existe uma **penalidade por vertimento** configurada. 
    > **Lógica Econômica:** Se o sistema é penalizado financeiramente ao verter energia renovável, um aumento na demanda torna-se um "benefício" (evita o pagamento da multa). Assim, o CMO negativo atua como um incentivo para o aumento do consumo ou armazenamento, reduzindo o *curtailment*. Nesses casos, recomenda-se revisar os valores das penalidades de renováveis e o volume de energia rejeitada.

#### Análise de Risco e Distribuição (Percentis):

A análise do CMO não deve se limitar à média, mas sim à distribuição estocástica entre os cenários:

* **P10 - Excesso de Oferta:** Se o percentil 10 for igual a zero, indica que em pelo menos **10% dos casos simulados** há excesso de energia no sistema.
* **P90 - Estresse Sistêmico:** Se o P90 for significativamente superior à média, o sistema apresenta alta volatilidade e risco. Isso aponta para cenários de baixa probabilidade, mas de altíssimo impacto financeiro, onde o custo de operação dispara.
* **Volatilidade:** A dispersão entre os percentis ajuda a identificar a sensibilidade do sistema a eventos hidrológicos ou climáticos extremos.

#### Geração e Balanço de Energia:

O equilíbrio entre oferta e demanda é a base da viabilidade operativa. O modelo analisa o atendimento da carga através da equação fundamental:

$$\text{Geração} + \text{Déficit} = \text{Demanda}$$

Onde a **Geração** é a soma das contribuições de cada agente (Hidro, Térmica, Renovável, etc.). 


* **Gargalos de Trasnmissão:** Se houver geração disponível em um submercado mas déficit em outro, o problema pode não ser a oferta total, mas sim restrições de transmissão que impedem o fluxo de energia.
* **Geração abaixo do esperado:** Caso algum agente apresente geração inferior ao esperado, é importante verificar os custos associados a ele, bem como identificar possíveis restrições de outros agentes que possam estar limitando ou desincentivando essa geração.

#### Risco de Déficit: 
Percentagem de cenários onde faltou energia em pelo menos uma etapa do ano, ou seja, se 100%, em todos os cenários, em alguma etapa do ano, houve défict.


#### Energia Natural Afluente (ENA): 
Compara a energia afluente com a dispersão de custos (períodos úmidos costumam apresentar maior dispersão).

