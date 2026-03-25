# scrapers/casasbahia.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class CasasBahiaScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Casas Bahia] Iniciando Scraper...")
            
            # --- SETUP (Proteção Server 2012 R2) ---
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--window-size=1920,3000") # Tela mais longa para caber tudo
            
            options.add_argument("--no-sandbox") 
            options.add_argument("--disable-dev-shm-usage") 
            options.add_argument("--disable-gpu") 
            
            driver = uc.Chrome(options=options, version_main=109)
            
            # 1. ACESSO
            print(f"   [Casas Bahia] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            # Scroll em etapas para forçar o carregamento dinâmico (Lazy Load)
            driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1200);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 2000);")
            time.sleep(1)

            # 2. INTERAÇÃO (CLICAR NAS SANFONAS)
            print("   [Casas Bahia] Abrindo menus de Descrição e Ficha Técnica...")
            try:
                # Tenta achar e clicar no botão de Descrição
                desc_btns = driver.find_elements(By.XPATH, "//p[contains(text(), 'Descrição do produto')]/parent::button | //p[contains(text(), 'Descrição do produto')]")
                for btn in desc_btns:
                    driver.execute_script("arguments[0].click();", btn)
                
                time.sleep(1) # Espera a animação abrir
                
                # Tenta achar e clicar no botão de Especificações
                specs_btns = driver.find_elements(By.XPATH, "//p[contains(text(), 'Especificações Técnicas')]/parent::button | //p[contains(text(), 'Especificações Técnicas')]")
                for btn in specs_btns:
                    driver.execute_script("arguments[0].click();", btn)
                    
                time.sleep(1.5) # Espera os dados carregarem no HTML
            except Exception as e:
                print(f"   ⚠️ Aviso: Não foi possível clicar nos botões, tentando ler o que já está na tela.")

            # 3. EXTRAÇÃO
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Casas Bahia"
            h1 = soup.find("h1", class_=re.compile(r"dsvia-heading"))
            if h1:
                titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- IMAGEM (PLANO DUPLO) ---
            print("   [Casas Bahia] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            # Busca a imagem principal pela tag 'data-testid'
            img_tag = soup.find("img", attrs={"data-testid": "gallery-image"})
            if img_tag and img_tag.get("src"):
                url_img = img_tag.get("src")
                print(f"   [Casas Bahia] URL da imagem encontrada: {url_img}")
                
                # Tentativa 1: Download Oculto
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # Tentativa 2: Screenshot Direto
            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Casas Bahia] Apelando para o Screenshot da imagem...")
                try:
                    el_img = None
                    try:
                        el_img = driver.find_element(By.CSS_SELECTOR, "img[data-testid='gallery-image']")
                    except:
                        pass
                    
                    if el_img:
                        filename = f"temp_img_cb_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1.5)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except Exception as e:
                    print(f"   ⚠️ Erro ao salvar imagem: {e}")

            # --- DESCRIÇÃO ---
            descricao = "Descrição indisponível."
            desc_div = soup.find("div", id="product-description")
            if desc_div:
                # Troca <br> por quebras de linha reais
                for br in desc_div.find_all("br"):
                    br.replace_with("\n")
                
                # O separator=' ' evita que as tags <strong> fiquem grudadas com o texto normal
                texto_bruto = desc_div.get_text(separator=" ")
                linhas = [line.strip() for line in texto_bruto.split('\n') if len(line.strip()) > 0]
                texto_limpo = "\n".join(linhas)
                
                descricao = self.limpar_lixo_comercial(texto_limpo)

            # --- FICHA TÉCNICA ---
            specs = {}
            # Baseado no seu HTML, a Casas Bahia coloca cada linha num display flex com 'dsvia-base-div'
            linhas_specs = soup.find_all("div", attrs={"display": "flex", "data-testid": "dsvia-base-div"})
            
            for linha in linhas_specs:
                p_tag = linha.find("p") # Chave (ex: Conectividade)
                span_tag = linha.find("span") # Valor (ex: Bluetooth, Wi-Fi)
                
                if p_tag and span_tag:
                    chave = self.limpar_texto(p_tag.get_text())
                    valor = self.limpar_texto(span_tag.get_text())
                    
                    if chave and valor:
                        specs[chave] = valor
            
            # Passa no seu filtro contra a palavra "garantia" e lixos comerciais
            specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [Casas Bahia] Gerando arquivos finais...")
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
            print(f"   ❌ [ERRO CASAS BAHIA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass