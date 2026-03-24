# scrapers/atacadosp.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
from .base import BaseScraper

class AtacadoSPScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            # CORREÇÃO CRÍTICA: Substituído 'pasta_saida' por 'output_folder' para bater com o base.py
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.add_argument("--window-size=1920,1080")
            
            # --- PROTEÇÕES DO WINDOWS SERVER 2012 ---
            options.add_argument("--no-sandbox") 
            options.add_argument("--disable-dev-shm-usage") 
            options.add_argument("--disable-gpu") 
            
            driver = uc.Chrome(options=options, version_main=109)
            
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "vtex-store-components-3-x-productBrand"))
                )
            except:
                pass

            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Atacado SP"
            h1 = soup.find(class_=lambda c: c and "productBrand" in c)
            if h1: 
                titulo = self.limpar_texto(h1.get_text())

            # --- IMAGEM (SCREENSHOT SEGURO) ---
            caminho_imagem = None
            try:
                seletor_img = "img.vtex-store-components-3-x-productImageTag--main"
                try: 
                    el_img = driver.find_element(By.CSS_SELECTOR, seletor_img)
                except:
                    imgs = driver.find_elements(By.CSS_SELECTOR, "img[src*='arquivos/ids']")
                    el_img = imgs[0] if imgs else None

                if el_img:
                    filename = "temp_img_atacadosp.png"
                    # Usando a variável corrigida aqui também
                    caminho_imagem = os.path.join(self.output_folder, filename)
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                    time.sleep(1.5)
                    el_img.screenshot(caminho_imagem)
            except Exception: 
                pass

            # --- DESCRIÇÃO ---
            descricao = "Descrição indisponível."
            div_desc = soup.find("div", class_=lambda c: c and "productDescriptionText" in c)
            if div_desc:
                texto_bruto = div_desc.get_text(separator="\n", strip=True)
                descricao = self.limpar_lixo_comercial(texto_bruto)

            # --- SPECS ---
            specs = {}
            tabelas = soup.find_all("table", class_=lambda c: c and "productSpecificationsTable" in c)
            if not tabelas:
                tabelas = soup.find_all("table")
            
            for tab in tabelas:
                rows = tab.find_all("tr")
                for r in rows:
                    cols = r.find_all(["td", "th"])
                    if len(cols) == 2:
                        k = self.limpar_texto(cols[0].get_text())
                        v = self.limpar_texto(cols[1].get_text())
                        if k and v and len(k) < 60 and "garantia" not in k.lower():
                            specs[k] = v

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            # Agora ele vai passar daqui sem travar!
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
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass