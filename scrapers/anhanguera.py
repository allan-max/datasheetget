# scrapers/anhanguera.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class AnhangueraScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Anhanguera] A iniciar Scraper (Motor FBITS com Analisador de Texto)...")
            
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
            
            print(f"   [Anhanguera] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Anhanguera] A aguardar renderização inicial...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1.product-title, .product-information_wrapper"))
                )
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. A forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Anhanguera] A executar rolagem para carregar descrições...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)
            
            # --- AUTO-CLICKER ---
            print("   [Anhanguera] A expandir abas ocultas...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('.tab, button, a, h2, h3, span');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto === 'descrição' || 
                            texto.includes('informações técnicas') || 
                            texto.includes('características') || 
                            texto.includes('especificações')) {
                            
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
            titulo = "Produto Anhanguera"
            h1 = soup.find('h1', class_='product-title')
            if not h1: h1 = soup.find('h1')
            if h1:
                # Remove a div interna de reviews que costuma sujar o título
                div_review = h1.find('div', id='yv-review-quickreview')
                if div_review: div_review.decompose()
                titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO E FICHA TÉCNICA (EXTRAÇÃO CONJUNTA) ---
            print("   [Anhanguera] A extrair e analisar blocos de informação...")
            descricao = "Descrição indisponível."
            specs = {}
            
            # Apanha todos os blocos de conteúdo de informação
            info_blocks = soup.find_all('div', class_=re.compile(r'product-information_content'))
            
            if len(info_blocks) >= 1:
                # O primeiro bloco é tipicamente a Descrição
                bloco_desc = info_blocks[0]
                for br in bloco_desc.find_all("br"): br.replace_with("\n")
                descricao_bruta = bloco_desc.get_text(separator="\n", strip=True)
                if descricao_bruta and len(descricao_bruta) > 10:
                    descricao = self.limpar_descricao_anhanguera(descricao_bruta)
                    print("   ✅ Descrição capturada com sucesso.")

            if len(info_blocks) >= 2:
                # O segundo bloco costuma ser a Ficha Técnica
                bloco_specs = info_blocks[1]
                for br in bloco_specs.find_all("br"): br.replace_with("\n")
                linhas_specs = bloco_specs.get_text(separator="\n", strip=True).split('\n')
                
                categoria_atual = ""
                for linha in linhas_specs:
                    linha = linha.strip()
                    if not linha: continue
                    
                    # Analisador de Texto para extrair chaves e valores
                    if ':' in linha:
                        partes = linha.split(':', 1)
                        # Limpa traços e espaços no início da chave
                        chave = self.limpar_texto(partes[0].replace('- ', '').strip())
                        # Limpa ponto e vírgula no final do valor
                        valor = self.limpar_texto(partes[1].replace(';', '').strip())
                        
                        if chave and valor:
                            # Se tiver uma categoria atual (ex: Máquina Inversora), adicionamos ao nome para não misturar com a Máscara
                            if categoria_atual:
                                chave_final = f"{categoria_atual} - {chave}"
                            else:
                                chave_final = chave
                            specs[chave_final] = valor
                        elif chave and not valor:
                            # Pode ser um cabeçalho de categoria, como "- Máquina Inversora de Solda:"
                            categoria_atual = chave
                    else:
                        pass # Ignora linhas soltas na ficha técnica que não têm formato Chave:Valor
                        
                print(f"   ✅ Specs analisadas do texto: {len(specs)} itens.")
            else:
                print("   ⚠️ Aviso: Bloco de Ficha Técnica separada não encontrado.")

            # Filtros adicionais de specs
            specs_limpas = {}
            termos_proibidos = ["garantia", "referência do fornecedor", "imagens meramente ilustrativas"]
            for k, v in specs.items():
                if not any(t in k.lower() for t in termos_proibidos) and not any(t in v.lower() for t in termos_proibidos):
                    specs_limpas[k] = v
                    
            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs_limpas)
            else:
                specs = specs_limpas

            # --- IMAGEM ---
            print("   [Anhanguera] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            # As imagens da plataforma FBITS ficam no subdomínio fbitsstatic.net
            img_tag = soup.find('img', src=re.compile(r'fbitsstatic\.net'))
            if img_tag:
                url_img = img_tag.get('src') or img_tag.get('data-src')

            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                # Remove parâmetros de redimensionamento para obter a qualidade máxima
                if "?" in url_img:
                    url_img = url_img.split("?")[0]
                print(f"   [Anhanguera] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Anhanguera] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[src*='fbitsstatic.net']")
                    if el_img:
                        filename = f"temp_img_anhanguera_{int(time.time())}.png"
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

            print("   [Anhanguera] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO ANHANGUERA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_anhanguera(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        termos_proibidos = [
            "garantia", "frete", "entrega", "pagamento", "boleto", 
            "cartão", "imagens meramente ilustrativas"
        ]

        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean:
                continue

            linha_lower = linha_clean.lower()

            if any(termo in linha_lower for termo in termos_proibidos):
                continue 
            
            # Limpa o traço inicial que a Anhanguera usa em vez de bullets reais
            if linha_clean.startswith("- "):
                linha_clean = "• " + linha_clean[2:]
                
            linhas_limpas.append(linha_clean)

        return "\n".join(linhas_limpas)