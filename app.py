import json
import time
from pathlib import Path

from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for, flash

import concurrent.futures

from config import config
from services import meta_service, report_runner, sheets_service

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

# Garante que o diretório de relatórios existe
config.REPORTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == config.DASHBOARD_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "Senha incorreta"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ──────────────────────────────────────────────────────────────
# INDEX
# ──────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    accounts = []
    error = None
    try:
        accounts = sheets_service.get_all_accounts()
    except sheets_service.SheetsError as e:
        error = str(e)
    return render_template("index.html", accounts=accounts, error=error)


# ──────────────────────────────────────────────────────────────
# RUN — dispara jobs em background
# ──────────────────────────────────────────────────────────────

@app.route("/run/all", methods=["POST"])
@login_required
def run_all():
    try:
        accounts = sheets_service.get_all_accounts()
    except sheets_service.SheetsError as e:
        return jsonify({"error": str(e)}), 500

    if not accounts:
        return jsonify({"error": "Nenhuma conta encontrada na planilha."}), 400

    job_ids = report_runner.run_all_accounts(accounts)
    return jsonify({"job_ids": job_ids})


@app.route("/run/<path:account_id>", methods=["POST"])
@login_required
def run_single(account_id):
    # account_id pode vir sem o prefixo act_
    if not account_id.startswith("act_"):
        account_id = f"act_{account_id}"

    try:
        accounts = sheets_service.get_all_accounts()
    except sheets_service.SheetsError as e:
        return jsonify({"error": str(e)}), 500

    account = next((a for a in accounts if a["account_id"] == account_id), None)
    if not account:
        return jsonify({"error": f"Conta {account_id} não encontrada na planilha."}), 404

    timestamp = int(time.time() * 1000)
    job_id = f"{account_id}_{timestamp}"

    import threading
    t = threading.Thread(
        target=report_runner.run_report_for_account,
        args=(job_id, account),
        daemon=True,
    )
    t.start()

    return jsonify({"job_id": job_id})


# ──────────────────────────────────────────────────────────────
# PROGRESS
# ──────────────────────────────────────────────────────────────

@app.route("/progress/<job_id>")
@login_required
def progress(job_id):
    return jsonify(report_runner.get_progress(job_id))


@app.route("/progress/all")
@login_required
def progress_all():
    return jsonify(report_runner.get_all_progress())


# ──────────────────────────────────────────────────────────────
# DASHBOARD API
# ──────────────────────────────────────────────────────────────

@app.route("/api/dashboard")
@login_required
def api_dashboard():
    """Retorna dados completos do dashboard: contas + saldo + resumo semanal."""
    try:
        accounts = sheets_service.get_all_accounts()
        budgets = sheets_service.get_budgets()
    except sheets_service.SheetsError as e:
        return jsonify({"error": str(e)}), 500

    def fetch_account_data(account):
        aid = account["account_id"]
        balance_info = meta_service.fetch_account_balance(aid)
        weekly = meta_service.fetch_weekly_summary(aid)
        budget = budgets.get(aid, 0)

        balance = balance_info["balance"]
        if balance is not None:
            threshold = 200 if budget > 1500 else 100
            if balance < threshold:
                balance_status = "danger"
            elif balance < threshold * 2:
                balance_status = "warning"
            else:
                balance_status = "healthy"
        else:
            balance_status = "postpaid"
            threshold = 0

        return {
            "account_id": aid,
            "client_name": account["client_name"],
            "whatsapp": account["whatsapp"],
            "is_prepaid": balance_info["is_prepaid"],
            "payment_label": "Pré-pago" if balance_info["is_prepaid"] else "Pós-pago",
            "balance": balance,
            "balance_status": balance_status,
            "budget": budget,
            "threshold": threshold,
            "weekly": weekly,
        }

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_account_data, a): a for a in accounts}
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                account = futures[future]
                results.append({
                    "account_id": account["account_id"],
                    "client_name": account["client_name"],
                    "whatsapp": account["whatsapp"],
                    "error": str(e),
                })

    results.sort(key=lambda x: x.get("client_name", ""))
    return jsonify({"accounts": results})


@app.route("/api/campaigns/<path:account_id>")
@login_required
def api_campaigns(account_id):
    """Retorna campanhas ativas da conta agrupadas por tipo, com métricas do período."""
    if not account_id.startswith("act_"):
        account_id = f"act_{account_id}"
    days = request.args.get("days", 7, type=int)
    if days not in (7, 14, 30):
        days = 7
    try:
        campaigns = meta_service.fetch_campaigns_for_dashboard(account_id, days)
        return jsonify({"campaigns": campaigns, "days": days})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────
# DOWNLOAD
# ──────────────────────────────────────────────────────────────

@app.route("/download/<filename>")
def download(filename):
    # Segurança: só permite servir arquivos do diretório de relatórios
    safe_name = Path(filename).name
    return send_from_directory(
        config.REPORTS_OUTPUT_DIR.resolve(),
        safe_name,
        as_attachment=True,
        mimetype="application/pdf",
    )


# ──────────────────────────────────────────────────────────────
# LISTA DE PDFs GERADOS
# ──────────────────────────────────────────────────────────────

@app.route("/reports")
def list_reports():
    files = sorted(
        config.REPORTS_OUTPUT_DIR.glob("*.pdf"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    reports = [{"name": f.name, "size_kb": round(f.stat().st_size / 1024, 1)} for f in files]
    return jsonify(reports)


if __name__ == "__main__":
    app.run(debug=True, threaded=True, host="0.0.0.0", port=5000)
