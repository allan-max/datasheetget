# scrapers/bradyid.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

# Tentativa de importar o tradutor
try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False
    print("⚠️ [AVISO] Biblioteca 'deep-translator' não encontrada. A tradução automática não vai funcionar. Rode: pip install deep-translator")

class BradyidScraper(BaseScraper):
    def traduzir(self, texto):
        if not texto or not HAS_TRANSLATOR: 
            return texto
        try:
            return GoogleTranslator(source='en', target='pt').translate(texto)
        except Exception as e:
            print(f"   ⚠️ Erro ao traduzir: {e}")
            return texto

    def executar(self):
        driver = None
        try:
            print(f"   [BradyID] A iniciar Scraper (Motor de Tradução Automática EN -> PT)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            
            print(f"   [BradyID] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [BradyID] A aguardar renderização inicial...")
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "pdptitle"))
                )
            except:
                print("   ⚠️ Aviso: Título não encontrado rapidamente. A forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            for i in range(4):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)

            # --- AUTO-CLICKER ---
            print("   [BradyID] A expandir painéis de especificações (Accordions)...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('summary.BR-AccordionHeader, details.BR-Accordion');
                for (var i = 0; i < botoes.length; i++) {
                    try { botoes[i].setAttribute('open', 'true'); } catch(e) {}
                    try { botoes[i].click(); } catch(e) {}
                }
            """)
            time.sleep(2)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo_en = "Produto BradyID"
            h1 = soup.find(id='pdptitle') or soup.find('h1', class_=re.compile(r'PDPTitleText'))
            if h1: titulo_en = self.limpar_texto(h1.get_text())
            titulo = self.traduzir(titulo_en)
            print(f"   ✅ Título capturado e traduzido: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [BradyID] A extrair e traduzir Descrição...")
            descricao_bruta = ""
            
            desc_div = soup.find(id="pdpdesc")
            if desc_div:
                descricao_bruta += desc_div.get_text(separator=" ", strip=True) + "\n\n"
                
            beneficios_ul = soup.find(id="featuredBenefits")
            if beneficios_ul:
                descricao_bruta += "Destaques do Produto:\n"
                for li in beneficios_ul.find_all('li'):
                    texto_li = li.get_text(separator=" ", strip=True)
                    if texto_li:
                        descricao_bruta += f"• {texto_li}\n"
            
            descricao = "Descrição indisponível."
            if descricao_bruta:
                # Traduz o bloco inteiro de texto
                descricao = self.traduzir(descricao_bruta.strip())
                print("   ✅ Descrição capturada e traduzida com sucesso.")

            # --- CARACTERÍSTICAS TÉCNICAS ---
            print("   [BradyID] A extrair e traduzir Ficha Técnica...")
            specs = {}
            try:
                tabelas = soup.find_all('table', class_=re.compile(r'BR-Table'))
                for tabela in tabelas:
                    for tr in tabela.find_all('tr'):
                        th = tr.find('th')
                        td = tr.find('td')
                        
                        if th and td:
                            # A BradyID coloca tooltips gigantes escondidos no <th>. Precisamos apagá-los antes de ler o texto!
                            for tooltip in th.find_all('span', class_=re.compile(r'BR-TooltipWrapper|BR-Tooltip')):
                                tooltip.decompose()
                            
                            chave_en = self.limpar_texto(th.get_text(separator=" ", strip=True))
                            valor_en = self.limpar_texto(td.get_text(separator=" ", strip=True))
                            
                            if chave_en and valor_en:
                                # Traduz a chave e o valor em tempo real
                                chave_pt = self.traduzir(chave_en)
                                valor_pt = self.traduzir(valor_en)
                                specs[chave_pt] = valor_pt

                if hasattr(self, 'filtrar_specs'):
                    specs = self.filtrar_specs(specs)
                    
                print(f"   ✅ Specs encontradas e traduzidas: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair specs: {e}")

            # --- IMAGEM ---
            print("   [BradyID] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_tag = soup.find('img', attrs={'data-test-id': 'media-gallery-main-image'})
            if img_tag: url_img = img_tag.get('src')

            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                print(f"   [BradyID] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [BradyID] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[data-test-id='media-gallery-main-image']")
                    if el_img:
                        filename = f"temp_img_brady_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except: pass

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [BradyID] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO BRADYID] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass