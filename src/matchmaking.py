
"""
MESAFARTAI - Motor de Matchmaking Logístico via KNN
Arquivo: src/matchmaking.py
Descrição: Localiza a ONG geograficamente mais próxima no espaço vetorial 2D.
"""

import sqlite3
import numpy as np
from sklearn.neighbors import NearestNeighbors


class MotorMatchmaking:
    def __init__(self, db_path="mesafartai.db"):
        self.db_path = db_path
        self._garantir_tabela_e_seeds()

    def _garantir_tabela_e_seeds(self):
        """Garante que a tabela 'usuarios' existe e possui dados de teste (ONGs)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Criar a tabela caso não exista
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                tipo TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL
            )
        """)

        # Verificar se existem ONGs cadastradas
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE tipo = 'ONG'")
        total_ongs = cursor.fetchone()[0]

        # Se não houver ONGs, insere dados fictícios para teste
        if total_ongs == 0:
            ongs_seed = [
                ("ONG Prato Quente - Centro", "ONG", -23.612, -46.781),
                ("Abrigo Esperança - Zona Sul", "ONG", -23.630, -46.800),
                ("Instituto Fartura - Zona Oeste", "ONG", -23.590, -46.750)
            ]
            cursor.executemany("""
                INSERT INTO usuarios (nome, tipo, latitude, longitude)
                VALUES (?, ?, ?, ?)
            """, ongs_seed)
            conn.commit()

        conn.close()

    def buscar_ongs(self):
        """Busca todas as ONGs ativas cadastradas no banco de dados SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, latitude, longitude FROM usuarios WHERE tipo = 'ONG'")
        ongs = cursor.fetchall()
        conn.close()
        return ongs

    def encontrar_ong_mais_proxima(self, lat_doador, long_doador):
        """Aplica o algoritmo KNN para encontrar o vizinho mais próximo."""
        ongs = self.buscar_ongs()
        if not ongs:
            return None

        # Monta a matriz de coordenadas das ONGs: [[lat, long], ...]
        coords_ongs = np.array([[ong[2], ong[3]] for ong in ongs])

        # Treina o modelo KNN com distância Euclidiana (1 vizinho)
        knn = NearestNeighbors(n_neighbors=1, metric='euclidean')
        knn.fit(coords_ongs)

        # Coordenada do Doador
        ponto_doador = np.array([[lat_doador, long_doador]])

        # Calcula a menor distância
        distancias, indices = knn.kneighbors(ponto_doador)

        idx_ong_proxima = indices[0][0]
        distancia_calculada = distancias[0][0]
        ong_selecionada = ongs[idx_ong_proxima]

        return {
            "ong_id": ong_selecionada[0],
            "ong_nome": ong_selecionada[1],
            "distancia_estimada": round(float(distancia_calculada * 111), 2)  # Conversão aprox. em KM
        }


if __name__ == "__main__":
    motor = MotorMatchmaking()
    # Coordenada de teste (Ex: Supermercado/Doador)
    lat_teste, long_teste = -23.615, -46.785
    match = motor.encontrar_ong_mais_proxima(lat_teste, long_teste)

    print("--- TESTE DE MATCHMAKING LOGÍSTICO (KNN) ---")
    if match:
        print(f"ONG Encontrada: {match['ong_nome']} (ID: {match['ong_id']})")
        print(f"Distância Estimada: {match['distancia_estimada']} km")
    else:
        print("Nenhuma ONG cadastrada para realizar o match.")
