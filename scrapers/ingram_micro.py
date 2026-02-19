# scrapers/ingrammicro.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import time
import os
import requests
from .base import BaseScraper

class IngramMicroScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Ingram Micro] Iniciando Scraper (V19 - Timeout Tático)...")
            
            # --- SETUP ---
            if not hasattr(self, 'pasta_saida'): self.pasta_saida = "output"
            if not os.path.exists(self.pasta_saida): os.makedirs(self.pasta_saida)

            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            # Eager: Espera o HTML carregar, mas não imagens pesadas
            options.page_load_strategy = 'eager' 
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.add_argument("--window-size=1920,1080")

            driver = uc.Chrome(options=options, version_main=144)
            
            # 1. ACESSO COM TIMEOUT CONTROLADO
            print(f"   [Ingram] Acessando: {self.url}")
            
            # Define limite rígido de 15 segundos
            driver.set_page_load_timeout(15)
            
            try:
                driver.get(self.url)
            except TimeoutException:
                print("   ⚠️ Timeout de 15s atingido (Isso é bom! Cortamos scripts lentos).")
                # O comando stop garante que o navegador pare de girar
                try: driver.execute_script("window.stop();")
                except: pass
            
            # Espera inteligente pelo Título (garante que o conteúdo útil carregou)
            print("   [Ingram] Aguardando renderização do conteúdo...")
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: d.find_element(By.TAG_NAME, "h1") or \
                              d.find_element(By.CLASS_NAME, "product-name")
                )
            except:
                print("   ⚠️ Aviso: Título principal demorou a aparecer.")

            # 2. INTERAÇÃO (Expandir Abas)
            try:
                # Procura abas de especificações e clica
                abas = driver.find_elements(By.XPATH, "//*[contains(@class, 'MuiTab') or contains(text(), 'Especifica')]")
                for aba in abas:
                    if aba.is_displayed():
                        driver.execute_script("arguments[0].click();", aba)
                        time.sleep(0.5)
            except: pass

            # 3. EXTRAÇÃO
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Ingram"
            h1 = soup.find("h1")
            if h1:
                titulo = self.limpar_texto(h1.get_text())
            else:
                # Tentativas extras
                candidates = soup.find_all(class_=lambda c: c and ("product-name" in c or "title" in c))
                for c in candidates:
                    if len(c.get_text()) > 10:
                        titulo = self.limpar_texto(c.get_text())
                        break
            
            print(f"   [DEBUG] Título: {titulo}")

            # --- IMAGEM (Download Autenticado) ---
            caminho_imagem = None
            url_img = None
            
            print("   [Ingram] Buscando imagem...")
            imgs = soup.find_all("img")
            for img in imgs:
                src = img.get("src", "")
                if "pimcontent" in src or "assets/images/product" in src:
                    url_img = src
                    break
            
            if not url_img:
                # Fallback: pega a maior imagem da tela
                try:
                    imgs_el = driver.find_elements(By.TAG_NAME, "img")
                    for el in imgs_el:
                        if el.size['width'] > 250:
                            url_img = el.get_attribute("src")
                            break
                except: pass

            if url_img:
                if url_img.startswith("//"): url_img = "https:" + url_img
                # DOWNLOAD COM COOKIES DO SELENIUM
                caminho_imagem = self.baixar_imagem_com_cookies(driver, url_img)
                if caminho_imagem:
                    print(f"   ✅ Imagem salva: {os.path.basename(caminho_imagem)}")
            else:
                print("   ⚠️ URL da imagem não encontrada.")

            # --- DESCRIÇÃO ---
            descricao = "Descrição indisponível."
            # Tenta pegar a descrição longa
            divs = soup.find_all("div")
            # Ordena divs por quantidade de texto (descrições costumam ser grandes)
            divs_com_texto = sorted([d for d in divs if 200 < len(d.get_text()) < 5000], key=lambda x: len(x.get_text()), reverse=True)
            
            if divs_com_texto:
                # Pega a maior, mas verifica se não é lixo (menu/footer)
                cand = divs_com_texto[0].get_text(separator="\n", strip=True)
                if "termos de uso" not in cand.lower():
                    descricao = cand[:2000] # Limita tamanho

            # --- SPECS ---
            specs = {}
            tabelas = soup.find_all("table")
            for t in tabelas:
                rows = t.find_all("tr")
                for r in rows:
                    cols = r.find_all(["td", "th"])
                    if len(cols) == 2:
                        k = self.limpar_texto(cols[0].get_text())
                        v = self.limpar_texto(cols[1].get_text())
                        if k and v: specs[k] = v
            
            # Se não achou tabelas, tenta listas LI
            if not specs:
                lis = soup.find_all("li")
                for li in lis:
                    txt = li.get_text()
                    if ":" in txt and len(txt) < 100:
                        parts = txt.split(":", 1)
                        specs[parts[0].strip()] = parts[1].strip()

            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO ---
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
            print(f"   ❌ [ERRO INGRAM] {e}")
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    # Função auxiliar para baixar imagem usando a sessão do Selenium
    def baixar_imagem_com_cookies(self, driver, url):
        try:
            # Pega cookies do navegador e passa para o Requests
            s = requests.Session()
            selenium_cookies = driver.get_cookies()
            for cookie in selenium_cookies:
                s.cookies.set(cookie['name'], cookie['value'])
            
            # Tenta simular um User-Agent real
            s.headers.update({
                "User-Agent": driver.execute_script("return navigator.userAgent;")
            })
            
            resp = s.get(url, timeout=10)
            if resp.status_code == 200:
                ext = "jpg" if ".jpg" in url else "png"
                filename = f"temp_img_ingram.{ext}"
                caminho = os.path.join(self.pasta_saida, filename)
                with open(caminho, 'wb') as f:
                    f.write(resp.content)
                return caminho
        except: return None
        return None