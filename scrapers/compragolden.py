from bs4 import BeautifulSoup

from .universal import UniversalScraper


class CompraGoldenScraper(UniversalScraper):
    ADAPTER = "COMPRA_GOLDEN"
    exigir_imagem = True

    def extrair_html(self, html, url):
        """A ficha deste site e uma lista; as tabelas mostram outros tamanhos."""
        soup = BeautifulSoup(html, "html.parser")
        produto = self.produto_jsonld(soup)
        titulo = self.limpar_texto(produto.get("name"))
        descricao = self.limpar_descricao(produto.get("description"))
        imagem = produto.get("image") or ""
        if isinstance(imagem, list):
            imagem = imagem[0] if imagem else ""

        specs = {}
        if produto.get("sku"):
            self.adicionar_spec(specs, "Modelo", produto["sku"])
        for lista in soup.find_all("ul"):
            if lista.find_parent(["footer", "nav"]) or lista.find_parent(id="menuRodape"):
                continue
            itens = lista.find_all("li", recursive=False)
            if len(itens) < 3:
                continue
            for item in itens:
                texto = self.limpar_texto(item.get_text(" ", strip=True))
                if ":" not in texto:
                    continue
                chave, valor = texto.split(":", 1)
                if len(chave) < 45 and len(valor) < 150:
                    self.adicionar_spec(specs, chave, valor)

        return titulo, descricao, specs, imagem, "json-ld"
