"""
database.py - Camada de dados do MESAFARTAI (SQLite).

Modelo de dados:
    ongs                  -> cadastradas SOMENTE pelo administrador
    doacoes               -> registradas pelo chatbot (doador anônimo, identificado por protocolo)
    itens_doacao          -> os alimentos de cada doação (alimento, quantidade, unidade, categorias)
    matches               -> até 2 ONGs sugeridas por doação (ordem 1 e 2)
    cache_geocodificacao  -> evita consultar as APIs de CEP/mapa repetidamente

Ciclo de vida da doação (doacoes.status):
    DISPONIVEL -> MATCH_SUGERIDO -> ACEITA
                                 -> SEM_DESTINO (doador recusou as duas opções ou não há ONG compatível)
    COLETADA (opcional, marcada manualmente pelo administrador)

Cada opção sugerida (matches.status): SUGERIDO -> ACEITO | RECUSADO

IMPORTANTE: o login do administrador NÃO fica aqui. Usuário e hash da senha ficam em
st.secrets (ou variáveis de ambiente), nunca no banco nem no GitHub.

Para trocar de banco na nuvem (Turso/Supabase), só a função `conectar()` precisa mudar.
"""
import json
import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------------
# Constantes de negócio
# ----------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("MESAFARTAI_DB", RAIZ / "data" / "mesafartai.db"))

TIPOS_ONG = ("Cozinha comunitária", "Abrigo", "Banco de alimentos", "Associação de moradores", "Outro")
# "Sólidos" não é uma categoria: quase todo alimento é sólido, então restringi-la bloquearia tudo.
CATEGORIAS_ALIMENTO = ("líquidos", "perecíveis", "congelados")
# Rótulos para a tela do administrador (a ONG marca o que NÃO aceita)
ROTULOS_RESTRICAO = {
    "líquidos": "Não aceitamos líquidos",
    "perecíveis": "Não aceitamos perecíveis",
    "congelados": "Não aceitamos congelados",
}
SEM_RESTRICOES = "sem restrições"
STATUS_DOACAO = ("DISPONIVEL", "MATCH_SUGERIDO", "ACEITA", "SEM_DESTINO", "COLETADA")
STATUS_MATCH = ("SUGERIDO", "ACEITO", "RECUSADO")

_RE_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


def _sql_in(valores):
    return ", ".join(f"'{v}'" for v in valores)


