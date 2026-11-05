import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from utils import issues

AGORA = datetime(2026, 11, 5, 10)


class Github:
    def __init__(self):
        self.chamadas = []

    def __call__(self, url, headers, timeout, json):
        self.chamadas.append((url, json))
        n = len(self.chamadas)

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"number": n, "html_url": "https://github.com/allan-max/datasheetget/issues/%s" % n}
        return R()


def ia(system, texto):
    ia.recebido = texto
    return json.dumps({"causa": "O site mudou o layout.", "conserto": "Atualizar o seletor do titulo."})


class IssuesTest(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.registro = os.path.join(self.pasta, "issues.json")
        self.gh = Github()

    def abrir(self, url, erro, site, **kw):
        return issues.registrar(url, erro, site, self.pasta, token="tok", post=self.gh, chamar=ia,
                                agora=AGORA, registro=self.registro, **kw)

    def test_bloqueio_404_e_url_recusada_nao_viram_issue(self):
        for erro in ("Universal: Pagina bloqueada ou desafio anti-bot (x.com)", "Universal: Pagina HTTP 404 (x.com)",
                     "Site bloqueado para datasheet: x.com", "URL recusada: sem caminho de produto"):
            self.assertIsNone(self.abrir("https://x.com/p", erro, None))
        self.assertEqual(self.gh.chamadas, [])

    def test_scraper_quebrado_abre_issue_com_ia_e_repeticao_comenta(self):
        url = self.abrir("https://www.kabum.com.br/produto/123", "Titulo nao encontrado no item 123", "KABUM")
        self.assertTrue(url.endswith("/issues/1"))
        enviado = self.gh.chamadas[0][1]
        self.assertEqual(enviado["labels"], ["robo-datasheet"])
        self.assertIn("KABUM: Titulo nao encontrado no item <n>", enviado["title"])
        self.assertIn("O site mudou o layout.", enviado["body"])
        self.assertIn("https://www.kabum.com.br/produto/123", enviado["body"])
        self.abrir("https://www.kabum.com.br/produto/456", "Titulo nao encontrado no item 456", "KABUM")
        self.abrir("https://www.kabum.com.br/produto/456", "Titulo nao encontrado no item 456", "KABUM")  # mesmo link
        self.assertEqual([u.rsplit("/", 1)[-1] for u, _ in self.gh.chamadas], ["issues", "comments"])

    def test_site_sem_scraper_vira_site_novo_e_ia_le_a_pagina_guardada(self):
        with open(os.path.join(self.pasta, "universal_falha_loja.com.br_1.html"), "w", encoding="utf-8") as f:
            f.write("<html><script>x()</script><h1>Furadeira 500W</h1><p>Potencia: 500W</p></html>")
        self.abrir("https://www.loja.com.br/furadeira", "Universal: Descricao curta e menos de 3 especificacoes (loja.com.br)", None)
        enviado = self.gh.chamadas[0][1]
        self.assertEqual(enviado["labels"], ["datasheet-site-novo"])
        self.assertIn("site novo: loja.com.br", enviado["title"])
        self.assertIn("Furadeira 500W", ia.recebido)
        self.assertNotIn("x()", ia.recebido)

    def test_sem_ia_a_issue_sai_assim_mesmo(self):
        def quebrada(system, texto):
            raise RuntimeError("sem credito")
        issues.registrar("https://a.com/p", "KeyError: 'preco'", "DELL", self.pasta, token="tok", post=self.gh,
                         chamar=quebrada, agora=AGORA, registro=self.registro)
        self.assertIn("(sem explicacao da IA)", self.gh.chamadas[0][1]["body"])

    def test_limite_de_issues_novas_por_dia(self):
        urls = [self.abrir("https://a.com/%s" % i, "erro tipo %s" % chr(97 + i), "DELL") for i in range(7)]
        self.assertEqual(urls[5:], [None, None])
        self.assertEqual(len(self.gh.chamadas), 5)

    def test_onde_aponta_o_nosso_codigo(self):
        try:
            issues.classificar(None, None, "X").nao_existe
        except AttributeError as e:
            self.assertTrue(issues.onde(e).startswith("tests/test_issues.py:"))

    def test_sem_token_nao_faz_nada(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN_ISSUES": ""}), patch.object(issues, "registrar") as reg:
            issues.em_fundo("https://a.com/p", "erro", "DELL")
        reg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
