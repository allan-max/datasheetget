# scrapers/tsshara.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class TSSharaScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [TS Shara] Iniciando Scraper...")
            
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
            
            # 1. ACESSO
            print(f"   [TS Shara] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            # Scroll para forçar carregamento das imagens (Lazy Load)
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1200);")
            time.sleep(1.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto TS Shara"
            h1 = soup.find("h1", class_="product-title")
            if h1:
                # Pega todos os spans ignorando o ID interno e as tags <i>
                spans = h1.find_all("span")
                if len(spans) > 1:
                    # O segundo span costuma ter o nome real sem o código "#4502"
                    titulo = self.limpar_texto(spans[1].contents[0] if spans[1].contents else spans[1].get_text())
                else:
                    titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- IMAGEM (PLANO DUPLO) ---
            print("   [TS Shara] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            # Tenta pegar pelo link em alta resolução no href do popup
            a_img = soup.find("a", class_=re.compile(r"popup-image"))
            if a_img and a_img.get("href"):
                url_img = a_img.get("href")
            else:
                # Fallback para a tag img normal
                img_tag = soup.find("img", class_=re.compile(r"litespeed-loaded|lazyloaded"))
                if img_tag:
                    url_img = img_tag.get("data-src") or img_tag.get("src")
            
            if url_img:
                print(f"   [TS Shara] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # Se o download falhar, tenta screenshot
            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [TS Shara] Apelando para captura de tela da imagem...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "a.popup-image img, .product-image img")
                    if el_img:
                        filename = f"temp_img_tsshara_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1.5)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except Exception as e:
                    print(f"   ⚠️ Erro ao salvar imagem: {e}")

            # --- DESCRIÇÃO ---
            descricao = "Descrição indisponível."
            desc_div = soup.find("div", class_="product-content")
            if desc_div:
                # Remove divs com scripts inúteis que o site injeta
                for lixo in desc_div.find_all("div", style=re.compile(r"z-index: 2147483647")):
                    lixo.decompose()
                    
                for br in desc_div.find_all("br"):
                    br.replace_with("\n")
                
                texto_bruto = desc_div.get_text(separator=" ")
                linhas = [line.strip() for line in texto_bruto.split('\n') if len(line.strip()) > 0]
                texto_limpo = "\n".join(linhas)
                
                descricao = self.limpar_lixo_comercial(texto_limpo)

            # --- FICHA TÉCNICA (COM EXCLUSÃO DE "ATENÇÃO" E GARANTIA) ---
            specs = {}
            tab_div = soup.find("div", id="tab-1")
            if not tab_div:
                tab_div = soup.find("div", class_=re.compile(r"tabs-panel"))
                
            if tab_div:
                # DESTRUIDOR DO AVISO "ATENÇÃO / ONDA PWM"
                nota = tab_div.find("div", class_="product-note")
                if nota:
                    nota.decompose() # Evapora este bloco do HTML antes de ler
                    
                lis = tab_div.find_all("li")
                lista_destaques = []
                
                # Termos proibidos extras (além dos do base.py) para TS Shara
                termos_extras = ["nota fiscal", "faturamento", "condição de pagamento", "faturado", "imposto"]
                
                for li in lis:
                    txt = self.limpar_texto(li.get_text())
                    if txt:
                        txt_lower = txt.lower()
                        tem_lixo = False
                        
                        # Verifica se existe venda, garantia ou pagamento nesta bolinha
                        for termo in self.termos_proibidos + termos_extras:
                            if termo in txt_lower:
                                tem_lixo = True
                                break
                        
                        # Se for limpo, entra no Datasheet
                        if not tem_lixo:
                            lista_destaques.append(f"- {txt}")
                
                if lista_destaques:
                    specs["Especificações Técnicas"] = "\n".join(lista_destaques)
            
            print(f"   ✅ Especificações filtradas e capturadas.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [TS Shara] Gerando arquivos finais...")
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
            print(f"   ❌ [ERRO TS SHARA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass