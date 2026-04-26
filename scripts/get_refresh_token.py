#!/usr/bin/env python3
"""
Gera o GOOGLE_ADS_REFRESH_TOKEN para uso no Easypanel.

Uso (na sua máquina local):
    cd /home/coder/projetos/relatorios-clientes
    .venv/bin/python3 scripts/get_refresh_token.py

O script vai:
1. Pedir o OAuth Client ID e Client Secret (cole quando perguntar)
2. Abrir o navegador para você logar com a conta Google que tem acesso à MCC
3. Imprimir o refresh token no terminal

Cole o valor impresso no Easypanel como GOOGLE_ADS_REFRESH_TOKEN.

IMPORTANTE: A conta Google que você usar para autorizar precisa ter acesso
à MCC (Conta Gerente) configurada em GOOGLE_ADS_LOGIN_CUSTOMER_ID.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main():
    print("=" * 60)
    print("Gerador de Refresh Token — Google Ads API")
    print("=" * 60)
    print()

    client_id = input("OAuth Client ID: ").strip()
    client_secret = input("OAuth Client Secret: ").strip()

    if not client_id or not client_secret:
        print("\n[ERRO] Client ID e Client Secret são obrigatórios.")
        return

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    print("\nAbrindo navegador para autorização...")
    print("(Faça login com a conta Google que tem acesso à sua MCC)\n")

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    # prompt='consent' força o Google a retornar refresh_token mesmo se já houve consent antes
    creds = flow.run_local_server(
        port=0,
        prompt="consent",
        access_type="offline",
        authorization_prompt_message="",
    )

    print("\n" + "=" * 60)
    print("SUCESSO! Copie o valor abaixo:")
    print("=" * 60)
    print(f"\nGOOGLE_ADS_REFRESH_TOKEN={creds.refresh_token}\n")
    print("=" * 60)
    print("Cole no Easypanel como GOOGLE_ADS_REFRESH_TOKEN e implante.")
    print("=" * 60)


if __name__ == "__main__":
    main()
