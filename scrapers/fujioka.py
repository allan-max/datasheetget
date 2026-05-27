# scrapers/fujioka.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class FujiokaScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Fujioka] Iniciando Scraper (Motor Javascript Ativado)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            opts = uc.ChromeOptions()
            opts.page_load_strategy = 'eager'
            opts.add_argument("--no-first-run")
            opts.add_argument("--password-store=basic")
            opts.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")}')
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            
            driver = uc.Chrome(options=opts, version_main=109)
            driver.minimize_window()

            print(f"   [Fujioka] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "productName")))
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. Tentando continuar.")
            
            # --- ROLAGEM PROGRESSIVA (Garante que a VTEX injeta a descrição no HTML) ---
            print("   [Fujioka] Vasculhando a página...")
            for i in range(4):
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)
                
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- 1. TÍTULO ---
            title_tag = soup.find(class_=re.compile(r"productName"))
            titulo = self.limpar_texto(title_tag.get_text()) if title_tag else "Fujioka Produto"
            print(f"   ✅ Título capturado: {titulo}")

            # --- 2. DESCRIÇÃO ---
            print("   [Fujioka] Extraindo Descrição...")
            descricao = "Descrição indisponível."
            
            desc_tag = soup.find("div", class_=re.compile(r"productDescription"))
            if desc_tag:
                for br in desc_tag.find_all("br"): br.replace_with("\n")
                desc_texto = desc_tag.get_text(separator="\n", strip=True)
                
                if len(desc_texto) > 10:
                    descricao = self.limpar_lixo_comercial(desc_texto)
                    print("   ✅ Descrição capturada com sucesso.")
            else:
                print("   ⚠️ Aviso: O bloco da descrição não foi renderizado a tempo.")

            # --- 3. IMAGEM ---
            print("   [Fujioka] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            # Tenta pegar pela meta tag do Facebook (A mais limpa)
            meta_img = soup.find("meta", property="og:image")
            if meta_img and meta_img.get("content"):
                url_img = meta_img.get("content")
            
            # Fallback para o container de imagem
            if not url_img:
                img_tag = soup.find("div", class_="product-image")
                if img_tag and img_tag.find("img"):
                    url_img = img_tag.find("img").get("src")
                elif soup.find("img", id="image-main"):
                    url_img = soup.find("img", id="image-main").get("src")

            if url_img:
                # O Truque da Qualidade: Força a imagem a baixar na resolução máxima (1000x1000)
                url_img = re.sub(r'-\d{2,4}-\d{2,4}', '-1000-1000', url_img)
                caminho_imagem = self.baixar_imagem_temp(url_img)
                
            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Fujioka] Apelando para o Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, ".product-image img, #image-main")
                    if el_img:
                        filename = f"temp_img_fujioka_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1.5)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except:
                    pass

            # --- 4. CARACTERÍSTICAS TÉCNICAS ---
            print("   [Fujioka] Extraindo Ficha Técnica...")
            specs = {}
            all_rows = soup.find_all("tr")
            for row in all_rows:
                key_cell = row.find(class_=lambda x: x and 'name-field' in x)
                val_cell = row.find(class_=lambda x: x and 'value-field' in x)

                if key_cell and val_cell:
                    k = self.limpar_texto(key_cell.get_text())
                    v = self.limpar_texto(val_cell.get_text())
                    if k and v:
                        specs[k] = v
            
            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [Fujioka] Gerando arquivos PDF/Word...")
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
            print(f"   ❌ [ERRO FUJIOKA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver: driver.quit()