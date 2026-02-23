# scrapers/samsung.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import json
import re
from .base import BaseScraper

class SamsungScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Samsung] Iniciando Scraper (V2 - Correção de Imagem)...")
            
            # --- SETUP (Padronizado para Win Server 2012 R2) ---
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
            print(f"   [Samsung] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            # Aguarda o elemento de Título específico
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
            except: pass

            # 2. Scroll para carregar conteúdo e imagens (Lazy Load)
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 2000);")
            time.sleep(1.5)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            # Tenta expandir botões de "Ver mais" ou "Especificações"
            try:
                btns = driver.find_elements(By.TAG_NAME, "button")
                for btn in btns:
                    txt = btn.text.lower()
                    if "especifica" in txt or "ver mais" in txt or "mostrar mais" in txt or "expandir" in txt:
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.5)
            except: pass

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Samsung"
            
            h1 = soup.find("h1", class_=lambda c: c and ("title" in c.lower() or "name" in c.lower()))
            if not h1:
                h1 = soup.find("h1")
                
            if h1: 
                titulo = self.limpar_texto(h1.get_text())

            if titulo == "Produto Samsung" or len(titulo) < 5:
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and data.get("@type") == "Product":
                            if data.get("name"):
                                titulo = self.limpar_texto(data.get("name"))
                                break
                    except: pass
                    
            print(f"   [DEBUG] Título capturado: {titulo}")

            # --- IMAGEM (NOVA LÓGICA DE CAPTURA) ---
            url_img = None
            
            # TENTATIVA 1: Busca diretamente as classes HTML da galeria de produtos
            img_tags = soup.find_all("img", class_=lambda c: c and (
                "first-image__main" in c or 
                "gallery-image" in c or 
                "pd-header-gallery__image" in c
            ))
            
            for img in img_tags:
                # O site da Samsung usa muito o 'srcset'. Pegamos a primeira URL dele.
                src = img.get("src")
                srcset = img.get("srcset")
                
                if not src and srcset:
                    # Pega o primeiro link antes da vírgula e do espaço
                    src = srcset.split(',')[0].strip().split(' ')[0]
                
                # Bloqueia logos e ícones
                if src and "logo" not in src.lower() and "icon" not in src.lower():
                    url_img = src
                    break

            # TENTATIVA 2: Meta Tags (Caso a visual falhe)
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img and "logo" not in meta_img["content"].lower():
                    url_img = meta_img["content"]
            
            # TENTATIVA 3: JSON-LD (Último recurso)
            if not url_img:
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and "image" in data:
                            imgs = data["image"]
                            candidato = imgs[0] if isinstance(imgs, list) else imgs
                            if isinstance(candidato, str) and "logo" not in candidato.lower():
                                url_img = candidato
                                break
                    except: pass
                    
            if url_img and url_img.startswith("//"): 
                url_img = "https:" + url_img

            if url_img:
                print(f"   [DEBUG] Imagem capturada: {url_img}")

            # --- DESCRIÇÃO ---
            descricao = "Descrição indisponível."
            blocos_desc = []
            
            features = soup.find_all(["p", "div", "h2", "h3"], class_=lambda c: c and (
                "feature-benefit__text" in c.lower() or 
                "feature-benefit__desc" in c.lower() or 
                "pd-info__summary" in c.lower() or 
                "product-details__desc" in c.lower() or
                "feature-benefit-text" in c.lower()
            ))
            
            for f in features:
                txt = f.get_text(separator="\n", strip=True)
                if len(txt) > 20 and txt not in blocos_desc:
                    blocos_desc.append(txt)
            
            if blocos_desc:
                descricao_bruta = "\n\n".join(blocos_desc)
                descricao = self.limpar_lixo_comercial(descricao_bruta)
            else:
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if data.get("@type") == "Product":
                            descricao_bruta = data.get("description", "")
                            if descricao_bruta:
                                descricao = self.limpar_lixo_comercial(descricao_bruta)
                    except: pass

            # --- FICHA TÉCNICA ---
            specs = {}
            
            spec_items = soup.find_all(["li", "div"], class_=lambda c: c and "spec" in c.lower() and "item" in c.lower())
            for item in spec_items:
                nome = item.find(["strong", "span", "p"], class_=lambda c: c and ("name" in c.lower() or "title" in c.lower()))
                valor = item.find(["span", "p", "div"], class_=lambda c: c and "value" in c.lower())
                
                if nome and valor:
                    k = self.limpar_texto(nome.get_text())
                    v = self.limpar_texto(valor.get_text())
                    if k and v and len(k) < 60:
                        specs[k] = v

            if not specs:
                tables = soup.find_all("table")
                for tbl in tables:
                    rows = tbl.find_all("tr")
                    for row in rows:
                        cols = row.find_all(["td", "th"])
                        if len(cols) >= 2:
                            k = self.limpar_texto(cols[0].get_text())
                            v = self.limpar_texto(cols[1].get_text())
                            if k and v and len(k) < 60: 
                                specs[k] = v

            # Filtros Finais
            specs_limpas = {}
            ignorar = ["garantia", "suporte", "sac", "parcelas", "juros", "meses"]
            for k, v in specs.items():
                if not any(x in k.lower() for x in ignorar):
                    specs_limpas[k] = v

            print(f"   ✅ Specs encontradas: {len(specs_limpas)} itens.")

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs_limpas,
                "caminho_imagem_temp": self.baixar_imagem_temp(url_img)
            }

            arquivos = self.gerar_arquivos_finais(dados)

            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs_limpas,
                'total_imagens': 1 if url_img else 0,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO SAMSUNG] {e}")
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass