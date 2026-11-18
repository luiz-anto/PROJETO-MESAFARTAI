"""
chatbot.py - Lógica da conversa do MESAFARTAI

A conversa é uma MÁQUINA DE ESTADOS. Cada etapa sabe o que o bot acabou de perguntar.

Regras de ouro:
  * o classificador de intenção (NLU) só decide o rumo no ESTADO "inicio". Quando o bot acabou de
    perguntar "qual seu e-mail?", a resposta é tratada como e-mail, não como intenção;
  * respostas sim/não são lidas primeiro por Regex (confiável) e só depois pelo NLU restrito;
  * nada é gravado no banco sem o consentimento do doador (LGPD).

Uso (a interface só precisa disto):
    conversa = Conversa(nlu, extrator, geocodificador, motor)
    conversa.enviar("Tenho 10 kg de arroz para doar")
    conversa.mensagens      # [{"role": "user"|"assistant", "content": "..."}]
    conversa.botoes()       # [(rótulo, texto_enviado), ...] atalhos para a etapa atual
"""
import re
from datetime import datetime

import database as db
from entities import PERGUNTAS
from nlu import RESPOSTAS

try:
    from zoneinfo import ZoneInfo
    _FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:
    _FUSO = None

RE_PROTOCOLO = re.compile(r"\bMF[-\s]?(\d{8})[-\s]?(\d{3,})\b", re.IGNORECASE)
_RE_SIM = re.compile(r"^\s*(sim|s|ok|okay|claro|certo|pode(\s+ser)?|aceito|aceita|confirmo|isso|fechado|beleza|"
                     r"combinado|perfeito|uhum|positivo|bora|correto|est[aá]\s+certo)\b", re.IGNORECASE)
_RE_NAO = re.compile(r"^\s*(n[aã]o|n|nope|negativo|recuso|outra|prefiro\s+(a\s+)?(outra|segunda)|"
                     r"pr[oó]xima|rejeito|descarto|errado|incorreto)\b", re.IGNORECASE)
_RE_CANCELAR = re.compile(r"^\s*(cancelar|cancela|desistir|desisto|recome[cç]ar|reiniciar|sair)\b", re.IGNORECASE)
_RE_PULAR = re.compile(r"\b(n[aã]o\s+sei|n[aã]o|pular|pula|sem\s+validade|nenhuma|desconhe[cç]o)\b", re.IGNORECASE)

STATUS_TEXTO = {
    "DISPONIVEL": "registrada, aguardando a sugestão de uma ONG",
    "MATCH_SUGERIDO": "uma ONG foi sugerida e aguarda a sua resposta",
    "ACEITA": "aceita — combine a entrega diretamente com a ONG",
    "SEM_DESTINO": "sem destino definido (nenhuma ONG foi aceita ou compatível)",
    "COLETADA": "coletada pela ONG",
}


# ----------------------------------------------------------------------------
# Formatação de textos
# ----------------------------------------------------------------------------
def km(valor):
    return f"{valor:.1f}".replace(".", ",") + " km"


