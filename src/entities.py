import re
from datetime import datetime, timedelta

class ExtratorEntidades:
    def __init__(self):
        # Padrão Regex para extrair números associados a unidades de peso
        self.padrao_quantidade = r'(\d+(?:[\.,]\d+)?)\s*(?:kg|quilos|kilos|caixas|sacas)'
        self.vocabulario_alimentos = [
            "arroz", "feijão", "feijao", "tomate", "banana", "leite", 
            "marmita", "marmitas", "pão", "pao", "legumes", "frutas", "carne"
        ]

    def extrair_quantidade(self, texto):
        match = re.search(self.padrao_quantidade, texto, re.IGNORECASE)
        if match:
            valor_str = match.group(1).replace(',', '.')
            return float(valor_str)
        return 1.0  # Valor padrão (1 kg) se não informado

    def extrair_alimento(self, texto):
        texto_lower = texto.lower()
        for item in self.vocabulario_alimentos:
            if item in texto_lower:
                return item.capitalize()
        return "Alimentos Diversos"

    def extrair_validade(self, texto):
        texto_lower = texto.lower()
        hoje = datetime.now()
        
        if "hoje" in texto_lower:
            return hoje.strftime("%Y-%m-%d")
        elif "amanhã" in texto_lower or "amanha" in texto_lower:
            return (hoje + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            return (hoje + timedelta(days=3)).strftime("%Y-%m-%d")

    def processar_texto(self, texto):
        return {
            "alimento": self.extrair_alimento(texto),
            "quantidade_kg": self.extrair_quantidade(texto),
            "data_validade": self.extrair_validade(texto)
        }

if __name__ == "__main__":
    extrator = ExtratorEntidades()
    frase_teste = "Tenho 15.5 kg de tomate para doar hoje até o final do dia"
    resultado = extrator.processar_texto(frase_teste)
    print("--- TESTE DE EXTRAÇÃO REGEX ---")
    print(f"Frase: '{frase_teste}'")
    print(f"Entidades Extraídas: {resultado}")
