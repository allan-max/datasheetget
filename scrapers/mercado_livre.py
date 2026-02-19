# scrapers/mercado_livre.py
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper

class MercadoLivreScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [ML] Acessando: {self.url}")
            response = requests.get(self.url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')

            # Título
            h1 = soup.find('h1', class_='ui-pdp-title')
            titulo = h1.text.strip() if h1 else "Produto Mercado Livre"

            # Descrição (COM LIMPEZA)
            desc_elem = soup.find('p', class_='ui-pdp-description__content')
            descricao_bruta = desc_elem.text if desc_elem else ""
            # --- AQUI APLICAMOS O FILTRO ---
            descricao = self.limpar_lixo_comercial(descricao_bruta)

            # Imagem (Meta Tag)
            url_img = None
            meta_img = soup.find('meta', property='og:image')
            if meta_img and meta_img.get('content'):
                url_img = meta_img['content']
            else:
                img_container = soup.find('img', class_='ui-pdp-image')
                if img_container:
                    src = img_container.get('src')
                    if src and "http" in src: url_img = src

            # Características
            specs = {}
            rows = soup.find_all('tr', class_='andes-table__row')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    specs[th.text.strip()] = td.text.strip()
            
            # --- FILTRA AS SPECS TAMBÉM (Remove 'Garantia', etc) ---
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