"""
MESAFARTAI - Módulo de Processamento de Linguagem Natural (NLU)
Arquivo: src/nlu.py
Descrição: Pipeline com TF-IDF, Random Forest e Trava de Segurança por Threshold.
"""

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier

# 1. BASE DE DADOS DE TREINO (Dataset de Intenções)
frases_treino = [
    # Intenção: cadastrar_doacao
    "Quero doar 10 kg de arroz",
    "Posso contribuir com 15 litros de leite",
    "Tenho 30 kg de banana para doar",
    "Tenho 20 caixas de tomate para doar hoje",
    "Gostaria de oferecer refeições prontas para abrigo",
    "Tenho sobra de alimentos do meu restaurante",
    "Posso entregar 5 kg de feijão perto da validade",
    "Queremos cadastrar uma doação de legumes",
    
    # Intenção: solicitar_alimentos
    "Nossa ONG precisa de doações de alimentos",
    "Estamos buscando marmitas e cestas básicas urgentemente",
    "Quais doações estão disponíveis para retirada na região?",
    "Preciso de suprimentos para o abrigo comunitário",
    "Como faço para solicitar comida para nossa cozinha social?",
    
    # Intenção: consultar_status
    "Onde está o meu pedido de doação?",
    "Gostaria de ver o histórico de matches das ONGs",
    "Qual o status do voluntário que vai retirar os alimentos?",
    "Como consultar se a doação já foi entregue?",
    
    # Intenção: fora_de_escopo (Frases aleatórias / Ruídos)
    "Qual é a previsão do tempo para hoje?",
    "Gosto de assistir filmes de ficção científica",
    "Quem venceu o jogo de futebol ontem?",
    "Como faço para trocar a senha da minha conta bancária?"
]

intencoes_treino = [
    "cadastrar_doacao", "cadastrar_doacao", "cadastrar_doacao", 
    "cadastrar_doacao", "cadastrar_doacao", "cadastrar_doacao", "cadastrar_doacao", "cadastrar_doacao",
    
    "solicitar_alimentos", "solicitar_alimentos", "solicitar_alimentos", 
    "solicitar_alimentos", "solicitar_alimentos",
    
    "consultar_status", "consultar_status", "consultar_status", "consultar_status",
    
    "fora_de_escopo", "fora_de_escopo", "fora_de_escopo", "fora_de_escopo"
]

class MotorNLU:
    def __init__(self, limiar_threshold=0.60):
        self.limiar_threshold = limiar_threshold
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        self.classifier = RandomForestClassifier(n_estimators=80, random_state=42)
        self._treinar_modelo()

    def _treinar_modelo(self):
        """Vetoriza os textos e treina o classificador Random Forest."""
        X_vec = self.vectorizer.fit_transform(frases_treino)
        self.classifier.fit(X_vec, intencoes_treino)
        print(" [NLU] Modelo Random Forest e Vetorizador TF-IDF treinados com sucesso!")

    def processar_mensagem(self, texto_usuario):
        """
        Processa uma mensagem do usuário e retorna a intenção, 
        o nível de confiança e a decisão de Fallback.
        """
        # 1. Vetorização da entrada
        vetor_texto = self.vectorizer.transform([texto_usuario])
        
        # 2. Predição de probabilidade via Random Forest
        probabilidades = self.classifier.predict_proba(vetor_texto)[0]
        max_confianca = float(np.max(probabilidades))
        indice_classe = int(np.argmax(probabilidades))
        intencao_predita = self.classifier.classes_[indice_classe]
        
        # 3. Trava de Segurança por Threshold
        if max_confianca < self.limiar_threshold or intencao_predita == "fora_de_escopo":
            return {
                "intencao": "fallback",
                "confianca": max_confianca,
                "resposta": (
                    "Desculpe, não consegui entender com clareza o seu pedido. \n"
                    "Você pode refazer a mensagem informando se deseja **doar alimentos** "
                    "ou **solicitar doações para uma ONG**?"
                )
            }
        
        return {
            "intencao": intencao_predita,
            "confianca": max_confianca,
            "resposta": f"Intenção '{intencao_predita}' identificada com {max_confianca*100:.1f}% de confiança."
        }

# --- TESTE DO MÓDULO EM TEMPO DE EXECUÇÃO ---
if __name__ == "__main__":
    nlu = MotorNLU(limiar_threshold=0.60)
    
    # Bateria de testes automatizados
    frases_teste = [
        "Tenho 30 kg de banana para doar",
        "Nossa instituição precisa de mantimentos",
        "Qual é a receita de bolo de cenoura?", # Frase fora de escopo
        "coisa comida doar la" # Frase confusa / ambígua
    ]
    
    print("\n--- BATERIA DE TESTES DE ESTRESSE NLU ---")
    for frase in frases_teste:
        resultado = nlu.processar_mensagem(frase)
        print(f"\nEntrada: '{frase}'")
        print(f"Intenção: {resultado['intencao']} | Confiança: {resultado['confianca']:.2f}")
        print(f"Retorno: {resultado['resposta']}")