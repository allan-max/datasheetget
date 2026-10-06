import os
import tempfile
import unittest
from unittest.mock import patch

from scrapers.universal import UniversalScraper
import config
import scraper_manager
import run


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(nome):
    with open(os.path.join(FIXTURES, nome), encoding="utf-8") as f:
        return f.read()


class UniversalTest(unittest.TestCase):
    def setUp(self):
        self.scraper = UniversalScraper("https://example.com/produto")

    def test_jsonld_graph_e_limpeza(self):
        titulo, desc, specs, img, fonte = self.scraper.extrair_html(
            fixture("product_jsonld.html"), self.scraper.url)
        self.assertEqual(fonte, "json-ld")
        self.assertEqual(titulo, "Câmera Série Pro")
        self.assertEqual(specs["Sensor"], "24 MP")
        self.assertNotIn("MENU LIXO", desc)
        self.assertNotIn("RODAPE LIXO", desc)
        self.assertNotIn("cookies", desc)
        self.assertEqual(img, "https://example.com/foto.jpg")

    def test_tabela_dl_lista(self):
        _, _, specs, _, _ = self.scraper.extrair_html(fixture("product_specs.html"), self.scraper.url)
        self.assertEqual(specs["Resolução"], "Full HD")
        self.assertEqual(specs["Tamanho"], "24 polegadas")
        self.assertTrue(any("HDMI e DP" == v for v in specs.values()))

    def test_ficha_dentro_do_formulario(self):
        html = fixture("product_specs.html").replace("<body>", "<body><form>").replace(
            "</body>", "</form></body>")
        _, _, specs, _, _ = self.scraper.extrair_html(html, self.scraper.url)
        self.assertEqual(specs["Resolução"], "Full HD")

    def test_vtex_descricao_tecnica_multilinha(self):
        class Resposta:
            def json(self):
                return [{"productName": "Conservador comercial", "description": "Produto de uso profissional com refrigeração constante e gabinete resistente para conservação de congelados.",
                         "allSpecifications": ["Descrição Técnica", "Tipo de Porta"],
                         "Descrição Técnica": ["Temperatura: -16 a -20 C\nMedidas:\nFrente(mm): 1400\nCapacidade bruta(litros): 1421"],
                         "Tipo de Porta": ["Porta cega"], "items": []}]
        with patch.object(self.scraper, "pedir", return_value=Resposta()):
            dados = self.scraper.extrair_api("<html>vtex</html>", "https://example.com/conservador/p", None)
        self.assertEqual(dados[2]["Temperatura"], "-16 a -20 C")
        self.assertEqual(dados[2]["Medidas - Capacidade bruta(litros)"], "1421")
        self.assertEqual(dados[2]["Tipo de Porta"], "Porta cega")

    def test_bloqueio_falha_clara_e_salva_html(self):
        class Resposta:
            text = fixture("blocked.html")
            url = "https://example.com/produto"
            status_code = 403
        with tempfile.TemporaryDirectory() as pasta:
            self.scraper.output_folder = pasta
            with patch.object(self.scraper, "pedir", return_value=Resposta()), patch.object(
                    self.scraper, "navegar", side_effect=RuntimeError("Chrome nao disponivel")):
                resultado = self.scraper.executar()
            self.assertFalse(resultado["sucesso"])
            self.assertIn("bloqueada", resultado["erro"])
            self.assertTrue(any(x.endswith(".html") for x in os.listdir(pasta)))

    def test_script_de_captcha_na_pagina_de_produto_nao_e_bloqueio(self):
        html = ("<html><body><h1>Monitor de 24 polegadas</h1>"
                "<p>Monitor para escritorio com entradas HDMI e DisplayPort,"
                " painel IPS e resolucao Full HD.</p>"
                "<script src='/recaptcha/api.js'></script></body></html>")
        self.assertFalse(self.scraper.bloqueada(html))
        self.assertTrue(self.scraper.bloqueada("<html><title>Just a moment</title></html>"))

    def test_404_falha_sem_abrir_chrome(self):
        class Resposta:
            text = "<html><h1>Pagina nao encontrada</h1></html>"
            url = "https://example.com/produto"
            status_code = 404
        with tempfile.TemporaryDirectory() as pasta:
            self.scraper.output_folder = pasta
            with patch.object(self.scraper, "pedir", return_value=Resposta()), patch.object(
                    self.scraper, "navegar") as navegar:
                resultado = self.scraper.executar()
            self.assertFalse(resultado["sucesso"])
            self.assertIn("404", resultado["erro"])
            navegar.assert_not_called()

    def test_url_privada(self):
        for url in ("http://127.0.0.1/", "http://10.0.0.1/", "http://192.168.0.1/",
                    "http://[::1]/", "file:///etc/passwd"):
            with self.assertRaises(ValueError):
                self.scraper.validar_url(url)

    def test_redirect_para_ip_privado(self):
        class Resposta:
            is_redirect = True
            headers = {"Location": "http://127.0.0.1/admin"}
        session = unittest.mock.Mock()
        session.get.return_value = Resposta()
        with patch.object(self.scraper, "validar_url", wraps=self.scraper.validar_url):
            with self.assertRaises(ValueError):
                self.scraper.pedir("https://example.com/produto", session)
        self.assertEqual(session.get.call_count, 1)

    def test_normalizacao_pdf(self):
        self.assertEqual(self.scraper.normalizar("“Olá”—™ 😀"), '"Olá"-TM ')

    def test_integracao_dos_dois_managers_e_interruptor(self):
        url = "https://site-sem-adapter.example/produto"
        esperado = {"sucesso": True, "adapter": "UNIVERSAL"}
        with patch.object(UniversalScraper, "executar", return_value=esperado):
            self.assertEqual(scraper_manager.ScraperManager().executar_scraping(url, "output"), esperado)
            self.assertEqual(run.ScraperManager().executar_scraping(url, "output"), esperado)
        with patch.object(config, "UNIVERSAL_ATIVO", False):
            self.assertFalse(scraper_manager.ScraperManager().executar_scraping(url, "output")["sucesso"])
            self.assertFalse(run.ScraperManager().executar_scraping(url, "output")["sucesso"])
        self.assertEqual(config.identificar_site("https://www.dell.com/produto")[0], "DELL")

    def test_sites_com_adapter_sao_habilitados_nos_dois_managers(self):
        from importlib import import_module
        urls = ("https://www.weg.net/catalog/produto",
                "https://www.magazineluiza.com.br/produto",
                "https://marchesoni.com.br/estufa-ouro/",
                "https://www.eaton.com/br/produto",
                "https://projetelas.com.br/produto/classic-lx",
                "https://www.terabyteshop.com.br/produto/123")
        with tempfile.TemporaryDirectory() as pasta:
            for url in urls:
                site, modulo, nome_classe = config.identificar_site(url)
                self.assertIsNotNone(site)
                self.assertIsNone(config.site_bloqueado(url))
                classe = getattr(import_module("scrapers." + modulo), nome_classe)
                esperado = {"sucesso": True, "adapter": site}
                with patch.object(classe, "executar", return_value=esperado):
                    for manager in (scraper_manager.ScraperManager(), run.ScraperManager()):
                        self.assertEqual(manager.executar_scraping(url, pasta), esperado)
            self.assertEqual(os.listdir(pasta), [])
        self.assertIsNone(config.site_bloqueado("https://www.magaluempresas.com.br/produto"))
        self.assertIsNone(config.site_bloqueado("https://weg.net.evil.example/produto"))


if __name__ == "__main__":
    unittest.main()
