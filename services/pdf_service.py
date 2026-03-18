import tempfile
from datetime import datetime
from pathlib import Path

import jinja2
import weasyprint

from config import config
from services import chart_service
from services.meta_service import (
    METRICS_CONFIG, AVERAGE_KEYS,
    CAMPAIGN_TYPE_COLUMNS, CAMPAIGN_TYPE_LABELS,
)

CURRENCY_FIELDS = {k for k, v in METRICS_CONFIG.items() if v.get("format") == "currency"}
PERCENT_FIELDS  = {k for k, v in METRICS_CONFIG.items() if v.get("format") == "percent"}

# key → label
METRIC_LABELS = {v["key"]: v["label"] for v in METRICS_CONFIG.values()}
# key → format
METRIC_FORMATS = {v["key"]: v.get("format", "number") for v in METRICS_CONFIG.values()}


def _format_metric(value, metric_key: str) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return str(value)

    fmt = METRIC_FORMATS.get(metric_key, "number")
    if fmt == "currency":
        return f"R$ {v:,.2f}"
    if fmt == "percent":
        return f"{v:.2f}%"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"{v:,.0f}"
    if v < 10:
        return f"{v:,.2f}"
    return f"{v:,.0f}"


_TYPE_ORDER = ["IG", "SITE", "MSG", "ECOMMERCE", "LEAD", "OTHER"]

_COST_DENOMINATORS = {
    "cost_per_link_click": "link_click",
    "cost_per_message":    "messages",
    "cost_per_purchase":   "purchases",
    "cost_per_lead":       "leads",
}


def _compute_group_totals(rows: list[dict], columns: list[dict]) -> dict:
    totals: dict = {}
    for col in columns:
        key = col["key"]
        if key in _COST_DENOMINATORS:
            continue
        totals[key] = sum(r.get(key) or 0.0 for r in rows)
    spend = totals.get("spend", 0.0)
    for key, den_key in _COST_DENOMINATORS.items():
        if any(c["key"] == key for c in columns):
            den = totals.get(den_key, 0.0)
            totals[key] = round(spend / den, 4) if den > 0 else 0.0
    return totals


def _build_jinja_env() -> jinja2.Environment:
    templates_dir = Path(__file__).parent.parent / "templates"
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(templates_dir)))

    def format_metric_filter(value, metric):
        return _format_metric(value, metric)

    env.filters["format_metric"] = format_metric_filter
    return env


def _format_date(date_str: str) -> str:
    """Converte YYYY-MM-DD para DD/MM/YYYY."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return date_str


def generate_pdf(
    account: dict,
    insights: list[dict],
    summary: dict,
    campaigns_table: list[dict],
    output_path: str,
) -> str:
    """
    Gera o PDF do relatório para uma conta e salva em output_path.
    Retorna o caminho do arquivo gerado.
    """
    metrics_pt = account.get("metrics_list", [])

    # Resolve keys internas para cada métrica em português
    from services.meta_service import METRICS_CONFIG
    metric_keys = []
    seen_keys = set()
    for pt in metrics_pt:
        cfg = METRICS_CONFIG.get(pt)
        if cfg and cfg["key"] not in seen_keys:
            metric_keys.append(cfg["key"])
            seen_keys.add(cfg["key"])

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Gera gráficos
        chart_spend_path = str(tmpdir_path / "chart_spend.png")
        chart_campaigns_path = str(tmpdir_path / "chart_campaigns.png")

        chart_service.plot_daily_spend(insights, chart_spend_path)

        perf_metric = next(
            (k for k in ["purchases", "leads", "messages", "link_click", "clicks", "impressions"]
             if k in metric_keys),
            "spend",
        )
        chart_service.plot_campaign_performance(insights, perf_metric, chart_campaigns_path)

        # Monta KPI cards (usando keys internas)
        kpi_cards = []
        for key in metric_keys:
            val = summary.get(key)
            if val is not None:
                kpi_cards.append({
                    "label": METRIC_LABELS.get(key, key.replace("_", " ").title()),
                    "value": _format_metric(val, key),
                })

        # Agrupa campanhas por tipo e calcula subtotais
        by_type: dict[str, list] = {t: [] for t in _TYPE_ORDER}
        for row in campaigns_table:
            t = row.get("campaign_type", "OTHER")
            by_type.setdefault(t, []).append(row)

        grouped_campaigns = []
        spend_breakdown = []
        total_spend = sum(r.get("spend") or 0.0 for r in campaigns_table)

        for t in _TYPE_ORDER:
            t_rows = by_type.get(t, [])
            if not t_rows:
                continue
            cols = CAMPAIGN_TYPE_COLUMNS[t]
            type_spend = sum(r.get("spend") or 0.0 for r in t_rows)
            grouped_campaigns.append({
                "type":       t,
                "type_label": CAMPAIGN_TYPE_LABELS[t],
                "columns":    cols,
                "rows":       t_rows,
                "totals":     _compute_group_totals(t_rows, cols),
                "spend":      type_spend,
            })
            spend_breakdown.append({
                "label": CAMPAIGN_TYPE_LABELS[t],
                "spend": type_spend,
            })

        # Período
        period_start = _format_date(summary.get("period_start", ""))
        period_end = _format_date(summary.get("period_end", ""))
        generated_at = datetime.now().strftime("%d/%m/%Y às %H:%M")

        # CSS path (absoluto para WeasyPrint)
        css_path = (Path(__file__).parent.parent / "static" / "css" / "report.css").resolve().as_uri()

        # Renderiza HTML
        env = _build_jinja_env()
        template = env.get_template("report/report_base.html")
        html_str = template.render(
            account=account,
            kpi_cards=kpi_cards,
            grouped_campaigns=grouped_campaigns,
            spend_breakdown=spend_breakdown,
            total_spend=total_spend,
            chart_spend=Path(chart_spend_path).resolve().as_uri(),
            chart_campaigns=Path(chart_campaigns_path).resolve().as_uri(),
            period_start=period_start,
            period_end=period_end,
            generated_at=generated_at,
            css_path=css_path,
        )

        # Converte para PDF
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        weasyprint.HTML(
            string=html_str,
            base_url=str(Path(__file__).parent.parent.resolve()),
        ).write_pdf(output_path)

    return output_path
