# scrapers/travessa.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class TravessaScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Travessa] A iniciar Scraper (Motor de Livraria / Extração Direta)...")
            
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
            
            print(f"   [Travessa] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Travessa] A aguardar renderização inicial...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#lblNomArtigo, #imgArtigo"))
                )
            except:
                print("   ⚠️ Aviso: Título ou imagem não encontrados rapidamente. A forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Travessa] A executar rolagem para acionar imagens preguiçosas (Lazy Load)...")
            for i in range(4):
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)
            
            # --- AUTO-CLICKER ---
            print("   [Travessa] A expandir Sinopse completa...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('.leiamais, a, p, span');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto.includes('leia mais') || texto === 'ver mais' || texto.includes('mais detalhes')) {
                            try { botoes[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(1.5)
            
            driver.execute_script("window.scrollTo(0, 200);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Livro Travessa"
            h1 = soup.find(id='lblNomArtigo')
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO (SINOPSE) ---
            print("   [Travessa] A extrair Sinopse...")
            descricao = "Sinopse indisponível."
            try:
                desc_tag = soup.find(id='lblSinopse')
                if desc_tag:
                    for br in desc_tag.find_all("br"): br.replace_with("\n")
                    descricao_bruta = desc_tag.get_text(separator="\n", strip=True)
                    if descricao_bruta and len(descricao_bruta) > 10:
                        descricao = descricao_bruta
                        print("   ✅ Sinopse capturada com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a sinopse.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair sinopse: {e}")

            # --- CARACTERÍSTICAS TÉCNICAS (DADOS DO PRODUTO) ---
            print("   [Travessa] A extrair Ficha Técnica...")
            specs = {}
            try:
                div_dados = soup.find('div', class_='dados')
                if div_dados:
                    # 1. Tratamento Especial para o Título (que tem a chave dentro do h1)
                    lbl_nome = div_dados.find(id='lblDadosNome')
                    if lbl_nome:
                        txt_desc = lbl_nome.find('span', class_='txtDescricao')
                        if txt_desc:
                            chave = self.limpar_texto(txt_desc.get_text(strip=True).replace(':', ''))
                            txt_desc.decompose() # Remove a chave do elemento principal
                            valor = self.limpar_texto(lbl_nome.get_text(strip=True))
                            if chave and valor: specs[chave] = valor

                    # 2. Extração dos pares Span Chave -> Span Valor
                    spans_desc = div_dados.find_all('span', class_='txtDescricao')
                    for span in spans_desc:
                        # Ignora elementos ocultos (display:none)
                        style = span.get('style', '').replace(' ', '').lower()
                        if 'display:none' in style: continue
                        
                        chave = self.limpar_texto(span.get_text(strip=True).replace(':', ''))
                        
                        # O valor costuma ser o próximo span no DOM
                        next_node = span.find_next_sibling('span')
                        if next_node:
                            next_style = next_node.get('style', '').replace(' ', '').lower()
                            if 'display:none' not in next_style:
                                valor = self.limpar_texto(next_node.get_text(strip=True))
                                if chave and valor: specs[chave] = valor

                    # 3. Tratamento Especial para Autores / Organizadores
                    partic = div_dados.find(id='lblTituloDadosParticipantes')
                    if partic:
                        # Pega o texto mantendo a separação visual dos autores
                        txt_participantes = partic.get_text(separator=" ", strip=True)
                        if ':' in txt_participantes:
                            partes = txt_participantes.split(':', 1)
                            chave = self.limpar_texto(partes[0])
                            # Troca o "|" por ", " para ficar mais bonito na ficha (ex: Autor 1, Autor 2)
                            valor = self.limpar_texto(partes[1].replace('|', ','))
                            if chave and valor: specs[chave] = valor

                if hasattr(self, 'filtrar_specs'):
                    specs = self.filtrar_specs(specs)
                    
                print(f"   ✅ Dados do produto encontrados: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair dados do produto: {e}")

            # --- IMAGEM ---
            print("   [Travessa] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_tag = soup.find(id='imgArtigo')
            if img_tag:
                url_img = img_tag.get('src') or img_tag.get('data-src')

            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                print(f"   [Travessa] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Travessa] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.ID, "imgArtigo")
                    if el_img:
                        filename = f"temp_img_travessa_{int(time.time())}.png"
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

            print("   [Travessa] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO TRAVESSA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass