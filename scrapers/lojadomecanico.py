# scrapers/lojadomecanico.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import re # Importante para a limpeza cirúrgica
from .base import BaseScraper

class LojaDoMecanicoScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [LojaDoMecanico] Iniciando Scraper (V3 - Limpeza Fina)...")
            
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
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "product-name"))
                )
            except:
                print("   [DEBUG] Tempo limite excedido. Tentando ler HTML atual...")
            
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Loja do Mecânico"
            h1 = soup.find("h1", class_="product-name")
            if h1:
                titulo = self.limpar_texto(h1.get_text())

            # --- IMAGEM ---
            url_img = None
            img_tag = soup.find("img", class_="product-zoom")
            if img_tag:
                url_img = img_tag.get("data-image") or img_tag.get("src")
            
            if url_img:
                if not url_img.startswith("http"):
                     url_img = "https:" + url_img if url_img.startswith("//") else "https://www.lojadomecanico.com.br" + url_img

            # --- DESCRIÇÃO ---
            descricao_bruta = ""
            desc_container = soup.find("div", id="descricao")
            if desc_container:
                descricao_bruta = desc_container.get_text(separator="\n", strip=True)
            
            # Aplica a limpeza aprimorada
            descricao = self.limpar_descricao_loja(descricao_bruta)

            # --- FICHA TÉCNICA ---
            specs = {}
            linhas = soup.find_all("tr")
            for linha in linhas:
                chave_td = linha.find("td", class_=lambda c: c and "text-description" in c)
                valor_td = linha.find("td", class_=lambda c: c and "text-value" in c)
                
                if chave_td and valor_td:
                    chave = self.limpar_texto(chave_td.get_text())
                    valor = self.limpar_texto(valor_td.get_text())
                    if chave and valor:
                        specs[chave] = valor

            specs = self.filtrar_specs_loja(specs)

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
            print(f"   [ERRO LOJA DO MECANICO] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                driver.quit()

    def limpar_descricao_loja(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        # 1. REMOÇÃO CIRÚRGICA DE GARANTIA (Regex)
        # Remove "- Garantia: ...", "Garantia: ..." até o fim da linha ou do bloco
        # Ex: "Peso: 8,5Kg - Garantia: 1 Ano" vira "Peso: 8,5Kg"
        texto_limpo = re.sub(r'-\s*Garantia:.*', '', texto_bruto, flags=re.IGNORECASE)
        texto_limpo = re.sub(r'Garantia:.*', '', texto_limpo, flags=re.IGNORECASE)

        linhas = texto_limpo.splitlines()
        linhas_limpas = []
        
        # Frases que, se aparecerem na linha, matam a linha inteira
        frases_banidas = [
            "imagens meramente ilustrativas",
            "todas as informações divulgadas",
            "responsabilidade do fabricante",
            "marca.:",
            "ref.:"
        ]
        
        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean: 
                if linhas_limpas and linhas_limpas[-1] != "": linhas_limpas.append("")
                continue
            
            linha_lower = linha_clean.lower()
            
            # 2. FILTRO DE FRASES BANIDAS
            if any(banida in linha_lower for banida in frases_banidas):
                continue

            # 3. FILTRO DE MARCA SOLTA (Ex: "WBERTOLO")
            # Remove se for uma palavra única, maiúscula e curta (provavelmente nome da marca perdido)
            if len(linha_clean) < 30 and linha_clean.isupper() and " " not in linha_clean:
                continue

            linhas_limpas.append(linha_clean)

        return "\n".join(linhas_limpas)

    def filtrar_specs_loja(self, specs):
        specs_limpas = {}
        ignorar = ["garantia", "ver parcelas"]
        for k, v in specs.items():
            k_lower = k.lower()
            if not any(x in k_lower for x in ignorar):
                specs_limpas[k] = v
        return specs_limpas