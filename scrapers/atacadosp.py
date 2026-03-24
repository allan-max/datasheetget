# scrapers/atacadosp.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import traceback
from .base import BaseScraper

class AtacadoSPScraper(BaseScraper):
    def log_debug(self, msg):
        try:
            # Cria um ficheiro de log direto na pasta datasheetget (impossível de ser bloqueado)
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_path = os.path.join(base_dir, "ATACADO_DEBUG.txt")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        except:
            pass

    def executar(self):
        driver = None
        self.log_debug("="*40)
        self.log_debug(f"1. INICIANDO ATACADO SP: {self.url}")
        try:
            # Garante que a pasta de destino correta está definida
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                try: os.makedirs(self.output_folder)
                except: pass
            
            self.log_debug(f"2. Pasta final dos PDFs definida: {self.output_folder}")

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
            
            self.log_debug("3. Abrindo Chrome Headless (V109)...")
            driver = uc.Chrome(options=options, version_main=109)
            
            self.log_debug("4. Acessando a página...")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "vtex-store-components-3-x-productBrand"))
                )
            except:
                self.log_debug("   [Aviso] Demora no carregamento, forçando continuação.")

            self.log_debug("5. Rolando a página para renderizar as imagens...")
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(1)

            self.log_debug("6. Analisando o site (BeautifulSoup)...")
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Atacado SP"
            h1 = soup.find(class_=lambda c: c and "productBrand" in c)
            if h1: 
                titulo = self.limpar_texto(h1.get_text())
            self.log_debug(f"7. Título capturado: {titulo}")

            # --- IMAGEM (SCREENSHOT SEGURO) ---
            self.log_debug("8. Tentando capturar a imagem...")
            caminho_imagem = None
            try:
                seletor_img = "img.vtex-store-components-3-x-productImageTag--main"
                el_img = None
                try: 
                    el_img = driver.find_element(By.CSS_SELECTOR, seletor_img)
                except:
                    imgs = driver.find_elements(By.CSS_SELECTOR, "img[src*='arquivos/ids']")
                    if imgs: el_img = imgs[0]

                if el_img:
                    filename = f"temp_img_atacadosp_{int(time.time())}.png"
                    # CRÍTICO: Guarda a imagem na pasta local do script para não haver bloqueios de rede!
                    caminho_imagem = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
                    
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                    time.sleep(1.5)
                    el_img.screenshot(caminho_imagem)
                    self.log_debug(f"   [OK] Imagem capturada localmente em: {caminho_imagem}")
                else:
                    self.log_debug("   [Aviso] Elemento da imagem não encontrado na tela.")
            except Exception as e: 
                self.log_debug(f"   [ERRO] Falha ao capturar a imagem: {e}")

            # --- DESCRIÇÃO ---
            self.log_debug("9. Extraindo descrição...")
            descricao = "Descrição indisponível."
            div_desc = soup.find("div", class_=lambda c: c and "productDescriptionText" in c)
            if div_desc:
                texto_bruto = div_desc.get_text(separator="\n", strip=True)
                descricao = self.limpar_lixo_comercial(texto_bruto)

            # --- SPECS ---
            self.log_debug("10. Extraindo Ficha Técnica...")
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
            self.log_debug(f"   [OK] {len(specs)} características encontradas.")

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            self.log_debug("11. Chamando o gerador de PDF e Word...")
            try:
                arquivos = self.gerar_arquivos_finais(dados)
                self.log_debug(f"12. SUCESSO! Ficheiros gravados: {arquivos}")
            except Exception as e:
                self.log_debug(f"[ERRO CRÍTICO A GERAR FICHEIROS] {traceback.format_exc()}")
                arquivos = {}
            
            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs,
                'total_imagens': 1 if caminho_imagem else 0,
                'arquivos': arquivos
            }

        except Exception as e:
            self.log_debug(f"[ERRO FATAL NO SCRAPER] {traceback.format_exc()}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass
            self.log_debug("13. Processo terminado. Chrome encerrado.")