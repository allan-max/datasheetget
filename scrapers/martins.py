# scrapers/martins.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class MartinsScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Martins Atacado] Iniciando Scraper V2 (Ataque ao Material-UI e Og:Image)...")
            
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
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)
            
            print(f"   [Martins Atacado] Acessando: {self.url}")
            driver.get(self.url)

            # 1. Espera a página processar os scripts do React (Pausa humana)
            print("   [Martins Atacado] Aguardando a montagem do site...")
            time.sleep(4) 
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)
            
            # --- O SEGREDO DO CLIQUE (IGNORA COMENTÁRIOS E ESPAÇOS OCULTOS) ---
            print("   [Martins Atacado] Forçando clique no botão 'Ver Mais'...")
            driver.execute_script("""
                var els = document.querySelectorAll('a, button, span, p, div');
                els.forEach(function(el) {
                    var text = el.textContent || el.innerText || '';
                    // Limpeza bruta: remove TUDO que for espaço ou quebra de linha
                    var textLimpo = text.replace(/\\s+/g, '').toLowerCase();
                    if (textLimpo.includes('vermais') || textLimpo.includes('especificações')) {
                        try { el.click(); } catch(e) {}
                    }
                });
            """)
            
            # Aguarda a animação do painel (Collapse) revelar as especificações
            time.sleep(2)
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- 1. TÍTULO ---
            titulo = "Produto Martins Atacado"
            h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- 2. IMAGEM (OG:IMAGE É A SALVAÇÃO) ---
            print("   [Martins Atacado] Capturando Imagem Principal (À prova de falhas)...")
            url_img = None
            caminho_imagem = None
            
            # Procura pela imagem oficial definida pelo Martins Atacado no cabeçalho oculto da página
            meta_img = soup.find("meta", property="og:image")
            if meta_img and meta_img.get("content"):
                url_img = meta_img.get("content")
            
            # Se a meta tag falhar, tenta procurar a imagem grande dentro do site
            if not url_img:
                imagens = soup.find_all('img')
                for img in imagens:
                    src = img.get('src') or ''
                    # Ignora logotipos, ícones de menu, etc.
                    if 'produto' in src.lower() or 'arquivos' in src.lower() or 'catalog' in src.lower():
                        if 'logo' not in src.lower() and 'icon' not in src.lower():
                            url_img = src
                            break

            if url_img:
                print(f"   [Martins Atacado] URL da Imagem Correta: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # --- 3. DESCRIÇÃO E FICHA TÉCNICA (EXTRAÇÃO EXATA DO BLOCO MUI) ---
            print("   [Martins Atacado] Lendo o bloco de Especificações revelado...")
            descricao = "Descrição indisponível."
            specs = {}
            
            # Procura a div específica que me mostrou no código: MuiCollapse-wrapperInner
            collapse = soup.find('div', class_=re.compile(r'MuiCollapse-wrapperInner'))
            
            if collapse:
                # Extrai a Descrição (dentro do H2/P do collapse)
                h2 = collapse.find('h2')
                if h2:
                    for br in h2.find_all("br"): br.replace_with("\n")
                    descricao = self.limpar_texto(h2.get_text(separator="\n"))
                
                # Extrai a Ficha Técnica (Tabela dentro do collapse)
                tabela = collapse.find('table')
                if tabela:
                    linhas = tabela.find_all('tr')
                    for linha in linhas:
                        tds = linha.find_all(['th', 'td'])
                        if len(tds) >= 2:
                            chave = self.limpar_texto(tds[0].get_text())
                            valor = self.limpar_texto(tds[1].get_text())
                            
                            ignorar = False
                            termos_proibidos = ["garantia", "código", "sku", "ean", "gtin", "estoque"]
                            if any(t in chave.lower() for t in termos_proibidos):
                                ignorar = True
                                
                            if not ignorar and chave and valor:
                                specs[chave] = valor
            else:
                print("   ⚠️ Aviso: Bloco MuiCollapse-wrapperInner não encontrado após o clique.")

            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO E CORREÇÃO DE PDF ---
            
            # Força o caminho absoluto e inverte barras para o gerador de PDF
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