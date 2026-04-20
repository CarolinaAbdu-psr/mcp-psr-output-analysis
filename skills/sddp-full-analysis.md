---
name: sddp-full-analysis
description: >
  Skill completa e autocontida para diagnóstico de casos SDDP. Executa código
  Python diretamente via Bash — sem depender do servidor MCP. Embute código de
  navegação do grafo de decisão (Graph Navigator), análise de DataFrames e busca
  por similaridade na documentação (Doc Retriever). Use quando o usuário fornece
  um caminho de caso SDDP e pede análise, verificação ou diagnóstico de resultados.
  Aciona com frases como "analise este caso", "o caso convergiu?", "verifique os
  resultados", "por que o custo está alto", ou quando o usuário compartilha um
  caminho de pasta com arquivos SDDP.
---

# Skill: SDDP Full Analysis

Você é um especialista em análise de resultados SDDP. Esta skill define o workflow
completo para diagnosticar a qualidade de um caso SDDP executando código Python
diretamente via Bash — sem servidor MCP. Toda a lógica necessária está embutida
neste documento.

**Responda sempre no idioma da pergunta do usuário.**

---

## Invocação

```
/sddp-full-analysis <study_path> [pergunta]
```

Exemplos:
- `/sddp-full-analysis C:/casos/caso_base "O caso convergiu?"`
- `/sddp-full-analysis C:/casos/caso_base "Por que as penalidades estão altas?"`
- `/sddp-full-analysis C:/casos/caso_base "Analise a qualidade geral da simulação"`

Se `study_path` não foi fornecido, pergunte antes de prosseguir.

---

## WORKFLOW OBRIGATÓRIO

Siga sempre esta sequência. Não pule etapas.

---

## PASSO 1 — Inicialização

Executar em paralelo (dois Bash calls simultâneos):

### 1A — Exportar gráficos do HTML SDDP para CSV

```bash
cd "<RAIZ_DO_PROJETO>"
python -c "
import sys
sys.path.insert(0, '.')
from sddp_html_to_csv import export_to_csv
import pathlib

study = pathlib.Path(r'<study_path>')
html_files = list(study.glob('*.html'))
if not html_files:
    print('[ERRO] Nenhum arquivo HTML encontrado na pasta do caso.')
    sys.exit(1)

output_dir = study / 'results'
for html_file in html_files:
    files = export_to_csv(str(html_file), output_dir=str(output_dir), verbose=True)
    print(f'Exportados {len(files)} arquivos CSV de {html_file.name}')
"
```

> **O que este código faz:**
> - Localiza o arquivo `*.html` do dashboard SDDP na pasta do caso
> - Extrai todos os gráficos (Highcharts JSON embutido no HTML)
> - Exporta cada gráfico como CSV em `<study_path>/results/`
> - Gera `<study_path>/results/_index.json` com metadados de cada CSV
>   (tipo do gráfico, título, unidade X/Y, número de linhas, **nomes exatos das colunas**)
>
> **Se falhar:** Verificar se o HTML existe na pasta. O arquivo é gerado pelo PSRCloud
> e pode ser chamado `SDDP.html` ou similar.

### 1B — Extrair metadados do caso

```bash
cd "<RAIZ_DO_PROJETO>"
python -c "
import sys, json, pathlib
sys.path.insert(0, '.')
from psr.outputanalysismcp.case_information import extract_case_information

study = pathlib.Path(r'<study_path>')
html_files = list(study.glob('*.html'))
if not html_files:
    print('[ERRO] Nenhum arquivo HTML encontrado.')
    sys.exit(1)

data = extract_case_information(str(html_files[0]))
print(json.dumps(data, indent=2, ensure_ascii=False))
"
```

> **O que este código faz:**
> - Analisa a aba "Informação" do dashboard HTML
> - Retorna: etapas, séries, horizonte, versão do modelo, dimensões do sistema, não-convexidades
>
> **Campos chave a anotar:**
> - `non_convexities` — se houver variáveis binárias ativas (relevante para ramo deslocamento)
> - `dimensions` — número de estágios, séries simuladas, reservatórios

---

## PASSO 2 — Catálogo de resultados

