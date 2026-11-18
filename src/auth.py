"""
auth.py - Autenticação do administrador 

* A senha NUNCA fica em texto: guardamos um hash PBKDF2-HMAC-SHA256 com sal aleatório.
* Usuário e hash ficam em st.secrets (.streamlit/secrets.toml local; "Secrets" no Streamlit Cloud),
  jamais no código nem no GitHub.
* Gere o hash com:  python scripts/gerar_hash_senha.py
* O LimitadorTentativas bloqueia temporariamente após várias senhas erradas (força bruta).
"""
import hashlib
import hmac
import os
import time

PREFIXO = "pbkdf2_sha256"
ITERACOES = 600_000  # recomendação OWASP (2023) para PBKDF2-HMAC-SHA256


def gerar_hash(senha, iteracoes=ITERACOES):
    """Retorna 'pbkdf2_sha256$iteracoes$sal_hex$hash_hex'."""
    if not senha:
        raise ValueError("A senha não pode ser vazia.")
    sal = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, iteracoes)
    return f"{PREFIXO}${iteracoes}${sal.hex()}${dk.hex()}"


def verificar_senha(senha, hash_armazenado):
    """Compara a senha com o hash em tempo constante. Hash malformado => False."""
    try:
        prefixo, iteracoes, sal_hex, hash_hex = str(hash_armazenado).split("$")
        if prefixo != PREFIXO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", (senha or "").encode("utf-8"), bytes.fromhex(sal_hex), int(iteracoes))
        return hmac.compare_digest(dk, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False


def verificar_credenciais(usuario, senha, usuario_cfg, hash_cfg):
    """O hash é sempre calculado, mesmo com usuário errado, para não revelar qual campo falhou."""
    usuario_ok = hmac.compare_digest((usuario or "").strip().encode("utf-8"), str(usuario_cfg).encode("utf-8"))
    senha_ok = verificar_senha(senha, hash_cfg)
    return usuario_ok and senha_ok


class LimitadorTentativas:
    """Bloqueia por `bloqueio_s` segundos após `max_falhas` tentativas erradas seguidas."""

    def __init__(self, max_falhas=5, bloqueio_s=60, relogio=time.monotonic):
        self.max_falhas, self.bloqueio_s, self._relogio = max_falhas, bloqueio_s, relogio
        self.falhas, self._ate = 0, 0.0

    def segundos_bloqueado(self):
        return max(0, int(self._ate - self._relogio() + 0.999))

    def registrar_falha(self):
        self.falhas += 1
        if self.falhas >= self.max_falhas:
            self._ate, self.falhas = self._relogio() + self.bloqueio_s, 0

    def registrar_sucesso(self):
        self.falhas, self._ate = 0, 0.0