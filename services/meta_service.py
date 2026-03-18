from datetime import date, timedelta
import requests
from config import config

# ──────────────────────────────────────────────────────────────
# Campos fixos sempre requisitados à API
# ──────────────────────────────────────────────────────────────
API_BASE_FIELDS = [
    "spend", "impressions", "clicks", "reach", "ctr", "cpm", "cpc",
    "actions", "unique_actions", "action_values", "cost_per_action_type",
    "video_30_sec_watched_actions",
]
ALWAYS_INCLUDE = ["campaign_name", "campaign_id", "date_start", "date_stop"]

# ──────────────────────────────────────────────────────────────
# Mapeamento optimization_goal → (result_key, result_label)
# Determina a "métrica de resultado" que o Meta Ads Manager mostra
# ──────────────────────────────────────────────────────────────
# result_key: chave interna usada nos rows (coincide com action_types abaixo)
OPTIMIZATION_GOAL_MAP: dict[str, tuple[str, str]] = {
    "PROFILE_VISIT":           ("link_click",      "Visitas ao Perfil"),
    "VISIT_INSTAGRAM_PROFILE": ("link_click",      "Visitas ao Perfil"),
    "LINK_CLICKS":             ("link_click",      "Cliques no Link"),
    "LANDING_PAGE_VIEWS":      ("landing_page_view","Visitas à Página"),
    "CONVERSATIONS":           ("messages",        "Mensagens"),
    "REPLIES":                 ("messages",        "Mensagens"),
    "LEAD_GENERATION":         ("leads",           "Leads"),
    "OFFSITE_CONVERSIONS":     ("purchases",       "Conversões"),
    "VALUE":                   ("purchase_value",  "Valor em Compras"),
    "REACH":                   ("reach",           "Alcance"),
    "IMPRESSIONS":             ("impressions",     "Impressões"),
    "VIDEO_VIEWS":             ("video_views",     "Views de Vídeo"),
    "THRUPLAY":                ("video_views",     "ThruPlays"),
    "POST_ENGAGEMENT":         ("post_engagement", "Engajamento"),
    "PAGE_LIKES":              ("post_engagement", "Curtidas"),
}
OPTIMIZATION_GOAL_DEFAULT = ("link_click", "Cliques")


# ──────────────────────────────────────────────────────────────
# Detecção de tipo de campanha pela tag no nome
# ──────────────────────────────────────────────────────────────

def detect_campaign_type(name: str) -> str:
    n = name.upper()
    if "[E-COMMERCE]" in n:
        return "ECOMMERCE"
    if "[LEAD]" in n:
        return "LEAD"
    if "[MSG]" in n:
        return "MSG"
    if "[IG]" in n:
        return "IG"
    if "[SITE]" in n:
        return "SITE"
    return "OTHER"


CAMPAIGN_TYPE_COLUMNS: dict[str, list[dict]] = {
    "IG": [
        {"key": "impressions",         "label": "Impressões"},
        {"key": "link_click",          "label": "Tráfego no Perfil"},
        {"key": "cost_per_link_click", "label": "Custo/Visita ao Perfil"},
        {"key": "spend",               "label": "Valor Gasto"},
    ],
    "SITE": [
        {"key": "impressions",         "label": "Impressões"},
        {"key": "link_click",          "label": "Cliques"},
        {"key": "landing_page_view",   "label": "Views Pág. Destino"},
        {"key": "cost_per_link_click", "label": "Custo/Clique"},
        {"key": "spend",               "label": "Valor Gasto"},
    ],
    "MSG": [
        {"key": "impressions",         "label": "Impressões"},
        {"key": "messages",            "label": "Mensagens"},
        {"key": "cost_per_message",    "label": "Custo/Mensagem"},
        {"key": "spend",               "label": "Valor Gasto"},
    ],
    "ECOMMERCE": [
        {"key": "impressions",         "label": "Impressões"},
        {"key": "link_click",          "label": "Cliques"},
        {"key": "landing_page_view",   "label": "Views Pág. Destino"},
        {"key": "cost_per_link_click", "label": "Custo/Clique"},
        {"key": "add_to_cart",         "label": "Ad. Carrinho"},
        {"key": "initiate_checkout",   "label": "Inic. Compra"},
        {"key": "purchases",           "label": "Compras"},
        {"key": "cost_per_purchase",   "label": "Custo/Compra"},
        {"key": "purchase_value",      "label": "Valor em Compras"},
    ],
    "LEAD": [
        {"key": "impressions",         "label": "Impressões"},
        {"key": "link_click",          "label": "Cliques"},
        {"key": "landing_page_view",   "label": "Views Pág. Destino"},
        {"key": "cost_per_link_click", "label": "Custo/Clique"},
        {"key": "leads",               "label": "Leads"},
        {"key": "cost_per_lead",       "label": "Custo/Lead"},
        {"key": "spend",               "label": "Valor Gasto"},
    ],
    "OTHER": [
        {"key": "impressions",         "label": "Impressões"},
        {"key": "link_click",          "label": "Cliques"},
        {"key": "spend",               "label": "Valor Gasto"},
    ],
}

CAMPAIGN_TYPE_LABELS: dict[str, str] = {
    "IG":       "Tráfego no Perfil [IG]",
    "SITE":     "Tráfego no Site [SITE]",
    "MSG":      "Mensagens [MSG]",
    "ECOMMERCE":"Vendas / E-commerce [E-COMMERCE]",
    "LEAD":     "Captação de Leads [LEAD]",
    "OTHER":    "Outras Campanhas",
}


# Labels de objetivo de campanha (para a coluna "Tipo")
OBJECTIVE_LABELS: dict[str, str] = {
    "OUTCOME_TRAFFIC":    "Tráfego",
    "OUTCOME_ENGAGEMENT": "Engajamento",
    "OUTCOME_MESSAGES":   "Mensagens",
    "OUTCOME_LEADS":      "Leads",
    "OUTCOME_SALES":      "Vendas",
    "OUTCOME_AWARENESS":  "Alcance",
    "VIDEO_VIEWS":        "Visualizações",
    "MESSAGES":           "Mensagens",
    "LINK_CLICKS":        "Cliques",
    "REACH":              "Alcance",
    "PAGE_LIKES":         "Curtidas",
}

# ──────────────────────────────────────────────────────────────
# Configuração de cada métrica em português (para KPI cards)
# ──────────────────────────────────────────────────────────────
METRICS_CONFIG: dict[str, dict] = {
    "visitas ao perfil": {
        "key": "profile_visits",
        "label": "Visitas ao Perfil",
        "type": "action",
        "action_types": ["link_click"],   # para campanhas PROFILE_VISIT, link_click = visita ao perfil
        "format": "number",
    },
    "cliques": {
        "key": "link_click",
        "label": "Cliques no Link",
        "type": "action",
        "action_types": ["link_click"],
        "format": "number",
    },
    "visualizações de vídeo": {
        "key": "video_views",
        "label": "Views de Vídeo",
        "type": "video",
        "format": "number",
    },
    "impressão": {
        "key": "impressions",
        "label": "Impressões",
        "type": "direct",
        "api_field": "impressions",
        "format": "number",
    },
    "impressões": {
        "key": "impressions",
        "label": "Impressões",
        "type": "direct",
        "api_field": "impressions",
        "format": "number",
    },
    "valor gasto": {
        "key": "spend",
        "label": "Valor Gasto",
        "type": "direct",
        "api_field": "spend",
        "format": "currency",
    },
    "custo por clique": {
        "key": "cost_per_link_click",
        "label": "Custo por Clique",
        "type": "computed",
        "formula_num": "spend",
        "formula_den": "link_click",
        "format": "currency",
    },
    "custo por visita ao perfil": {
        "key": "cost_per_profile_visit",
        "label": "Custo por Visita ao Perfil",
        "type": "computed",
        "formula_num": "spend",
        "formula_den": "profile_visits",
        "format": "currency",
    },
    "mensagens": {
        "key": "messages",
        "label": "Mensagens",
        "type": "action",
        "action_types": [
            "onsite_conversion.messaging_conversation_started_7d",
            "onsite_conversion.total_messaging_connection",
        ],
        "format": "number",
    },
    "custo por mensagem": {
        "key": "cost_per_message",
        "label": "Custo por Mensagem",
        "type": "computed",
        "formula_num": "spend",
        "formula_den": "messages",
        "format": "currency",
    },
    "adições ao carrinho": {
        "key": "add_to_cart",
        "label": "Adições ao Carrinho",
        "type": "action",
        "action_types": ["add_to_cart"],
        "format": "number",
    },
    "inicialização de compras": {
        "key": "initiate_checkout",
        "label": "Inic. de Compras",
        "type": "action",
        "action_types": ["initiate_checkout"],
        "format": "number",
    },
    "compras": {
        "key": "purchases",
        "label": "Compras",
        "type": "action",
        "action_types": ["purchase"],
        "format": "number",
    },
    "custo por compra": {
        "key": "cost_per_purchase",
        "label": "Custo por Compra",
        "type": "computed",
        "formula_num": "spend",
        "formula_den": "purchases",
        "format": "currency",
    },
    "valor em compra": {
        "key": "purchase_value",
        "label": "Valor em Compras",
        "type": "action_value",
        "action_types": ["purchase"],
        "format": "currency",
    },
    "leads": {
        "key": "leads",
        "label": "Leads",
        "type": "action",
        "action_types": [
            "lead", "offsite_conversion.fb_pixel_lead",
            "onsite_conversion.lead_grouped", "onsite_conversion.lead",
        ],
        "format": "number",
    },
    "custo por lead": {
        "key": "cost_per_lead",
        "label": "Custo por Lead",
        "type": "computed",
        "formula_num": "spend",
        "formula_den": "leads",
        "format": "currency",
    },
}

# Métricas que são médias (não soma) ao agregar
AVERAGE_KEYS = {
    "cpc", "cpm", "ctr",
    "cost_per_link_click", "cost_per_profile_visit",
    "cost_per_message", "cost_per_purchase", "cost_per_lead",
}

# Sempre extraídos em _flatten_row (independente de métricas solicitadas)
_ALWAYS_EXTRACT_ACTIONS = {
    "link_click":        (["link_click"], "actions"),
    "landing_page_view": (["landing_page_view", "omni_landing_page_view"], "actions"),
    "post_engagement":   (["post_engagement"], "actions"),
    "video_views":       (None, "video"),   # tratado especialmente
    "messages":          (["onsite_conversion.messaging_conversation_started_7d",
                           "onsite_conversion.total_messaging_connection"], "actions"),
    "purchases":         (["purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"], "actions"),
    "leads":             (["lead", "offsite_conversion.fb_pixel_lead",
                           "onsite_conversion.lead_grouped"], "actions"),
    "reach":             (None, "direct_reach"),
}


class MetaAPIError(Exception):
    def __init__(self, message: str, code: int = None):
        super().__init__(message)
        self.code = code


def get_metric_config(portuguese_name: str) -> dict | None:
    return METRICS_CONFIG.get(portuguese_name.strip().lower())


def _get_date_range() -> tuple[str, str]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=6)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


# ──────────────────────────────────────────────────────────────
# Busca objetivos e optimization_goal por campanha
# ──────────────────────────────────────────────────────────────

def fetch_campaign_result_configs(account_id: str) -> dict[str, dict]:
    """
    Retorna {campaign_id: {result_key, result_label, objective, objective_label}}
    Combina dados de campaigns + adsets para determinar a métrica de resultado por campanha.
    """
    # 1. Objetivos das campanhas
    camp_resp = requests.get(
        f"{config.META_BASE_URL}/{account_id}/campaigns",
        params={
            "access_token": config.META_ACCESS_TOKEN,
            "fields": "id,name,objective",
            "limit": 200,
        },
        timeout=20,
    )
    campaign_objectives: dict[str, str] = {}
    for c in camp_resp.json().get("data", []):
        campaign_objectives[c["id"]] = c.get("objective", "UNKNOWN")

    # 2. optimization_goal por ad set
    adset_resp = requests.get(
        f"{config.META_BASE_URL}/{account_id}/adsets",
        params={
            "access_token": config.META_ACCESS_TOKEN,
            "fields": "id,campaign_id,optimization_goal,destination_type",
            "filtering": '[{"field":"effective_status","operator":"IN","value":["ACTIVE","PAUSED"]}]',
            "limit": 500,
        },
        timeout=20,
    )

    # Para cada campanha, pega o optimization_goal mais comum entre os ad sets
    from collections import Counter
    campaign_goals: dict[str, Counter] = {}
    for a in adset_resp.json().get("data", []):
        cid = a.get("campaign_id", "")
        goal = a.get("optimization_goal", "")
        if cid and goal:
            if cid not in campaign_goals:
                campaign_goals[cid] = Counter()
            campaign_goals[cid][goal] += 1

    # 3. Monta config final por campanha
    result: dict[str, dict] = {}
    for cid, objective in campaign_objectives.items():
        if cid in campaign_goals:
            most_common_goal = campaign_goals[cid].most_common(1)[0][0]
        else:
            most_common_goal = None

        result_key, result_label = OPTIMIZATION_GOAL_MAP.get(
            most_common_goal, OPTIMIZATION_GOAL_DEFAULT
        )

        result[cid] = {
            "objective":       objective,
            "objective_label": OBJECTIVE_LABELS.get(objective, objective),
            "optimization_goal": most_common_goal or "",
            "result_key":      result_key,
            "result_label":    result_label,
        }

    return result


# ──────────────────────────────────────────────────────────────
# Insights
# ──────────────────────────────────────────────────────────────

def fetch_campaign_insights(account_id: str, metrics_pt: list[str]) -> list[dict]:
    """
    Busca insights dos últimos 7 dias para uma conta.
    Retorna linhas diárias por campanha com valores extraídos.
    """
    date_start, date_stop = _get_date_range()
    fields = list(dict.fromkeys(API_BASE_FIELDS + ALWAYS_INCLUDE))

    params = {
        "access_token": config.META_ACCESS_TOKEN,
        "time_range": f'{{"since":"{date_start}","until":"{date_stop}"}}',
        "level": "campaign",
        "fields": ",".join(fields),
        "time_increment": 1,
        "limit": 100,
    }

    url = f"{config.META_BASE_URL}/{account_id}/insights"
    raw_rows: list[dict] = []

    while url:
        try:
            resp = requests.get(
                url,
                params=params if "?" not in url else None,
                timeout=30,
            )
        except requests.exceptions.Timeout:
            raise MetaAPIError("Timeout ao conectar na API do Meta Ads.")
        except requests.exceptions.ConnectionError as e:
            raise MetaAPIError(f"Erro de conexão com a API do Meta Ads: {e}")

        data = resp.json()

        if "error" in data:
            err = data["error"]
            raise MetaAPIError(
                f"Erro Meta API [{err.get('code')}]: {err.get('message', 'desconhecido')}",
                code=err.get("code"),
            )

        raw_rows.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
        params = None

    return [_flatten_row(r, metrics_pt) for r in raw_rows]


def _extract_action(row: dict, action_types: list[str], field: str = "actions") -> float:
    actions = row.get(field, [])
    total = 0.0
    for a in actions:
        if a.get("action_type") in action_types:
            try:
                total += float(a.get("value", 0))
            except (ValueError, TypeError):
                pass
    return total


def _flatten_row(raw: dict, metrics_pt: list[str]) -> dict:
    """
    Converte um row bruto da API em dict normalizado.
    Sempre extrai campos base + link_click + landing_page_view + actions chave.
    """
    row: dict = {
        "campaign_name": raw.get("campaign_name", ""),
        "campaign_id":   raw.get("campaign_id", ""),
        "date_start":    raw.get("date_start", ""),
        "date_stop":     raw.get("date_stop", ""),
    }

    # Campos diretos sempre extraídos
    for field in ("spend", "impressions", "clicks", "reach", "ctr", "cpm", "cpc"):
        try:
            row[field] = float(raw.get(field, 0) or 0)
        except (ValueError, TypeError):
            row[field] = 0.0

    # Actions sempre extraídas (base para per-campaign result)
    row["link_click"]        = _extract_action(raw, ["link_click"])
    row["landing_page_view"] = _extract_action(raw, ["landing_page_view"])
    row["post_engagement"]   = _extract_action(raw, ["post_engagement"])
    row["messages"]          = _extract_action(raw, [
        "onsite_conversion.messaging_conversation_started_7d",
        "onsite_conversion.total_messaging_connection",
    ])
    row["purchases"]         = _extract_action(raw, ["purchase"])
    row["leads"]             = _extract_action(raw, [
        "lead", "offsite_conversion.fb_pixel_lead",
        "onsite_conversion.lead_grouped", "onsite_conversion.lead",
    ])
    row["add_to_cart"]       = _extract_action(raw, ["add_to_cart"])
    row["initiate_checkout"] = _extract_action(raw, ["initiate_checkout"])
    row["purchase_value"]    = _extract_action(raw, ["purchase"], field="action_values")

    # Vídeo: 30s watched actions
    row["video_views"] = _extract_action(raw, ["video_view"], field="video_30_sec_watched_actions")
    if row["video_views"] == 0.0:
        row["video_views"] = sum(
            float(a.get("value", 0))
            for a in raw.get("video_30_sec_watched_actions", [])
            if a.get("value")
        )

    # Métricas solicitadas em português (usadas nos KPI cards)
    for pt_name in metrics_pt:
        cfg = METRICS_CONFIG.get(pt_name)
        if not cfg:
            continue
        key = cfg["key"]
        mtype = cfg["type"]

        if key in row:
            continue  # já foi extraído acima

        if mtype == "direct":
            try:
                row[key] = float(raw.get(cfg["api_field"], 0) or 0)
            except (ValueError, TypeError):
                row[key] = 0.0
        elif mtype == "action":
            row[key] = _extract_action(raw, cfg["action_types"])
        elif mtype == "action_multi_source":
            val = 0.0
            for source in cfg.get("sources", ["actions"]):
                val = _extract_action(raw, cfg["action_types"], field=source)
                if val > 0:
                    break
            row[key] = val
        elif mtype == "action_value":
            row[key] = _extract_action(raw, cfg["action_types"], field="action_values")
        elif mtype == "computed":
            row[key] = None  # resolvido abaixo

    # "visitas ao perfil" = link_click (para campanhas com optimization_goal PROFILE_VISIT)
    if "profile_visits" not in row:
        row["profile_visits"] = row["link_click"]

    # Resolve computed
    for pt_name in metrics_pt:
        cfg = METRICS_CONFIG.get(pt_name)
        if not cfg or cfg["type"] != "computed":
            continue
        key = cfg["key"]
        num = row.get(cfg["formula_num"], 0.0) or 0.0
        den = row.get(cfg["formula_den"], 0.0) or 0.0
        row[key] = round(num / den, 4) if den > 0 else 0.0

    return row


def compute_summary(rows: list[dict], metrics_pt: list[str]) -> dict:
    """Agrega linhas diárias num resumo único (KPI cards)."""
    keys_volume: list[str] = []
    keys_computed: list[dict] = []

    for pt in metrics_pt:
        cfg = METRICS_CONFIG.get(pt)
        if not cfg:
            continue
        if cfg["type"] == "computed":
            keys_computed.append(cfg)
        else:
            keys_volume.append(cfg["key"])

    totals: dict[str, float] = {k: 0.0 for k in keys_volume}
    for row in rows:
        for k in keys_volume:
            totals[k] = totals.get(k, 0.0) + (row.get(k) or 0.0)

    summary = dict(totals)

    for cfg in keys_computed:
        key = cfg["key"]
        num = summary.get(cfg["formula_num"], 0.0)
        den = summary.get(cfg["formula_den"], 0.0)
        summary[key] = round(num / den, 4) if den > 0 else 0.0

    if rows:
        dates = sorted({r.get("date_start", "") for r in rows if r.get("date_start")})
        summary["period_start"] = dates[0] if dates else ""
        summary["period_end"]   = dates[-1] if dates else ""

    return summary


def get_campaigns_table(
    rows: list[dict],
    metrics_pt: list[str],
    campaign_result_configs: dict[str, dict] | None = None,
) -> list[dict]:
    """
    Agrega linhas diárias por campanha.
    Cada entrada inclui a métrica de resultado específica da campanha.
    """
    campaigns: dict[str, dict] = {}
    volume_keys: list[str] = []
    computed_cfgs: list[dict] = []

    for pt in metrics_pt:
        cfg = METRICS_CONFIG.get(pt)
        if not cfg:
            continue
        if cfg["type"] == "computed":
            computed_cfgs.append(cfg)
        else:
            volume_keys.append(cfg["key"])

    # Garante que campos base estejam sempre agregados
    base_keys = ["link_click", "landing_page_view", "messages", "purchases",
                 "leads", "video_views", "add_to_cart", "post_engagement",
                 "purchase_value", "reach", "impressions", "spend"]
    all_keys = list(dict.fromkeys(volume_keys + base_keys))

    for row in rows:
        cid = row.get("campaign_id", "")
        if not cid:
            continue
        if cid not in campaigns:
            cname = row.get("campaign_name", "")
            campaigns[cid] = {
                "campaign_name": cname,
                "campaign_id":   cid,
                "campaign_type": detect_campaign_type(cname),
                **{k: 0.0 for k in all_keys},
            }
        for k in all_keys:
            campaigns[cid][k] = campaigns[cid].get(k, 0.0) + (row.get(k) or 0.0)

    # Resolve computed e adiciona métricas de resultado por campanha
    _ALWAYS_COMPUTED = [
        ("cost_per_link_click", "spend", "link_click"),
        ("cost_per_message",    "spend", "messages"),
        ("cost_per_purchase",   "spend", "purchases"),
        ("cost_per_lead",       "spend", "leads"),
    ]
    for cid, cdata in campaigns.items():
        # Computed das métricas do cliente
        for cfg in computed_cfgs:
            num = cdata.get(cfg["formula_num"], 0.0)
            den = cdata.get(cfg["formula_den"], 0.0)
            cdata[cfg["key"]] = round(num / den, 4) if den > 0 else 0.0

        # Computed sempre necessários para tabelas por tipo
        for key, num_k, den_k in _ALWAYS_COMPUTED:
            if key not in cdata or cdata.get(key, 0.0) == 0.0:
                den = cdata.get(den_k, 0.0)
                cdata[key] = round(cdata["spend"] / den, 4) if den > 0 else 0.0

        # Resultado específico da campanha
        rc = (campaign_result_configs or {}).get(cid, {})
        result_key   = rc.get("result_key", "link_click")
        result_label = rc.get("result_label", "Cliques")
        result_value = cdata.get(result_key, 0.0)

        cdata["objective"]       = rc.get("objective", "")
        cdata["objective_label"] = rc.get("objective_label", "")
        cdata["result_key"]      = result_key
        cdata["result_label"]    = result_label
        cdata["result_value"]    = result_value
        cdata["cost_per_result"] = round(cdata["spend"] / result_value, 4) if result_value > 0 else 0.0

    result = list(campaigns.values())
    result.sort(key=lambda x: x.get("spend", 0), reverse=True)
    return result