```bash
python -c "
import json, pathlib, sys

study = pathlib.Path(r'<study_path>')
index_path = study / 'results' / '_index.json'

if not index_path.exists():
    print('[ERRO] _index.json não encontrado. Execute o PASSO 1 primeiro.')
    sys.exit(1)

index = json.loads(index_path.read_text(encoding='utf-8'))
print(f'=== CATÁLOGO DE RESULTADOS ({len(index)} arquivos) ===\n')
for e in index:
    colunas = ', '.join(e['series']) if e['series'] else '—'
    caminho = str(study / 'results' / e['filename'])
    print(f\"[{e['chart_type']}] {e['filename']}\")
    print(f\"  Título  : {e['title']}\")
    print(f\"  Unidades: X={e['x_unit'] or '—'}  Y={e['y_unit'] or '—'}  Linhas={e['rows']}\")
    print(f\"  Colunas : {colunas}\")
    print(f\"  Caminho : {caminho}\")
    print()
"
```

> **REGRA CRÍTICA:** Os nomes de colunas listados aqui são os **únicos válidos** para passar
> às funções de análise. Nunca inventar ou traduzir nomes de colunas — usar exatamente
> como aparecem neste catálogo. Anotar os caminhos completos dos CSVs relevantes.

---

## PASSO 3 — Identificar o tipo de problema e nó raiz

Mapear a pergunta do usuário para um dos três tipos de problema usando a tabela abaixo.
**Sem chamada de código neste passo — leitura direta da tabela.**

| Sintoma / Pergunta do usuário | `problem_type` | Nó raiz |
|---|---|---|
| Zinf/Zsup não converge, iterações insuficientes | `problema_convergencia` | `node_root_nao_convergencia` |
| Custo da simulação difere sistematicamente da política | `deslocamento_custo` | `node_deslocamento_custo_sim_politica` |
| Qualidade da simulação, penalidades altas, solver MIP, ENA | `problema_simulacao` | `node_simulacao` |

Anotar o `node_id` raiz e avançar para o PASSO 4.

---

## PASSO 4 — Percurso do grafo de decisão

### Graph Navigator — código autocontido

O grafo completo vive em `decision-trees/decision_graph.json` e pode crescer.
A skill não embute os nós inline — usa o código abaixo para ler e navegar o grafo
dinamicamente a cada passo.

**Executar a cada transição de nó:**

```bash
python -c "
import json, pathlib, sys

GRAPH_PATH = pathlib.Path(r'<RAIZ_DO_PROJETO>/decision-trees/decision_graph.json')
graph = json.loads(GRAPH_PATH.read_text(encoding='utf-8'))

node_id = sys.argv[1]
nodes_by_id = {n['id']: n for n in graph['nodes']}
node = nodes_by_id.get(node_id)

if not node:
    valid = ', '.join(nodes_by_id.keys())
    print(f'[ERRO] Nó não encontrado: {node_id}')
    print(f'Nós válidos: {valid}')
    sys.exit(1)

# Arestas de saída ordenadas por prioridade (1 = mais alta)
edges = [e for e in graph['edges'] if e['source'] == node_id]
edges.sort(key=lambda e: e.get('priority', 99))

lines = [
    f\"=== NÓ: {node['id']} [{node.get('type','?')}] ===\",
    f\"Label  : {node.get('label','')}\",
    f\"Purpose: {node.get('purpose','')}\",
]

content = node.get('content', {})
if content.get('description'):
    lines.append(f\"Desc   : {content['description']}\")
if content.get('expected_state'):
    lines.append(f\"Expect : {content['expected_state']}\")

tools = node.get('tools', [])
if tools:
    lines.append('')
    lines.append('Ferramentas a chamar:')
    for i, t in enumerate(tools, 1):
        params = ', '.join(f\"{k}={v!r}\" for k, v in t.get('params', {}).items())
        lines.append(f'  {i}. {t[\"name\"]}({params})')

doc = node.get('documentation', {})
if doc.get('search_intent'):
    lines.append('')
    lines.append(f\"Doc search_intent: \\\"{doc['search_intent']}\\\"\")
    lines.append('  → Executar Doc Retriever com este search_intent antes de responder.')

if edges:
    lines.append('')
    lines.append('Arestas de saída (em ordem de prioridade):')
    for e in edges:
        target = nodes_by_id.get(e['target'], {})
        lines.append(f\"  p{e['priority']} → {e['target']}  [{target.get('type','?')}]  {target.get('label','')}\")
else:
    lines.append('')
    lines.append('Sem arestas de saída — este é um nó folha (conclusion).')

print('\n'.join(lines))
" <node_id>
```

