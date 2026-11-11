import re

from bs4 import BeautifulSoup

from .universal import UniversalScraper


class TerabyteShopScraper(UniversalScraper):
    ADAPTER = "TERABYTESHOP"
    exigir_imagem = True
    espera_css = "h1"
    imagem_css = 'img[src*="img.terabyteshop.com.br/produto/g/"]'

    def baixar_imagem(self, url, session):
        caminho = super().baixar_imagem(url, session)
        if not caminho:
            # O HTML pode abrir por requests, mas o CDN da foto devolver desafio.
            self.navegar(self.url)
            caminho = getattr(self, "_foto_navegador", None)
        return caminho

    def extrair_html(self, html, url):
        soup = BeautifulSoup(html, "html.parser")
        produto = self.produto_jsonld(soup)
        h1 = soup.find("h1")
        titulo = self.limpar_texto(h1.get_text(" ", strip=True)) if h1 else ""
        descricao = self.limpar_descricao(produto.get("description"))
        # limpar_descricao junta as frases do paragrafo; o convite da loja sai por frase.
        descricao = "\n".join(" ".join(f for f in re.split(r"(?<=[.!?])\s+", linha)
                                       if not f.lower().startswith(("aproveite", "compre", "garanta")))
                              for linha in descricao.splitlines())
        descricao = "\n".join(l for l in descricao.splitlines() if l.strip())
        imagem = produto.get("image") or ""
        if isinstance(imagem, list):
            imagem = imagem[0] if imagem else ""

        specs = {}
        for bloco in soup.select(".especificacoes .tecnicas"):
            for linha in bloco.find_all("p"):
                texto = self.limpar_texto(linha.get_text(" ", strip=True))
                if ":" in texto:
                    chave, valor = texto.split(":", 1)
                    self.adicionar_spec(specs, chave, valor)
        return titulo, descricao, specs, imagem, "html"
