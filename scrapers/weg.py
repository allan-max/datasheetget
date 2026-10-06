from bs4 import BeautifulSoup

from .universal import UniversalScraper


class WegScraper(UniversalScraper):
    ADAPTER = "WEG"
    exigir_imagem = True
    espera_css = "h1.product-card-title"

    def extrair_html(self, html, url):
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.select_one("h1.product-card-title")
        titulo = self.limpar_texto(h1.get_text(" ", strip=True)) if h1 else ""
        bloco = soup.select_one(".xtt-product-description")
        descricao = self.limpar_descricao(str(bloco)) if bloco else ""
        foto = soup.select_one("a.xtt-product-image-zoom")
        imagem = foto.get("href", "") if foto else ""

        specs = {}
        for tabela in soup.select("table.table"):
            for linha in tabela.find_all("tr"):
                celulas = linha.find_all(["th", "td"], recursive=False)
                if len(celulas) == 2:
                    self.adicionar_spec(specs, celulas[0].get_text(" ", strip=True),
                                       celulas[1].get_text(" ", strip=True))
        return titulo, descricao, specs, imagem, "selenium"
