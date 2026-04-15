# Custos Marginais, ENA e Déficit (5.1.5)

**Área diagnóstica:** Equilíbrio econômico do sistema — se os preços de energia refletem a realidade e se a demanda é atendida.

---

## Custo Marginal de Operação (CMO)

O **CMO** representa o custo de atender a um incremento unitário de demanda (1 MW adicional) em uma determinada etapa e patamar de carga. É o **principal indicador econômico do despacho**.

$$CMO = \frac{\partial \text{Custo Total}}{\partial \text{Demanda}}$$

---

## Comportamento do CMO

### CMO Positivo (Normal)
O sistema tem custos para atender demanda adicional. Valor reflete o custo da usina marginal (geralmente térmica de maior custo variável).

### CMO Zero
**Diagnóstico:** O sistema possui **excesso de oferta**. Atender incremento de carga é "indiferente" — há energia excedente sem custo variável disponível.

Causas comuns:
- Muita geração renovável em período úmido
- Reservatórios cheios sem possibilidade de vertimento penalizado

### CMO Negativo
**Diagnóstico:** Fenômeno ocorre quando **geração renovável ou hidrelétrica supera a demanda** E existe uma **penalidade por vertimento configurada**.

**Lógica Econômica Completa:**
> Se o sistema é penalizado financeiramente ao verter energia renovável, um aumento na demanda torna-se um **benefício econômico** — consome energia que de outra forma seria vertida com custo. Assim, o CMO negativo é um incentivo para aumentar consumo ou armazenamento.

**O que verificar:**
1. Volume de energia rejeitada (curtailment) no período
2. Valor da penalidade de vertimento configurada
3. Se a penalidade está superestimada (gerando CMO excessivamente negativo)

**Ação:** Revisar valores das penalidades de renováveis e o volume de energia rejeitada.

---

## Análise de Risco — Distribuição Estocástica (Percentis)

A análise do CMO não deve se limitar à média. A distribuição entre cenários revela riscos sistêmicos:

| Percentil | Significado | Alerta quando |
|---|---|---|
| **P10** | 10% dos cenários mais favoráveis | P10 = 0 → excesso de oferta em ≥10% dos casos |
| **Média** | Expectativa central | Referência base |
| **P90** | 10% dos cenários mais críticos | P90 >> Média → alta volatilidade financeira |

### P10 = 0
Indica que em **pelo menos 10% dos cenários simulados** há excesso de energia no sistema.
Interpretar junto com ENA — geralmente coincide com anos de alta afluência.

### P90 >> Média (Alta Volatilidade)
Indica cenários de **baixa probabilidade, mas altíssimo impacto financeiro**.
O sistema é muito sensível a eventos hidrológicos/climáticos extremos.

**Use:** `df_cross_correlation` (ENA vs CMO) para quantificar a sensibilidade hídrica.

---

## Geração e Balanço de Energia

### Equação Fundamental
$$\text{Geração} + \text{Déficit} = \text{Demanda}$$

Onde Geração = Hidro + Térmica + Renovável + Intercâmbio

### Gargalos de Transmissão
**Sinal:** Geração disponível em um submercado, mas déficit em outro.

**Diagnóstico:** O problema não é falta de geração total — é **restrição de transmissão** impedindo o fluxo entre submercados.

**Como identificar:** Comparar CMO entre submercados. CMO muito diferente entre regiões na mesma etapa → gargalo de transmissão.

### Geração Abaixo do Esperado
Se um agente específico gera menos que o esperado:
1. Verificar custos variáveis associados a ele
2. Verificar se há restrições de outros agentes que **limitam ou desincentivam** essa geração
3. Verificar disponibilidade de combustível ou insumo

---

## Energia Natural Afluente (ENA)

A **ENA** mede a energia potencial das vazões naturais nos rios. É o principal driver de incerteza do sistema hidrotérmico.

### Correlação ENA ↔ Custo

| Período | ENA | Comportamento esperado |
|---|---|---|
| Úmido | Alta | Maior variabilidade de custo (mais cenários possíveis) |
| Seco | Baixa | Custo mais previsível e alto |

**Ferramenta:** `df_cross_correlation` entre ENA e CMO → Pearson r próximo de -1 confirma relação inversa esperada (mais ENA = menor custo).

Se a correlação for fraca (|r| < 0.5), investigar se há fontes de incerteza adicionais além da hidrologia.

---

## Risco de Déficit

**Definição:** Percentagem de cenários onde faltou energia em **pelo menos uma etapa** do horizonte.

| Valor | Interpretação |
|---|---|
| 0% | Nenhum cenário com déficit — sistema seguro |
| < 5% | Risco baixo — apenas cenários extremos |
| 5–20% | Risco moderado — revisar expansão ou despacho |
| > 20% | Risco alto — ação urgente necessária |
| 100% | Em **todos** os cenários houve déficit em alguma etapa — problema crítico |

---

## Ferramentas Relevantes

| Diagnóstico | Ferramenta | Parâmetros |
|---|---|---|
| CMO estatísticas gerais | `df_get_summary` | `{"CMO_mean":["mean","min"],"CMO_P10":["min"],"CMO_P90":["mean","max"]}` |
| Detectar CMO negativo | `df_get_summary` | checar `min` de `CMO_mean` |
| Correlação ENA vs CMO | `df_cross_correlation` | `col_a="ENA_mean"`, `col_b="CMO_mean"`, `join_on="Stage"` |
| Risco de déficit por etapa | `df_analyze_composition` | `target_cost_col="Deficit_frequency"` |
| Balanço de geração | `df_get_summary` | somar colunas de geração por fonte |

---

## Limiares de Referência

| Métrica | Normal | Alerta | Crítico |
|---|---|---|---|
| CMO médio | > 0 | = 0 | < 0 |
| % cenários P10 = 0 | < 10% | 10–30% | > 30% |
| Razão P90/Média | < 2× | 2–5× | > 5× |
| Risco de déficit | < 5% | 5–20% | > 20% |
| Correlação ENA/CMO (|r|) | > 0.7 | 0.4–0.7 | < 0.4 |
