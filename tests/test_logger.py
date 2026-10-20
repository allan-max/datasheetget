import os
import tempfile
import unittest
from unittest.mock import patch

from scrapers.base import BaseScraper
import utils.logger as ds_logger


class DummyKabumScraper(BaseScraper):
    def executar(self):
        dados = {
            "titulo": "Monitor Gamer 27 Polegadas",
            "descricao": "Descrição indisponível.",
            "caracteristicas": {},
            "caminho_imagem_temp": None,
        }
        arquivos = self.gerar_arquivos_finais(dados)
        return {"sucesso": True, "arquivos": arquivos}


class LoggerTest(unittest.TestCase):
    def test_reporta_modulo_e_problemas_sem_imagem_e_sem_descricao(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_temp = os.path.join(tmpdir, "datasheet.txt")
            with patch.object(ds_logger, "LOG_DIR_SERVIDOR", tmpdir), patch.object(
                ds_logger, "LOG_PATH_SERVIDOR", log_temp
            ):
                ds_logger.registrar_modulo_ligado(
                    "KABUM", "kabum", "KabumScraper", "https://www.kabum.com.br/produto/123"
                )
                scraper = DummyKabumScraper("https://www.kabum.com.br/produto/123")
                scraper.site_nome = "KABUM"
                scraper.modulo_nome = "kabum"
                scraper.output_folder = tmpdir
                resultado = scraper.executar()

                self.assertTrue(resultado["sucesso"])
                self.assertTrue(os.path.exists(log_temp))
                with open(log_temp, "r", encoding="utf-8") as f:
                    conteudo = f.read()

                self.assertIn("[MODULO LIGADO]", conteudo)
                self.assertIn("KABUM (scrapers.kabum.KabumScraper)", conteudo)
                self.assertIn("Item veio SEM IMAGEM", conteudo)
                self.assertIn("Item veio SEM DESCRIÇÃO", conteudo)
                self.assertIn("Item veio SEM FICHA TÉCNICA", conteudo)
                self.assertIn("Módulo que apresentou problema: KABUM", conteudo)


if __name__ == "__main__":
    unittest.main()
