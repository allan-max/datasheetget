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
            print(f"   [Martins Atacado] Iniciando Scraper (Ver Mais Dinâmico e Imagem Responsiva)...")
            
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

            # 1. Espera a página processar os scripts
            time.sleep(4) 
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)
            
            # --- O SEGREDO DO CLIQUE: LEITURA DE HTML CRU ---
            # Clica no "Ver Mais" apenas para expandir a div MuiCollapse, quer tenha o <!-- --> ou não.
            print("   [Martins Atacado] Verificando botão 'Ver Mais'...")
            driver.execute_script("""
                var els = document.querySelectorAll('a, button, span, div');
                for (var i = 0; i < els.length; i++) {
                    var htmlInterno = els[i].innerHTML || '';
                    if (htmlInterno.includes('Ver') && htmlInterno.includes('Mais')) {
                        try { els[i].click(); } catch(e) {}
                    }
                }
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

            # --- 2. IMAGEM (Usando o padrão exato da loja) ---
            print("   [Martins Atacado] Extraindo Imagem...")
            url_img = None
            
            # Tenta pegar pela pasta padronizada de imagens do catálogo deles
            img_tag = soup.find('img', src=re.compile(r'catalogoimg'))
            
            if not img_tag:
                # Alternativa: O padrão data-nimg="responsive"
                img_tag = soup.find('img', attrs={"data-nimg": "responsive"})

            if img_tag:
                raw_src = img_tag.get('src')
                if raw_src:
                    url_img = raw_src
                    if url_img.startswith("/"):
                        url_img = "https://www.martinsatacado.com.br" + url_img

            caminho_imagem = None
            if url_img:
                print(f"   [Martins Atacado] URL da Imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)
            else:
                print("   ⚠️ Nenhuma imagem principal identificada nas tags.")

            # --- 3. DESCRIÇÃO E FICHA TÉCNICA (EXTRAÇÃO DO BLOCO MUI) ---
            print("   [Martins Atacado] Lendo o bloco de Especificações revelado...")
            descricao = "Descrição indisponível."
            specs = {}
            
            # Procura a div específica MuiCollapse-wrapperInner
            collapse = soup.find('div', class_=re.compile(r'MuiCollapse-wrapperInner'))
            
            if collapse:
                # Extrai a Descrição (dentro do H2)
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
                print("   ⚠️ Aviso: Bloco MuiCollapse-wrapperInner não encontrado (o clique pode não ter funcionado ou a página não tem especificações extra).")

            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO E CORREÇÃO DE PDF ---
            # Força o caminho absoluto e inverte barras para o gerador de PDF ler sem falhas
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