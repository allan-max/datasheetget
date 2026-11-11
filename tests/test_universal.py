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

    def test_ficha_em_negrito_com_br_sem_barra(self):
        # html.parser aninha o resto dentro de <br> sem barra; nada pode se perder.
        html = ("<html><body><h1>Ar condicionado 12000</h1><div class='product-detail-right__technical-information'>"
                "<b>Ciclo: </b> Frio<br><br> <b>Cor: </b> Branco<br><br>"
                "<b>Tecnologia: </b>Inverter<br/><br/><b>Voltagem (V): </b>220V<br/></div></body></html>")
        _, _, specs, _, _ = self.scraper.extrair_html(html, self.scraper.url)
        self.assertEqual(specs["Ciclo"], "Frio")
        self.assertEqual(specs["Voltagem (V)"], "220V")

    def test_specs_dentro_da_descricao(self):
        html = ("<html><body><h1>Alcool isopropilico 1L</h1><div id='tab-description'>"
                "<p>CARACTERÍSTICAS<br>– MARCA: BETZ<br>– MODELO: Garrafa<br>– Conteúdo: 1L<br>"
                "– Usado para limpeza de placas eletronicas</p></div></body></html>")
        _, desc, specs, _, _ = self.scraper.extrair_html(html, self.scraper.url)
        self.assertEqual(specs["Marca"], "BETZ")
        self.assertEqual(specs["Conteúdo"], "1L")
        self.assertIn("MARCA: BETZ", desc)

    def test_ficha_por_titulo_com_linhas_sem_classe(self):
        html = ("<html><body><h1>Geladeira 375L</h1><section><p>Ficha Técnica</p><div>"
                "<div><p>Marca</p><p>LG</p></div><div><p>Capacidade em litros</p><p>375 litros</p></div>"
                "<div><p>Altura</p><p>172 cm</p></div></div></section></body></html>")
        _, _, specs, _, _ = self.scraper.extrair_html(html, self.scraper.url)
        self.assertEqual(specs["Capacidade em litros"], "375 litros")
        self.assertEqual(specs["Altura"], "172 cm")

    def test_vtex_io_data_specification(self):
        html = ("<html><body><h1>Grill eletrico</h1><div>"
                "<span data-specification-name='Peso (kg)' data-specification-value='4,04kg'>4,04kg</span>"
                "</div></body></html>")
        _, _, specs, _, _ = self.scraper.extrair_html(html, self.scraper.url)
        self.assertEqual(specs["Peso (kg)"], "4,04kg")

    def test_lixo_comercial_por_palavra_inteira(self):
        self.assertFalse(self.scraper.tem_lixo("Saco de lixo 200L reforcado"))
        self.assertFalse(self.scraper.tem_lixo("Trocador de calor em cobre"))
        self.assertTrue(self.scraper.tem_lixo("Fale com o SAC"))
        self.assertTrue(self.scraper.tem_lixo("Frete gratis para todo o Brasil"))
        desc = self.scraper.limpar_descricao("<p>Saco de lixo azul reforcado para uso industrial. Frete gratis.</p>")
        self.assertIn("Saco de lixo azul", desc)
        self.assertNotIn("Frete", desc)

    def test_specs_lixo_descartadas(self):
        specs = {}
        for k, v in (("Unit price (excl. VAT)", "49.20 EUR"), ("Seg - Sex", "8:00 - 18:00"), ("1.", "nota"),
                     ("Sku 123", "Em estoque"), ("Marca", "Marca: DJI"), ("Propriedade", "Especificação"),
                     ("Sale Price", "R$ 0,00"), ("Material", "Aço inox.")):
            self.scraper.adicionar_spec(specs, k, v)
        self.assertEqual(specs, {"Marca": "DJI", "Material": "Aço inox"})

    def test_titulo_limpo(self):
        def titulo(html):
            return self.scraper.extrair_html(html, "https://www.edcabos.com/produto")[0]
        self.assertEqual(titulo("<html><head><title>23200005 Cabo CAT5E Furukawa | ED Cabos</title></head>"
                                "<body><h1>23200005 | Cabo CAT5E Furukawa</h1></body></html>"),
                         "23200005 Cabo CAT5E Furukawa")
        self.assertEqual(titulo("<html><body><h1>Comprar Clivador Tawaa FC-33</h1></body></html>"),
                         "Clivador Tawaa FC-33")
        self.assertEqual(titulo("<html><body><h1>Lousa Digital - de R$12.174,72 a R$27.065,97</h1></body></html>"),
                         "Lousa Digital")
        # Sem h1: usa o <title> sem o nome da loja.
        self.assertEqual(titulo("<html><head><title>Luva 3000 lbs solda | Produtos | Edcabos</title></head>"
                                "<body><p>x</p></body></html>"), "Luva 3000 lbs solda Produtos")

    def test_paginas_de_desafio_sao_bloqueio(self):
        self.assertTrue(self.scraper.bloqueada("<html><title>Acesso Bloqueado</title><h1>Ops :(</h1></html>"))
        self.assertTrue(self.scraper.bloqueada("<html><title>Verificação de Segurança</title>"
                                               "<script src='/challenge.js'></script></html>"))
        self.assertTrue(self.scraper.bloqueada("<title>Verifying your browser. Please wait</title>"))

    def test_encoding_sem_charset_no_cabecalho(self):
        class Resposta:
            headers = {"Content-Type": "text/html"}
            content = "<html><head><meta charset='utf-8'></head><title>Aço</title></html>".encode("utf-8")
            encoding = "ISO-8859-1"
            apparent_encoding = "utf-8"
        r = Resposta()
        self.scraper.corrigir_encoding(r)
        self.assertEqual(r.encoding.lower(), "utf-8")

    def test_vtex_slug_aninhado_e_skuid(self):
        chamadas = []

        class Resposta:
            def json(self):
                return [{"productName": "Grill", "description": "", "allSpecifications": [], "items": []}]

        def pedir(url, session=None):
            chamadas.append(url)
            return Resposta()
        with patch.object(self.scraper, "pedir", side_effect=pedir):
            self.scraper.produto_vtex("https://www.loja.com.br/eletro/grill-oster-721817/p?idsku=1538647", None)
        self.assertTrue(chamadas[0].endswith("/api/catalog_system/pub/products/search/grill-oster-721817/p"))

    def test_og_title_com_nome_da_loja_e_ignorado(self):
        html = ("<html><head><title>Jogo de chave allen longa 14 pecas</title>"
                "<meta property='og:title' content='Ferramentas Gedore'>"
                "<meta property='og:site_name' content='Ferramentas Gedore'></head><body><p>x</p></body></html>")
        self.assertEqual(self.scraper.extrair_html(html, self.scraper.url)[0], "Jogo de chave allen longa 14 pecas")

    def test_versoes_grandes_da_foto(self):
        v = self.scraper.versoes_grandes
        self.assertEqual(v("https://cdn.x.com/media/catalog/product/cache/a32edb92ec28608aa0d56d3d7df2922f/b/3/foto.jpg")[0],
                         "https://cdn.x.com/media/catalog/product/b/3/foto.jpg")
        self.assertEqual(v("https://x.com/wp-content/uploads/2025/07/foto-150x150.jpg")[0],
                         "https://x.com/wp-content/uploads/2025/07/foto.jpg")
        self.assertEqual(v("https://x.com/p/F.jpg?optimize=high&width=265&height=265&v=2")[0], "https://x.com/p/F.jpg?v=2")
        self.assertEqual(v("https://x.com/arquivos/ids/155392-500-500/grill.jpg")[0],
                         "https://x.com/arquivos/ids/155392-1000-1000/grill.jpg")
        self.assertEqual(v("https://x.com/a/foto.jpg"), ["https://x.com/a/foto.jpg"])

    def test_ranking_de_imagens(self):
        html = ("<html><head><meta property='og:image' content='https://example.com/images/og-default.png'></head><body>"
                "<header><img src='/topo/marca.jpg' alt='Loja'></header>"
                "<h1>Furadeira de impacto Bosch 700W</h1>"
                "<div class='related'><img src='/p/outro.jpg' alt='Furadeira de impacto Makita'></div>"
                "<img src='/p/aplicacao.jpg' alt='uso'>"
                "<div class='product-gallery'><img src='/p/furadeira.jpg' alt='Furadeira de impacto Bosch 700W'></div>"
                "<img src='/img/visa.png'></body></html>")
        self.scraper._candidatos_imagem = []
        img = self.scraper.extrair_html(html, self.scraper.url)[3]
        self.assertEqual(img, "https://example.com/p/furadeira.jpg")
        candidatos = self.scraper._candidatos_imagem
        self.assertNotIn("https://example.com/images/og-default.png", candidatos)
        self.assertNotIn("https://example.com/img/visa.png", candidatos)
        self.assertLess(candidatos.index("https://example.com/p/aplicacao.jpg"),
                        candidatos.index("https://example.com/topo/marca.jpg"))

    def test_mesma_foto_da_og_em_tamanho_maior_ganha(self):
        html = ("<html><head><meta property='og:image' content='https://example.com/produto/m/notebook_275594.jpg'>"
                "</head><body><h1>Notebook</h1><img src='/banner/promo.jpg'><img src='/foto/aplicacao.jpg'>"
                "<img src='https://example.com/produto/g/notebook_275594.jpg'></body></html>")
        self.scraper._candidatos_imagem = []
        self.assertEqual(self.scraper.extrair_html(html, self.scraper.url)[3],
                         "https://example.com/produto/g/notebook_275594.jpg")

    def test_imagem_pequena_tenta_a_proxima_e_aceita_reserva(self):
        from PIL import Image
        tamanhos = {"https://example.com/a.jpg": (150, 150), "https://example.com/b.jpg": (740, 101),
                    "https://example.com/c.jpg": (288, 200), "https://example.com/d.jpg": (800, 800)}

        def abrir(endereco, session):
            if endereco not in tamanhos:
                raise ValueError("404")
            return Image.new("RGBA", tamanhos[endereco], "red")
        with tempfile.TemporaryDirectory() as pasta:
            self.scraper.output_folder = pasta
            with patch.object(self.scraper, "abrir_imagem", side_effect=abrir):
                boa = self.scraper.baixar_imagem("https://example.com/a.jpg", None,
                                                 ["https://example.com/b.jpg", "https://example.com/c.jpg",
                                                  "https://example.com/d.jpg"])
                self.assertEqual(Image.open(boa).size, (800, 800))
                reserva = self.scraper.baixar_imagem("https://example.com/a.jpg", None,
                                                     ["https://example.com/b.jpg", "https://example.com/c.jpg"])
                self.assertEqual(Image.open(reserva).size, (288, 200))

    def test_vtex_io_state_no_html(self):
        estado = {
            "Product:grill-oster-721817": {
                "productName": "Grill Oster", "linkText": "grill-oster-721817", "brand": "OSTER",
                "description": "Grill eletrico multiuso com chapas antiaderentes e coletor de gordura.",
                "productReference": "7898742841370",
                "specificationGroups": [{"type": "id", "id": "Product:grill-oster-721817.specificationGroups.0"},
                                        {"type": "id", "id": "Product:grill-oster-721817.specificationGroups.1"}],
                "items": [{"type": "id", "id": "Product:grill-oster-721817.items.0"}]},
            "Product:grill-oster-721817.specificationGroups.0": {
                "name": "Informações Técnicas",
                "specifications": [{"type": "id", "id": "Product:grill-oster-721817.specificationGroups.0.specifications.0"}]},
            "Product:grill-oster-721817.specificationGroups.0.specifications.0": {
                "name": "Peso (kg)", "values": {"type": "json", "json": ["4,04kg"]}},
            "Product:grill-oster-721817.specificationGroups.1": {"name": "allSpecifications", "specifications": []},
            "Product:grill-oster-721817.items.0": {
                "ean": "7898742841370", "images": [{"type": "id", "id": "Product:grill-oster-721817.items.0.images.0"}]},
            "Product:grill-oster-721817.items.0.images.0": {"imageUrl": "https://x.vtexassets.com/arquivos/ids/1/g.jpg"},
        }
        import json
        html = ('<html><body><template data-type="json" data-varname="__STATE__"><script>%s</script></template>'
                '</body></html>' % json.dumps(estado))
        titulo, desc, specs, img, fonte = self.scraper.produto_vtex_io(
            html, "https://www.loja.com.br/eletro/grill-oster-721817/p?idsku=1")
        self.assertEqual(titulo, "Grill Oster")
        self.assertEqual(specs["Peso (kg)"], "4,04kg")
        self.assertEqual(specs["Marca"], "OSTER")
        self.assertEqual(specs["EAN"], "7898742841370")
        self.assertIn("coletor de gordura", desc)
        self.assertEqual(img, "https://x.vtexassets.com/arquivos/ids/1/g.jpg")
        self.assertEqual(fonte, "vtex-state")

    def test_conteudo_depois_do_h1_sem_classes(self):
        html = ("<html><body><div class='topo'><p>Ha mais de 30 anos oferecendo solucoes em iluminacao.</p></div>"
                "<div><h1>Luminaria de emergencia BLL IP66</h1>"
                "<p>Unidade autonoma de sobrepor para aclaramento de galpoes industriais.</p>"
                "<p>Funciona na falta ou queda parcial de energia com comutacao automatica.</p>"
                "<p>Tensao: 110 ou 220V</p><p>Bateria: 12V selada</p><p>Frequencia: 50/60Hz</p>"
                "<p>Luminaria de emergencia BLL IP66 versao 1200</p>"
                "<h3>Produtos relacionados</h3><p>Luminaria industrial de alto fluxo para galpoes grandes.</p>"
                "<p>Telefone (11) 3966-6211 de seg a sex</p></div></body></html>")
        _, desc, specs, _, _ = self.scraper.extrair_html(html, self.scraper.url)
        self.assertEqual(specs["Tensao"], "110 ou 220V")
        self.assertEqual(specs["Frequencia"], "50/60Hz")
        self.assertIn("Funciona na falta", desc)
        self.assertNotIn("30 anos", desc)
        self.assertNotIn("alto fluxo", desc)
        self.assertNotIn("versao 1200", desc)

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
