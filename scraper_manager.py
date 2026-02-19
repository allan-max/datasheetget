# scraper_manager.py
import importlib
import sys
import os
from config import identificar_site

# --- CORREÇÃO DE PATH ---
# Adiciona o diretório atual (onde está este arquivo) ao sys.path
# Isso garante que o Python encontre a pasta 'scrapers'
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
if diretorio_atual not in sys.path:
    sys.path.append(diretorio_atual)
# ------------------------

class ScraperManager:
    def __init__(self):
        self.scrapers_carregados = {}
    
    def carregar_scraper(self, modulo_nome, classe_nome):
        # Carregamento dinâmico
        chave = f"{modulo_nome}.{classe_nome}"
        if chave in self.scrapers_carregados:
            return self.scrapers_carregados[chave]
        
        try:
            # Tenta importar como "scrapers.modulo"
            modulo = importlib.import_module(f"scrapers.{modulo_nome}")
            return getattr(modulo, classe_nome)
        except ModuleNotFoundError as e:
            # Debug detalhado se falhar
            print(f"DEBUG PATH: {sys.path}")
            raise Exception(f"Erro de Importação: {e}. Verifique se 'scrapers/{modulo_nome}.py' existe e se tem __init__.py na pasta.")
    
    def executar_scraping(self, url, output_folder):
        try:
            site_nome, modulo_nome, classe_nome = identificar_site(url)
            
            if not site_nome:
                return {'sucesso': False, 'erro': 'Site não configurado ou URL inválida'}
            
            ClasseScraper = self.carregar_scraper(modulo_nome, classe_nome)
            
            # Instancia o scraper
            scraper = ClasseScraper(url)
            scraper.output_folder = output_folder
            
            print(f"   --> Iniciando scraper: {site_nome}")
            return scraper.executar()
            
        except Exception as e:
            # Retorna o erro detalhado para aparecer no log da API
            return {'sucesso': False, 'erro': str(e)}