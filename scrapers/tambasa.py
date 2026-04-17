# scrapers/tambasa.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class TambasaScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Tambasa] Iniciando Scraper...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            # --- SETUP (Proteção Server 2012 R2 - V109) ---
            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--window-size=1920,3000")
            
            options.add_argument("--no-sandbox") 
            options.add_argument("--disable-dev-shm-usage") 
            options.add_argument("--disable-gpu") 
            
            driver = uc.Chrome(options=options, version_main=109)
            
            # 1. ACESSO COM TRATAMENTO DE TIMEOUT
            print(f"   [Tambasa] Acessando: {self.url}")
            driver.set_page_load_timeout(20)
            
            try:
                driver.get(self.url)
            except TimeoutException:
                print("   [Tambasa] Aviso: A página demorou muito, forçando a extração do que já carregou!")
            except Exception as e:
                print(f"   [Tambasa] Erro de rede: {e}")

            # Scroll rápido para renderizar imagens preguiçosas
            try:
                driver.execute_script("window.scrollTo(0, 600);")
                time.sleep(1)
            except: pass

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Tambasa"
            h1 = soup.find("h1", class_=re.compile(r"product-name"))
            if h1:
                titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- IMAGEM (PLANO DUPLO COM TRATAMENTO DE URL RELATIVA) ---
            print("   [Tambasa] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_tag = soup.find("img", class_=re.compile(r"product-detail__large-image"))
            if img_tag:
                # Tenta pegar a imagem com zoom (melhor resolução), senão pega o src normal
                src = img_tag.get("data-zoom-image") or img_tag.get("src")
                if src:
                    # Se o link começar com '/', precisamos adicionar o domínio base
                    if src.startswith("/"):
                        url_img = "https://tambasa.com" + src
                    else:
                        url_img = src

            if url_img:
                print(f"   [Tambasa] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Tambasa] Apelando para captura de tela da imagem...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img.product-detail__large-image")
                    if el_img:
                        filename = f"temp_img_tambasa_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1.5)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except Exception as e:
                    print(f"   ⚠️ Erro ao salvar imagem: {e}")

           # --- DESCRIÇÃO (COM LIMPEZA PROFUNDA DE LIXO COMERCIAL) ---
            descricao = "Descrição indisponível."
            desc_div = soup.find("div", class_="product-detail__descriptions-text")
            
            if desc_div:
                # 1. Remove códigos e scripts ocultos
                for tag in desc_div(["script", "style", "meta"]):
                    tag.decompose()
                
                # 2. Destruidor de parágrafos comerciais (Garantia, Nota Fiscal, etc.)
                termos_extras = ["nota fiscal", "faturamento", "condição de pagamento", "faturado", "imposto", "garantia", "boleto", "cartão", "frete"]
                termos_verificacao = self.termos_proibidos + termos_extras
                
                # CORREÇÃO AQUI: Removi a tag "div" para ele não apagar o bloco principal inteiro!
                # Agora ele só deleta linhas específicas (p, li, h2, h3, h4, span, strong)
                for el in desc_div.find_all(["p", "li", "h2", "h3", "h4", "span", "strong"]):
                    texto_el = el.get_text().lower()
                    if any(termo in texto_el for termo in termos_verificacao):
                        el.decompose() # Evapora apenas a frase que tem o lixo comercial
                
                # 3. Formata o que sobrou
                for br in desc_div.find_all("br"):
                    br.replace_with("\n")
                
                # Usa \n como separador para não grudar as frases
                texto_bruto = desc_div.get_text(separator="\n", strip=True)
                linhas = [line.strip() for line in texto_bruto.split('\n') if len(line.strip()) > 0]
                texto_limpo = "\n".join(linhas)
                
                descricao = self.limpar_lixo_comercial(texto_limpo)

            # --- FICHA TÉCNICA (ATRIBUTOS) ---
            specs = {}
            attr_container = soup.find("div", class_="product-detail__descriptions-attributes")
            
            if attr_container:
                atributos = attr_container.find_all("div", class_="product-detail__attribute")
                for attr in atributos:
                    title_span = attr.find("span", class_="product-detail__attribute-title")
                    
                    # O valor pode estar num span ou numa tag <a> (como a marca)
                    text_span = attr.find("span", class_="product-detail__attribute-text")
                    if not text_span:
                        text_span = attr.find("a", class_=re.compile(r"product-detail__attribute-text"))
                        
                    if title_span and text_span:
                        chave = self.limpar_texto(title_span.get_text())
                        valor = self.limpar_texto(text_span.get_text())
                        
                        # Passa pelo filtro final contra vendas/garantia
                        ignorar = False
                        for termo in termos_verificacao:
                            if termo in chave.lower() or termo in valor.lower():
                                ignorar = True
                                break
                                
                        if not ignorar and chave and valor:
                            specs[chave] = valor
                            
            print(f"   ✅ Especificações filtradas e capturadas: {len(specs)} itens.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [Tambasa] Gerando arquivos finais...")
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
            print(f"   ❌ [ERRO TAMBASA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass