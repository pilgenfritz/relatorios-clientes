import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_REQUIRED = [
    "SPREADSHEET_ID",
    "META_ACCESS_TOKEN",
    "ZAPI_INSTANCE_ID",
    "ZAPI_TOKEN",
    "ZAPI_CLIENT_TOKEN",
    "FLASK_SECRET_KEY",
]


def _validate():
    missing = [k for k in _REQUIRED if not os.getenv(k)]
    if missing:
        raise EnvironmentError(
            f"Variáveis de ambiente obrigatórias não definidas: {', '.join(missing)}\n"
            "Copie .env.example para .env e preencha os valores."
        )


class Config:
    GOOGLE_SERVICE_ACCOUNT_FILE: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials/service_account.json")
    SPREADSHEET_ID: str = os.getenv("SPREADSHEET_ID", "")

    META_ACCESS_TOKEN: str = os.getenv("META_ACCESS_TOKEN", "")
    META_API_VERSION: str = os.getenv("META_API_VERSION", "v21.0")
    META_BASE_URL: str = f"https://graph.facebook.com/{os.getenv('META_API_VERSION', 'v21.0')}"

    ZAPI_INSTANCE_ID: str = os.getenv("ZAPI_INSTANCE_ID", "")
    ZAPI_TOKEN: str = os.getenv("ZAPI_TOKEN", "")
    ZAPI_CLIENT_TOKEN: str = os.getenv("ZAPI_CLIENT_TOKEN", "")
    ZAPI_BASE_URL: str = (
        f"https://api.z-api.io/instances/{os.getenv('ZAPI_INSTANCE_ID', '')}"
        f"/token/{os.getenv('ZAPI_TOKEN', '')}"
    )

    FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "dev")
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:5000")
    REPORTS_OUTPUT_DIR: Path = Path(os.getenv("REPORTS_OUTPUT_DIR", "output/reports"))


config = Config()
