# Tempo de Execução (5.1.3)

**Área diagnóstica:** Performance computacional — se o algoritmo está rodando de forma eficiente.

---

## Evolução dos Tempos por Iteração

O tempo de execução **cresce gradualmente** ao longo das iterações. Isso é **normal e esperado** — a cada iteração, novos cortes de Benders são adicionados, aumentando o tamanho dos subproblemas.

### Relação Forward / Backward

| Fase | Característica | Tempo relativo |
|---|---|---|
| **Forward** | Simula N cenários propagando o estado do sistema | Mais rápida |
| **Backward** | Resolve x·y subproblemas para construir novos cortes de Benders | Mais lenta |

A fase **Backward é naturalmente mais lenta** que a Forward porque resolve um volume massivo de subproblemas a cada iteração para construir os cortes que aproximam a FCF.

**Alerta:** Se Forward > Backward → investigar se os cortes estão sendo construídos corretamente.

---

## Dispersão dos Tempos por Cenário

Cenários com tempo de solução muito acima da média indicam ativação de restrições complexas:

| Causa | Sinal | O que verificar |
|---|---|---|
| **Variáveis binárias** | Cenários com MIP complexo demoram muito mais | Status da solução MIP — ver [docs/simulation.md](simulation.md) |
| **Acoplamento intertemporal** | Limites de rampa, restrições de startup/shutdown | Restrições intertemporal no modelo |
| **Rigidez do espaço de soluções** | Poucos graus de liberdade (sem "folgas" operativas) | Verificar limites operativos e capacidades instaladas |

---

## Padrões de Tempo e Seus Significados

| Padrão observado | Diagnóstico provável |
|---|---|
| Crescimento linear suave | Normal — acúmulo gradual de cortes |
| Salto abrupto em uma iteração | Nova restrição ativada ou mudança de regime |
| Backward muito lenta desde o início | Alta complexidade do modelo (muitas binárias, muitas restrições) |
| Dispersão crescente entre cenários | Ativação progressiva de restrições complexas em mais cenários |
| Tempo estabiliza após muitas iterações | Cortes cobrem bem o espaço de estados — perto da convergência |

---

## Ferramentas Relevantes

| Diagnóstico | Ferramenta | Parâmetros |
|---|---|---|
| Tempo médio por fase | `df_get_summary` | `{"Forward_Time":["mean","max"],"Backward_Time":["mean","max"]}` |
| Crescimento de tempo (estagna?) | `df_analyze_stagnation` | `target_col="Total_Time"` |
| Dispersão por cenário | `df_get_summary` | `{"Solve_Time":["mean","std","max"]}` |
| Correlação tempo vs. iteração | `df_analyze_bounds` | rastrear `Total_Time` ao longo de `Iteration` |

---

## Limiares de Referência

| Métrica | Normal | Alerta |
|---|---|---|
| Razão Backward/Forward | 2–10× | < 1× (backward mais rápida que forward) |
| CV do tempo por cenário | < 50% | > 100% (alta dispersão) |
| Crescimento total de tempo (iter 1 → última) | < 5× | > 20× |
