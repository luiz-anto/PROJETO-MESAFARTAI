"""
MESAFARTAI
Arquivo: src/app.py
"""

import streamlit as st
import pandas as pd
import sqlite3
from nlu import MotorNLU
from entities import ExtratorEntidades
from matchmaking import MotorMatchmaking

# Configuração da página do Streamlit
st.set_page_config(
    page_title="MESAFARTAI - Combate à Fome",
    page_icon=" ", # TODO: coloque um ícone aqui
    layout="wide"
)

# Inicializar instâncias dos motores
nlu = MotorNLU()
extrator = ExtratorEntidades()
matchmaker = MotorMatchmaking()

st.title("mesa farta ai") # TODO: escolha um título aqui
st.caption("projetasso") # TODO: escolha um subtítulo aqui

# Criação de abas para separar o Chatbot do Dashboard
aba_chat, aba_dashboard = st.tabs(["💬 Chatbot de Doações", "📊 Dashboard de Impacto Social"])

with aba_chat:
    st.subheader("Conversar com o Assistente de Doações")
    
    # Historico da sessão de conversa
    if "mensagens" not in st.session_state:
        st.session_state.mensagens = [
            {"role": "assistant", "content": "Olá seja bem-vindo"} # TODO: crie um mensagem de iniciar o chat
        ]

    # Exibir mensagens anteriores
    for msg in st.session_state.mensagens:
        st.chat_message(msg["role"]).write(msg["content"])

    # Entrada do Usuário
    if prompt := st.chat_input("Ex: Tenho 20 kg de arroz para doar hoje no centro"):
        st.session_state.mensagens.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

         # 1. Processar NLU (Chamando o método correto e capturando o dicionário)
        resultado_nlu = nlu.processar_mensagem(prompt)
        intencao = resultado_nlu["intencao"]
        confianca = resultado_nlu["confianca"]

        # 2. Resposta baseada na intenção
        # Nota: Seu nlu.py já converte para "fallback" se a confiança for menor que o limiar
        if intencao == "cadastrar_doacao":
            entidades = extrator.processar_texto(prompt)
            match = matchmaker.encontrar_ong_mais_proxima(-23.615, -46.785) # Coordenada exemplo
            
            resposta = f"**Doação Registrada com Sucesso!**\n\n" \
                       f"• **Item:** {entidades['alimento']}\n" \
                       f"• **Quantidade:** {entidades['quantidade_kg']} kg\n" \
                       f"• **Validade Estimada:** {entidades['data_validade']}\n\n"
            
            if match:
                resposta += f"**Match Logístico (KNN):** Encaminhado para **{match['ong_nome']}** (~{match['distancia_estimada']} km)."
            
        elif intencao == "solicitar_alimentos":
            resposta = "Entendemos seu pedido. Estamos buscando doações disponíveis próximas a você no banco de dados."
        else:
            # Caso caia em "fallback" ou "consultar_status" sem tratamento específico ainda
            resposta = resultado_nlu["resposta"]
with aba_dashboard:
    st.subheader("Indicadores Logísticos e Sociais em Tempo Real")
    
    # Conexão com o banco SQLite para alimentar o Dashboard
    conn = sqlite3.connect("mesafartai.db")
    df_ongs = pd.read_sql_query("SELECT * FROM usuarios WHERE tipo = 'ONG'", conn)
    conn.close()

    # Métricas Globais (KPIs)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de ONGs Ativas", len(df_ongs))
    col2.metric("Alimentos Arrecadados (kg)", "1,250 kg", "+150 kg esta semana")
    col3.metric("Refeições Estimadas Proporcionadas", "~2,500 refeições", "ODS 2")

    st.markdown("---")
    st.write("###  Unidades de Atendimento Cadastradas")
    st.dataframe(df_ongs[["id", "nome", "latitude", "longitude"]], use_container_width=True)
