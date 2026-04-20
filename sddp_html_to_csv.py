"""
sddp_html_to_csv.py
--------------------
Extrai os dados dos gráficos de um dashboard SDDP (.html gerado pelo PSRIO)
e salva cada gráfico como um arquivo CSV — equivalente ao botão "Download CSV"
da interface Highcharts.

Uso via linha de comando:
    python sddp_html_to_csv.py SDDP.html
    python sddp_html_to_csv.py SDDP.html ./minha_pasta_de_saida

Uso como módulo Python:
    from sddp_html_to_csv import extract_charts, export_to_csv

    charts = extract_charts("SDDP.html")
    for chart in charts:
        print(chart["title"])
        print(chart["df"].head())

    saved_files = export_to_csv("SDDP.html", output_dir="charts_csv")
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos para nomes de arquivo."""
    return re.sub(r'[<>:"/\\|?*%\n\r\t]', "_", name).strip()


def _is_timestamp(value) -> bool:
    """Verifica se um valor é um timestamp Unix em milissegundos (> ano 2000)."""
    return isinstance(value, (int, float)) and value > 9_000_000_000_00  # > 10 dígitos ms


def _ms_to_date(ms: float, domain: str) -> str:
    """Converte timestamp em ms para string de data legível."""
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    if domain == "year":
        return dt.strftime("%Y")
    return dt.strftime("%Y-%m-%d %H:%M")


def _as_str(value) -> str:
    """Garante que um valor lido do JSON seja uma string simples."""
    if isinstance(value, list):
        return value[0] if value else ""
    return str(value) if value is not None else ""


def _detect_chart_type(layer_types: list[str]) -> str:
    """
    Infers the dominant chart type from the list of layer type strings.

    Priority (most distinctive first):
        heatmap  — any layer is "heatmap" or "heatmap_series"
        band     — any layer is "area_range" (confidence/tolerance band)
        bar      — any layer is "column"
        line     — default (line / spline / scatter)
    """
    types = set(layer_types)
    if types & {"heatmap", "heatmap_series"}:
        return "heatmap"
    if "area_range" in types:
        return "band"
    if "column" in types:
        return "bar"
    return "line"


def _find_title_from_html(content: str, container_id: str) -> str:
    """
    Fallback: localiza o <h2> mais próximo do <div id="container_id"> no HTML.

    Útil quando o título passado ao PSRPlot está vazio ("").
    """
    id_match = re.search(rf'id="{re.escape(container_id)}"', content)
    if not id_match:
        return ""
    h2_match = re.search(r'<h2[^>]*>(.*?)</h2>', content[id_match.end():],
                         re.IGNORECASE | re.DOTALL)
    if not h2_match:
        return ""
    return re.sub(r'<[^>]+>', '', h2_match.group(1)).strip()


# --- NOVA FUNÇÃO ADICIONADA AQUI ---
def _extract_tab_mapping(content: str, plots: dict) -> None:
    """
    Mapeia a hierarquia de abas (Aba Pai > Aba Filha) para cada container de gráfico,
    adicionando a chave 'tab_name' ao dicionário de cada plot.
    """
    # 1. Mapear IDs de menus colapsáveis para seus nomes (Abas Pais)
    parent_names = {}
    for m in re.finditer(r'href="#([^"]+)"[^>]*>.*?</span>\s*([^<]+)</a>', content):
        parent_names[m.group(1)] = m.group(2).strip()

    # 2. Mapear Sub-abas para seus respectivos Pais
    tab_to_full_name = {}
    collapse_sections = re.finditer(r'<div[^>]*class="[^"]*collapse[^"]*"[^>]*id="([^"]+)"', content)
    
    for section in collapse_sections:
        parent_id = section.group(1)
        parent_name = parent_names.get(parent_id, "")
        
        start_pos = section.end()
        end_search = content.find('</div>', start_pos)
        if end_search == -1: 
            end_search = len(content)
        
        sub_content = content[start_pos:end_search]
        for sub_m in re.finditer(r'data-bs-target="#([^"]+)"[^>]*>.*?</span>\s*([^<]+)</a>', sub_content):
            sub_id = sub_m.group(1)
            sub_name = sub_m.group(2).strip()
            if parent_name:
                tab_to_full_name[sub_id] = f"{parent_name} - {sub_name}"
            else:
                tab_to_full_name[sub_id] = sub_name

    # 3. Adicionar abas simples (que não têm pai)
    for m in re.finditer(r'data-bs-target="#([^"]+)"[^>]*>.*?</span>\s*([^<]+)</a>', content):
        tid = m.group(1)
        if tid not in tab_to_full_name:
            tab_to_full_name[tid] = m.group(2).strip()

    # 4. Vincular cada container_id à sua aba correspondente no corpo do HTML
    for plot_info in plots.values():
        container_id = plot_info["container_id"]
        c_match = re.search(rf'id="{re.escape(container_id)}"', content)
        final_name = "Geral"
        
        if c_match:
            c_pos = c_match.start()
            tabs_before = [m.group(1) for m in re.finditer(r'<div[^>]*class="[^"]*tab-pane[^"]*"[^>]*id="([^"]+)"', content[:c_pos])]
            if tabs_before:
                last_tab_id = tabs_before[-1]
                final_name = tab_to_full_name.get(last_tab_id, last_tab_id)
        
        plot_info["tab_name"] = final_name
# -----------------------------------


def _extract_push_layers(content: str) -> list[tuple[str, str]]:
    """
    Extrai todos os pares (var_name, json_str) de chamadas push_layers,
    suportando JSON em linha única *e* multi-linha.

    Estratégia: ao encontrar `varName.push_layers(`, usa contador de colchetes
    para localizar o `]` de fechamento correto, ignorando colchetes dentro de
    strings JSON.
    """
    results: list[tuple[str, str]] = []
    pattern = re.compile(r'(\w+)\.push_layers\(')

    i = 0
    while True:
        m = pattern.search(content, i)
        if not m:
            break
        var_name = m.group(1)
        pos = m.end()          # posição logo após o '(' de abertura

        # Percorrer caractere a caractere para balancear colchetes,
        # ignorando conteúdo dentro de strings JSON (aspas duplas).
        depth = 0
        in_string = False
        escape_next = False
        start = pos
        j = pos
        while j < len(content):
            ch = content[j]
            if escape_next:
                escape_next = False
            elif ch == '\\' and in_string:
                escape_next = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        json_str = content[start:j + 1]
                        results.append((var_name, json_str))
                        i = j + 1
                        break
            j += 1
        else:
            # Não encontrou fechamento — avança para não entrar em loop infinito
            i = m.end()

    return results


def _has_embedded_x(data: list, series_type: str) -> bool:
    """
    Determina se o eixo X está embutido nos dados.

    Regras:
      - area_range: x embutido quando cada row tem 3 elementos [x, low, high]
                    sem x quando cada row tem 2 elementos [low, high]
      - outros tipos: x embutido quando cada row é uma lista [x, y]
                      sem x quando os elementos são escalares
    """
    if not data or not isinstance(data[0], list):
        return False
    if series_type == "area_range":
        return len(data[0]) == 3   # [x, low, high]
    return len(data[0]) >= 2       # [x, y]


def _build_x_axis(data: list, point_start, domain: str, has_x: bool) -> list:
    """
    Constrói o eixo X de uma série.

    Formatos suportados de `data`:
      - [[x, y], ...]        → x explícito (line/column)
      - [[x, low, high], ...]→ x explícito (area_range)
      - [[low, high], ...]   → sem x (area_range via pointStart)
      - [v, v, ...]          → sem x (escalares via pointStart)
    """
    if has_x:
        xs = [row[0] for row in data]
        if _is_timestamp(xs[0]):
            return [_ms_to_date(x, domain) for x in xs]
        return xs

    # Sem x — gerar a partir de pointStart
    n = len(data)
    if _is_timestamp(point_start):
        start_dt = datetime.fromtimestamp(point_start / 1000, tz=timezone.utc)
        if domain == "year":
            return [str(start_dt.year + i) for i in range(n)]
        if domain == "week":
            from datetime import timedelta
            return [(start_dt + timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(n)]
        # month e outros domínios temporais — incrementar mês a mês
        results = []
        for i in range(n):
            total_months = start_dt.month - 1 + i
            year = start_dt.year + total_months // 12
            month = total_months % 12 + 1
            results.append(f"{year}-{month:02d}")
        return results

    start = int(point_start) if point_start is not None else 1
    return list(range(start, start + n))


def _extract_y_columns(data: list, series_type: str, name: str, has_x: bool) -> dict:
    """
    Retorna um dicionário {nome_coluna: [valores]}.

    - line / column / etc. → {name: [y]}
    - area_range           → {name + " low": [low], name + " high": [high]}

    O parâmetro `has_x` indica se o primeiro elemento de cada row é o eixo X.
    """
    if not data:
        return {}

    if series_type == "area_range":
        if has_x:
            # [x, low, high]
            return {
                f"{name} low":  [row[1] for row in data],
                f"{name} high": [row[2] for row in data],
            }
        if isinstance(data[0], list):
            # [low, high] sem x
            return {
                f"{name} low":  [row[0] for row in data],
                f"{name} high": [row[1] for row in data],
            }

    if has_x:
        # Heatmaps têm estrutura [x, y_axis, value] — o valor real está em row[2]
        if (series_type == "heatmap" or series_type == "heatmap_series" )  and data and isinstance(data[0], (list, tuple)) and len(data[0]) >= 3:
            return {name: [row[2] for row in data]}
        return {name: [row[1] for row in data]}

    # Dados escalares
    return {name: list(data)}


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

def extract_charts(html_path: str) -> list[dict]:
    """
    Lê um arquivo HTML do dashboard SDDP e retorna uma lista de gráficos.

    Cada elemento da lista é um dicionário com:
        - "title"  (str)            : título do gráfico
        - "x_unit" (str)            : unidade do eixo X
        - "y_unit" (str)            : unidade do eixo Y
        - "df"     (pd.DataFrame)   : dados do gráfico, índice = eixo X

    Parameters
    ----------
    html_path : str
        Caminho para o arquivo SDDP.html.

    Returns
    -------
    list[dict]
    """
    content = Path(html_path).read_text(encoding="utf-8", errors="replace")

    # Padrão: const varName = new PSRPlot("container_id", "Título", "subtitle");
    plot_re = re.compile(
        r'const\s+(\w+)\s*=\s*new PSRPlot\("([^"]+)",\s*"([^"]*)",\s*"([^"]*)"\);'
    )

    # 1. Mapear varName → metadados do gráfico (guarda container_id para fallback de título)
    plots: dict[str, dict] = {}
    for m in plot_re.finditer(content):
        var_name, container_id, title, _subtitle = m.groups()
        plots[var_name] = {"title": title, "container_id": container_id, "layers": []}

    # ADIÇÃO: Descobrir a qual Aba (tab) cada gráfico pertence
    _extract_tab_mapping(content, plots)

    # 2. Associar layers aos gráficos (suporta JSON em linha única e multi-linha)
    for var_name, layers_json in _extract_push_layers(content):
        if var_name not in plots:
            continue
        try:
            layers = json.loads(layers_json)
            plots[var_name]["layers"].extend(layers)
        except json.JSONDecodeError:
            # JSON malformado — ignorar silenciosamente
            pass

    # 3. Construir DataFrames
    charts = []
    for plot_info in plots.values():
        # Fallback: se o título do PSRPlot está vazio, busca o <h2> próximo ao container
        title = plot_info["title"] or _find_title_from_html(content, plot_info["container_id"])
        tab_name = plot_info.get("tab_name", "Geral") # ADIÇÃO
        layers = plot_info["layers"]
        if not layers:
            continue

        series: dict[str, list] = {}
        x_index = None
        x_unit = ""
        y_unit = ""
        layer_types: list[str] = []

        for layer in layers:
            name        = layer.get("name", "")
            data        = layer.get("data", [])
            series_type = layer.get("type", "line")
            layer_types.append(series_type)
            domain      = layer.get("domain", "linear")
            point_start = layer.get("pointStart", 1)
            x_unit      = _as_str(layer.get("xUnit", x_unit))
            y_unit      = _as_str(layer.get("yUnit", y_unit))

            if not data:
                continue

            has_x = _has_embedded_x(data, series_type)
            xs = _build_x_axis(data, point_start, domain, has_x)
            if x_index is None:
                x_index = xs

            y_cols = _extract_y_columns(data, series_type, name, has_x)
            series.update(y_cols)

        if not series or x_index is None:
            continue

        df = pd.DataFrame(series, index=x_index)
        df.index.name = x_unit or "x"

        charts.append({
            "tab_name":   tab_name, # ADIÇÃO
            "title":      title,
            "chart_type": _detect_chart_type(layer_types),
            "x_unit":     x_unit,
            "y_unit":     y_unit,
            "df":         df,
        })

    return charts


def export_to_csv(
    html_path: str,
    output_dir: str | None = None,
    verbose: bool = True,
) -> list[str]:
    """
    Extrai todos os gráficos de um dashboard SDDP e salva como arquivos CSV.

    Parameters
    ----------
    html_path : str
        Caminho para o arquivo SDDP.html.
    output_dir : str, optional
        Pasta de destino. Padrão: subpasta `charts_csv/` ao lado do HTML.
    verbose : bool
        Se True, imprime o nome de cada arquivo salvo.

    Returns
    -------
    list[str]
        Lista dos caminhos dos arquivos CSV criados.
    """
    html_path = Path(html_path)

    if output_dir is None:
        output_dir = html_path.parent / "charts_csv"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    charts = extract_charts(html_path)
    saved = []
    index_entries = []

    for chart in charts:
        # ADIÇÃO: Incluir o nome da aba e hierarquia no filename ("Aba Pai - Aba Filha - Titulo do Grafico_Unidade")
        raw_filename = f"{chart['tab_name']} - {chart['title']}_{chart['y_unit']}"
        filename = _sanitize_filename(raw_filename) + ".csv"
        
        out_path = output_dir / filename
        chart["df"].to_csv(out_path, encoding="utf-8-sig")  # utf-8-sig → abre bem no Excel
        saved.append(str(out_path))
        
        index_entries.append({
            "filename":   filename,
            "tab_name":   chart["tab_name"], # ADIÇÃO
            "title":      chart["title"],
            "chart_type": chart["chart_type"],
            "x_unit":     chart["x_unit"],
            "y_unit":     chart["y_unit"],
            "series":     chart["df"].columns.tolist(),
            "rows":       len(chart["df"]),
        })
        if verbose:
            print(f"  [{chart['chart_type']:<7}] {filename}")

    # Write companion index so consumers know type/units without parsing filenames
    index_path = output_dir / "_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_entries, f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"\n{len(saved)} graficos exportados para: {output_dir}")
        print(f"  Índice escrito em: {index_path.name}")

    return saved


# ---------------------------------------------------------------------------
# Ponto de entrada via linha de comando
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python sddp_html_to_csv.py <SDDP.html> [pasta_de_saida]")
        sys.exit(1)

    html_file = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else None
    export_to_csv(html_file, out_dir)