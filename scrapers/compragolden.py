# scrapers/compragolden.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class CompraGoldenScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Compra Golden] Iniciando Scraper (Padrão VTEX - Win2012)...")
            
            # --- SETUP ---
            if not hasattr(self, 'pasta_saida'): self.pasta_saida = "output"
            if not os.path.exists(self.pasta_saida): os.makedirs(self.pasta_saida)

            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.page_load_strategy = 'eager'

            # CRÍTICO: Versão 109 para rodar no Windows Server 2012 R2
            driver = uc.Chrome(options=options, version_main=109)
            
            # 1. ACESSO
            print(f"   [Compra Golden] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            # Espera o título principal aparecer (Padrão VTEX)
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "vtex-store-components-3-x-productBrand"))
                )
            except:
                print("   ⚠️ Timeout no carregamento do título.")

            # Scroll para carregar imagens e descrições (Lazy Load típico da VTEX)
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1600);")
            time.sleep(1.5)

            # 2. EXTRAÇÃO
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Compra Golden"
            h1 = soup.find(class_=lambda c: c and "productBrand" in c)
            if h1: 
                titulo = self.limpar_texto(h1.get_text())
            print(f"   [DEBUG] Título: {titulo}")

            # --- IMAGEM ---
            url_img = None
            img_tag = soup.find("img", class_=lambda c: c and "productImageTag--main" in c)
            if img_tag:
                url_img = img_tag.get("src")
            
            if not url_img:
                # Fallback: pega qualquer imagem da galeria da VTEX
                imgs = soup.find_all("img", class_=lambda c: c and "productImageTag" in c)
                if imgs: url_img = imgs[0].get("src")
                
            if url_img and url_img.startswith("//"):
                url_img = "https:" + url_img

            # --- DESCRIÇÃO ---
            descricao = "Descrição indisponível."
            div_desc = soup.find("div", class_=lambda c: c and "productDescriptionText" in c)
            if div_desc:
                texto_bruto = div_desc.get_text(separator="\n", strip=True)
                descricao = self.limpar_lixo_comercial(texto_bruto)

            # --- FICHA TÉCNICA (SPECS) ---
            specs = {}
            tabelas = soup.find_all("table", class_=lambda c: c and "productSpecificationsTable" in c)
            
            for tab in tabelas:
                # Na VTEX, as linhas tem a classe specificationItemRow
                rows = tab.find_all("tr", class_=lambda c: c and "specificationItemRow" in c)
                for r in rows:
                    # O nome da especificação fica no <th> e o valor no <td>
                    th = r.find("th")
                    td = r.find("td")
                    if th and td:
                        k = self.limpar_texto(th.get_text())
                        v = self.limpar_texto(td.get_text())
                        if k and v and len(k) < 60 and "garantia" not in k.lower():
                            specs[k] = v

            # Fallback se não achar a tabela específica, procura tabelas genéricas
            if not specs:
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

            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO E GERAÇÃO DE ARQUIVOS ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": self.baixar_imagem_temp(url_img)
            }
            
            arquivos = self.gerar_arquivos_finais(dados)
            
            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs,
                'total_imagens': 1 if url_img else 0,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO COMPRA GOLDEN] {e}")
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass