# scrapers/magalu.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup, Comment
import time
import json
import re
from .base import BaseScraper

class MagaluScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Magalu] Iniciando Scraper (V6 - Bloqueio Total de Tabelas Financeiras)...")
            
            opts = Options()
            opts.add_argument("--headless=new") 
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument('--ignore-certificate-errors')
            opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

            driver = webdriver.Chrome(options=opts)
            driver.get(self.url)

            # 1. Aguarda carregamento
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
            except: pass

            # 2. Scroll para carregar conteúdo
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
            h1 = soup.find("h1")
            if h1: titulo = self.limpar_texto(h1.get_text())

            # --- IMAGEM (OG:IMAGE) ---
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
            
            # Identifica container
            container_desc = soup.find("div", attrs={"data-testid": "product-description"})
            if not container_desc:
                for header in soup.find_all(["h2", "h3"]):
                    if "descrição" in header.get_text().lower():
                        container_desc = header.find_next_sibling("div")
                        break
            
            if container_desc:
                # DESTRUIDOR DE ELEMENTOS FINANCEIROS NO HTML
                # Remove qualquer tabela ou lista que contenha "x de" ou "juros"
                elementos_financeiros = container_desc.find_all(['table', 'ul', 'ol', 'div', 'p'])
                regex_fin = re.compile(r'(R\$\s*\d)|(\d{1,2}x\s*de)|(sem\s*juros)', re.IGNORECASE)

                for elem in elementos_financeiros:
                    txt = elem.get_text()
                    # Se tiver mais de 1 ocorrência de preço no mesmo bloco, deleta o bloco
                    if len(re.findall(regex_fin, txt)) >= 1:
                         # Verifica se não é a descrição principal inteira (evita deletar tudo)
                         if len(txt) < 500: 
                             elem.decompose()

                descricao_bruta = container_desc.get_text(separator="\n")
            
            if not descricao_bruta:
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if data.get("@type") == "Product":
                            descricao_bruta = data.get("description", "")
                    except: pass

            # Limpeza de Texto Final
            descricao = self.limpar_descricao_sem_precos(descricao_bruta)

            # --- FICHA TÉCNICA (O PULO DO GATO) ---
            specs = {}
            tables = soup.find_all("table")
            
            for tbl in tables:
                rows = tbl.find_all("tr")
                for row in rows:
                    cols = row.find_all(["td", "th"])
                    if len(cols) >= 2:
                        k = self.limpar_texto(cols[0].get_text())
                        v = self.limpar_texto(cols[1].get_text())
                        
                        # --- FILTRO DE SEGURANÇA NA TABELA ---
                        # Se a chave ou o valor parecerem dinheiro, PULA essa linha
                        if self.e_texto_financeiro(k) or self.e_texto_financeiro(v):
                            continue
                        # -------------------------------------

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
            ignorar = ["garantia", "sac", "código", "vendido por", "entregue por", "ver mais", "parcelas", "juros"]
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
            print(f"   [ERRO MAGALU] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                driver.quit()

    def e_texto_financeiro(self, texto):
        """Verifica se um texto curto contém padrões de preço/parcelamento"""
        if not texto: return False
        
        # Padrões que condenam uma linha de tabela
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
            
            # Reutiliza a verificação financeira
            if self.e_texto_financeiro(linha_clean):
                continue
            
            linhas_limpas.append(linha_clean)

        return "\n\n".join(linhas_limpas)