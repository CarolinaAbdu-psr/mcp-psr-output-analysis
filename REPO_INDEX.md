# REPO_INDEX — mcp-psr-output-analysis

> **Auto-alimentado pela skill `repo-edit`.** Sempre que você usar `/repo-edit` e fizer alterações neste repositório, atualize este arquivo antes de encerrar a sessão.
>
> **Leia este arquivo primeiro** em qualquer sessão de edição. Ele é o mapa mais rápido do estado atual do repositório.

---

## Estrutura de arquivos

```
mcp-psr-output-analysis/
│
├── psr/outputanalysismcp/
│   ├── server.py              ← Exposição das tools via FastMCP. Ponto de entrada da API.
│   ├── dataframe_functions.py ← Implementação pura das análises (sem MCP). Funções reutilizáveis.
│   └── case_information.py    ← Extração de metadados do HTML do SDDP
│
├── decision-trees/
│   ├── decision_graph.json    ← GRAFO EM DESENVOLVIMENTO. Novo formato de árvore com tools[].
│   ├── convergence.json       ← Árvore de convergência estável (usado em produção)
│   ├── simulation.json        ← Árvore de simulação estável
│   ├── violations.json        ← Árvore de violações estável
│   ├── marginal-costs.json    ← Árvore de CMO estável
│   └── master.json            ← Roteador geral entre árvores
│
├── docs/
│   ├── index.md               ← Lookup de palavras-chave → área diagnóstica
│   ├── convergence.md         ← Contexto técnico de convergência Zinf/Zsup
│   ├── simulation.md          ← Contexto técnico de qualidade da simulação
│   ├── violations.md          ← Contexto técnico de violações e penalidades
│   ├── marginal-costs.md      ← Contexto técnico de CMO, ENA e déficit
│   ├── execution-time.md      ← Contexto técnico de tempo de execução
│   └── csv-schema.md          ← Mapeamento CSV → colunas SDDP
│
├── skills/
│   ├── sddp-diagnose.md       ← Skill de diagnóstico de casos SDDP
│   └── repo-edit.md           ← Skill de edição deste repositório (esta skill)
│
├── REPO_INDEX.md              ← ESTE ARQUIVO. Mapa vivo do repositório.
├── TOOLS.md                   ← Referência de todas as MCP tools (formato tabela)
├── README.md                  ← Instalação e configuração do servidor
└── sddp_html_to_csv.py        ← Parser HTML → CSV para dashboards SDDP
```

---

## MCP Tools disponíveis

Definidas em `server.py`, implementadas em `dataframe_functions.py`.

### Inicialização e metadados

| Tool | Assinatura resumida | Para que serve |
|---|---|---|
| `extract_html_results` | `(study_path)` | Parseia o HTML do SDDP e exporta todos os gráficos como CSV em `results/` |
| `get_avaliable_results` | `(study_path)` | Define `RESULTS_FOLDER`. Lê `_index.json` e retorna bloco por arquivo com tipo, título, unidades, linhas e **nomes exatos das colunas**. Substitui `df_get_columns` para arquivos exportados do dashboard. **Chamar sempre primeiro.** |
| `get_case_information` | `(study_path)` | Extrai metadados do HTML: etapas, séries, horizonte, versão, não-convexidades |
| `get_workflow_doc` | `(doc_name)` | Carrega um arquivo de `docs/` (index, convergence, simulation, violations, marginal-costs, execution-time, csv-schema) |
| `get_diagnostic_graph` | `()` | Carrega e formata `decision_graph.json` com nós, arestas ordenadas por prioridade e regras de travessia |
| `get_conclusion_documentation` | `(search_intent, top_k=2)` | Busca por similaridade de palavras-chave nas seções de `Results.md`; retorna os top_k trechos mais relevantes |

### Inspeção de DataFrames

| Tool | Assinatura resumida | Para que serve |
|---|---|---|
| `df_get_head` | `(file_path, n=5)` | Primeiras N linhas + shape. Revela escala e formato dos dados. |

> `df_get_columns` e `df_get_size` foram removidos — colunas e shape já estão em `get_avaliable_results`.

### Estatísticas

| Tool | Assinatura resumida | Para que serve |
|---|---|---|
| `df_get_summary` | `(file_path, operations_json)` | Média / std / min / max em colunas selecionadas. `operations_json` = `'{"Col": ["mean","std"]}'` |

### Análise de convergência e limites

| Tool | Assinatura resumida | Para que serve |
|---|---|---|
| `df_analyze_bounds` | `(file_path, target_col, lower_bound_col, upper_bound_col, reference_val_col, iteration_col="", lock_threshold=0.005)` | Verifica se `target_col` está dentro da banda `[lower, upper]` e rastreia distância ao `reference`. Retorna `bounds_status`, `reference_accuracy`, `stability.is_locked`. |
| `df_analyze_stagnation` | `(file_path, target_col, window_size=5, cv_threshold=1.0, slope_threshold=0.01)` | Detecta se uma série parou de melhorar nas últimas N linhas. Retorna `status: "Stagnated" | "Active"`. |

### Análise de composição e proporção

| Tool | Assinatura resumida | Para que serve |
|---|---|---|
| `df_analyze_composition` | `(file_path, target_cost_col, all_cost_cols_json, label_col, min_threshold=0.0, max_threshold=0.0)` | Calcula a participação de uma coluna no total. `all_cost_cols_json` é um JSON array. Retorna `composition_metrics.target_share_of_total_pct`. |

### Análise de heatmap e filtros

| Tool | Assinatura resumida | Para que serve |
|---|---|---|
| `df_analyze_heatmap` | `(file_path, mode="solver_status", label_col="", value_cols_json="", threshold=0.0, top_n=10)` | Analisa matriz etapa × cenário. `mode="solver_status"` (inteiros 0-3) ou `mode="threshold"` (valores contínuos). Retorna ranking de etapas e cenários críticos. |
| `df_filter_above_threshold` | `(file_path, threshold, label_col="", value_cols_json="", direction="above", top_n=10)` | Identifica quais colunas (agentes/penalidades) excedem o limiar em cada etapa. Retorna `top_exceeding_columns` e `by_stage`. |

### Correlação cruzada

| Tool | Assinatura resumida | Para que serve |
|---|---|---|
| `df_cross_correlation` | `(file_path_a, file_path_b, col_a, col_b, join_on="", output_csv_path="")` | Pearson r, R², elasticidade OLS entre dois arquivos. `join_on` para merge por chave; vazio para alinhar por índice. |

---

## decision_graph.json — estado atual

**Formato:** Nós com `tools: []` (array, pode ter N ferramentas). Usado para o novo workflow de diagnóstico guiado.

### Nós

| ID | Tipo | Ferramentas | Propósito |
|---|---|---|---|
| `node_root_nao_convergencia` | analysis | `df_analyze_bounds` | Ponto de entrada — verifica se o caso convergiu |
| `node_zinf_aproximando_zsup` | analysis | `df_analyze_bounds` | Zinf evoluindo — identifica iterações insuficientes |
| `node_iteracoes_insuficientes` | conclusion | — (documentation) | Limite de iterações atingido antes da convergência |
| `node_zinf_zsup_distantes` | analysis | `df_analyze_bounds` | Estagnação detectada — roteia para causa |
| `node_penalidades_altas` | analysis | `df_analyze_composition`, `df_analyze_heatmap`, `df_filter_above_threshold` | Verifica dominância de penalidades (< 80% custo operativo) |
| `node_calibrar_penalidades` | conclusion | — (documentation) | Recomenda calibração de penalidades |
| `node_baixo_forwards` | analysis | `df_analyze_stagnation` | Estagnação com penalidades OK — verifica amostragem |
| `node_limitacao_cenarios` | conclusion | — (documentation) | Forwards insuficientes para cobertura do espaço de estados |

### Arestas

```
node_root_nao_convergencia  →  node_zinf_zsup_distantes     (priority 1)
node_root_nao_convergencia  →  node_zinf_aproximando_zsup   (priority 2)
node_zinf_aproximando_zsup  →  node_iteracoes_insuficientes (priority 1)
node_zinf_zsup_distantes    →  node_penalidades_altas       (priority 1)
node_zinf_zsup_distantes    →  node_baixo_forwards          (priority 2)
node_penalidades_altas      →  node_calibrar_penalidades    (priority 1)
node_baixo_forwards         →  node_limitacao_cenarios      (priority 1)
```

---

## Convenções do decision_graph.json

### Tipos de nó

| Tipo | Quando usar | Tem `tools[]`? | Tem `documentation`? |
|---|---|---|---|
| `analysis` | Executa ferramentas e interpreta resultado | Sim | Não |
| `conclusion` | Diagnóstico final — recomendação ao usuário | Não | Sim |
| `action` | Ação prescritiva intermediária (não terminal) | Não | Opcional |

### Estrutura de um nó `analysis`

```json
{
  "id": "node_<nome>",
  "type": "analysis",
  "label": "Texto legível para humanos",
  "purpose": "Uma frase sobre o que este nó decide",
  "content": {
    "description": "O que analisar e por que",
    "expected_state": "O que o resultado deve mostrar para prosseguir"
  },
  "tools": [
    {
      "name": "<nome_da_tool>",
      "params": { "<param>": "<valor_ou_placeholder>" }
    }
  ]
}
```

### Estrutura de um nó `conclusion`

```json
{
  "id": "node_<nome>",
  "type": "conclusion",
  "label": "Texto legível para humanos",
  "purpose": "Uma frase sobre o diagnóstico final",
  "content": {
    "description": "Explicação do que causa este estado",
    "expected_state": ""
  },
  "documentation": {
    "retrieval_strategy": "similarity",
    "search_intent": "Termos para busca nos docs técnicos",
    "top_k": 2
  }
}
```

### Regras de consistência

- Todo ID referenciado em `edges` deve existir em `nodes`
- `tools` é sempre um **array** — mesmo com uma única ferramenta
- Parâmetros de ferramentas que aceitam JSON usam strings: `"all_cost_cols_json": "[\"A\", \"B\"]"`
- Nós `conclusion` não têm `tools`; nós `analysis` não têm `documentation`

---

## Changelog

| Data | Mudança | Arquivo |
|---|---|---|
| 2026-04-16 | Criação do `decision_graph.json` com 8 nós e 7 arestas (ramo de convergência) | `decision-trees/decision_graph.json` |
| 2026-04-16 | Migração de `tools` de objeto para array em todos os nós | `decision-trees/decision_graph.json` |
| 2026-04-16 | Adição de `df_analyze_heatmap` e `df_filter_above_threshold` em `node_penalidades_altas` | `decision-trees/decision_graph.json` |
| 2026-04-16 | Criação de `REPO_INDEX.md` e `skills/repo-edit.md` | — |
| 2026-04-16 | Removidos `df_get_columns`, `df_get_size`, `get_decision_tree` do servidor | `server.py` |
| 2026-04-16 | Adicionados `get_diagnostic_graph` e `get_conclusion_documentation` | `server.py` |
| 2026-04-16 | `get_conclusion_documentation` busca seções de `Results.md` por similaridade de palavras-chave | `server.py` |
| 2026-04-16 | Skill `sddp-diagnose` reescrita para o novo workflow de grafo | `skills/sddp-diagnose.md` |
| 2026-04-16 | `sddp_html_to_csv.py`: detecta tipo de gráfico por camada; gera `_index.json` junto com os CSVs | `sddp_html_to_csv.py` |
| 2026-04-16 | `get_avaliable_results` lê `_index.json` e expõe nomes de colunas por arquivo — substitui `df_get_columns` para arquivos do dashboard | `server.py` |
