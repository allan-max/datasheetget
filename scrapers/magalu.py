from bs4 import BeautifulSoup

from .universal import UniversalScraper


class MagaluScraper(UniversalScraper):
    ADAPTER = "MAGALU"
    exigir_imagem = True
    espera_css = 'h1[data-testid="heading"]'

    def extrair_html(self, html, url):
        """Usa apenas dados da pagina real, nunca o titulo de bloqueio Akamai."""
        titulo, descricao, specs, imagem, fonte = super().extrair_html(html, url)
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.select_one('h1[data-testid="heading"]')
        if h1:
            titulo = self.limpar_texto(h1.get_text(" ", strip=True))
        bloco = soup.select_one('[data-testid="product-description"]')
        if bloco:
            descricao = self.limpar_descricao(str(bloco))
        for tabela in soup.find_all("table"):
            for linha in tabela.find_all("tr"):
                colunas = linha.find_all(["th", "td"], recursive=False)
                if len(colunas) == 2:
                    self.adicionar_spec(specs, colunas[0].get_text(" ", strip=True),
                                       colunas[1].get_text(" ", strip=True))
        for dt in soup.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                self.adicionar_spec(specs, dt.get_text(" ", strip=True), dd.get_text(" ", strip=True))
        return titulo, descricao, specs, imagem, fonte
