# scrapers/lenovo.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class LenovoScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Lenovo] A iniciar Scraper (Motor Híbrido + Imagens Alta Resolução)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")}')
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            
            # Força o navegador a ter um tamanho Full HD para que os screenshots saiam com alta qualidade
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            
            # Em vez de minimizar completamente (o que estraga os screenshots), definimos um tamanho fixo grande
            driver.set_window_size(1920, 1080)
            
            print(f"   [Lenovo] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Lenovo] A aguardar renderização...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .product_summary, .gallery-image"))
                )
            except:
                print("   ⚠️ Aviso: Elementos iniciais não encontrados rapidamente. A forçar continuação.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Lenovo] A executar rolagem para carregar descrições...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(1.5)
            
            # --- AUTO-CLICKER PARA ESPECIFICAÇÕES ---
            print("   [Lenovo] A abrir separadores de especificações...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('button, a, span, li');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto === 'especificações técnicas' || 
                            texto === 'tech specs' || 
                            texto.includes('ver todas as especificações') ||
                            texto.includes('mostrar mais')) {
                            
                            try { botoes[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(2)
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Lenovo"
            title_tag = soup.find(['h1', 'h2'], class_=re.compile(r'product_summary|product-name'))
            if not title_tag: title_tag = soup.find('h1')
            if title_tag: titulo = self.limpar_texto(title_tag.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [Lenovo] A extrair Descrição...")
            descricao_bruta = ""
            
            blades = soup.find_all(class_=re.compile(r'feature-blade|feature_blade'))
            if blades:
                linhas_desc = []
                for blade in blades:
                    hl = blade.find(class_=re.compile(r'headline'))
                    desc = blade.find(class_=re.compile(r'description'))
                    if hl: linhas_desc.append(hl.get_text(separator=" ", strip=True))
                    if desc: linhas_desc.append(desc.get_text(separator=" ", strip=True))
                descricao_bruta = "\n\n".join(linhas_desc)
            
            if not descricao_bruta or len(descricao_bruta) < 20:
                overview = soup.find(class_=re.compile(r'overview_content|overview-content'))
                if overview:
                    for br in overview.find_all("br"): br.replace_with("\n")
                    descricao_bruta = overview.get_text(separator="\n", strip=True)

            descricao = self.limpar_descricao_lenovo(descricao_bruta)
            if descricao and descricao != "Descrição indisponível.":
                print("   ✅ Descrição capturada com sucesso.")
            else:
                print("   ⚠️ Aviso: Não foi possível extrair a descrição.")

            # --- FICHA TÉCNICA ---
            print("   [Lenovo] A extrair Ficha Técnica...")
            specs = {}
            
            specs_items = soup.find_all(class_=re.compile(r'specs\\?_item|specs-item'))
            if specs_items:
                for item in specs_items:
                    nome_tag = item.find(class_=re.compile(r'item\\?_name|item-name'))
                    val_tag = item.find(class_=re.compile(r'item\\?_content|item-content'))
                    if nome_tag and val_tag:
                        k = self.limpar_texto(nome_tag.get_text())
                        v = self.limpar_texto(val_tag.get_text())
                        if k and v: specs[k] = v

            if not specs:
                for row in soup.find_all("tr"):
                    cols = row.find_all(["th", "td"])
                    if len(cols) == 2:
                        k = self.limpar_texto(cols[0].get_text())
                        v = self.limpar_texto(cols[1].get_text())
                        if k and v: specs[k] = v

            if not specs:
                ul_specs = soup.find('ul', style=re.compile(r'list-style:disc'))
                if ul_specs:
                    para_specs = ul_specs.find_all('li')
                    for i, li in enumerate(para_specs):
                        texto_li = self.limpar_texto(li.get_text())
                        if texto_li:
                            if ":" in texto_li:
                                partes = texto_li.split(":", 1)
                                specs[partes[0].strip()] = partes[1].strip()
                            else:
                                specs[f"Destaque {i+1}"] = texto_li

            specs_limpas = {}
            termos_proibidos_specs = ["garantia", "linguagem", "software", "teclado", "dispositivo apontador", "optical drive", "cor"]
            for k, v in specs.items():
                if not any(t in k.lower() or t in v.lower() for t in termos_proibidos_specs):
                    specs_limpas[k] = v
            
            if hasattr(self, 'filtrar_specs'): specs_limpas = self.filtrar_specs(specs_limpas)
            specs = specs_limpas
            
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- IMAGEM ---
            print("   [Lenovo] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_tags = soup.find_all('img', class_=re.compile(r'gallery-image|blade-media'))
            if not img_tags:
                canvas = soup.find('li', class_='canvas-item')
                if canvas: img_tags = [canvas.find('img')]
                
            for img in img_tags:
                if img:
                    src = img.get('data-src') or img.get('src')
                    if src and not src.endswith('.gif'): 
                        url_img = src
                        break

            if url_img:
                if url_img.startswith("//"): url_img = "https:" + url_img
                elif url_img.startswith("/"): url_img = "https://www.lenovo.com" + url_img
                
                # O TRUQUE DE QUALIDADE: Limpa os parâmetros de redimensionamento do link
                if "?" in url_img:
                    url_img = url_img.split("?")[0]
                    
                print(f"   [Lenovo] URL da imagem de alta resolução encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Lenovo] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img.gallery-image, li.canvas-item img")
                    if el_img:
                        filename = f"temp_img_lenovo_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot em Full HD!")
                except:
                    pass

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [Lenovo] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO LENOVO] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_lenovo(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        termos_proibidos = [
            "as especificações podem variar", "garantia", "consulte o manual",
            "financiamento", "frete", "entrega", "parcelamento", "compre agora"
        ]

        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean:
                continue

            linha_lower = linha_clean.lower()
            
            if any(termo in linha_lower for termo in termos_proibidos):
                continue 
            
            linhas_limpas.append(linha_clean)

        return "\n\n".join(linhas_limpas)