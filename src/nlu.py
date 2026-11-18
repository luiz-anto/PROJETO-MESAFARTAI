"""
nlu.py - Motor de compreensão de linguagem natural (NLU) do MESAFARTAI.

Pipeline:
    texto -> pré-processamento (Regex + Spacy) -> TF-IDF (palavras + caracteres)
          -> Regressão Logística -> intenção + confiança -> regra de threshold (fallback)

Pontos didáticos:
  * Spacy faz a lematização ("doaria", "doando" -> "doar").
  * Regex troca e-mails, CEPs, protocolos e números por "marcadores" genéricos, para o
    modelo aprender o padrão da frase e não o valor específico.
  * TF-IDF de caracteres torna o modelo tolerante a erros de digitação.
  * O threshold é calibrado com dados (veja `varrer_limiares`), não por palpite.
  * `intencoes_permitidas` restringe a classificação ao contexto da conversa
    (ex.: ao perguntar "aceita esta ONG?", só importam aceitar_opcao / recusar_opcao).

Uso:
    from nlu import MotorNLU
    nlu = MotorNLU()
    nlu.processar_mensagem("Tenho 30 kg de banana para doar")

Teste rápido:  python src/nlu.py
"""
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.pipeline import FeatureUnion, Pipeline

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_TREINO = RAIZ / "data" / "dataset_intencoes.csv"
CAMINHO_TESTE = RAIZ / "data" / "dataset_teste.csv"

LIMIAR_PADRAO = 0.50  # escolhido com `python src/nlu.py` (tabela de limiares); revise com dados reais

# ----------------------------------------------------------------------------
# Respostas-padrão por intenção (o app.py pode sobrescrever conforme o fluxo)
# ----------------------------------------------------------------------------
RESPOSTAS = {
    "saudacao_ajuda": (
        "Olá! Eu sou o assistente do **MESAFARTAI**. Eu conecto quem tem alimentos para doar "
        "às ONGs mais próximas. Para começar, me conte **o que você deseja doar**."
    ),
    "cadastrar_doacao": "Que ótimo! Vamos registrar a sua doação.",
    "solicitar_alimentos": (
        "Este canal é para **quem deseja doar**. As ONGs são cadastradas pela administração do "
        "MESAFARTAI e passam a receber as doações automaticamente. Se a sua organização quer "
        "participar, entre em contato com a administração."
    ),
    "consultar_status": "Claro! Me informe o **código de protocolo** da sua doação (ex.: MF-20261103-0042).",
    "aceitar_opcao": "Perfeito, vou confirmar essa opção.",
    "recusar_opcao": "Sem problemas, vou verificar a próxima opção.",
    "fora_de_escopo": (
        "Eu só consigo ajudar com **doação de alimentos**. Se quiser doar, me diga o que você tem "
        "disponível."
    ),
    "fallback": (
        "Desculpe, não consegui entender com clareza. Você quer **doar alimentos** ou "
        "**consultar uma doação**?"
    ),
}

# ----------------------------------------------------------------------------
# Pré-processamento
# ----------------------------------------------------------------------------
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_RE_PROTOCOLO = re.compile(r"\bmf[-\s]?\d{6,8}[-\s]?\d{3,}\b", re.IGNORECASE)
_RE_CEP = re.compile(r"\b\d{5}-?\d{3}\b")
_RE_DATA = re.compile(r"\b\d{1,2}/\d{1,2}(/\d{2,4})?\b")
_RE_HORA = re.compile(r"\b\d{1,2}(h\d{0,2}|:\d{2})\b", re.IGNORECASE)
_RE_NUMERO = re.compile(r"\d+([.,]\d+)?")
_RE_TOKEN = re.compile(r"[a-zà-ú0-9]+", re.IGNORECASE)

_NLP = None
_SPACY_TENTADO = False


def _carregar_spacy():
    """Carrega o Spacy uma única vez. Se o modelo não estiver instalado, devolve None."""
    global _NLP, _SPACY_TENTADO
    if not _SPACY_TENTADO:
        _SPACY_TENTADO = True
        try:
            import spacy
            _NLP = spacy.load("pt_core_news_sm", disable=["parser", "ner"])
        except Exception:
            _NLP = None
    return _NLP


def remover_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def mascarar_padroes(texto):
    """Troca valores específicos por marcadores genéricos (o Spacy não os altera)."""
    t = texto.lower()
    t = _RE_EMAIL.sub(" xemailx ", t)
    t = _RE_PROTOCOLO.sub(" xprotocolox ", t)
    t = _RE_CEP.sub(" xcepx ", t)
    t = _RE_DATA.sub(" xdatax ", t)
    t = _RE_HORA.sub(" xhorax ", t)
    t = _RE_NUMERO.sub(" xnumx ", t)
    return t


def preprocessar(texto, usar_spacy=True):
    """Normaliza o texto: marcadores -> lematização (Spacy) -> sem acentos."""
    t = mascarar_padroes(str(texto))
    nlp = _carregar_spacy() if usar_spacy else None
    if nlp is not None:
        tokens = [tok.lemma_.lower() for tok in nlp(t) if not (tok.is_punct or tok.is_space)]
        t = " ".join(tokens)
    else:
        t = " ".join(_RE_TOKEN.findall(t))
    return remover_acentos(t)


# ----------------------------------------------------------------------------
# Motor de NLU
# ----------------------------------------------------------------------------
class MotorNLU:
    def __init__(self, limiar_threshold=LIMIAR_PADRAO, caminho_treino=CAMINHO_TREINO, usar_spacy=True):
        self.limiar_threshold = limiar_threshold
        self.usar_spacy = usar_spacy and _carregar_spacy() is not None
        self.modelo = Pipeline([
            ("tfidf", FeatureUnion([
                ("palavras", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
                ("caracteres", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)),
            ])),
            ("clf", LogisticRegression(C=20, max_iter=3000, class_weight="balanced")),
        ])
        self._treinar(caminho_treino)

    # --- treino ---------------------------------------------------------------
    def _prep_lote(self, textos):
        return [preprocessar(t, self.usar_spacy) for t in textos]

    def _treinar(self, caminho):
        df = pd.read_csv(caminho, encoding="utf-8").dropna()
        self.modelo.fit(self._prep_lote(df["frase"]), df["intencao"])
        self.classes = list(self.modelo.classes_)
        modo = "Spacy + Regex" if self.usar_spacy else "somente Regex (modelo Spacy não encontrado)"
        print(f" [NLU] Modelo treinado com {len(df)} frases | pré-processamento: {modo}")

    # --- inferência -------------------------------------------------------------
    def _probabilidades(self, texto):
        return self.modelo.predict_proba(self._prep_lote([texto]))[0]

    def processar_mensagem(self, texto_usuario, intencoes_permitidas=None):
        """
        Classifica a mensagem.

        intencoes_permitidas: lista opcional de intenções válidas no contexto atual.
        Retorna um dicionário:
            intencao   -> nome da intenção, "fora_de_escopo" ou "fallback" (baixa confiança)
            confianca  -> probabilidade da melhor intenção (0 a 1)
            fallback   -> True quando o app deve pedir esclarecimento / recusar o assunto
            top3       -> as 3 intenções mais prováveis (útil para depuração e aulas)
            resposta   -> texto-padrão sugerido
        """
        texto = (texto_usuario or "").strip()
        if not texto:
            return self._montar("fallback", 0.0, [("fallback", 0.0)])

        probs = self._probabilidades(texto)
        pares = list(zip(self.classes, probs))

        if intencoes_permitidas:
            pares = [(c, p) for c, p in pares if c in intencoes_permitidas]
            total = sum(p for _, p in pares)
            pares = [(c, p / total) for c, p in pares] if total > 0 else pares

        pares.sort(key=lambda x: x[1], reverse=True)
        intencao, confianca = pares[0]
        top3 = [(c, round(float(p), 3)) for c, p in pares[:3]]

        if confianca < self.limiar_threshold:
            return self._montar("fallback", confianca, top3)
        return self._montar(intencao, confianca, top3)

    @staticmethod
    def _montar(intencao, confianca, top3):
        return {
            "intencao": intencao,
            "confianca": float(confianca),
            "fallback": intencao in ("fallback", "fora_de_escopo"),
            "top3": top3,
            "resposta": RESPOSTAS[intencao],
        }

    # --- avaliação ----------------------------------------------------------------
    def avaliar(self, caminho_teste=CAMINHO_TESTE, verbose=True):
        """Mede o desempenho em frases que o modelo NUNCA viu no treino."""
        df = pd.read_csv(caminho_teste, encoding="utf-8").dropna()
        pred = self.modelo.predict(self._prep_lote(df["frase"]))
        acc = accuracy_score(df["intencao"], pred)
        if verbose:
            print(f"\n Acurácia no conjunto de teste ({len(df)} frases): {acc:.1%}\n")
            print(classification_report(df["intencao"], pred, zero_division=0))
            erros = df[df["intencao"] != pred].assign(previsto=pred[df["intencao"] != pred])
            if len(erros):
                print(" Erros:")
                for _, r in erros.iterrows():
                    print(f"   '{r['frase']}'  esperado={r['intencao']}  previsto={r['previsto']}")
        return acc

    def varrer_limiares(self, caminho_teste=CAMINHO_TESTE, limiares=(0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70)):
        """
        Mostra o compromisso do threshold:
          - cobertura: % de mensagens que o bot aceita responder
          - acerto entre as aceitas: % de acerto quando ele responde
        """
        df = pd.read_csv(caminho_teste, encoding="utf-8").dropna()
        probs = self.modelo.predict_proba(self._prep_lote(df["frase"]))
        previsto = np.array(self.classes)[probs.argmax(axis=1)]
        conf = probs.max(axis=1)
        certo = previsto == df["intencao"].values
        print("\n limiar | cobertura | acerto entre as aceitas")
        for lim in limiares:
            aceitas = conf >= lim
            cob = aceitas.mean()
            acerto = certo[aceitas].mean() if aceitas.any() else float("nan")
            print(f"  {lim:.2f}  |  {cob:7.1%}  |  {acerto:7.1%}")


# ----------------------------------------------------------------------------
# Teste em linha de comando:  python src/nlu.py
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    nlu = MotorNLU()
    nlu.avaliar()
    nlu.varrer_limiares()

    print("\n--- DEMONSTRAÇÃO ---")
    exemplos = [
        "Tenho 30 kg de banana para doar",
        "Oi, sou a Marina, quero doar 15 kg de arroz, meu email é marina@teste.com",
        "Nossa instituição precisa de mantimentos",
        "Qual é a receita de bolo de cenoura?",
        "coisa comida doar la",
        "Quero ver o protocolo MF-20261103-0042",
        "qro doa uns paes",
    ]
    for frase in exemplos:
        r = nlu.processar_mensagem(frase)
        print(f"\n'{frase}'\n  -> {r['intencao']} ({r['confianca']:.2f}) | top3: {r['top3']}")

    print("\n--- COM CONTEXTO (esperando aceite ou recusa) ---")
    for frase in ["pode ser", "não, quero a outra", "banana"]:
        r = nlu.processar_mensagem(frase, intencoes_permitidas=["aceitar_opcao", "recusar_opcao"])
        print(f"'{frase}' -> {r['intencao']} ({r['confianca']:.2f})")