def data_br(texto):
    """'2026-11-15' -> '15/11/2026' | '2026-11-15 18:00' -> '15/11/2026 às 18:00'"""
    try:
        if " " in texto:
            return datetime.strptime(texto, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y às %H:%M")
        return datetime.strptime(texto, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return texto


def data_local(criado_em_utc):
    """O SQLite guarda CURRENT_TIMESTAMP em UTC; mostramos em horário de Brasília."""
    try:
        dt = datetime.strptime(criado_em_utc, "%Y-%m-%d %H:%M:%S")
        if _FUSO:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc).astimezone(_FUSO)
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return str(criado_em_utc)


def formatar_ong(ong):
    """Bloco de contato da ONG (aceita o dict do match ou da tabela ongs)."""
    nome = ong.get("ong_nome") or ong.get("nome")
    rua = ", ".join(x for x in (ong.get("logradouro"), ong.get("numero")) if x)
    local = " – ".join(x for x in (rua, ong.get("bairro"), ong.get("cidade")) if x)
    linhas = [f"**{nome}**"]
    if local or ong.get("cep"):
        linhas.append(f"📍 {local}{' ' if local else ''}(CEP {ong['cep']})" if ong.get("cep") else f"📍 {local}")
    if ong.get("telefone"):
        linhas.append(f"📞 {ong['telefone']}")
    if ong.get("email"):
        linhas.append(f"✉️ {ong['email']}")
    if ong.get("horario_recebimento"):
        linhas.append(f"🕒 Recebimento: {ong['horario_recebimento']}")
    return "  \n".join(linhas)


def formatar_doacao(d):
    """Resposta pública da consulta por protocolo (não expõe nome nem e-mail do doador)."""
    linhas = [f"**Protocolo {d['protocolo']}**",
              f"- 🗓️ Registrada em {data_local(d['criado_em'])}",
              f"- 🥫 Itens: {d['descricao_alimento']}",
              f"- 📌 Situação: {STATUS_TEXTO.get(d['status'], d['status'])}"]
    aceito = next((m for m in d["matches"] if m["status"] == "ACEITO"), None)
    pendente = next((m for m in d["matches"] if m["status"] == "SUGERIDO"), None)
    if aceito:
        linhas += ["", "ONG que receberá a doação:", formatar_ong(aceito)]
    elif pendente:
        linhas += ["", f"ONG sugerida aguardando resposta: **{pendente['ong_nome']}** ({km(pendente['distancia_km'])})"]
    return "\n".join(linhas)


# ----------------------------------------------------------------------------
# Conversa
# ----------------------------------------------------------------------------
class Conversa:
    def __init__(self, nlu, extrator, geocodificador, motor, contexto_geografico=None):
        self.nlu, self.ex, self.geo_api, self.motor = nlu, extrator, geocodificador, motor
        self.contexto = contexto_geografico
        self.protocolo = ""
        self.mensagens = []
        self._zerar_fluxo()
        self._dizer(
            "Olá! Eu sou o assistente do **MESAFARTAI** 🍽️, que conecta quem tem alimentos para doar às ONGs "
            "mais próximas.\n\nMe conte **o que você quer doar** (ex.: *Tenho 10 kg de arroz para doar*) ou "
            "digite o **protocolo** de uma doação para acompanhá-la.")

    # --- estado ---------------------------------------------------------------------
    def _zerar_fluxo(self):
        self.etapa = "inicio"
        self.dados = {}
        self.campo = None            # campo que o bot acabou de perguntar (etapa "coletando")
        self.geo = None              # resultado da geocodificação
        self.local_confirmado = False
        self.validade_perguntada = False
        self.mensagem_original = None
        self.oferta = None
        self.doacao_id = None

    def _dizer(self, texto):
        self.mensagens.append({"role": "assistant", "content": texto})

    def botoes(self):
        """Atalhos de resposta rápida para a etapa atual: [(rótulo, texto_enviado)]."""
        if self.etapa == "consentimento":
            return [("✅ Sim, pode registrar", "sim"), ("❌ Não", "não")]
        if self.etapa == "confirmando_local":
            return [("✅ Está correto", "sim"), ("❌ Não é esse local", "não")]
        if self.etapa == "oferta" and self.oferta:
            segunda = ("↪️ Ver outra opção", "outra opção") if self.oferta["ha_segunda_opcao"] \
                else ("❌ Não posso levar até lá", "não")
            return [("✅ Aceito esta ONG", "aceito"), segunda]
        return []

    # --- entrada ----------------------------------------------------------------------
    def enviar(self, texto):
        texto = (texto or "").strip()
        if not texto:
            return
        self.mensagens.append({"role": "user", "content": texto})
        if self.etapa != "inicio" and _RE_CANCELAR.match(texto):
            self._zerar_fluxo()
            self._dizer("Tudo bem, cancelei este atendimento. Nenhum dado foi salvo. "
                        "Quando quiser, me diga o que deseja doar.")
            return
        getattr(self, f"_etapa_{self.etapa}")(texto)

    # --- utilitários ----------------------------------------------------------------------
    def _sim_nao(self, texto):
        """True / False / None (não entendi). Regex primeiro; NLU restrito como plano B."""
        if _RE_SIM.match(texto):
            return True
        if _RE_NAO.match(texto):
            return False
        r = self.nlu.processar_mensagem(texto, intencoes_permitidas=["aceitar_opcao", "recusar_opcao"])
        if r["confianca"] >= 0.70 and not r["fallback"]:
            return r["intencao"] == "aceitar_opcao"
        return None

    # --- etapa: inicio ------------------------------------------------------------------------
    def _etapa_inicio(self, texto):
        resultado = self.nlu.processar_mensagem(texto)
        intencao = resultado["intencao"]
        extraido = self.ex.processar_texto(texto)
        protocolo = RE_PROTOCOLO.search(texto)

        if protocolo:
            intencao = "consultar_status"
        elif intencao == "fallback" and extraido["itens"]:
            intencao = "cadastrar_doacao"  # frase curta como "10 kg de arroz": o Regex salvou a conversa

        if intencao == "cadastrar_doacao":
            self.mensagem_original = texto
            self.dados = self.ex.mesclar({}, extraido)
            self._dizer(RESPOSTAS["cadastrar_doacao"])
            self._avancar()
        elif intencao == "consultar_status":
            if protocolo:
                self._consultar(protocolo.group(0))
            else:
                self.etapa = "protocolo"
                self._dizer(RESPOSTAS["consultar_status"])
        elif intencao in ("aceitar_opcao", "recusar_opcao"):
            self._dizer("No momento não há nenhuma sugestão de ONG aguardando resposta. "
                        "Se quiser doar, me diga o que você tem disponível.")
        else:  # saudacao_ajuda, solicitar_alimentos, fora_de_escopo, fallback
            self._dizer(RESPOSTAS[intencao])

    # --- etapa: protocolo ------------------------------------------------------------------------
    def _etapa_protocolo(self, texto):
        m = RE_PROTOCOLO.search(texto)
        if not m:
            self._dizer("Não encontrei um protocolo nessa mensagem. Ele tem o formato **MF-20261103-0001**. "
                        "Digite-o novamente ou escreva *cancelar*.")
            return
        self.etapa = "inicio"
        self._consultar(m.group(0))

    def _consultar(self, texto_protocolo):
        d = db.buscar_doacao_por_protocolo(texto_protocolo)
        self._dizer(formatar_doacao(d) if d else
                    "Não encontrei nenhuma doação com esse protocolo. Confira o código e tente novamente.")

    # --- etapa: coletando (slot filling) -------------------------------------------------------------
    def _etapa_coletando(self, texto):
        campo = self.campo
        direto = self.ex.processar_resposta(campo, texto)
        geral = self.ex.processar_texto(texto)
        # Informações extras que o doador deu de bônus. Nome e e-mail já conhecidos nunca são sobrescritos
        # por palpites (o NER do Spacy erra com frases curtas); só a correção explícita vale.
        extras = {k: geral[k] for k in ("doador_email", "cep", "endereco_texto", "data_validade", "validade_texto")
                  if geral.get(k) and not (k == "doador_email" and self.dados.get("doador_email"))}
        if not self.dados.get("doador_nome"):
            nome_explicito = self.ex.extrair_nome_explicito(texto)
            if nome_explicito:
                extras["doador_nome"] = nome_explicito
        novo = {**extras, **{k: v for k, v in direto.items() if v not in (None, [], "")}}

        chaves = {"nome": ("doador_nome",), "email": ("doador_email",), "itens": ("itens",),
                  "localizacao": ("cep", "endereco_texto")}[campo]
        entendeu = any(novo.get(k) for k in chaves)
        if any(k in novo for k in ("cep", "endereco_texto")):
            self.geo, self.local_confirmado = None, False  # a localização mudou: geocodificar de novo
            if "cep" in novo and "endereco_texto" not in novo:
                self.dados.pop("endereco_texto", None)
        self.dados = self.ex.mesclar(self.dados, novo)
        if not entendeu:
            self._dizer("Hmm, não consegui entender essa resposta.")
        self._avancar()

    # --- etapa: categoria (alimento fora do dicionário) --------------------------------------------------
    def _etapa_categoria(self, texto):
        pendentes = self.ex.itens_sem_categoria(self.dados)
        categorias = self.ex.extrair_categorias(texto)
        if categorias is None:
            self._dizer("Não entendi. " + PERGUNTAS["categorias"].format(alimento=pendentes[0]["alimento"]))
            return
        item = pendentes[0]  # a resposta vale para o item que foi perguntado
        item["categorias"], item["reconhecido"] = categorias, True
        self.dados["categorias"] = self.ex.unir_categorias(self.dados["itens"])
        self._avancar()

    # --- etapa: validade (só para perecíveis) ----------------------------------------------------------------
    def _etapa_validade(self, texto):
        if _RE_PULAR.search(texto) and not re.search(r"\d", texto):
            self._avancar()
            return
        resposta = self.ex.processar_resposta("validade", texto)
        if not resposta["data_validade"]:
            self._dizer("Não consegui entender a data. Tente *amanhã*, *15/11*, *em 3 dias* ou *sexta* — "
                        "ou responda *não sei*.")
            return
        self.dados = self.ex.mesclar(self.dados, resposta)
        self._avancar()

    # --- etapa: confirmando_local ------------------------------------------------------------------------------
    def _etapa_confirmando_local(self, texto):
        resposta = self._sim_nao(texto)
        if resposta is None:
            self._dizer("Responda **sim** se o local está correto ou **não** para informar outro endereço/CEP.")
        elif resposta:
            self.local_confirmado = True
            self._avancar()
        else:
            self.dados.pop("endereco_texto", None)
            self.dados.pop("cep", None)
            self.geo, self.local_confirmado = None, False
            self._avancar()

    # --- etapa: consentimento ---------------------------------------------------------------------------------------
    def _etapa_consentimento(self, texto):
        resposta = self._sim_nao(texto)
        if resposta is None:
            self._dizer("Responda **sim** para registrar a doação ou **não** para cancelar.")
        elif resposta:
            self._registrar()
        else:
            self._zerar_fluxo()
            self._dizer("Tudo bem! Sem a sua autorização eu não registro nada, e **nenhum dado foi salvo**. "
                        "Se mudar de ideia, é só me chamar.")

    # --- etapa: oferta ------------------------------------------------------------------------------------------------
    def _etapa_oferta(self, texto):
        resposta = self._sim_nao(texto)
        if resposta is None:
            self._dizer("Para continuar, **aceite** a ONG sugerida ou peça **outra opção** "
                        "(use os botões ou escreva *aceito* / *outra*).")
        else:
            self.responder_oferta(resposta)

    # --- motor da conversa: decide a próxima pergunta -------------------------------------------------------------------
    def _avancar(self):
        d = self.dados
        faltam = self.ex.campos_faltantes(d)
        if faltam:
            self.campo, self.etapa = faltam[0], "coletando"
            self._dizer(PERGUNTAS[self.campo])
            return

        sem_categoria = self.ex.itens_sem_categoria(d)
        if sem_categoria:
            self.etapa = "categoria"
            self._dizer(PERGUNTAS["categorias"].format(alimento=sem_categoria[0]["alimento"]))
            return

        if "perecíveis" in d.get("categorias", []) and not d.get("data_validade") and not self.validade_perguntada:
            self.validade_perguntada, self.etapa = True, "validade"
            self._dizer("Como há itens **perecíveis**, qual a **validade**? (ex.: *amanhã*, *15/11*, *em 3 dias*) "
                        "— ou responda *não sei*.")
            return

        if self.geo is None:
            self._localizar()
            if self.geo is None:
                return
        if self.geo["precisao"] == "aproximada" and not self.local_confirmado:
            self.etapa = "confirmando_local"
            self._dizer(f"📍 Encontrei este local: **{self.geo['endereco_formatado']}**. Está correto?")
            return

        self.etapa = "consentimento"
        self._dizer(self._resumo())

    def _localizar(self):
        d, achado = self.dados, None
        try:
            if d.get("cep"):
                achado = self.geo_api.geocodificar_cep(d["cep"])
            if not achado and d.get("endereco_texto"):
                achado = self.geo_api.geocodificar_endereco(d["endereco_texto"], contexto=self.contexto)
        except ValueError:
            achado = None
        if not achado:
            d.pop("cep", None)
            d.pop("endereco_texto", None)
            self.campo, self.etapa = "localizacao", "coletando"
            self._dizer("Não consegui localizar esse CEP/endereço. Confira e informe novamente o **CEP** "
                        "(ou o endereço completo, com cidade).")
            return
        self.geo = achado
        if achado["precisao"] != "aproximada":
            self._dizer(f"📍 Localizei: **{achado['endereco_formatado']}**")

    def _resumo(self):
        d, g = self.dados, self.geo
        linhas = ["Confira os dados da sua doação:", "", f"- 🥫 **Itens:** {d['descricao_alimento']}"]
        if d.get("categorias"):
            linhas.append(f"- 🏷️ **Categorias:** {', '.join(d['categorias'])}")
        if d.get("data_validade"):
            linhas.append(f"- 🗓️ **Validade:** {data_br(d['data_validade'])}")
        linhas += [f"- 👤 **Doador:** {d['doador_nome']} ({d['doador_email']})",
                   f"- 📍 **Retirada:** {g['endereco_formatado'] or d.get('cep') or d.get('endereco_texto')}"]
        for alerta in d.get("alertas", []):
            linhas.append(f"- ⚠️ {alerta}")
        linhas += ["", "Ao confirmar, você **autoriza o uso do seu nome e e-mail** apenas para registrar esta doação "
                       "e para contato da administração do MESAFARTAI (LGPD). Posso registrar?"]
        return "\n".join(linhas)

    # --- registro e oferta ------------------------------------------------------------------------------------------------
    def _registrar(self):
        d, g = self.dados, self.geo
        try:
            self.doacao_id, protocolo = db.registrar_doacao(
                d["doador_nome"], d["doador_email"], True, d["itens"], d.get("categorias"), d.get("descricao_alimento"),
                d.get("data_validade"), d.get("cep"), d.get("endereco_texto") or g.get("endereco_formatado"),
                g["latitude"], g["longitude"], self.mensagem_original)
        except ValueError as erro:
            self._zerar_fluxo()
            self._dizer(f"Não consegui registrar a doação: {erro}. Vamos tentar de novo? Me diga o que deseja doar.")
            return
        self.protocolo = protocolo
        self._dizer(f"✅ Doação registrada! Seu protocolo é **{protocolo}** — guarde-o para acompanhar depois.")
        self._apresentar(self.motor.oferecer_proxima_opcao(self.doacao_id))

    def _apresentar(self, r):
        if r["status"] in ("OFERECIDA", "PENDENTE"):
            self.etapa, self.oferta = "oferta", r
            titulo = "A ONG **mais próxima** compatível com a sua doação é:" if r["ordem"] == 1 \
                else "A **segunda opção** (a última que posso oferecer) é:"
            rodape = "Você aceita esta ONG?" if r["ordem"] == 2 or not r["ha_segunda_opcao"] \
                else "Você aceita esta ONG ou prefere ver a **segunda opção**?"
            self._dizer(f"{titulo}\n\n{formatar_ong(r['ong'])}  \n A cerca de **{km(r['distancia_km'])}** de você.\n\n{rodape}")
        else:
            motivo = r.get("motivo")
            self._dizer("Infelizmente, no momento **não há ONG compatível** com esta doação "
                        "(por localização ou restrições de alimentos). A sua doação ficou registrada como "
                        f"*sem destino* com o protocolo **{self.protocolo}**." if motivo == "sem_ong_compativel"
                        else "Não há uma segunda ONG compatível para sugerir. A doação ficou registrada como "
                             f"*sem destino* com o protocolo **{self.protocolo}**. Obrigado por querer ajudar!")
            self._zerar_fluxo()

    def responder_oferta(self, aceito):
        """Registra a resposta do doador à ONG sugerida (usada pelo texto e pelos botões)."""
        oferta = self.oferta
        db.responder_match(oferta["match_id"], aceito)
        protocolo = self.protocolo
        if aceito:
            self._dizer(" **Combinado!** Entre em contato com a ONG para combinar a entrega:\n\n"
                        f"{formatar_ong(oferta['ong'])}\n\nProtocolo: **{protocolo}**. Muito obrigado por ajudar "
                        "a combater a fome!")
            self._zerar_fluxo()
        elif oferta["ordem"] == 1:
            self._apresentar(self.motor.oferecer_proxima_opcao(self.doacao_id))
        else:
            self._dizer("Entendido. Como as duas opções não serviram, a doação ficou registrada como *sem destino* "
                        f"(protocolo **{protocolo}**). Obrigado por querer ajudar!")
            self._zerar_fluxo()
