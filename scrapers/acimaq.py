# scrapers/acimaq.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class AcimaqScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Acimaq] Iniciando Scraper (Estratégia VTEX Avançada)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
            
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.maximize_window() 
            
            print(f"   [Acimaq] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Acimaq] Aguardando renderização do produto...")
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. Continuando a extração.")
            
            # --- 1. ROLAGEM LENTA (Lazy Load) ---
            print("   [Acimaq] Vasculhando a página...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)
            
            # --- 2. CLICAR EM "VER MAIS" (Expandir a Descrição da VTEX) ---
            print("   [Acimaq] Procurando botões para expandir a descrição e ficha técnica...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('button, a, span, div');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto === 'ver mais' || 
                            texto === 'mostrar mais' || 
                            texto.includes('especificações') || 
                            texto.includes('características')) {
                            
                            // Remove href para não sair da página
                            if(botoes[i].tagName.toLowerCase() === 'a') {
                                botoes[i].removeAttribute('href');
                            }
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
            titulo = "Produto Acimaq"
            h1 = soup.find('h1', class_=re.compile(r'productNameContainer'))
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [Acimaq] Extraindo Descrição...")
            descricao = "Descrição indisponível."
            try:
                # Usa JS para capturar a div exata da VTEX ignorando as restrições de tamanho
                descricao_bruta = driver.execute_script("""
                    var d = document.querySelector('[class*="productDescriptionText"], [class*="productDescriptionContainer"]');
                    if(d) return d.innerText;
                    return '';
                """)
                
                if not descricao_bruta or len(descricao_bruta.strip()) < 15:
                    # Fallback BeautifulSoup
                    desc_bs4 = soup.find('div', class_=re.compile(r"productDescriptionText"))
                    if desc_bs4:
                        for br in desc_bs4.find_all("br"): br.replace_with("\n")
                        descricao_bruta = desc_bs4.get_text(separator="\n", strip=True)

                if descricao_bruta and len(descricao_bruta.strip()) > 10:
                    descricao = self.limpar_lixo_comercial(descricao_bruta.strip())
                    print("   ✅ Descrição capturada com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a descrição.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair descrição: {e}")

            # --- CARACTERÍSTICAS (Filtra a Garantia) ---
            print("   [Acimaq] Extraindo Ficha Técnica...")
            specs = {}
            try:
                specs_dict = driver.execute_script("""
                    var specs = {};
                    // Busca pela estrutura de tabela da Acimaq (item_technical_info) ou tabelas clássicas
                    var rows = document.querySelectorAll('[class*="item_technical_info"], tr');
                    rows.forEach(r => {
                        var th, td;
                        if(r.tagName.toLowerCase() === 'tr') {
                            th = r.querySelector('th');
                            td = r.querySelector('td');
                        } else {
                            // Estrutura VTEX customizada da Acimaq
                            th = r.querySelector('[class*="title_technical_info"]');
                            td = r.querySelector('[class*="value_technical_info"]');
                        }
                        
                        if(th && td) {
                            var key = th.innerText.trim();
                            var val = td.innerText.trim();
                            if(key && val && key !== val) {
                                specs[key] = val;
                            }
                        }
                    });
                    return specs;
                """)
                
                if specs_dict:
                    for k, v in specs_dict.items():
                        chave_limpa = self.limpar_texto(k)
                        valor_limpo = self.limpar_texto(v)
                        # Aplica o bloqueio de Lixo Comercial
                        ignorar = False
                        termos_proibidos_specs = ["garantia", "manutenção", "sac", "nota fiscal", "assistência"]
                        if any(t in chave_limpa.lower() or t in valor_limpo.lower() for t in termos_proibidos_specs):
                            ignorar = True

                        if not ignorar and chave_limpa and valor_limpo:
                            specs[chave_limpa] = valor_limpo
                            
                print(f"   ✅ Specs encontradas: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair specs via JS: {e}")

            # --- IMAGEM ---
            print("   [Acimaq] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_container = soup.find('img', class_=re.compile(r'productImageTag--main|productImageTag'))
            if img_container:
                url_img = img_container.get('src')

            if url_img:
                print(f"   [Acimaq] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Acimaq] Apelando para o Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[class*='productImageTag--main'], img[class*='productImageTag']")
                    if el_img:
                        filename = f"temp_img_acimaq_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except:
                    pass

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [Acimaq] Gerando arquivos PDF/Word...")
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
            print(f"   ❌ [ERRO ACIMAQ] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass