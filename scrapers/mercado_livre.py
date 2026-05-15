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
            print(f"   [ML] Iniciando Scraper (Estratégia Anti-Bloqueio e Clique Seguro)...")
            
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
            
            # Mantemos maximizado para você poder resolver o Captcha se necessário
            driver.maximize_window() 
            
            print(f"   [ML] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            # --- 1. VERIFICAÇÃO DE CAPTCHA INTERATIVA ---
            time.sleep(3) 
            if "verifique que você não é um robô" in driver.page_source.lower() or "recaptcha" in driver.page_source.lower():
                print("   🚨 [ALERTA] MERCADO LIVRE PEDIU CAPTCHA!")
                print("   ⏳ O robô vai pausar por 25 SEGUNDOS. Por favor, resolva o Captcha na janela do Chrome AGORA!")
                time.sleep(25)
                print("   ▶️ Retomando a extração...")
            
            print("   [ML] Aguardando renderização inicial...")
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
            except:
                print("   ⚠️ H1 não encontrado. Pode ser um erro de carregamento, mas vamos tentar continuar.")
            
            # --- 2. ROLAGEM MUITO LENTA ---
            print("   [ML] Vasculhando a página lentamente...")
            for i in range(8):
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)
            
            # --- 3. DESTRUIDOR DE BOTÕES SEGURO (Evita sair da página) ---
            print("   [ML] Procurando botões ocultos de forma segura...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('button, a, span, div');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        
                        // PALAVRAS PROIBIDAS: Se tiver isso, ignora o botão para não sair da página!
                        if (texto.includes('perguntas') || texto.includes('loja') || texto.includes('opiniões') || texto.includes('ofertas') || texto.includes('produtos') || texto.includes('ver todas as marcas')) {
                            continue;
                        }
                        
                        // PALAVRAS EXATAS: Só clica se for especificamente da ficha técnica/descrição
                        if (texto.includes('todas as características') || 
                            texto === 'mostrar mais' || 
                            texto === 'ler mais' || 
                            texto === 'ver mais' ||
                            texto.includes('descrição completa')) {
                            
                            // DESARMADOR DE LINKS: Tira o link (href) da tag <a> para o navegador não sair da tela do produto
                            if(botoes[i].tagName.toLowerCase() === 'a') {
                                botoes[i].removeAttribute('href');
                                botoes[i].removeAttribute('target');
                            }
                            
                            try { botoes[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(3) 
            
            driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Mercado Livre"
            h1 = soup.find('h1', class_=re.compile(r'ui-pdp-title'))
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")
            
            if titulo == "Produto Mercado Livre":
                print("   ❌ ERRO CRÍTICO: O Mercado Livre bloqueou o acesso completamente.")

            # --- DESCRIÇÃO ---
            print("   [ML] Extraindo Descrição...")
            descricao = "Descrição indisponível."
            desc_texto = ""
            
            desc_caixa = soup.find(class_=re.compile(r'ui-pdp-description__content|ui-pdp-family-description'))
            if desc_caixa:
                for br in desc_caixa.find_all("br"): br.replace_with("\n")
                desc_texto = desc_caixa.get_text(separator="\n", strip=True)
                
            if len(desc_texto) < 15:
                for tag in soup.find_all(['h2', 'h3', 'div', 'p']):
                    if tag.text and tag.text.strip().lower() in ['descrição', 'descrição do produto']:
                        irmao = tag.find_next_sibling()
                        if irmao:
                            for br in irmao.find_all("br"): br.replace_with("\n")
                            desc_texto = irmao.get_text(separator="\n", strip=True)
                            if len(desc_texto) > 15: break

            if len(desc_texto) > 15:
                descricao = self.limpar_lixo_comercial(desc_texto)
                print("   ✅ Descrição capturada com sucesso.")
            else:
                print("   ⚠️ Aviso: Mercado Livre não renderizou a descrição nesta página.")

            # --- CARACTERÍSTICAS ---
            print("   [ML] Extraindo Ficha Técnica...")
            specs = {}
            try:
                specs_dict = driver.execute_script("""
                    var specs = {};
                    var rows = document.querySelectorAll('tr, [class*="specs__row"], [class*="andes-table__row"], [class*="specs-table__row"], [class*="row--key-value"]');
                    rows.forEach(r => {
                        var th = r.querySelector('th, [class*="row-title"], [class*="table__header"]');
                        var td = r.querySelector('td, [class*="row-condition"], [class*="table__column"]');
                        if(th && td) {
                            var key = th.innerText.trim();
                            var val = td.innerText.trim();
                            if(key && val && key !== val) {
                                specs[key] = val;
                            }
                        } else {
                            var p_label = r.querySelector('p[class*="key-value__labels"]');
                            if(p_label) {
                                var spans = p_label.querySelectorAll(':scope > span');
                                if(spans.length >= 2) {
                                    var key = spans[0].innerText.replace(/:$/, '').trim();
                                    var val = spans[spans.length - 1].innerText.trim();
                                    if(key && val && key !== val) {
                                        specs[key] = val;
                                    }
                                }
                            }
                        }
                    });
                    return specs;
                """)
                
                if specs_dict:
                    for k, v in specs_dict.items():
                        chave_limpa = self.limpar_texto(k)
                        valor_limpo = self.limpar_texto(v)
                        if chave_limpa and valor_limpo:
                            specs[chave_limpa] = valor_limpo
                            
                specs = self.filtrar_specs(specs)
                print(f"   ✅ Specs encontradas: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair specs via JS: {e}")

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
                except:
                    pass

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