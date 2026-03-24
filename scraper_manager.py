# scraper_manager.py
import importlib
import sys
import os
from config import identificar_site

diretorio_atual = os.path.dirname(os.path.abspath(__file__))
if diretorio_atual not in sys.path:
    sys.path.append(diretorio_atual)

class ScraperManager:
    def __init__(self):
        self.scrapers_carregados = {}
    
    def carregar_scraper(self, modulo_nome, classe_nome):
        chave = f"{modulo_nome}.{classe_nome}"
        if chave in self.scrapers_carregados:
            return self.scrapers_carregados[chave]
        
        try:
            print(f" [SISTEMA] Carregando o motor: scrapers.{modulo_nome} -> {classe_nome}")
            modulo = importlib.import_module(f"scrapers.{modulo_nome}")
            return getattr(modulo, classe_nome)
        except ModuleNotFoundError as e:
            print(f" [ERRO FATAL] Falha ao carregar o robô {modulo_nome}: {e}")
            raise Exception(f"Erro de Importação: {e}")
    
    def executar_scraping(self, url, output_folder):
        try:
            print(f" [SISTEMA] Analisando URL recebida: {url}")
            site_nome, modulo_nome, classe_nome = identificar_site(url)
            
            if not site_nome:
                print(" [ALERTA] URL não reconhecida na nossa config.py!")
                return {'sucesso': False, 'erro': 'Site não configurado ou URL inválida'}
            
            print(f" [SISTEMA] Site identificado: {site_nome.upper()}")
            ClasseScraper = self.carregar_scraper(modulo_nome, classe_nome)
            
            scraper = ClasseScraper(url)
            scraper.output_folder = output_folder
            
            print(f" [SISTEMA] Dando a partida no {classe_nome}...")
            return scraper.executar()
            
        except Exception as e:
            print(f" [ERRO GERENCIADOR] Aconteceu um desastre ao executar: {str(e)}")
            return {'sucesso': False, 'erro': str(e)}