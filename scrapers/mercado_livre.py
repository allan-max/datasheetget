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
            print(f"   [ML] Iniciando Scraper (Motor de Catálogo V7 - Adaptação Highlighted Specs)...")
            
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
            driver.minimize_window() 
            
            print(f"   [ML] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [ML] Aguardando renderização inicial...")
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
            except:
                pass
            
            # --- 1. ROLAGEM FORÇADA ---
            print("   [ML] Vasculhando a página para carregar elementos ocultos...")
            for i in range(4):
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(1)
            
            # --- 2. DESTRUIDOR DE BOTÕES DE CATÁLOGO (Atualizado com "Conferir") ---
            print("   [ML] Clicando nos botões de expansão de ficha técnica...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('button, a, span');
                for (var i = 0; i < botoes.length; i++) {
                    var texto = botoes[i].innerText.toLowerCase();
                    if (texto.includes('ver todas') || 
                        texto.includes('conferir todas') || 
                        texto.includes('características completas') || 
                        texto.includes('mostrar mais') || 
                        texto.includes('mais características')) {
                        try { botoes[i].click(); } catch(e) {}
                    }
                }
            """)
            time.sleep(2.5) 
            
            # Volta ao topo
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Mercado Livre"
            h1 = soup.find('h1', class_=re.compile(r'ui-pdp-title'))
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [ML] Extraindo Descrição...")
            descricao = "Descrição indisponível."
            try:
                descricao_bruta = driver.execute_script("""
                    var d = document.querySelector('[class*="description__content"], [data-testid="content"], .ui-pdp-description, .ui-pdp-family-description');
                    if(d && d.innerText.length > 10) return d.innerText;
                    
                    var headers = document.querySelectorAll('h2, h3, div, p');
                    for(var i=0; i<headers.length; i++) {
                        var txt = headers[i].innerText.toLowerCase().trim();
                        if(txt === 'descrição' || txt === 'descrição do produto') {
                            var next = headers[i].nextElementSibling;
                            if(next && next.innerText.length > 10) return next.innerText;
                        }
                    }
                    return '';
                """)
                
                if descricao_bruta and len(descricao_bruta.strip()) > 10:
                    descricao = self.limpar_lixo_comercial(descricao_bruta.strip())
                    print("   ✅ Descrição capturada com sucesso.")
                else:
                    # Fallback BeautifulSoup para a classe exata que enviou
                    desc_bs4 = soup.find('p', attrs={"data-testid": "content", "class": re.compile(r"description__content")})
                    if desc_bs4:
                        for br in desc_bs4.find_all("br"): br.replace_with("\n")
                        descricao = self.limpar_lixo_comercial(desc_bs4.get_text(separator="\n", strip=True))
                        print("   ✅ Descrição capturada via fallback BS4.")
                    else:
                        print("   ⚠️ Aviso: Mercado Livre não renderizou a descrição.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair descrição via JS: {e}")

            # --- CARACTERÍSTICAS (Atualizado para Highlighted Specs) ---
            print("   [ML] Extraindo Ficha Técnica...")
            specs = {}
            try:
                specs_dict = driver.execute_script("""
                    var specs = {};
                    // Apanha as linhas antigas, as de catálogo e as novas Highlighted
                    var rows = document.querySelectorAll('tr, [class*="specs__row"], [class*="andes-table__row"], [class*="specs-table__row"], [class*="row--key-value"]');
                    rows.forEach(r => {
                        // Tenta estrutura de Tabela/Divs Antiga
                        var th = r.querySelector('th, [class*="row-title"], [class*="table__header"]');
                        var td = r.querySelector('td, [class*="row-condition"], [class*="table__column"]');
                        if(th && td) {
                            var key = th.innerText.trim();
                            var val = td.innerText.trim();
                            if(key && val && key !== val) {
                                specs[key] = val;
                            }
                        } else {
                            // Tenta estrutura Nova (Highlighted Specs) que você encontrou no Forno
                            var p_label = r.querySelector('p[class*="key-value__labels"]');
                            if(p_label) {
                                var spans = p_label.querySelectorAll(':scope > span');
                                if(spans.length >= 2) {
                                    // Pega o primeiro span como chave (remove os dois pontos no fim) e o último como valor
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