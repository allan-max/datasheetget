# scrapers/mercado_livre.py
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import time
import os
from .base import BaseScraper

class MercadoLivreScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [ML] Iniciando Scraper (Modo Indetectável)...")
            
            # --- SETUP DO CHROME FANTASMA (Proteção Server 2012 R2) ---
            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.add_argument("--window-size=1920,1080")
            
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            
            # version_main=109 é CRÍTICO para o seu Windows Server 2012 R2
            driver = uc.Chrome(options=options, version_main=109)
            
            print(f"   [ML] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            # Dá um tempinho para o Mercado Livre carregar o conteúdo dinâmico
            time.sleep(2)
            
            # Passa o HTML carregado pelo navegador real para o BeautifulSoup
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            h1 = soup.find('h1', class_='ui-pdp-title')
            titulo = h1.text.strip() if h1 else "Produto Mercado Livre"

            # --- DESCRIÇÃO (COM LIMPEZA) ---
            desc_elem = soup.find('p', class_='ui-pdp-description__content')
            descricao_bruta = desc_elem.text if desc_elem else ""
            descricao = self.limpar_lixo_comercial(descricao_bruta)

            # --- IMAGEM ---
            url_img = None
            meta_img = soup.find('meta', property='og:image')
            if meta_img and meta_img.get('content'):
                url_img = meta_img['content']
            else:
                img_container = soup.find('img', class_='ui-pdp-image')
                if img_container:
                    src = img_container.get('src')
                    if src and "http" in src: url_img = src

            # --- CARACTERÍSTICAS ---
            specs = {}
            rows = soup.find_all('tr', class_='andes-table__row')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    specs[th.text.strip()] = td.text.strip()
            
            specs = self.filtrar_specs(specs)

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": self.baixar_imagem_temp(url_img)
            }

            print("   [ML] Gerando arquivos PDF/Word...")
            arquivos = self.gerar_arquivos_finais(dados)

            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs,
                'total_imagens': 1,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO ML] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass