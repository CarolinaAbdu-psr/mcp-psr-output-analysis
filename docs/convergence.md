# Convergência e Política (5.1.1)

**Área diagnóstica:** Qualidade da otimização — se a Função de Custo Futuro (FCF) foi bem construída.

---

## O que é a aba Política

A aba **Política** exibe os resultados do processo de otimização estocástica dual dinâmica (SDDP). O objetivo é verificar se o algoritmo convergiu, ou seja, se a estratégia de operação futura foi corretamente aprendida.

---

## Parâmetros Fundamentais

### Limite Inferior — Z_inf
O valor da função objetivo na **primeira etapa**. É um limite inferior porque a FCF é aproximada por cortes de Benders que estão sempre **abaixo ou no nível** da função real convexa:

$$FCF(x) \geq \sum (\text{Cortes de Benders})$$

Z_inf só pode crescer com mais iterações — cada novo corte melhora a aproximação.

### Limite Superior — Z_sup
O **custo total da operação simulada**. No caso estocástico, é a média aritmética dos custos de N cenários de vazões:

$$\bar{Z}_{sup} = \frac{1}{N} \sum_{n=1}^{N} CT(n)$$

---

## Critérios de Convergência

### Caso Determinístico
$$\frac{Z_{sup} - Z_{inf}}{Z_{sup}} \leq \text{Tolerância}$$

### Caso Estocástico
Z_inf deve pertencer ao intervalo de confiança de 95% do custo médio da fase forward:

$$Z_{inf} \in \left[ \bar{Z}_{sup} - 1{,}96 \frac{\sigma_{Z_{sup}}}{\sqrt{N}};\; \bar{Z}_{sup} + 1{,}96 \frac{\sigma_{Z_{sup}}}{\sqrt{N}} \right]$$

---

## Diagnóstico de Não-Convergência

### Causa 1 — Iterações Insuficientes
**Sinal:** Z_inf ainda está subindo nas últimas iterações (tendência de aproximação visível, mas não atingiu a tolerância).
**Solução:** Aumentar o número máximo de iterações.

### Causa 2 — Estagnação por Penalidades Excessivas
**Sinal:** Z_inf parou de evoluir antes de atingir o critério.
**Mecanismo:** Penalidades muito altas criam cortes de Benders "dominados" — eles ficam abaixo dos cortes reais e não contribuem para aproximar a FCF. O algoritmo para de aprender.
**Solução:** Revisar calibração de penalidades. Consulte [docs/violations.md](violations.md) para orientação.

### Causa 3 — Amostra Insuficiente de Forward
**Sinal:** Z_inf estagna com poucos cenários de forward (N pequeno).
**Mecanismo:** Com poucos cenários, a fase forward não explora regiões suficientes do espaço de estados, resultando em cortes imprecisos.
**Solução:** Aumentar o número de séries na fase forward.

---

## Política vs. Simulação Final

Este gráfico compara o valor esperado da função objetivo da **última iteração da política** com os **resultados da simulação final**. Se a simulação final ficar fora do intervalo de confiança da política:

| Causa | Diagnóstico | Solução |
|---|---|---|
| **Política incompleta** | FCF não convergiu → sinais de custo imprecisos | Resolver a não-convergência primeiro |
| **Não-convexidade (MIP)** | Variáveis binárias em simulação horária criam descontinuidades | Ativar: Configuração → Estratégia de Solução → Não-Convexidade da Política |
| **Discrepância de amostragem** | FCF copiada de outro caso sem cobrir cenários extremos usados na simulação | Regenerar política com os mesmos cenários da simulação |
| **Esatado da solução horária não é ótimo** | Caso o estado da solução horária seja diferente de solução ótima, pode haver deslocamentos entre a simulação e a 
política | Aumentar o tempo de solução para o MIP | 

---

## Ferramentas Relevantes

| Diagnóstico | Ferramenta | Parâmetros principais |
|---|---|---|
| Verificar gap Zinf/Zsup | `df_analyze_bounds` | `target_col="Zinf"`, bounds = CI, `reference_val_col="Zsup"` |
| Verificar se Zinf estagna | `df_analyze_stagnation` | `target_col="Zinf"`, `window_size=5` |
| Verificar crescimento de cortes | `df_analyze_stagnation` | `target_col="Cuts"` |
| Verificar se penalidades dominam | `df_analyze_composition` | `target_cost_col="Operating_Cost"`, `min_threshold=80.0` |

---

## Limiares de Referência

| Métrica | Normal | Alerta | Crítico |
|---|---|---|---|
| Gap Zinf/Zsup | ≤ tolerância configurada | 1–5× tolerância | > 5× tolerância |
| Zinf estagnado (últimas 5 iter.) | CV < 1% | CV 1–3% | CV > 3% sem tendência |
| Custo operativo / total | ≥ 80% | 60–80% | < 60% |
