from bs4 import BeautifulSoup

from .universal import UniversalScraper


class GedoreScraper(UniversalScraper):
    ADAPTER = "GEDORE"
    exigir_imagem = True

    def extrair_html(self, html, url):
        """Catálogo Gedore: sem JSON-LD nem h1; tudo vem no HTML estático."""
        soup = BeautifulSoup(html or "", "html.parser")
        titulo = soup.select_one("#banner .group-title .title")
        titulo = self.limpar_texto(titulo.get_text(" ", strip=True)) if titulo else ""

        # Descrição: subtítulo + texto ao lado da foto (dicas de uso/segurança)
        partes = [str(b) for b in soup.select("#banner .subtitle, #main-info .right-box .text")]
        descricao = self.limpar_descricao("\n".join(partes))

        specs = {}
        codigo = soup.select_one("#banner .group-title .code")
        if codigo:
            self.adicionar_spec(specs, "Código", codigo.get_text(" ", strip=True).split()[-1])

        # Tabela de informações: a linha "highlighted" é o produto da página
        tabela = soup.select_one("#other-info li.info table")
        if tabela:
            nomes = [th.get_text(" ", strip=True) for th in tabela.select("thead th")]
            linha = tabela.select_one("tbody tr.highlighted") or tabela.select_one("tbody tr")
            if linha:
                for nome, td in zip(nomes, linha.find_all("td")):
                    if nome and nome != "*":  # colunas só com ícone não têm rótulo
                        self.adicionar_spec(specs, nome, td.get_text(" ", strip=True))

        # Composição do jogo: "Composição - <referência>" = "<qtd> x <peça>"
        for linha in soup.select("#other-info li.composition table tbody tr"):
            celulas = [td.get_text(" ", strip=True) for td in linha.find_all("td")]
            if len(celulas) >= 5 and celulas[1]:
                self.adicionar_spec(specs, "Composição - " + celulas[1], "%s x %s" % (celulas[4], celulas[3]))

        foto = soup.select_one("#main-info .left-box a.fancybox")
        imagem = (foto.get("href") or foto.get("data-src") or "") if foto else ""
        return titulo, descricao, specs, imagem, "html"
