# scrapers/electrolux.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class ElectroluxScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Electrolux] A iniciar Scraper (Correção do Motor de Descrição)...")
            
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
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.minimize_window() 
            
            print(f"   [Electrolux] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Electrolux] A aguardar renderização...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .electrolux-electrolux-components-io-0-x-productNameCustomBrand"))
                )
            except:
                print("   ⚠️ Aviso: Título não encontrado rapidamente. A tentar forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Electrolux] A executar rolagem para carregar descrições e imagens...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)
            
            # --- DESTRUIDOR DE BOTÕES DE CATÁLOGO ---
            print("   [Electrolux] A expandir características ocultas...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('button, a, span, div');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto === 'ver mais' || 
                            texto.includes('leia mais') || 
                            texto.includes('especificações') || 
                            texto.includes('características')) {
                            
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
            titulo = "Produto Electrolux"
            title_tag = soup.find(['span', 'h1', 'div'], class_=re.compile(r'productNameCustomBrand|productNameContainer'))
            if not title_tag: title_tag = soup.find('h1')
            if title_tag: titulo = self.limpar_texto(title_tag.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [Electrolux] A extrair Descrição...")
            descricao = "Descrição indisponível."
            try:
                # Captura o texto completo via innerText direto do container para não perder as tags span
                descricao_bruta = driver.execute_script("""
                    var desc = document.querySelector('[class*="productDescriptionText"], .productDescription, [class*="productDescriptionContainer"]');
                    if (desc) return desc.innerText;
                    return '';
                """)
                
                if not descricao_bruta or len(descricao_bruta.strip()) < 15:
                    desc_bs4 = soup.find('div', class_=re.compile(r"productDescriptionText"))
                    if desc_bs4:
                        for br in desc_bs4.find_all("br"): br.replace_with("\n")
                        descricao_bruta = desc_bs4.get_text(separator="\n", strip=True)

                if descricao_bruta and len(descricao_bruta.strip()) > 10:
                    descricao = self.limpar_descricao_electrolux(descricao_bruta.strip())
                    print("   ✅ Descrição capturada e limpa com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a descrição.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair descrição: {e}")

            # --- FICHA TÉCNICA ---
            print("   [Electrolux] A extrair Ficha Técnica...")
            specs = {}
            try:
                specs_dict = driver.execute_script("""
                    var specs = {};
                    var rows = document.querySelectorAll('tr, .vtex-store-components-3-x-specificationsTablePropertyRow');
                    rows.forEach(r => {
                        var th = r.querySelector('th, .vtex-store-components-3-x-specificationsTablePropertyName');
                        var td = r.querySelector('td, .vtex-store-components-3-x-specificationsTablePropertyValue');
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
                        chave_limpa = self.limpar_texto(k)
                        valor_limpo = self.limpar_texto(v)
                        
                        ignorar = False
                        termos_proibidos_specs = [
                            "garantia", "ean", "referência", "sku", "sac", "nota fiscal", "instalação"
                        ]
                        if any(t in chave_limpa.lower() or t in valor_limpo.lower() for t in termos_proibidos_specs):
                            ignorar = True

                        if not ignorar and chave_limpa and valor_limpo:
                            specs[chave_limpa] = valor_limpo
                            
                if hasattr(self, 'filtrar_specs'):
                    specs = self.filtrar_specs(specs)
                    
                print(f"   ✅ Specs encontradas: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair specs via JS: {e}")

            # --- IMAGEM ---
            print("   [Electrolux] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_container = soup.find('img', class_=re.compile(r'productImageTag--main|productImageTag'))
            if img_container:
                url_img = img_container.get('src')
                
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                print(f"   [Electrolux] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Electrolux] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[class*='productImageTag--main'], img[class*='productImageTag']")
                    if el_img:
                        filename = f"temp_img_electrolux_{int(time.time())}.png"
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

            print("   [Electrolux] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO ELECTROLUX] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_electrolux(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        termos_proibidos_frase = [
            "garantia", "loja oficial", "instalação", "serviço oficial",
            "condições exclusivas", "devolução", "troca", "frete", "entrega", 
            "pagamento", "boleto", "cartão", "preço", "oferta", "promoção", 
            "fale conosco", "televendas", "atendimento", "sac", "consulte o manual"
        ]

        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean:
                continue

            linha_lower = linha_clean.lower()
            
            if "garanta sua" in linha_lower or "compre agora" in linha_lower:
                continue

            if any(termo in linha_lower for termo in termos_proibidos_frase):
                continue 
            
            linhas_limpas.append(linha_clean)

        return "\n\n".join(linhas_limpas)