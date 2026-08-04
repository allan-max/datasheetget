# scrapers/martinsatacado.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class MartinsAtacadoScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Martins Atacado] Iniciando Scraper (Auto-Clicker para Material-UI)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            # --- Configuração Selenium Blindado ---
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
            
            print(f"   [Martins Atacado] Acessando: {self.url}")
            driver.get(self.url)

            # 1. Espera o título carregar
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
                )
            except:
                print("   [Martins Atacado] Aviso: Timeout esperando título h1.")

            # 2. Scroll para garantir carregamento dos scripts da página
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1)
            
            # --- O SEGREDO: CLICAR NO "VER MAIS" DO REACT/MUI ---
            print("   [Martins Atacado] À procura de botões 'Ver Mais' para expandir a ficha...")
            driver.execute_script("""
                var elementos = document.querySelectorAll('a, button, span, p');
                for (var i = 0; i < elementos.length; i++) {
                    if (elementos[i].innerText) {
                        // Limpa quebras de linha e espaços extras que o React coloca (como o <!-- -->)
                        var texto = elementos[i].innerText.toLowerCase().replace(/\\s+/g, ' ').trim();
                        if (texto === 'ver mais' || texto.includes('ver mais') || texto.includes('especificações')) {
                            try { elementos[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            
            # Aguarda a animação do painel "MuiCollapse" descer
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 1200);")
            time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- 1. TÍTULO ---
            titulo = "Produto Martins Atacado"
            h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- 2. IMAGEM ---
            print("   [Martins Atacado] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            # Captura imagens principais do carrossel ou div principal
            img_tag = soup.find('img', class_=re.compile(r'MuiBox-root|Image|Carousel'))
            
            # Fallback seguro para encontrar a maior imagem da página se a classe mudar
            if not img_tag or not img_tag.get('src'):
                todas_imagens = soup.find_all('img')
                for img in todas_imagens:
                    src = img.get('src') or ''
                    if 'http' in src and ('produto' in src.lower() or 'catalog' in src.lower() or 'arquivos' in src.lower()):
                        url_img = src
                        break
            else:
                url_img = img_tag.get('src')
                
            if url_img:
                print(f"   [Martins Atacado] URL da imagem: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)
                
            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Martins Atacado] Tentativa de Screenshot da Imagem Principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    # Aponta para a imagem dentro da estrutura geral de vitrine
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[src*='http']")
                    if el_img and el_img.is_displayed() and el_img.size['width'] > 100:
                        filename = f"temp_img_martins_atacado_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        el_img.screenshot(caminho_imagem)
                except:
                    pass

            # --- 3. DESCRIÇÃO ---
            print("   [Martins Atacado] Extraindo Descrição...")
            descricao_bruta = ""
            
            # Procura dentro do MuiCollapse ou qualquer tag <p> que pareça descrição
            collapse_div = soup.find('div', class_=re.compile(r'MuiCollapse-wrapperInner|description'))
            if collapse_div:
                for br in collapse_div.find_all("br"): br.replace_with("\n")
                
                # Apanha parágrafos específicos dentro da estrutura
                p_tags = collapse_div.find_all('p')
                linhas = []
                for p in p_tags:
                    txt = p.get_text(separator=" ", strip=True)
                    if txt and len(txt) > 20: # Evita apanhar títulos pequenos
                        linhas.append(txt)
                descricao_bruta = "\n\n".join(linhas)

            descricao = self.limpar_descricao_martins(descricao_bruta)

            # --- 4. FICHA TÉCNICA (MUITable) ---
            print("   [Martins Atacado] Extraindo Ficha Técnica...")
            specs = {}
            tabelas = soup.find_all('table', class_=re.compile(r'MuiTable-root'))
            
            for tabela in tabelas:
                linhas = tabela.find_all('tr', class_=re.compile(r'MuiTableRow-root'))
                for linha in linhas:
                    tds = linha.find_all('td', class_=re.compile(r'MuiTableCell-root'))
                    if len(tds) >= 2:
                        chave = self.limpar_texto(tds[0].get_text())
                        valor = self.limpar_texto(tds[1].get_text())
                        
                        ignorar = False
                        termos_proibidos_specs = ["garantia", "sku", "código", "ean", "gtin", "estoque", "avaliação"]
                        if any(t in chave.lower() for t in termos_proibidos_specs):
                            ignorar = True
                            
                        if not ignorar and chave and valor:
                            specs[chave] = valor

            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO E CORREÇÃO DE PDF ---
            
            # TRUQUE PARA O PDF: Forçar o caminho absoluto e inverter as barras para o padrão Web/PDF
            if caminho_imagem and os.path.exists(caminho_imagem):
                caminho_absoluto = os.path.abspath(caminho_imagem)
                caminho_imagem = caminho_absoluto.replace("\\", "/")

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [Martins Atacado] Gerando arquivos finais...")
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
            print(f"   ❌ [ERRO MARTINS ATACADO] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_martins(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        
        texto_limpo = re.sub(r'\s+', ' ', texto_bruto).strip()
        frases = re.split(r'(?<=[.!?])\s+', texto_limpo)
        frases_aprovadas = []
        
        termos_proibidos = [
            "garantia", "meses", "tire suas dúvidas", "compre agora",
            "atendimento", "boleto", "cartão", "entrega", "frete",
            "pagamento", "devolução"
        ]
        
        for frase in frases:
            frase_lower = frase.lower()
            if len(frase) < 4: continue
            
            if not any(termo in frase_lower for termo in termos_proibidos):
                frases_aprovadas.append(frase.strip())
                
        return "\n\n".join(frases_aprovadas)