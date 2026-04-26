"""
Google Ads service — espelha a interface do meta_service mas para Google Ads.

Funções públicas:
- fetch_account_spend_mtd(customer_id) -> {'spend_mtd', 'currency'}
- fetch_weekly_summary(customer_id) -> {'spend', 'impressions', 'clicks', 'conversions'}
- fetch_campaigns_for_dashboard(customer_id, days, filter) -> list[dict]
"""
from datetime import date
from typing import Optional

from config import config


_client = None


class GoogleAdsServiceError(Exception):
    pass


def _normalize_customer_id(customer_id: str) -> str:
    return (customer_id or "").replace("-", "").strip()


def get_client():
    """Singleton GoogleAdsClient construído a partir de env vars."""
    global _client
    if _client is not None:
        return _client

    if not config.GOOGLE_ADS_ENABLED:
        raise GoogleAdsServiceError(
            "Google Ads não configurado. Defina GOOGLE_ADS_DEVELOPER_TOKEN e demais env vars."
        )

    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError as e:
        raise GoogleAdsServiceError(
            "Pacote google-ads não instalado. Rode: pip install google-ads"
        ) from e

    credentials = {
        "developer_token": config.GOOGLE_ADS_DEVELOPER_TOKEN,
        "client_id": config.GOOGLE_ADS_CLIENT_ID,
        "client_secret": config.GOOGLE_ADS_CLIENT_SECRET,
        "refresh_token": config.GOOGLE_ADS_REFRESH_TOKEN,
        "use_proto_plus": True,
    }
    if config.GOOGLE_ADS_LOGIN_CUSTOMER_ID:
        credentials["login_customer_id"] = config.GOOGLE_ADS_LOGIN_CUSTOMER_ID

    _client = GoogleAdsClient.load_from_dict(credentials)
    return _client


def detect_google_campaign_type(name: str) -> str:
    """Retorna 'GOOGLE_CONVERSAO' se nome contém [CONVERSÃO]/[CONVERSAO]/[LEAD], senão 'GOOGLE_DEFAULT'."""
    n = (name or "").upper()
    if "[CONVERSÃO]" in n or "[CONVERSAO]" in n or "[LEAD]" in n:
        return "GOOGLE_CONVERSAO"
    return "GOOGLE_DEFAULT"


def _micros_to_brl(micros: Optional[int]) -> float:
    if not micros:
        return 0.0
    return float(micros) / 1_000_000


def _run_query(customer_id: str, query: str):
    client = get_client()
    ga_service = client.get_service("GoogleAdsService")
    cid = _normalize_customer_id(customer_id)
    return ga_service.search(customer_id=cid, query=query)


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

def fetch_account_spend_mtd(customer_id: str) -> dict:
    """Gasto do mês até hoje (MTD), na moeda da conta."""
    today = date.today()
    first_of_month = today.replace(day=1).isoformat()
    today_str = today.isoformat()

    query = f"""
        SELECT customer.currency_code, metrics.cost_micros
        FROM customer
        WHERE segments.date BETWEEN '{first_of_month}' AND '{today_str}'
    """

    spend = 0.0
    currency = "BRL"
    try:
        for row in _run_query(customer_id, query):
            spend += _micros_to_brl(row.metrics.cost_micros)
            currency = row.customer.currency_code or currency
    except Exception as e:
        raise GoogleAdsServiceError(f"Erro ao buscar gasto MTD ({customer_id}): {e}") from e

    return {"spend_mtd": round(spend, 2), "currency": currency}


def fetch_weekly_summary(customer_id: str, days: int = 7) -> dict:
    """Resumo agregado dos últimos N dias da conta."""
    duration = {7: "LAST_7_DAYS", 14: "LAST_14_DAYS", 30: "LAST_30_DAYS"}.get(days, "LAST_7_DAYS")
    query = f"""
        SELECT metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions
        FROM customer
        WHERE segments.date DURING {duration}
    """

    spend = 0.0
    impressions = 0
    clicks = 0
    conversions = 0.0
    try:
        for row in _run_query(customer_id, query):
            spend += _micros_to_brl(row.metrics.cost_micros)
            impressions += int(row.metrics.impressions or 0)
            clicks += int(row.metrics.clicks or 0)
            conversions += float(row.metrics.conversions or 0)
    except Exception as e:
        raise GoogleAdsServiceError(f"Erro ao buscar resumo semanal ({customer_id}): {e}") from e

    return {
        "spend": round(spend, 2),
        "impressions": impressions,
        "clicks": clicks,
        "conversions": round(conversions, 2),
    }


def fetch_campaigns_for_dashboard(customer_id: str, days: int = 7, campaign_filter: str = "") -> list[dict]:
    """Campanhas habilitadas com gasto no período."""
    duration = {7: "LAST_7_DAYS", 14: "LAST_14_DAYS", 30: "LAST_30_DAYS"}.get(days, "LAST_7_DAYS")
    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            metrics.cost_micros,
            metrics.clicks,
            metrics.impressions,
            metrics.conversions,
            metrics.cost_per_conversion
        FROM campaign
        WHERE segments.date DURING {duration}
          AND campaign.status = 'ENABLED'
          AND metrics.cost_micros > 0
        ORDER BY metrics.cost_micros DESC
    """

    filter_tokens = _parse_filter(campaign_filter)
    campaigns: list[dict] = []
    try:
        for row in _run_query(customer_id, query):
            name = row.campaign.name or ""
            if filter_tokens and not _name_matches(name, filter_tokens):
                continue

            spend = _micros_to_brl(row.metrics.cost_micros)
            clicks = int(row.metrics.clicks or 0)
            impressions = int(row.metrics.impressions or 0)
            conversions = float(row.metrics.conversions or 0)
            cpc = (spend / clicks) if clicks > 0 else 0.0
            cost_per_conv = _micros_to_brl(row.metrics.cost_per_conversion)
            ctype = detect_google_campaign_type(name)

            campaigns.append({
                "campaign_id": str(row.campaign.id),
                "campaign_name": name,
                "campaign_type": ctype,
                "type_label": "Conversão / Lead" if ctype == "GOOGLE_CONVERSAO" else "Google Ads",
                "spend": round(spend, 2),
                "clicks": clicks,
                "impressions": impressions,
                "cpc": round(cpc, 2),
                "conversions": round(conversions, 2) if ctype == "GOOGLE_CONVERSAO" else None,
                "cost_per_conversion": round(cost_per_conv, 2) if ctype == "GOOGLE_CONVERSAO" else None,
            })
    except Exception as e:
        raise GoogleAdsServiceError(f"Erro ao buscar campanhas ({customer_id}): {e}") from e

    return campaigns


def _parse_filter(campaign_filter: str) -> list[str]:
    """Suporta filtros tipo '[TELHAS]' ou '[PISOS]|[BLOCOS]' (case-insensitive)."""
    if not campaign_filter:
        return []
    return [t.strip().upper() for t in campaign_filter.split("|") if t.strip()]


def _name_matches(name: str, tokens: list[str]) -> bool:
    n = name.upper()
    return any(t in n for t in tokens)
