"""
Hospedagem temporária de PDFs para envio via Z-API.
Usa Litterbox (catbox.moe) — links expiram em 72h.
"""
import requests


def upload_pdf(pdf_path: str) -> str:
    """
    Faz upload do PDF e retorna uma URL pública de download direto.
    Expira em 72 horas.
    """
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data={"reqtype": "fileupload", "time": "72h"},
            files={"fileToUpload": (pdf_path.split("/")[-1], f, "application/pdf")},
            timeout=60,
        )

    resp.raise_for_status()
    url = resp.text.strip()

    if not url.startswith("https://"):
        raise RuntimeError(f"Upload falhou: {url}")

    return url
