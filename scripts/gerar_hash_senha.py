"""Gera o hash da senha do administrador para colar em .streamlit/secrets.toml.
Uso:  python scripts/gerar_hash_senha.py
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from auth import gerar_hash  # noqa: E402

if __name__ == "__main__":
    senha = getpass.getpass("Nova senha do administrador (mín. 10 caracteres): ")
    if len(senha) < 10:
        sys.exit("Senha muito curta: use pelo menos 10 caracteres.")
    if senha != getpass.getpass("Repita a senha: "):
        sys.exit("As senhas não conferem.")
    print("\nCopie o bloco abaixo para .streamlit/secrets.toml (e para os Secrets do Streamlit Cloud):\n")
    print("[admin]")
    print('usuario = "admin"')
    print(f'senha_hash = "{gerar_hash(senha)}"')