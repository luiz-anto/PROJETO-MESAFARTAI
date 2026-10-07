# Escopo do Projeto – MESAFARTAI

O MESAFARTAI busca reduzir o desperdício de alimentos e facilitar sua distribuição para organizações que combatem a fome.
O público-alvo é dividido entre **Doadores** e **ONGs**.
Doadores poderão cadastrar alimentos disponíveis para doação.
ONGs poderão solicitar alimentos e consultar informações.
O sistema utilizará NLU para compreender mensagens enviadas pelo chat.
As principais intenções são: `cadastrar_doacao`, `solicitar_alimentos`, `consultar_status` e `fora_de_escopo`.
O sistema coletará informações como nome, alimento, quantidade e validade.
Também serão utilizados CEP, localização e telefone para facilitar o matchmaking.
Regex será utilizada para extrair quantidades, alimentos e prazos das mensagens.
Um mecanismo de Threshold/Fallback evitará respostas incorretas quando houver baixa confiança.
O KNN será utilizado para encontrar a ONG mais próxima da doação.
O banco SQLite armazenará usuários, doações e matches.
O projeto está alinhado à **ODS 2 – Fome Zero e Agricultura Sustentável**.
