"""
entities.py - Extração de entidades das mensagens do doador (MESAFARTAI).

O que extrai de um texto livre:
    nome, e-mail, CEP / endereço, itens (alimento + quantidade + unidade + categorias) e validade.

Estratégia (ótima para ensinar):
    1ª linha  -> Regex   (e-mail, CEP, datas, horas, quantidades, endereços)
    2ª linha  -> Dicionário data/alimentos.csv (editável sem mexer em código)
    3ª linha  -> Spacy   (lematização para achar alimentos em formas não previstas, e NER de pessoas)

Princípio: NUNCA inventar dado. O que não foi informado volta como None / lista vazia, e
`campos_faltantes()` diz ao chatbot o que ainda precisa ser perguntado.

Uso:
    ex = ExtratorEntidades()
    dados = ex.processar_texto("Sou a Marina, tenho 15 kg de tomate, vence amanhã. marina@x.com")
    ex.campos_faltantes(dados)   # -> ['localizacao']

Teste rápido:  python src/entities.py
"""
import csv
import re
import unicodedata
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:  # sem tzdata (ex.: Windows): usa a hora local da máquina
    _FUSO = None

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_ALIMENTOS = RAIZ / "data" / "alimentos.csv"
CATEGORIAS = ("líquidos", "perecíveis", "congelados")  # "sólidos" foi retirado (decisão do projeto)

PERGUNTAS = {
    "nome": "Qual é o seu **nome**?",
    "email": "Qual é o seu **e-mail** para contato?",
    "itens": "O que você deseja **doar**? (ex.: 10 kg de arroz)",
    "categorias": "O alimento **{alimento}** é líquido, perecível ou congelado? (responda \"nenhum\" se não for nenhum deles)",
    "localizacao": "Qual é o **CEP** (ou endereço) de onde os alimentos serão retirados?",
}


# ----------------------------------------------------------------------------
# Normalização de texto
# ----------------------------------------------------------------------------
def remover_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _singular(p):
    """Singularização simples do português: pães -> pao, feijões -> feijao, legumes -> legume."""
    if len(p) <= 3:
        return p
    if p.endswith(("oes", "aes")):
        return p[:-3] + "ao"
    if p.endswith("ais"):
        return p[:-3] + "al"
    if p.endswith("ns"):
        return p[:-2] + "m"
    if p.endswith("s") and not p.endswith(("ss", "us", "is")):
        return p[:-1]
    return p


def normalizar_termo(texto):
    """'Pães Franceses' -> 'pao frances' (minúsculo, sem acento, no singular)."""
    palavras = re.findall(r"[a-z0-9]+", remover_acentos(str(texto).lower()))
    return " ".join(_singular(p) for p in palavras)


# ----------------------------------------------------------------------------
# Tabelas auxiliares
# ----------------------------------------------------------------------------
UNIDADES = {
    "kg": "kg", "kgs": "kg", "kilo": "kg", "quilo": "kg", "quilograma": "kg",
    "g": "g", "grama": "g",
    "l": "L", "lt": "L", "lts": "L", "litro": "L", "ml": "ml", "mililitro": "ml",
    "caixa": "caixa", "unidade": "unidade", "un": "unidade", "und": "unidade",
    "pacote": "pacote", "pct": "pacote", "saco": "saco", "saca": "saca", "lata": "lata",
    "fardo": "fardo", "duzia": "dúzia", "bandeja": "bandeja", "garrafa": "garrafa", "pote": "pote",
}
NUMEROS_EXTENSO = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
    "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "quinze": 15, "vinte": 20, "trinta": 30,
    "quarenta": 40, "cinquenta": 50, "cem": 100, "cento": 100,
}
CONECTORES = {"de", "do", "da", "dos", "das", "em"}
PARADA = {  # palavras que encerram o nome de um alimento
    "e", "ou", "para", "pra", "pro", "que", "com", "sem", "vence", "vencem", "vencimento", "validade",
    "valido", "perto", "proximo", "ate", "hoje", "amanha", "a", "ao", "no", "na", "nos", "nas", "aqui", "la",
    "ja", "mas", "se", "quero", "tenho", "vou", "posso", "gostaria", "meu", "minha", "nosso", "nossa",
    "cep", "sobrou", "sobraram", "doar", "doacao", "retirada", "retirar", "como", "por", "favor", "hj",
    "porque", "pois", "so", "fica", "ficam", "estao", "esta",
}
ORGANIZACOES = {
    "mercado", "supermercado", "restaurante", "padaria", "empresa", "loja", "lanchonete", "hotel", "escola",
    "condominio", "feira", "sacolao", "acougue", "hortifruti", "ong", "igreja", "associacao", "instituicao",
    "fazenda", "sitio", "buffet", "cozinha", "quitanda", "mercearia", "atacado", "mercadinho", "comercio",
    "industria", "fabrica", "cooperativa", "grupo", "rede", "casa", "bar", "pizzaria", "confeitaria",
}
NAO_NOMES = {  # após "sou ..." isso NÃO é um nome
    "de", "da", "do", "dos", "das", "um", "uma", "dono", "dona", "gerente", "proprietario", "proprietaria",
    "empresario", "empresaria", "voluntario", "voluntaria", "representante", "responsavel", "funcionario",
    "funcionaria", "doador", "doadora", "morador", "moradora", "cliente", "comerciante", "chef", "cozinheiro",
    "cozinheira", "padeiro", "padeira", "feirante", "produtor", "produtora", "nao", "novo", "nova", "aqui",
}
PARADA_NOME = {
    "e", "ou", "que", "quero", "tenho", "vou", "gostaria", "posso", "preciso", "estou", "queria", "venho",
    "trabalho", "moro", "represento", "com", "para", "pra", "na", "no", "aqui", "meu", "minha", "tem",
    "oi", "ola", "sim", "ok", "nao", "obrigado", "obrigada", "email", "cep",
}
DIAS_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}

# ----------------------------------------------------------------------------
# Expressões regulares
# ----------------------------------------------------------------------------
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_RE_CEP = re.compile(r"(?<!\d)(\d{5})-?(\d{3})(?!\d)")
_RE_PROTOCOLO = re.compile(r"\bmf[-\s]?\d{6,8}[-\s]?\d{3,}\b", re.IGNORECASE)
_RE_DATA = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])")
_RE_HORA = re.compile(r"(?<!\d)(\d{1,2})\s*(?:h|:)\s*(\d{2})?(?![\d])", re.IGNORECASE)
_RE_NUM_LONGO = re.compile(r"\d{9,}")
_RE_TOKEN = re.compile(r"\d{1,3}(?:\.\d{3})+(?!\d)|\d+(?:[.,]\d+)?|[a-zà-ÿ]+|[,;.!?#]", re.IGNORECASE)
_RE_ENDERECO = re.compile(
    r"\b(?:rua|r\.|avenida|av\.?|alameda|travessa|estrada|rodovia|pra[cç]a|largo)\s+"
    r"[^,;\n\d]{2,50}?(?:\s*,?\s*(?:n[ºo°.]*\s*)?\d{1,5})?(?=[,;.\n]|\s+(?:cep|bairro|e-?mail)|$)",
    re.IGNORECASE)
_RE_NOME_GATILHO = re.compile(
    r"(?:meu\s+nome\s*(?:é|e|eh|:)?|me\s+chamo|chamo-me|nome\s*:|aqui\s+(?:é|e|eh)|(?:eu\s+)?sou)\s+"
    r"(?:(?:o|a)\s+)?(?P<resto>[^,.;!?\n@\d]{2,60})", re.IGNORECASE)
_RE_CUE_VALIDADE = re.compile(r"venc\w*|validade|v[aá]lid[oa]|expir\w*|bom\s+at[eé]|consumir\s+at[eé]|val\.", re.IGNORECASE)
_RE_PERTO_VENC = re.compile(r"(?:perto|pr[oó]ximo|prestes)\s+(?:d?o\s+|a\s+|ao\s+)?(?:vencimento|vencer)", re.IGNORECASE)


# ----------------------------------------------------------------------------
# Spacy (opcional): lematização e reconhecimento de pessoas
# ----------------------------------------------------------------------------
_NLP = None
_SPACY_TENTADO = False


