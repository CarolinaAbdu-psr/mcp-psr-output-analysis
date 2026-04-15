# Violações e Penalidades (5.1.4)

**Área diagnóstica:** Qualidade da modelagem de restrições — se o sistema está respeitando os limites operativos.

---

## Tipos de Restrições no SDDP

### Restrições Rígidas (Hard Constraints)
Condições **obrigatórias** para que uma solução seja viável. Exemplo:
$$g \leq G_{max} \quad \text{(geração não pode exceder capacidade instalada)}$$

Não podem ser violadas sob nenhuma circunstância.

### Restrições Flexíveis (Soft Constraints)
Permitem violação, desde que um **custo de penalidade** seja pago na função objetivo. Funcionam como artifício matemático para evitar infeasibility:

$$\text{Objetivo} += \text{Penalidade} \times \text{Magnitude da Violação}$$

Exemplos: meta de reservatório, nível mínimo de armazenamento, limite de rampa.

---

## Calibração de Penalidades

As penalidades devem ser **bem calibradas**. Penalidades mal configuradas causam dois problemas distintos:

| Penalidade | Problema gerado |
|---|---|
| **Muito baixa** | O modelo prefere violar a restrição em vez de operar corretamente → operação irreal |
| **Muito alta** | Cria cortes de Benders "dominados" que não aproximam corretamente a FCF → convergência prejudicada |

**Regra prática:** A penalidade deve ser maior que o custo real de violar a restrição no sistema, mas não tão alta que distorça a função objetivo.

Para detalhes técnicos de penalidades padrão, consulte: [docs.psr-inc.com/knowledge/faq/sddp/penalty_summary](https://docs.psr-inc.com/knowledge/faq/sddp/penalty_summary.html).

---

## Análise de Resultados de Violação

### Dimensões de Análise

| Dimensão | O que mede | Quando usar |
|---|---|---|
| **Média** | Performance geral do sistema (todos os cenários) | Comportamento sistêmico |
| **Máximo** | Pior cenário (análise de estresse) | Segurança operativa |

### Interpretações-Chave

#### Média ≈ Máximo
**Diagnóstico:** A violação não ocorre apenas em cenários extremos — é **recorrente em quase todos os cenários**. Indica problema **estrutural** ou de calibração.

Possíveis causas:
- Restrição impossível de cumprir com os recursos disponíveis
- Penalidade muito baixa (modelo prefere violar)
- Conflito entre duas restrições

#### Violação Sazonal (concentrada em período seco)
**Diagnóstico:** A restrição está sendo violada apenas nos meses de seca.

**Mecanismo:** O modelo não está tomando decisões antecipadas de conservação de água porque a penalidade não é alta o suficiente para justificar o custo de oportunidade.

**Solução:** Aumentar a penalidade para forçar o modelo a poupar água nas etapas úmidas, antecipando a necessidade futura.

#### Conflito de Restrições
**Diagnóstico:** Violações constantes independentemente do valor da penalidade.

**Sinal:** Ao aumentar a penalidade, a frequência de violação não reduz.

**Causa:** Duas ou mais restrições são mutuamente excludentes (ex: geração mínima obrigatória + limite de combustível disponível).

**Solução:** Revisar as restrições e identificar o conflito lógico.

#### Restrição Excessivamente Conservadora
**Diagnóstico:** Violações frequentes que não impactam a operação real.

**Sinal:** A violação ocorre, mas o sistema opera normalmente sem consequências práticas.

**Solução:** Relaxar a restrição no modelo (ou aumentar o limite permitido).

---

## Padrões de Alerta por Período

| Padrão | Diagnóstico | Ação |
|---|---|---|
| Violação só em meses de seca | Penalidade insuficiente para antecipar conservação | Aumentar penalidade |
| Violação em todos os meses | Problema estrutural ou conflito | Revisar restrições |
| Violação aleatória (cenários extremos) | Normal — apenas cenários muito secos | Monitorar P90 |
| Violação crescente ao longo do horizonte | Acúmulo de restrições ao longo do tempo | Verificar acoplamento intertemporal |

---

## Ferramentas Relevantes

| Diagnóstico | Ferramenta | Parâmetros principais |
|---|---|---|
| Média e máximo das violações | `df_get_summary` | `{"Mean_Violation": ["mean","max"], "Max_Violation": ["mean","max"]}` |
| Razão Média/Máximo por etapa | `df_analyze_composition` | usar `Mean_Violation` como target, `all_cols = [Mean, Max]` |
| Sazonalidade da violação | `df_get_summary` por `Stage` | agrupa por etapa para ver concentração temporal |
| Impacto nas penalidades vs operativo | `df_analyze_composition` | verificar regra dos 80% em custo total |

---

## Limiares de Referência

| Métrica | Normal | Alerta | Crítico |
|---|---|---|---|
| Média/Máximo da violação | < 0.5 (violação rara) | 0.5–0.9 | > 0.9 (estrutural) |
| % cenários com violação | < 10% | 10–50% | > 50% |
| % etapas com penalidade > 20% do custo total | 0% | < 5% | > 10% |
