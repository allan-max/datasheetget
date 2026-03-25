# scrapers/dell.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
from PIL import Image
import os
from .base import BaseScraper

class DellScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Dell] Iniciando Scraper (V3 - No Warranty / Win2012 Fix)...")
            
            # --- SETUP ---
            if not hasattr(self, 'pasta_saida'): self.pasta_saida = "output"
            if not os.path.exists(self.pasta_saida): os.makedirs(self.pasta_saida)

            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.add_argument("--window-size=1920,1080")
            
            # --- CRÍTICO: Versão 109 para Windows Server 2012 R2 ---
            # Se usar 144 aqui, vai dar o erro [WinError 193]
            driver = uc.Chrome(options=options, version_main=109)
            
            # 1. ACESSO
            print(f"   [Dell] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            # Espera o título principal
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "pg-title"))
                )
            except:
                print("   ⚠️ Timeout no carregamento inicial.")

            # Scroll em etapas para carregar lazy load
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1600);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 3000);")
            time.sleep(1.5)

            # 2. EXTRAÇÃO
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Dell"
            div_title = soup.find("div", class_="pg-title")
            if div_title:
                h1 = div_title.find("h1")
                if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   [DEBUG] Título: {titulo}")

            # --- IMAGEM (PLANO DUPLO COM PROCESSAMENTO DE PILLOW) ---
            print("   [Dell] Preparando captura inteligente de imagem...")
            url_img = None
            caminho_imagem_final = None # Este será o JPEG definitivo
            caminho_img_raw = None # PNG bruto do screenshot
            
            # Prioridade 1: ID da Dell (novo layout)
            img_tag = soup.find("img", attrs={"data-testid": "sharedPolarisHeroPdImage"})
            # Prioridade 2: Fallback (layout antigo)
            if not img_tag:
                img_tag = soup.find("img", class_="u-max-full-width")
            
            if img_tag and img_tag.get("src"):
                src = img_tag.get("src")
                if src.startswith("//"): 
                    src = "https:" + src
                url_img = src
                print(f"   [Dell] URL da imagem encontrada: {url_img}")
                
                # TENTATIVA 1: Baixar a imagem diretamente
                caminho_img_raw = self.baixar_imagem_temp(url_img)

            # TENTATIVA 2: Se o download direto falhar, apela para o screenshot da tela
            if not caminho_img_raw or not os.path.exists(caminho_img_raw):
                print("   [Dell] Download falhou. Fazendo screenshot de alta qualidade...")
                try:
                    # Rola um pouco para carregar a imagem principal (às vezes é lazy load)
                    driver.execute_script("window.scrollTo(0, 0);")
                    
                    el_img = None
                    # Tenta achar o elemento para screenshot
                    wait = WebDriverWait(driver, 10)
                    try:
                        el_img = wait.until(EC.visibility_of_element_condition_located((By.CSS_SELECTOR, "img[data-testid='sharedPolarisHeroPdImage']")))
                    except:
                        imgs = driver.find_elements(By.TAG_NAME, "img")
                        for img in imgs:
                            if img.get_attribute("src") == url_img:
                                el_img = img
                                break
                    
                    if el_img:
                        # Gera um nome de arquivo temporário PNG
                        temp_png = f"raw_dell_{int(time.time())}.png"
                        caminho_img_raw = os.path.join(self.output_folder, temp_png)
                        
                        # Centraliza para garantir que a imagem não saia cortada
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1.5) # Espera renderizar o zoom
                        el_img.screenshot(caminho_img_raw)
                        print(f"   [Dell] Screenshot capturado com sucesso (PNG)!")
                except Exception as e:
                    print(f"   ⚠️ Erro crítico ao capturar imagem: {e}")

            # === O PULO DO GATO: PROCESSAMENTO DE IMAGEM COM PILLOW ===
            if camino_img_raw and os.path.exists(caminho_img_raw):
                try:
                    print("   [Dell] Processando imagem para JPEG (Word/PDF)...")
                    # Abre a imagem bruta (PNG do print)
                    img = Image.open(caminho_img_raw)
                    
                    # Converte para RGB (remove transparência do PNG para garantir que não dê erro)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                        
                    # Define nome final JPEG
                    final_jpeg = f"dell_{int(time.time())}.jpg"
                    caminho_imagem_final = os.path.join(self.output_folder, final_jpeg)
                    
                    # Redimensiona mantendo a proporção (máximo 800px de altura para não explodir o PDF)
                    max_height = 800
                    if img.height > max_height:
                        ratio = max_height / float(img.height)
                        new_width = int(float(img.width) * float(ratio))
                        img = img.resize((new_width, max_height), Image.Resampling.LANCZOS)

                    # Salva como JPEG com alta qualidade
                    img.save(caminho_imagem_final, "JPEG", quality=90)
                    print(f"   ✅ Imagem processada e salva em JPEG!")
                    
                    # Fecha o objeto da imagem explicitamente para liberar o Windows
                    img.close()
                    
                    # Tenta deletar o arquivo bruto (PNG) para não poluir a pasta e liberar o bloqueio
                    time.sleep(0.5) # Pausa micro para garantir a liberação
                    try:
                        os.remove(caminho_img_raw)
                        print("   ✅ Arquivo PNG temporário deletado com sucesso.")
                    except: pass # Se não der para deletar agora, paciência

                except Exception as pi_err:
                    print(f"   ❌ Erro ao processar imagem com Pillow: {pi_err}")
                    # Se falhar o processamento, tenta usar a raw mesmo
                    caminho_imagem_final = caminho_img_raw
            else:
                print("   ⚠️ Aviso: Nenhuma imagem RAW foi capturada.")
                
            # --- DESCRIÇÃO (ATUALIZADO PARA O NOVO LAYOUT DA DELL) ---
            descricao = "Descrição indisponível."
            
            # Tenta achar a div nova (long-description ou hero-long-desc) ou a antiga (pd-features)
            desc_container = soup.find("div", id="long-description")
            if not desc_container:
                desc_container = soup.find("div", id="hero-long-desc")
            if not desc_container:
                desc_container = soup.find("div", class_="pd-features")
                
            if desc_container:
                # Remove scripts e estilos escondidos para não poluir o PDF
                for script in desc_container(["script", "style"]):
                    script.decompose()
                
                texto_bruto = desc_container.get_text(separator="\n", strip=True)
                descricao = self.limpar_descricao_dell(texto_bruto)
                print("   ✅ Descrição extraída com sucesso.")
            else:
                print("   ⚠️ Caixa de descrição não encontrada no HTML.")

            # --- FICHA TÉCNICA (COM FILTRO DE GARANTIA) ---
            specs = {}
            spec_items = soup.find_all("div", class_="spec__item")
            
            # Se não achou, tenta abrir a aba de specs
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
                    
                    # Remove a chave do valor (ex: "Peso: 10kg" -> "10kg")
                    if valor_completo.lower().startswith(chave.lower()):
                        valor = valor_completo[len(chave):].strip()
                    else:
                        valor = valor_completo
                    
                    # --- FILTROS DE EXCLUSÃO (GARANTIA) ---
                    termo_chave = chave.lower()
                    termo_valor = valor.lower()
                    
                    ignorar = False
                    palavras_proibidas = [
                        "garantia", "warranty", "serviço", "troca avançada", 
                        "hardware limitado", "suporte", "service"
                    ]
                    
                    # Verifica se a CHAVE contém palavra proibida
                    if any(p in termo_chave for p in palavras_proibidas):
                        ignorar = True
                    
                    # Verifica se o VALOR contém palavra proibida (ex: "3 anos de garantia")
                    if any(p in termo_valor for p in palavras_proibidas):
                        ignorar = True

                    if not ignorar and chave and valor:
                        specs[chave] = valor

            print(f"   ✅ Specs encontradas: {len(specs)} itens (Garantia removida).")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [Dell] Gerando arquivos...")
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
            print(f"   ❌ [ERRO DELL] {e}")
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass
    
    def limpar_descricao_dell(self, texto):
        """Limpa textos de marketing e garantia da descrição"""
        if not texto: return ""
        
        palavras_proibidas = [
            "adquira", "compre", "clique", "confira", 
            "garantia", "troca avançada", "hardware limitado",
            "serviço de troca", "dell.com", "fale conosco"
        ]
        
        linhas_limpas = []
        for linha in texto.splitlines():
            linha_lower = linha.lower().strip()
            if len(linha_lower) < 2: continue
            
            # Se a linha contiver palavra proibida, pula
            if any(bad in linha_lower for bad in palavras_proibidas):
                continue
                
            linhas_limpas.append(linha.strip())
            
        return "\n".join(linhas_limpas)