# Índice de Documentação — Diagnóstico SDDP

Este arquivo é o **ponto de entrada** para o agente identificar qual documentação e qual árvore de decisão usar para cada pergunta.

---

## Lookup por Palavras-chave

| Tópico / Palavras-chave | Arquivo de Documentação | Árvore de Decisão |
|---|---|---|
| convergência, zinf, zsup, benders, iteração, cortes, política, FCF, não convergiu | [docs/convergence.md](convergence.md) | `decision-trees/convergence.json` |
| simulação, custo operativo, 80%, penalidade, MIP, ótimo, relaxado, factível, erro, solver | [docs/simulation.md](simulation.md) | `decision-trees/simulation.json` |
| tempo de execução, backward, forward, cenário lento, runtime, subproblemas | [docs/execution-time.md](execution-time.md) | — |
| violação, penalidade, restrição, meta, soft constraint, hard constraint, seca, calibração | [docs/violations.md](violations.md) | `decision-trees/violations.json` |
| CMO, custo marginal, déficit, ENA, energia afluente, negativo, P10, P90, geração, balanço, transmissão | [docs/marginal-costs.md](marginal-costs.md) | `decision-trees/marginal-costs.json` |

---

## Fluxo de Uso pelo Agente

```
1. Receber pergunta do usuário
2. Identificar palavras-chave → localizar linha nesta tabela
3. Ler o arquivo de documentação correspondente (contexto técnico)
4. Carregar a árvore de decisão correspondente
5. Executar o workflow de extração de dados guiado pela árvore
6. Sintetizar resposta com dados + documentação
```

---

## Mapeamento de CSVs por Área

Para saber quais arquivos CSV correspondem a cada área diagnóstica, consulte [docs/csv-schema.md](csv-schema.md).

Resumo rápido:

| Área | Arquivo CSV esperado (nomes típicos) |
|---|---|
| Convergência / Política | `convergence*.csv`, `policy*.csv` |
| Custo Operativo / Simulação | `cost*.csv`, `simulation*.csv`, `operating*.csv` |
| Violações e Penalidades | `violation*.csv`, `penalty*.csv` |
| CMO | `marginal_cost*.csv`, `cmo*.csv` |
| ENA / Energia Afluente | `inflow*.csv`, `ena*.csv` |
| Déficit | `deficit*.csv` |
| Tempo de Execução | `runtime*.csv`, `time*.csv` |

> Sempre chame `get_avaliable_results(study_path)` primeiro para listar os CSVs reais do caso. Se os nomes diferirem do padrão acima, use `df_get_columns` para verificar o conteúdo.

---

## Quando Usar Domain Tools vs Generic Tools

| Situação | Abordagem |
|---|---|
| Pergunta de alto nível sobre um diagnóstico SDDP padrão | Use **domain tools** primeiro (elas já conhecem o schema) |
| CSV com estrutura não padrão ou análise customizada | Use **generic tools** (`df_get_columns` → `df_get_summary` → análise específica) |
| Precisar de correlação entre dois arquivos | Use `df_cross_correlation` (generic tool) |
| Detecção de estagnação em qualquer série | Use `df_analyze_stagnation` (generic tool) |
