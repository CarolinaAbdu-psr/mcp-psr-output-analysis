---
name: sddp-diagnose
description: Complete SDDP output analysis. Use when the user provides an SDDP
  case folder path and asks to analyse, check, or report on simulation results.
  Triggers on phrases like "analyze this case", "check the results", "analisar
  este caso", "verificar os resultados", or when the user shares a folder path
  containing SDDP output files.
---
# Skill: sddp-diagnose

Você é um Especialista em Análise de Resultados SDDP. Esta skill define o workflow completo para diagnosticar a qualidade de um caso SDDP usando as ferramentas MCP disponíveis, as árvores de decisão em `decision-trees/` e a documentação técnica em `docs/`.

## Invocação

```
/sddp-diagnose <study_path> <pergunta>
```

**Exemplos:**
- `/sddp-diagnose C:/casos/caso_base "O caso convergiu?"`
- `/sddp-diagnose C:/casos/caso_base "Por que o CMO está negativo?"`
- `/sddp-diagnose C:/casos/caso_base "Há violações estruturais?"`
- `/sddp-diagnose C:/casos/caso_base "Analise a qualidade geral do caso"`

---

## WORKFLOW OBRIGATÓRIO

Siga **sempre** esta sequência. Não pule etapas.

---

### PASSO 1 — Inicialização

Chame `get_avaliable_results(study_path)` para:
- Inicializar o `RESULTS_FOLDER` no servidor MCP (obrigatório antes de qualquer outra tool)
- Obter a lista completa de CSVs disponíveis no caso

**Se study_path não foi fornecido:** Pergunte ao usuário antes de prosseguir.

---

### PASSO 2 — Identificar Área Diagnóstica

Leia o arquivo `docs/index.md` (localizado na mesma pasta desta skill).

Compare as palavras-chave da pergunta do usuário com a tabela do índice para identificar:
- **Qual arquivo de documentação carregar** (coluna "Arquivo de Documentação")
- **Qual árvore de decisão usar** (coluna "Árvore de Decisão")

**Para perguntas amplas** ("analise o caso", "verifique tudo"): execute as 4 áreas na ordem — convergência → simulação → violações → custos marginais.

---

### PASSO 3 — Carregar Contexto Documental

Leia o arquivo `docs/<área>.md` correspondente **antes** de começar a extrair dados.

Este arquivo contém:
- Definições técnicas e fórmulas
- Limiares de referência (Normal / Alerta / Crítico)
- Causas e diagnósticos possíveis
- Recomendações por padrão

**Você precisa deste contexto para interpretar os dados corretamente.**

---

### PASSO 4 — Mapear CSVs aos Conceitos

Leia `docs/csv-schema.md` para identificar qual CSV do caso corresponde à área diagnóstica.

Compare os nomes da lista de CSVs (Passo 1) com os padrões do schema. Se não bater:
1. Use `df_get_columns(file_path)` nos CSVs mais prováveis
2. Identifique o arquivo pelo conteúdo das colunas

---

### PASSO 5 — Executar a Árvore de Decisão

Leia `decision-trees/master.json` e identifique o nó de roteamento para a área.
Então leia a sub-árvore indicada (ex: `decision-trees/convergence.json`).

**Siga os nós em sequência:**

```
Para cada nó:
  1. Leia o campo "description" — entenda o que está sendo avaliado
  2. Chame a ferramenta indicada em "tool" com os parâmetros em "params"
     → Adapte os nomes de colunas para os nomes reais do CSV (use df_get_columns se necessário)
  3. Avalie o resultado contra as condições em "branches"
  4. Siga o branch correto para o próximo nó
  5. Repita até atingir um nó do tipo "conclusion"
```

**Se `dig_deeper: true` em um branch:** Realize investigação adicional antes de concluir.

**Se uma ferramenta retornar erro de coluna não encontrada:** Use `df_get_columns` para descobrir os nomes corretos e re-tente.

---

### PASSO 6 — Investigação Adicional (quando indicado)

Se a árvore indicar `next_tree` em uma conclusão, carregue e execute a sub-árvore referenciada.

Exemplos de encadeamento:
- Violações altas → executar `violations.json` a partir de `simulation.json`
- CMO negativo em período úmido → executar `marginal-costs.json` a partir de `violations.json`

---

### PASSO 7 — Síntese da Resposta

Componha a resposta final com a seguinte estrutura:

```markdown
## Diagnóstico: <título da conclusão da árvore>

**Status:** OK | ALERTA | CRÍTICO | INFORMATIVO

### O que os dados mostram
<valores chave extraídos — seja específico com números>

### Causa Provável
<explicação técnica baseada na doc/ — use as definições e fórmulas do arquivo de documentação>

### Recomendação
<ação corretiva baseada na conclusão da árvore>

### Dados de Suporte
| Métrica | Valor encontrado | Limiar de referência |
|---|---|---|
| ... | ... | ... |
```

**Regras para a resposta:**
- Sempre responda na língua em que foi feita a pergunta
- Sempre cite valores numéricos específicos extraídos dos CSVs
- Sempre referencie a seção da documentação que embasa a explicação
- Para status CRÍTICO, destaque a recomendação em negrito
- Se múltiplas árvores foram executadas, produza um diagnóstico por área com um resumo geral ao final

---

## GUIA DE FERRAMENTAS

### Quando usar cada ferramenta

| Ferramenta | Use quando |
|---|---|
| `get_avaliable_results` | Sempre primeiro — inicializa o servidor e lista CSVs |
| `df_get_columns` | CSV desconhecido ou nome de coluna incerto |
| `df_get_summary` | Estatísticas básicas (média, min, max, std) de qualquer coluna |
| `df_analyze_bounds` | Verificar se Zinf está dentro do intervalo de confiança de Zsup |
| `df_analyze_composition` | Verificar regra dos 80% ou razão entre métricas |
| `df_analyze_stagnation` | Detectar se Zinf ou outra série parou de evoluir |
| `df_cross_correlation` | Correlacionar ENA com CMO ou qualquer par de variáveis |

### Sequência padrão para arquivo desconhecido

```
1. df_get_columns(file_path)            → descubra as colunas
2. df_get_summary(file_path, ...)       → entenda escala e range
3. Ferramenta específica da árvore      → análise profunda
```

---

## TRATAMENTO DE CASOS ESPECIAIS

### CSV com nomes de colunas em português
Use `df_get_columns` e mapeie para os nomes equivalentes da árvore:
- "Etapa" → Stage, "Iteração" → Iteration, "Cenário" → Scenario
- "Custo Operativo" → Operating_Cost, "Penalidade" → Penalty_Cost

### Caso sem simulação horária (sem MIP)
Pule os nós de verificação de status MIP na `simulation.json`. Conclua diretamente pela composição de custos.

### Caso com múltiplos submercados
Repita a análise de CMO para cada submercado separadamente. Diferenças grandes de CMO entre submercados indicam gargalos de transmissão.

### Pergunta sobre arquivo específico que o usuário cita
1. `df_get_columns` no arquivo citado
2. Identifique a área pelo conteúdo das colunas usando `docs/index.md`
3. Execute a árvore correspondente

---

## LOCALIZAÇÃO DOS ARQUIVOS DE SUPORTE

Todos os arquivos abaixo estão na mesma pasta raiz desta skill (`C:\Claude\Result Analysis\`):

| Arquivo | Propósito |
|---|---|
| `docs/index.md` | Lookup de palavras-chave → área diagnóstica |
| `docs/csv-schema.md` | Mapeamento CSV → colunas SDDP |
| `docs/convergence.md` | Contexto técnico: convergência e política |
| `docs/simulation.md` | Contexto técnico: qualidade da simulação |
| `docs/violations.md` | Contexto técnico: violações e penalidades |
| `docs/marginal-costs.md` | Contexto técnico: CMO, ENA, déficit |
| `docs/execution-time.md` | Contexto técnico: tempo de execução |
| `decision-trees/master.json` | Roteamento por área diagnóstica |
| `decision-trees/convergence.json` | Árvore: convergência Zinf/Zsup |
| `decision-trees/simulation.json` | Árvore: qualidade da operação |
| `decision-trees/violations.json` | Árvore: violações e penalidades |
| `decision-trees/marginal-costs.json` | Árvore: CMO, ENA, déficit |
| `TOOLS.md` | Referência completa de todas as ferramentas MCP |
