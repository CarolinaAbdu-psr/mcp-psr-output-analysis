---
name: repo-edit
description: Edição e manutenção do repositório mcp-psr-output-analysis. Use quando
  o usuário quiser adicionar ou modificar nós/arestas no decision_graph, adicionar
  novas ferramentas ao servidor MCP, entender como as tools funcionam, ou fazer
  qualquer alteração estrutural neste repositório.
---
# Skill: repo-edit

Você é um colaborador técnico do repositório **mcp-psr-output-analysis**. Esta skill define como ler, editar e manter os arquivos deste projeto com consistência.

## Invocação

```
/repo-edit <instrução>
```

**Exemplos:**
- `/repo-edit adicionar nó de análise de não-convexidade ao decision_graph`
- `/repo-edit explicar o que df_analyze_heatmap faz e quando usar`
- `/repo-edit adicionar nova tool ao server.py para análise de duração`
- `/repo-edit atualizar REPO_INDEX após as mudanças de hoje`

---

## PASSO 1 — Orientação obrigatória

**Antes de qualquer ação**, leia `REPO_INDEX.md` na raiz do repositório.

Este arquivo contém:
- Mapa de todos os arquivos e suas funções
- Catálogo completo das MCP tools com assinaturas
- Estado atual do `decision_graph.json` (nós, arestas, ferramentas por nó)
- Convenções e regras de consistência
- Changelog das últimas mudanças

Se o `REPO_INDEX.md` contradisser o que você vê no código, **confie no código** — o índice pode estar desatualizado. Atualize-o ao final.

---

## PASSO 2 — Identifique o tipo de tarefa