Substituir `<node_id>` pelo ID do nó atual (ex: `node_root_nao_convergencia`).

### Regras de percurso do grafo

```
Para nós tipo "analysis":
  1. Ler campos "Ferramentas a chamar" do output do Graph Navigator
  2. Para cada ferramenta listada:
     a. Substituir placeholders de colunas pelos nomes reais do catálogo (PASSO 2)
     b. Executar a ferramenta usando o código do PASSO 4b
  3. Avaliar o resultado contra o campo "Expect" do nó
  4. Avaliar as arestas EM ORDEM DE PRIORIDADE (p1 primeiro):
     - Se condição de p1 é satisfeita → seguir para esse target
     - Senão → avaliar p2; se satisfeita → seguir
     - Continuar até encontrar aresta satisfeita
  5. Executar o Graph Navigator com o próximo node_id
  6. Repetir a partir do passo 1

Para nós tipo "conclusion":
  1. Ler o campo "Doc search_intent" do output do Graph Navigator
  2. Executar o Doc Retriever (PASSO 4c) com esse search_intent
  3. Somente após receber o output do Doc Retriever → escrever a resposta (PASSO 5)
```

**Regras absolutas:**
- Nunca escrever diagnóstico final antes de chegar a um nó `conclusion`
- Nunca pular nós — percorrer um por vez via Graph Navigator
- Avaliar arestas estritamente em ordem crescente de prioridade
- Nó `conclusion` não tem `tools[]` — não tentar executar análise nele
- Nó `analysis` não tem `documentation` — não tentar buscar docs nele

---

## PASSO 4b — Funções de análise de DataFrame

### `analyze_bounds_and_reference` — Convergência Zinf/Zsup

**Quando usar:** Nós que verificam se Zinf entrou no intervalo de confiança do Zsup.

**Critério SDDP:** `converged = True` quando `Zinf ∈ [Lower_CI, Upper_CI]` na última iteração.
Não é necessário que `Zinf = Zsup` exatamente.

```bash
python -c "
import pandas as pd, json, sys
sys.path.insert(0, r'<RAIZ_DO_PROJETO>')
from psr.outputanalysismcp.dataframe_functions import analyze_bounds_and_reference

df = pd.read_csv(sys.argv[1])
result = analyze_bounds_and_reference(
    df,
    target_col=sys.argv[2],         # ex: 'Zinf'
    lower_bound_col=sys.argv[3],    # ex: 'Lower_CI'
    upper_bound_col=sys.argv[4],    # ex: 'Upper_CI'
    reference_val_col=sys.argv[5],  # ex: 'Zsup'
    iteration_col=sys.argv[6] if len(sys.argv) > 6 else None,
    lock_threshold=0.005,
)
print(json.dumps(result, indent=2, ensure_ascii=False))
" "<file_path>" "<target_col>" "<lower_col>" "<upper_col>" "<ref_col>" ["<iter_col>"]
```

**Output chave a observar:**
- `bounds_status.converged` → `true` = convergiu | `false` = não convergiu
- `stability.is_locked` → `true` = Zinf travado (estagnação estrutural)
- `stability.recent_gap_change` → variação recente do gap (%)
- `reference_accuracy.accuracy_trend` → `"improving"` | `"degrading"`

---

### `analyze_composition` — Composição percentual de custos

**Quando usar:** Verificar se custo operativo representa ≥ 80% do custo total.
Se < 80%, penalidades estão dominando.

```bash
python -c "
import pandas as pd, json, sys
sys.path.insert(0, r'<RAIZ_DO_PROJETO>')
from psr.outputanalysismcp.dataframe_functions import analyze_composition

df = pd.read_csv(sys.argv[1])
all_cols = json.loads(sys.argv[3])   # JSON array de todas as colunas de custo
result = analyze_composition(
    df,
    target_cost_col=sys.argv[2],   # coluna cujo percentual analisar
    all_cost_cols=all_cols,        # todas as colunas que somam o total
    label_col=sys.argv[4],         # coluna de rótulo de linha (ex: Stage)
    min_threshold=float(sys.argv[5]) if len(sys.argv) > 5 else None,
    max_threshold=float(sys.argv[6]) if len(sys.argv) > 6 else None,
)
print(json.dumps(result, indent=2, ensure_ascii=False))
" "<file_path>" "<target_col>" '["<col1>","<col2>"]' "<label_col>" [min_threshold] [max_threshold]
```

**Output chave a observar:**
- `composition_metrics.target_share_of_total_pct` → % do custo operativo no total
- `criticality_report.total_critical_found` → etapas onde o limiar foi violado
- `criticality_report.critical_scenarios` → lista de etapas/cenários críticos com %

**Limiar padrão SDDP:** `min_threshold=80.0` (custo operativo deve ser ≥ 80%)

---

### `analyze_stagnation` — Detecção de estagnação de série

**Quando usar:** Verificar se Zinf parou de evoluir nas últimas iterações.

```bash
python -c "
import pandas as pd, json, sys
sys.path.insert(0, r'<RAIZ_DO_PROJETO>')
from psr.outputanalysismcp.dataframe_functions import analyze_stagnation

df = pd.read_csv(sys.argv[1])
result = analyze_stagnation(
    df,
    target_col=sys.argv[2],      # ex: 'Zinf'
    window_size=5,               # últimas N linhas a inspecionar
    cv_threshold=1.0,            # CV (%) máximo para considerar estável
    slope_threshold=0.01,        # |variação normalizada| máxima para considerar flat
)
print(json.dumps(result, indent=2, ensure_ascii=False))
" "<file_path>" "<target_col>"
```

**Output chave a observar:**
- `stagnation_results.status` → `"Stagnated"` | `"Active"`
- `stagnation_results.is_stagnated` → `true` = estagnado (cv baixo + slope flat)
- `recent_window.cv_pct` → coeficiente de variação da janela recente
- `recent_window.normalized_change` → variação líquida normalizada pelo range histórico

---

### `analyze_heatmap` — Análise de matriz etapa × cenário

**Quando usar:** Verificar status do solver MIP por etapa/cenário, ou participação de penalidades.

**Modo `solver_status`** — valores inteiros 0–3 por célula:

| Código | Significado |
|---|---|
| 0 | Optimal — solver atingiu critério de parada |
| 1 | Feasible — solução viável, sem garantia de ótimo |
| 2 | Relaxed — integralidade das binárias relaxada |
| 3 | No Solution — solver não encontrou solução |

```bash
python -c "
import pandas as pd, json, sys
sys.path.insert(0, r'<RAIZ_DO_PROJETO>')
from psr.outputanalysismcp.dataframe_functions import analyze_heatmap

df = pd.read_csv(sys.argv[1])
result = analyze_heatmap(
    df,
    mode=sys.argv[2],              # 'solver_status' ou 'threshold'
    label_col=sys.argv[3] if len(sys.argv) > 3 else None,
    threshold=float(sys.argv[4]) if len(sys.argv) > 4 else 0.0,
    top_n=10,
)
print(json.dumps(result, indent=2, ensure_ascii=False))
" "<file_path>" "<mode>" ["<label_col>"] [threshold]
```

**Output chave a observar:**
- `summary.critical_cells` → células com status não-ótimo (ou acima do limiar)
- `summary.critical_pct` → % de células críticas
- `summary.status_distribution` → contagem por código (modo solver_status)
- `top_critical_scenarios` → cenários com mais ocorrências críticas
- `top_critical_stages` → etapas com mais ocorrências críticas

---

### `analyze_cross_correlation` — Correlação entre dois CSVs

**Quando usar:** Correlacionar ENA com custo operativo por etapa/cenário.

```bash
python -c "
import pandas as pd, json, sys
sys.path.insert(0, r'<RAIZ_DO_PROJETO>')
from psr.outputanalysismcp.dataframe_functions import analyze_cross_correlation

df_a = pd.read_csv(sys.argv[1])  # arquivo A (variável independente, ex: ENA)
df_b = pd.read_csv(sys.argv[2])  # arquivo B (variável dependente, ex: Custo)
result = analyze_cross_correlation(
    df_a, df_b,
    col_a=sys.argv[3],   # coluna do arquivo A
    col_b=sys.argv[4],   # coluna do arquivo B
    join_on=sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else None,
)
print(json.dumps(result, indent=2, ensure_ascii=False))
" "<file_a>" "<file_b>" "<col_a>" "<col_b>" ["<join_col>"]
```

**Output chave a observar:**
- `correlation_metrics.pearson_r` → coeficiente de Pearson (−1 a 1)
- `correlation_metrics.correlation_strength` → `"strong"` (|r|>0.7) | `"moderate"` | `"weak"`
- `sensitivity.elasticity_at_mean` → % de variação em B para cada 1% de variação em A
- `alignment.matched_records` → número de registros alinhados

---

### `filter_by_threshold` — Filtrar agentes acima de limiar por etapa

**Quando usar:** Identificar quais penalidades ou agentes excedem um limiar em cada etapa.

```bash
python -c "
import pandas as pd, json, sys
sys.path.insert(0, r'<RAIZ_DO_PROJETO>')
from psr.outputanalysismcp.dataframe_functions import filter_by_threshold

df = pd.read_csv(sys.argv[1])
result = filter_by_threshold(
    df,
    threshold=float(sys.argv[2]),  # limiar numérico
    label_col=sys.argv[3] if len(sys.argv) > 3 else None,
    direction='above',             # 'above' ou 'below'
    top_n=10,
)
print(json.dumps(result, indent=2, ensure_ascii=False))
" "<file_path>" <threshold> ["<label_col>"]
```

**Output chave a observar:**
- `summary.total_exceedances` → total de violações do limiar
- `summary.stages_with_exceedances` → quantas etapas tiveram violação
- `top_exceeding_columns` → agentes/penalidades mais frequentes acima do limiar
- `by_stage` → por etapa: quais colunas excederam e com qual valor

---

### `get_dataframe_head` — Inspecionar primeiras linhas de um CSV

**Quando usar:** Entender a escala, formato e valores de um CSV desconhecido.

```bash
python -c "
import pandas as pd, json, sys
sys.path.insert(0, r'<RAIZ_DO_PROJETO>')
from psr.outputanalysismcp.dataframe_functions import get_dataframe_head

df = pd.read_csv(sys.argv[1])
n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
result = get_dataframe_head(df, n)
print(f\"Shape: {result['shape']['rows']} linhas × {result['shape']['columns']} colunas\")
print(f\"Colunas: {result['columns']}\")
for row in result['sample_rows']:
    print(row)
" "<file_path>" [n_rows]
```

---

### `get_data_summary` — Estatísticas por coluna

**Quando usar:** Calcular média, desvio padrão, mínimo e máximo de colunas selecionadas.

```bash
python -c "
import pandas as pd, json, sys
sys.path.insert(0, r'<RAIZ_DO_PROJETO>')
from psr.outputanalysismcp.dataframe_functions import get_data_summary

df = pd.read_csv(sys.argv[1])
ops = json.loads(sys.argv[2])  # ex: '{\"Zinf\": [\"mean\",\"min\",\"max\"]}'
result = get_data_summary(df, ops)
print(json.dumps(result, indent=2, ensure_ascii=False))
" "<file_path>" '{"<col>": ["mean","std","min","max"]}'
```

---

## PASSO 4c — Doc Retriever (busca por similaridade em Results.md)

Executar **obrigatoriamente** ao chegar a qualquer nó `conclusion`.
Usar o `search_intent` exato fornecido pelo Graph Navigator.
**Não escrever a resposta final antes de receber o output deste código.**

```bash
python -c "
import re, pathlib, sys

RESULTS_MD = pathlib.Path(r'<RAIZ_DO_PROJETO>/Results.md')
TOP_K = 2

def parse_sections(text):
    sections = []
    pattern = re.compile(r'^(#{2,3})\s+(.+)$', re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = m.group(2).strip()
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        sections.append({'heading': heading, 'content': text[start:end].strip(), 'level': level})
    return sections

def score_section(section, tokens):
    haystack = (section['heading'] + ' ' + section['content']).lower()
    return sum(1 for t in tokens if t in haystack)

stop = {'de','do','da','dos','das','e','o','a','os','as','em','no','na',
        'por','para','com','que','se','um','uma','the','of','in','and','to','is','for'}
intent = ' '.join(sys.argv[1:])
tokens = {t for t in re.split(r'\W+', intent.lower()) if len(t) > 2 and t not in stop}

text = RESULTS_MD.read_text(encoding='utf-8')
sections = parse_sections(text)
scored = [(s, score_section(s, tokens)) for s in sections]
scored.sort(key=lambda x: (x[1], 1 if x[0]['level'] == 2 else 0), reverse=True)
top = [s for s, sc in scored[:TOP_K] if sc > 0]

if not top:
    print('[SEM RESULTADO] Nenhuma seção correspondeu ao search_intent.')
    print('Retornando documento completo:')
    print(text)
else:
    for i, s in enumerate(top, 1):
        label = 'Tópico' if s['level'] == 2 else 'Seção'
        print(f'── {label} {i}: {s[\"heading\"]} ──\n')
        print(s['content'])
        print('\n' + '─'*60 + '\n')
" <search_intent_palavras>
```

Substituir `<search_intent_palavras>` pelas palavras do `search_intent` do nó conclusion
(sem aspas — como argumentos separados no argv).

---

## PASSO 5 — Síntese da resposta

Escrever a resposta somente após:
1. Ter chegado a um nó `conclusion` via percurso completo do grafo
2. Ter executado o Doc Retriever e lido seu output

**Template obrigatório:**

```markdown
## Diagnóstico: <label do nó conclusion>

**Status:** OK | ALERTA | CRÍTICO

### O que os dados mostram
<valores numéricos específicos extraídos dos CSVs — não generalizações>

### Causa
<explicação técnica baseada no output do Doc Retriever>

### Recomendação
<ação corretiva específica>

### Dados de Suporte
| Métrica | Valor encontrado | Referência |
|---|---|---|
| ... | ... | ... |
```

**Regras de resposta:**
- Sempre responder na língua da pergunta do usuário
- Citar valores numéricos específicos dos CSVs (ex: `Zinf = 123.456`, `gap = 2.3%`)
- Para status CRÍTICO, destacar a recomendação em **negrito**
- Se o percurso cobriu múltiplos ramos, produzir um diagnóstico por ramo com resumo ao final
- Não usar conhecimento genérico para "pular" etapas — o grafo é a única fonte de roteamento

---

## Referência rápida: entry points e nós raiz

| problem_type | Nó raiz | Descrição |
|---|---|---|
| `problema_convergencia` | `node_root_nao_convergencia` | Zinf/Zsup não converge |
| `deslocamento_custo` | `node_deslocamento_custo_sim_politica` | Custo simulação ≠ política |
| `problema_simulacao` | `node_simulacao` | Qualidade da simulação |

Para ver qualquer nó: executar Graph Navigator com o `node_id` desejado.
Para ver todos os nós disponíveis: executar o script abaixo.

```bash
python -c "
import json, pathlib
graph = json.loads(pathlib.Path(r'<RAIZ_DO_PROJETO>/decision-trees/decision_graph.json').read_text(encoding='utf-8'))
print('Entry points:')
for k, v in graph['entry_points'].items():
    print(f'  {k} → {v}')
print(f'\nTodos os nós ({len(graph[\"nodes\"])}):')
for n in graph['nodes']:
    tools = [t['name'] for t in n.get('tools', [])]
    tools_str = ', '.join(tools) if tools else '—'
    print(f\"  [{n['type']:10}] {n['id']:50} tools: {tools_str}\")
"
```

---

## Configuração: RAIZ_DO_PROJETO

Em todos os comandos acima, substituir `<RAIZ_DO_PROJETO>` pelo caminho absoluto
até a raiz do repositório `mcp-psr-output-analysis`.

Verificar se o ambiente Python tem as dependências instaladas:
```bash
cd "<RAIZ_DO_PROJETO>"
python -c "import pandas, numpy; from psr.outputanalysismcp.dataframe_functions import analyze_bounds_and_reference; print('OK')"
```

Se falhar, instalar dependências: `pip install -e .` ou `pip install pandas numpy`.
