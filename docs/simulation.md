# Qualidade da Simulação (5.1.2)

**Área diagnóstica:** Qualidade da operação simulada — custos, dispersão e status do solver.

---

## O que é a aba Simulação

A aba **Simulação** avalia se a operação produzida pelo modelo é realista e de boa qualidade. Os principais indicadores são a composição dos custos, a dispersão entre cenários e o status de solução dos MIPs horários.

---

## 1. Porções do Custo Operativo Total

### Regra dos 80%
O **Custo Operativo** (geração térmica, combustível, custo de água) deve representar **pelo menos 80% do Custo Total**.

$$\frac{\text{Custo Operativo}}{\text{Custo Total}} \geq 80\%$$

**Custo Total = Custo Operativo + Soma de todos os Custos de Penalidade**

### Interpretação

| Proporção do Custo Operativo | Diagnóstico |
|---|---|
| ≥ 80% | Operação realista — custos refletem decisões operativas reais |
| 60–80% | Alerta — verificar quais penalidades estão elevadas |
| < 60% | Crítico — operação irreal; o modelo está violando restrições sistematicamente para viabilizar o problema |

**Quando penalidades dominam:** O modelo está "pagando multas" em vez de operar normalmente. Isso significa que as restrições não estão sendo respeitadas na operação, gerando resultados sem validade prática.

**Ação:** Identificar as etapas e restrições com maiores penalidades. Consulte [docs/violations.md](violations.md).

---

## 2. Custo Operativo Médio por Etapa

Mostra a evolução do custo ao longo do horizonte de planejamento.

- **Picos de custo** → etapas de maior estresse do sistema (geralmente período seco)
- **Concentração de violações** → etapas onde penalidades aparecem junto ao custo operativo elevado

**Use:** `df_get_summary` agrupado por `Stage` para ver a evolução temporal dos custos.

---

## 3. Dispersão de Custos por Etapa (P10 / P90)

| Percentil | Significado |
|---|---|
| **P10** | Cenários mais favoráveis — hidrologias boas, baixo custo |
| **P90** | Cenários críticos — hidrologias secas, alto custo |

**Correlação esperada com ENA:**
- Período **úmido** → maior variabilidade (P90/P10 mais afastados)
- Período **seco** → mais previsível (P90/P10 mais próximos)

Se a dispersão não se correlacionar com ENA, investigue se há penalidades ou restrições adicionando ruído artificial.

---

## 4. Estado da Solução MIP (Simulação Horária)

Aplicável apenas quando a simulação usa **sub-etapas horárias** com variáveis binárias.

### Estados e Significados

| Estado | Descrição | Confiabilidade |
|---|---|---|
| **Ótima** | Solver atingiu o critério de parada | Alta |
| **Factível** | Solução viável encontrada, sem garantia de otimalidade | Média |
| **Relaxada** | Variáveis binárias assumiram valores contínuos [0,1] | Baixa |
| **Erro** | Solver não conseguiu satisfazer todas as restrições no tempo estipulado | Muito baixa |

### Recomendações por Estado

**Para Factível e Relaxada:**
1. Aumentar gradualmente o tempo de solução do MIP
2. Diminuir a duração das sub-etapas (de 168h para 24h) → MIPs menores com menos variáveis

**Para Erro:**
1. Tentar as soluções acima
2. Verificar se há restrições conflitantes (ex: geração mínima obrigatória > combustível disponível)
3. Revisar as restrições em conflito

### Limiar de Alerta
- Se > 5% das etapas/cenários apresentam estado `Relaxada` ou `Erro` → investigação prioritária
- Se todas as etapas de um período específico apresentam `Erro` → provável conflito de restrições naquele período

---

## Ferramentas Relevantes

| Diagnóstico | Ferramenta | Parâmetros principais |
|---|---|---|
| Verificar regra dos 80% | `df_analyze_composition` | `target_cost_col`, `all_cost_cols_json`, `min_threshold=80.0` |
| Custos médios por etapa | `df_get_summary` | `{"Operating_Cost": ["mean","std","min","max"]}` |
| Dispersão P10/P90 | `df_get_summary` | `{"P10": ["mean"], "P90": ["mean","max"]}` |
| Status MIP por etapa | `df_get_summary` | colunas de status |

---

## Limiares de Referência

| Métrica | Normal | Alerta | Crítico |
|---|---|---|---|
| Custo Operativo / Total | ≥ 80% | 60–80% | < 60% |
| % etapas com status Ótima | ≥ 95% | 80–95% | < 80% |
| % etapas com status Erro | 0% | < 2% | ≥ 5% |
