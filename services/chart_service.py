import os
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


# Paleta de cores consistente
PRIMARY_COLOR = "#1877F2"   # azul Meta
SECONDARY_COLOR = "#E9562C" # laranja
BG_COLOR = "#FFFFFF"
TEXT_COLOR = "#1C1E21"
GRID_COLOR = "#E4E6EB"

FIGURE_WIDTH_WIDE = 10
FIGURE_HEIGHT_WIDE = 4
FIGURE_WIDTH_BAR = 9
FIGURE_HEIGHT_BAR = 5


def _apply_style(ax, fig):
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID_COLOR)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelsize=9)
    ax.yaxis.set_tick_params(labelcolor=TEXT_COLOR)
    ax.xaxis.set_tick_params(labelcolor=TEXT_COLOR)
    ax.title.set_color(TEXT_COLOR)


def plot_daily_spend(rows: list[dict], output_path: str) -> str:
    """Gráfico de linha: gasto diário total."""
    # Agrupa por data
    daily: dict[str, float] = defaultdict(float)
    for row in rows:
        d = row.get("date_start", "")
        spend = row.get("spend", 0.0)
        if d:
            daily[d] += float(spend)

    if not daily:
        return _empty_chart(output_path, "Sem dados de investimento")

    dates = sorted(daily.keys())
    values = [daily[d] for d in dates]

    # Formata datas para exibição (DD/MM)
    labels = [f"{d[8:10]}/{d[5:7]}" for d in dates]

    fig, ax = plt.subplots(figsize=(FIGURE_WIDTH_WIDE, FIGURE_HEIGHT_WIDE), dpi=150)
    _apply_style(ax, fig)

    ax.plot(labels, values, color=PRIMARY_COLOR, linewidth=2.5, marker="o", markersize=5, zorder=3)
    ax.fill_between(range(len(labels)), values, alpha=0.12, color=PRIMARY_COLOR)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R$ {x:,.2f}"))
    ax.set_title("Investimento Diário", fontsize=13, fontweight="bold", pad=12)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8, zorder=0)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
    return output_path


def plot_campaign_performance(rows: list[dict], metric: str, output_path: str) -> str:
    """Gráfico de barras horizontais: performance por campanha."""
    # Determina o melhor metric disponível
    priority = ["conversions", "clicks", "impressions", "spend", "reach"]
    if metric not in [r.get(metric) for r in rows[:1]]:
        for p in priority:
            if any(p in r for r in rows):
                metric = p
                break

    # Agrega por campanha
    campaign_totals: dict[str, float] = defaultdict(float)
    campaign_names: dict[str, str] = {}
    for row in rows:
        cid = row.get("campaign_id", "")
        cname = row.get("campaign_name", cid)
        val = row.get(metric, 0.0)
        if cid:
            campaign_totals[cid] += float(val)
            campaign_names[cid] = cname

    if not campaign_totals:
        return _empty_chart(output_path, "Sem dados de campanhas")

    # Top 10 campanhas
    sorted_campaigns = sorted(campaign_totals.items(), key=lambda x: x[1], reverse=True)[:10]
    ids = [c[0] for c in sorted_campaigns]
    values = [c[1] for c in sorted_campaigns]
    names = [_truncate(campaign_names[cid], 40) for cid in ids]

    fig, ax = plt.subplots(figsize=(FIGURE_WIDTH_BAR, max(FIGURE_HEIGHT_BAR, len(names) * 0.55 + 1.5)), dpi=150)
    _apply_style(ax, fig)

    bars = ax.barh(range(len(names)), values, color=PRIMARY_COLOR, alpha=0.85, height=0.6)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()

    # Rótulos nas barras
    max_val = max(values) if values else 1
    for bar, val in zip(bars, values):
        label = _format_metric_value(metric, val)
        ax.text(
            bar.get_width() + max_val * 0.01,
            bar.get_y() + bar.get_height() / 2,
            label,
            va="center", ha="left", fontsize=8.5, color=TEXT_COLOR
        )

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _format_metric_value(metric, x)))
    title = _metric_label(metric)
    ax.set_title(f"Performance por Campanha — {title}", fontsize=13, fontweight="bold", pad=12)
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.8, zorder=0)
    ax.set_xlim(0, max_val * 1.18)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
    return output_path


def _empty_chart(output_path: str, message: str) -> str:
    fig, ax = plt.subplots(figsize=(FIGURE_WIDTH_WIDE, FIGURE_HEIGHT_WIDE), dpi=150)
    _apply_style(ax, fig)
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=14, color="#888", transform=ax.transAxes)
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
    return output_path


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _format_metric_value(metric: str, value: float) -> str:
    currency = {"spend", "cpm", "cpc", "cpp", "cost_per_conversion"}
    percent = {"ctr", "video_view_rate"}
    if metric in currency:
        return f"R$ {value:,.2f}"
    if metric in percent:
        return f"{value:.2f}%"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:,.0f}"


def _metric_label(metric: str) -> str:
    from services.meta_service import METRICS_CONFIG
    for cfg in METRICS_CONFIG.values():
        if cfg.get("key") == metric:
            return cfg["label"]
    return metric.replace("_", " ").title()
