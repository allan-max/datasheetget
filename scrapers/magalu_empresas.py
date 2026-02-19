# scrapers/magalu_empresas.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import re
import json
from .base import BaseScraper

class MagaluEmpresasScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Magalu Empresas] Iniciando Scraper (V3 - Fix px bug)...")
            
            opts = Options()
            opts.add_argument("--headless=new") 
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument('--ignore-certificate-errors')
            opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

            driver = webdriver.Chrome(options=opts)
            driver.get(self.url)

            # 1. Espera
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
            except: pass

            # 2. Scroll e Expansão
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1)
            
            # Tenta clicar para expandir ficha
            try:
                driver.execute_script("""
                    var els = document.querySelectorAll('button, a, h3, h4, div[role="button"]');
                    els.forEach(el => {
                        var txt = el.innerText.toLowerCase();
                        if(txt.includes('ficha') || txt.includes('técnica') || txt.includes('especificações') || txt.includes('características')) {
                            el.click();
                        }
                    });
                """)
                time.sleep(2)
            except: pass
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Magalu Empresas"
            h1 = soup.find("h1")
            if h1: titulo = self.limpar_texto(h1.get_text())

            # --- BUSCA AVANÇADA DE IMAGEM ---
            url_img = None

            # 1. Tenta Meta Tag (Geralmente a melhor qualidade)
            meta_img = soup.find("meta", property="og:image")
            if meta_img: url_img = meta_img["content"]
            
            # 2. Tenta JSON-LD
            if not url_img:
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and "image" in data:
                            imgs = data["image"]
                            url_img = imgs[0] if isinstance(imgs, list) else imgs
                            if url_img: break
                    except: pass

            # 3. Tenta Seletores Visuais (COM CORREÇÃO DE INTEIRO)
            if not url_img:
                img_candidates = soup.find_all("img")
                for img in img_candidates:
                    src = img.get("src") or img.get("data-src") or ""
                    
                    if not src: continue
                    if "icon" in src or "thumb" in src or "avatar" in src: continue
                    
                    # CORREÇÃO DO ERRO "110px"
                    width_val = self._parse_size(img.get("width"))
                    if width_val > 0 and width_val < 200: continue # Ignora se for muito pequena
                    
                    classes = str(img.get("class"))
                    if "showcase" in classes or "product" in classes or "zoom" in classes:
                        url_img = src
                        break

            # 4. Fallback JavaScript (Acha a maior imagem na tela)
            if not url_img:
                print("   [DEBUG] Tentando busca visual JS...")
                url_img = driver.execute_script("""
                    var imgs = document.getElementsByTagName('img');
                    var largestImg = '';
                    var maxArea = 0;
                    for(var i=0; i<imgs.length; i++) {
                        var img = imgs[i];
                        var rect = img.getBoundingClientRect();
                        if(rect.width > 200 && rect.height > 200 && rect.top < 800) {
                            var area = rect.width * rect.height;
                            if(area > maxArea) {
                                maxArea = area;
                                largestImg = img.src || img.dataset.src;
                            }
                        }
                    }
                    return largestImg;
                """)

            if url_img and "magazineluiza" in url_img:
                url_img = url_img.replace("400x400", "1200x1200").replace("200x200", "1200x1200")

            # --- DESCRIÇÃO ---
            descricao_bruta = ""
            desc_containers = soup.find_all("div", attrs={"data-testid": re.compile("description", re.I)})
            
            # Se não achou por testid, busca por header
            if not desc_containers:
                for header in soup.find_all(["h2", "h3", "h4"]):
                    if "descrição" in header.get_text().lower():
                        container = header.find_next_sibling("div") or header.parent.find("div", recursive=False)
                        if container:
                            descricao_bruta += container.get_text(separator="\n") + "\n"

            for c in desc_containers:
                descricao_bruta += c.get_text(separator="\n") + "\n"
            
            if not descricao_bruta:
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if data.get("@type") == "Product":
                            descricao_bruta = data.get("description", "")
                    except: pass

            descricao = self.limpar_texto_sem_precos(descricao_bruta)

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
                        if not self.e_financeiro(k) and not self.e_financeiro(v):
                            specs[k] = v

            dts = soup.find_all("dt")
            for dt in dts:
                dd = dt.find_next_sibling("dd")
                if dd:
                    k = self.limpar_texto(dt.get_text())
                    v = self.limpar_texto(dd.get_text())
                    if not self.e_financeiro(k) and not self.e_financeiro(v):
                        specs[k] = v
            
            # Fallback de texto se não achou tabela
            if len(specs) < 2:
                text_blocks = soup.find_all(["p", "li", "span", "div"])
                for block in text_blocks:
                    txt = block.get_text().strip()
                    if ":" in txt and len(txt) < 100 and len(txt) > 3:
                        parts = txt.split(":", 1)
                        k = self.limpar_texto(parts[0])
                        v = self.limpar_texto(parts[1])
                        if len(k) < 40 and len(v) > 0 and "http" not in v:
                            if not self.e_financeiro(k) and not self.e_financeiro(v):
                                specs[k] = v

            specs_limpas = {}
            ignorar = ["garantia", "sac", "código", "vendido", "entregue", "ver mais", "descrição", "juros"]
            for k, v in specs.items():
                if not any(x in k.lower() for x in ignorar):
                    specs_limpas[k] = v

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
            print(f"   [ERRO MAGALU EMPRESAS] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                driver.quit()

    def _parse_size(self, val):
        """Converte '110px', '100%', 'auto' para int ou 0"""
        if not val: return 0
        try:
            # Remove tudo que não for dígito
            clean = re.sub(r'[^\d]', '', str(val))
            return int(clean) if clean else 0
        except:
            return 0

    def e_financeiro(self, texto):
        if not texto: return False
        regex = re.compile(r'(R\$\s*\d)|(\d{1,2}x\s*de)|(sem\s*juros)|(parcela)|(à\s*vista)|(cartão)', re.IGNORECASE)
        return bool(regex.search(texto))

    def limpar_texto_sem_precos(self, texto):
        if not texto: return "Descrição indisponível."
        texto = texto.replace("Descrição do Produto", "").replace("Informações Técnicas", "")
        linhas = texto.splitlines()
        linhas_limpas = []
        ignorar = ["garantia", "sac", "atendimento", "loja", "oferta", "frete", "entrega", "vendido por", "entregue por"]
        for linha in linhas:
            linha = linha.strip()
            if not linha: continue
            if self.e_financeiro(linha): continue
            if any(x in linha.lower() for x in ignorar): continue
            linhas_limpas.append(linha)
        return "\n\n".join(linhas_limpas)