import json
import re
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup

from .universal import UniversalScraper


class ProjetelasScraper(UniversalScraper):
    ADAPTER = "PROJETELAS"
    exigir_imagem = True

    def extrair_api(self, html, url, session):
        """A loja Base44 entrega o produto por API; o HTML inicial e vazio."""
        slug = urlparse(url).path.rstrip("/").split("/")[-1]
        app = re.search(r"media\.base44\.com/images/public/([a-f0-9]{24})/", html)
        if not app or not slug or "/produto/" not in urlparse(url).path:
            return None
        api = "https://projetelas.com.br/api/apps/%s/entities/Product" % app.group(1)
        resposta = self.pedir(api + "?q=" + quote(json.dumps({"slug": slug}), safe=""), session)
        produtos = resposta.json() if resposta.status_code == 200 else []
        produto = next((p for p in produtos if p.get("slug") == slug), None)
        if not produto:
            return None
        descricao = BeautifulSoup(produto.get("full_description") or "", "html.parser").get_text("\n", strip=True)
        descricao = self.limpar_descricao(descricao or produto.get("short_description"))
        specs = {}
        for chave, valor in (produto.get("specs") or {}).items():
            if chave.lower() != "garantia":
                self.adicionar_spec(specs, chave, valor)
        return produto.get("name", ""), descricao, specs, produto.get("image_url", ""), "projetelas-api"
