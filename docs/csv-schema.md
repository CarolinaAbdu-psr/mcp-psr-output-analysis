# Schema de CSVs do SDDP — Mapeamento de Arquivos e Colunas

Este documento mapeia os conceitos diagnósticos do SDDP para os arquivos CSV típicos e suas colunas.

> **Como usar:** Ao receber a lista de arquivos de `get_avaliable_results`, compare com os padrões abaixo para identificar qual CSV corresponde a cada análise. Se houver dúvida, use `df_get_columns(file_path)` para inspecionar.

---

## Como Descobrir Colunas de um CSV Desconhecido

Se o arquivo não bate com nenhum padrão abaixo:

```
1. df_get_columns(file_path)          → lista todas as colunas
2. df_get_summary(file_path, {"col": ["mean","min","max"]})  → entenda a escala dos dados
3. Procure colunas com nomes como: Stage, Iteration, Scenario, Step, Etapa, Cenário
   → estas são geralmente as dimensões de indexação
4. Colunas numéricas com valores monetários (R$, US$, k$) → custos
5. Colunas com valores em MW, MWh → energia/geração
6. Colunas com valores entre 0-1 → percentuais ou probabilidades
```

---

## 1. Convergência / Política

**Arquivo típico:** `convergence.csv`, `policy_convergence.csv`, `zinf_zsup.csv`

| Coluna esperada | Tipo | Descrição |
|---|---|---|
| `Iteration` | int | Número da iteração |
| `Zinf` | float | Limite inferior (primeira etapa + cortes de Benders) |
| `Zsup` | float | Limite superior (custo médio simulado) |
| `Lower_CI` | float | Limite inferior do intervalo de confiança de Zsup |
| `Upper_CI` | float | Limite superior do intervalo de confiança de Zsup |
| `Gap` ou `Gap(%)` | float | Diferença relativa (Zsup - Zinf) / Zsup |
| `Cuts` | int | Número acumulado de cortes de Benders |

**Uso com ferramentas:**
- `df_analyze_bounds`: `target_col="Zinf"`, `lower_bound_col="Lower_CI"`, `upper_bound_col="Upper_CI"`, `reference_val_col="Zsup"`, `iteration_col="Iteration"`
- `df_analyze_stagnation`: `target_col="Zinf"` ou `target_col="Gap"`

---

## 2. Custo Operativo / Simulação

**Arquivo típico:** `cost_summary.csv`, `simulation_cost.csv`, `operating_cost.csv`

| Coluna esperada | Tipo | Descrição |
|---|---|---|
| `Stage` ou `Etapa` | int/str | Etapa de tempo |
| `Operating_Cost` ou `Custo Operativo` | float | Custo operativo (geração, combustível) |
| `Penalty_Cost` ou `Custo Penalidade` | float | Soma de todos os custos de penalidade |
| `Total_Cost` ou `Custo Total` | float | Custo total (operativo + penalidades) |
| `P10`, `P90` | float | Percentis 10 e 90 (cenários favorável e crítico) |

**Uso com ferramentas:**
- `df_analyze_composition`: `target_cost_col="Operating_Cost"`, `all_cost_cols_json='["Operating_Cost","Penalty_Cost"]'`, `label_col="Stage"`, `min_threshold=80.0`

---

## 3. Status da Solução MIP (Simulação Horária)

**Arquivo típico:** `mip_status.csv`, `solution_status.csv`

| Coluna esperada | Tipo | Descrição |
|---|---|---|
| `Stage` | int | Etapa |
| `Scenario` | int | Cenário |
| `Status` | str | `Optimal`, `Feasible`, `Relaxed`, `Error` |
| `Solve_Time` | float | Tempo de solução do MIP (segundos) |

**Uso com ferramentas:**
- `df_get_summary`: contar ocorrências de cada status por coluna
- Filtre por `Status != "Optimal"` para identificar problemas

---

## 4. Violações e Penalidades

**Arquivo típico:** `violations.csv`, `penalty_summary.csv`

| Coluna esperada | Tipo | Descrição |
|---|---|---|
| `Stage` ou `Etapa` | int | Etapa |
| `Constraint` ou `Restrição` | str | Nome da restrição violada |
| `Mean_Violation` | float | Média da violação entre todos os cenários |
| `Max_Violation` | float | Violação máxima (pior cenário) |
| `Frequency(%)` | float | % de cenários onde a violação ocorreu |

**Uso com ferramentas:**
- `df_get_summary`: `{"Mean_Violation": ["mean","max"], "Max_Violation": ["mean","max"]}`
- Razão `Mean/Max` próxima de 1.0 → violação estrutural (ocorre em quase todos os cenários)

---

## 5. Custo Marginal de Operação (CMO)

**Arquivo típico:** `marginal_cost.csv`, `cmo.csv`, `spot_price.csv`

| Coluna esperada | Tipo | Descrição |
|---|---|---|
| `Stage` ou `Etapa` | int | Etapa |
| `CMO_mean` ou `Mean` | float | CMO médio |
| `CMO_P10` ou `P10` | float | Percentil 10 (excesso de oferta) |
| `CMO_P90` ou `P90` | float | Percentil 90 (estresse sistêmico) |
| `CMO_max` ou `Max` | float | CMO máximo (pior cenário) |
| `Submarket` | str | Submercado (SE, S, NE, N) |

**Alertas:**
- `CMO_mean < 0` → possível penalidade de vertimento ativa
- `CMO_P10 == 0` → excesso de oferta em ≥10% dos cenários
- `CMO_P90 / CMO_mean >> 1` → alta volatilidade

---

## 6. Energia Natural Afluente (ENA)

**Arquivo típico:** `inflow_energy.csv`, `ena.csv`

| Coluna esperada | Tipo | Descrição |
|---|---|---|
| `Stage` | int | Etapa |
| `ENA_mean` | float | ENA média |
| `ENA_P10` | float | Período úmido / favorável |
| `ENA_P90` | float | Período seco / crítico |

**Uso com ferramentas:**
- `df_cross_correlation`: correlacionar `ENA_mean` com `CMO_mean` para confirmar sensibilidade hídrica

---

## 7. Déficit

**Arquivo típico:** `deficit.csv`, `energy_deficit.csv`

| Coluna esperada | Tipo | Descrição |
|---|---|---|
| `Stage` | int | Etapa |
| `Deficit_mean` | float | Déficit médio por etapa |
| `Deficit_frequency(%)` | float | % de cenários com déficit nesta etapa |
| `Submarket` | str | Submercado |

**Alerta:** `Deficit_frequency = 100%` → em todos os cenários houve déficit nesta etapa (crítico).

---

## 8. Tempo de Execução

**Arquivo típico:** `runtime.csv`, `execution_time.csv`

| Coluna esperada | Tipo | Descrição |
|---|---|---|
| `Iteration` | int | Iteração |
| `Forward_Time` | float | Tempo da fase forward (segundos) |
| `Backward_Time` | float | Tempo da fase backward (segundos) |
| `Total_Time` | float | Tempo total da iteração |
| `Scenario` | int | Cenário (para dispersão por cenário) |

**Normal:** Backward > Forward; crescimento gradual com iterações (acúmulo de cortes).