def _carregar_spacy():
    global _NLP, _SPACY_TENTADO
    if not _SPACY_TENTADO:
        _SPACY_TENTADO = True
        try:
            import spacy
            _NLP = spacy.load("pt_core_news_sm", disable=["parser"])
        except Exception:
            _NLP = None
    return _NLP


@lru_cache(maxsize=2048)
def _lema(palavra):
    nlp = _carregar_spacy()
    if nlp is None:
        return normalizar_termo(palavra)
    doc = nlp(palavra)
    return normalizar_termo(doc[0].lemma_) if len(doc) else normalizar_termo(palavra)


def _titulo(nome):
    particulas = {"de", "da", "do", "dos", "das", "e"}
    return " ".join(p.lower() if p.lower() in particulas else p[:1].upper() + p[1:].lower() for p in nome.split())


def _numero(token):
    """'15,5' -> 15.5 | '1.000' -> 1000 | '10' -> 10"""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
        return int(token.replace(".", ""))
    valor = float(token.replace(",", "."))
    return int(valor) if valor.is_integer() else valor


# ----------------------------------------------------------------------------
# Extrator
# ----------------------------------------------------------------------------
class ExtratorEntidades:
    def __init__(self, caminho_alimentos=CAMINHO_ALIMENTOS, usar_spacy=True):
        self.usar_spacy = usar_spacy
        self.alimentos = {}   # nome canônico -> lista de categorias
        self._indice = {}     # termo normalizado (nome ou sinônimo) -> nome canônico
        self._max_ngram = 1
        self._carregar_dicionario(caminho_alimentos)

    # --- dicionário -------------------------------------------------------------
    def _carregar_dicionario(self, caminho):
        with open(caminho, encoding="utf-8", newline="") as f:
            for linha in csv.DictReader(f, delimiter=";"):
                nome = linha["alimento"].strip()
                cats = [c.strip() for c in linha["categorias"].split("|") if c.strip()]
                invalidas = set(cats) - set(CATEGORIAS)
                if invalidas:
                    raise ValueError(f"Categoria inválida em '{nome}': {', '.join(invalidas)}")
                self.alimentos[nome] = [c for c in CATEGORIAS if c in cats]
                termos = [nome] + [s for s in (linha.get("sinonimos") or "").split("|") if s.strip()]
                for termo in termos:
                    chave = normalizar_termo(termo)
                    self._indice[chave] = nome
                    self._max_ngram = max(self._max_ngram, len(chave.split()))

    def _buscar_alimento(self, tokens, i):
        """Procura o maior termo do dicionário começando em tokens[i]. Retorna (nome, nº de tokens)."""
        for n in range(min(self._max_ngram, len(tokens) - i), 0, -1):
            nome = self._indice.get(" ".join(tokens[i:i + n]))
            if nome:
                return nome, n
        if self.usar_spacy:  # plano B: lema da palavra (ex.: formas verbais/flexões não previstas)
            nome = self._indice.get(_lema(tokens[i]))
            if nome:
                return nome, 1
        return None, 0

    # --- utilidades de tempo ----------------------------------------------------
    @staticmethod
    def _agora():
        return datetime.now(_FUSO) if _FUSO else datetime.now()

    # --- e-mail / CEP / endereço --------------------------------------------------
    def extrair_email(self, texto):
        m = _RE_EMAIL.search(texto or "")
        return m.group(0).rstrip(".").lower() if m else None

    def extrair_cep(self, texto):
        m = _RE_CEP.search(_RE_PROTOCOLO.sub(" ", texto or ""))
        return f"{m.group(1)}-{m.group(2)}" if m else None

    def extrair_endereco(self, texto):
        m = _RE_ENDERECO.search(texto or "")
        return re.sub(r"\s+", " ", m.group(0)).strip(" ,.;") if m else None

    # --- nome -------------------------------------------------------------------
    def extrair_nome(self, texto, resposta_direta=False):
        """
        resposta_direta=True: o bot acabou de perguntar o nome, então a resposta inteira é o nome
        (ex.: "Maria da Silva"). Caso contrário procuramos padrões como "meu nome é ..." / "sou o ...".
        """
        texto = (texto or "").strip()
        nome = self._nome_por_gatilho(texto)
        if nome:
            return nome
        if resposta_direta:
            limpo = re.sub(r"^(?:é|e|eh)\s+(?:o\s+|a\s+)?", "", texto.strip(" .!"), flags=re.IGNORECASE)
            palavras = limpo.split()
            if 1 <= len(palavras) <= 5 and all(re.fullmatch(r"[A-Za-zÀ-ÿ'’-]+", p) for p in palavras) \
                    and not any(remover_acentos(p.lower()) in PARADA_NOME for p in palavras):
                return _titulo(limpo)
            return None
        return self._nome_por_spacy(texto)

    def extrair_nome_explicito(self, texto):
        """Só aceita nomes ditos de forma explícita ('meu nome é...', 'sou o...'), sem o palpite do Spacy."""
        return self._nome_por_gatilho((texto or "").strip())

    def _nome_por_gatilho(self, texto):
        for m in _RE_NOME_GATILHO.finditer(texto):
            palavras = m.group("resto").split()
            nome, i = [], 0
            while i < len(palavras) and len(nome) < 5:
                p = palavras[i]
                n = remover_acentos(p.lower())
                if not re.fullmatch(r"[A-Za-zÀ-ÿ'’-]+", p):
                    break
                if not nome and (n in NAO_NOMES or n in ORGANIZACOES):
                    break
                if n in PARADA_NOME or n in ORGANIZACOES:
                    break
                if n in {"de", "da", "do", "dos", "das"}:
                    prox = remover_acentos(palavras[i + 1].lower()) if i + 1 < len(palavras) else ""
                    if not nome or not prox or prox in ORGANIZACOES or prox in PARADA_NOME or prox in NAO_NOMES:
                        break
                nome.append(p)
                i += 1
            while nome and remover_acentos(nome[-1].lower()) in {"de", "da", "do", "dos", "das"}:
                nome.pop()
            if nome:
                return _titulo(" ".join(nome))
        return None

    def _nome_por_spacy(self, texto):
        nlp = _carregar_spacy() if self.usar_spacy else None
        if nlp is None:
            return None
        for ent in nlp(texto).ents:
            palavras = ent.text.split()
            if ent.label_ == "PER" and 1 <= len(palavras) <= 4 and \
                    not any(remover_acentos(p.lower()) in (ORGANIZACOES | PARADA_NOME | NAO_NOMES) for p in palavras):
                return _titulo(ent.text)
        return None

    # --- itens (alimento + quantidade + unidade) -----------------------------------
    def _mascarar(self, texto):
        t = _RE_EMAIL.sub(" # ", texto)
        t = _RE_PROTOCOLO.sub(" # ", t)
        t = _RE_CEP.sub(" # ", t)
        t = _RE_DATA.sub(" # ", t)
        t = _RE_HORA.sub(" # ", t)
        return _RE_NUM_LONGO.sub(" # ", t)

    def extrair_itens(self, texto):
        """
        Retorna uma lista de itens: {"alimento", "quantidade", "unidade", "categorias", "reconhecido"}.
        Alimento fora do dicionário (mas com quantidade + unidade) volta com reconhecido=False.
        """
        brutos = _RE_TOKEN.findall(self._mascarar(texto or ""))
        tokens = [remover_acentos(t.lower()) for t in brutos]
        norm = [_singular(t) if t.isalpha() else t for t in tokens]  # tokens no singular
        itens, usados = [], set()
        i = 0
        while i < len(tokens):
            tk = tokens[i]
            e_num = tk[0].isdigit()
            e_extenso = tk in NUMEROS_EXTENSO
            if not (e_num or e_extenso):
                i += 1
                continue
            qtd = _numero(brutos[i]) if e_num else NUMEROS_EXTENSO[tk]
            j = i + 1
            unidade = None
            if j < len(tokens) and norm[j] in UNIDADES:
                unidade = UNIDADES[norm[j]]
                j += 1
            if j < len(tokens) and tokens[j] in CONECTORES:
                j += 1
            # janela com o possível nome do alimento (até 4 palavras)
            fim = j
            while fim < len(tokens) and fim - j < 4 and tokens[fim].isalpha() and \
                    (tokens[fim] in CONECTORES or tokens[fim] not in PARADA):
                fim += 1
            while fim > j and tokens[fim - 1] in CONECTORES:
                fim -= 1
            janela = norm[j:fim]
            if not janela:
                i += 1
                continue
            nome, n = self._buscar_alimento(janela, 0)
            if nome:
                itens.append({"alimento": nome, "quantidade": qtd, "unidade": unidade or "unidade",
                              "categorias": self._ajustar_categorias(self.alimentos[nome], janela[n:n + 2]),
                              "reconhecido": True})
                usados.add(nome)
                i = j + n
            elif unidade:  # tem quantidade e unidade, mas o alimento não está no dicionário
                desconhecido = " ".join(brutos[j:min(fim, j + 2)]).lower()
                itens.append({"alimento": desconhecido, "quantidade": qtd, "unidade": unidade,
                              "categorias": [], "reconhecido": False})
                i = max(fim, j)
            else:
                i += 1
        # alimentos citados sem quantidade ("tenho feijão e arroz")
        palavras = [(t, _singular(t)) for t in tokens if t.isalpha()]
        ns = [n for _, n in palavras]
        k = 0
        while k < len(ns):
            nome, n = self._buscar_alimento(ns, k)
            if nome:
                if nome not in usados:
                    itens.append({"alimento": nome, "quantidade": None, "unidade": None,
                                  "categorias": self._ajustar_categorias(self.alimentos[nome], ns[k + n:k + n + 2]),
                                  "reconhecido": True})
                    usados.add(nome)
                k += n
            else:
                k += 1
        return itens

    @staticmethod
    def _ajustar_categorias(categorias, palavras_seguintes):
        """'carne moída congelada': o modificador troca 'perecíveis' por 'congelados'."""
        cats = list(categorias)
        if any(p.startswith("congelad") for p in palavras_seguintes) and "congelados" not in cats:
            cats = [c for c in cats if c != "perecíveis"] + ["congelados"]
        return [c for c in CATEGORIAS if c in cats]

    @staticmethod
    def unir_categorias(itens):
        achadas = {c for it in itens for c in it["categorias"]}
        return [c for c in CATEGORIAS if c in achadas]

    @staticmethod
    def descrever_itens(itens):
        partes = []
        for it in itens:
            if it["quantidade"] is None:
                partes.append(it["alimento"])
            else:
                un = "un." if it["unidade"] == "unidade" else it["unidade"]
                partes.append(f"{it['quantidade']} {un} de {it['alimento']}")
        return "; ".join(partes)

    @staticmethod
    def extrair_categorias(texto):
        """
        Para alimentos desconhecidos: lê a resposta do doador.
        Retorna a lista de categorias, [] se a resposta for "nenhum / não / sólido",
        ou None se não entendeu (o bot deve perguntar de novo).
        """
        t = remover_acentos((texto or "").lower())
        achadas = []
        if "liquid" in t and not re.search(r"nao\s+(?:e\s+)?liquid", t):
            achadas.append("líquidos")
        if re.search(r"perecivel|pereciveis", t) and \
                not re.search(r"nao\s+(?:e\s+|sao\s+)?(?:um\s+)?perecivel|nao\s+pereciveis|imperecivel", t):
            achadas.append("perecíveis")
        if "congelad" in t and not re.search(r"nao\s+(?:e\s+|sao\s+)?congelad", t):
            achadas.append("congelados")
        if achadas:
            return [c for c in CATEGORIAS if c in achadas]
        if re.search(r"\b(?:nenhum|nenhuma|nada|solido|seco|nao)\b", t):
            return []
        return None

    # --- validade ---------------------------------------------------------------
    def extrair_validade(self, texto, agora=None, resposta_direta=False):
        """
        Só considera validade quando há uma pista ("vence", "validade", "válido até"...), para não
        confundir com o prazo de entrega ("posso doar hoje"). Com resposta_direta=True (o bot acabou
        de perguntar a validade) o texto inteiro é analisado.
        Retorna {"data_validade": 'AAAA-MM-DD[ HH:MM]' | None, "validade_texto": str | None, "alertas": [...]}
        """
        agora = agora or self._agora()
        hoje = agora.date()
        texto = texto or ""
        res = {"data_validade": None, "validade_texto": None, "alertas": []}

        if resposta_direta:
            janela = texto
        else:
            cue = _RE_CUE_VALIDADE.search(texto)
            perto = _RE_PERTO_VENC.search(texto)
            if perto and (not cue or perto.start() <= cue.start() < perto.end()):
                res["validade_texto"] = "perto do vencimento"  # sem data exata
                return res
            if not cue:
                return res
            janela = texto[cue.start(): cue.end() + 50]

        t = remover_acentos(janela.lower())
        data, trecho = None, None

        m = _RE_DATA.search(janela)
        if m:
            dia, mes = int(m.group(1)), int(m.group(2))
            ano = int(m.group(3)) if m.group(3) else hoje.year
            ano = ano + 2000 if ano < 100 else ano
            try:
                data = date(ano, mes, dia)
                if not m.group(3) and data < hoje - timedelta(days=30):
                    data = date(ano + 1, mes, dia)
                trecho = m.group(0)
            except ValueError:
                res["alertas"].append(f"Data inválida: {m.group(0)}.")
        if data is None:
            if re.search(r"depois\s+de\s+amanha", t):
                data, trecho = hoje + timedelta(days=2), "depois de amanhã"
            elif re.search(r"amanha", t):
                data, trecho = hoje + timedelta(days=1), "amanhã"
            elif re.search(r"\bhoje\b", t):
                data, trecho = hoje, "hoje"
        if data is None:
            m = re.search(r"(?:em|de|daqui\s+a|dentro\s+de|ate)\s+(\d{1,3})\s+dias?", t) or \
                re.search(r"(?<!\d)(\d{1,3})\s+dias?\b", t)
            if m:
                data, trecho = hoje + timedelta(days=int(m.group(1))), m.group(0)
        if data is None:
            m = re.search(r"(?:em|de|daqui\s+a)\s+(\d{1,2})\s+semanas?", t)
            if m:
                data, trecho = hoje + timedelta(weeks=int(m.group(1))), m.group(0)
            elif re.search(r"semana\s+que\s+vem|proxima\s+semana", t):
                data, trecho = hoje + timedelta(days=7), "semana que vem"
        if data is None:
            m = re.search(r"\bdia\s+(\d{1,2})\b", t)
            if m:
                try:
                    data = date(hoje.year, hoje.month, int(m.group(1)))
                    if data < hoje:
                        ano, mes = (hoje.year + 1, 1) if hoje.month == 12 else (hoje.year, hoje.month + 1)
                        data = date(ano, mes, int(m.group(1)))
                    trecho = m.group(0)
                except ValueError:
                    res["alertas"].append(f"Dia inválido: {m.group(0)}.")
        if data is None:
            m = re.search(r"\b(segunda|terca|quarta|quinta|sexta|sabado|domingo)\b", t)
            if m:
                data = hoje + timedelta(days=(DIAS_SEMANA[m.group(1)] - hoje.weekday()) % 7)
                trecho = m.group(0)

        hora = None
        mh = _RE_HORA.search(janela)
        if mh and int(mh.group(1)) <= 23 and int(mh.group(2) or 0) <= 59:
            hora = f"{int(mh.group(1)):02d}:{int(mh.group(2) or 0):02d}"
            trecho = f"{trecho} {mh.group(0)}".strip() if trecho else mh.group(0)
            data = data or hoje  # só a hora ("vence às 18h"): considera hoje

        if data:
            res["data_validade"] = f"{data.isoformat()} {hora}" if hora else data.isoformat()
            res["validade_texto"] = trecho
            if data < hoje:
                res["alertas"].append("A validade informada já passou. Confirme com o doador antes de seguir.")
        return res

    # --- API principal --------------------------------------------------------------
    def processar_texto(self, texto, agora=None):
        itens = self.extrair_itens(texto)
        validade = self.extrair_validade(texto, agora)
        return {
            "doador_nome": self.extrair_nome(texto),
            "doador_email": self.extrair_email(texto),
            "cep": self.extrair_cep(texto),
            "endereco_texto": self.extrair_endereco(texto),
            "itens": itens,
            "categorias": self.unir_categorias(itens),
            "descricao_alimento": self.descrever_itens(itens) or None,
            "data_validade": validade["data_validade"],
            "validade_texto": validade["validade_texto"],
            "alertas": validade["alertas"],
        }

    def processar_resposta(self, campo, texto, agora=None):
        """
        Interpreta a resposta a uma pergunta específica do bot (slot filling).
        campo: 'nome' | 'email' | 'localizacao' | 'validade' | 'itens' | 'categorias'
        Retorna um dicionário parcial, pronto para `mesclar()`.
        """
        if campo == "nome":
            return {"doador_nome": self.extrair_nome(texto, resposta_direta=True)}
        if campo == "email":
            return {"doador_email": self.extrair_email(texto)}
        if campo == "localizacao":
            cep = self.extrair_cep(texto)
            endereco = self.extrair_endereco(texto)
            if not cep and not endereco and len((texto or "").strip()) >= 5:
                endereco = texto.strip()  # ex.: "Centro, Taboão da Serra"
            return {"cep": cep, "endereco_texto": endereco}
        if campo == "validade":
            v = self.extrair_validade(texto, agora, resposta_direta=True)
            return {"data_validade": v["data_validade"], "validade_texto": v["validade_texto"], "alertas": v["alertas"]}
        if campo == "itens":
            return {"itens": self.extrair_itens(texto)}
        if campo == "categorias":
            return {"categorias_informadas": self.extrair_categorias(texto)}
        raise ValueError(f"Campo desconhecido: {campo}")

    # --- slot filling ------------------------------------------------------------------
    @staticmethod
    def campos_faltantes(dados):
        """Lista o que o chatbot ainda precisa perguntar (na ordem da conversa)."""
        faltam = []
        if not dados.get("itens"):
            faltam.append("itens")
        if not dados.get("doador_nome"):
            faltam.append("nome")
        if not dados.get("doador_email"):
            faltam.append("email")
        if not (dados.get("cep") or dados.get("endereco_texto")):
            faltam.append("localizacao")
        return faltam

    @staticmethod
    def itens_sem_categoria(dados):
        """Alimentos fora do dicionário: o bot deve perguntar se são líquidos/perecíveis/congelados (PERGUNTAS['categorias'])."""
        return [it for it in dados.get("itens", []) if not it["reconhecido"]]

    def mesclar(self, antigo, novo):
        """Junta o que já se sabe com o que chegou agora. Valores novos substituem os antigos."""
        r = dict(antigo or {})
        novo = dict(novo or {})
        informadas = novo.pop("categorias_informadas", None)  # [] = "nenhum"; None = não entendeu
        for chave, valor in novo.items():
            if chave == "itens":
                existentes = r.get("itens", [])
                for it in valor:
                    if not any((e["alimento"], e["quantidade"], e["unidade"]) ==
                               (it["alimento"], it["quantidade"], it["unidade"]) for e in existentes):
                        existentes.append(it)
                r["itens"] = existentes
            elif chave == "alertas":
                r["alertas"] = sorted(set(r.get("alertas", [])) | set(valor))
            elif valor not in (None, [], ""):
                r[chave] = valor
        itens = r.get("itens", [])
        if informadas is not None:
            for it in itens:
                if not it["reconhecido"]:
                    it["categorias"] = informadas
                    it["reconhecido"] = True
        r["categorias"] = self.unir_categorias(itens)
        r["descricao_alimento"] = self.descrever_itens(itens) or None
        return r


# ----------------------------------------------------------------------------
# Teste em linha de comando:  python src/entities.py
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    ex = ExtratorEntidades()
    agora = datetime(2026, 11, 3, 15, 0)  # data fixa (terça-feira) para o exemplo ser reproduzível
    frases = [
        "Tenho 15.5 kg de tomate para doar hoje até o final do dia",
        "Oi, sou a Marina Souza, tenho 10 litros de leite e 5 kg de arroz. Meu email é marina@teste.com, CEP 06700-000. Vence dia 15/11",
        "Doar 3 kg de jabuticaba, vence em 2 dias",
        "Tenho 200 marmitas, vencem às 18h. Moro na Rua das Flores, 120",
    ]
    for f in frases:
        d = ex.processar_texto(f, agora)
        print(f"\n'{f}'")
        for k, v in d.items():
            if v not in (None, [], ""):
                print(f"   {k}: {v}")
        print("   faltam:", ex.campos_faltantes(d))