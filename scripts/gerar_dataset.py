"""
gerar_dataset.py - Gera data/dataset_intencoes.csv (treino) e data/dataset_teste.csv (avaliação).

Estratégia (boa prática de ML para ensinar em aula):
  * TREINO = frases escritas à mão + frases geradas por templates (com ruído: sem acento,
    erros de digitação, minúsculas).
  * TESTE  = frases escritas à mão, diferentes do treino. Nunca misturamos com o treino,
    senão a acurácia fica "inflada" (vazamento de dados / data leakage).

Uso:  python scripts/gerar_dataset.py
"""
import csv
import random
import unicodedata
from collections import Counter
from pathlib import Path

random.seed(42)
RAIZ = Path(__file__).resolve().parent.parent
PASTA_DATA = RAIZ / "data"

# =============================================================================
# 1. FRASES ESCRITAS À MÃO (TREINO)
# =============================================================================
MANUAL = {
    "cadastrar_doacao": [
        "Quero doar 10 kg de arroz", "Posso contribuir com 15 litros de leite",
        "Tenho 30 kg de banana para doar", "Tenho 20 caixas de tomate para doar hoje",
        "Gostaria de oferecer refeições prontas para um abrigo",
        "Tenho sobra de alimentos do meu restaurante",
        "Posso entregar 5 kg de feijão perto da validade",
        "Queremos cadastrar uma doação de legumes", "quero fazer uma doação",
        "Gostaria de doar alimentos", "tenho comida pra doar", "quero doar comida",
        "Sobrou muita comida aqui na empresa, queria doar", "Vou doar uns pães de ontem",
        "Minha padaria quer doar pães todo dia", "Temos excedente de hortifrúti para doação",
        "Preciso doar 200 marmitas que sobraram do evento", "dá pra doar 3 caixas de iogurte?",
        "Quero doar cestas básicas", "Gostaria de registrar uma doação de alimentos",
        "posso doar frutas?", "Tenho verduras que não vou conseguir vender, posso doar?",
        "Quero ajudar doando alimentos", "como posso doar 50 kg de batata?",
        "Estou com 100 pacotes de macarrão para doar", "doação de 40 latas de milho e ervilha",
        "Quero doar uma carga de frutas que está perto de vencer",
        "Nossa empresa deseja doar o excedente da produção",
        "queria doar umas cestas de natal", "tenho 12 dúzias de ovos para doação",
        "vou doar leite e biscoitos", "quero fazer uma doação de água mineral",
        "Posso doar o que sobrou do buffet de ontem?", "Tenho alimentos não perecíveis para doar",
        "doar 80 kg de frango congelado", "meu mercado tem produtos perto do vencimento para doar",
        "Gostaria de contribuir com a campanha doando comida", "quero doar!",
        "Preciso me desfazer de alimentos e prefiro doar",
        "Nosso condomínio fez uma campanha e vamos doar os alimentos",
        "qro doar comida", "to com pao e leite pra doar", "vc consegue receber uma doação minha?",
        "tenho uns pães pra doa", "queria doa umas frutas",
    ],
    "solicitar_alimentos": [
        "Nossa ONG precisa de doações de alimentos",
        "Estamos buscando marmitas e cestas básicas urgentemente",
        "Quais doações estão disponíveis para retirada na região?",
        "Preciso de suprimentos para o abrigo comunitário",
        "Como faço para solicitar comida para nossa cozinha social?",
        "Somos uma ONG e queremos receber doações", "Nossa instituição precisa de mantimentos",
        "Quero cadastrar minha ONG para receber alimentos", "Como minha ONG recebe doações?",
        "Estamos com falta de alimentos no abrigo", "Precisamos de arroz e feijão para a nossa cozinha",
        "Queria pedir alimentos para a minha comunidade", "Tem comida disponível para a gente buscar?",
        "Nossa associação de moradores precisa de cestas básicas",
        "Preciso de comida, estou passando necessidade", "Minha família está sem comida, como consigo ajuda?",
        "Quero receber doações de alimentos", "Como faço para a minha ONG entrar no sistema?",
        "A nossa cozinha comunitária está sem estoque", "Precisamos de leite para as crianças do abrigo",
        "Quero pedir uma cesta básica", "Existe alguma doação para retirar hoje?",
        "Gostaria de receber alimentos para o nosso projeto social",
        "Sou de uma instituição e precisamos de ajuda com alimentos",
        "Onde peço comida para o meu grupo de voluntários?", "Quero solicitar doação para um asilo",
        "Nosso banco de alimentos precisa de reposição", "Como cadastro minha entidade para receber comida?",
        "estamos precisando de alimentos urgente", "preciso de ajuda com comida",
    ],
    "consultar_status": [
        "Onde está o meu pedido de doação?", "Gostaria de ver o histórico das minhas doações",
        "Qual o status da minha doação?", "Como consultar se a doação já foi entregue?",
        "Quero acompanhar minha doação", "Minha doação foi aceita?", "Já tem ONG para a minha doação?",
        "Qual o protocolo da minha doação?", "Quero consultar o protocolo",
        "Tenho um protocolo, como vejo a situação?",
        "como está a minha doação", "consultar status da doação", "Cadê minha doação?",
        "A ONG já recebeu o que eu doei?", "Quero saber o andamento da doação que fiz ontem",
        "Preciso verificar uma doação que cadastrei", "me diz a situação da doação",
        "Fiz uma doação semana passada, como está?", "ver andamento", "status da doação por favor",
        "Qual ONG ficou com a minha doação?", "Quero saber para onde foi minha doação",
        "Consegue ver o meu protocolo?", "Acompanhar doação", "Minha doação ainda está pendente?",
        "Como sei se minha doação foi aceita pela ONG?", "histórico do meu cadastro de doação",
        "Gostaria de checar uma doação", "tenho um código de acompanhamento",
        "Já foi retirada a minha doação?",
    ],
    "aceitar_opcao": [
        "Aceito", "aceito sim", "Sim", "sim, pode ser", "Pode ser essa mesmo", "Quero essa ONG",
        "Fechado", "Ok, pode confirmar", "Confirmo", "Perfeito, vou levar lá", "Beleza, aceito",
        "Tá ótimo, pode ser", "pode mandar", "isso mesmo", "Essa serve", "ótimo, pode ser essa",
        "Combinado", "concordo", "Pode confirmar essa opção", "Gostei, vou doar para essa",
        "Opção 1 está ótima", "Fico com a primeira", "sim, aceito a ONG sugerida", "ok", "bora",
        "Está bom, aceito", "tudo certo, pode ser", "positivo", "Eu aceito essa ONG", "uhum, pode ser",
    ],
    "recusar_opcao": [
        "Não aceito, quero a segunda opção", "Prefiro a outra", "Tem outra mais perto?",
        "Essa é muito longe", "Mostra a segunda opção", "Não posso levar até lá",
        "Próxima opção, por favor", "Quero ver a outra ONG", "Não", "não, obrigado",
        "Recuso essa opção", "Nao quero essa, tem outra?", "Prefiro a segunda", "Pode mostrar a outra",
        "Essa não dá, fica longe demais", "Não consigo ir nessa", "Troca por outra ONG",
        "outra opção", "Não fico com essa", "quero a segunda ONG", "Não serve, mostra a próxima",
        "Não, prefiro outra", "negativo", "não, quero outra opção", "Essa ONG não me atende",
        "Tem alguma outra?", "Passo essa, qual a outra?", "melhor a outra", "Não é essa que eu quero",
        "recuso", "Não aceito", "Não aceito essa ONG", "Eu rejeito essa opção", "Rejeito a sugestão",
        "Descarto essa, qual a outra?", "Não aceito, tem outra?", "nao aceito",
    ],
    "saudacao_ajuda": [
        "Oi", "Olá", "Bom dia", "Boa tarde", "Boa noite", "E aí", "Opa", "oie", "Olá, tudo bem?",
        "oi, tudo bem?", "Preciso de ajuda", "Como funciona?", "O que você faz?",
        "Como esse sistema funciona?", "Quem é você?", "O que é o MESAFARTAI?", "Me ajuda?", "ajuda",
        "Como usar o chat?", "Oi, pode me ajudar?", "olá, queria entender como funciona", "Hello",
        "Salve", "bom dia, tudo certo?", "Para que serve esse chat?", "Como funciona a doação por aqui?",
        "menu", "Início", "começar", "Pode me explicar o sistema?",
    ],
    "fora_de_escopo": [
        "Qual é a previsão do tempo para hoje?", "Gosto de assistir filmes de ficção científica",
        "Quem venceu o jogo de futebol ontem?", "Como faço para trocar a senha da minha conta bancária?",
        "Qual é a receita de bolo de cenoura?", "Quanto custa o quilo do arroz no mercado?",
        "Onde comprar feijão barato?", "Como cozinhar arroz soltinho?", "Me conta uma piada",
        "Qual o preço da banana hoje?", "Quem é o presidente do Brasil?",
        "Traduza esta frase para o inglês", "Quanto é 25 vezes 4?", "Como emagrecer rápido?",
        "Qual o melhor celular para comprar?", "Preciso de um encanador",
        "Qual o horário do ônibus para o centro?", "Quero comprar um carro usado",
        "Me indica uma série para assistir", "Como faço um currículo?", "asdfgh", "kkkkkkk", "123456",
        "coisa comida la", "teste", "bla bla bla", "Qual a capital da França?",
        "Como declarar imposto de renda?", "Quero pedir uma pizza", "Me ensina a programar em Python",
        "Qual o resultado da loteria?", "receita de feijoada", "Como fazer pão caseiro?",
        "quanto custa um iphone", "Tem desconto no supermercado hoje?",
        "Estou com dor de cabeça, o que tomo?", "Onde fica o hospital mais próximo?",
        "Vou viajar amanhã, qual roupa levo?", "Que horas são?", "Qual é o seu time de futebol?",
    ],
}

# =============================================================================
# 2. TEMPLATES (somente para ampliar o treino)
# =============================================================================
ALIMENTOS = ["arroz", "feijão", "macarrão", "banana", "tomate", "leite", "óleo de soja", "farinha",
             "açúcar", "pão", "frango congelado", "carne moída", "legumes", "verduras", "frutas",
             "iogurte", "suco", "água mineral", "refeições prontas", "marmitas", "biscoito", "enlatados",
             "ovos", "batata", "cebola", "cenoura", "mamão", "laranja", "queijo", "sopa", "café", "fubá",
             "sardinha em lata", "peixe congelado", "hortifrúti", "cesta básica"]
UNIDADES = ["kg", "quilos", "litros", "caixas", "unidades", "pacotes", "sacos", "latas", "bandejas",
            "fardos", "dúzias"]
LOCAIS = ["restaurante", "mercado", "padaria", "feira", "sacolão", "empresa", "condomínio", "lanchonete",
          "açougue", "escola", "refeitório", "hotel"]
VALIDADES = ["vence amanhã", "vence hoje", "validade até sexta", "vence em {n} dias", "validade {d}/{m}",
             "vence às {h}h", "perto do vencimento", "validade de {n} dias"]
SAUDACOES = ["Oi", "Olá", "Bom dia", "Boa tarde", "Boa noite", "Oi, tudo bem?"]
NOMES = ["João Silva", "Maria Souza", "Carlos Lima", "Ana Pereira", "Pedro Alves", "Fernanda Costa",
         "Luiz Rocha", "Bianca Dias"]
EMAILS = ["joao@email.com", "maria.souza@gmail.com", "contato@mercadosilva.com.br",
          "carlos_lima@outlook.com", "ana.p@empresa.com"]
CEPS = ["06700-000", "06705-000", "06710-100", "06754-020", "06800000"]


def _qtd():
    return str(random.choice([2, 3, 5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 80, 100, 150, 200]))


def _validade():
    v = random.choice(VALIDADES)
    return v.format(n=random.randint(2, 10), d=random.randint(1, 28), m=random.randint(1, 12),
                    h=random.randint(8, 22))


def gerar_cadastrar(n):
    modelos = [
        "Quero doar {q} {u} de {a}", "Tenho {q} {u} de {a} para doar", "Posso doar {q} {u} de {a}, {v}",
        "Sobraram {q} {u} de {a} aqui no {l}, queria doar", "Gostaria de doar {a}",
        "{s}, quero doar {q}{u} de {a}", "Doação: {q} {u} de {a}, {v}. Contato: {e}",
        "Sou {nome}, do {l}. Tenho {q} {u} de {a} para doar. Meu email é {e}",
        "{s}! Tenho {a} para doação, {q} {u}. CEP {c}", "meu {l} quer doar {q} {u} de {a} ({v})",
        "Vou doar {a}: {q} {u}. Retirada no CEP {c}", "Quero cadastrar a doação de {q} {u} de {a} e {a2}",
        "{nome} aqui, tenho {a} e {a2} pra doar, {v}", "Posso entregar {q} {u} de {a} {v}",
    ]
    return [random.choice(modelos).format(
        q=_qtd(), u=random.choice(UNIDADES), a=random.choice(ALIMENTOS), a2=random.choice(ALIMENTOS),
        v=_validade(), l=random.choice(LOCAIS), s=random.choice(SAUDACOES),
        nome=random.choice(NOMES), e=random.choice(EMAILS), c=random.choice(CEPS)) for _ in range(n)]


def gerar_solicitar(n):
    modelos = [
        "Nossa ONG precisa de {a}", "Estamos precisando de doações de {a}",
        "Somos uma {t} e precisamos de {a}", "Como minha {t} pode receber {a}?",
        "Nossa {t} está sem {a}, como pedir?", "Precisamos de {q} {u} de {a} para a nossa {t}",
        "Queremos receber doações de {a} e {a2}", "A {t} precisa urgente de {a}",
    ]
    tipos = ["ONG", "cozinha comunitária", "associação de moradores", "instituição", "creche",
             "entidade", "casa de acolhimento"]
    return [random.choice(modelos).format(
        a=random.choice(ALIMENTOS), a2=random.choice(ALIMENTOS), t=random.choice(tipos),
        q=_qtd(), u=random.choice(UNIDADES)) for _ in range(n)]


def gerar_status(n):
    modelos = [
        "Qual o status do protocolo {p}?", "Quero consultar a doação {p}", "Meu protocolo é {p}, como está?",
        "Como está a doação {p}?", "Consultar {p}", "status {p}", "Acompanhar protocolo {p}",
        "Minha doação {p} já foi aceita?", "O protocolo {p} já tem ONG?", "{p} - qual a situação?",
    ]
    return [random.choice(modelos).format(
        p=f"MF-2026{random.randint(1, 12):02d}{random.randint(1, 28):02d}-{random.randint(1, 9999):04d}")
        for _ in range(n)]


# =============================================================================
# 3. RUÍDO (simula digitação real: sem acento, erros, minúsculas)
# =============================================================================
def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def ruido(t):
    r = random.random()
    if r < 0.30:
        return t.lower()
    if r < 0.50:
        return sem_acento(t).lower()
    if r < 0.65 and len(t) > 6:  # erro de digitação: troca duas letras vizinhas
        i = random.randint(1, len(t) - 3)
        return t[:i] + t[i + 1] + t[i] + t[i + 2:]
    if r < 0.75 and len(t) > 6:  # esquece uma letra
        i = random.randint(1, len(t) - 2)
        return t[:i] + t[i + 1:]
    return t


