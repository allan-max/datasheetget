import importlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import config
import run
import scraper_manager
from scrapers.base import BaseScraper
from utils import seguranca


def carregar_api():
    # api.py cria a pasta de rede na importação; aqui ela não deve ser criada
    with patch("os.makedirs"):
        return importlib.import_module("api")


class RoteamentoPorDominioTest(unittest.TestCase):
    def test_dominio_no_caminho_nao_escolhe_adapter(self):
        for url in ("https://loja-qualquer.example/produto?ref=kabum.com.br",
                    "https://example.com/www.dell.com/p",
                    "https://modell.com/produto"):
            self.assertEqual(config.identificar_site(url), (None, None, None), url)
            self.assertEqual(run.identificar_site(url), (None, None, None), url)

    def test_subdominio_e_url_sem_esquema(self):
        self.assertEqual(config.identificar_site("https://produto.mercadolivre.com.br/MLB-1")[1], "mercado_livre")
        self.assertEqual(config.identificar_site("www.kabum.com.br/produto/1")[1], "kabum")
        self.assertEqual(config.identificar_site("https://WWW.AMAZON.COM.BR/dp/1")[1], "amazon")
        self.assertEqual(run.identificar_site("https://www.dell.com/pt-br/p")[0], "DELL")

    def test_magalu_empresas_nao_cai_no_magalu(self):
        self.assertEqual(config.identificar_site("https://www.magaluempresas.com.br/p/1")[1], "magalu_empresas")


class UrlInternaTest(unittest.TestCase):
    def test_validar_url_produto(self):
        for url in ("http://127.0.0.1:3000/?x=kabum.com.br", "http://192.168.1.3/kabum.com.br",
                    "http://localhost/", "file:///C:/Windows/win.ini", "http://[::1]/",
                    "https://user:senha@www.kabum.com.br/", "www.kabum.com.br/produto"):
            with self.assertRaises(ValueError, msg=url):
                seguranca.validar_url_produto(url)
        self.assertEqual(seguranca.validar_url_produto("https://www.kabum.com.br/p"), "https://www.kabum.com.br/p")

    def test_managers_recusam_url_interna_sem_abrir_scraper(self):
        url = "http://127.0.0.1:3000/admin?ref=kabum.com.br"
        for manager in (scraper_manager.ScraperManager(), run.ScraperManager()):
            with patch("importlib.import_module") as importar:
                resultado = manager.executar_scraping(url, "output")
            self.assertFalse(resultado["sucesso"])
            importar.assert_not_called()


class WebhookETokenTest(unittest.TestCase):
    def test_webhook_permitido(self):
        self.assertTrue(seguranca.webhook_permitido("http://127.0.0.1:3000/api/datasheet/webhook"))
        self.assertFalse(seguranca.webhook_permitido("file:///etc/passwd"))
        self.assertFalse(seguranca.webhook_permitido("gopher://127.0.0.1:25/"))
        with patch.dict(os.environ, {seguranca.ENV_WEBHOOK_HOSTS: "127.0.0.1, localhost"}):
            self.assertTrue(seguranca.webhook_permitido("http://127.0.0.1:3000/x"))
            self.assertFalse(seguranca.webhook_permitido("http://10.0.0.5/x"))

    def test_token(self):
        with patch.dict(os.environ, {seguranca.ENV_TOKEN: ""}):
            self.assertTrue(seguranca.token_valido({}))
        with patch.dict(os.environ, {seguranca.ENV_TOKEN: "abc"}):
            self.assertFalse(seguranca.token_valido({}))
            self.assertFalse(seguranca.token_valido({"X-Api-Token": "errado"}))
            self.assertTrue(seguranca.token_valido({"X-Api-Token": "abc"}))
            self.assertTrue(seguranca.token_valido({"Authorization": "Bearer abc"}))


class RotaProcessarTest(unittest.TestCase):
    def setUp(self):
        self.api = carregar_api()

    def apps(self):
        return ((run, run.app.test_client()), (self.api, self.api.app.test_client()))

    def test_token_obrigatorio_quando_configurado(self):
        for modulo, cliente in self.apps():
            with patch.dict(os.environ, {seguranca.ENV_TOKEN: "abc"}), patch.object(modulo.threading, "Thread") as thread:
                r = cliente.post("/api/datasheet/processar", json={"url": "https://www.kabum.com.br/p"})
                self.assertEqual(r.status_code, 401, modulo.__name__)
                r = cliente.post("/api/datasheet/processar", json={"url": "https://www.kabum.com.br/p"},
                                 headers={"X-Api-Token": "abc"})
                self.assertEqual(r.status_code, 202, modulo.__name__)
                thread.assert_called_once()

    def test_json_estranho_nao_derruba_a_rota(self):
        for modulo, cliente in self.apps():
            with patch.object(modulo.threading, "Thread"):
                for corpo in ([1, 2], {"dados": None, "url": None}, {"urls": 5}, {"urls": [None]}):
                    r = cliente.post("/api/datasheet/processar", json=corpo)
                    self.assertEqual(r.status_code, 400, (modulo.__name__, corpo))

    def test_webhook_invalido_recusado(self):
        for modulo, cliente in self.apps():
            with patch.object(modulo.threading, "Thread") as thread:
                r = cliente.post("/api/datasheet/processar",
                                 json={"url": "https://www.kabum.com.br/p", "webhook_url": "file:///etc/passwd"})
                self.assertEqual(r.status_code, 400, modulo.__name__)
                thread.assert_not_called()

    def test_run_bloco_dados_sem_webhook_usa_padrao(self):
        with patch.object(run.threading, "Thread") as thread:
            r = run.app.test_client().post("/api/datasheet/processar",
                                           json={"codigoTarefa": "T1", "dados": {"url": "https://www.kabum.com.br/p"}})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(thread.call_args.kwargs["args"][2], run.URL_CALLBACK_PADRAO)


class ThreadDeProcessamentoTest(unittest.TestCase):
    def test_run_erro_leva_codigo_tarefa_e_excecao_avisa_webhook(self):
        with patch.object(run.scraper_manager, "executar_scraping", return_value={"sucesso": False, "erro": "x"}), \
                patch.object(run, "enviar_webhook") as wh:
            run.pedidos["a"] = {"status": "processando"}
            run.processar_pedido_background("a", "https://www.kabum.com.br/p", "http://127.0.0.1:3000/w", "API", "T1", None)
        self.assertEqual(wh.call_args.args[1]["codigoTarefa"], "T1")
        self.assertEqual(run.pedidos["a"]["status"], "erro")

        with patch.object(run.scraper_manager, "executar_scraping", side_effect=RuntimeError("quebrou")), \
                patch.object(run, "enviar_webhook") as wh:
            run.pedidos["b"] = {"status": "processando"}
            run.processar_pedido_background("b", "https://www.kabum.com.br/p", "http://127.0.0.1:3000/w", "API", "T2", None)
        self.assertEqual(run.pedidos["b"]["status"], "erro_critico")
        self.assertFalse(wh.call_args.args[1]["sucesso"])
        self.assertEqual(wh.call_args.args[1]["codigoTarefa"], "T2")

    def test_api_excecao_avisa_webhook(self):
        api = carregar_api()
        with patch.object(api.scraper_manager, "executar_scraping", side_effect=RuntimeError("quebrou")), \
                patch.object(api, "enviar_webhook") as wh:
            api.pedidos["c"] = {"status": "processando"}
            api.processar_pedido_background("c", "https://x.example/p", "http://127.0.0.1:3000/w", "API_NOVA", "T3")
        self.assertEqual(api.pedidos["c"]["status"], "erro_critico")
        self.assertEqual(wh.call_args.args[1], {"codigoTarefa": "T3", "status": "ERRO", "sucesso": False,
                                                 "erro": "Erro interno: quebrou"})

    def test_lista_de_pedidos_nao_cresce_sem_limite(self):
        with patch.object(run, "LIMITE_PEDIDOS_GUARDADOS", 3), patch.dict(run.pedidos, clear=True):
            run.guardar_pedido("ativo", {"status": "processando"})
            for i in range(5):
                run.guardar_pedido(str(i), {"status": "concluido"})
            self.assertEqual(len(run.pedidos), 3)
            self.assertIn("ativo", run.pedidos)
            self.assertIn("4", run.pedidos)


class ImagemTemporariaTest(unittest.TestCase):
    def test_pedidos_simultaneos_nao_dividem_a_mesma_imagem(self):
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), (255, 0, 0)).save(buf, "PNG")

        class Resposta:
            status_code = 200
            content = buf.getvalue()

        with tempfile.TemporaryDirectory() as pasta, patch("scrapers.base.requests.get", return_value=Resposta()):
            caminhos = []
            for _ in range(2):
                s = BaseScraper("https://www.kabum.com.br/p")
                s.output_folder = pasta
                caminhos.append(s.baixar_imagem_temp("https://img.example/foto.png"))
            self.assertNotEqual(caminhos[0], caminhos[1])
            self.assertTrue(all(os.path.exists(c) for c in caminhos))


if __name__ == "__main__":
    unittest.main()
