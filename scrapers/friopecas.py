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
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            # 3. EXTRAÇÃO INTELIGENTE (DESCRIÇÃO E SPECS MISTURADOS)
            descricao_linhas = []
            specs_texto = {}
            
            desc_div = soup.find(class_=re.compile(r"productDescriptionText|productDescription|friopecas-store-theme-.*-fluid-text"))

            if desc_div:
                # Troca <br> por quebra de linha real (\n)
                for br in desc_div.find_all("br"):
                    br.replace_with("\n")
                
                raw_text = desc_div.get_text(separator=' ')
                linhas = [line.strip() for line in raw_text.split('\n') if len(line.strip()) > 0]
                
                modo_specs = False
                
                for linha in linhas:
                    linha_lower = linha.lower()
                    
                    # Se achar o gatilho, liga o modo de captura de specs e pula a linha do título
                    if "especificações técnicas" in linha_lower or "características técnicas" in linha_lower:
                        modo_specs = True
                        continue
                        
                    # Se achar gatilhos de fim de bloco, desliga o modo specs
                    if modo_specs and ("informação adicional" in linha_lower or "imagens meramente ilustrativas" in linha_lower):
                        modo_specs = False
                    
                    if modo_specs:
                        # Se tem ':', é uma especificação técnica
                        if ":" in linha:
                            partes = linha.split(":", 1)
                            chave = self.limpar_texto(partes[0])
                            valor = self.limpar_texto(partes[1])
                            if chave and valor:
                                specs_texto[chave] = valor
                        else:
                            # Se não tem ':', ignora ou trata como continuação
                            pass
                    else:
                        # Se não está no modo specs, vai para a descrição normal
                        descricao_linhas.append(linha)

            texto_limpo = "\n".join(descricao_linhas)
            descricao = self.limpar_lixo_comercial(texto_limpo)

            # 4. CARACTERÍSTICAS (TENTA O PADRÃO VTEX PRIMEIRO)
            specs = {}
            itens_especificos = soup.find_all(attrs={"data-specification-name": True, "data-specification-value": True})
            
            for item in itens_especificos:
                chave = item.get("data-specification-name")
                valor = item.get("data-specification-value")
                if chave and valor:
                    k = self.limpar_texto(chave)
                    v = self.limpar_texto(valor)
                    if k and v:
                        specs[k] = v

            # Se não achou do jeito padrão, tenta pegar de tabelas
            if not specs:
                tables = soup.find_all("table")
                for table in tables:
                    for row in table.find_all("tr"):
                        cols = row.find_all(["td", "th"])
                        if len(cols) >= 2:
                            k = self.limpar_texto(cols[0].get_text())
                            v = self.limpar_texto(cols[1].get_text())
                            specs[k] = v

            # Se tudo falhar, usa as specs extraídas do texto bagunçado
            if not specs and specs_texto:
                specs = specs_texto

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