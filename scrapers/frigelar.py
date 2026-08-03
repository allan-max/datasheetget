# scrapers/frigelar.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class FrigelarScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Frigelar] Iniciando Scraper (Bypass Direto no Servidor de Arquivos OCC)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            # --- Configuração Selenium Blindado ---
            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")}')
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)
            
            print(f"   [Frigelar] Acessando: {self.url}")
            driver.get(self.url)

            # 1. Espera o título carregar
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "product-name"))
                )
            except:
                print("   [Frigelar] Aviso: Timeout esperando título.")

            # 2. Scroll para baixo (Essencial para carregar Descrição e Imagens em Lazy Load)
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- 1. TÍTULO ---
            titulo = "Produto Frigelar"
            h1 = soup.find("h1", class_="product-name")
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- 2. IMAGEM (ENGENHARIA REVERSA NO SERVIDOR) ---
            print("   [Frigelar] Extraindo Imagem...")
            url_img = None
            
            img_tag = soup.find("img", src=re.compile(r'source=/file/'))
            if not img_tag:
                img_tag = soup.find("img", attrs={"data-src": re.compile(r'source=/file/')})
                
            if img_tag:
                raw_src = img_tag.get("src") or img_tag.get("data-src")
                if raw_src:
                    # EXTRAÇÃO DIRETA: Retira apenas o diretório base (/file/...) ignorando a API de redimensionamento
                    match = re.search(r'source=(/file/[^&]+)', raw_src)
                    if match:
                        url_img = "https://www.frigelar.com.br" + match.group(1)
                    else:
                        clean_src = raw_src.split('&')[0]
                        if clean_src.startswith("/"):
                            url_img = "https://www.frigelar.com.br" + clean_src
                        else:
                            url_img = clean_src

            caminho_imagem = None
            if url_img:
                print(f"   [Frigelar] URL Raiz do Servidor encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # --- PLANO B: SCREENSHOT SEM MENUS (Filtro de Ficheiros Corrompidos) ---
            # Verifica se não baixou ou se baixou um arquivo muito pequeno (erro do WAF)
            if not caminho_imagem or not os.path.exists(caminho_imagem) or os.path.getsize(caminho_imagem) < 1024:
                print("   [Frigelar] Download bloqueado pela Frigelar. Iniciando Plano de Screenshot...")
                try:
                    # Esconde o cabeçalho para não ficar por cima da foto da máquina
                    driver.execute_script("""
                        var menus = document.querySelectorAll('header, nav, .header, [style*="position: fixed"], [style*="position: sticky"], .z-50');
                        menus.forEach(m => m.style.display = 'none');
                    """)
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    
                    imagens_candidatas = driver.find_elements(By.CSS_SELECTOR, "img[src*='source=/file/'], #cc_img__resize_wrapper img")
                    
                    el_img = None
                    for img in imagens_candidatas:
                        if img.is_displayed() and img.size['width'] > 50:
                            el_img = img
                            break
                            
                    if el_img:
                        filename = f"temp_img_frigelar_{int(time.time())}.png"
                        caminho_imagem_fallback = os.path.join(self.output_folder, filename)
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem_fallback)
                        
                        if os.path.exists(caminho_imagem_fallback) and os.path.getsize(caminho_imagem_fallback) > 1024:
                            caminho_imagem = caminho_imagem_fallback
                            print("   ✅ Imagem capturada com sucesso via screenshot!")
                        else:
                            print("   ⚠️ Screenshot capturou uma imagem corrompida.")
                    else:
                        print("   ⚠️ Nenhuma imagem física visível na tela para fotografar.")
                        
                except Exception as e:
                    print(f"   ⚠️ Falha no processo de screenshot: {e}")

            # --- 3. DESCRIÇÃO (Limpeza Cirúrgica) ---
            print("   [Frigelar] Extraindo Descrição...")
            descricao_bruta = ""
            desc_container = soup.find("div", class_="frigelar-product-description-section")
            
            if desc_container:
                for iframe in desc_container.find_all("iframe"): iframe.extract()
                for h in desc_container.find_all(["h1", "h2", "h3"]):
                    if "vantagens" in h.get_text().lower() or "confira" in h.get_text().lower():
                        h.extract()

                descricao_bruta = desc_container.get_text(separator="\n")

            descricao = self.limpar_descricao_cirurgica(descricao_bruta)

            # --- 4. FICHA TÉCNICA ---
            print("   [Frigelar] Extraindo Ficha Técnica...")
            specs = {}
            tabela_specs = soup.find('table', class_=re.compile(r'props-table'))
            
            if tabela_specs:
                linhas = tabela_specs.find_all('tr')
                for linha in linhas:
                    tds = linha.find_all('td')
                    if len(tds) >= 2:
                        chave = self.limpar_texto(tds[0].get_text())
                        valor = self.limpar_texto(tds[1].get_text())
                        
                        ignorar = False
                        termos_proibidos_specs = ["garantia", "manutenção", "sac", "nota fiscal", "assistência", "pagamento"]
                        
                        if any(t in chave.lower() or t in valor.lower() for t in termos_proibidos_specs):
                            ignorar = True
                        if "clique aqui" in valor.lower() or "http" in valor.lower():
                            ignorar = True
                            
                        if not ignorar and chave and valor:
                            specs[chave] = valor

            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)
                
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [Frigelar] Gerando arquivos finais...")
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
            print(f"   ❌ [ERRO FRIGELAR] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_cirurgica(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        texto_limpo = re.sub(r'\s+', ' ', texto_bruto).strip()
        frases = re.split(r'(?<=[.!?])\s+', texto_limpo)
        frases_aprovadas = []
        
        termos_proibidos = [
            "garantia", "meses", "confira as vantagens", "assista o vídeo",
            "código frigelar", "esconder produto", "fale conosco",
            "youtube", "inscreva-se", "preço", "oferta", "frete",
            "condições de pagamento", "boleto", "cartão", "entrega",
            "instalação", "pagamento"
        ]

        for frase in frases:
            frase_lower = frase.lower()
            contem_proibido = False
            
            if len(frase) < 4: continue

            for termo in termos_proibidos:
                if termo in frase_lower:
                    contem_proibido = True
                    break
            
            if not contem_proibido:
                frases_aprovadas.append(frase.strip())

        return "\n\n".join(frases_aprovadas)