# ----------------------------------------------------------------------------
# Conexão
# ----------------------------------------------------------------------------
def conectar():
    """Abre a conexão com chaves estrangeiras ativas e linhas acessíveis por nome."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # no SQLite é preciso ligar a cada conexão
    return conn


@contextmanager
def sessao():
    """with sessao() as conn: ... -> faz commit no sucesso, rollback no erro e sempre fecha."""
    conn = conectar()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# Utilitários de normalização / validação
# ----------------------------------------------------------------------------
def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower().strip()


def normalizar_cep(cep):
    digitos = re.sub(r"\D", "", str(cep or ""))
    if len(digitos) != 8:
        raise ValueError("CEP inválido: informe 8 dígitos.")
    return f"{digitos[:5]}-{digitos[5:]}"


def normalizar_restricoes(valor):
    """
    Regra do projeto: campo vazio vira 'sem restrições'.
    Aceita None, texto ('perecíveis, congelados') ou lista. Devolve texto canônico em ordem fixa.
    """
    if valor is None:
        return SEM_RESTRICOES
    itens = re.split(r"[,;]", valor) if isinstance(valor, str) else list(valor)
    mapa = {_sem_acento(c): c for c in CATEGORIAS_ALIMENTO}
    escolhidas = set()
    for item in itens:
        chave = _sem_acento(str(item))
        if not chave or chave == _sem_acento(SEM_RESTRICOES):
            continue
        if chave not in mapa:
            raise ValueError(f"Restrição desconhecida: '{item}'. Use: {', '.join(CATEGORIAS_ALIMENTO)}.")
        escolhidas.add(mapa[chave])
    if not escolhidas:
        return SEM_RESTRICOES
    return ", ".join(c for c in CATEGORIAS_ALIMENTO if c in escolhidas)


def restricoes_como_conjunto(texto):
    """'perecíveis, congelados' -> {'perecíveis', 'congelados'} | 'sem restrições' -> set()"""
    if not texto or _sem_acento(texto) == _sem_acento(SEM_RESTRICOES):
        return set()
    return {c.strip() for c in texto.split(",") if c.strip()}


# ----------------------------------------------------------------------------
# Criação do banco
# ----------------------------------------------------------------------------
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS ongs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ({_sql_in(TIPOS_ONG)})),
    cep TEXT NOT NULL,
    numero TEXT,
    logradouro TEXT,
    bairro TEXT,
    cidade TEXT,
    uf TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    telefone TEXT,
    email TEXT,
    restricoes_alimentares TEXT NOT NULL DEFAULT '{SEM_RESTRICOES}',
    horario_recebimento TEXT,
    capacidade_kg REAL,
    observacoes TEXT,
    ativa INTEGER NOT NULL DEFAULT 1 CHECK (ativa IN (0, 1)),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (telefone IS NOT NULL OR email IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS doacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocolo TEXT UNIQUE,
    doador_nome TEXT NOT NULL,
    doador_email TEXT NOT NULL,
    descricao_alimento TEXT NOT NULL,
    categorias TEXT,
    data_validade TEXT,
    cep TEXT,
    endereco_texto TEXT,
    latitude REAL,
    longitude REAL,
    mensagem_original TEXT,
    consentimento_lgpd INTEGER NOT NULL CHECK (consentimento_lgpd = 1),
    status TEXT NOT NULL DEFAULT 'DISPONIVEL' CHECK (status IN ({_sql_in(STATUS_DOACAO)})),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS itens_doacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doacao_id INTEGER NOT NULL,
    alimento TEXT NOT NULL,
    quantidade REAL,
    unidade TEXT,
    categorias TEXT,
    FOREIGN KEY (doacao_id) REFERENCES doacoes (id)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doacao_id INTEGER NOT NULL,
    ong_id INTEGER NOT NULL,
    ordem INTEGER NOT NULL CHECK (ordem IN (1, 2)),
    distancia_km REAL,
    status TEXT NOT NULL DEFAULT 'SUGERIDO' CHECK (status IN ({_sql_in(STATUS_MATCH)})),
    data_match TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data_resposta TEXT,
    UNIQUE (doacao_id, ordem),
    FOREIGN KEY (doacao_id) REFERENCES doacoes (id),
    FOREIGN KEY (ong_id) REFERENCES ongs (id)
);

CREATE TABLE IF NOT EXISTS cache_geocodificacao (
    chave TEXT PRIMARY KEY,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    endereco_formatado TEXT,
    fonte TEXT,
    detalhes TEXT,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_doacoes_status ON doacoes (status);
CREATE INDEX IF NOT EXISTS idx_matches_doacao ON matches (doacao_id);
CREATE INDEX IF NOT EXISTS idx_itens_doacao ON itens_doacao (doacao_id);
"""

# ONGs FICTÍCIAS apenas para demonstração em sala (inseridas só se a tabela estiver vazia).
SEEDS_ONGS = [
    dict(nome="ONG Prato Quente", tipo="Cozinha comunitária", cep="06700-000", latitude=-23.612,
         longitude=-46.781, telefone="11999990001", email="contato@pratoquente.example", restricoes=None),
    dict(nome="Abrigo Esperança", tipo="Abrigo", cep="06705-000", latitude=-23.625, longitude=-46.795,
         telefone="11999990002", email="contato@esperanca.example", restricoes=["perecíveis", "congelados"]),
    dict(nome="Banco de Alimentos Solidário", tipo="Banco de alimentos", cep="06710-100", latitude=-23.640,
         longitude=-46.770, telefone="11999990004", email="contato@bancosolidario.example", restricoes=["líquidos"]),
    dict(nome="Associação Vizinhança Solidária", tipo="Associação de moradores", cep="06715-200",
         latitude=-23.598, longitude=-46.800, telefone="11999990005", email=None, restricoes=["congelados"]),
]