# =============================================================================
# 4. FRASES ESCRITAS À MÃO (TESTE) - diferentes do treino
# =============================================================================
TESTE = {
    "cadastrar_doacao": [
        "Boa tarde, queria doar umas 40 marmitas que sobraram aqui", "tenho 8 caixas de laranja pra doar",
        "Gostaria de saber se posso doar 25 kg de farinha",
        "minha lanchonete fecha hoje e sobrou bastante comida, quero doar",
        "Vou doar 6 pacotes de café e 10 de açúcar", "queria doar o estoque de legumes da minha feira",
        "Posso mandar 100 litros de suco que vencem semana que vem?",
        "doar alimentos pra quem precisa, tenho 15 cestas",
        "Sou da padaria Central e tenho pão para doar todo fim de tarde",
        "Quero entregar 70 kg de arroz para quem precisar",
        "Oi, meu nome é Paulo e quero doar 20 kg de feijão, meu email é paulo@teste.com",
        "tenho um monte de fruta madura pra doação",
    ],
    "solicitar_alimentos": [
        "Nossa casa de acolhimento está precisando de alimentos",
        "Quero registrar minha associação para receber cestas",
        "Estamos sem comida na creche, como faço para pedir?",
        "Gostaria de solicitar alimentos para 50 famílias", "Preciso de comida para meus filhos",
        "Como a nossa cozinha solidária recebe doação?", "Tem algum alimento disponível para o nosso abrigo?",
        "Somos voluntários e queremos pedir mantimentos", "Nossa entidade precisa de leite e arroz",
        "Quero receber as doações da região", "Como a minha comunidade consegue pedir alimentos?",
        "falta comida aqui no abrigo",
    ],
    "consultar_status": [
        "Quero ver como está minha doação, o protocolo é MF-20261015-0007", "A ONG já aceitou o que eu doei?",
        "Como acompanho a doação que cadastrei?", "Qual a situação do protocolo MF-20261101-0120?",
        "Preciso saber onde está minha doação", "já foi coletada minha doação?", "consulta de protocolo",
        "Fiz uma doação ontem e quero saber o andamento", "Quero o status do meu pedido",
        "Pode checar a minha doação para mim?", "Tem novidade sobre a doação que eu fiz?",
        "Meu código de doação é MF-20260920-0003, e agora?",
    ],
    "aceitar_opcao": [
        "Sim, essa ONG está boa", "Pode ser, aceito", "Tudo bem, vou levar para essa",
        "Aceito a primeira opção", "sim!", "Ok, pode confirmar para mim", "Fechou", "Está ótimo, confirmo",
        "pode registrar com essa ONG", "perfeito", "Concordo com essa sugestão", "isso, quero essa",
    ],
    "recusar_opcao": [
        "Não, mostra a outra opção", "Essa fica longe pra mim, tem outra?", "Prefiro ver a segunda ONG",
        "Não posso ir lá, qual a próxima?", "Rejeito essa", "não quero essa ONG", "Tem uma segunda opção?",
        "Não vai dar, me mostra a outra", "Quero outra ONG por favor", "nao, a outra",
        "Não aceito essa sugestão", "Essa não, a próxima",
    ],
    "saudacao_ajuda": [
        "Oi, boa noite!", "Olá, preciso de uma ajuda", "Como eu uso esse chat?", "Oi, o que dá pra fazer aqui?",
        "bom dia, tudo bem?", "Queria entender como funciona o sistema", "E aí, tudo certo?",
        "Olá! Pode me orientar?", "Opa, tudo bem?", "me explica como funciona", "Olá, o que é esse sistema?",
        "boa tarde, pode me ajudar?",
    ],
    "fora_de_escopo": [
        "Vai chover amanhã?", "Qual a melhor receita de lasanha?", "quanto custa o feijão no atacado?",
        "Me recomenda um filme", "Como abro uma conta no banco?", "Quem ganhou o campeonato?",
        "Onde compro tomate mais barato?", "Qual a cotação do dólar?", "sdfsdfsdf", "Quero aprender inglês",
        "Como faço pra cozinhar macarrão?", "Me conta uma curiosidade",
    ],
}


def salvar(caminho, linhas):
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frase", "intencao"])
        w.writerows(linhas)


def main():
    PASTA_DATA.mkdir(parents=True, exist_ok=True)
    treino = {(f, i) for i, fs in MANUAL.items() for f in fs}

    extras = {"cadastrar_doacao": gerar_cadastrar(170), "solicitar_alimentos": gerar_solicitar(45),
              "consultar_status": gerar_status(40)}
    for intencao, frases in extras.items():
        for f in frases:
            treino.add((ruido(f), intencao))

    # Variações com ruído das frases manuais (robustez a digitação)
    for i, fs in MANUAL.items():
        for f in fs:
            if random.random() < 0.5:
                treino.add((ruido(f), i))

    treino_textos = {f.lower() for f, _ in treino}
    teste = {(f, i) for i, fs in TESTE.items() for f in fs if f.lower() not in treino_textos}

    treino = sorted(treino, key=lambda x: (x[1], x[0]))
    teste = sorted(teste, key=lambda x: (x[1], x[0]))
    salvar(PASTA_DATA / "dataset_intencoes.csv", treino)
    salvar(PASTA_DATA / "dataset_teste.csv", teste)

    print("Treino:", len(treino), dict(Counter(i for _, i in treino)))
    print("Teste :", len(teste), dict(Counter(i for _, i in teste)))


if __name__ == "__main__":
    main()
