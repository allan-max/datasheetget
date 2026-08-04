# scrapers/mercadolivre.py
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
            print(f"   [Mercado Livre] Iniciando Scraper (Tática Googlebot SEO - Imune a Login)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            # --- Configuração Selenium com Camuflagem de SEO (Googlebot) ---
            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            
            # O SEGREDO: A assinatura exata do rastreador do Google! O ML é obrigado a deixar passar.
            options.add_argument("--user-agent=Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
            
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)

            print(f"   [Mercado Livre] Acessando URL como Googlebot: {self.url}")
            driver.get(self.url)

            # 1. Espera o título carregar
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1.ui-pdp-title"))
                )
            except:
                print("   [Mercado Livre] Aviso: Timeout esperando título. A extrair o que foi carregado...")

            # 2. Scroll leve para garantir carregamento
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- 1. TÍTULO ---
            titulo = "Produto Mercado Livre"
            h1 = soup.find('h1', class_=re.compile(r'ui-pdp-title'))
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- 2. IMAGEM ---
            print("   [Mercado Livre] A extrair Imagem...")
            url_img = None
            
            # O ML guarda a imagem de alta resolução (zoom) no data-zoom ou exibe diretamente a imagem da galeria
            img_tag = soup.find('img', class_=re.compile(r'ui-pdp-image|ui-pdp-gallery__figure__image'))
            if img_tag:
                url_img = img_tag.get('data-zoom') or img_tag.get('src')

            caminho_imagem = None
            if url_img:
                print(f"   [Mercado Livre] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # --- 3. DESCRIÇÃO ---
            print("   [Mercado Livre] A extrair Descrição...")
            descricao_bruta = ""
            desc_tag = soup.find('p', class_=re.compile(r'ui-pdp-description__content'))
            if desc_tag:
                for br in desc_tag.find_all("br"): br.replace_with("\n")
                descricao_bruta = desc_tag.get_text(separator="\n")
            
            descricao = self.limpar_descricao_ml(descricao_bruta)

            # --- 4. FICHA TÉCNICA ---
            print("   [Mercado Livre] A extrair Ficha Técnica...")
            specs = {}
            tabelas = soup.find_all('table', class_=re.compile(r'andes-table'))
            
            for tabela in tabelas:
                linhas = tabela.find_all('tr')
                for linha in linhas:
                    th = linha.find('th')
                    td = linha.find('td')
                    
                    if th and td:
                        chave = self.limpar_texto(th.get_text())
                        valor = self.limpar_texto(td.get_text())
                        
                        ignorar = False
                        termos_proibidos = ["garantia", "código universal", "sku", "ean", "gtin", "condição", "quantidade"]
                        if any(t in chave.lower() for t in termos_proibidos):
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

            print("   [Mercado Livre] A gerar PDF e Word instantâneos...")
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
            print(f"   ❌ [ERRO MERCADO LIVRE] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_ml(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        termos_proibidos = [
            "garantia", "mercado envio", "mercado pago", "tire suas dúvidas", 
            "perguntas", "clique em comprar", "aguardamos sua compra", "frete", 
            "atendimento", "nota fiscal", "nf-e", "pronta entrega", "devolução grátis"
        ]
        
        for linha in linhas:
            linha_lower = linha.lower().strip()
            if not linha_lower: continue
            if any(termo in linha_lower for termo in termos_proibidos): continue
            linhas_limpas.append(linha.strip())
            
        return "\n\n".join(linhas_limpas)