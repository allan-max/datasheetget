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
            
            # A pasta certa é a do pedido (o output_folder da base). O 'pasta_saida'
            # não existe no BaseScraper e criava uma pasta 'output' à parte.
            if self.output_folder and not os.path.exists(self.output_folder):
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            # NÃO usar --headless: em headless a Dell devolve "Access Denied" com
            # 368 bytes e a página não traz nada. Sem headless vem completa.
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
            titulo = None
            div_title = soup.find("div", class_="pg-title")
            if div_title:
                h1 = div_title.find("h1")
                if h1: titulo = self.limpar_texto(h1.get_text())

            if not titulo:
                # Sem título não vale a pena continuar: antes saía um datasheet
                # vazio chamado "Produto Dell" e mesmo assim com sucesso=True.
                html = driver.page_source
                if "Access Denied" in html:
                    raise Exception("Bloqueado pela Dell (Access Denied)")
                raise Exception(f"Título não encontrado (página com {len(html)} bytes)")
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

            # Se o download falhar, abre só a imagem numa aba nova e tira a foto lá:
            # sem a loja por trás não há banner de cookies para ficar à frente.
            if url_img and (not caminho_img_raw or not os.path.exists(caminho_img_raw)):
                print("   [Dell] Download bloqueado pela Dell. Fotografando a imagem numa aba nova...")
                caminho_img_raw = self.fotografar_em_nova_aba(driver, url_img)

           # Se ainda assim falhar, tenta o screenshot na própria página (com DESTRUIÇÃO de cookies)
            if not caminho_img_raw or not os.path.exists(caminho_img_raw):
                print("   [Dell] Extraindo via screenshot limpo...")
                try:
                    # --- OCULTADOR DE BANNERS (MÉTODO SEGURO VIA CSS) ---
                    print("   [Dell] A ocultar o banner de cookies via CSS...")
                    time.sleep(2) # Espera que o banner carregue
                    
                    driver.execute_script("""
                        // Cria uma regra CSS imperativa que esconde o TrustArc sem alterar a estrutura da página
                        var estilo = document.createElement('style');
                        estilo.innerHTML = `
                            iframe[src*="trustarc"], iframe[src*="consent"], 
                            [id*="trustarc"], [class*="trustarc"],
                            [id*="truste"], [class*="truste"],
                            #cookie-consent, #consent_blackbar {
                                display: none !important;
                                visibility: hidden !important;
                                opacity: 0 !important;
                                pointer-events: none !important;
                                z-index: -9999 !important;
                            }
                        `;
                        document.head.appendChild(estilo);
                    """)
                    time.sleep(1.5) # Dá tempo ao navegador para aplicar a invisibilidade
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
                        caminho_img_raw = os.path.join(self.output_folder, temp_png)
                        
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
                    caminho_imagem_final = os.path.join(self.output_folder, final_jpeg)
                    
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
            # Fica com o bloco que tiver mais texto: o #long-description é só uma
            # frase solta e a descrição a sério está no .pd-features. Antes ganhava
            # sempre o primeiro e o datasheet saía com 106 caracteres.
            candidatos = [soup.find("div", id="long-description"),
                          soup.find("div", id="hero-long-desc"),
                          soup.find("div", class_="pd-features")]
            candidatos = [c for c in candidatos if c]
            desc_container = max(candidatos, key=lambda c: len(c.get_text(strip=True))) if candidatos else None

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
    
    def fotografar_em_nova_aba(self, driver, url_img):
        """Abre só a imagem numa aba nova e tira a foto lá. Assim o banner de
        cookies da Dell nunca fica à frente do produto. Devolve o PNG bruto."""
        if not url_img or not self.output_folder or not driver: return None
        aba_loja = driver.current_window_handle
        try:
            # Aba nova pelo Selenium: o window.open() é bloqueado como pop-up.
            driver.switch_to.new_window("tab")
            driver.get(url_img)
            el_img = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "img"))
            )
            # Espera a imagem carregar mesmo, senão a foto sai em branco.
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script(
                    "return arguments[0].complete && arguments[0].naturalWidth > 0", el_img)
            )
            time.sleep(0.5)
            caminho = os.path.join(self.output_folder, f"raw_dell_{int(time.time())}.png")
            el_img.screenshot(caminho)
            print(f"   [Dell] Foto tirada na aba nova: {caminho}")
            return caminho
        except Exception as e:
            print(f"   [Dell] Não deu para fotografar na aba nova ({e}); vou tentar na página.")
            return None
        finally:
            try:
                if driver.current_window_handle != aba_loja:
                    driver.close()
                driver.switch_to.window(aba_loja)
            except Exception: pass

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