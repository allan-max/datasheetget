# scrapers/elgin.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class ElginScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Elgin] A iniciar Scraper...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            # --- SETUP (Proteção Server 2012 R2) ---
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
            
            # 1. ACESSO
            print(f"   [Elgin] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            # Scroll para forçar o carregamento dinâmico (VTEX Lazy Load)
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1.5)
            driver.execute_script("window.scrollTo(0, 1600);")
            time.sleep(1.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Elgin"
            h1 = soup.find("h1", class_=re.compile(r"productNameContainer"))
            if h1:
                span = h1.find("span", class_=re.compile(r"productBrand"))
                if span:
                    titulo = self.limpar_texto(span.get_text())
                else:
                    titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- IMAGEM (PLANO DUPLO) ---
            print("   [Elgin] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_tag = soup.find("img", class_=re.compile(r"productImageTag--main"))
            if img_tag and img_tag.get("src"):
                url_img = img_tag.get("src")
                print(f"   [Elgin] URL da imagem encontrada: {url_img}")
                # Tentativa 1: Download Oculto
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # Tentativa 2: Screenshot Direto (se o download falhar)
            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Elgin] A apelar para a captura de ecrã da imagem...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[class*='productImageTag--main']")
                    if el_img:
                        filename = f"temp_img_elgin_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1.5)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem guardada via captura de ecrã!")
                except Exception as e:
                    print(f"   ⚠️ Erro ao guardar imagem: {e}")

            # --- DESCRIÇÃO ---
            descricao = "Descrição indisponível."
            # A Elgin escreveu "DescriptonLong" (faltou o 'i' no HTML deles), então usamos Regex para prevenir
            desc_div = soup.find("div", class_=re.compile(r"DescriptonLong|text tc"))
            if desc_div:
                for br in desc_div.find_all("br"):
                    br.replace_with("\n")
                
                texto_bruto = desc_div.get_text(separator=" ")
                linhas = [line.strip() for line in texto_bruto.split('\n') if len(line.strip()) > 0]
                texto_limpo = "\n".join(linhas)
                
                descricao = self.limpar_lixo_comercial(texto_limpo)

            # --- FICHA TÉCNICA (COMBINADA) ---
            specs = {}
            
            # Parte 1: Especificações Padrão (s-item)
            s_items = soup.find_all("div", class_="s-item")
            for item in s_items:
                nome_div = item.find("div", class_=re.compile(r"specificationName"))
                valor_div = item.find("div", class_=re.compile(r"specificationValue"))
                
                if nome_div and valor_div:
                    chave = self.limpar_texto(nome_div.get_text())
                    valor = self.limpar_texto(valor_div.get_text())
                    if chave and valor:
                        specs[chave] = valor

            # Parte 2: Tópicos de Características (descriptionShort) COM FILTRO INDIVIDUAL
            char_div = soup.find("div", class_="descriptionShort")
            if char_div:
                ul = char_div.find("ul")
                if ul:
                    lis = ul.find_all("li")
                    lista_destaques = []
                    for li in lis:
                        txt = self.limpar_texto(li.get_text())
                        if txt:
                            # Faz a verificação contra a sua lista de termos proibidos ANTES de adicionar
                            txt_lower = txt.lower()
                            tem_lixo = False
                            for termo in self.termos_proibidos:
                                if termo in txt_lower:
                                    tem_lixo = True
                                    break
                            
                            # Se a linha não tiver palavras de garantia/venda, ela entra na lista
                            if not tem_lixo:
                                lista_destaques.append(f"- {txt}")
                    
                    if lista_destaques:
                        specs["Principais Características"] = "\n".join(lista_destaques)
            
            # Filtra lixo comercial (Garantia, frete, etc)
            specs = self.filtrar_specs(specs)
            print(f"   ✅ Especificações encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [Elgin] A gerar ficheiros finais...")
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
            print(f"   ❌ [ERRO ELGIN] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass