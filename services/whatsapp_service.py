import requests
from config import config
from services.meta_service import (
    CAMPAIGN_TYPE_COLUMNS, CAMPAIGN_TYPE_LABELS,
    detect_campaign_type,
)


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Client-Token": config.ZAPI_CLIENT_TOKEN,
    }


_TYPE_ORDER = ["IG", "SITE", "MSG", "ECOMMERCE", "LEAD", "OTHER"]

_FORMAT_MAP = {
    "spend":               "currency",
    "cost_per_link_click": "currency",
    "cost_per_message":    "currency",
    "cost_per_purchase":   "currency",
    "cost_per_lead":       "currency",
    "purchase_value":      "currency",
}


def _fmt_val(value: float, key: str) -> str:
    fmt = _FORMAT_MAP.get(key, "number")
    if fmt == "currency":
        return f"R$ {value:,.2f}"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value:,.0f}"
    if value < 10 and value != int(value):
        return f"{value:,.2f}"
    return f"{value:,.0f}"


def _build_text_message(
    client_name: str,
    summary: dict,
    campaigns_table: list[dict],
) -> str:
    from datetime import datetime

    def fmt_date(d: str) -> str:
        try:
            return datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            return d

    period_start = fmt_date(summary.get("period_start", ""))
    period_end = fmt_date(summary.get("period_end", ""))
    total_spend = sum(r.get("spend", 0) for r in campaigns_table)

    lines = [
        f"📊 Relatório semanal — *{client_name}*",
        "",
        f"*Período:* {period_start} a {period_end}",
        f"*Investimento Total:* {_fmt_val(total_spend, 'spend')}",
    ]

    # Agrupa campanhas por tipo
    by_type: dict[str, list[dict]] = {}
    for row in campaigns_table:
        t = row.get("campaign_type", detect_campaign_type(row.get("campaign_name", "")))
        by_type.setdefault(t, []).append(row)

    for t in _TYPE_ORDER:
        t_rows = by_type.get(t)
        if not t_rows:
            continue

        cols = CAMPAIGN_TYPE_COLUMNS.get(t, CAMPAIGN_TYPE_COLUMNS["OTHER"])
        type_label = CAMPAIGN_TYPE_LABELS.get(t, t)
        type_spend = sum(r.get("spend", 0) for r in t_rows)

        lines.append("")
        lines.append(f"▸ *{type_label}*")
        lines.append(f"  Investimento: {_fmt_val(type_spend, 'spend')}")

        # Soma métricas do grupo (exceto spend que já foi mostrado)
        for col in cols:
            key = col["key"]
            if key == "spend":
                continue
            if key in _FORMAT_MAP and key.startswith("cost_"):
                # Custo = spend / denominador
                den_key = key.replace("cost_per_", "")
                if den_key == "link_click":
                    den = sum(r.get("link_click", 0) for r in t_rows)
                elif den_key == "message":
                    den = sum(r.get("messages", 0) for r in t_rows)
                elif den_key == "purchase":
                    den = sum(r.get("purchases", 0) for r in t_rows)
                elif den_key == "lead":
                    den = sum(r.get("leads", 0) for r in t_rows)
                else:
                    den = 0
                val = round(type_spend / den, 2) if den > 0 else 0
            else:
                val = sum(r.get(key, 0) for r in t_rows)

            if val > 0 or key in _FORMAT_MAP:
                lines.append(f"  {col['label']}: {_fmt_val(val, key)}")

    return "\n".join(lines)


def send_report(
    phone: str,
    client_name: str,
    summary: dict,
    campaigns_table: list[dict],
) -> bool:
    """
    Envia mensagem de texto para o número/grupo via Z-API.
    phone pode ser número individual (551199999999) ou grupo (1234567890-group).
    """
    text = _build_text_message(client_name, summary, campaigns_table)

    try:
        text_resp = requests.post(
            f"{config.ZAPI_BASE_URL}/send-text",
            headers=_headers(),
            json={"phone": phone, "message": text},
            timeout=30,
        )
        text_data = text_resp.json()
        if not text_data.get("messageId") and not text_data.get("zaapId"):
            print(f"[WhatsApp] Aviso texto para {phone}: {text_data}")
            return False
    except Exception as e:
        print(f"[WhatsApp] Erro ao enviar texto: {e}")
        return False

    return True
