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
            print(f"   [Frigelar] Iniciando Scraper (Motor Oracle Cloud Commerce e Busca Direta de Imagem)...")
            
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

            # --- 2. IMAGEM (BUSCA DIRETA NA TAG E LIMPEZA DE PARÂMETROS) ---
            print("   [Frigelar] Extraindo Imagem...")
            url_img = None
            
            # Procura diretamente por uma imagem que tenha o padrão de diretório do OCC (Oracle Cloud Commerce)
            img_tag = soup.find("img", src=re.compile(r'source=/file/'))
            if not img_tag:
                img_tag = soup.find("img", attrs={"data-src": re.compile(r'source=/file/')})
                
            if img_tag:
                raw_src = img_tag.get("src") or img_tag.get("data-src")
                if raw_src:
                    # Corta pelo '&' para remover &height=X&width=Y e forçar a imagem original
                    clean_src = raw_src.split('&')[0]
                    if clean_src.startswith("/"):
                        url_img = "https://www.frigelar.com.br" + clean_src
                    else:
                        url_img = clean_src

            caminho_imagem = None
            if url_img:
                print(f"   [Frigelar] URL da imagem original encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # PLANO B: Se o download falhar, tira uma fotografia à imagem (Screenshot)
            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Frigelar] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    # Tenta fotografar a imagem principal
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[src*='source=/file/']")
                    if el_img:
                        filename = f"temp_img_frigelar_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except Exception as e:
                    print(f"   ⚠️ Falha no screenshot: {e}")

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
                        
                        # Filtro rigoroso contra Garantia e Condições de Venda
                        ignorar = False
                        termos_proibidos_specs = ["garantia", "manutenção", "sac", "nota fiscal", "assistência", "pagamento"]
                        
                        if any(t in chave.lower() or t in valor.lower() for t in termos_proibidos_specs):
                            ignorar = True
                            
                        # Limpa links extras inseridos acidentalmente no HTML
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
        """Remove apenas frases com termos proibidos, mantendo o resto."""
        if not texto_bruto: return "Descrição indisponível."

        texto_limpo = re.sub(r'\s+', ' ', texto_bruto).strip()
        
        # Divide por pontuação para analisar frase a frase
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
            
            if len(frase) < 4:
                continue

            for termo in termos_proibidos:
                if termo in frase_lower:
                    contem_proibido = True
                    break
            
            if not contem_proibido:
                frases_aprovadas.append(frase.strip())

        return "\n\n".join(frases_aprovadas)