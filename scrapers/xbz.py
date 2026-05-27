# scrapers/xbz.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class XbzScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [XBZ] Iniciando Scraper (Motor de Extração Simplificada)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")}')
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.minimize_window() 
            
            print(f"   [XBZ] Acedendo: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [XBZ] A aguardar renderização do produto...")
            try:
                # O título neste site geralmente está num p.produto-nome
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "p.produto-nome, h1"))
                )
            except:
                print("   ⚠️ Aviso: Título não encontrado rapidamente. A tentar continuar a extração.")
            
            # --- 1. ROLAGEM PROGRESSIVA (Lazy Load) ---
            for i in range(3):
                driver.execute_script("window.scrollBy(0, 400);")
                time.sleep(1)
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto XBZ"
            title_tag = soup.find(['p', 'h1'], class_=re.compile(r'produto-nome'))
            if not title_tag: title_tag = soup.find('h1')
            if title_tag: titulo = self.limpar_texto(title_tag.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO / FICHA TÉCNICA ---
            print("   [XBZ] A extrair Descrição e Características...")
            descricao = "Descrição indisponível."
            specs = {}
            
            desc_tag = soup.find('div', class_=re.compile(r'desc'))
            if desc_tag:
                # A XBZ costuma colocar a descrição no span.desc-sub
                desc_sub = desc_tag.find('span', class_=re.compile(r'desc-sub'))
                if desc_sub:
                    for br in desc_sub.find_all("br"): br.replace_with("\n")
                    descricao_bruta = desc_sub.get_text(separator="\n", strip=True)
                else:
                    for br in desc_tag.find_all("br"): br.replace_with("\n")
                    descricao_bruta = desc_tag.get_text(separator="\n", strip=True)
                
                if len(descricao_bruta) > 5:
                    descricao = self.limpar_lixo_comercial(descricao_bruta.strip())
                    print("   ✅ Descrição capturada com sucesso.")
                    
            # Procura tabelas caso produtos mais complexos (como mochilas) tenham ficha técnica
            all_rows = soup.find_all("tr")
            for row in all_rows:
                cols = row.find_all(['th', 'td'])
                if len(cols) == 2:
                    k = self.limpar_texto(cols[0].get_text())
                    v = self.limpar_texto(cols[1].get_text())
                    if k and v:
                        specs[k] = v
            
            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- IMAGEM ---
            print("   [XBZ] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_tag = soup.find('img', class_=re.compile(r'media-object'))
            if not img_tag:
                img_tag = soup.find('img', id="imagem_principal")
                
            if img_tag:
                # Prioriza o data-original para evitar carregar a versão miniatura desfocada
                url_img = img_tag.get('data-original') or img_tag.get('src')
                
            if url_img:
                # O site usa caminhos relativos, precisamos adicionar a raiz
                if url_img.startswith("/"):
                    url_img = "https://www.xbzbrindes.com.br" + url_img
                print(f"   [XBZ] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [XBZ] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "a.fancybox img, img.media-object, #imagem_principal")
                    if el_img:
                        filename = f"temp_img_xbz_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except:
                    pass

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [XBZ] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO XBZ] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass