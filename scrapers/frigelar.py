# scrapers/frigelar.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import re
from .base import BaseScraper

class FrigelarScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Frigelar] Iniciando Scraper (Sem Ficha Técnica)...")
            
            # --- Configuração Selenium ---
            opts = Options()
            opts.add_argument("--headless=new") 
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument('--ignore-certificate-errors')
            opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

            driver = webdriver.Chrome(options=opts)
            driver.get(self.url)

            # 1. Espera o título carregar
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "product-name"))
                )
            except:
                print("   [Frigelar] Aviso: Timeout esperando título.")

            # 2. Scroll para baixo (Essencial para carregar Descrição que usa Lazy Load)
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1200);")
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- 1. TÍTULO ---
            titulo = "Produto Frigelar"
            # <h1 class="product-name ...">
            h1 = soup.find("h1", class_="product-name")
            if h1: titulo = self.limpar_texto(h1.get_text())

            # --- 2. IMAGEM ---
            url_img = None
            # A imagem principal geralmente está num container ccResizeImage
            # O site usa caminhos relativos (/ccstore/v1/images/...)
            img_tag = soup.find("img", attrs={"data-bind": re.compile("ccResizeImage")})
            
            if not img_tag:
                # Fallback: pega a primeira imagem dentro da galeria principal
                img_tag = soup.find("div", id="prod-img-container").find("img") if soup.find("div", id="prod-img-container") else None

            if img_tag:
                src = img_tag.get("src") or img_tag.get("data-src")
                if src:
                    if src.startswith("/"):
                        url_img = "https://www.frigelar.com.br" + src
                    else:
                        url_img = src

            # --- 3. DESCRIÇÃO (Limpeza Cirúrgica) ---
            descricao_bruta = ""
            
            # Container: frigelar-product-description-section
            desc_container = soup.find("div", class_="frigelar-product-description-section")
            if desc_container:
                # Remove iframes (vídeos do youtube) antes de pegar o texto
                for iframe in desc_container.find_all("iframe"): iframe.extract()
                
                # Remove títulos de marketing como "Confira as Vantagens"
                for h in desc_container.find_all(["h1", "h2", "h3"]):
                    if "vantagens" in h.get_text().lower() or "confira" in h.get_text().lower():
                        h.extract()

                descricao_bruta = desc_container.get_text(separator="\n")

            descricao = self.limpar_descricao_cirurgica(descricao_bruta)

            # --- 4. FICHA TÉCNICA (REMOVIDA) ---
            specs = {} # Passa um dicionário vazio para não quebrar a geração do arquivo
            print("   [Frigelar] Especificações técnicas ignoradas conforme solicitado.")

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
                'total_imagens': 1,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   [ERRO FRIGELAR] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                driver.quit()

    def limpar_descricao_cirurgica(self, texto_bruto):
        """Remove apenas frases com termos proibidos, mantendo o resto."""
        if not texto_bruto: return "Descrição indisponível."

        texto_limpo = re.sub(r'\s+', ' ', texto_bruto).strip()
        
        # Divide por pontuação para analisar frase a frase
        frases = re.split(r'(?<=[.!?])\s+', texto_limpo)
        frases_aprovadas = []
        
        # Lista Negra baseada no seu pedido
        termos_proibidos = [
            "garantia", "meses", "confira as vantagens", "assista o vídeo",
            "código frigelar", "esconder produto", "fale conosco",
            "youtube", "inscreva-se", "preço", "oferta", "frete",
            "condições de pagamento", "boleto", "cartão", "entrega"
        ]

        for frase in frases:
            frase_lower = frase.lower()
            contem_proibido = False
            
            # Se a frase for muito curta (ex: "Benefícios"), ignora
            if len(frase) < 4:
                continue

            for termo in termos_proibidos:
                if termo in frase_lower:
                    contem_proibido = True
                    break
            
            if not contem_proibido:
                frases_aprovadas.append(frase)

        return "\n\n".join(frases_aprovadas)