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
            print(f"   [Frigelar] Iniciando Scraper (Bypass Absoluto por Nova Aba)...")
            
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

            # 2. Scroll para baixo
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
            
            # Dá prioridade ao data-src, pois é onde a imagem de alta resolução se esconde antes do lazy load atuar
            img_tag = soup.find("img", attrs={"data-src": re.compile(r'source=/file/')})
            if not img_tag:
                img_tag = soup.find("img", src=re.compile(r'source=/file/'))
                
            if img_tag:
                raw_src = img_tag.get("data-src") or img_tag.get("src")
                if raw_src:
                    match = re.search(r'source=(/file/[^&]+)', raw_src)
                    if match:
                        url_img = "https://www.frigelar.com.br" + match.group(1)
                    else:
                        clean_src = raw_src.split('&')[0]
                        if clean_src.startswith("/"):
                            url_img = "https://www.frigelar.com.br" + clean_src
                        else:
                            url_img = clean_src

            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            caminho_imagem = None
            if url_img:
                print(f"   [Frigelar] URL Raiz do Servidor encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # --- PLANO B: SCREENSHOT NA NOVA ABA (BYPASS WAF/CLOUDFLARE E PIXEIS BRANCOS) ---
            # Se falhar ou baixar um ficheiro com menos de 5KB (o típico pixel transparente do Lazy Load)
            if not caminho_imagem or not os.path.exists(caminho_imagem) or os.path.getsize(caminho_imagem) < 5000:
                print("   [Frigelar] Download bloqueado/corrompido. Iniciando Bypass de Nova Aba...")
                try:
                    if url_img:
                        # Abre a imagem isolada num novo separador
                        driver.execute_script(f"window.open('{url_img}', '_blank');")
                        driver.switch_to.window(driver.window_handles[1])
                        time.sleep(3) # Aguarda renderizar perfeitamente no centro
                        
                        el_img = driver.find_element(By.TAG_NAME, "img")
                        filename = f"temp_img_frigelar_{int(time.time())}.png"
                        caminho_imagem_aba = os.path.join(self.output_folder, filename)
                        
                        el_img.screenshot(caminho_imagem_aba)
                        
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                        
                        if os.path.exists(caminho_imagem_aba) and os.path.getsize(caminho_imagem_aba) > 1024:
                            caminho_imagem = caminho_imagem_aba
                            print("   ✅ Imagem capturada com sucesso no Bypass da Nova Aba!")
                        else:
                            print("   ⚠️ O Bypass da Nova Aba capturou um ficheiro corrompido.")
                except Exception as e:
                    print(f"   ⚠️ Falha no Bypass da Nova Aba: {e}")
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])

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
                        if any(t in chave.lower() or t in valor.lower() for t in termos_proibidos_specs): ignorar = True
                        if "clique aqui" in valor.lower() or "http" in valor.lower(): ignorar = True
                        
                        if not ignorar and chave and valor:
                            specs[chave] = valor

            if hasattr(self, 'filtrar_specs'): specs = self.filtrar_specs(specs)
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
            return {'sucesso': True, 'titulo': titulo, 'descricao': descricao, 'caracteristicas': specs, 'total_imagens': 1 if caminho_imagem else 0, 'arquivos': arquivos}

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
            if len(frase) < 4: continue
            if not any(termo in frase_lower for termo in termos_proibidos):
                frases_aprovadas.append(frase.strip())
        return "\n\n".join(frases_aprovadas)