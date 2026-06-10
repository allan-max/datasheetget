# scrapers/martinsfontes.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class MartinsFontesScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Martins Fontes] A iniciar Scraper (Motor VTEX Clássico para Livrarias)...")
            
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
            
            print(f"   [Martins Fontes] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Martins Fontes] A aguardar renderização inicial...")
            try:
                # Aguarda o carregamento do título do livro
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".productName, h1"))
                )
            except:
                print("   ⚠️ Aviso: Título não encontrado rapidamente. A forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Martins Fontes] A executar rolagem para garantir o carregamento do conteúdo...")
            for i in range(4):
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)
            
            # --- AUTO-CLICKER ---
            print("   [Martins Fontes] A expandir sinopse e especificações...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('a, button, span, div, p');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto === 'leia mais' || 
                            texto === 'ler mais' || 
                            texto.includes('características') || 
                            texto.includes('especificações')) {
                            
                            if(botoes[i].tagName.toLowerCase() === 'a') {
                                botoes[i].removeAttribute('href');
                            }
                            try { botoes[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(1.5)
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Livro Martins Fontes"
            h1 = soup.find(['div', 'h1'], class_=re.compile(r'productName'))
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO (SINOPSE) ---
            print("   [Martins Fontes] A extrair Sinopse...")
            descricao = "Sinopse indisponível."
            try:
                descricao_bruta = ""
                # O site utiliza a div de classe "productDescription" [cite: 250]
                desc_tag = soup.find('div', class_=re.compile(r'productDescription'))
                if desc_tag:
                    for br in desc_tag.find_all("br"): br.replace_with("\n")
                    descricao_bruta = desc_tag.get_text(separator="\n", strip=True)
                
                # Fallback JS
                if not descricao_bruta or len(descricao_bruta) < 15:
                    descricao_bruta = driver.execute_script("""
                        var desc = document.querySelector('.productDescription');
                        if (desc) return desc.innerText;
                        return '';
                    """)

                if descricao_bruta and len(descricao_bruta.strip()) > 10:
                    descricao = descricao_bruta.strip()
                    print("   ✅ Sinopse capturada com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a sinopse.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair sinopse: {e}")

            # --- CARACTERÍSTICAS TÉCNICAS (Ficha do Livro) ---
            print("   [Martins Fontes] A extrair Ficha Técnica...")
            specs = {}
            try:
                # O padrão VTEX clássico para especificações usa tabelas com a classe "group" ou dentro de "productSpecifications"
                specs_dict = driver.execute_script("""
                    var specs = {};
                    var rows = document.querySelectorAll('table.group tr, .productSpecifications tr, .specification-table tr');
                    rows.forEach(r => {
                        var th = r.querySelector('th');
                        var td = r.querySelector('td');
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
                        
                        ignorar = False
                        termos_proibidos = ["garantia", "sac", "altura", "largura", "peso", "profundidade"]
                        # Muitos não querem o peso e medidas de um livro na ficha final, mas se quiser, pode remover as últimas 4 palavras acima.
                        if any(t in chave_limpa.lower() for t in termos_proibidos):
                            ignorar = True
                            
                        if not ignorar and chave_limpa and valor_limpo:
                            specs[chave_limpa] = valor_limpo
                            
                if hasattr(self, 'filtrar_specs'):
                    specs = self.filtrar_specs(specs)
                    
                print(f"   ✅ Dados do livro encontrados: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair dados do livro: {e}")

            # --- IMAGEM ---
            print("   [Martins Fontes] A extrair Capa do Livro em Alta Resolução...")
            url_img = None
            caminho_imagem = None
            
            # O ID image-main costuma guardar a imagem principal [cite: 250]
            img_tag = soup.find('img', id='image-main') or soup.find('img', class_=re.compile(r'sku-rich-image-main'))
            if img_tag:
                url_img = img_tag.get('src') or img_tag.get('data-src')

            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                # TRUQUE DE ALTA RESOLUÇÃO VTEX:
                # O link vem como ".../ids/1592522-511-511/808848.jpg" [cite: 250]
                # Nós vamos substituir o "-511-511" (ou qualquer outra resolução baixa) por "-1000-1000" para forçar uma capa de livro nítida
                url_img = re.sub(r'-\d+-\d+', '-1000-1000', url_img)
                
                # Se tiver query params irritantes de redimensionamento na ponta do URL (ex: ?width=...), limpe-os.
                if "?" in url_img:
                    url_img = url_img.split("?")[0]
                    
                print(f"   [Martins Fontes] URL da imagem GIGANTE encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Martins Fontes] A recorrer ao Screenshot da capa do livro...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "#image-main, .sku-rich-image-main")
                    if el_img:
                        filename = f"temp_img_martins_{int(time.time())}.png"
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

            print("   [Martins Fontes] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO MARTINS FONTES] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass