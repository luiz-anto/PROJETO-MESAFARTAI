"""
app.py - Interface Streamlit do MESAFARTAI.

    ÁREA PÚBLICA (sem login)                      ÁREA ADMINISTRATIVA (login + senha)
    ├─ Quero doar (chatbot)                    ├─ Dashboard
    ├─ Acompanhar doação (protocolo)           ├─ ONGs (cadastrar, editar, desativar)
    └─ Como funciona                           └─ Doações (registro, detalhes, exportar)

Este arquivo é só front-end. As regras ficam nos módulos:
    chatbot.py (conversa) · nlu.py · entities.py · matchmaking.py · geocoding.py · database.py · auth.py

Para rodar:   streamlit run src/app.py
"""
import os
from datetime import timedelta
from types import SimpleNamespace

import pandas as pd
import streamlit as st

st.set_page_config(page_title="MESAFARTAI", page_icon="🍽️", layout="wide")


def segredo(chave, padrao=None):
    """Lê st.secrets sem quebrar quando o arquivo de segredos não existe."""
    try:
        return st.secrets.get(chave, padrao)
    except Exception:
        return padrao


# O Nominatim exige um User-Agent que identifique o app: precisa ser definido ANTES de importar geocoding.
_cfg_app = segredo("app", {}) or {}
if _cfg_app.get("nominatim_user_agent"):
    os.environ.setdefault("MESAFARTAI_USER_AGENT", str(_cfg_app["nominatim_user_agent"]))

import database as db  # noqa: E402
from auth import LimitadorTentativas, verificar_credenciais  # noqa: E402
from chatbot import Conversa, formatar_doacao  # noqa: E402
from entities import ExtratorEntidades  # noqa: E402
from geocoding import Geocodificador  # noqa: E402
from matchmaking import MotorMatchmaking  # noqa: E402
from nlu import MotorNLU  # noqa: E402

FUSO = "America/Sao_Paulo"
PRECISAO = {"numero": "endereço exato", "cep": "CEP (rua/bairro)", "aproximada": "aproximada",
            "demonstracao": "dado de demonstração"}


# ============================================================================
# Serviços compartilhados (carregados uma única vez por servidor)
# ============================================================================
@st.cache_resource(show_spinner="Preparando o assistente (na primeira vez pode demorar um pouco)...")
def servicos():
    db.inicializar_banco(inserir_seeds=bool(_cfg_app.get("inserir_ongs_demonstracao", True)))
    return SimpleNamespace(nlu=MotorNLU(), extrator=ExtratorEntidades(), geo=Geocodificador(),
                           motor=MotorMatchmaking(), limitador=LimitadorTentativas(max_falhas=5, bloqueio_s=60))


def garantir_banco():
    """Recria o banco se o arquivo sumir com o app em execução (o disco do Streamlit Cloud é efêmero)."""
    if not db.DB_PATH.exists():
        db.inicializar_banco(inserir_seeds=bool(_cfg_app.get("inserir_ongs_demonstracao", True)))


def flash(tipo, mensagem):
    """Mensagem que sobrevive ao st.rerun()."""
    st.session_state["_flash"] = (tipo, mensagem)


def mostrar_flash():
    if "_flash" in st.session_state:
        tipo, mensagem = st.session_state.pop("_flash")
        getattr(st, tipo)(mensagem)


# ============================================================================
# Chat do doador
# ============================================================================
def pagina_doar(s):
    _, centro, _ = st.columns([1, 3, 1])
    with centro:
        if "conversa" not in st.session_state:
            st.session_state.conversa = Conversa(s.nlu, s.extrator, s.geo, s.motor,
                                                 contexto_geografico=_cfg_app.get("contexto_geografico"))
        conversa = st.session_state.conversa

        st.title("💬 Quero doar alimentos")
        st.caption("Converse com o assistente: ele registra sua doação e indica a ONG compatível mais próxima. "
                   "Não é preciso criar conta.")

        for m in conversa.mensagens:
            with st.chat_message(m["role"], avatar="🍽️" if m["role"] == "assistant" else "🙂"):
                st.markdown(m["content"])

        botoes = conversa.botoes()
        if botoes:
            colunas = st.columns(len(botoes))
            for i, (rotulo, texto) in enumerate(botoes):
                if colunas[i].button(rotulo, key=f"atalho_{len(conversa.mensagens)}_{i}", width="stretch"):
                    enviar(conversa, texto)

        prompt = st.chat_input("Escreva sua mensagem...")
        if prompt:
            enviar(conversa, prompt)


def enviar(conversa, texto):
    with st.chat_message("user", avatar="🙂"):
        st.markdown(texto)
    with st.spinner("Pensando..."):
        conversa.enviar(texto)
    st.rerun()


# ============================================================================
# Acompanhar doação
# ============================================================================
def pagina_consulta():
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.title("🔎 Acompanhar doação")
        st.write("Informe o **protocolo** que você recebeu ao registrar a doação.")
        with st.form("consulta"):
            protocolo = st.text_input("Protocolo", placeholder="MF-20261103-0001")
            enviado = st.form_submit_button("Consultar", type="primary")
        if enviado:
            doacao = db.buscar_doacao_por_protocolo(protocolo)
            if doacao:
                st.markdown(formatar_doacao(doacao))
            else:
                st.error("Não encontrei nenhuma doação com esse protocolo. Confira o código e tente novamente.")


# ============================================================================
# Como funciona
# ============================================================================
def pagina_sobre():
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.title("ℹ️ Como funciona o MESAFARTAI")
        st.markdown("""
O **MESAFARTAI** conecta empresas e pessoas que têm **alimentos para doar** às **ONGs que combatem a fome**
mais próximas.

**Para quem quer doar**
1. Abra **💬 Quero doar** e conte, em linguagem natural, o que você tem (ex.: *"Tenho 10 kg de arroz"*).
2. O assistente pergunta o que faltar: nome, e-mail e CEP/endereço de retirada.
3. Ele indica a **ONG compatível mais próxima**. Você pode aceitar ou pedir **uma segunda opção**
   (nunca são oferecidas mais de duas).
4. Guarde o **protocolo** para acompanhar a doação em **🔎 Acompanhar doação**.

**Como a ONG é escolhida**
Primeiro eliminamos as ONGs que não aceitam o tipo de alimento (líquidos, perecíveis ou congelados). Depois um
algoritmo de vizinhos mais próximos (**KNN**, com distância de Haversine) escolhe as mais perto de você.

**Para ONGs**
As ONGs são cadastradas pela administração do MESAFARTAI e passam a receber doações sem nenhuma outra etapa.
Quer participar? Entre em contato com a administração.

**Seus dados (LGPD)**
Nome e e-mail só são gravados **depois do seu consentimento** e servem para registrar a doação e para contato da
administração. A consulta por protocolo **não mostra** seus dados pessoais.

**Créditos:** endereços e mapas usam dados do © OpenStreetMap contributors, BrasilAPI e ViaCEP.
""")


# ============================================================================
# Administração
# ============================================================================
def pagina_admin(s):
    if not st.session_state.get("admin_ok"):
        return tela_login(s)

    topo1, topo2 = st.columns([5, 1])
    topo1.title("🔐 Administração")
    if topo2.button("Sair", width="stretch"):
        st.session_state.admin_ok = False
        st.rerun()
    mostrar_flash()

    aba_dash, aba_ongs, aba_doacoes = st.tabs(["📊 Dashboard", "🏢 ONGs", "📋 Doações"])
    with aba_dash:
        dashboard()
    with aba_ongs:
        aba_gestao_ongs(s)
    with aba_doacoes:
        aba_registro_doacoes()


def tela_login(s):
    _, centro, _ = st.columns([1, 1, 1])
    with centro:
        st.title("🔐 Administração")
        cfg = segredo("admin")
        if not cfg or not cfg.get("usuario") or not cfg.get("senha_hash"):
            st.error("A área administrativa está **desativada**: não há credenciais configuradas.")
            st.markdown("Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml`, gere o hash com "
                        "`python scripts/gerar_hash_senha.py` e reinicie o app.")
            return
        espera = s.limitador.segundos_bloqueado()
        if espera:
            st.warning(f"Muitas tentativas incorretas. Aguarde {espera}s para tentar novamente.")
            return
        with st.form("login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            entrou = st.form_submit_button("Entrar", type="primary", width="stretch")
        if entrou:
            if verificar_credenciais(usuario, senha, cfg["usuario"], cfg["senha_hash"]):
                s.limitador.registrar_sucesso()
                st.session_state.admin_ok = True
                st.rerun()
            s.limitador.registrar_falha()
            st.error("Usuário ou senha incorretos.")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def _para_local(serie_utc):
    dt = pd.to_datetime(serie_utc, utc=True)
    try:
        return dt.dt.tz_convert(FUSO)
    except Exception:
        return dt


def dashboard():
    doacoes = pd.DataFrame(db.listar_doacoes())
    itens = pd.DataFrame(db.listar_itens())
    matches = pd.DataFrame(db.listar_matches())
    ongs = pd.DataFrame(db.listar_ongs(apenas_ativas=False))
    ongs_ativas = ongs[ongs["ativa"] == 1] if not ongs.empty else ongs

    if doacoes.empty:
        st.info("Ainda não há doações registradas. Quando houver, os indicadores aparecem aqui.")
        mapa_ongs(ongs_ativas, pd.DataFrame())
        return

    periodo = st.segmented_control("Período", ["Últimos 7 dias", "Últimos 30 dias", "Tudo"], default="Tudo",
                                   key="dash_periodo") or "Tudo"
    doacoes["data"] = _para_local(doacoes["criado_em"])
    if periodo != "Tudo":
        dias = 7 if "7" in periodo else 30
        limite = pd.Timestamp.now(tz=doacoes["data"].dt.tz) - timedelta(days=dias)
        doacoes = doacoes[doacoes["data"] >= limite]
    if doacoes.empty:
        st.info("Nenhuma doação neste período.")
        return
    protocolos = set(doacoes["protocolo"])
    if not itens.empty:
        itens = itens[itens["protocolo"].isin(protocolos)]
    if not matches.empty:
        matches = matches[matches["protocolo"].isin(protocolos)]

    total = len(doacoes)
    aceitas = int(doacoes["status"].isin(["ACEITA", "COLETADA"]).sum())
    sem_destino = int((doacoes["status"] == "SEM_DESTINO").sum())
    dist_media = matches.loc[matches["status"] == "ACEITO", "distancia_km"].mean() if not matches.empty else float("nan")
    kg = itens.loc[itens["unidade"] == "kg", "quantidade"].sum() if not itens.empty else 0

    m = st.columns(5)
    m[0].metric("Doações registradas", total)
    m[1].metric("Aceitas pelo doador", aceitas, f"{aceitas / total:.0%} do total", delta_color="off")
    m[2].metric("Sem destino", sem_destino, f"{sem_destino / total:.0%} do total", delta_color="off")
    m[3].metric("Distância média (aceitas)", "—" if pd.isna(dist_media) else f"{dist_media:.1f} km".replace(".", ","))
    m[4].metric("Itens em kg", f"{kg:g} kg", help="Soma só os itens informados em kg; litros, caixas e "
                                                  "dúzias não são somados porque não são comparáveis.")
    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Doações por dia")
        por_dia = doacoes["data"].dt.strftime("%d/%m").value_counts().sort_index()
        st.bar_chart(por_dia)
    with c2:
        st.subheader("Doações por situação")
        st.bar_chart(doacoes["status"].value_counts())

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Itens por categoria")
        if itens.empty:
            st.caption("Sem itens no período.")
        else:
            cat = itens["categorias"].fillna("sem categoria especial").str.split(", ").explode().value_counts()
            st.bar_chart(cat)
    with c4:
        st.subheader("ONGs que mais receberam")
        if matches.empty or not (matches["status"] == "ACEITO").any():
            st.caption("Nenhuma doação aceita ainda.")
        else:
            st.bar_chart(matches.loc[matches["status"] == "ACEITO", "ong_nome"].value_counts())

    c5, c6 = st.columns(2)
    with c5:
        st.subheader("Aceite por opção oferecida")
        if matches.empty:
            st.caption("Ainda não há opções oferecidas.")
        else:
            resp = matches[matches["status"].isin(["ACEITO", "RECUSADO"])]
            tab = resp.groupby("ordem")["status"].agg(respondidas="count",
                                                      aceitas=lambda x: int((x == "ACEITO").sum())).reset_index()
            tab["taxa de aceite"] = (tab["aceitas"] / tab["respondidas"]).map("{:.0%}".format)
            tab["ordem"] = tab["ordem"].map({1: "1ª opção (mais próxima)", 2: "2ª opção"})
            st.dataframe(tab.rename(columns={"ordem": "opção"}), width="stretch", hide_index=True)
    with c6:
        st.subheader("Demanda não atendida")
        sd = doacoes[doacoes["status"] == "SEM_DESTINO"]
        if sd.empty:
            st.caption("Nenhuma doação ficou sem destino. 🎉")
        else:
            st.caption("Categorias das doações sem destino: ajudam a decidir que tipo de ONG cadastrar.")
            it = itens[itens["protocolo"].isin(sd["protocolo"])] if not itens.empty else itens
            cat = it["categorias"].fillna("sem categoria especial").str.split(", ").explode().value_counts() \
                if not it.empty else pd.Series(dtype=int)
            st.dataframe(cat.rename_axis("categoria").reset_index(name="itens"), width="stretch", hide_index=True)

    if not itens.empty:
        st.subheader("Itens por unidade")
        tab = itens.groupby(itens["unidade"].fillna("sem unidade"))["id"].count().rename("itens").reset_index()
        st.dataframe(tab.rename(columns={"unidade": "unidade"}), width="stretch", hide_index=True)

    mapa_ongs(ongs_ativas, doacoes)


def mapa_ongs(ongs_ativas, doacoes):
    pontos = []
    if not ongs_ativas.empty:
        pontos.append(pd.DataFrame({"lat": ongs_ativas["latitude"], "lon": ongs_ativas["longitude"],
                                    "color": "#2e7d32", "size": 120}))
    if not doacoes.empty and doacoes["latitude"].notna().any():
        d = doacoes.dropna(subset=["latitude", "longitude"])
        pontos.append(pd.DataFrame({"lat": d["latitude"], "lon": d["longitude"], "color": "#ef6c00", "size": 70}))
    if pontos:
        st.subheader("Mapa: ONGs (verde) e doações (laranja)")
        st.map(pd.concat(pontos), latitude="lat", longitude="lon", color="color", size="size")
        st.caption("Mapa: © OpenStreetMap contributors.")


# ---------------------------------------------------------------------------
# ONGs
# ---------------------------------------------------------------------------
def aba_gestao_ongs(s):
    sub_lista, sub_nova, sub_editar = st.tabs(["📋 Cadastradas", "➕ Cadastrar ONG", "✏️ Editar / desativar"])

    with sub_lista:
        ongs = db.listar_ongs(apenas_ativas=False)
        if not ongs:
            st.info("Nenhuma ONG cadastrada.")
        else:
            df = pd.DataFrame(ongs)
            df["situação"] = df["ativa"].map({1: "ativa", 0: "inativa"})
            df["endereço"] = df.apply(lambda r: ", ".join(str(x) for x in (r["logradouro"], r["numero"], r["bairro"],
                                                                           r["cidade"]) if pd.notna(x) and x) or "—",
                                      axis=1)
            st.dataframe(df[["nome", "tipo", "endereço", "cep", "telefone", "email", "restricoes_alimentares",
                             "situação"]].rename(columns={"restricoes_alimentares": "não aceita"}),
                         width="stretch", hide_index=True)

    with sub_nova:
        st.caption("Somente a administração cadastra ONGs. Após o cadastro, a ONG passa a receber doações "
                   "automaticamente, sem nenhum aviso ou acompanhamento.")
        formulario_ong(s, modo="nova")

    with sub_editar:
        ongs = db.listar_ongs(apenas_ativas=False)
        if not ongs:
            st.info("Cadastre uma ONG primeiro.")
            return
        nomes = {o["id"]: o["nome"] + ("" if o["ativa"] else " (inativa)") for o in ongs}
        # a seleção guarda o ID (e não a posição): continua na mesma ONG depois de salvar, mesmo que a ordem mude
        escolhida_id = st.selectbox("ONG", list(nomes), format_func=nomes.get, key="editar_escolha")
        escolhida = next(o for o in ongs if o["id"] == escolhida_id)
        formulario_ong(s, modo="editar", ong=escolhida)
        st.divider()
        if escolhida["ativa"]:
            st.caption("Desativar **não apaga** a ONG nem o histórico: ela só deixa de receber novas doações.")
            if st.button("🚫 Desativar esta ONG", key=f"desativar_{escolhida['id']}"):
                db.alterar_status_ong(escolhida["id"], False)
                flash("success", f"ONG “{escolhida['nome']}” desativada.")
                st.rerun()
        elif st.button("✅ Reativar esta ONG", key=f"reativar_{escolhida['id']}"):
            db.alterar_status_ong(escolhida["id"], True)
            flash("success", f"ONG “{escolhida['nome']}” reativada.")
            st.rerun()


def formulario_ong(s, modo, ong=None):
    """Formulário de cadastro/edição. O endereço só é salvo depois de localizado e confirmado."""
    versao = st.session_state.setdefault(f"ong_versao_{modo}", 0)

    def chave(nome):
        return f"{modo}_{ong['id'] if ong else 'novo'}_{versao}_{nome}"

    ini = ong or {}
    nome = st.text_input("Nome da ONG *", value=ini.get("nome", ""), key=chave("nome"))
    tipo = st.selectbox("Tipo de ONG *", db.TIPOS_ONG, key=chave("tipo"),
                        index=db.TIPOS_ONG.index(ini["tipo"]) if ini.get("tipo") in db.TIPOS_ONG else 0)
    c1, c2 = st.columns([2, 1])
    cep = c1.text_input("CEP *", value=ini.get("cep", ""), placeholder="00000-000", key=chave("cep"))
    numero = c2.text_input("Número", value=ini.get("numero") or "", key=chave("numero"))
    c3, c4 = st.columns(2)
    telefone = c3.text_input("Telefone", value=ini.get("telefone") or "", key=chave("tel"))
    email = c4.text_input("E-mail", value=ini.get("email") or "", key=chave("email"),
                          help="Informe ao menos um contato (telefone ou e-mail).")
    restricoes = st.multiselect(
        "Restrições alimentares: a ONG **não** aceita…", db.CATEGORIAS_ALIMENTO,
        default=sorted(db.restricoes_como_conjunto(ini.get("restricoes_alimentares", ""))),
        format_func=lambda c: db.ROTULOS_RESTRICAO[c].replace("Não aceitamos ", ""), key=chave("restr"),
        help="Deixe em branco se não houver restrições: será gravado como “sem restrições”.")
    with st.expander("Informações opcionais"):
        horario = st.text_input("Horário de recebimento", value=ini.get("horario_recebimento") or "",
                                placeholder="Seg a sex, 8h às 17h", key=chave("horario"))
        capacidade = st.number_input("Capacidade (kg)", min_value=0.0, value=float(ini.get("capacidade_kg") or 0),
                                     key=chave("cap"), help="0 = não informado")
        obs = st.text_area("Observações", value=ini.get("observacoes") or "", key=chave("obs"))

    # --- localização -------------------------------------------------------------
    atual = (cep.strip(), numero.strip())
    if st.button("📍 Localizar endereço", key=chave("localizar")):
        try:
            with st.spinner("Consultando o CEP..."):
                r = s.geo.geocodificar_cep(cep, numero.strip() or None)
            if r is None:
                st.error("Não encontrei esse CEP. Confira o número ou tente novamente em instantes.")
            else:
                st.session_state[chave("geo")] = {"consulta": atual, "r": r}
        except ValueError as erro:
            st.error(str(erro))
    estado = st.session_state.get(chave("geo"))
    localizado = bool(estado and estado["consulta"] == atual)
    inalterado = False
    if ong:
        try:
            inalterado = (db.normalizar_cep(cep), numero.strip()) == (ong["cep"], (ong.get("numero") or ""))
        except ValueError:
            inalterado = False

    if localizado:
        r = estado["r"]
        st.success(f"📍 {r['endereco_formatado'] or 'Local encontrado'} · precisão: {PRECISAO.get(r['precisao'], r['precisao'])}")
        if r["fonte"] == "demonstracao":
            st.warning("Coordenadas de **demonstração** (sem internet). Use apenas para testes.")
        st.map(pd.DataFrame({"lat": [r["latitude"]], "lon": [r["longitude"]]}), zoom=15, height=220)
        st.caption("Confira se o ponto no mapa está correto antes de salvar. Mapa: © OpenStreetMap contributors.")
    elif estado:
        st.info("O CEP ou o número mudou: clique em **Localizar endereço** novamente.")
    elif inalterado:
        st.caption("Endereço atual mantido. Altere o CEP/número e localize de novo apenas se precisar mudá-lo.")

    pode_salvar = localizado or inalterado
    if not pode_salvar:
        st.caption("👆 Localize e confirme o endereço para liberar o botão de salvar.")
    rotulo = "💾 Cadastrar ONG" if modo == "nova" else "💾 Salvar alterações"
    if st.button(rotulo, type="primary", disabled=not pode_salvar, key=chave("salvar")):
        campos = dict(telefone=telefone.strip() or None, email=email.strip() or None, numero=numero.strip() or None,
                      horario_recebimento=horario.strip() or None,
                      capacidade_kg=capacidade or None, observacoes=obs.strip() or None)
        if localizado:
            r = estado["r"]
            campos.update(latitude=r["latitude"], longitude=r["longitude"], logradouro=r["logradouro"],
                          bairro=r["bairro"], cidade=r["cidade"], uf=r["uf"])
        try:
            if modo == "nova":
                db.cadastrar_ong(nome=nome, tipo=tipo, cep=cep, restricoes=restricoes, **campos)
                flash("success", f"ONG “{nome.strip()}” cadastrada! Ela já pode receber doações.")
            else:
                db.editar_ong(ong["id"], nome=nome.strip(), tipo=tipo, cep=cep, restricoes_alimentares=restricoes,
                              **campos)
                flash("success", f"ONG “{nome.strip()}” atualizada.")
        except ValueError as erro:
            st.error(str(erro))
        else:
            st.session_state[f"ong_versao_{modo}"] = versao + 1
            st.rerun()


# ---------------------------------------------------------------------------
# Doações
# ---------------------------------------------------------------------------
def aba_registro_doacoes():
    doacoes = pd.DataFrame(db.listar_doacoes())
    if doacoes.empty:
        st.info("Ainda não há doações registradas.")
        return

    doacoes["registrada em"] = _para_local(doacoes["criado_em"]).dt.strftime("%d/%m/%Y %H:%M")
    f1, f2 = st.columns([2, 3])
    status = f1.multiselect("Situação", sorted(doacoes["status"].unique()), default=sorted(doacoes["status"].unique()))
    busca = f2.text_input("Buscar", placeholder="protocolo, doador, e-mail ou alimento")
    vis = doacoes[doacoes["status"].isin(status)]
    if busca.strip():
        alvo = (vis["protocolo"].fillna("") + " " + vis["doador_nome"] + " " + vis["doador_email"] + " "
                + vis["descricao_alimento"]).str.lower()
        vis = vis[alvo.str.contains(busca.strip().lower(), regex=False)]

    tabela = vis[["protocolo", "registrada em", "doador_nome", "doador_email", "descricao_alimento", "categorias",
                  "data_validade", "status", "ong_aceita", "distancia_aceita"]].rename(columns={
        "doador_nome": "doador", "doador_email": "e-mail", "descricao_alimento": "itens",
        "data_validade": "validade", "ong_aceita": "ONG", "distancia_aceita": "km"})
    st.dataframe(tabela, width="stretch", hide_index=True)
    st.download_button("⬇️ Baixar CSV (contém dados pessoais: use com cuidado)",
                       tabela.to_csv(index=False).encode("utf-8-sig"), "doacoes_mesafartai.csv", "text/csv")

    if vis.empty:
        return
    st.subheader("Detalhes da doação")
    protocolo = st.selectbox("Protocolo", vis["protocolo"].tolist())
    d = db.buscar_doacao_por_protocolo(protocolo)
    if d:
        a, b = st.columns(2)
        a.markdown(f"**Doador:** {d['doador_nome']} · {d['doador_email']}  \n"
                   f"**Local:** {d['endereco_texto'] or d['cep'] or '—'}  \n"
                   f"**Validade:** {d['data_validade'] or 'não informada'}  \n"
                   f"**Situação:** {d['status']}")
        b.dataframe(pd.DataFrame(d["itens"]).rename(columns={"alimento": "alimento", "categorias": "categorias"}),
                    width="stretch", hide_index=True)
        if d["matches"]:
            st.markdown("**Opções oferecidas ao doador**")
            st.dataframe(pd.DataFrame(d["matches"])[["ordem", "ong_nome", "distancia_km", "status"]],
                         width="stretch", hide_index=True)
        if d["status"] == "ACEITA" and st.button("📦 Marcar como coletada", key=f"coletada_{d['id']}"):
            db.marcar_coletada(d["id"])
            flash("success", f"Doação {d['protocolo']} marcada como coletada.")
            st.rerun()


# ============================================================================
# Navegação
# ============================================================================
def main():
    s = servicos()
    garantir_banco()
    st.sidebar.title("🍽️ MESAFARTAI")
    st.sidebar.caption("Conectando quem tem alimento a quem combate a fome.")
    pagina = st.sidebar.radio("Menu", ["💬 Quero doar", "🔎 Acompanhar doação", "ℹ️ Como funciona", "🔐 Administração"],
                              key="menu")
    if pagina == "💬 Quero doar" and st.sidebar.button("🔄 Nova conversa", width="stretch"):
        st.session_state.pop("conversa", None)
        st.rerun()

    if pagina == "💬 Quero doar":
        pagina_doar(s)
    elif pagina == "🔎 Acompanhar doação":
        pagina_consulta()
    elif pagina == "ℹ️ Como funciona":
        pagina_sobre()
    else:
        pagina_admin(s)


main()
