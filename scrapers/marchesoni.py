import re

from bs4 import BeautifulSoup

from .universal import UniversalScraper


class MarchesoniScraper(UniversalScraper):
    ADAPTER = "MARCHESONI"
    exigir_imagem = True

    def extrair_html(self, html, url):
        """A pagina da Estufa Ouro e de uma familia, com varios tamanhos."""
        soup = BeautifulSoup(html, "html.parser")
        titulo = self.limpar_texto(soup.title.get_text().split("–")[0]) if soup.title else ""
        specs = {}
        for cabecalho in soup.find_all("h3"):
            chave = self.limpar_texto(cabecalho.get_text(" ", strip=True))
            if chave not in ("Mais agilidade no atendimento", "Exposição atraente",
                             "Umidade controlada", "Variedade de capacidade", "Fácil limpeza"):
                continue
            bloco = cabecalho.parent.parent.parent
            valor = self.limpar_texto(bloco.get_text(" ", strip=True))
            if valor.startswith(chave):
                valor = valor[len(chave):].strip()
            self.adicionar_spec(specs, chave, valor)

        descricao = self.limpar_descricao("\n".join(specs.values()))
        imagem = ""
        for tag in soup.find_all("img"):
            candidato = tag.get("data-src") or tag.get("src") or ""
            if re.search(r"Estufa-Ouro-3-Bandejas", candidato, re.I):
                imagem = candidato
                break
        return titulo, descricao, specs, imagem, "html"
