# scrapers/madeiramadeira.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class MadeiraMadeiraScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [MadeiraMadeira] Iniciando Scraper (Bypass Anti-Bot e Filtro Rigoroso)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            # --- SETUP: BYPASS COM JANELA MINIMIZADA ---
            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            
            # Disfarce de User-Agent
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
            
            options.add_argument("--no-sandbox") 
            options.add_argument("--disable-dev-shm-usage") 
            options.add_argument("--disable-gpu") 
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.minimize_window()
            
            # 1. ACESSO
            print(f"   [MadeiraMadeira] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            print("   [MadeiraMadeira] Aguardando carregamento da página...")
            time.sleep(5) # Espera o desafio de segurança passar

            driver.maximize_window() # Maximiza rapidamente para renderizar tudo corretamente

            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
            except:
                print("   ⚠️ Aviso: Título demorou, continuando com o que carregou.")

            # Scroll em etapas
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(1.5)

            # 2. INTERAÇÃO (CLICAR EM 'VER MAIS CARACTERÍSTICAS')
            print("   [MadeiraMadeira] Expandindo especificações técnicas...")
            driver.execute_script("""
                try {
                    var btn = document.querySelector('button[data-testid="product_characteristics-button-see_more_characteristics"]');
                    if(btn) btn.click();
                } catch(e) {}
            """)
            time.sleep(1.5)

            # 3. EXTRAÇÃO
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto MadeiraMadeira"
            h1 = soup.find("h1")
            if h1:
                titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- IMAGEM (PLANO DUPLO) ---
            print("   [MadeiraMadeira] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            # Tenta pegar a imagem principal do carrossel
            img_tag = soup.find("img", attrs={"fetchpriority": "high", "data-nimg": "1"})
            if not img_tag:
                img_tag = soup.find("img", class_=re.compile(r"carousel", re.I))
                
            if img_tag and img_tag.get("src"):
                url_img = img_tag.get("src")
                print(f"   [MadeiraMadeira] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # Se falhar o download, tira print da galeria
            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [MadeiraMadeira] Apelando para o Screenshot da imagem...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "li[data-index='0'] img, img[fetchpriority='high']")
                    if el_img:
                        filename = f"temp_img_madeira_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1.5)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except Exception as e:
                    print(f"   ⚠️ Erro ao salvar imagem: {e}")

            # --- DESCRIÇÃO (COM LIMPEZA AGRESSIVA) ---
            descricao = "Descrição indisponível."
            desc_div = soup.find("div", attrs={"data-testid": "product_information-container-product_description"})
            
            if desc_div:
                # Termos proibidos extras focados em móveis/MadeiraMadeira
                termos_extras = ["nota fiscal", "faturamento", "condição de pagamento", "faturado", "imposto", "garantia", "montagem não inclusa", "contrate a montagem", "frete"]
                termos_verificacao = self.termos_proibidos + termos_extras
                
                # Apaga os parágrafos que contêm propagandas ou condições comerciais
                for el in desc_div.find_all(["p", "span", "strong", "li"]):
                    texto_el = el.get_text().lower()
                    if any(termo in texto_el for termo in termos_verificacao):
                        el.decompose()
                
                for br in desc_div.find_all("br"):
                    br.replace_with("\n")
                
                texto_bruto = desc_div.get_text(separator="\n", strip=True)
                linhas = [line.strip() for line in texto_bruto.split('\n') if len(line.strip()) > 0]
                texto_limpo = "\n".join(linhas)
                
                descricao = self.limpar_lixo_comercial(texto_limpo)
                print("   ✅ Descrição capturada e limpa.")

            # --- FICHA TÉCNICA ---
            specs = {}
            # As características estão dentro de divs com data-testid="table-attributes"
            blocos_tabelas = soup.find_all("div", attrs={"data-testid": "table-attributes"})
            
            termos_proibidos_specs = ["garantia", "documentos", "manual", "montador", "sac"]
            
            for bloco in blocos_tabelas:
                linhas = bloco.find_all("div", class_=re.compile(r"bg_\$background-neutral-subtlest"))
                
                for linha in linhas:
                    divs = linha.find_all("div", recursive=False) # Pega apenas as divs filhas diretas (Chave e Valor)
                    if len(divs) >= 2:
                        chave = self.limpar_texto(divs[0].get_text())
                        valor = self.limpar_texto(divs[1].get_text())
                        
                        ignorar = False
                        # Filtro rigoroso: se tiver a palavra "Garantia", ignora a linha toda
                        if any(t in chave.lower() or t in valor.lower() for t in termos_proibidos_specs):
                            ignorar = True
                            
                        # Limpa links de "Documentos Adicionais" como o manual PDF que estava no código
                        if "clique aqui" in valor.lower() or "http" in valor.lower():
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
            
            print("   [MadeiraMadeira] Gerando arquivos finais...")
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
            print(f"   ❌ [ERRO MADEIRA MADEIRA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass