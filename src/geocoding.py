"""
geocoding.py - Transforma CEP / endereço em latitude e longitude (APIs gratuitas, com cache).

Ordem de tentativas para um CEP:
    1. cache no SQLite (tabela cache_geocodificacao)       -> não gasta nenhuma API
    2. BrasilAPI v2   (CEP -> endereço + coordenadas, quando conhecidas)
    3. ViaCEP         (CEP -> endereço, sem coordenadas)
    4. Nominatim/OpenStreetMap (endereço -> coordenadas)
    5. tabela de demonstração (só os CEPs das ONGs fictícias), se estiver sem internet

Regras de uso do Nominatim público (https://operations.osmfoundation.org/policies/nominatim/):
    * no máximo 1 requisição por segundo            -> implementado (INTERVALO_NOMINATIM_S)
    * User-Agent que identifique o aplicativo        -> defina MESAFARTAI_USER_AGENT com um contato
    * guardar resultados em cache                    -> implementado (SQLite)
    * exibir atribuição "© OpenStreetMap contributors" onde os dados forem mostrados (mapa/dashboard)

Cada resultado traz "precisao":
    numero         -> endereço exato (rua + número) encontrado
    cep            -> coordenada do CEP (rua/bairro); boa para matchmaking
    aproximada     -> só cidade/bairro ou busca textual; mostre ao usuário para confirmar
    demonstracao   -> dado fictício de teste (nunca vai para o cache)

Uso:
    geo = Geocodificador()
    geo.geocodificar_cep("06700-000")
    geo.geocodificar_cep("06700-000", numero="120")          # cadastro de ONG (mais preciso)
    geo.geocodificar_endereco("Rua das Flores, 120, Taboão da Serra - SP")
"""
import logging
import os
import re
import threading
import time

import database as db
from matchmaking import distancia_haversine_km

log = logging.getLogger("mesafartai.geocoding")

USER_AGENT = os.environ.get("MESAFARTAI_USER_AGENT",
                            "MESAFARTAI/1.0 (projeto educacional; defina MESAFARTAI_USER_AGENT com um contato)")
URL_BRASILAPI = "https://brasilapi.com.br/api/cep/v2/{cep}"
URL_VIACEP = "https://viacep.com.br/ws/{cep}/json/"
URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"
INTERVALO_NOMINATIM_S = 1.1
TIMEOUT_S = 6
RAIO_VALIDACAO_KM = 5.0  # um resultado "por número" mais longe que isso do CEP é descartado
_BRASIL = (-34.0, 6.0, -74.5, -32.0)  # lat_min, lat_max, lon_min, lon_max
_RE_CEP = re.compile(r"(?<!\d)(\d{5})-?(\d{3})(?!\d)")


def _http_get_json(url, params=None, headers=None):
    """Chamada HTTP padrão (requests). Em testes, injete outra função no Geocodificador."""
    import requests
    resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()


