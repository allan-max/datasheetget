# scrapers/magalu.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup, Comment
import time
import json
import re
import os
from .base import BaseScraper

class MagaluScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Magalu] Iniciando Scraper (V7 - Title Fix & Win2012 Ready)...")
            
            # --- SETUP (Padronizado para Win Server 2012 R2) ---
            if not hasattr(self, 'pasta_saida'): self.pasta_saida = "output"
            if not os.path.exists(self.pasta_saida): os.makedirs(self.pasta_saida)

            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.page_load_strategy = 'eager'

            # CRÍTICO: Versão 109 para rodar no Windows Server 2012 R2
            driver = uc.Chrome(options=options, version_main=109)
            
            # 1. ACESSO
            print(f"   [Magalu] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            # Aguarda o elemento de Título específico do Magalu
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1[data-testid='heading']"))
                )
            except: pass

            # 2. Scroll para carregar conteúdo (Lazy Load)
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(1)
            
            # Tenta clicar em "Ver mais"
            try:
                btns = driver.find_elements(By.TAG_NAME, "button")
                for btn in btns:
                    if "ver mais" in btn.text.lower():
                        driver.execute_script("arguments[0].click();", btn)
                        break
            except: pass

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Magalu"
            
            # 1. Tenta pela tag exata que você mandou
            h1 = soup.find("h1", attrs={"data-testid": "heading"})
            if not h1:
                # Fallback para o primeiro h1 genérico
                h1 = soup.find("h1")
                
            if h1: 
                titulo = self.limpar_texto(h1.get_text())

            # 2. Plano B (JSON-LD) se o título visual falhar ou vier vazio
            if titulo == "Produto Magalu" or len(titulo) < 5:
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and data.get("@type") == "Product":
                            nome_json = data.get("name")
                            if nome_json:
                                titulo = self.limpar_texto(nome_json)
                                break
                    except: pass
                    
            print(f"   [DEBUG] Título capturado: {titulo}")

            # --- IMAGEM (OG:IMAGE ou JSON) ---
            url_img = None
            meta_img = soup.find("meta", property="og:image")
            if meta_img: url_img = meta_img["content"]
            
            if not url_img:
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and "image" in data:
                            imgs = data["image"]
                            if isinstance(imgs, list): url_img = imgs[0]
                            else: url_img = imgs
                            break
                    except: pass

            # --- DESCRIÇÃO ---
            descricao_bruta = ""
            
            container_desc = soup.find("div", attrs={"data-testid": "product-description"})
            if not container_desc:
                for header in soup.find_all(["h2", "h3"]):
                    if "descrição" in header.get_text().lower():
                        container_desc = header.find_next_sibling("div")
                        break
            
            if container_desc:
                # Remove tabelas/listas financeiras da descrição
                elementos_financeiros = container_desc.find_all(['table', 'ul', 'ol', 'div', 'p'])
                regex_fin = re.compile(r'(R\$\s*\d)|(\d{1,2}x\s*de)|(sem\s*juros)', re.IGNORECASE)

                for elem in elementos_financeiros:
                    txt = elem.get_text()
                    if len(re.findall(regex_fin, txt)) >= 1:
                         if len(txt) < 500: 
                             elem.decompose()

                descricao_bruta = container_desc.get_text(separator="\n")
            
            # Fallback Descrição (JSON-LD)
            if not descricao_bruta:
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if data.get("@type") == "Product":
                            descricao_bruta = data.get("description", "")
                    except: pass

            descricao = self.limpar_descricao_sem_precos(descricao_bruta)

            # --- FICHA TÉCNICA ---
            specs = {}
            tables = soup.find_all("table")
            
            for tbl in tables:
                rows = tbl.find_all("tr")
                for row in rows:
                    cols = row.find_all(["td", "th"])
                    if len(cols) >= 2:
                        k = self.limpar_texto(cols[0].get_text())
                        v = self.limpar_texto(cols[1].get_text())
                        
                        if self.e_texto_financeiro(k) or self.e_texto_financeiro(v):
                            continue

                        if k and v: specs[k] = v
            
            dts = soup.find_all("dt")
            for dt in dts:
                dd = dt.find_next_sibling("dd")
                if dd:
                    k = self.limpar_texto(dt.get_text())
                    v = self.limpar_texto(dd.get_text())
                    
                    if self.e_texto_financeiro(k) or self.e_texto_financeiro(v):
                        continue
                        
                    specs[k] = v

            # Filtros Finais
            specs_limpas = {}
            ignorar = ["garantia", "sac", "código", "vendido por", "entregue por", "ver mais", "parcelas", "juros", "meses"]
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
                'total_imagens': 1,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO MAGALU] {e}")
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def e_texto_financeiro(self, texto):
        if not texto: return False
        regex_lixo = re.compile(r'(R\$\s*\d)|(\d{1,2}x\s*de)|(sem\s*juros)|(com\s*juros)|(parcelas)|(à\s*vista)|(cartão)', re.IGNORECASE)
        return bool(regex_lixo.search(texto))

    def limpar_descricao_sem_precos(self, texto):
        if not texto: return "Descrição indisponível."
        texto = texto.replace("Descrição do Produto", "").replace("Informações Técnicas", "")
        linhas = texto.splitlines()
        linhas_limpas = []
        
        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean: continue
            if self.e_texto_financeiro(linha_clean): continue
            linhas_limpas.append(linha_clean)

        return "\n\n".join(linhas_limpas)