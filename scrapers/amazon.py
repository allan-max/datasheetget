# scrapers/amazon.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
#teste
from .base import BaseScraper

class AmazonScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            # undetected_chromedriver como nos outros scrapers: o Selenium puro
            # era reconhecido pela Amazon, que devolvia a página "Continuar
            # comprando" (3 KB) sem produto nenhum.
            opts = uc.ChromeOptions()
            opts.add_argument("--headless=new") 
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument('--ignore-certificate-errors')
            opts.page_load_strategy = 'eager'

            # CRÍTICO: Versão 109 para rodar no Windows Server 2012 R2
            driver = uc.Chrome(options=opts, version_main=109)

            print(f"   [Amazon] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            time.sleep(5)

            # A Amazon BR às vezes mete uma página intermédia com o botão
            # "Continuar comprando". Clica-se e volta-se ao link do produto.
            for tentativa in range(2):
                if "validateCaptcha" not in driver.page_source: break
                print("   [Amazon] Página 'Continuar comprando'; a clicar e a voltar ao produto...")
                try:
                    driver.find_element(By.CSS_SELECTOR, "form[action*='validateCaptcha'] button").click()
                    time.sleep(3)
                except Exception: pass
                driver.get(self.url)
                time.sleep(5)

            # A secção "Informações do produto" só carrega depois de descer a página.
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            if "robot check" in soup.text.lower() or "validateCaptcha" in driver.page_source:
                raise Exception("Amazon bloqueou o acesso (Captcha detectado).")
            if not soup.find(id="productTitle"):
                # Antes saía um datasheet vazio chamado "Amazon Produto" com sucesso=True.
                raise Exception(f"Produto não encontrado na página ({len(driver.page_source)} bytes)")

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

            # Imagem: o data-old-hires é a versão grande; o src é a miniatura.
            img = soup.find(id="landingImage")
            url_img = (img.get("data-old-hires") or img.get("src")) if img else None

            # Specs. A Amazon BR não usa o productDetails_techSpec_section_1: a
            # ficha está nas tabelas do #prodDetails ("Informações do produto"),
            # com reserva no #productOverview_feature_div e nos detailBullets.
            specs = {}
            # As tabelas repetem chaves só com maiúsculas diferentes ("Marca" e
            # "Nome da marca" não, mas "Cor" e "COR" sim); fica a primeira.
            ja_tem = lambda chave: chave.lower() in [c.lower() for c in specs]
            for container_id in ["prodDetails", "productDetails_techSpec_section_1",
                                 "productDetails_detailBullets_sections1", "productOverview_feature_div"]:
                container = soup.find(id=container_id)
                if not container: continue
                for row in container.find_all("tr"):
                    k = row.find("th") or row.find("td")
                    v = row.find_all("td")[-1] if row.find_all("td") else None
                    if k and v and k is not v:
                        chave = self.limpar_texto(k.get_text())
                        valor = self.limpar_texto(v.get_text())
                        if chave and valor and not ja_tem(chave):
                            specs[chave] = valor
            for li in (soup.find(id="detailBullets_feature_div") or soup.new_tag("div")).find_all("li"):
                partes = li.find_all("span")
                if len(partes) >= 3:
                    chave = self.limpar_texto(partes[1].get_text()).rstrip(":").strip()
                    valor = self.limpar_texto(partes[2].get_text())
                    if chave and valor and not ja_tem(chave):
                        specs[chave] = valor
            # Códigos internos da Amazon e ranking não são ficha técnica.
            for lixo in ["ASIN", "UPC", "Número de identificação de comércio internacional",
                         "Ranking dos mais vendidos", "Avaliações de clientes", "Escala"]:
                specs.pop(lixo, None)
            
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
                'total_imagens': 1 if url_img else 0,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   [ERRO SELENIUM] {str(e)}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver: driver.quit()