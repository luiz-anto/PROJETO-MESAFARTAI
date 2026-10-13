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


Prompt usado para criar a logo:

"Crie um logotipo profissional, moderno e acolhedor para o projeto **MESAFARTAI – Logística e Inteligência Assistiva no Combate à Fome**. Utilize a foto de referência fornecida para transformar a pessoa em uma ilustração vetorial estilizada, preservando suas principais características visuais, como cabelo, barba, formato do rosto e sorriso. A pessoa deve aparecer sorrindo e fazendo o sinal de paz com a mão, integrada harmoniosamente ao símbolo da marca.

Combine a imagem da pessoa com uma tigela verde contendo alimentos frescos, como tomates, cenouras e folhas verdes, representando a doação de alimentos e o combate à fome. Acrescente mãos estilizadas em laranja e azul envolvendo a tigela, simbolizando acolhimento, solidariedade e cooperação. Inclua um ícone azul de chatbot ou inteligência artificial próximo à cabeça da pessoa, representando tecnologia e comunicação inteligente.

Utilize uma paleta de cores composta por verde, azul, laranja e branco. Abaixo do símbolo, escreva **MESAFARTAI** em letras grandes, modernas e em negrito, com “MESA” em verde e “FARTAI” em azul-escuro. Adicione o slogan “Logística e Inteligência Assistiva no Combate à Fome” em fonte menor, legível e elegante.

O resultado deve ter estilo de ilustração vetorial, contornos limpos, cores vibrantes, composição equilibrada e aparência profissional, adequada para um projeto acadêmico de tecnologia e impacto social. Utilize fundo branco, centralize os elementos e evite excesso de detalhes. Garanta que o nome MESAFARTAI e o slogan estejam escritos corretamente. A imagem deve funcionar como identidade visual para um sistema de doações de alimentos e assistência logística com inteligência artificial."

Passo 4: Script de Banco de Dados (src/database.py) 

Criar o script Python responsável por inicializar o banco de dados relacional SQLite3 (mesafartai.db) com as tabelas fundamentais e popular com dados de teste. 

O código deve contemplar a estrutura abaixo: 
