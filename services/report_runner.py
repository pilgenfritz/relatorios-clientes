import threading
import time
from datetime import datetime

from services import meta_service, whatsapp_service
from services.meta_service import get_campaigns_table

_progress: dict[str, dict] = {}
_lock = threading.Lock()


def _set(job_id: str, **kwargs):
    with _lock:
        _progress[job_id].update(kwargs)


def get_progress(job_id: str) -> dict:
    with _lock:
        return dict(_progress.get(job_id, {"status": "not_found"}))


def get_all_progress() -> dict:
    with _lock:
        return {k: dict(v) for k, v in _progress.items()}


def run_report_for_account(job_id: str, account: dict) -> None:
    with _lock:
        _progress[job_id] = {
            "status": "running",
            "current_step": "Iniciando...",
            "steps_done": 0,
            "steps_total": 3,
            "error_message": None,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "client_name": account.get("client_name", ""),
            "account_id": account.get("account_id", ""),
        }

    try:
        # Passo 1: Busca dados no Meta
        _set(job_id, current_step="Buscando dados no Meta Ads...", steps_done=0)
        insights = meta_service.fetch_campaign_insights(
            account["account_id"], account["metrics_list"]
        )

        # Passo 2: Calcula resumo e monta tabela de campanhas
        _set(job_id, current_step="Calculando métricas...", steps_done=1)
        summary = meta_service.compute_summary(insights, account["metrics_list"])
        result_configs = meta_service.fetch_campaign_result_configs(account["account_id"])
        campaigns_table = get_campaigns_table(insights, account["metrics_list"], result_configs)

        # Passo 3: Envia mensagem via WhatsApp
        _set(job_id, current_step="Enviando via WhatsApp...", steps_done=2)
        whatsapp_service.send_report(
            phone=account["whatsapp"],
            client_name=account["client_name"],
            summary=summary,
            campaigns_table=campaigns_table,
        )

        # Concluído
        _set(
            job_id,
            status="done",
            current_step="Concluído!",
            steps_done=3,
            finished_at=datetime.now().isoformat(),
        )

    except Exception as e:
        _set(
            job_id,
            status="error",
            current_step="Erro durante processamento",
            error_message=str(e),
            finished_at=datetime.now().isoformat(),
        )
        print(f"[Runner] Erro em {account.get('account_id')}: {e}")


def run_all_accounts(accounts: list[dict]) -> list[str]:
    """Dispara uma thread por conta e retorna lista de job_ids."""
    job_ids = []
    for i, account in enumerate(accounts):
        timestamp = int(time.time() * 1000) + i
        job_id = f"{account['account_id']}_{timestamp}"
        job_ids.append(job_id)

        t = threading.Thread(
            target=run_report_for_account,
            args=(job_id, account),
            daemon=True,
        )
        t.start()

        # Pequeno atraso para evitar burst na API do Meta
        if i < len(accounts) - 1:
            time.sleep(1)

    return job_ids
