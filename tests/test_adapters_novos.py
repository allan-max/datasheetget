import json
import unittest

from config import identificar_site, site_bloqueado
from scrapers.compragolden import CompraGoldenScraper
from scrapers.eaton import EatonScraper
from scrapers.magalu import MagaluScraper
from scrapers.marchesoni import MarchesoniScraper
from scrapers.projetelas import ProjetelasScraper
from scrapers.terabyteshop import TerabyteShopScraper
from scrapers.weg import WegScraper


class AdaptersNovosTest(unittest.TestCase):
    def test_roteamento(self):
        for dominio, modulo in (
            ("weg.net", "weg"), ("magazineluiza.com.br", "magalu"),
            ("marchesoni.com.br", "marchesoni"), ("eaton.com", "eaton"),
            ("projetelas.com.br", "projetelas"),
            ("terabyteshop.com.br", "terabyteshop"),
            ("compregolden.com.br", "compragolden"),
            ("belmicro.com.br", "belmicro"),
        ):
            url = "https://www." + dominio + "/produto"
            self.assertEqual(identificar_site(url)[1], modulo)
            self.assertIsNone(site_bloqueado(url))

    def test_weg(self):
        html = '<h1 class="product-card-title">Motor WEG</h1><div class="xtt-product-description">Motor monofasico de uso geral com alto desempenho.</div><a class="xtt-product-image-zoom" href="https://static.weg.net/foto.jpg"></a><table class="table"><tr><th>Potencia</th><td>0.5 cv</td></tr></table>'
        t, d, s, i, _ = WegScraper("https://www.weg.net/p/1").extrair_html(html, "")
        self.assertEqual((t, s["Potencia"], i), ("Motor WEG", "0.5 cv", "https://static.weg.net/foto.jpg"))
        self.assertIn("Motor", d)

    def test_magalu_bloqueio(self):
        scraper = MagaluScraper("https://www.magazineluiza.com.br/p/1")
        self.assertTrue(scraper.bloqueada('<div id="sec-if-cpt-container"></div>', 200))

    def test_terabyteshop(self):
        html = '<h1>SSD Kingston NV3</h1><script type="application/ld+json">{"@type":"Product","description":"SSD NV3 para computadores com interface PCIe 4.0 e capacidade de 1TB. Aproveite na Terabyte!","image":"https://img.terabyteshop.com.br/produto/g/ssd.jpg"}</script><div class="especificacoes"><div class="tecnicas"><p>Modelo: NV3</p><p>Capacidade: 1TB</p></div></div>'
        t, d, s, i, _ = TerabyteShopScraper("https://www.terabyteshop.com.br/produto/1").extrair_html(html, "")
        self.assertEqual((t, s["Modelo"], s["Capacidade"]), ("SSD Kingston NV3", "NV3", "1TB"))
        self.assertIn("ssd.jpg", i)
        self.assertNotIn("Aproveite", d)

    def test_eaton(self):
        html = '<h1>No-break 5E da Eaton</h1><div class="product-family-card__description">No-break de linha interativa.</div><img alt="No-break 5E" src="/foto.png"><div class="product-highlights__content"><div class="product-highlights__title">Potencia</div><div class="product-highlights__text">650 a 2200VA</div></div>'
        t, _, s, i, _ = EatonScraper("https://www.eaton.com/br/produto").extrair_html(html, "")
        self.assertEqual((t, s["Potencia"], i), ("No-break 5E da Eaton", "650 a 2200VA", "/foto.png"))

    def test_compra_golden_sem_rodape(self):
        produto = json.dumps({"@type": "Product", "name": "Cabo Golden", "description": "Cabo HDMI de alta velocidade para sistemas de video e audio digitais.", "image": "https://example.com/cabo.jpg", "sku": "08.111CG"})
        html = '<script type="application/ld+json">%s</script><ul><li>Versao HDMI: 2.1</li><li>Condutor: Cobre</li><li>Blindagem: Dupla</li></ul><section id="menuRodape"><ul><li>Horario: 8h</li><li>Telefone: 123</li><li>Endereco: Rua</li></ul></section>' % produto
        _, _, s, _, _ = CompraGoldenScraper("https://www.compregolden.com.br/cabo").extrair_html(html, "")
        self.assertEqual(s["Versao HDMI"], "2.1")
        self.assertNotIn("Horario", s)

    def test_marchesoni_familia(self):
        html = '<title>Estufa Ouro – Marchesoni</title><div><div><div><h3>Umidade controlada</h3></div><p>Umidificador integrado para conservar alimentos aquecidos.</p></div></div><img src="https://marchesoni.com.br/Estufa-Ouro-3-Bandejas.png">'
        t, _, s, i, _ = MarchesoniScraper("https://marchesoni.com.br/estufa-ouro/").extrair_html(html, "")
        self.assertEqual(t, "Estufa Ouro")
        self.assertIn("Umidade controlada", s)
        self.assertIn("3-Bandejas", i)

    def test_projetelas_api(self):
        scraper = ProjetelasScraper("https://projetelas.com.br/produto/classic-lx")
        produto = {"slug": "classic-lx", "name": "Classic LX", "full_description": "<p>Tela motorizada tensionada para ambientes residenciais e corporativos.</p>", "specs": {"Motor": "127 V", "Garantia": "1 ano"}, "image_url": "https://example.com/foto.jpg"}
        class Resposta:
            status_code = 200
            def json(self): return [produto]
        scraper.pedir = lambda url, session: Resposta()
        html = 'https://media.base44.com/images/public/69f2bb72709c74ed7d2f939d/foto.png'
        t, _, s, i, _ = scraper.extrair_api(html, scraper.url, None)
        self.assertEqual((t, s["Motor"], i), ("Classic LX", "127 V", "https://example.com/foto.jpg"))
        self.assertNotIn("Garantia", s)


if __name__ == "__main__":
    unittest.main()