def _backup_banco_legado():
    """Se existir um banco da versão antiga (tabela 'usuarios'), guarda uma cópia e recomeça limpo."""
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    legado = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone()
    conn.close()
    if legado:
        destino = DB_PATH.with_name(f"{DB_PATH.stem}_legado_{datetime.now():%Y%m%d%H%M%S}.db")
        DB_PATH.rename(destino)
        print(f" Banco da versão antiga preservado em '{destino.name}'. Criando o novo esquema.")


def inicializar_banco(inserir_seeds=True):
    """Cria as tabelas (se não existirem) e, opcionalmente, as ONGs de demonstração."""
    _backup_banco_legado()
    with sessao() as conn:
        conn.executescript(SCHEMA)
        colunas = {c["name"] for c in conn.execute("PRAGMA table_info(cache_geocodificacao)")}
        if "detalhes" not in colunas:  # bancos criados antes desta coluna
            conn.execute("ALTER TABLE cache_geocodificacao ADD COLUMN detalhes TEXT")
        total = conn.execute("SELECT COUNT(*) FROM ongs").fetchone()[0]
    if inserir_seeds and total == 0:
        for ong in SEEDS_ONGS:
            cadastrar_ong(**ong)
        print(f" {len(SEEDS_ONGS)} ONGs de demonstração (fictícias) inseridas.")
    print(f" Banco pronto em: {DB_PATH}")


# ----------------------------------------------------------------------------
# ONGs (uso exclusivo do administrador)
# ----------------------------------------------------------------------------
_CAMPOS_EDITAVEIS_ONG = {
    "nome", "tipo", "cep", "numero", "logradouro", "bairro", "cidade", "uf", "latitude", "longitude",
    "telefone", "email", "restricoes_alimentares", "horario_recebimento", "capacidade_kg", "observacoes",
}


