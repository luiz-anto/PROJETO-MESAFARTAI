"""
matchmaking.py - Motor de matchmaking logístico do MESAFARTAI.

Para cada doação:
    1. descarta ONGs inativas
    2. descarta ONGs que restringem alguma categoria da doação (líquidos / perecíveis / congelados)
    3. KNN (vizinhos mais próximos) com distância de Haversine sobre as ONGs restantes
    4. oferece NO MÁXIMO 2 opções ao doador: a mais próxima e, se ele recusar, a segunda

Por que Haversine e não distância euclidiana em latitude/longitude?
    A Terra é esférica: 1° de longitude em São Paulo (~23° S) mede ~102 km, e 1° de latitude ~111 km.
    A distância euclidiana trata os dois igual e pode inverter a ordem das ONGs
    (veja tests/test_matchmaking.py::test_haversine_corrige_euclidiana).

O módulo é separado em duas camadas:
    * funções puras (distância, filtro, ranking) -> fáceis de testar e de ensinar
    * `MotorMatchmaking.oferecer_proxima_opcao` -> conversa com o banco (database.py)

Teste rápido:  python src/matchmaking.py
"""
import math

import numpy as np
from sklearn.neighbors import NearestNeighbors

import database as db

RAIO_TERRA_KM = 6371.0088
MAX_OPCOES = 2  # regra do projeto: o doador nunca recebe mais de duas opções


# ----------------------------------------------------------------------------
# Funções puras
# ----------------------------------------------------------------------------
def validar_coordenadas(latitude, longitude):
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        raise ValueError("Coordenadas inválidas: informe latitude e longitude numéricas.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or math.isnan(lat) or math.isnan(lon):
        raise ValueError("Coordenadas fora do intervalo válido.")
    return lat, lon


def distancia_haversine_km(lat1, lon1, lat2, lon2):
    """Distância em km, em linha reta sobre a superfície da Terra (fórmula de Haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_KM * math.asin(math.sqrt(a))


def restricoes_conflitantes(ong, categorias):
    """Categorias da doação que a ONG NÃO aceita. Conjunto vazio = a ONG aceita a doação."""
    return db.restricoes_como_conjunto(ong.get("restricoes_alimentares")) & set(categorias or [])


def ranquear_ongs(latitude, longitude, ongs, max_opcoes=MAX_OPCOES):
    """
    KNN com métrica Haversine. Recebe ONGs já filtradas e devolve as `max_opcoes` mais próximas,
    da mais perto para a mais longe: [(ong, distancia_km), ...]. Empates desempatam pelo id da ONG.
    """
    if not ongs:
        return []
    ongs = sorted(ongs, key=lambda o: o["id"])  # ordem estável => resultado determinístico
    coords = np.radians([[o["latitude"], o["longitude"]] for o in ongs])
    k = min(max_opcoes, len(ongs))  # pedir mais vizinhos do que ONGs causaria erro no sklearn
    knn = NearestNeighbors(n_neighbors=k, metric="haversine", algorithm="ball_tree").fit(coords)
    dist_rad, idx = knn.kneighbors(np.radians([[latitude, longitude]]))
    return [(ongs[i], float(d) * RAIO_TERRA_KM) for d, i in zip(dist_rad[0], idx[0])]


# ----------------------------------------------------------------------------
# Motor
# ----------------------------------------------------------------------------
class MotorMatchmaking:
    def __init__(self, raio_max_km=None):
        """raio_max_km: se informado, ONGs além dessa distância não são oferecidas (padrão: sem limite)."""
        self.raio_max_km = raio_max_km

    # --- cálculo (sem gravar nada) ------------------------------------------------
    def sugerir(self, latitude, longitude, categorias=(), excluir_ong_ids=(), max_opcoes=MAX_OPCOES, ongs=None):
        """
        Calcula as melhores opções para uma doação, sem gravar no banco.

        Retorna:
            opcoes                      -> lista (já ordenada) de {"ong_id", "ong_nome", "distancia_km", "ong"}
            ongs_ativas                 -> quantas ONGs ativas existem
            ongs_compativeis            -> quantas passaram no filtro de restrições
            descartadas_por_restricao   -> [{"ong_id", "ong_nome", "categorias"}] (útil para o admin/dashboard)
            descartadas_por_distancia   -> quantas ficaram fora por causa do raio máximo
        """
        lat, lon = validar_coordenadas(latitude, longitude)
        todas = db.listar_ongs(apenas_ativas=True) if ongs is None else [o for o in ongs if o.get("ativa", 1)]
        todas = [o for o in todas if o["id"] not in set(excluir_ong_ids)]

        compativeis, descartadas = [], []
        for ong in todas:
            conflito = restricoes_conflitantes(ong, categorias)
            if conflito:
                descartadas.append({"ong_id": ong["id"], "ong_nome": ong["nome"],
                                    "categorias": sorted(conflito)})
            else:
                compativeis.append(ong)

        ranking = ranquear_ongs(lat, lon, compativeis, max_opcoes)
        por_distancia = 0
        if self.raio_max_km is not None:
            por_distancia = sum(1 for _, d in ranking if d > self.raio_max_km)
            ranking = [(o, d) for o, d in ranking if d <= self.raio_max_km]

        return {
            "opcoes": [{"ong_id": o["id"], "ong_nome": o["nome"], "distancia_km": round(d, 2), "ong": o}
                       for o, d in ranking],
            "ongs_ativas": len(todas),
            "ongs_compativeis": len(compativeis),
            "descartadas_por_restricao": descartadas,
            "descartadas_por_distancia": por_distancia,
        }

    # --- fluxo completo com o banco ----------------------------------------------------
    def oferecer_proxima_opcao(self, doacao_id):
        """
        Oferece ao doador a próxima opção (1ª ou 2ª ONG) e registra em `matches`.

        É idempotente: o Streamlit reexecuta o script a cada clique, então, se já existe uma
        opção aguardando resposta, ela é devolvida em vez de criar outra.

        Retorna um dicionário com "status":
            OFERECIDA  -> opção registrada (ordem, match_id, ong, distancia_km, ha_segunda_opcao)
            PENDENTE   -> já havia uma opção aguardando resposta (mesmos campos de OFERECIDA)
            SEM_OPCAO  -> não há ONG compatível (motivo: sem_ong_compativel | sem_segunda_opcao);
                          a doação passa a SEM_DESTINO
            ENCERRADA  -> a doação já foi aceita, coletada ou encerrada
        """
        doacao = db.buscar_doacao(doacao_id)
        if not doacao:
            raise ValueError("Doação não encontrada.")
        if doacao["status"] in ("ACEITA", "COLETADA", "SEM_DESTINO"):
            return {"status": "ENCERRADA", "doacao_status": doacao["status"]}
        if doacao["latitude"] is None or doacao["longitude"] is None:
            raise ValueError("A doação não tem coordenadas: geocodifique o CEP/endereço antes do match.")

        matches = doacao["matches"]
        categorias = [c.strip() for c in (doacao["categorias"] or "").split(",") if c.strip()]
        pendente = next((m for m in matches if m["status"] == "SUGERIDO"), None)
        if pendente:
            resultado = self._resultado("PENDENTE", pendente)
            if pendente["ordem"] == 1:  # ainda existe uma 2ª opção disponível?
                resto = self.sugerir(doacao["latitude"], doacao["longitude"], categorias,
                                     excluir_ong_ids=[pendente["ong_id"]], max_opcoes=1)
                resultado["ha_segunda_opcao"] = bool(resto["opcoes"])
            else:
                resultado["ha_segunda_opcao"] = False
            return resultado

        ordem = len(matches) + 1
        if ordem > MAX_OPCOES:
            db.marcar_sem_destino(doacao_id)
            return {"status": "SEM_OPCAO", "ordem": ordem, "motivo": "limite_de_opcoes"}

        calculo = self.sugerir(doacao["latitude"], doacao["longitude"], categorias,
                               excluir_ong_ids=[m["ong_id"] for m in matches], max_opcoes=MAX_OPCOES)
        if not calculo["opcoes"]:
            db.marcar_sem_destino(doacao_id)
            return {"status": "SEM_OPCAO", "ordem": ordem,
                    "motivo": "sem_ong_compativel" if ordem == 1 else "sem_segunda_opcao", "detalhe": calculo}

        escolhida = calculo["opcoes"][0]
        match_id = db.registrar_match(doacao_id, escolhida["ong_id"], ordem, escolhida["distancia_km"])
        ong = escolhida["ong"]
        resultado = self._resultado("OFERECIDA", {
            "id": match_id, "ordem": ordem, "distancia_km": escolhida["distancia_km"],
            "ong_id": ong["id"], "ong_nome": ong["nome"], "telefone": ong["telefone"], "email": ong["email"],
            "cep": ong["cep"], "numero": ong["numero"], "logradouro": ong["logradouro"],
            "bairro": ong["bairro"], "cidade": ong["cidade"], "horario_recebimento": ong["horario_recebimento"]})
        resultado["ha_segunda_opcao"] = ordem == 1 and len(calculo["opcoes"]) > 1
        return resultado

    @staticmethod
    def _resultado(status, m):
        return {
            "status": status, "ordem": m["ordem"], "match_id": m.get("id"), "distancia_km": m["distancia_km"],
            "ong": {k: m.get(k) for k in ("ong_id", "ong_nome", "telefone", "email", "cep", "numero",
                                           "logradouro", "bairro", "cidade", "horario_recebimento")},
        }


# ----------------------------------------------------------------------------
# Teste em linha de comando:  python src/matchmaking.py
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    db.inicializar_banco()
    motor = MotorMatchmaking()
    doador = (-23.615, -46.785)  # ponto de teste
    for categorias in ([], ["perecíveis"], ["líquidos", "congelados"]):
        r = motor.sugerir(*doador, categorias)
        print(f"\nDoação com categorias {categorias or 'nenhuma'}:")
        for i, o in enumerate(r["opcoes"], 1):
            print(f"  opção {i}: {o['ong_nome']} a {o['distancia_km']} km")
        for d in r["descartadas_por_restricao"]:
            print(f"  descartada: {d['ong_nome']} (restrição: {', '.join(d['categorias'])})")