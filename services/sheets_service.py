import json
import os
import gspread
from google.oauth2.service_account import Credentials
from config import config

WORKSHEET_NAME = os.getenv("SPREADSHEET_SHEET", "Página3")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


class SheetsError(Exception):
    pass


def _get_client() -> gspread.Client:
    try:
        # Prioriza JSON inline via variável de ambiente (para containers)
        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if sa_json:
            info = json.loads(sa_json)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(
                config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
        return gspread.authorize(creds)
    except FileNotFoundError:
        raise SheetsError(
            f"Arquivo de credenciais não encontrado: {config.GOOGLE_SERVICE_ACCOUNT_FILE}"
        )
    except Exception as e:
        raise SheetsError(f"Erro ao autenticar no Google: {e}")


def get_all_accounts() -> list[dict]:
    """
    Lê todas as contas da aba da planilha.

    Colunas esperadas:
      Nome | ID da Conta de Anúncios | Grupo WhatsApp | Objetivo | Métricas
    """
    try:
        client = _get_client()
        spreadsheet = client.open_by_key(config.SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        rows = worksheet.get_all_records()
    except gspread.exceptions.SpreadsheetNotFound:
        raise SheetsError(f"Planilha não encontrada. SPREADSHEET_ID: {config.SPREADSHEET_ID}")
    except gspread.exceptions.WorksheetNotFound:
        raise SheetsError(f"Aba '{WORKSHEET_NAME}' não encontrada na planilha.")
    except gspread.exceptions.APIError as e:
        raise SheetsError(f"Erro na API do Google Sheets: {e}")
    except SheetsError:
        raise
    except Exception as e:
        raise SheetsError(f"Erro inesperado ao ler planilha: {e}")

    accounts = []
    for i, row in enumerate(rows, start=2):
        client_name = str(row.get("Nome", "")).strip()
        account_id  = str(row.get("ID da Conta de Anúncios", "")).strip()
        whatsapp    = str(row.get("Grupo WhatsApp", "")).strip()
        objective   = str(row.get("Objetivo", "")).strip()
        metrics_raw = str(row.get("Métricas", "")).strip()

        if not account_id or not client_name:
            continue

        # Garante prefixo act_
        if not account_id.startswith("act_"):
            account_id = f"act_{account_id}"

        # Parse métricas: split por vírgula, lowercase, strip
        metrics_list = [m.strip().lower() for m in metrics_raw.split(",") if m.strip()]

        if not metrics_list:
            print(f"[Sheets] Linha {i}: sem métricas para {client_name}, pulando.")
            continue

        accounts.append({
            "account_id": account_id,
            "client_name": client_name,
            "objective": objective,
            "metrics_raw": metrics_raw,
            "metrics_list": metrics_list,
            "whatsapp": whatsapp,
        })

    return accounts