def _para_float(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _no_brasil(lat, lon):
    return lat is not None and lon is not None and _BRASIL[0] <= lat <= _BRASIL[1] and _BRASIL[2] <= lon <= _BRASIL[3]


class Geocodificador:
    def __init__(self, http_get=None, dormir=time.sleep):
        self._http_get = http_get or _http_get_json
        self._dormir = dormir
        self._lock = threading.Lock()
        self._ultimo_nominatim = float("-inf")
        # CEPs fictícios das ONGs de demonstração (funciona sem internet)
        self._demo = {o["cep"]: (o["latitude"], o["longitude"]) for o in db.SEEDS_ONGS}

    # --- provedores ------------------------------------------------------------------
    def _brasilapi(self, cep):
        try:
            d = self._http_get(URL_BRASILAPI.format(cep=cep.replace("-", "")), headers={"User-Agent": USER_AGENT})
        except Exception as e:
            log.info("BrasilAPI indisponível para %s: %s", cep, e)
            return None
        coords = ((d.get("location") or {}).get("coordinates")) or {}
        lat, lon = _para_float(coords.get("latitude")), _para_float(coords.get("longitude"))
        return {"logradouro": d.get("street"), "bairro": d.get("neighborhood"), "cidade": d.get("city"),
                "uf": d.get("state"), "latitude": lat if _no_brasil(lat, lon) else None,
                "longitude": lon if _no_brasil(lat, lon) else None}

    def _viacep(self, cep):
        try:
            d = self._http_get(URL_VIACEP.format(cep=cep.replace("-", "")), headers={"User-Agent": USER_AGENT})
        except Exception as e:
            log.info("ViaCEP indisponível para %s: %s", cep, e)
            return None
        if not isinstance(d, dict) or d.get("erro"):
            return None
        return {"logradouro": d.get("logradouro"), "bairro": d.get("bairro"), "cidade": d.get("localidade"),
                "uf": d.get("uf"), "latitude": None, "longitude": None}

    def _nominatim(self, **params):
        """Consulta o Nominatim respeitando 1 requisição/segundo. Retorna (lat, lon, nome) ou None."""
        with self._lock:
            espera = INTERVALO_NOMINATIM_S - (time.monotonic() - self._ultimo_nominatim)
            if espera > 0:
                self._dormir(espera)
            self._ultimo_nominatim = time.monotonic()
        params.update({"format": "jsonv2", "limit": 1, "countrycodes": "br"})
        try:
            resultados = self._http_get(URL_NOMINATIM, params=params, headers={"User-Agent": USER_AGENT})
        except Exception as e:
            log.info("Nominatim indisponível: %s", e)
            return None
        if not resultados:
            return None
        r = resultados[0]
        lat, lon = _para_float(r.get("lat")), _para_float(r.get("lon"))
        return (lat, lon, r.get("display_name")) if _no_brasil(lat, lon) else None

    # --- cache -------------------------------------------------------------------------
    @staticmethod
    def _do_cache(consulta):
        c = db.obter_cache_geo(consulta)
        if not c:
            return None
        d = c["detalhes"]
        return {"latitude": c["latitude"], "longitude": c["longitude"], "logradouro": d.get("logradouro"),
                "bairro": d.get("bairro"), "cidade": d.get("cidade"), "uf": d.get("uf"),
                "endereco_formatado": c["endereco_formatado"], "fonte": c["fonte"],
                "precisao": d.get("precisao", "cep"), "do_cache": True}

    @staticmethod
    def _gravar(consulta, r):
        if r["fonte"] != "demonstracao":
            db.salvar_cache_geo(consulta, r["latitude"], r["longitude"], r["endereco_formatado"], r["fonte"],
                                {k: r.get(k) for k in ("logradouro", "bairro", "cidade", "uf", "precisao")})
        return r

    @staticmethod
    def _formatar(p):
        partes = [p.get("logradouro"), p.get("bairro"), p.get("cidade"), p.get("uf")]
        return ", ".join(x for x in partes if x) or None

    # --- API pública ---------------------------------------------------------------------
    def geocodificar_cep(self, cep, numero=None):
        """
        CEP (e opcionalmente o número) -> {"latitude", "longitude", "logradouro", "bairro", "cidade", "uf",
        "endereco_formatado", "fonte", "precisao"}. Retorna None se nenhuma fonte encontrou o CEP.
        Levanta ValueError se o CEP não tiver 8 dígitos.
        """
        cep = db.normalizar_cep(cep)
        numero = (str(numero).strip() if numero else "") or None
        consulta = f"{cep}|{numero}" if numero else cep
        em_cache = self._do_cache(consulta)
        if em_cache:
            return em_cache

        info = self._brasilapi(cep)
        fonte = "brasilapi"
        if info is None or not (info["logradouro"] or info["cidade"]):
            via = self._viacep(cep)
            if via:
                info, fonte = via, "viacep"
        if info is None:
            return self._demonstracao(cep)

        lat, lon = info["latitude"], info["longitude"]
        precisao = "cep" if lat is not None else None

        if numero and info["logradouro"] and info["cidade"]:  # tenta o endereço exato
            achado = self._nominatim(street=f"{numero} {info['logradouro']}", city=info["cidade"],
                                     state=info["uf"] or "", country="Brazil")
            if achado and (lat is None or distancia_haversine_km(lat, lon, achado[0], achado[1]) <= RAIO_VALIDACAO_KM):
                lat, lon, fonte, precisao = achado[0], achado[1], f"{fonte}+nominatim", "numero"

        if lat is None:  # sem coordenadas do CEP: busca pelo endereço (sem número)
            consulta_txt = ", ".join(x for x in (info["logradouro"], info["bairro"], info["cidade"], info["uf"]) if x)
            achado = self._nominatim(q=f"{consulta_txt}, Brasil") if consulta_txt else None
            if achado:
                lat, lon, fonte, precisao = achado[0], achado[1], f"{fonte}+nominatim", \
                    "cep" if info["logradouro"] else "aproximada"

        if lat is None:
            return self._demonstracao(cep)

        resultado = {"latitude": lat, "longitude": lon, "logradouro": info["logradouro"], "bairro": info["bairro"],
                     "cidade": info["cidade"], "uf": info["uf"], "endereco_formatado": self._formatar(info),
                     "fonte": fonte, "precisao": precisao, "do_cache": False}
        return self._gravar(consulta, resultado)

    def geocodificar_endereco(self, texto, contexto=None):
        """
        Endereço digitado livremente ("Rua das Flores, 120, Taboão da Serra") -> coordenadas aproximadas.
        contexto: cidade/UF padrão acrescentada à busca, se o texto não a mencionar (ex.: "Taboão da Serra, SP").
        """
        texto = re.sub(r"\s+", " ", (texto or "")).strip()
        if len(texto) < 5:
            return None
        consulta = f"{texto}, {contexto}" if contexto else texto
        em_cache = self._do_cache(consulta)
        if em_cache:
            return em_cache
        achado = self._nominatim(q=consulta)
        if not achado:
            return None
        resultado = {"latitude": achado[0], "longitude": achado[1], "logradouro": None, "bairro": None,
                     "cidade": None, "uf": None, "endereco_formatado": achado[2], "fonte": "nominatim",
                     "precisao": "aproximada", "do_cache": False}
        return self._gravar(consulta, resultado)

    def geocodificar(self, consulta):
        """Atalho para o chatbot: usa o CEP se houver um no texto; senão, trata como endereço."""
        m = _RE_CEP.search(consulta or "")
        if m:
            return self.geocodificar_cep(f"{m.group(1)}-{m.group(2)}")
        return self.geocodificar_endereco(consulta)

    def _demonstracao(self, cep):
        coords = self._demo.get(cep)
        if not coords:
            return None
        return {"latitude": coords[0], "longitude": coords[1], "logradouro": None, "bairro": None,
                "cidade": None, "uf": None, "endereco_formatado": f"CEP {cep} (dados de demonstração)",
                "fonte": "demonstracao", "precisao": "demonstracao", "do_cache": False}


# ----------------------------------------------------------------------------
# Teste em linha de comando (precisa de internet):  python src/geocoding.py 06700-000
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    db.inicializar_banco()
    alvo = sys.argv[1] if len(sys.argv) > 1 else "01001-000"
    print(Geocodificador().geocodificar(alvo))