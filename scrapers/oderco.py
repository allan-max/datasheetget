# scrapers/oderco.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import re
from .base import BaseScraper

class OdercoScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Oderco] Iniciando Scraper (v2 - Tab Clicker)...")
            
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

            # 1. Espera o carregamento inicial
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-ui-id='page-title-wrapper']"))
                )
            except:
                print("   [Oderco] Aviso: Timeout esperando título.")

            # 2. Scroll para baixo
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1000);")
            time.sleep(2)

            # --- 3. FORÇA ABERTURA DA ABA DE SPECS ---
            # Magento geralmente esconde specs na aba #additional (ou similar)
            print("   [DEBUG] Tentando expandir abas de informação...")
            try:
                # Tenta clicar em qualquer link que pareça ser a aba de especificações
                abas = driver.find_elements(By.CSS_SELECTOR, "a.data.switch")
                for aba in abas:
                    if "adicional" in aba.text.lower() or "especificações" in aba.text.lower() or "additional" in aba.get_attribute("href"):
                        driver.execute_script("arguments[0].click();", aba)
                        time.sleep(2)
                        print("   [DEBUG] Aba clicada via JS.")
            except: pass

            # Força bruta via JS para mostrar o conteúdo caso o clique falhe
            try:
                driver.execute_script("""
                    var blocks = document.querySelectorAll('.data.item.content');
                    blocks.forEach(b => { 
                        b.style.display = 'block'; 
                        b.classList.add('active'); 
                    });
                """)
            except: pass

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Oderco"
            h1 = soup.find("span", attrs={"data-ui-id": "page-title-wrapper"})
            if h1: titulo = self.limpar_texto(h1.get_text())
            elif soup.find("h1", class_="page-title"):
                 titulo = self.limpar_texto(soup.find("h1", class_="page-title").get_text())

            # --- IMAGEM ---
            url_img = None
            img_tag = soup.find("img", class_="fotorama__img")
            if img_tag: url_img = img_tag.get("src")
            if not url_img:
                img_main = soup.find("img", class_="gallery-placeholder__image")
                if img_main: url_img = img_main.get("src")

            # --- DESCRIÇÃO ---
            descricao_bruta = ""
            desc_div = soup.find("div", class_="product attribute description")
            if desc_div:
                val_div = desc_div.find("div", class_="value")
                target = val_div if val_div else desc_div
                descricao_bruta = target.get_text(separator="\n")

            descricao = self.limpar_descricao_cirurgica(descricao_bruta)

            # --- FICHA TÉCNICA (EXTRAÇÃO VIA JS) ---
            # O layout da Oderco usa divs com classe "col data two"
            # Vamos pegar direto do navegador para evitar problemas com espaços duplos na classe
            print("   [DEBUG] Extraindo specs via JS...")
            
            script_specs = """
                var specs = {};
                // Seleciona todas as divs que tenham a classe 'col', 'data' e 'two'
                // O seletor CSS abaixo pega qualquer ordem de classes
                var items = document.querySelectorAll('.col.data.two');
                
                items.forEach(function(item) {
                    var label = item.querySelector('.label');
                    var value = item.querySelector('.data');
                    
                    if (label && value) {
                        var k = label.innerText.trim().replace(':', '');
                        var v = value.innerText.trim();
                        if (k && v) {
                            specs[k] = v;
                        }
                    }
                });
                return specs;
            """
            
            specs_brutas = driver.execute_script(script_specs)
            specs = {}
            
            if specs_brutas:
                print(f"   [DEBUG] {len(specs_brutas)} specs encontradas via JS.")
                specs = specs_brutas
            else:
                print("   [DEBUG] JS falhou. Tentando Fallback BeautifulSoup...")
                # Fallback manual
                specs_container = soup.find("div", id="additional-new") or soup.find("div", class_="additional-attributes")
                if specs_container:
                    items = specs_container.find_all("div", class_=lambda x: x and 'col' in x and 'data' in x)
                    for item in items:
                        lbl = item.find("span", class_="label")
                        val = item.find("span", class_="data")
                        if lbl and val:
                            specs[self.limpar_texto(lbl.get_text())] = self.limpar_texto(val.get_text())

            # Filtros finais
            specs = self.filtrar_specs_oderco(specs)

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
            print(f"   [ERRO ODERCO] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                driver.quit()

    def limpar_descricao_cirurgica(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        texto_limpo = re.sub(r'\s+', ' ', texto_bruto).strip()
        frases = re.split(r'(?<=[.!?])\s+|\n', texto_limpo)
        frases_aprovadas = []
        termos_proibidos = [
            "garantia", "meses", "filial", "estoque", "preço", 
            "oferta", "frete", "entrega", "condições de pagamento", 
            "boleto", "cartão", "cnpj", "endereço", "ncm", 
            "código de barras", "part number"
        ]
        for frase in frases:
            frase_lower = frase.lower()
            if len(frase) < 4: continue
            if not any(termo in frase_lower for termo in termos_proibidos):
                frases_aprovadas.append(frase)
        return "\n".join(frases_aprovadas)

    def filtrar_specs_oderco(self, specs):
        specs_limpas = {}
        # Filtra os dados logísticos que você marcou no arquivo
        ignorar = [
            "filial", "part number", "múltiplo", "código de barras", 
            "ean", "ncm", "origem", "garantia", "quantidade caixa", "peso"
        ]
        
        for k, v in specs.items():
            k_lower = k.lower()
            if not any(x in k_lower for x in ignorar):
                specs_limpas[k] = v
        return specs_limpas