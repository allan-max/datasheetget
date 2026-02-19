# scrapers/weg.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
from .base import BaseScraper

class WegScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [WEG] Iniciando Scraper (V8 - Híbrido: Tabela + Texto)...")
            
            # --- CONFIGURAÇÃO ---
            opts = Options()
            opts.add_argument("--headless=new") 
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

            driver = webdriver.Chrome(options=opts)
            
            print(f"   [WEG] Acessando: {self.url}")
            driver.get(self.url)
            
            # Espera carregar
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1.product-card-title"))
                )
            except:
                print("   ⚠️ Timeout título. Prosseguindo...")

            # --- IMAGEM (CAPTURA URL) ---
            url_img = None
            try:
                zoom_link = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a.xtt-product-image-zoom"))
                )
                url_img = zoom_link.get_attribute("href")
            except:
                try:
                    img_tag = driver.find_element(By.CSS_SELECTOR, "div.col-sm-6 img")
                    url_img = img_tag.get_attribute("src")
                except: pass

            if url_img and not url_img.startswith("http"):
                 url_img = "https://static.weg.net" + url_img if url_img.startswith("/") else url_img

            print(f"   [DEBUG] Imagem: {url_img}")

            # --- EXTRAÇÃO DE TEXTO ---
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # Título
            titulo = "Produto WEG"
            h1 = soup.find("h1", class_="product-card-title")
            if h1: titulo = self.limpar_texto(h1.get_text())

            # Descrição
            descricao = "Descrição indisponível."
            div_desc = soup.find("div", class_="xtt-product-description")
            if div_desc:
                descricao = div_desc.get_text(separator="\n", strip=True)

            # --- FICHA TÉCNICA HÍBRIDA ---
            specs = {}

            # MODO 1: Extração via Tabelas (Padrão Baterias/Automação)
            tabelas = soup.find_all("table", class_="table")
            for tabela in tabelas:
                linhas = tabela.find_all("tr")
                for linha in linhas:
                    for input_tag in linha.find_all("input"):
                        input_tag.decompose()
                    th = linha.find("th")
                    td = linha.find("td")
                    if th and td:
                        k = self.limpar_texto(th.get_text())
                        v = self.limpar_texto(td.get_text())
                        if k and v and k != "&nbsp;":
                            specs[k] = v

            # MODO 2: Extração via Texto CMS (Padrão Redutores/Motorredutores)
            # Procura divs com a classe 'yCmsComponent' que contenham "Dados Técnicos"
            divs_cms = soup.find_all("div", class_="yCmsComponent")
            for div in divs_cms:
                texto_div = div.get_text()
                
                # Só processa se tiver indício de ser specs
                if "Dados Técnicos" in texto_div or "Disposição dos eixos" in texto_div:
                    paragrafos = div.find_all("p")
                    for p in paragrafos:
                        texto_p = p.get_text(" ", strip=True) # Usa espaço para não colar palavras
                        
                        # Lógica: Se tem ":" é provavelmente Chave: Valor
                        if ":" in texto_p:
                            partes = texto_p.split(":", 1)
                            chave = self.limpar_texto(partes[0])
                            valor = self.limpar_texto(partes[1])
                            
                            # Filtra o próprio título "Dados Técnicos" para não entrar na lista
                            if "dados técnicos" in chave.lower():
                                continue
                            
                            if chave and valor:
                                specs[chave] = valor

            # --- DOWNLOAD VIA NAVEGAÇÃO (MÉTODO V7 BLINDADO) ---
            caminho_imagem = self.baixar_imagem_navegando(driver, url_img)

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
                'total_imagens': 1,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   [ERRO WEG] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                driver.quit()

    def baixar_imagem_navegando(self, driver, url):
        """Abre nova aba, vai até a imagem e tira screenshot (Anti-403)"""
        if not url: return None
        try:
            print(f"   [DOWNLOAD] Navegando até a imagem: {url}")
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get(url)
            
            try:
                img_element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "img"))
                )
                
                ext = "jpg"
                if "png" in url.lower(): ext = "png"
                if "webp" in url.lower(): ext = "webp"
                filename = f"temp_img_weg.{ext}"
                caminho = os.path.join(self.pasta_saida if hasattr(self, 'pasta_saida') else "output", filename)
                
                img_element.screenshot(caminho)
                
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
                return caminho
                
            except Exception as e:
                print(f"   ⚠️ Erro render imagem: {e}")
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
                return None

        except Exception as e:
            print(f"   ⚠️ Erro navegação img: {e}")
            try: driver.switch_to.window(driver.window_handles[0])
            except: pass
            return None