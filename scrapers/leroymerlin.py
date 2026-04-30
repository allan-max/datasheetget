# scrapers/leroymerlin.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class LeroyMerlinScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Leroy Merlin] Iniciando Scraper (Bypass Anti-Bot e Filtro de Propagandas)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            # --- SETUP: BYPASS DE FIREWALL COM JANELA MINIMIZADA ---
            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            
            # Disfarce de User-Agent moderno
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
            
            options.add_argument("--no-sandbox") 
            options.add_argument("--disable-dev-shm-usage") 
            options.add_argument("--disable-gpu") 
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.minimize_window() # Minimiza para não atrapalhar no Servidor
            
            # 1. ACESSO
            print(f"   [Leroy Merlin] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            print("   [Leroy Merlin] Aguardando carregamento da página...")
            time.sleep(5) # Espera o desafio de segurança passar

            driver.maximize_window() # Maximiza rapidamente para a foto

            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
            except:
                print("   ⚠️ Aviso: Título demorou, continuando com o que carregou.")

            # Scroll para forçar carregamento de imagens preguiçosas (Lazy Load)
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(1.5)

            # 3. EXTRAÇÃO
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            if "access denied" in soup.get_text().lower() or "cloudflare" in soup.get_text().lower():
                print("   ❌ ERRO: Bloqueado pelo firewall da Leroy Merlin.")

            # --- TÍTULO ---
            titulo = "Produto Leroy Merlin"
            h1 = soup.find("h1")
            if h1:
                titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- IMAGEM (PLANO DUPLO) ---
            print("   [Leroy Merlin] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            # A Leroy Merlin usa tags <img> com data-nimg ou fetchpriority
            img_tag = soup.find("img", attrs={"fetchpriority": "high"})
            if not img_tag:
                img_tags = soup.find_all("img")
                for img in img_tags:
                    alt_text = img.get("alt", "")
                    # Procura a imagem que tenha o mesmo texto alternativo do título
                    if titulo.lower() in alt_text.lower():
                        img_tag = img
                        break

            if img_tag and img_tag.get("src"):
                url_img = img_tag.get("src")
                print(f"   [Leroy Merlin] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # Se falhar o download, tira print
            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Leroy Merlin] Apelando para o Screenshot da imagem...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "div[data-is-active='true'] img, img[fetchpriority='high']")
                    if el_img:
                        filename = f"temp_img_leroy_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1.5)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except Exception as e:
                    print(f"   ⚠️ Erro ao salvar imagem: {e}")

            # --- DESCRIÇÃO (COM LIMPEZA AGRESSIVA) ---
            descricao = "Descrição indisponível."
            desc_div = soup.find("div", id="descricao-do-produto")
            
            if desc_div:
                # 1. Remove scripts/estilos
                for tag in desc_div(["script", "style"]):
                    tag.decompose()
                
                # 2. Destruidor de propagandas da Leroy Merlin
                # Adicionamos os termos da Leroy à sua lista de proibidos
                termos_leroy = ["leroy merlin", "instalação", "instala", "fidelidade", "aproveite", "receba em sua casa", "garantia", "parcelamento", "contrate"]
                termos_verificacao = self.termos_proibidos + termos_leroy
                
                # Vamos apagar apenas as tags de texto (p, h2, h3, h4, li) que contenham a propaganda,
                # para não apagar a div inteira sem querer.
                for el in desc_div.find_all(["p", "h2", "h3", "h4", "li", "span", "strong", "em"]):
                    texto_el = el.get_text().lower()
                    if any(termo in texto_el for termo in termos_verificacao):
                        try: el.decompose() 
                        except: pass
                
                # 3. Formatação
                for br in desc_div.find_all("br"):
                    br.replace_with("\n")
                
                texto_bruto = desc_div.get_text(separator="\n", strip=True)
                linhas = [line.strip() for line in texto_bruto.split('\n') if len(line.strip()) > 0]
                texto_limpo = "\n".join(linhas)
                
                descricao = self.limpar_lixo_comercial(texto_limpo)
                print("   ✅ Descrição capturada e limpa com sucesso.")

            # --- FICHA TÉCNICA (TABELA) ---
            specs = {}
            # A Leroy Merlin guarda as specs numa <table>
            tabelas = soup.find_all("table")
            for tabela in tabelas:
                linhas_tr = tabela.find_all("tr")
                for linha in linhas_tr:
                    th = linha.find("th")
                    td = linha.find("td")
                    
                    if th and td:
                        chave = self.limpar_texto(th.get_text())
                        valor = self.limpar_texto(td.get_text())
                        
                        # Filtro contra campos de garantia e manutenção na Ficha Técnica
                        ignorar = False
                        termos_proibidos_specs = ["garantia", "manutenção", "conservação", "assistência", "sac"]
                        if any(t in chave.lower() or t in valor.lower() for t in termos_proibidos_specs):
                            ignorar = True
                            
                        if not ignorar and chave and valor:
                            specs[chave] = valor
            
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [Leroy Merlin] Gerando arquivos finais...")
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
            print(f"   ❌ [ERRO LEROY MERLIN] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass