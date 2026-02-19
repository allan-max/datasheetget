# scrapers/fujioka.py
import requests
import re
from bs4 import BeautifulSoup
from .base import BaseScraper

class FujiokaScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [Fujioka] Acessando: {self.url}")
            # Headers específicos que ajudam a não ser bloqueado pela VTEX
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            }
            
            response = requests.get(self.url, headers=headers, timeout=20)
            soup = BeautifulSoup(response.content, 'html.parser')

            # 1. Título
            title_tag = soup.find(class_="productName")
            titulo = self.limpar_texto(title_tag.get_text()) if title_tag else "Fujioka Produto"

            # 2. Descrição (Com limpeza de lixo comercial)
            desc_tag = soup.find(class_="productDescription")
            descricao_bruta = self.limpar_texto(desc_tag.get_text()) if desc_tag else ""
            descricao = self.limpar_lixo_comercial(descricao_bruta)

            # 3. IMAGEM (Lógica Reforçada)
            url_img = None
            
            # Tentativa A: Meta Tag (Geralmente a melhor)
            meta_img = soup.find("meta", property="og:image")
            if meta_img and meta_img.get("content"):
                url_img = meta_img.get("content")
            
            # Tentativa B: Busca por classe de imagem de produto
            if not url_img:
                img_tag = soup.find("div", class_="product-image")
                if img_tag and img_tag.find("img"):
                    url_img = img_tag.find("img").get("src")
                elif soup.find("img", id="image-main"):
                    url_img = soup.find("img", id="image-main").get("src")

            # Tentativa C: Busca genérica por imagens da VTEX (arquivos/ids)
            if not url_img:
                imgs = soup.find_all("img")
                for i in imgs:
                    src = i.get("src", "")
                    if "arquivos/ids" in src:
                        url_img = src
                        break

            # TRUQUE DE QUALIDADE: Força a imagem a ficar grande (1000x1000)
            # A Fujioka/VTEX costuma entregar links tipo: ...-292-292/imagem.jpg
            if url_img:
                url_img = re.sub(r'-\d{2,4}-\d{2,4}', '-1000-1000', url_img)

            # 4. Características
            specs = {}
            all_rows = soup.find_all("tr")
            for row in all_rows:
                key_cell = row.find(class_=lambda x: x and 'name-field' in x)
                val_cell = row.find(class_=lambda x: x and 'value-field' in x)

                if key_cell and val_cell:
                    k = self.limpar_texto(key_cell.get_text())
                    v = self.limpar_texto(val_cell.get_text())
                    if k and v:
                        specs[k] = v
            
            # Filtra specs inúteis (Garantia, etc)
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
            return {'sucesso': False, 'erro': str(e)}