| Tipo de tarefa | Vá para |
|---|---|
| Entender uma tool MCP | [Seção: Lendo as tools](#lendo-as-tools) |
| Editar o `decision_graph.json` | [Seção: Editando o decision_graph](#editando-o-decision_graph) |
| Adicionar tool ao `server.py` | [Seção: Adicionando tools ao servidor](#adicionando-tools-ao-servidor) |
| Atualizar documentação / docs | [Seção: Mantendo a documentação](#mantendo-a-documentação) |
| Encerrar a sessão | [Seção: Auto-alimentação — atualizar REPO_INDEX](#auto-alimentação--atualizar-repo_index) |

---

## Lendo as tools

### Onde estão definidas

- **Exposição MCP (assinatura + docstring):** `psr/outputanalysismcp/server.py`
  - Cada `@mcp.tool()` define o que a LLM pode chamar
  - A docstring é o contrato público — descreve parâmetros, comportamento e quando usar

- **Implementação (lógica pura):** `psr/outputanalysismcp/dataframe_functions.py`
  - Funções Python sem dependência do MCP
  - Contém docstrings detalhadas com exemplos, formato de retorno e casos de borda

### Como ler uma tool desconhecida

1. Leia a `@mcp.tool()` correspondente em `server.py` para entender a interface pública
2. Leia a função em `dataframe_functions.py` para entender o que o resultado contém
3. Preste atenção nos campos do dict retornado — esses são os campos que a LLM lê ao usar a tool

### Mapeamento server.py → dataframe_functions.py

| Tool MCP | Função Python |
|---|---|
| `df_analyze_bounds` | `analyze_bounds_and_reference` |
| `df_analyze_composition` | `analyze_composition` |
| `df_analyze_stagnation` | `analyze_stagnation` |
| `df_analyze_heatmap` | `analyze_heatmap` |
| `df_filter_above_threshold` | `filter_by_threshold` |
| `df_cross_correlation` | `analyze_cross_correlation` |
| `df_get_summary` | `get_data_summary` |
| `df_get_columns` | `get_column_names` |
| `df_get_head` | `get_dataframe_head` |
| `df_get_size` | `get_dataframe_size` |

### O que observar em cada tool

Ao ler uma tool, extraia:
1. **Parâmetros obrigatórios vs. opcionais** (com defaults)
2. **Parâmetros que aceitam JSON string** (ex: `all_cost_cols_json`, `operations_json`, `value_cols_json`) — esses precisam ser formatados como string JSON, não como objeto
3. **Campos-chave do resultado** — quais campos a LLM deve ler para tomar uma decisão
4. **Critério de corte** — qual valor numérico separa "normal" de "crítico"

---

## Editando o decision_graph

### Onde fica

`decision-trees/decision_graph.json`

Este é o **novo formato de árvore em desenvolvimento**, diferente dos arquivos `convergence.json`, `simulation.json`, etc. (que são os formatos estáveis usados em produção).

### Convenções obrigatórias

**Tipos de nó válidos:**

| Tipo | Tem `tools[]`? | Tem `documentation`? | Terminal? |
|---|---|---|---|
| `analysis` | Sim | Não | Não |
| `conclusion` | Não | Sim | Sim |
| `action` | Não | Opcional | Não |

**`tools` é sempre um array** — mesmo com uma única ferramenta:
```json
"tools": [
  { "name": "df_analyze_bounds", "params": { ... } }
]
```

**Parâmetros JSON:** tools que aceitam listas usam string JSON:
```json
"all_cost_cols_json": "[\"Operating_Cost\", \"Penalty_Cost\"]"
```

**Consistência de arestas:** todo ID em `edges` deve existir em `nodes`. Verifique antes e depois de qualquer edição.

### Adicionando um nó `analysis`

```json
{
  "id": "node_<nome_snake_case>",
  "type": "analysis",
  "label": "Frase descritiva legível",
  "purpose": "O que este nó decide em uma frase",
  "content": {
    "description": "O que analisar, qual arquivo CSV, qual critério de corte",
    "expected_state": "O que o resultado deve mostrar para seguir para o próximo nó"
  },
  "tools": [
    {
      "name": "<tool_name>",
      "params": {
        "<param1>": "<valor ou placeholder>",
        "<param2>": "<valor>"
      }
    }
  ]
}
```

**Para escolher qual tool usar:** consulte o catálogo no `REPO_INDEX.md` ou releia as seções correspondentes de `server.py`.

### Adicionando um nó `conclusion`

```json
{
  "id": "node_<nome_snake_case>",
  "type": "conclusion",
  "label": "Frase descritiva legível",
  "purpose": "O diagnóstico final em uma frase",
  "content": {
    "description": "Causa técnica deste estado e impacto no sistema",
    "expected_state": ""
  },
  "documentation": {
    "retrieval_strategy": "similarity",
    "search_intent": "Termos técnicos para busca nos docs — seja específico",
    "top_k": 2
  }
}
```

### Adicionando uma aresta

```json
{ "source": "node_origem", "target": "node_destino", "priority": 1 }
```

`priority` define a ordem de avaliação quando um nó tem múltiplos destinos: 1 = primeiro a verificar.

### Checklist após editar o decision_graph

- [ ] Todos os IDs de arestas existem como nós?
- [ ] Nós `analysis` têm `tools` como array?
- [ ] Nós `conclusion` têm `documentation` e não têm `tools`?
- [ ] O JSON é válido? (sem vírgulas sobrando, sem aspas erradas)
- [ ] REPO_INDEX.md foi atualizado? (tabela de nós + arestas + changelog)

---

## Adicionando tools ao servidor

### Onde adicionar

1. **Implementação:** `psr/outputanalysismcp/dataframe_functions.py`
   - Adicione a função Python pura que recebe `df: pd.DataFrame` e retorna `dict`
   - Siga o padrão das funções existentes: docstring completa com seções `Args`, `Returns` e `Example`

2. **Exposição MCP:** `psr/outputanalysismcp/server.py`
   - Importe a função nova no bloco de imports
   - Crie um `@mcp.tool()` que chama `_load_csv`, passa para a função e chama `_format_result`
   - Siga o padrão dos tools existentes

### Padrão de um tool MCP

```python
@mcp.tool()
def df_nova_analise(
    file_path: str,
    coluna_alvo: str,
    parametro_opcional: float = 0.0,
) -> str:
    """
    Uma linha descrevendo o que faz.

    Contexto de uso: quando chamar esta tool e para que tipo de arquivo.

    Args:
        file_path:          Absolute path to the CSV file.
        coluna_alvo:        Column name to analyse.
        parametro_opcional: Description of what this controls. Default 0.0.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    result = nova_analise(df, coluna_alvo=coluna_alvo, parametro=parametro_opcional)
    return _format_result(result, f"NOVA ANÁLISE — {Path(file_path).name}")
```

### Depois de adicionar uma tool

1. Atualize `TOOLS.md` com a nova tool (tabela + descrição completa)
2. Atualize `REPO_INDEX.md` (seção "MCP Tools disponíveis" + changelog)
3. Se a tool puder ser usada em nós do `decision_graph.json`, documente os parâmetros típicos

---

## Mantendo a documentação

### Arquivos de documentação técnica (`docs/`)

Cada arquivo segue a estrutura:
- Conceito técnico com fórmulas
- Limiares: Normal / Alerta / Crítico
- Causas possíveis e como identificar
- Recomendações

**Quando atualizar:** sempre que adicionar um nó `conclusion` com `search_intent` que aponta para uma área técnica não coberta pelo doc correspondente.

### `TOOLS.md`

Referência pública de todas as tools. Mantenha sincronizado com `server.py`. Inclua:
- Tabela de parâmetros (nome, tipo, default, descrição)
- Exemplo de chamada
- Formato do retorno

---

## Auto-alimentação — atualizar REPO_INDEX

**Esta etapa é obrigatória ao final de qualquer sessão que fizer mudanças.**

### O que atualizar no REPO_INDEX.md

| Seção | Atualizar quando |
|---|---|
| `## Estrutura de arquivos` | Novo arquivo criado ou renomeado |
| `## MCP Tools disponíveis` | Nova tool adicionada ou assinatura mudada |
| `## decision_graph.json — estado atual` | Qualquer mudança de nó ou aresta |
| `## Convenções` | Nova regra ou exceção identificada |
| `## Changelog` | **Sempre** — toda sessão com mudanças |

### Formato do changelog

```markdown
| 2026-04-16 | Descrição objetiva da mudança | `arquivo/modificado.json` |
```

Use a data atual. Se múltiplos arquivos foram modificados, use uma linha por mudança significativa.

### O que NÃO colocar no REPO_INDEX

- Código-fonte (só referências a arquivos)
- Conteúdo que já está em `TOOLS.md` ou `docs/` — use links, não duplicatas
- Detalhes de implementação que mudam frequentemente — fique no nível de "o que existe" e "para que serve"

---

## Referência rápida de arquivos-chave

| Preciso de... | Leia... |
|---|---|
| Assinatura completa de uma tool | `server.py` (bloco `@mcp.tool()`) |
| Lógica e campos do retorno | `dataframe_functions.py` |
| Estado atual do decision_graph | `REPO_INDEX.md` → seção "decision_graph.json" |
| Contexto técnico de convergência | `docs/convergence.md` |
| Contexto técnico de violações | `docs/violations.md` |
| Schema de CSVs do SDDP | `docs/csv-schema.md` |
| Árvore estável de convergência | `decision-trees/convergence.json` |
| Como a skill de diagnóstico funciona | `skills/sddp-diagnose.md` |
