# scrapers/dimensional.py
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper
import urllib3

# Desabilita avisos SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class DimensionalScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [Dimensional] Iniciando Scraper...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Referer": "https://www.google.com/"
            }

            # 1. Requisição Padrão
            response = requests.get(self.url, headers=headers, timeout=20, verify=False)
            
            if response.status_code != 200:
                raise Exception(f"Erro HTTP {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')

            # --- TÍTULO ---
            # Identificado: <span class="vtex-store-components-3-x-productBrand ...">
            titulo = "Produto Dimensional"
            # Busca spans cuja classe contenha 'productBrand'
            span_titulo = soup.find("span", class_=lambda c: c and "productBrand" in c)
            if span_titulo:
                titulo = self.limpar_texto(span_titulo.get_text())

            # --- IMAGEM ---
            # Identificado: <img ... class="...productImageTag--main" src="...">
            url_img = None
            img_tag = soup.find("img", class_=lambda c: c and "productImageTag--main" in c)
            
            if img_tag:
                url_img = img_tag.get("src")
                # Se for srcset, pega o primeiro link
                if not url_img and img_tag.get("srcset"):
                    url_img = img_tag.get("srcset").split(" ")[0]

            # --- DESCRIÇÃO ---
            # Identificado: <div class="vtex-store-components-3-x-productDescriptionText ...">
            descricao = "Descrição indisponível."
            div_desc = soup.find("div", class_=lambda c: c and "productDescriptionText" in c)
            
            if div_desc:
                descricao = div_desc.get_text(separator="\n", strip=True)

            # --- FICHA TÉCNICA ---
            # O site tem dois tipos de estrutura para specs misturadas.
            specs = {}
            
            # Container principal das especificações
            container_specs = soup.find("div", class_=lambda c: c and "contentSpecifications" in c)
            
            if container_specs:
                # TIPO 1: Linhas de Tabela (.specificationsRow)
                rows_1 = container_specs.find_all("div", class_=lambda c: c and "specificationsRow" in c)
                for row in rows_1:
                    name_div = row.find("div", class_=lambda c: c and "specificationsName" in c)
                    val_div = row.find("div", class_=lambda c: c and "specificationsValue" in c)
                    
                    if name_div and val_div:
                        k = self.limpar_texto(name_div.get_text())
                        v = self.limpar_texto(val_div.get_text())
                        
                        # FILTRO: Ignorar Datasheet/Baixar Arquivo conforme solicitado 
                        if "datasheet" in k.lower() or "baixar arquivo" in v.lower():
                            continue
                            
                        specs[k] = v

                # TIPO 2: Grupos (.containerEspecificationsGroup)
                # O HTML mostra classes como "especificationName" (com 'e' no começo)
                rows_2 = container_specs.find_all("div", class_=lambda c: c and "containerEspecificationsGroup" in c)
                for row in rows_2:
                    # Busca classes que contenham 'Name' e 'Value' dentro desse grupo
                    # Nota: O site usa 'especificationName' (pt-br) vs 'specificationsName' (en) em locais diferentes
                    name_div = row.find("div", class_=lambda c: c and "specificationName" in c) # Pega Especification ou Specification
                    val_div = row.find("div", class_=lambda c: c and "specificationValue" in c)
                    
                    if name_div and val_div:
                        k = self.limpar_texto(name_div.get_text())
                        v = self.limpar_texto(val_div.get_text())
                        
                        if "datasheet" in k.lower() or "baixar arquivo" in v.lower():
                            continue

                        specs[k] = v

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
            print(f"   [ERRO DIMENSIONAL] {e}")
            return {'sucesso': False, 'erro': str(e)}