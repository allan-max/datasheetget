# scrapers/projetelas.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
from .base import BaseScraper

class ProjetelasScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Projetelas] A iniciar Scraper...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            
            print(f"   [Projetelas] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            time.sleep(2) # Site simples, carrega rápido
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Projetelas"
            h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO E SPECS MISTURADOS ---
            print("   [Projetelas] A extrair Descrição e Ficha Técnica...")
            descricao = "Descrição indisponível."
            specs = {}
            
            # O conteúdo está todo dentro desta div
            content_div = soup.find('div', class_='col-lg-7') or soup.find('div', class_='col-sm-6')
            
            if content_div:
                linhas = []
                for elemento in content_div.find_all(['p', 'li']):
                    texto = elemento.get_text(separator=" ", strip=True)
                    if texto and "MAIS INFORMAÇÕES" not in texto and "Garantia:" not in texto:
                        if elemento.name == 'li':
                            linhas.append(f"• {texto}")
                        else:
                            linhas.append(texto)
                
                if linhas:
                    descricao = "\n".join(linhas)
                    print("   ✅ Descrição/Specs capturadas com sucesso.")

            # --- IMAGEM ---
            print("   [Projetelas] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            # A imagem na Projetelas costuma estar no href da lightbox
            img_tag = soup.find('a', class_='lightbox')
            if img_tag:
                url_img = img_tag.get('href')
                # Se o link for relativo (ex: /upload/files...), adicionamos o domínio
                if url_img and url_img.startswith('/'):
                    url_img = "https://www.projetelas.com.br" + url_img

            if url_img:
                print(f"   [Projetelas] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs, # Vazio pois pusemos tudo na descrição formatada
                "caminho_imagem_temp": caminho_imagem
            }

            arquivos = self.gerar_arquivos_finais(dados)

            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs,
                'total_imagens': 1 if caminho_imagem else 0,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO PROJETELAS] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass