1.	Informe quantos número de árvores foram utilizados no motor NLU.
R: 80 arvores
2.	Informa qual o valor de threshold foi utilizado no processo de limiar de confiança
R: 60%
3.	Coloque o resultado da primeira execução
R: [NLU] Modelo Random Forest e Vetorizador TF-IDF treinados com sucesso!

--- BATERIA DE TESTES DE ESTRESSE NLU ---

Entrada: 'Tenho 30 kg de banana para doar'
Intenção: cadastrar_doacao | Confiança: 0.93
Retorno: Intenção 'cadastrar_doacao' identificada com 92.5% de confiança.

Entrada: 'Nossa instituição precisa de mantimentos'
Intenção: fallback | Confiança: 0.41
Retorno: Desculpe, não consegui entender com clareza o seu pedido. 
Você pode refazer a mensagem informando se deseja **doar alimentos** ou **solicitar doações para uma ONG**?

Entrada: 'Qual é a receita de bolo de cenoura?'
Intenção: fallback | Confiança: 0.49
Retorno: Desculpe, não consegui entender com clareza o seu pedido. 
Você pode refazer a mensagem informando se deseja **doar alimentos** ou **solicitar doações para uma ONG**?

Entrada: 'coisa comida doar la'
Intenção: fallback | Confiança: 0.42
Retorno: Desculpe, não consegui entender com clareza o seu pedido. 
Você pode refazer a mensagem informando se deseja **doar alimentos** ou **solicitar doações para uma ONG**?
4.	Descreva como você poderia fazer para os resultados de testes serem melhores, aumento o grau de confiança dos resultados
R:Colocando mais exemplos no treinamento
5.	Descreva por que o Random Forest foi o melhor método de Machine Learning para essa fase.
R:Por utilizar varias arvores de decisão