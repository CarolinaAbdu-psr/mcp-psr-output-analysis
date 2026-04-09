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


def _build_x_axis(data: list, point_start, domain: str) -> list:
    """
    Constrói o eixo X de uma série.

    Formatos possíveis de `data`:
      - [[x, y], ...]       → x explícito
      - [[x, y1, y2], ...]  → x explícito (area_range)
      - [v1, v2, ...]       → x derivado de pointStart
    """
    use_timestamps = _is_timestamp(point_start) or domain == "year"

    # Dados com x embutido
    if data and isinstance(data[0], list):
        xs = [row[0] for row in data]
        if use_timestamps:
            return [_ms_to_date(x, domain) for x in xs]
        return xs

    # Dados escalares — gerar x a partir de pointStart
    n = len(data)
    if use_timestamps:
        start_dt = datetime.fromtimestamp(point_start / 1000, tz=timezone.utc)
        if domain == "year":
            return [str(start_dt.year + i) for i in range(n)]
        # Para outros domínios temporais, incrementar por mês
        results = []
        for i in range(n):
            total_months = start_dt.month - 1 + i
            year = start_dt.year + total_months // 12
            month = total_months % 12 + 1
            results.append(f"{year}-{month:02d}")
        return results

    start = int(point_start) if point_start is not None else 1
    return list(range(start, start + n))


def _extract_y_columns(data: list, series_type: str, name: str) -> dict:
    """
    Retorna um dicionário {nome_coluna: [valores]}.

    - line / column / etc. → {name: [y]}
    - area_range           → {name + " low": [y1], name + " high": [y2]}
    """
    if not data:
        return {}

    if isinstance(data[0], list):
        if series_type == "area_range":
            return {
                f"{name} low":  [row[1] for row in data],
                f"{name} high": [row[2] for row in data],
            }
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

    # Padrão: const varName = new PSRPlot("id", "Título", "");
    plot_re = re.compile(
        r'const\s+(\w+)\s*=\s*new PSRPlot\("([^"]+)",\s*"([^"]*)",\s*"([^"]*)"\);'
    )
    # Padrão: varName.push_layers([...]);  — cada chamada está em uma única linha
    layers_re = re.compile(r'(\w+)\.push_layers\((\[.+\])\);')

    # 1. Mapear varName → metadados do gráfico
    plots: dict[str, dict] = {}
    for m in plot_re.finditer(content):
        var_name, _container_id, title, _subtitle = m.groups()
        plots[var_name] = {"title": title, "layers": []}

    # 2. Associar layers aos gráficos
    for m in layers_re.finditer(content):
        var_name, layers_json = m.groups()
        if var_name not in plots:
            continue
        try:
            layers = json.loads(layers_json)
            plots[var_name]["layers"].extend(layers)
        except json.JSONDecodeError:
            # Linha malformada — ignorar silenciosamente
            pass

    # 3. Construir DataFrames
    charts = []
    for plot_info in plots.values():
        title = plot_info["title"]
        layers = plot_info["layers"]
        if not layers:
            continue

        series: dict[str, list] = {}
        x_index = None
        x_unit = ""
        y_unit = ""

        for layer in layers:
            name        = layer.get("name", "")
            data        = layer.get("data", [])
            series_type = layer.get("type", "line")
            domain      = layer.get("domain", "linear")
            point_start = layer.get("pointStart", 1)
            x_unit      = layer.get("xUnit", x_unit)
            y_unit      = layer.get("yUnit", y_unit)

            if not data:
                continue

            xs = _build_x_axis(data, point_start, domain)
            if x_index is None:
                x_index = xs

            y_cols = _extract_y_columns(data, series_type, name)
            series.update(y_cols)

        if not series or x_index is None:
            continue

        df = pd.DataFrame(series, index=x_index)
        df.index.name = x_unit or "x"

        charts.append({
            "title":  title,
            "x_unit": x_unit,
            "y_unit": y_unit,
            "df":     df,
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

    for chart in charts:
        filename = _sanitize_filename(chart["title"]) + ".csv"
        out_path = output_dir / filename
        chart["df"].to_csv(out_path, encoding="utf-8-sig")  # utf-8-sig → abre bem no Excel
        saved.append(str(out_path))
        if verbose:
            print(f"  [OK] {filename}")

    if verbose:
        print(f"\n{len(saved)} graficos exportados para: {output_dir}")

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


