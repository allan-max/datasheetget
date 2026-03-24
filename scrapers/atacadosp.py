# scrapers/atacadosp.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import json
from .base import BaseScraper

class AtacadoSPScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Atacado SP] Iniciando Scraper (V2 - Extrator Universal + VTEX)...")
            
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
            
            # CRÍTICO: Versão 109 para Windows Server 2012 R2
            driver = uc.Chrome(options=options, version_main=109)
            
            # 1. ACESSO
            print(f"   [Atacado SP] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            # Espera o título principal (H1 universal ou VTEX)
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
            except:
                print("   ⚠️ Timeout no carregamento inicial. Tentando forçar...")

            # Scroll para carregar imagens e descrições (Lazy Load)
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(1.5)

            # 2. EXTRAÇÃO
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Atacado SP"
            h1 = soup.find(class_=lambda c: c and "productBrand" in c)
            if not h1:
                h1 = soup.find("h1")
                
            if h1: 
                titulo = self.limpar_texto(h1.get_text())
                
            # Fallback (OG Meta Tag)
            if titulo == "Produto Atacado SP" or len(titulo) < 3:
                meta_title = soup.find("meta", property="og:title")
                if meta_title: 
                    titulo = self.limpar_texto(meta_title.get("content"))

            print(f"   [DEBUG] Título capturado: {titulo}")

            # --- IMAGEM (AGORA BAIXA A URL EM VEZ DE TIRAR PRINT) ---
            url_img = None
            
            # Tenta pegar pela meta tag (Mais seguro)
            meta_img = soup.find("meta", property="og:image")
            if meta_img:
                url_img = meta_img.get("content")
                
            # Se não achar, tenta as classes da VTEX
            if not url_img:
                img_tag = soup.find("img", class_=lambda c: c and "productImageTag" in c)
                if img_tag:
                    url_img = img_tag.get("src")
                    
            if url_img and url_img.startswith("//"):
                url_img = "https:" + url_img
                
            if url_img:
                print(f"   [DEBUG] Imagem capturada: {url_img}")

            # --- DESCRIÇÃO ---
            descricao = "Descrição indisponível."
            div_desc = soup.find("div", class_=lambda c: c and "productDescriptionText" in c)
            
            if not div_desc:
                 div_desc = soup.find("div", id=lambda x: x and "desc" in x.lower())
                 
            if div_desc:
                texto_bruto = div_desc.get_text(separator="\n", strip=True)
                descricao = self.limpar_lixo_comercial(texto_bruto)

            # --- FICHA TÉCNICA (SPECS) ---
            specs = {}
            print("   [Atacado SP] Lendo especificações...")
            
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

            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO E GERAÇÃO DE ARQUIVOS ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": self.baixar_imagem_temp(url_img)
            }
            
            print("   [Atacado SP] Gerando arquivos finais...")
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
            print(f"   ❌ [ERRO ATACADO SP] {e}")
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass