"""
Gera um HTML interativo do grafo de decisão a partir do decision_graph.json.

Uso:
    python graph_to_html.py [caminho_do_json] [caminho_de_saida]

Padrões:
    json  → decision_graph.json  (mesma pasta do script)
    saida → decision_graph.html  (mesma pasta do script)
"""

import json
import sys
from pathlib import Path

# ─── paleta por tipo de nó ────────────────────────────────────────────────────
NODE_COLORS = {
    "analysis":   {"bg": "#3B82F6", "border": "#1D4ED8", "text": "#FFFFFF"},
    "conclusion": {"bg": "#10B981", "border": "#065F46", "text": "#FFFFFF"},
    "entry":      {"bg": "#F59E0B", "border": "#B45309", "text": "#FFFFFF"},
}
DEFAULT_COLOR = {"bg": "#6B7280", "border": "#374151", "text": "#FFFFFF"}

PRIORITY_COLORS = {1: "#EF4444", 2: "#F97316", 3: "#EAB308", 4: "#6B7280"}
PRIORITY_DEFAULT = "#9CA3AF"


def edge_color(priority: int) -> str:
    return PRIORITY_COLORS.get(priority, PRIORITY_DEFAULT)


def escape_js(text: str) -> str:
    """Escapa aspas e quebras de linha para uso em strings JS."""
    return (
        text.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "")
    )


def build_node_detail_html(node: dict, entry_points: dict) -> str:
    """Gera o HTML de detalhe de um nó para exibição no painel lateral."""
    nid  = node.get("id", "")
    ntype = node.get("type", "unknown")
    label = node.get("label", nid)
    purpose = node.get("purpose", "")
    content = node.get("content", {})
    desc = content.get("description", "")
    expected = content.get("expected_state", "")
    tools = node.get("tools", [])
    doc = node.get("documentation", {})

    # Quais entry points mapeiam para esse nó
    entries = [k for k, v in entry_points.items() if v == nid]

    parts = []
    parts.append(f'<h2 class="detail-title">{label}</h2>')

    type_label = {"analysis": "Análise", "conclusion": "Conclusão"}.get(ntype, ntype)
    color_map  = NODE_COLORS.get(ntype, DEFAULT_COLOR)
    parts.append(
        f'<span class="badge" style="background:{color_map["bg"]};color:{color_map["text"]}">'
        f'{type_label}</span>'
    )

    if entries:
        ep_html = "".join(f'<span class="tag entry-tag">{e}</span>' for e in entries)
        parts.append(f'<div class="detail-section"><strong>Ponto de entrada:</strong> {ep_html}</div>')

    if purpose:
        parts.append(f'<div class="detail-section"><strong>Objetivo:</strong><p>{purpose}</p></div>')

    if desc:
        parts.append(f'<div class="detail-section"><strong>Descrição:</strong><p>{desc}</p></div>')

    if expected:
        parts.append(
            f'<div class="detail-section expected-box">'
            f'<strong>Estado esperado:</strong><p>{expected}</p></div>'
        )

    if tools:
        tools_html = ""
        for t in tools:
            tname = t.get("name", "")
            params = t.get("params", {})
            params_html = "".join(
                f'<tr><td class="param-key">{k}</td><td class="param-val">{v}</td></tr>'
                for k, v in params.items()
            )
            tools_html += (
                f'<div class="tool-card">'
                f'<div class="tool-name">🔧 {tname}</div>'
                f'<table class="param-table">{params_html}</table>'
                f'</div>'
            )
        parts.append(f'<div class="detail-section"><strong>Ferramentas:</strong>{tools_html}</div>')

    if doc:
        strategy = doc.get("retrieval_strategy", "")
        intent   = doc.get("search_intent", "")
        top_k    = doc.get("top_k", "")
        parts.append(
            f'<div class="detail-section doc-box">'
            f'<strong>Documentação:</strong>'
            f'<p><em>Estratégia:</em> {strategy} | <em>top_k:</em> {top_k}</p>'
            f'<p><em>Busca:</em> {intent}</p>'
            f'</div>'
        )

    return "".join(parts)


def generate_html(graph: dict) -> str:
    entry_points = graph.get("entry_points", {})
    nodes_data   = graph.get("nodes", [])
    edges_data   = graph.get("edges", [])
    graph_id     = graph.get("graph_id", "")
    version      = graph.get("version", "")

    entry_node_ids = set(entry_points.values())

    # ── nós Cytoscape ────────────────────────────────────────────────────────
    cy_nodes = []
    node_details = {}  # id -> html string

    for node in nodes_data:
        nid   = node.get("id", "")
        label = node.get("label", nid)
        ntype = node.get("type", "analysis")

        is_entry = nid in entry_node_ids
        display_type = "entry" if is_entry else ntype
        col = NODE_COLORS.get(display_type, DEFAULT_COLOR)

        tools = node.get("tools", [])
        tool_names = [t.get("name", "") for t in tools]

        cy_nodes.append(
            f'  {{data: {{id: "{nid}", label: "{escape_js(label)}", '
            f'type: "{display_type}", '
            f'tools: {json.dumps(tool_names)}}}, '
            f'style: {{"background-color": "{col["bg"]}", '
            f'"border-color": "{col["border"]}", '
            f'"color": "{col["text"]}"}} }}'
        )
        node_details[nid] = escape_js(build_node_detail_html(node, entry_points))

    # ── arestas Cytoscape ─────────────────────────────────────────────────────
    cy_edges = []
    for i, edge in enumerate(edges_data):
        src  = edge.get("source", "")
        tgt  = edge.get("target", "")
        prio = edge.get("priority", 99)
        col  = edge_color(prio)
        cy_edges.append(
            f'  {{data: {{id: "e{i}", source: "{src}", target: "{tgt}", '
            f'priority: {prio}, label: "P{prio}"}}, '
            f'style: {{"line-color": "{col}", "target-arrow-color": "{col}"}} }}'
        )

    # ── node_details JS dict ──────────────────────────────────────────────────
    nd_js_entries = ",\n".join(f'  "{k}": \'{v}\'' for k, v in node_details.items())
    nd_js = f"{{\n{nd_js_entries}\n}}"

    # ── entry_points badges ───────────────────────────────────────────────────
    ep_badges = "".join(
        f'<span class="ep-badge" onclick="focusNode(\'{v}\')">{k}</span>'
        for k, v in entry_points.items()
    )

    nodes_js = "[\n" + ",\n".join(cy_nodes) + "\n]"
    edges_js = "[\n" + ",\n".join(cy_edges) + "\n]"

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Grafo de Decisão — {graph_id} v{version}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0F172A;
    color: #E2E8F0;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }}

  /* ── header ──────────────────────────────────────────────────────────── */
  header {{
    background: #1E293B;
    padding: 10px 18px;
    border-bottom: 1px solid #334155;
    display: flex;
    align-items: center;
    gap: 14px;
    flex-shrink: 0;
  }}
  header h1 {{ font-size: 1rem; font-weight: 600; color: #F1F5F9; }}
  header .meta {{ font-size: 0.75rem; color: #94A3B8; }}
  .ep-area {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-left: auto; }}
  .ep-label {{ font-size: 0.72rem; color: #94A3B8; }}
  .ep-badge {{
    font-size: 0.72rem; padding: 3px 9px; border-radius: 12px;
    background: #F59E0B; color: #1C1917; cursor: pointer; font-weight: 600;
    transition: opacity .15s;
  }}
  .ep-badge:hover {{ opacity: .8; }}

  /* ── layout principal ─────────────────────────────────────────────────── */
  .main {{
    display: flex;
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }}

  /* ── wrapper relativo do grafo ────────────────────────────────────────── */
  .cy-wrapper {{
    position: relative;
    flex: 1;
    min-width: 0;
    min-height: 0;
  }}

  /* ── grafo: ocupa todo o wrapper via posicionamento absoluto ──────────── */
  #cy {{
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: #0F172A;
  }}

  /* ── painel lateral ───────────────────────────────────────────────────── */
  #panel {{
    width: 360px;
    background: #1E293B;
    border-left: 1px solid #334155;
    overflow-y: auto;
    padding: 18px;
    transition: width .2s;
    flex-shrink: 0;
  }}
  #panel.hidden {{ width: 0; padding: 0; overflow: hidden; }}

  .panel-placeholder {{
    color: #475569;
    font-size: 0.9rem;
    text-align: center;
    margin-top: 60px;
  }}

  .detail-title {{
    font-size: 1rem;
    font-weight: 700;
    color: #F1F5F9;
    margin-bottom: 8px;
    line-height: 1.35;
  }}
  .badge {{
    display: inline-block;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 600;
    margin-bottom: 12px;
  }}
  .tag {{
    display: inline-block;
    font-size: 0.68rem;
    padding: 2px 7px;
    border-radius: 8px;
    margin: 2px;
    background: #334155;
    color: #CBD5E1;
  }}
  .entry-tag {{ background: #B45309; color: #FEF3C7; }}

  .detail-section {{
    margin-top: 12px;
    font-size: 0.82rem;
    color: #CBD5E1;
  }}
  .detail-section strong {{ color: #F1F5F9; font-size: 0.78rem; display: block; margin-bottom: 4px; }}
  .detail-section p {{ line-height: 1.55; color: #94A3B8; }}

  .expected-box {{
    background: #0F172A;
    border-left: 3px solid #3B82F6;
    padding: 8px 10px;
    border-radius: 0 6px 6px 0;
  }}
  .expected-box p {{ color: #CBD5E1; }}

  .doc-box {{
    background: #0F172A;
    border-left: 3px solid #10B981;
    padding: 8px 10px;
    border-radius: 0 6px 6px 0;
  }}

  .tool-card {{
    background: #0F172A;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 10px;
    margin-top: 6px;
  }}
  .tool-name {{ font-weight: 600; color: #38BDF8; margin-bottom: 6px; font-size: 0.8rem; }}
  .param-table {{ width: 100%; border-collapse: collapse; font-size: 0.74rem; }}
  .param-table td {{ padding: 2px 4px; vertical-align: top; }}
  .param-key {{ color: #7DD3FC; width: 45%; word-break: break-word; }}
  .param-val {{ color: #CBD5E1; }}

  /* ── legenda ──────────────────────────────────────────────────────────── */
  .legend {{
    position: absolute;
    bottom: 14px;
    left: 14px;
    background: rgba(30,41,59,.92);
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.72rem;
    pointer-events: none;
  }}
  .legend-title {{ font-weight: 700; margin-bottom: 7px; color: #F1F5F9; }}
  .legend-row {{ display: flex; align-items: center; gap: 7px; margin-bottom: 4px; }}
  .legend-dot {{
    width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;
  }}
  .legend-line {{
    width: 22px; height: 3px; border-radius: 2px; flex-shrink: 0;
  }}

  /* ── toolbar ──────────────────────────────────────────────────────────── */
  .toolbar {{
    position: absolute;
    top: 14px;
    right: 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .tb-btn {{
    background: #1E293B;
    border: 1px solid #334155;
    color: #E2E8F0;
    border-radius: 6px;
    padding: 6px 10px;
    cursor: pointer;
    font-size: 0.8rem;
    transition: background .15s;
  }}
  .tb-btn:hover {{ background: #334155; }}

  #panel {{
    scrollbar-width: thin;
    scrollbar-color: #334155 transparent;
  }}
</style>
</head>
<body>

<header>
  <div>
    <h1>Grafo de Decisão SDDP</h1>
    <div class="meta">{graph_id} &nbsp;·&nbsp; v{version} &nbsp;·&nbsp;
      {len(nodes_data)} nós &nbsp;·&nbsp; {len(edges_data)} arestas</div>
  </div>
  <div class="ep-area">
    <span class="ep-label">Pontos de entrada →</span>
    {ep_badges}
  </div>
</header>

<div class="main">
  <div class="cy-wrapper">
    <div id="cy"></div>

    <!-- legenda -->
    <div class="legend">
      <div class="legend-title">Legenda</div>
      <div class="legend-row"><div class="legend-dot" style="background:#F59E0B"></div>Ponto de entrada</div>
      <div class="legend-row"><div class="legend-dot" style="background:#3B82F6"></div>Nó de análise</div>
      <div class="legend-row"><div class="legend-dot" style="background:#10B981"></div>Conclusão</div>
      <div style="border-top:1px solid #334155; margin:7px 0"></div>
      <div class="legend-row"><div class="legend-line" style="background:#EF4444"></div>Prioridade 1</div>
      <div class="legend-row"><div class="legend-line" style="background:#F97316"></div>Prioridade 2</div>
      <div class="legend-row"><div class="legend-line" style="background:#EAB308"></div>Prioridade 3</div>
      <div class="legend-row"><div class="legend-line" style="background:#6B7280"></div>Prioridade 4+</div>
    </div>

    <!-- toolbar -->
    <div class="toolbar">
      <button class="tb-btn" onclick="cy.fit()">⊡ Fit</button>
      <button class="tb-btn" onclick="cy.zoom(cy.zoom()*1.3); cy.center()">＋</button>
      <button class="tb-btn" onclick="cy.zoom(cy.zoom()*.77); cy.center()">－</button>
      <button class="tb-btn" onclick="relayout()">↺ Layout</button>
      <button class="tb-btn" onclick="togglePanel()">☰ Painel</button>
    </div>
  </div>

  <div id="panel">
    <div class="panel-placeholder">Clique em um nó<br>para ver os detalhes</div>
  </div>
</div>

<script>
// ── dados do grafo ────────────────────────────────────────────────────────────
const nodeDetails = {nd_js};

const cyNodes = {nodes_js};

const cyEdges = {edges_js};

// ── inicializa Cytoscape ──────────────────────────────────────────────────────
const cy = cytoscape({{
  container: document.getElementById('cy'),
  elements: {{ nodes: cyNodes, edges: cyEdges }},
  style: [
    {{
      selector: 'node',
      style: {{
        'label': 'data(label)',
        'text-wrap': 'wrap',
        'text-max-width': '140px',
        'font-size': '11px',
        'text-valign': 'center',
        'text-halign': 'center',
        'width': 'label',
        'height': 'label',
        'padding': '12px',
        'shape': 'round-rectangle',
        'border-width': '2px',
        'border-style': 'solid',
        'transition-property': 'border-width, border-color',
        'transition-duration': '0.15s',
        'font-family': '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif',
        'font-weight': '600',
        'text-outline-width': 0,
      }}
    }},
    {{
      selector: 'node[type="entry"]',
      style: {{
        'shape': 'hexagon',
        'font-size': '12px',
      }}
    }},
    {{
      selector: 'node[type="conclusion"]',
      style: {{
        'shape': 'round-rectangle',
        'border-style': 'dashed',
        'border-width': '2px',
      }}
    }},
    {{
      selector: 'node:selected, node.highlighted',
      style: {{
        'border-width': '4px',
        'border-color': '#FFFFFF',
      }}
    }},
    {{
      selector: 'edge',
      style: {{
        'width': 2,
        'curve-style': 'bezier',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 1.2,
        'label': 'data(label)',
        'font-size': '9px',
        'color': '#94A3B8',
        'text-background-color': '#0F172A',
        'text-background-opacity': 0.85,
        'text-background-padding': '2px',
        'transition-property': 'width',
        'transition-duration': '0.15s',
        'font-family': '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif',
      }}
    }},
    {{
      selector: 'edge[priority=1]',
      style: {{ 'width': 3 }}
    }},
    {{
      selector: 'edge.faded',
      style: {{ 'opacity': 0.15 }}
    }},
    {{
      selector: 'node.faded',
      style: {{ 'opacity': 0.2 }}
    }},
  ],
  layout: {{ name: 'breadthfirst', directed: true, spacingFactor: 1.6, padding: 40 }},
  minZoom: 0.1,
  maxZoom: 4,
  wheelSensitivity: 0.3,
}});

// ── layout ────────────────────────────────────────────────────────────────────
function relayout() {{
  cy.layout({{ name: 'breadthfirst', directed: true, spacingFactor: 1.6, padding: 40 }}).run();
}}

// ── painel de detalhes ────────────────────────────────────────────────────────
const panel = document.getElementById('panel');

function showDetail(nodeId) {{
  const html = nodeDetails[nodeId];
  if (html) {{
    panel.innerHTML = html;
    panel.classList.remove('hidden');
  }}
}}

function togglePanel() {{
  panel.classList.toggle('hidden');
}}

// ── foco num nó (entry points) ────────────────────────────────────────────────
function focusNode(nodeId) {{
  const n = cy.getElementById(nodeId);
  if (!n.length) return;
  cy.animate({{
    center: {{ eles: n }},
    zoom: 1.6,
  }}, {{ duration: 500 }});
  n.emit('tap');
}}

// ── highlight de vizinhança ───────────────────────────────────────────────────
cy.on('tap', 'node', function(evt) {{
  const node = evt.target;
  const nodeId = node.id();

  // highlight
  cy.elements().removeClass('faded highlighted');
  const neighborhood = node.closedNeighborhood();
  cy.elements().not(neighborhood).addClass('faded');
  node.addClass('highlighted');

  // detalhe
  showDetail(nodeId);
}});

cy.on('tap', function(evt) {{
  if (evt.target === cy) {{
    cy.elements().removeClass('faded highlighted');
  }}
}});

// ── tooltip simples no hover ──────────────────────────────────────────────────
cy.on('mouseover', 'node', function(evt) {{
  document.getElementById('cy').style.cursor = 'pointer';
}});
cy.on('mouseout', 'node', function() {{
  document.getElementById('cy').style.cursor = 'default';
}});

cy.fit();
</script>
</body>
</html>
"""
    return html


def main():
    base = Path(__file__).parent
    json_path = Path(sys.argv[1]) if len(sys.argv) > 1 else base / "decision_graph.json"
    out_path  = Path(sys.argv[2]) if len(sys.argv) > 2 else base / "decision_graph.html"

    if not json_path.exists():
        print(f"Arquivo não encontrado: {json_path}")
        sys.exit(1)

    graph = json.loads(json_path.read_text(encoding="utf-8"))
    html  = generate_html(graph)
    out_path.write_text(html, encoding="utf-8")
    print(f"HTML gerado: {out_path}")


if __name__ == "__main__":
    main()
