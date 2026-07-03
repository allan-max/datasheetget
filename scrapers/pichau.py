# scrapers/pichau.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class PichauScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Pichau] A iniciar Scraper (Motor Material-UI + Filtro CSS)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")}')
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)
            
            print(f"   [Pichau] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Pichau] A aguardar renderização inicial...")
            try:
                # Aguarda o carregamento do título pelo data-cy ou classe da Pichau
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-cy='product-page-title'], h1"))
                )
            except:
                print("   ⚠️ Aviso: Título não encontrado rapidamente. A forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Pichau] A executar rolagem profunda para carregar conteúdo Lazy Load...")
            for i in range(7):
                driver.execute_script("window.scrollBy(0, 700);")
                time.sleep(1)
            
            driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Pichau"
            h1 = soup.find('h1', attrs={"data-cy": "product-page-title"})
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO (COM FILTRO DE CSS/STYLE) ---
            print("   [Pichau] A extrair Descrição...")
            descricao = "Descrição indisponível."
            try:
                descricao_bruta = ""
                # O texto rico da Pichau fica nestas divs
                desc_container = soup.find('div', class_=re.compile(r'description-rich-text'))
                
                if desc_container:
                    # Passo Crítico: Remover todas as tags <style> e <script> inseridas no meio do HTML
                    for lixo in desc_container.find_all(['style', 'script', 'link']):
                        lixo.decompose()
                        
                    linhas_desc = []
                    # Vamos apanhar apenas os cabeçalhos e parágrafos para ignorar imagens soltas
                    for tag in desc_container.find_all(['h2', 'h3', 'p', 'li']):
                        texto = tag.get_text(separator=" ", strip=True)
                        if texto and len(texto) > 3:
                            # Se for um título (h2/h3), adicionamos uma quebra de linha extra para formatar bonito
                            if tag.name in ['h2', 'h3']:
                                linhas_desc.append(f"\n{texto.upper()}")
                            else:
                                linhas_desc.append(texto)
                                
                    descricao_bruta = "\n".join(linhas_desc).strip()

                if descricao_bruta and len(descricao_bruta) > 15:
                    descricao = self.limpar_descricao_pichau(descricao_bruta)
                    print("   ✅ Descrição capturada com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a descrição rica.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair descrição: {e}")

            # --- CARACTERÍSTICAS TÉCNICAS ---
            print("   [Pichau] A extrair Ficha Técnica...")
            specs = {}
            try:
                # A Pichau tem tabelas muito bem estruturadas
                tabelas = soup.find_all('table', class_=re.compile(r'table-specification|table'))
                for tabela in tabelas:
                    linhas = tabela.find_all('tr')
                    for linha in linhas:
                        th = linha.find('th')
                        td = linha.find('td')
                        if th and td:
                            # Removemos os dois pontos finais da chave
                            chave = self.limpar_texto(th.get_text(strip=True)).rstrip(":")
                            
                            # Tratamos as quebras de linha dentro da célula de valor (ex: compatibilidade Windows/PlayStation)
                            for br in td.find_all("br"): br.replace_with("; ")
                            valor = self.limpar_texto(td.get_text(separator=" ", strip=True))
                            
                            if chave and valor:
                                specs[chave] = valor

                # Limpeza rigorosa
                specs_limpas = {}
                termos_proibidos_specs = ["garantia", "ean", "sku"]
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
            print("   [Pichau] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            # A Pichau usa classes que contêm 'slideImage' ou tem imagens na galeria principal
            img_tag = soup.find('img', class_=re.compile(r'slideImage'))
            if not img_tag:
                img_tag = soup.find('img', alt=re.compile(r'^Mostrando', re.I)) # Às vezes as de destaque
                
            if img_tag:
                url_img = img_tag.get('src')
                
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                print(f"   [Pichau] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Pichau] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[class*='slideImage'], img[data-cy='product-image']")
                    if el_img:
                        filename = f"temp_img_pichau_{int(time.time())}.png"
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

            print("   [Pichau] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO PICHAU] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_pichau(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        termos_proibidos = [
            "garantia", "frete", "entrega", "pagamento", "boleto", 
            "cartão", "consulte o manual", "pichau", "adicione ao carrinho"
        ]

        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean:
                # Preserva algumas quebras de linha para manter os parágrafos separados
                if linhas_limpas and linhas_limpas[-1] != "":
                    linhas_limpas.append("")
                continue

            linha_lower = linha_clean.lower()

            if any(termo in linha_lower for termo in termos_proibidos):
                continue 
            
            linhas_limpas.append(linha_clean)

        # Remove quebras de linha duplicadas
        resultado = "\n".join(linhas_limpas)
        resultado = re.sub(r'\n{3,}', '\n\n', resultado)
        
        return resultado.strip()