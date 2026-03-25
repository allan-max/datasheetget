# scrapers/dell.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
from PIL import Image
from .base import BaseScraper

class DellScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Dell] Iniciando Scraper (V4 - Tratamento de Imagem Completo)...")
            
            if not hasattr(self, 'pasta_saida'): self.pasta_saida = "output"
            if not os.path.exists(self.pasta_saida): os.makedirs(self.pasta_saida)

            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.add_argument("--window-size=1920,3000")
            
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            
            driver = uc.Chrome(options=options, version_main=109)
            
            print(f"   [Dell] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            # Scroll para forçar carregamento da página
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1600);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 3000);")
            time.sleep(1.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Dell"
            div_title = soup.find("div", class_="pg-title")
            if div_title:
                h1 = div_title.find("h1")
                if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   [DEBUG] Título: {titulo}")

            # --- IMAGEM (DOWNLOAD + SCREENSHOT + PILLOW) ---
            print("   [Dell] Processando a imagem...")
            url_img = None
            caminho_img_raw = None
            caminho_imagem_final = None
            
            img_tag = soup.find("img", attrs={"data-testid": "sharedPolarisHeroPdImage"})
            if not img_tag:
                img_tag = soup.find("img", class_="u-max-full-width")
            
            if img_tag and img_tag.get("src"):
                src = img_tag.get("src")
                if src.startswith("//"): src = "https:" + src
                url_img = src
                print(f"   [Dell] URL da imagem encontrada: {url_img}")
                caminho_img_raw = self.baixar_imagem_temp(url_img)

           # Se o download falhar, tenta o screenshot (com DESTRUIÇÃO de cookies)
            if not caminho_img_raw or not os.path.exists(caminho_img_raw):
                print("   [Dell] Download bloqueado pela Dell. Extraindo via screenshot limpo...")
                try:
                    # --- DESTRUIDOR DE BANNERS (Injeta JS para deletar o overlay do HTML) ---
                    print("   [Dell] Evaporando banner de cookies da tela...")
                    driver.execute_script("""
                        // Procura todos os elementos conhecidos de cookies da Dell/TrustArc
                        var lixos = document.querySelectorAll('.trustarc-banner-safe-area, #trustarc-banner, .trustarc-banner-container, iframe[src*="trustarc"], #cookie-consent');
                        // Deleta todos eles da página
                        lixos.forEach(elemento => elemento.remove());
                        // Destrava a rolagem da página caso o banner tenha travado
                        document.body.style.overflow = 'auto';
                    """)
                    time.sleep(1) # Dá 1 segundo pro navegador processar a exclusão
                    # ------------------------------------------------------------------------

                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = None
                    
                    # Procura a imagem
                    try:
                        el_img = driver.find_element(By.CSS_SELECTOR, "img[data-testid='sharedPolarisHeroPdImage']")
                    except:
                        imgs = driver.find_elements(By.TAG_NAME, "img")
                        for img in imgs:
                            if img.get_attribute("src") == url_img:
                                el_img = img
                                break
                    
                    if el_img:
                        temp_png = f"raw_dell_{int(time.time())}.png"
                        caminho_img_raw = os.path.join(self.pasta_saida, temp_png)
                        
                        # Centraliza para garantir que a imagem não saia cortada
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1.5) 
                        
                        # Agora tira o print da imagem limpa (o banner foi deletado)
                        el_img.screenshot(caminho_img_raw)
                        print(f"   [Dell] Screenshot RAW salvo perfeitamente em {caminho_img_raw}")
                    else:
                        print("   [Dell] ERRO: Não achou o elemento da imagem para o print.")
                except Exception as e:
                    print(f"   ⚠️ Erro crítico no screenshot: {e}")

            # === CONVERSÃO PARA JPEG PARA O WORD/PDF (O PULO DO GATO) ===
            if caminho_img_raw and os.path.exists(caminho_img_raw):
                try:
                    img = Image.open(caminho_img_raw)
                    # Remove transparências problemáticas
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                        
                    final_jpeg = f"dell_final_{int(time.time())}.jpg"
                    caminho_imagem_final = os.path.join(self.pasta_saida, final_jpeg)
                    
                    # Redimensiona para não estourar o limite do PDF
                    max_size = 600
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

                    img.save(caminho_imagem_final, "JPEG", quality=95)
                    img.close()
                    print(f"   ✅ Imagem convertida para JPEG com sucesso!")
                    
                    # Apaga o PNG temporário para não sujar a pasta
                    time.sleep(0.5)
                    try: os.remove(caminho_img_raw)
                    except: pass
                except Exception as pi_err:
                    print(f"   ❌ Erro na conversão PIL: {pi_err}")
                    caminho_imagem_final = caminho_img_raw

            # --- DESCRIÇÃO ---
            descricao = "Descrição indisponível."
            desc_container = soup.find("div", id="long-description")
            if not desc_container:
                desc_container = soup.find("div", id="hero-long-desc")
            if not desc_container:
                desc_container = soup.find("div", class_="pd-features")
                
            if desc_container:
                for script in desc_container(["script", "style"]):
                    script.decompose()
                texto_bruto = desc_container.get_text(separator="\n", strip=True)
                descricao = self.limpar_descricao_dell(texto_bruto)

            # --- FICHA TÉCNICA ---
            specs = {}
            spec_items = soup.find_all("div", class_="spec__item")
            
            if not spec_items:
                try:
                    aba_specs = driver.find_element(By.ID, "techspecs_section-title")
                    driver.execute_script("arguments[0].click();", aba_specs)
                    time.sleep(1.5)
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    spec_items = soup.find_all("div", class_="spec__item")
                except: pass

            for item in spec_items:
                title_div = item.find("div", class_="spec__item__title")
                if title_div:
                    chave = self.limpar_texto(title_div.get_text())
                    valor_completo = self.limpar_texto(item.get_text())
                    
                    if valor_completo.lower().startswith(chave.lower()):
                        valor = valor_completo[len(chave):].strip()
                    else:
                        valor = valor_completo
                    
                    ignorar = False
                    palavras_proibidas = ["garantia", "warranty", "serviço", "troca avançada", "hardware limitado", "suporte", "service"]
                    
                    if any(p in chave.lower() for p in palavras_proibidas) or any(p in valor.lower() for p in palavras_proibidas):
                        ignorar = True

                    if not ignorar and chave and valor:
                        specs[chave] = valor

            # --- FINALIZAÇÃO E GERADOR DE ARQUIVOS ---
            print("   [Dell] Preparando envio para o Gerador...")
            
            # ATENÇÃO AQUI: Passando a variável correta para o gerador
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem_final
            }
            
            arquivos = self.gerar_arquivos_finais(dados)
            
            if arquivos:
                print("   ✅ Arquivos gerados com sucesso!")
            else:
                print("   ❌ Falha ao gerar arquivos no Word/PDF.")
            
            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs,
                'total_imagens': 1 if caminho_imagem_final else 0,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO DELL] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass
    
    def limpar_descricao_dell(self, texto):
        if not texto: return ""
        palavras_proibidas = ["adquira", "compre", "clique", "confira", "garantia", "troca avançada", "hardware limitado", "serviço de troca", "dell.com", "fale conosco"]
        linhas_limpas = []
        for linha in texto.splitlines():
            linha_lower = linha.lower().strip()
            if len(linha_lower) < 2: continue
            if any(bad in linha_lower for bad in palavras_proibidas): continue
            linhas_limpas.append(linha.strip())
        return "\n".join(linhas_limpas)