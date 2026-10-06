from bs4 import BeautifulSoup

from .universal import UniversalScraper


class EatonScraper(UniversalScraper):
    ADAPTER = "EATON"
    exigir_imagem = True
    espera_css = ".product-highlights__content"
    imagem_css = 'img[alt*="5E"]'

    def extrair_html(self, html, url):
        soup = BeautifulSoup(html, "html.parser")
        titulo_tag = soup.find("h1", string=lambda s: s and "Eaton" in s)
        titulo = self.limpar_texto(titulo_tag.get_text()) if titulo_tag else ""
        bloco = soup.select_one(".product-family-card__description")
        descricao = self.limpar_descricao(str(bloco)) if bloco else ""
        foto = soup.find("img", alt=lambda a: a and "5E" in a)
        imagem = foto.get("src", "") if foto else ""
        specs = {}
        for linha in soup.select(".product-highlights__content"):
            chave = linha.select_one(".product-highlights__title")
            valor = linha.select_one(".product-highlights__text")
            if chave and valor:
                self.adicionar_spec(specs, chave.get_text(" ", strip=True),
                                   valor.get_text(" ", strip=True))
        return titulo, descricao, specs, imagem, "selenium"
