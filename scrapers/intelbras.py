# scrapers/intelbras.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
import requests
from .base import BaseScraper

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

class IntelbrasScraper(BaseScraper):
    def executar(self):
        # Detecta se é PDF pela extensão ou cabeçalho content-type se necessário
        if self.url.lower().endswith('.pdf'):
            if not fitz:
                return {'sucesso': False, 'erro': "Instale o PyMuPDF: pip install pymupdf"}
            return self.processar_pdf()
        
        return self.processar_html()

    # =========================================================================
    # LÓGICA PARA PDF (DATASHEET) - VERSÃO V3 (SORT & CLEAN)
    # =========================================================================
    def processar_pdf(self):
        print(f"   [Intelbras] Processando Datasheet PDF (V3 - Layout Fix)...")
        try:
            # 1. DOWNLOAD
            if not hasattr(self, 'pasta_saida'): self.pasta_saida = "output"
            if not os.path.exists(self.pasta_saida): os.makedirs(self.pasta_saida)
            
            response = requests.get(self.url, timeout=30)
            if response.status_code != 200:
                raise Exception(f"Erro HTTP {response.status_code}")
            
            doc = fitz.open(stream=response.content, filetype="pdf")
            page1 = doc[0]

            # 2. TÍTULO (Busca o maior texto na primeira página)
            titulo = "Produto Intelbras PDF"
            max_size = 0
            blocks = page1.get_text("dict")["blocks"]
            for b in blocks:
                if "lines" in b:
                    for l in b["lines"]:
                        for s in l["spans"]:
                            if s["size"] > max_size and len(s["text"].strip()) > 3:
                                # Ignora textos genéricos grandes
                                txt = s["text"].strip()
                                if "intelbras" not in txt.lower() and "datasheet" not in txt.lower():
                                    max_size = s["size"]
                                    titulo = txt
            
            # Fallback se o título ficou genérico
            if titulo == "Produto Intelbras PDF":
                # Tenta pegar o nome do arquivo limpo
                titulo = self.url.split('/')[-1].replace('-', ' ').replace('.pdf', '').title()

            print(f"   [DEBUG] Título PDF: {titulo}")

            # 3. IMAGEM (Extrai a maior imagem da pág 1)
            caminho_imagem = None
            try:
                images = page1.get_images(full=True)
                if images:
                    # Pega a imagem com maior área (largura x altura)
                    xref_img = max(images, key=lambda x: x[2] * x[3])[0]
                    base_img = doc.extract_image(xref_img)
                    if base_img["width"] > 100: # Filtra ícones pequenos
                        filename = f"temp_img_intelbras_pdf.{base_img['ext']}"
                        caminho_imagem = os.path.join(self.pasta_saida, filename)
                        with open(caminho_imagem, "wb") as f:
                            f.write(base_img["image"])
                        print(f"   ✅ Imagem extraída: {filename}")
            except: pass

            # 4. SPECS (O Pulo do Gato: sort=True)
            specs = {}
            full_text = ""
            
            for page in doc:
                # sort=True organiza o texto visualmente (linha a linha)
                # Isso junta "Processador" (esquerda) com "Intel" (direita) na mesma string
                text_page = page.get_text("text", sort=True)
                full_text += text_page + "\n"
                
                lines = text_page.splitlines()
                for line in lines:
                    line = line.strip()
                    # Filtra lixo de rodapé/cabeçalho
                    if len(line) < 4 or "intelbras.com.br" in line or "sujeitas a alteração" in line:
                        continue

                    # Regex poderoso para separar Chave de Valor
                    # Procura por:
                    # 1. Dois ou mais pontos (..)
                    # 2. Dois pontos (:)
                    # 3. Dois ou mais espaços (  )
                    # 4. Tabulação (\t)
                    # 5. Caractere '–' ou '-' isolado entre espaços
                    parts = re.split(r'\.{2,}|:| {2,}|\t| – | - ', line)
                    
                    if len(parts) >= 2:
                        k = self.limpar_texto(parts[0])
                        v = self.limpar_texto(parts[-1]) # Pega o último pedaço como valor
                        
                        # Validação para não pegar lixo
                        if 2 < len(k) < 60 and len(v) > 0:
                            if "garantia" not in k.lower() and "especificações" not in k.lower():
                                specs[k] = v

            # Descrição: Pega os primeiros parágrafos limpos
            desc_lines = [l for l in full_text.splitlines() if len(l) > 50][:10]
            descricao = "\n".join(desc_lines) if desc_lines else "Descrição extraída do datasheet técnico."

            print(f"   ✅ Specs PDF encontradas: {len(specs)} itens.")

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
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
            print(f"   ❌ [ERRO PDF] {e}")
            return {'sucesso': False, 'erro': str(e)}

    # =========================================================================
    # LÓGICA HTML (Mantida)
    # =========================================================================
    def processar_html(self):
        driver = None
        try:
            print(f"   [Intelbras] Iniciando Scraper (HTML Mode)...")
            
            if not hasattr(self, 'pasta_saida'): self.pasta_saida = "output"
            if not os.path.exists(self.pasta_saida): os.makedirs(self.pasta_saida)

            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.add_argument("--window-size=1920,1080")

            driver = uc.Chrome(options=options, version_main=144)
            
            print(f"   [Intelbras] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "vtex-store-components-3-x-productNameContainer"))
                )
            except: pass

            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 3500);")
            time.sleep(1.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            titulo = "Produto Intelbras"
            h1 = soup.find("h1", class_=lambda c: c and "productNameContainer" in c)
            if h1: titulo = self.limpar_texto(h1.get_text())

            caminho_imagem = None
            try:
                seletor_img = "img.vtex-store-components-3-x-productImageTag--main"
                try: el_img = driver.find_element(By.CSS_SELECTOR, seletor_img)
                except: 
                    imgs = driver.find_elements(By.CSS_SELECTOR, "img[fetchpriority='high']")
                    el_img = imgs[0] if imgs else None

                if el_img:
                    filename = "temp_img_intelbras.png"
                    caminho_imagem = os.path.join(self.pasta_saida, filename)
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                    time.sleep(1)
                    el_img.screenshot(caminho_imagem)
            except: pass

            descricao = "Descrição indisponível."
            textos_desc = []
            div_main = soup.find("div", class_="intelbras-store-theme-4-x-description")
            if div_main: textos_desc.append(div_main.get_text(separator="\n", strip=True))
            
            infos = soup.find_all(class_=lambda c: c and "description_info__description" in c)
            for info in infos:
                pai = info.find_parent()
                titulo_info = ""
                if pai:
                    t = pai.find(class_=lambda c: c and "description_info__title" in c)
                    if t: titulo_info = t.get_text(strip=True) + ": "
                textos_desc.append(f"{titulo_info}{info.get_text(separator=' ', strip=True)}")

            if textos_desc:
                texto_completo = "\n\n".join(textos_desc)
                descricao = self.limpar_descricao_promocional(texto_completo)

            specs = {}
            container_specs = soup.find("td", attrs={"data-specification": True})
            if not container_specs:
                container_specs = soup.find("td", class_=lambda c: c and "specificationItemSpecifications" in c)

            if container_specs:
                conteudo = container_specs.get_text(separator="\n")
                linhas = conteudo.split(">")
                for linha in linhas:
                    linha = self.limpar_texto(linha)
                    if not linha or "garantia" in linha.lower(): continue
                    
                    match = re.match(r"^([A-Za-zÀ-ÿ\s/]+)(\d.*)?$", linha)
                    if match:
                        chave = match.group(1).strip()
                        valor = match.group(2).strip() if match.group(2) else ""
                        if not valor and " " in chave:
                            partes = chave.rsplit(" ", 1)
                            if len(partes) == 2: chave, valor = partes[0], partes[1]
                        if not valor: valor = "Sim"
                        if len(chave) > 1: specs[chave] = valor

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
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
            print(f"   ❌ [ERRO INTELBRAS] {e}")
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_promocional(self, texto):
        if not texto: return ""
        palavras_proibidas = [
            "adquira", "compre", "intelbras", "loja", "acesse", 
            "clique", "confira", "aproveite", "estoque", 
            "entrega", "garantia", "site", "www.", ".com.br",
            "vendido separadamente", "contratado separadamente"
        ]
        linhas_limpas = []
        for linha in texto.splitlines():
            linha_lower = linha.lower().strip()
            if len(linha_lower) < 2: continue
            if any(bad in linha_lower for bad in palavras_proibidas):
                continue
            linhas_limpas.append(linha.strip())
        return "\n".join(linhas_limpas)