def cadastrar_ong(nome, tipo, cep, latitude, longitude, telefone=None, email=None, restricoes=None,
                  numero=None, logradouro=None, bairro=None, cidade=None, uf=None,
                  horario_recebimento=None, capacidade_kg=None, observacoes=None):
    """Cadastra uma ONG ativa. Restrições vazias viram 'sem restrições'. Retorna o id."""
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome da ONG.")
    if tipo not in TIPOS_ONG:
        raise ValueError(f"Tipo inválido. Use um destes: {', '.join(TIPOS_ONG)}.")
    if latitude is None or longitude is None:
        raise ValueError("Coordenadas obrigatórias: geocodifique o endereço antes de salvar.")
    telefone = (telefone or "").strip() or None
    email = (email or "").strip() or None
    if not telefone and not email:
        raise ValueError("Informe ao menos um contato (telefone ou e-mail).")
    if email and not _RE_EMAIL.match(email):
        raise ValueError("E-mail da ONG inválido.")

    with sessao() as conn:
        cur = conn.execute(
            """INSERT INTO ongs (nome, tipo, cep, numero, logradouro, bairro, cidade, uf, latitude, longitude,
                                 telefone, email, restricoes_alimentares, horario_recebimento,
                                 capacidade_kg, observacoes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (nome, tipo, normalizar_cep(cep), numero, logradouro, bairro, cidade, uf, float(latitude),
             float(longitude), telefone, email, normalizar_restricoes(restricoes), horario_recebimento,
             capacidade_kg, observacoes))
        return cur.lastrowid


def editar_ong(ong_id, **campos):
    """Edita campos da ONG (lista branca). Use alterar_status_ong para ativar/desativar."""
    invalidos = set(campos) - _CAMPOS_EDITAVEIS_ONG
    if invalidos:
        raise ValueError(f"Campos não editáveis: {', '.join(sorted(invalidos))}")
    if "nome" in campos and not str(campos["nome"] or "").strip():
        raise ValueError("Informe o nome da ONG.")
    if "tipo" in campos and campos["tipo"] not in TIPOS_ONG:
        raise ValueError(f"Tipo inválido. Use um destes: {', '.join(TIPOS_ONG)}.")
    if campos.get("email") and not _RE_EMAIL.match(campos["email"]):
        raise ValueError("E-mail da ONG inválido.")
    if "cep" in campos:
        campos["cep"] = normalizar_cep(campos["cep"])
    if "restricoes_alimentares" in campos:
        campos["restricoes_alimentares"] = normalizar_restricoes(campos["restricoes_alimentares"])
    if not campos:
        return
    colunas = ", ".join(f"{c} = ?" for c in campos)
    try:
        with sessao() as conn:
            cur = conn.execute(f"UPDATE ongs SET {colunas} WHERE id = ?", (*campos.values(), ong_id))
            if cur.rowcount == 0:
                raise ValueError("ONG não encontrada.")
    except sqlite3.IntegrityError:
        raise ValueError("Dados inválidos: a ONG precisa de ao menos um contato (telefone ou e-mail).")


def alterar_status_ong(ong_id, ativa):
    """Desativar não apaga: preserva o histórico de matches."""
    with sessao() as conn:
        conn.execute("UPDATE ongs SET ativa = ? WHERE id = ?", (1 if ativa else 0, ong_id))


def buscar_ong(ong_id):
    with sessao() as conn:
        linha = conn.execute("SELECT * FROM ongs WHERE id = ?", (ong_id,)).fetchone()
    return dict(linha) if linha else None


def listar_ongs(apenas_ativas=True):
    sql = "SELECT * FROM ongs" + (" WHERE ativa = 1" if apenas_ativas else "") + " ORDER BY nome"
    with sessao() as conn:
        return [dict(l) for l in conn.execute(sql).fetchall()]


# ----------------------------------------------------------------------------
# Doações e matches (uso do chatbot)
# ----------------------------------------------------------------------------
def _descrever_itens(itens):
    partes = []
    for it in itens:
        if it.get("quantidade") is None:
            partes.append(it["alimento"])
        else:
            un = "un." if it.get("unidade") in (None, "unidade") else it["unidade"]
            partes.append(f"{it['quantidade']} {un} de {it['alimento']}")
    return "; ".join(partes)


def registrar_doacao(doador_nome, doador_email, consentimento_lgpd, itens, categorias=None, descricao_alimento=None,
                     data_validade=None, cep=None, endereco_texto=None, latitude=None, longitude=None,
                     mensagem_original=None):
    """
    Registra a doação e devolve (id, protocolo). Exige o consentimento do doador (LGPD).
    itens: lista de dicts {"alimento", "quantidade", "unidade", "categorias"} (formato do entities.py).
    """
    if not consentimento_lgpd:
        raise ValueError("É necessário o consentimento do doador para guardar nome e e-mail.")
    doador_nome = (doador_nome or "").strip()
    doador_email = (doador_email or "").strip()
    if not doador_nome:
        raise ValueError("Informe o nome do doador.")
    if not _RE_EMAIL.match(doador_email):
        raise ValueError("E-mail inválido.")
    if not itens:
        raise ValueError("Informe o que será doado.")

    if categorias is None:  # junta as categorias de todos os itens
        categorias = {c for it in itens for c in (it.get("categorias") or [])}
    categorias_txt = ", ".join(c for c in CATEGORIAS_ALIMENTO if c in set(categorias)) or None
    descricao = (descricao_alimento or _descrever_itens(itens)).strip()
    cep_norm = normalizar_cep(cep) if cep else None

    with sessao() as conn:
        cur = conn.execute(
            """INSERT INTO doacoes (doador_nome, doador_email, descricao_alimento, categorias, data_validade,
                                    cep, endereco_texto, latitude, longitude, mensagem_original,
                                    consentimento_lgpd)
               VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
            (doador_nome, doador_email, descricao, categorias_txt, data_validade, cep_norm, endereco_texto,
             latitude, longitude, mensagem_original))
        doacao_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO itens_doacao (doacao_id, alimento, quantidade, unidade, categorias) VALUES (?,?,?,?,?)",
            [(doacao_id, it["alimento"], it.get("quantidade"), it.get("unidade"),
              ", ".join(it.get("categorias") or []) or None) for it in itens])
        protocolo = f"MF-{datetime.now():%Y%m%d}-{doacao_id:04d}"
        conn.execute("UPDATE doacoes SET protocolo = ? WHERE id = ?", (protocolo, doacao_id))
    return doacao_id, protocolo


def registrar_match(doacao_id, ong_id, ordem, distancia_km):
    """Registra a opção 1 ou 2 oferecida ao doador e marca a doação como MATCH_SUGERIDO."""
    with sessao() as conn:
        cur = conn.execute(
            "INSERT INTO matches (doacao_id, ong_id, ordem, distancia_km) VALUES (?,?,?,?)",
            (doacao_id, ong_id, ordem, round(float(distancia_km), 2)))
        conn.execute("UPDATE doacoes SET status = 'MATCH_SUGERIDO' WHERE id = ?", (doacao_id,))
        return cur.lastrowid


def responder_match(match_id, aceito):
    """
    Registra a resposta do doador.
      aceito=True              -> match ACEITO e doação ACEITA
      aceito=False (opção 1)   -> match RECUSADO; doação segue MATCH_SUGERIDO (aguarda a opção 2)
      aceito=False (opção 2)   -> match RECUSADO; doação SEM_DESTINO
    Se a opção 1 for recusada e não existir opção 2, chame marcar_sem_destino().
    """
    with sessao() as conn:
        m = conn.execute("SELECT doacao_id, ordem FROM matches WHERE id = ?", (match_id,)).fetchone()
        if not m:
            raise ValueError("Match não encontrado.")
        conn.execute("UPDATE matches SET status = ?, data_resposta = CURRENT_TIMESTAMP WHERE id = ?",
                     ("ACEITO" if aceito else "RECUSADO", match_id))
        if aceito:
            conn.execute("UPDATE doacoes SET status = 'ACEITA' WHERE id = ?", (m["doacao_id"],))
        elif m["ordem"] == 2:
            conn.execute("UPDATE doacoes SET status = 'SEM_DESTINO' WHERE id = ?", (m["doacao_id"],))


def marcar_sem_destino(doacao_id):
    with sessao() as conn:
        conn.execute("UPDATE doacoes SET status = 'SEM_DESTINO' WHERE id = ?", (doacao_id,))


def marcar_coletada(doacao_id):
    """Opcional: o administrador registra que a coleta aconteceu."""
    with sessao() as conn:
        conn.execute("UPDATE doacoes SET status = 'COLETADA' WHERE id = ? AND status = 'ACEITA'", (doacao_id,))


def _doacao_completa(conn, d):
    matches = conn.execute(
        """SELECT m.id, m.ong_id, m.ordem, m.status, m.distancia_km, o.nome AS ong_nome, o.telefone, o.email,
                  o.cep, o.numero, o.logradouro, o.bairro, o.cidade, o.horario_recebimento
           FROM matches m JOIN ongs o ON o.id = m.ong_id
           WHERE m.doacao_id = ? ORDER BY m.ordem""", (d["id"],)).fetchall()
    itens = conn.execute("SELECT alimento, quantidade, unidade, categorias FROM itens_doacao "
                         "WHERE doacao_id = ? ORDER BY id", (d["id"],)).fetchall()
    resultado = dict(d)
    resultado["itens"] = [dict(i) for i in itens]
    resultado["matches"] = [dict(m) for m in matches]
    return resultado


