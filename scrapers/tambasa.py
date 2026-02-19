# scrapers/tambasa.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import json
import re
from .base import BaseScraper

class TambasaScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Tambasa] Iniciando Scraper...")
            
            # --- Configuração Anti-Bloqueio ---
            opts = Options()
            opts.add_argument("--headless=new") 
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument('--ignore-certificate-errors')
            opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

            driver = webdriver.Chrome(options=opts)
            driver.get(self.url)

            # Espera carregar o título principal
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "js-product-name-detail"))
                )
            except:
                print("   [Tambasa] Aviso: Timeout esperando título.")

            # Scroll para garantir carregamento de imagens
            driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- 1. TÍTULO ---
            titulo = "Produto Tambasa"
            h1 = soup.find("h1", class_="js-product-name-detail")
            if h1: titulo = self.limpar_texto(h1.get_text())

            # --- 2. IMAGEM ---
            url_img = None
            img_tag = soup.find("img", class_="js-product-detail__large-image")
            if img_tag:
                src = img_tag.get("src")
                if src:
                    # O site usa URLs relativas (/imagem/...)
                    if src.startswith("/"):
                        url_img = "https://loja.tambasa.com" + src
                    else:
                        url_img = src

            # --- 3. DESCRIÇÃO E SPECS (Estratégia Híbrida) ---
            descricao_bruta = ""
            specs = {}

            # TENTATIVA 1: JSON-LD (Dados estruturados escondidos)
            # A Tambasa coloca dados muito bons dentro de tags <script type="application/ld+json">
            scripts_json = soup.find_all("script", type="application/ld+json")
            for script in scripts_json:
                try:
                    data = json.loads(script.string)
                    # Verifica se é uma lista ou dict
                    if isinstance(data, dict):
                         data = [data]
                    
                    for item in data:
                        # Pega descrição do JSON
                        if "description" in item and not descricao_bruta:
                            descricao_bruta = item["description"]
                        
                        # Pega specs do JSON (alguns produtos tem campo 'specifications')
                        if "specifications" in item:
                             for k, v in item["specifications"].items():
                                 specs[k] = v
                except: pass

            # TENTATIVA 2: HTML Visual (Fallback)
            if not descricao_bruta:
                desc_container = soup.find("div", class_="product-detail__descriptions-text")
                if desc_container:
                    # Remove scripts e estilos de dentro
                    for tag in desc_container(["script", "style"]): tag.extract()
                    descricao_bruta = desc_container.get_text(separator="\n")

            # --- 4. LIMPEZA CIRÚRGICA DA DESCRIÇÃO ---
            # Remove frases específicas de garantia, preço, etc, mas mantém o resto.
            descricao = self.limpar_descricao_cirurgica(descricao_bruta)

            # --- 5. FICHA TÉCNICA (Complementar) ---
            # Busca as caixas de atributos visuais
            # Container: product-detail__descriptions-attributes
            attr_container = soup.find("div", class_="product-detail__descriptions-attributes")
            if attr_container:
                items = attr_container.find_all("div", class_="product-detail__attribute")
                for item in items:
                    lbl = item.find("span", class_="product-detail__attribute-title")
                    val = item.find("span", class_="product-detail__attribute-text")
                    
                    # Às vezes o valor é um link
                    if not val:
                        val = item.find("a", class_="product-detail__attribute-text")

                    if lbl and val:
                        k = self.limpar_texto(lbl.get_text())
                        v = self.limpar_texto(val.get_text())
                        if k and v:
                            specs[k] = v

            # Filtra specs indesejadas
            specs = self.filtrar_specs_tambasa(specs)

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
            print(f"   [ERRO TAMBASA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                driver.quit()

    def limpar_descricao_cirurgica(self, texto_bruto):
        """
        Divide o texto em frases. Analisa uma por uma.
        Se a frase tiver palavras proibidas (garantia, preço, loja, telefone), ela é deletada.
        O resto do texto é mantido.
        """
        if not texto_bruto: return "Descrição indisponível."

        # Limpa espaços excessivos primeiro
        texto_limpo = re.sub(r'\s+', ' ', texto_bruto).strip()
        
        # Divide por pontuação (. ! ?) mantendo a pontuação para reconstruir
        # O regex abaixo divide frases preservando o delimitador
        frases = re.split(r'(?<=[.!?])\s+', texto_limpo)
        
        frases_aprovadas = []
        
        termos_proibidos = [
            "garantia", "meses de garantia", "assistência técnica", 
            "consulte o site", "atendimento", "sac", "telefone", 
            "loja", "tambasa", "preço", "oferta", "frete", "entrega",
            "condições de pagamento", "boleto", "cartão", "estoque",
            "vendido por", "entregue por", "cnpj", "endereço",
            "www.", ".com.br", "origem", "importado"
        ]

        for frase in frases:
            frase_lower = frase.lower()
            contem_proibido = False
            
            for termo in termos_proibidos:
                if termo in frase_lower:
                    contem_proibido = True
                    break
            
            # Regra extra: Se a frase for muito curta e parecer lixo (ex: "EAN")
            if len(frase) < 4:
                contem_proibido = True

            if not contem_proibido:
                frases_aprovadas.append(frase)

        return "\n\n".join(frases_aprovadas)

    def filtrar_specs_tambasa(self, specs):
        """Filtro específico para remover dados logísticos da Tambasa"""
        specs_limpas = {}
        ignorar = [
            "ean", "código", "origem", "embalagem", "quantidade", 
            "ncm", "peso bruto", "peso liquido", "dun", "sku", 
            "garantia", "marca" # Marca já costuma ir no título
        ]
        
        for k, v in specs.items():
            k_lower = k.lower()
            if not any(x in k_lower for x in ignorar):
                specs_limpas[k] = v
        return specs_limpas