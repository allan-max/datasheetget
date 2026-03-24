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
            print(f"   [Atacado SP] Iniciando Scraper (V4 - Correção de Pasta)...", flush=True)
            
            # CORREÇÃO CRÍTICA AQUI: O sistema base exige o nome 'output_folder'
            if not hasattr(self, 'output_folder'): 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            
            # --- ESCUDOS PARA O WINDOWS SERVER 2012 ---
            options.add_argument("--no-sandbox") 
            options.add_argument("--disable-dev-shm-usage") 
            options.add_argument("--disable-gpu") 

            options.page_load_strategy = 'eager'
            
            driver = uc.Chrome(options=options, version_main=109)
            
            print(f"   [Atacado SP] Acessando: {self.url}", flush=True)
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "vtex-store-components-3-x-productBrand"))
                )
            except:
                print("   [Aviso] Timeout no carregamento inicial.", flush=True)

            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            titulo = "Produto Atacado SP"
            h1 = soup.find(class_=lambda c: c and "productBrand" in c)
            if h1: 
                titulo = self.limpar_texto(h1.get_text())
            print(f"   [DEBUG] Titulo: {titulo}", flush=True)

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
                    # Usando a variável correta agora:
                    caminho_imagem = os.path.join(self.output_folder, filename)
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                    time.sleep(1)
                    el_img.screenshot(caminho_imagem)
                    print(f"   [Sucesso] Imagem salva: {filename}", flush=True)
            except Exception as e: 
                print(f"   [Aviso] Erro ao capturar imagem: {e}", flush=True)

            descricao = "Descricao indisponivel."
            div_desc = soup.find("div", class_=lambda c: c and "productDescriptionText" in c)
            if div_desc:
                texto_bruto = div_desc.get_text(separator="\n", strip=True)
                descricao = self.limpar_lixo_comercial(texto_bruto)

            specs = {}
            print("   [Atacado SP] Lendo especificacoes...", flush=True)
            
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

            print(f"   [Sucesso] Specs encontradas: {len(specs)} itens.", flush=True)

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [Atacado SP] Gerando arquivos finais...", flush=True)
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
            print(f"   [ERRO ATACADO SP] {e}", flush=True)
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass