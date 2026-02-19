# scrapers/fastshop.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import urllib.parse
import re
from .base import BaseScraper

class FastShopScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [FastShop] Iniciando Scraper (v2 - Line Breaker)...")
            
            # --- Configuração ---
            opts = Options()
            opts.add_argument("--headless=new") 
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument('--ignore-certificate-errors')
            opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

            driver = webdriver.Chrome(options=opts)
            driver.get(self.url)

            # 1. Espera Título
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
            except: pass

            # 2. Scroll e Expansão
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1200);")
            time.sleep(2)
            
            # Tenta clicar em "Ver mais"
            try:
                botoes = driver.find_elements(By.TAG_NAME, "button")
                for btn in botoes:
                    if "ver mais" in btn.text.lower():
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(1)
                        break
            except: pass

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- 1. TÍTULO ---
            titulo = "Produto FastShop"
            header_div = soup.find("div", attrs={"data-fs-product-title-header": "true"})
            if header_div and header_div.find("h1"):
                titulo = self.limpar_texto(header_div.find("h1").get_text())
            else:
                h1 = soup.find("h1")
                if h1: titulo = self.limpar_texto(h1.get_text())

            # --- 2. IMAGEM ---
            url_img = None
            img_tag = soup.find("img", attrs={"data-fs-image": "true"})
            if img_tag:
                raw_src = img_tag.get("src")
                if raw_src:
                    if "/_next/image" in raw_src and "url=" in raw_src:
                        parsed = urllib.parse.urlparse(raw_src)
                        qs = urllib.parse.parse_qs(parsed.query)
                        if 'url' in qs: url_img = qs['url'][0]
                    else:
                        url_img = raw_src

            # --- 3. MINERAÇÃO DE SPECS E DESCRIÇÃO ---
            descricao_final = ""
            specs = {}
            
            # Localiza o container da descrição
            desc_div = soup.find("div", attrs={"data-testid": "long-description-expanded"})
            if not desc_div:
                desc_div = soup.find("div", class_=lambda x: x and "LongDescription" in x)

            if desc_div:
                # ESTRATÉGIA DE QUEBRA DE LINHA (<br>)
                # O método get_text(separator="\n") substitui <br> por quebras de linha reais
                texto_completo = desc_div.get_text(separator="\n")
                
                linhas = texto_completo.split("\n")
                linhas_descricao = []
                
                # Flag para saber se entramos numa "zona de especificações"
                zona_tecnica = False

                for linha in linhas:
                    linha = self.limpar_texto(linha)
                    if not linha: continue

                    linha_lower = linha.lower()

                    # Detecta cabeçalhos de specs
                    headers_specs = ["características", "especificações técnicas", "dimensões e peso", "itens inclusos"]
                    if any(x == linha_lower for x in headers_specs):
                        zona_tecnica = True
                        continue # Não adiciona o título na descrição

                    # Tenta extrair chave:valor
                    if ":" in linha:
                        partes = linha.split(":", 1)
                        if len(partes) == 2:
                            k = partes[0].strip()
                            v = partes[1].strip()
                            
                            # Validação: Chaves técnicas costumam ser curtas (< 40 chars)
                            # E valores não devem ser vazios
                            if len(k) < 40 and len(v) > 0:
                                # Filtra lixo comercial nas chaves
                                if "garantia" not in k.lower() and "ean" not in k.lower():
                                    specs[k] = v
                                    # Se achou uma spec, considera que estamos em zona técnica ou é uma linha técnica
                                    # Portanto, NÃO adiciona na descrição
                                    continue
                    
                    # Se não for spec, verificamos se é texto útil para descrição
                    # Ignora linhas curtas soltas que não são frases
                    if len(linha) > 3:
                        linhas_descricao.append(linha)

                descricao_final = "\n\n".join(linhas_descricao)

            # --- 4. LIMPEZA COMERCIAL ---
            descricao = self.limpar_descricao_cirurgica(descricao_final)

            # --- 5. FILTRO FINAL DE SPECS ---
            specs = self.filtrar_specs_fastshop(specs)

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": self.baixar_imagem_temp(url_img)
            }

            arquivos = self.gerar_arquivos_finais(dados)

            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs,
                'total_imagens': 1,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   [ERRO FASTSHOP] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                driver.quit()

    def limpar_descricao_cirurgica(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        texto_limpo = re.sub(r'\s+', ' ', texto_bruto).strip()
        frases = re.split(r'(?<=[.!?])\s+', texto_limpo)
        frases_aprovadas = []
        termos_proibidos = [
            "garantia", "meses", "sac", "atendimento", "telefone", 
            "loja", "fast shop", "preço", "oferta", "frete", "entrega",
            "condições de pagamento", "boleto", "cartão", "estoque",
            "vendido por", "entregue por", "cnpj", "endereço", "ean",
            "código de barras", "itens inclusos", "ver mais", "ver menos"
        ]
        for frase in frases:
            frase_lower = frase.lower()
            if len(frase) < 4: continue
            if not any(termo in frase_lower for termo in termos_proibidos):
                frases_aprovadas.append(frase)
        return "\n\n".join(frases_aprovadas)

    def filtrar_specs_fastshop(self, specs):
        specs_limpas = {}
        ignorar = ["garantia", "ean", "código", "modelo", "sac", "fornecedor", "ver mais"]
        for k, v in specs.items():
            if not any(x in k.lower() for x in ignorar):
                specs_limpas[k] = v
        return specs_limpas