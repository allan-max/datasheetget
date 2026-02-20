# scrapers/bhphotovideo.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import json
from deep_translator import GoogleTranslator
from .base import BaseScraper

class BhPhotoVideoScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [B&H] Iniciando Scraper (V28 - Headless & Win2012 Fix)...")
            
            # --- SETUP ---
            if not hasattr(self, 'pasta_saida'): self.pasta_saida = "output"
            if not os.path.exists(self.pasta_saida): os.makedirs(self.pasta_saida)

            options = uc.ChromeOptions()
            
            # --- CORREÇÕES APLICADAS AQUI ---
            options.add_argument("--headless=new") # Modo invisível
            options.add_argument("--window-size=1920,1080") # Evita quebras de layout
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check") # Pula a tela de boas-vindas
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.page_load_strategy = 'eager'
            
            # CRÍTICO: Versão 109 para rodar no Windows Server 2012 R2
            driver = uc.Chrome(options=options, version_main=109)
            
            # =========================================================
            # ETAPA 1: PÁGINA PRINCIPAL
            # =========================================================
            print(f"   [B&H] Acessando Principal: {self.url}")
            driver.set_page_load_timeout(25)
            driver.get(self.url)

            # Tenta fechar popups/cookies se aparecerem
            try:
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-selenium='cooc-close']"))
                ).click()
            except: pass

            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1[data-selenium='productTitle']"))
                )
            except: pass

            soup_main = BeautifulSoup(driver.page_source, 'html.parser')
            titulo = "Produto B&H"
            h1 = soup_main.find("h1", attrs={"data-selenium": "productTitle"})
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   [DEBUG] Título: {titulo}")

            # --- IMAGEM ---
            caminho_imagem = None
            seletores_img = [
                "img[data-selenium='inlineMediaMainImage']",
                "div[data-selenium='inlineMedia'] img",
                "img[class*='mainImage']"
            ]
            
            for seletor in seletores_img:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, seletor)
                    for el in els:
                        if el.is_displayed() and el.size['width'] > 50:
                            filename = "temp_img_bh.png"
                            caminho_imagem = os.path.join(self.pasta_saida, filename)
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                            time.sleep(0.3)
                            el.screenshot(caminho_imagem)
                            print(f"   ✅ Imagem salva.")
                            break
                    if caminho_imagem: break
                except: pass

            # =========================================================
            # ETAPA 2: OVERVIEW
            # =========================================================
            url_overview = self.url.split("?")[0].rstrip("/") + "/overview"
            if "/overview" not in driver.current_url:
                driver.set_page_load_timeout(10)
                try: driver.get(url_overview)
                except: driver.execute_script("window.stop();")

            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1) 

            soup_ov = BeautifulSoup(driver.page_source, 'html.parser')
            descricao_en = ""
            blocos_desc = []

            features = soup_ov.find_all("div", class_=lambda c: c and "feature_" in c)
            if not features:
                div_long = soup_ov.find("div", attrs={"data-selenium": "overviewLongDescription"})
                if div_long: features = [div_long]

            seen_text = set()
            for feat in features:
                if len(feat.find_all("div", class_=lambda c: c and "feature_" in c)) > 1: continue
                header = feat.find("div", class_=lambda c: c and "featureHeader_" in c)
                body = feat.find("div", class_="js-injected-html")
                txt_h = header.get_text(strip=True) if header else ""
                txt_b = body.get_text(separator="\n", strip=True) if body else ""
                if txt_b and txt_b not in seen_text:
                    seen_text.add(txt_b)
                    chunk = f"### {txt_h}\n{txt_b}\n" if txt_h else f"{txt_b}\n"
                    blocos_desc.append(chunk)

            if blocos_desc: descricao_en = "\n".join(blocos_desc)
            else:
                div_d = soup_ov.find("div", class_=lambda c: c and "js-injected-html" in c)
                if div_d: descricao_en = div_d.get_text(separator="\n\n", strip=True)

            print("   [B&H] Traduzindo descrição...")
            descricao_pt = self.traduzir_texto(descricao_en)

            # =========================================================
            # ETAPA 3: SPECS (COM VERIFICAÇÃO ATIVA)
            # =========================================================
            print(f"   [B&H] Extraindo Specs...")
            
            tabela_detectada = False
            
            # TENTATIVA 1: Clique na Aba
            try:
                abas_specs = driver.find_elements(By.CSS_SELECTOR, "a[href*='/specs'], li[data-tab='specs']")
                for aba in abas_specs:
                    if "specs" in aba.text.lower() or "specifications" in aba.text.lower():
                        if aba.is_displayed():
                            print("   [B&H] Clicando na aba Specs...")
                            driver.execute_script("arguments[0].click();", aba)
                            
                            try:
                                WebDriverWait(driver, 4).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "table[data-selenium='specsItemGroupTable']"))
                                )
                                tabela_detectada = True
                            except: pass
                            break
            except: pass

            # TENTATIVA 2: Navegação Direta (Se clique falhou)
            if not tabela_detectada:
                print("   [B&H] Navegando direto para Specs (Timeout 6s)...")
                url_specs = self.url.split("?")[0].rstrip("/") + "/specs"
                driver.set_page_load_timeout(6) 
                try: 
                    driver.get(url_specs)
                except: 
                    driver.execute_script("window.stop();")
            
            # --- PARSE ---
            soup_specs = BeautifulSoup(driver.page_source, 'html.parser')
            specs = {}
            tabelas = soup_specs.find_all("table", attrs={"data-selenium": "specsItemGroupTable"})
            if not tabelas: tabelas = soup_specs.find_all("table")

            # 1. Extração Visual (Tabelas)
            if tabelas:
                print(f"   ✅ {len(tabelas)} tabelas visuais encontradas.")
                for tabela in tabelas:
                    for linha in tabela.find_all("tr"):
                        cols = linha.find_all("td")
                        if len(cols) >= 2:
                            k = self.limpar_texto(cols[0].get_text())
                            v = self.limpar_texto(cols[1].get_text())
                            if len(k) < 100 and len(v) > 0:
                                if not any(ig in k.lower() for ig in ["packaging", "box dim", "peso da emb"]):
                                    specs[k] = v
            
            # 2. Extração Oculta (JSON-LD)
            if not specs:
                print("   ⚠️ Tabelas vazias. Buscando dados ocultos (JSON-LD)...")
                try:
                    scripts = soup_specs.find_all("script", type="application/ld+json")
                    for script in scripts:
                        try:
                            txt = script.get_text()
                            if "weight" in txt or "width" in txt:
                                data = json.loads(txt)
                                if isinstance(data, list): data = data[0]
                                
                                if "width" in data: specs["Largura"] = str(data["width"])
                                if "height" in data: specs["Altura"] = str(data["height"])
                                if "depth" in data: specs["Profundidade"] = str(data["depth"])
                                if "weight" in data: specs["Peso"] = str(data["weight"])
                                if "sku" in data: specs["SKU"] = str(data["sku"])
                                if "brand" in data: 
                                    b = data["brand"]
                                    if isinstance(b, dict): specs["Marca"] = b.get("name", "")
                                    else: specs["Marca"] = str(b)
                        except: pass
                except: pass

            # --- TRADUÇÃO EM LOTE ---
            specs_final = {}
            if specs:
                print(f"   [B&H] Traduzindo {len(specs)} itens em lote...")
                try:
                    chaves_en = list(specs.keys())
                    valores_en = list(specs.values())
                    
                    try:
                        translator = GoogleTranslator(source='en', target='pt')
                        chaves_pt = translator.translate_batch(chaves_en)
                        valores_pt = translator.translate_batch(valores_en)
                        specs_final = dict(zip(chaves_pt, valores_pt))
                    except:
                        print("   ⚠️ Batch falhou, tentando linear...")
                        for k, v in specs.items():
                            specs_final[self.traduzir_texto(k)] = self.traduzir_texto(v)
                except Exception as e:
                    print(f"   ⚠️ Erro tradução: {e}. Mantendo inglês.")
                    specs_final = specs
            
            print(f"   ✅ Specs prontas: {len(specs_final)} itens.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao_pt,
                "caracteristicas": specs_final,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [B&H] Gerando arquivos finais...")
            arquivos = self.gerar_arquivos_finais(dados)
            
            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao_pt,
                'caracteristicas': specs_final,
                'total_imagens': 1 if caminho_imagem else 0,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO B&H] {e}")
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def traduzir_texto(self, texto, curto=False):
        if not texto or len(texto) < 2: return texto
        try:
            limit = 4500
            texto_safe = texto[:limit]
            translator = GoogleTranslator(source='en', target='pt')
            return translator.translate(texto_safe)
        except: return texto