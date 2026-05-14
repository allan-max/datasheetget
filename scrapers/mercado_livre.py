# scrapers/mercado_livre.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class MercadoLivreScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [ML] Iniciando Scraper (Bypass e Busca Profunda)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            # --- SETUP: A MÁGICA DE TIRAR O HEADLESS ---
            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            
            # Disfarce de User-Agent
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
            
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            
            # version_main=109 é CRÍTICO para o seu Windows Server 2012 R2
            driver = uc.Chrome(options=options, version_main=109)
            driver.minimize_window() 
            
            print(f"   [ML] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [ML] Aguardando renderização do produto...")
            try:
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
            except:
                print("   ⚠️ Aviso: O carregamento demorou muito. Forçando a leitura do HTML atual.")
            
            # --- SCROLL PROGRESSIVO (A CHAVE PARA CARREGAR A DESCRIÇÃO) ---
            print("   [ML] Rolando a página aos poucos para acionar a descrição (Lazy Load)...")
            # O ML só carrega a descrição se descermos devagar. São 5 descidas curtas.
            for i in range(1, 6):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(0.8)

            # Volta um pouco pro topo para garantir que o print da imagem depois saia direito
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            if "verifique que você não é um robô" in soup.get_text().lower() or "recaptcha" in soup.get_text().lower():
                print("   ❌ ERRO CRÍTICO: Bloqueado pelo Captcha do Mercado Livre.")

            # --- TÍTULO ---
            titulo = "Produto Mercado Livre"
            h1 = soup.find('h1', class_=re.compile(r'ui-pdp-title'))
            if not h1:
                h1 = soup.find('h1')
            
            if h1:
                titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO (Busca Ultra-Flexível) ---
            descricao = "Descrição indisponível."
            
            # Procura por qualquer elemento (seja p, div ou span) que tenha a classe da descrição
            desc_elem = soup.find(class_=re.compile(r'ui-pdp-description__content'))
            if not desc_elem:
                # Fallback para a caixa principal
                desc_elem = soup.find('div', class_=re.compile(r'ui-pdp-description'))
                
            if desc_elem:
                # Troca os <br> do HTML por quebras de linha reais
                for br in desc_elem.find_all("br"):
                    br.replace_with("\n")
                
                # O separator="\n" garante que os parágrafos não fiquem colados
                descricao_bruta = desc_elem.get_text(separator="\n", strip=True)
                
                if descricao_bruta and len(descricao_bruta) > 5:
                    descricao = self.limpar_lixo_comercial(descricao_bruta)
                    print("   ✅ Descrição capturada com sucesso.")
                else:
                    print("   ⚠️ Aviso: Bloco de descrição encontrado, mas estava vazio.")

            # --- IMAGEM ---
            print("   [ML] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            meta_img = soup.find('meta', property='og:image')
            if meta_img and meta_img.get('content'):
                url_img = meta_img['content']
            else:
                img_container = soup.find('img', class_=re.compile(r'ui-pdp-image'))
                if img_container:
                    src = img_container.get('src')
                    if src and "http" in src: url_img = src

            if url_img:
                print(f"   [ML] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [ML] Apelando para o Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "figure.ui-pdp-gallery__figure img, img.ui-pdp-image")
                    if el_img:
                        filename = f"temp_img_ml_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except Exception as e:
                    print(f"   ⚠️ Erro ao salvar imagem: {e}")

            # --- CARACTERÍSTICAS (Universal: Anúncio Clássico + Catálogo) ---
            specs = {}
            
            # TENTATIVA 1: O Padrão de Tabelas
            rows = soup.find_all('tr')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    chave = self.limpar_texto(th.get_text())
                    valor = self.limpar_texto(td.get_text())
                    if chave and valor:
                        specs[chave] = valor
            
            # TENTATIVA 2: Se não houver tabelas (Página de Catálogo Moderna)
            if len(specs) < 2:
                div_rows = soup.find_all('div', class_=re.compile(r'ui-pdp-specs__row|ui-vpp-striped-specs__row|andes-table__row'))
                for row in div_rows:
                    textos = row.find_all(['span', 'p', 'div'])
                    if len(textos) >= 2:
                        chave = self.limpar_texto(textos[0].get_text())
                        valor = self.limpar_texto(textos[-1].get_text())
                        if chave and valor and chave != valor:
                            specs[chave] = valor

            specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [ML] Gerando arquivos PDF/Word...")
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
            print(f"   ❌ [ERRO ML] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass