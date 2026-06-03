# scrapers/dufrio.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class DufrioScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Dufrio] A iniciar Scraper (Motor de Abas Alpine.js)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")}')
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)
            
            print(f"   [Dufrio] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Dufrio] A aguardar renderização inicial...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1.page-title, span.base"))
                )
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. A forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Dufrio] A vasculhar a página para contornar o Lazy Load...")
            for i in range(6):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)
            
            # --- AUTO-CLICKER ---
            print("   [Dufrio] A expandir Características Técnicas...")
            driver.execute_script("""
                // Procura botões e cabeçalhos que abrem as abas de especificações
                var botoes = document.querySelectorAll('h2, button, a, span');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto === 'características técnicas' || 
                            texto === 'especificações' || 
                            texto.includes('ver mais')) {
                            
                            try { botoes[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(2) # Aguarda a transição da aba
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Dufrio"
            h1 = soup.find(['h1', 'span'], class_=re.compile(r'page-title|base'))
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [Dufrio] A extrair Descrição...")
            descricao = "Descrição indisponível."
            try:
                descricao_bruta = ""
                
                # A Dufrio costuma usar blocos hidden md:block para a descrição textual
                desc_container = soup.find('div', class_=re.compile(r'md:block'))
                if desc_container and desc_container.find('p'):
                    # Captura apenas se houver parágrafos lá dentro
                    ps = desc_container.find_all('p')
                    linhas_desc = [p.get_text(separator=" ", strip=True) for p in ps if len(p.get_text(strip=True)) > 10]
                    descricao_bruta = "\n\n".join(linhas_desc)
                
                # Fallback JS se o CSS mudar
                if not descricao_bruta or len(descricao_bruta) < 15:
                    descricao_bruta = driver.execute_script("""
                        var text = '';
                        var ps = document.querySelectorAll('.md\\\\:block p, .product-description p');
                        ps.forEach(p => {
                            if(p.innerText.trim().length > 15) {
                                text += p.innerText.trim() + '\\n\\n';
                            }
                        });
                        return text;
                    """)

                if descricao_bruta and len(descricao_bruta.strip()) > 15:
                    descricao = self.limpar_descricao_dufrio(descricao_bruta.strip())
                    print("   ✅ Descrição capturada e limpa com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a descrição.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair descrição: {e}")

            # --- CARACTERÍSTICAS TÉCNICAS ---
            print("   [Dufrio] A extrair Ficha Técnica...")
            specs = {}
            try:
                # O site tem várias tabelas class="additional-attributes"
                tabelas = soup.find_all('table', class_=re.compile(r'additional-attributes'))
                
                for tabela in tabelas:
                    linhas = tabela.find_all('tr')
                    for linha in linhas:
                        th = linha.find('th')
                        td = linha.find('td')
                        
                        if th and td:
                            chave = self.limpar_texto(th.get_text(strip=True))
                            valor = self.limpar_texto(td.get_text(strip=True))
                            if chave and valor:
                                specs[chave] = valor
                                
                # Fallback JS
                if not specs:
                    specs_dict = driver.execute_script("""
                        var specs = {};
                        var rows = document.querySelectorAll('.additional-attributes tr');
                        rows.forEach(r => {
                            var th = r.querySelector('th');
                            var td = r.querySelector('td');
                            if(th && td) {
                                var key = th.innerText.trim();
                                var val = td.innerText.trim();
                                if(key && val && key !== val) specs[key] = val;
                            }
                        });
                        return specs;
                    """)
                    if specs_dict:
                        for k, v in specs_dict.items():
                            specs[self.limpar_texto(k)] = self.limpar_texto(v)

                # Limpeza rigorosa
                specs_limpas = {}
                termos_proibidos_specs = ["garantia", "ean", "referência do fornecedor", "sku"]
                for k, v in specs.items():
                    k_lower = k.lower()
                    if not any(t in k_lower for t in termos_proibidos_specs):
                        specs_limpas[k] = v
                
                specs = specs_limpas
                if hasattr(self, 'filtrar_specs'):
                    specs = self.filtrar_specs(specs)
                    
                print(f"   ✅ Specs encontradas: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair specs: {e}")

            # --- IMAGEM ---
            print("   [Dufrio] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            # A Dufrio guarda as imagens do produto na pasta /media/catalog/product/
            imagens = soup.find_all('img')
            for img in imagens:
                src = img.get('src') or img.get('data-src') or img.get(':src')
                if src and '/media/catalog/product/' in src:
                    url_img = src
                    break
                    
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                print(f"   [Dufrio] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Dufrio] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[src*='/media/catalog/product/']")
                    if el_img:
                        filename = f"temp_img_dufrio_{int(time.time())}.png"
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

            print("   [Dufrio] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO DUFRIO] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_dufrio(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        termos_proibidos = [
            "garantia", "frete", "entrega", "pagamento", "boleto", 
            "cartão", "consulte o manual"
        ]

        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean:
                continue

            linha_lower = linha_clean.lower()

            if any(termo in linha_lower for termo in termos_proibidos):
                continue 
            
            linhas_limpas.append(linha_clean)

        return "\n\n".join(linhas_limpas)