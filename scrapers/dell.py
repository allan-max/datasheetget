# scrapers/dell.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
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

            # --- IMAGEM ---
            url_img = None
            caminho_imagem = None
            
            # Prioridade: ID da Dell > Classe genérica > Primeira imagem grande
            img_tag = soup.find("img", attrs={"data-testid": "sharedPolarisHeroPdImage"})
            if not img_tag:
                img_tag = soup.find("img", class_="u-max-full-width")
            
            if img_tag:
                src = img_tag.get("src")
                if src:
                    if src.startswith("//"): src = "https:" + src
                    url_img = src
            
            if url_img:
                try:
                    # Busca elemento para screenshot
                    el_img = None
                    try:
                        el_img = driver.find_element(By.CSS_SELECTOR, "img[data-testid='sharedPolarisHeroPdImage']")
                    except:
                        # Fallback
                        imgs = driver.find_elements(By.TAG_NAME, "img")
                        for img in imgs:
                            if img.get_attribute("src") == url_img:
                                el_img = img
                                break
                    
                    if el_img:
                        filename = "temp_img_dell.png"
                        caminho_imagem = os.path.join(self.pasta_saida, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print(f"   ✅ Imagem salva: {filename}")
                except Exception as e:
                    print(f"   ⚠️ Erro ao salvar imagem: {e}")

            # --- DESCRIÇÃO ---
            descricao = "Descrição indisponível."
            desc_container = soup.find("div", class_="pd-features")
            if desc_container:
                for script in desc_container(["script", "style"]):
                    script.decompose()
                texto_bruto = desc_container.get_text(separator="\n", strip=True)
                descricao = self.limpar_descricao_dell(texto_bruto)

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