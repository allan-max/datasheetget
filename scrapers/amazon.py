# scrapers/amazon.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
from .base import BaseScraper
# teste
class AmazonScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            opts = Options()
            opts.add_argument("--headless=new") 
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument('--ignore-certificate-errors')
            opts.add_argument(f'user-agent={self.headers["User-Agent"]}')

            driver = webdriver.Chrome(options=opts)

            print(f"   [Amazon] Acessando: {self.url}")
            driver.get(self.url)
            time.sleep(5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            if "robot check" in soup.text.lower():
                raise Exception("Amazon bloqueou o acesso (Captcha detectado).")

            # Título
            titulo = soup.find(id="productTitle")
            titulo = titulo.text.strip() if titulo else "Amazon Produto"

            # Descrição (Busca Bullets e Descrição Longa)
            textos_desc = []
            
            # 1. Bullets (Sobre este item)
            bullets = soup.find(id="feature-bullets")
            if bullets:
                items = bullets.find_all("span", class_="a-list-item")
                for i in items:
                    textos_desc.append(i.text)
            
            # 2. Descrição Longa
            desc_longa = soup.find(id="productDescription")
            if desc_longa:
                textos_desc.append(desc_longa.text)

            descricao_unida = "\n".join(textos_desc)
            
            # --- APLICA A LIMPEZA ---
            descricao = self.limpar_lixo_comercial(descricao_unida)

            # Imagem
            img = soup.find(id="landingImage")
            url_img = img.get("src") if img else None

            # Specs
            specs = {}
            tables = soup.find_all("table", id="productDetails_techSpec_section_1")
            for table in tables:
                for row in table.find_all("tr"):
                    k = row.find("th")
                    v = row.find("td")
                    if k and v:
                        specs[k.text.strip()] = v.text.strip()
            
            # --- FILTRA AS SPECS ---
            specs = self.filtrar_specs(specs)
            if not specs: specs = {"Info": "Verificar descrição completa"}

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
            print(f"   [ERRO SELENIUM] {str(e)}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver: driver.quit()