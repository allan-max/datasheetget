# teste_atacado.py
import sys
import os

# Força o terminal a aceitar UTF-8
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

print("="*60)
print(" 🛑 TESTE DE ISOLAMENTO (SEM API, SEM FLASK) ")
print(" Se esta tela falar, o culpado é o Flask!")
print("="*60)

# Importa o seu scraper
from scrapers.atacadosp import AtacadoSPScraper

# Pede o link
url_teste = input("\nCole o link do Atacado SP e aperte Enter:\n> ").strip()

if not url_teste:
    print("Nenhum link. Saindo...")
    sys.exit()

print(f"\n[SISTEMA] Iniciando a extração para: {url_teste}")

# Prepara a pasta e roda
scraper = AtacadoSPScraper(url_teste)
scraper.pasta_saida = "output"
os.makedirs("output", exist_ok=True)

try:
    print("[SISTEMA] Chamando o robô agora. Atenção aos logs abaixo:\n")
    print("-" * 60)
    
    resultado = scraper.executar()
    
    print("-" * 60)
    print("\n[SISTEMA] RESUMO FINAL DEVOLVIDO:")
    print(resultado)
except Exception as e:
    print(f"\n❌ ERRO CRÍTICO CAPTURADO: {e}")