def buscar_doacao_por_protocolo(protocolo):
    """Consulta pública (chatbot): devolve a doação + itens + opções oferecidas, ou None."""
    protocolo = re.sub(r"\s+", "", str(protocolo or "")).upper()
    with sessao() as conn:
        d = conn.execute("SELECT * FROM doacoes WHERE protocolo = ?", (protocolo,)).fetchone()
        return _doacao_completa(conn, d) if d else None


def buscar_doacao(doacao_id):
    """Igual a buscar_doacao_por_protocolo, mas pelo id interno (uso do sistema)."""
    with sessao() as conn:
        d = conn.execute("SELECT * FROM doacoes WHERE id = ?", (doacao_id,)).fetchone()
        return _doacao_completa(conn, d) if d else None


def listar_doacoes():
    """Visão para o painel do administrador (uma linha por doação, com a ONG aceita, se houver)."""
    with sessao() as conn:
        linhas = conn.execute(
            """SELECT d.*, o.nome AS ong_aceita, m.distancia_km AS distancia_aceita
               FROM doacoes d
               LEFT JOIN matches m ON m.doacao_id = d.id AND m.status = 'ACEITO'
               LEFT JOIN ongs o ON o.id = m.ong_id
               ORDER BY d.criado_em DESC""").fetchall()
    return [dict(l) for l in linhas]


def listar_itens():
    """Itens de todas as doações (para o dashboard)."""
    with sessao() as conn:
        linhas = conn.execute(
            """SELECT i.*, d.criado_em AS doacao_criada_em, d.status AS doacao_status, d.protocolo
               FROM itens_doacao i JOIN doacoes d ON d.id = i.doacao_id ORDER BY i.id""").fetchall()
    return [dict(l) for l in linhas]


def listar_matches():
    """Todas as opções oferecidas, com a ONG e a data da doação (para o dashboard)."""
    with sessao() as conn:
        linhas = conn.execute(
            """SELECT m.*, o.nome AS ong_nome, d.criado_em AS doacao_criada_em, d.protocolo
               FROM matches m JOIN ongs o ON o.id = m.ong_id JOIN doacoes d ON d.id = m.doacao_id
               ORDER BY m.id""").fetchall()
    return [dict(l) for l in linhas]


# ----------------------------------------------------------------------------
# Cache de geocodificação
# ----------------------------------------------------------------------------
def _chave_geo(consulta):
    texto = str(consulta or "")
    digitos = re.sub(r"\D", "", texto)
    return f"cep:{digitos}" if len(digitos) == 8 and len(texto.strip()) <= 9 else f"txt:{_sem_acento(texto)}"


def obter_cache_geo(consulta):
    """Devolve {'latitude', 'longitude', 'endereco_formatado', 'fonte', 'detalhes': {...}} ou None."""
    with sessao() as conn:
        l = conn.execute("SELECT * FROM cache_geocodificacao WHERE chave = ?", (_chave_geo(consulta),)).fetchone()
    if not l:
        return None
    r = dict(l)
    r["detalhes"] = json.loads(r["detalhes"]) if r.get("detalhes") else {}
    return r


def salvar_cache_geo(consulta, latitude, longitude, endereco_formatado=None, fonte=None, detalhes=None):
    with sessao() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO cache_geocodificacao
                   (chave, latitude, longitude, endereco_formatado, fonte, detalhes)
               VALUES (?,?,?,?,?,?)""",
            (_chave_geo(consulta), float(latitude), float(longitude), endereco_formatado, fonte,
             json.dumps(detalhes, ensure_ascii=False) if detalhes else None))


if __name__ == "__main__":
    inicializar_banco()