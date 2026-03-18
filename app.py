import json
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory, flash

from config import config
from services import report_runner, sheets_service

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

# Garante que o diretório de relatórios existe
config.REPORTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────
# INDEX
# ──────────────────────────────────────────────────────────────

@app.route("/")
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
def progress(job_id):
    return jsonify(report_runner.get_progress(job_id))


@app.route("/progress/all")
def progress_all():
    return jsonify(report_runner.get_all_progress())


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
