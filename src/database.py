import sqlite3 

def inicializar_banco(): 

    conn = sqlite3.connect('mesafartai.db') 

    cursor = conn.cursor() 

    # 1. Tabela de Usuários (Doadores e ONGs) 

    cursor.execute(''' 

        CREATE TABLE IF NOT EXISTS usuarios ( 

            id INTEGER PRIMARY KEY AUTOINCREMENT, 

            nome TEXT NOT NULL, 

            tipo TEXT CHECK(tipo IN ('DOADOR', 'ONG')) NOT NULL, 

            cep TEXT NOT NULL, 

            latitude REAL, 

            longitude REAL, 

            telefone TEXT 

        ) 

    ''') 

 

    # 2. Tabela de Doações de Alimentos 

    cursor.execute(''' 

        CREATE TABLE IF NOT EXISTS doacoes ( 

            id INTEGER PRIMARY KEY AUTOINCREMENT, 

            doador_id INTEGER, 

            descricao_alimento TEXT NOT NULL, 

            quantidade_kg REAL, 

            data_validade TEXT, 

            status TEXT DEFAULT 'DISPONIVEL', 

            FOREIGN KEY (doador_id) REFERENCES usuarios (id) 

        ) 

    ''') 

 

    # 3. Tabela de Matches Logísticos 

    cursor.execute(''' 

        CREATE TABLE IF NOT EXISTS matches ( 

            id INTEGER PRIMARY KEY AUTOINCREMENT, 

            doacao_id INTEGER, 

            ong_id INTEGER, 

            distancia_km REAL, 

            data_match TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 

            FOREIGN KEY (doacao_id) REFERENCES doacoes (id), 

            FOREIGN KEY (ong_id) REFERENCES usuarios (id) 

        ) 

    ''') 

    # Inserção de Carga Inicial (Seeds de Teste) 

    cursor.execute("SELECT COUNT(*) FROM usuarios") 

    if cursor.fetchone()[0] == 0: 

        # Cadastra ONGs de teste 

        cursor.execute("INSERT INTO usuarios (nome, tipo, cep, latitude, longitude, telefone) VALUES ('ONG Prato Quente', 'ONG', '06700-000', -23.612, -46.781, '11999990001')") 

        cursor.execute("INSERT INTO usuarios (nome, tipo, cep, latitude, longitude, telefone) VALUES ('Abrigo Esperanca', 'ONG', '06705-000', -23.625, -46.795, '11999990002')") 

         

        # Cadastra Doadores de teste 

        cursor.execute("INSERT INTO usuarios (nome, tipo, cep, latitude, longitude, telefone) VALUES ('Supermercado Silva', 'DOADOR', '06701-000', -23.615, -46.785, '11999990003')") 

        cursor.execute("INSERT INTO usuarios (nome, tipo, cep, latitude, longitude, telefone) VALUES ('Restaurante Sabor', 'DOADOR', '06703-000', -23.618, -46.789, '11999990004')") 

        print(" Dados iniciais de teste inseridos com sucesso!") 

    conn.commit() 

    conn.close() 

    print(" Banco de dados 'mesafartai.db' inicializado com sucesso!") 

if __name__ == "__main__": 

    inicializar_banco()
