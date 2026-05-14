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
            print(f"   [ML] Iniciando Scraper (Catálogo Ultimate V5)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
            
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.minimize_window() 
            
            print(f"   [ML] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [ML] Aguardando renderização inicial...")
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
            except:
                pass
            
            # --- 1. ROLAGEM FORÇADA ---
            print("   [ML] Vasculhando a página para carregar elementos ocultos...")
            for i in range(4):
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(1)
            
            # --- 2. DESTRUIDOR DE BOTÕES DE CATÁLOGO (Ver Todas as Características) ---
            print("   [ML] Clicando nos botões de expansão de ficha técnica...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('button, a, span');
                for (var i = 0; i < botoes.length; i++) {
                    var texto = botoes[i].innerText.toLowerCase();
                    if (texto.includes('ver todas as características') || 
                        texto.includes('características completas') || 
                        texto.includes('mostrar mais') || 
                        texto.includes('mais características')) {
                        try { botoes[i].click(); } catch(e) {}
                    }
                }
            """)
            time.sleep(2.5) # Pausa maior para garantir que a janela modal de Specs abriu
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Mercado Livre"
            h1 = soup.find('h1', class_=re.compile(r'ui-pdp-title'))
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO (Estratégia Blindada para Catálogo) ---
            descricao = "Descrição indisponível."
            desc_elem = soup.find(['p', 'div', 'span'], class_=re.compile(r'ui-pdp-description__content'))
            
            if not desc_elem:
                desc_elem = soup.find('div', class_=re.compile(r'ui-pdp-description'))
                
            # Caçador agressivo pela palavra "Descrição" nos cabeçalhos
            if not desc_elem or len(desc_elem.get_text(strip=True)) < 15:
                for h in soup.find_all(['h2', 'h3', 'p', 'div']):
                    if "descrição" in h.get_text().lower() and len(h.get_text(strip=True)) < 20:
                        desc_elem = h.find_next_sibling()
                        if desc_elem and len(desc_elem.get_text(strip=True)) > 10:
                            break

            if desc_elem:
                for br in desc_elem.find_all("br"):
                    br.replace_with("\n")
                descricao_bruta = desc_elem.get_text(separator="\n", strip=True)
                
                if len(descricao_bruta) > 10:
                    descricao = self.limpar_lixo_comercial(descricao_bruta)
                    print("   ✅ Descrição capturada e limpa.")
                else:
                    print("   ⚠️ Aviso: Bloco de descrição vazio ou ausente nesta página de catálogo.")

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
                except:
                    pass

            # --- CARACTERÍSTICAS (O Pesadelo do Catálogo Resolvido) ---
            specs = {}
            
            # TENTATIVA 1: Tabelas Andes e VPP (Tabelas Reais)
            linhas_tabela = soup.find_all('tr', class_=re.compile(r'andes-table__row|ui-vpp-striped-specs__row|ui-pdp-specs__table-row'))
            for row in linhas_tabela:
                th = row.find(['th', 'td'], class_=re.compile(r'andes-table__header|ui-pdp-specs__row-title'))
                if not th: th = row.find('th')
                
                td = row.find(['td', 'span'], class_=re.compile(r'andes-table__column|ui-pdp-specs__row-condition'))
                if not td: td = row.find('td')
                
                if th and td:
                    chave = self.limpar_texto(th.get_text())
                    valor = self.limpar_texto(td.get_text())
                    if chave and valor and chave != valor:
                        specs[chave] = valor

            # TENTATIVA 2: Layout Baseado em Divs (Se a Tabela Falhar)
            if len(specs) < 2:
                linhas_div = soup.find_all('div', class_=re.compile(r'ui-pdp-specs__row|ui-vpp-striped-specs__row'))
                for row in linhas_div:
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