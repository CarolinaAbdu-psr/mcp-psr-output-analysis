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
├── sddp_agent/
│   ├── agent.py               ← LangGraph StateGraph (wires all nodes)
│   ├── state.py               ← AgentState TypedDict + SessionMemory
│   ├── system_prompt.py       ← SDDP domain system prompt
│   ├── __main__.py            ← Interactive REPL (python -m sddp_agent)
│   ├── nodes/                 ← LangGraph node implementations
│   │   ├── initialize.py      ← HTML→CSV export, catalog loading
│   │   ├── router.py          ← query → problem_type via LLM
│   │   ├── graph_navigator.py ← traversal: tool selection, col resolution, hypothesis
│   │   ├── doc_retriever.py   ← Results.md keyword search at conclusion nodes
│   │   └── synthesizer.py     ← final structured diagnosis
│   ├── tools/
│   │   ├── graph_loader.py    ← decision_graph.json loader + cache
│   │   ├── catalog.py         ← _index.json helpers
│   │   └── dataframe_tools.py ← wrappers calling dataframe_functions.py
│   ├── prompts/               ← LLM prompt templates (.txt)
│   ├── README.md              ← Agent usage documentation
│   └── CLAUDE.md              ← AI-reusable context for this package
│
├── REPO_INDEX.md              ← ESTE ARQUIVO. Mapa vivo do repositório.
├── TOOLS.md                   ← Referência de todas as MCP tools (formato tabela)
├── README.md                  ← Instalação e configuração do servidor
├── .env                       ← API keys (não commitar — está no .gitignore)
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

### Grafo de diagnóstico (traversal incremental)

| Tool | Assinatura resumida | Para que serve |
|---|---|---|
| `get_graph_entry_point` | `(problem_type)` | **Passo 3** — retorna o nó raiz + sumário 2 níveis da subárvore + filhos imediatos. Se `problem_type` não bater, faz busca por keywords em todos os nós e retorna candidatos. |
| `get_graph_node` | `(node_id)` | **Passo 4** — retorna um nó pelo ID com seus filhos imediatos (~200-400 tokens). Chamar repetidamente até chegar a um nó `conclusion`. |
| `get_conclusion_documentation` | `(search_intent, top_k=2)` | **Obrigatório em todo nó conclusion** — busca por similaridade nas seções de `Results.md`; retorna os top_k trechos mais relevantes. A resposta final não pode ser escrita sem ter chamado esta ferramenta. |
| `get_diagnostic_graph` | `()` | **Deprecated** — carrega o grafo inteiro (~5500 tokens). Substituído por `get_graph_entry_point` + `get_graph_node`. |

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

**Versão:** 1.1 — **26 nós, 28 arestas, 3 entry points**

### Entry points

| problem_type | Nó raiz |
|---|---|
| `problema_convergencia` | `node_root_nao_convergencia` |
| `deslocamento_custo` | `node_deslocamento_custo_sim_politica` |
| `problema_simulacao` | `node_simulacao` |

### Nós — ramo convergência

| ID | Tipo | Ferramentas | Propósito |
|---|---|---|---|
| `node_root_nao_convergencia` | analysis | `df_analyze_bounds` | **Entry point** — verifica se Zinf entrou no IC do Zsup |
| `node_zinf_aproximando_zsup` | analysis | `df_analyze_bounds` | Zinf em trajetória (não-locked) — identifica iterações insuficientes |
| `node_iteracoes_insuficientes` | conclusion | — | Limite de iterações atingido antes da convergência |
| `node_zinf_zsup_distantes` | analysis | `df_analyze_bounds` | Estagnação estrutural — roteia para causa |
| `node_penalidades_altas` | analysis | `df_analyze_composition`, `df_analyze_heatmap`, `df_filter_above_threshold` | Penalidades dominam (< 80% custo operativo) |
| `node_calibrar_penalidades` | conclusion | — | Recomenda calibração de penalidades |
| `node_baixo_forwards` | analysis | `df_analyze_stagnation` | Estagnação com penalidades OK — verifica amostragem forward |
| `node_limitacao_cenarios` | conclusion | — | Forwards insuficientes para cobrir espaço de estados |

### Nós — ramo deslocamento de custos

| ID | Tipo | Ferramentas | Propósito |
|---|---|---|---|
| `node_deslocamento_custo_sim_politica` | analysis | — | **Entry point** — divergência sistemática simulação vs política |
| `node_variaveis_binarias` | analysis | — | Verifica presença de não-convexidades (via `get_case_information`) |
| `node_integralidade_violada` | analysis | — | Confirma que integralidade não está sendo respeitada na simulação |
| `node_ativar_nao_convexidade` | conclusion | — | Ativar solver MIP na fase de política |
| `node_dados_diferentes_politica` | analysis | — | Dados divergentes que não afetam a FCF |
| `node_fcf_outro_caso` | conclusion | — | FCF gerada por caso diferente |

### Nós — ramo simulação

| ID | Tipo | Ferramentas | Propósito |
|---|---|---|---|
| `node_simulacao` | analysis | — | **Entry point** — qualidade da fase de simulação |
| `node_proporcao_custo_operativo_sim` | analysis | `df_analyze_composition` | Participação do custo operativo < 80% na simulação |
| `node_verificar_etapas_penalidades_sim` | analysis | `df_analyze_composition`, `df_filter_above_threshold` | Etapas e agentes com penalidades elevadas |
| `node_dispersao_custos_ena` | analysis | `df_cross_correlation` | Correlação custo operativo × ENA |
| `node_dispersao_periodo_umido` | conclusion | — | Dispersão concentrada no período úmido |
| `node_estado_solucao_etapa_cenario` | analysis | `df_analyze_heatmap` (solver_status) | Status do solver MIP por etapa × cenário |
| `node_solucao_viavel` | analysis | — | Solver encontrou viável mas não ótima (tempo esgotado) |
| `node_solucao_relaxada` | analysis | — | Solver relaxou integralidade |
| `node_solucao_erro` | analysis | — | Solver sem solução (infactível ou erro) |
| `node_aumentar_tempo_mip` | conclusion | — | Aumentar tempo limite do solver MIP |
| `node_usar_slices_menores` | conclusion | — | Subdividir janela temporal do MIP |
| `node_checar_conflito_variaveis` | conclusion | — | Investigar restrições conflitantes |

> `node_calibrar_penalidades` é compartilhado pelos ramos convergência e simulação.

### Arestas principais

```
── Convergência ──────────────────────────────────────────────────────
node_root_nao_convergencia      → node_zinf_zsup_distantes         (p1)
node_root_nao_convergencia      → node_zinf_aproximando_zsup       (p2)
node_zinf_aproximando_zsup      → node_iteracoes_insuficientes     (p1)
node_zinf_zsup_distantes        → node_penalidades_altas           (p1)
node_zinf_zsup_distantes        → node_baixo_forwards              (p2)
node_penalidades_altas          → node_calibrar_penalidades        (p1)
node_baixo_forwards             → node_limitacao_cenarios          (p1)

── Deslocamento de custos ────────────────────────────────────────────
node_deslocamento_custo_sim_politica → node_variaveis_binarias     (p1)
node_deslocamento_custo_sim_politica → node_dados_diferentes_politica (p2)
node_variaveis_binarias         → node_integralidade_violada       (p1)
node_integralidade_violada      → node_ativar_nao_convexidade      (p1)
node_dados_diferentes_politica  → node_fcf_outro_caso              (p1)

── Simulação ─────────────────────────────────────────────────────────
node_simulacao → node_proporcao_custo_operativo_sim                (p1)
node_simulacao → node_dispersao_custos_ena                         (p2)
node_simulacao → node_estado_solucao_etapa_cenario                 (p3)
node_proporcao_custo_operativo_sim → node_verificar_etapas_penalidades_sim (p1)
node_verificar_etapas_penalidades_sim → node_calibrar_penalidades  (p1)
node_dispersao_custos_ena       → node_dispersao_periodo_umido     (p1)
node_estado_solucao_etapa_cenario → node_solucao_viavel            (p1)
node_estado_solucao_etapa_cenario → node_solucao_relaxada          (p2)
node_estado_solucao_etapa_cenario → node_solucao_erro              (p3)
node_solucao_viavel/relaxada/erro → node_aumentar_tempo_mip        (p1)
node_solucao_viavel/relaxada/erro → node_usar_slices_menores       (p2)
node_solucao_erro               → node_checar_conflito_variaveis   (p3)
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
| 2026-04-16 | Grafo expandido para 26 nós / 28 arestas: ramos deslocamento de custos e simulação adicionados | `decision-trees/decision_graph.json` |
| 2026-04-16 | `get_diagnostic_graph` deprecated; adicionados `get_graph_entry_point` e `get_graph_node` para traversal incremental (~200 tokens/passo vs ~5500) | `server.py` |
| 2026-04-16 | `get_graph_entry_point`: fallback por busca de keywords + sumário 2 níveis da subárvore quando `problem_type` não bate exato | `server.py` |
| 2026-04-16 | Critério de convergência explicitado: Zinf dentro de [Lower_CI, Upper_CI] = convergido (independente de igualar Zsup) | `decision-trees/decision_graph.json` |
| 2026-04-16 | Skill atualizada: travessia incremental, avaliação sequencial de prioridades, `get_conclusion_documentation` obrigatório antes de responder | `skills/sddp-diagnose.md` |
| 2026-04-20 | Criação do pacote `sddp_agent/`: agente LangGraph standalone com REPL interativo, sessão multi-turn e travessia por hipóteses | `sddp_agent/` |
