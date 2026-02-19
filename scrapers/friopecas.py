# scrapers/friopecas.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import re
from .base import BaseScraper

class FrioPecasBot(BaseScraper):
    def executar(self):
        driver = None
        try:
            # --- CONFIGURAÇÃO DO NAVEGADOR ---
            opts = Options()
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,3000")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument(f'user-agent={self.headers["User-Agent"]}')
            
            driver = webdriver.Chrome(options=opts)

            print(f"   [FrioPecas] Acessando: {self.url}")
            driver.get(self.url)
            
            # Scroll para forçar carregamento das specs
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(2)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # 1. TÍTULO
            title_div = soup.find(class_=re.compile(r"productName|vtex-store-components-3-x-productNameContainer"))
            titulo = self.limpar_texto(title_div.get_text()) if title_div else "Produto FrioPeças"

            # 2. IMAGEM
            url_img = None
            img = soup.find("img", class_=re.compile(r"productImageTag--main"))
            if img: url_img = img.get("src")
            if not url_img:
                # Backup pela Meta Tag
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            # 3. DESCRIÇÃO (TRATAMENTO DE HTML SUJO)
            descricao = "Informações não detalhadas."
            
            # Procura a div exata que você mostrou no log
            desc_div = soup.find(class_=re.compile(r"productDescriptionText"))
            if not desc_div:
                desc_div = soup.find(class_=re.compile(r"productDescription"))

            if desc_div:
                # TRUQUE DE MESTRE: Troca <br> por quebra de linha real (\n)
                for br in desc_div.find_all("br"):
                    br.replace_with("\n")
                
                # Pega o texto limpo
                raw_text = desc_div.get_text()
                
                # Filtra linhas vazias e lixo comercial
                linhas = [line.strip() for line in raw_text.split('\n') if len(line.strip()) > 0]
                texto_limpo = "\n".join(linhas)
                
                descricao = self.limpar_lixo_comercial(texto_limpo)

            # 4. CARACTERÍSTICAS (LEITURA LIMPA DOS ATRIBUTOS DATA)
            specs = {}
            
            # O HTML da Friopeças tem os dados puros dentro das tags span:
            # <span data-specification-name="Voltagem" data-specification-value="220V">
            
            itens_especificos = soup.find_all(attrs={"data-specification-name": True, "data-specification-value": True})
            
            for item in itens_especificos:
                chave = item.get("data-specification-name")
                valor = item.get("data-specification-value")
                
                if chave and valor:
                    k = self.limpar_texto(chave)
                    v = self.limpar_texto(valor)
                    
                    # Evita duplicidade e chaves vazias
                    if k and v:
                        specs[k] = v

            # Se a estratégia acima falhar (site antigo), tenta tabelas
            if not specs:
                tables = soup.find_all("table")
                for table in tables:
                    for row in table.find_all("tr"):
                        cols = row.find_all(["td", "th"])
                        if len(cols) >= 2:
                            k = self.limpar_texto(cols[0].get_text())
                            v = self.limpar_texto(cols[1].get_text())
                            specs[k] = v

            # Filtro final de lixo nas specs
            specs = self.filtrar_specs(specs)

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
            print(f"   [ERRO FRIOPECAS] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver: driver.quit()