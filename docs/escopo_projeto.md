3. ESCOPO GERAL DO PROJETO & REQUISITOS TÉCNICOS 

O ecossistema do MESAFARTAI é composto por 4 grandes pilares tecnológicos desenvolvidos 100% em Python: 

Interface Conversacional (Front-End - Streamlit): 

Chat interativo para cadastro de doações e consultas de ONGs. 

Alternância de perfil na barra lateral ([Sou Doador | Sou ONG]). 

Motor de NLU & Trava de Segurança (Back-End - Scikit-Learn / Spacy): 

Classificação de intenções (cadastrar_doacao, solicitar_alimentos, consultar_status, fora_de_escopo). 

Mecanismo de Threshold (ex: < 0.60) com resposta de Fallback amigável quando a frase for ambígua. 

Extração de Entidades (Regex): 

Captura automática de quantidades (kg, caixas, unidades), tipos de alimentos e prazos de validade (hoje, amanhã, 18h). 

Matchmaking Logístico & Banco de Dados (KNN + SQLite3): 

Algoritmo KNN para calcular o match perfeito entre a oferta do doador e a ONG receptora mais próxima. 

Banco de dados SQLite3 para persistência de doadores, receptores, doações e histórico de coletas. 


Passo 4: Script de Banco de Dados (src/database.py) 

Criar o script Python responsável por inicializar o banco de dados relacional SQLite3 (mesafartai.db) com as tabelas fundamentais e popular com dados de teste. 

O código deve contemplar a estrutura abaixo: 
