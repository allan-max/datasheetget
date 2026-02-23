# scrapers/compragolden.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import json
from .base import BaseScraper

class CompraGoldenScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Compra Golden] Iniciando Scraper (V2 - Extrator Universal)...")
            
            # --- SETUP (Win Server 2012 R2) ---
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

            # Espera um elemento genérico e universal: a tag H1
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
            except:
                print("   ⚠️ Timeout esperando o H1. Tentando forçar extração...")

            # Scroll longo para garantir o carregamento das imagens
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(1)

            # 2. EXTRAÇÃO
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Compra Golden"
            h1 = soup.find("h1")
            if h1:
                titulo = self.limpar_texto(h1.get_text())
                
            # Plano B para o Título (OG Meta Tag ou JSON-LD)
            if titulo == "Produto Compra Golden" or len(titulo) < 3:
                meta_title = soup.find("meta", property="og:title")
                if meta_title: 
                    titulo = self.limpar_texto(meta_title.get("content"))
                    
            print(f"   [DEBUG] Título capturado: {titulo}")

            # --- IMAGEM ---
            url_img = None
            
            # Tenta pela Meta Tag Universal (A mais garantida)
            meta_img = soup.find("meta", property="og:image")
            if meta_img:
                url_img = meta_img.get("content")
            
            # Fallback JSON-LD
            if not url_img:
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and "image" in data:
                            imgs = data["image"]
                            url_img = imgs[0] if isinstance(imgs, list) else imgs
                            break
                    except: pass
                    
            if url_img and url_img.startswith("//"):
                url_img = "https:" + url_img
                
            if url_img:
                print(f"   [DEBUG] Imagem encontrada: {url_img}")

            # --- DESCRIÇÃO ---
            descricao = "Descrição indisponível."
            
            # Procura qualquer DIV que tenha "desc" ou "detalhe" no ID ou Classe
            div_desc = soup.find("div", id=lambda x: x and "desc" in x.lower())
            if not div_desc:
                div_desc = soup.find("div", class_=lambda x: x and "desc" in x.lower())
            if not div_desc:
                div_desc = soup.find("div", id=lambda x: x and "detalhe" in x.lower())
                
            if div_desc:
                texto_bruto = div_desc.get_text(separator="\n", strip=True)
                descricao = self.limpar_lixo_comercial(texto_bruto)
            else:
                # Tenta pegar da Meta Description se o corpo falhar
                meta_desc = soup.find("meta", property="og:description")
                if not meta_desc: meta_desc = soup.find("meta", attrs={"name": "description"})
                if meta_desc:
                    descricao = self.limpar_lixo_comercial(meta_desc.get("content", ""))

            # --- FICHA TÉCNICA (SPECS) ---
            specs = {}
            # Como a busca por tabela genérica já tinha funcionado para você antes, vamos mantê-la!
            tabelas = soup.find_all("table")
            for tab in tabelas:
                rows = tab.find_all("tr")
                for r in rows:
                    cols = r.find_all(["td", "th"])
                    # Se tiver 2 colunas, é chave=valor
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