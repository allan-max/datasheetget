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
            print(f"   [ML] Iniciando Scraper (Modo Catálogo Avançado)...")
            
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
            
            print("   [ML] Aguardando renderização do produto...")
            time.sleep(3) # Tempo inicial para o Javascript base montar a página
            
            # --- 1. ROLAGEM DUPLA (Lazy Load) ---
            print("   [ML] Forçando o carregamento das seções ocultas...")
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 2000);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 3500);")
            time.sleep(1)
            
            # --- 2. CLIQUE EM "VER MAIS" (Essencial para links /up/ de Catálogo) ---
            driver.execute_script("""
                // Procura botões de 'Ver todas as características' ou 'Descrição completa'
                var botoes = document.querySelectorAll('button, a, span');
                for (var i = 0; i < botoes.length; i++) {
                    var texto = botoes[i].innerText.toLowerCase();
                    if (texto.includes('ver todas as características') || 
                        texto.includes('mostrar mais') || 
                        texto.includes('mais características')) {
                        try { botoes[i].click(); } catch(e) {}
                    }
                }
            """)
            time.sleep(2) # Espera a janela de especificações abrir e popular o HTML
            
            # Rola para o topo para garantir que o print de tela saia certo
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Mercado Livre"
            h1 = soup.find('h1', class_=re.compile(r'ui-pdp-title'))
            if not h1:
                h1 = soup.find('h1')
            if h1:
                titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO (Modo Força Bruta) ---
            descricao = "Descrição indisponível."
            desc_elem = soup.find(['p', 'div', 'span'], class_=re.compile(r'ui-pdp-description__content'))
            
            if not desc_elem:
                desc_elem = soup.find('div', class_=re.compile(r'ui-pdp-description'))
                
            # Se ainda falhar, procura literalmente a palavra "Descrição" nos cabeçalhos e apanha o bloco seguinte
            if not desc_elem or len(desc_elem.get_text(strip=True)) < 15:
                h_desc = soup.find(lambda tag: tag.name in ["h2", "h3", "div", "p"] and tag.text and "Descrição" in tag.text.strip())
                if h_desc:
                    desc_elem = h_desc.find_next_sibling()
                    if not desc_elem or len(desc_elem.get_text(strip=True)) < 5:
                        desc_elem = h_desc.parent # Pega o bloco inteiro como último recurso

            if desc_elem:
                for br in desc_elem.find_all("br"):
                    br.replace_with("\n")
                
                descricao_bruta = desc_elem.get_text(separator="\n", strip=True)
                if len(descricao_bruta) > 10:
                    descricao = self.limpar_lixo_comercial(descricao_bruta)
                    print("   ✅ Descrição capturada e limpa.")
                else:
                    print("   ⚠️ Aviso: Bloco de descrição encontrado, mas texto estava vazio.")

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

            # --- CARACTERÍSTICAS (Extração Universal) ---
            specs = {}
            
            # Estratégia 1: Tabelas HTML puras (padrão antigo e alguns novos)
            rows = soup.find_all('tr')
            for row in rows:
                th = row.find(['th', 'td'], class_=re.compile(r'andes-table__header|ui-pdp-specs__row-title'))
                if not th: th = row.find('th')
                
                td = row.find(['td', 'span'], class_=re.compile(r'andes-table__column|ui-pdp-specs__row-condition'))
                if not td: td = row.find('td')
                
                if th and td:
                    chave = self.limpar_texto(th.get_text())
                    valor = self.limpar_texto(td.get_text())
                    if chave and valor and chave != valor:
                        specs[chave] = valor

            # Estratégia 2: Estrutura baseada em DIVs (Layout de Catálogo Moderno)
            if len(specs) < 2:
                div_rows = soup.find_all('div', class_=re.compile(r'ui-pdp-specs__row|ui-vpp-striped-specs__row|andes-table__row'))
                for row in div_rows:
                    # Extrai os textos. Geralmente a chave é a primeira div/span e o valor é a última.
                    textos = row.find_all(['span', 'p', 'div', 'th', 'td'])
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