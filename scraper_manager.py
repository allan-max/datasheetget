# scraper_manager.py
import importlib
import sys
import os
import time
import config
from config import identificar_site
from urllib.parse import urlparse
from utils.logger import (
    definir_contexto_execucao,
    identificar_modulo_scraper,
    registrar_log,
    registrar_modulo_ligado,
    registrar_erro_modulo,
)

# --- CORREÇÃO DE PATH ---
# Adiciona o diretório atual (onde está este arquivo) ao sys.path
# Isso garante que o Python encontre a pasta 'scrapers'
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
if diretorio_atual not in sys.path:
    sys.path.append(diretorio_atual)
# ------------------------

class ScraperManager:
    def __init__(self):
        self.scrapers_carregados = {}
    
    def carregar_scraper(self, modulo_nome, classe_nome):
        # Carregamento dinâmico
        chave = f"{modulo_nome}.{classe_nome}"
        if chave in self.scrapers_carregados:
            return self.scrapers_carregados[chave]
        
        try:
            # Tenta importar como "scrapers.modulo"
            registrar_log(f"Importando módulo 'scrapers.{modulo_nome}' (classe '{classe_nome}')...", nivel="INFO", modulo="GERENCIADOR")
            modulo = importlib.import_module(f"scrapers.{modulo_nome}")
            return getattr(modulo, classe_nome)
        except ModuleNotFoundError as e:
            # Debug detalhado se falhar
            print(f"DEBUG PATH: {sys.path}")
            raise Exception(f"Erro de Importação: {e}. Verifique se 'scrapers/{modulo_nome}.py' existe e se tem __init__.py na pasta.")
    
    def executar_scraping(self, url, output_folder):
        site_nome, modulo_nome, classe_nome = None, None, None
        inicio = time.time()
        try:
            definir_contexto_execucao(modulo="GERENCIADOR", url=url)
            registrar_log(f"Analisando URL recebida para seleção de módulo: {url}", nivel="INFO", modulo="GERENCIADOR")
            dominio_bloqueado = config.site_bloqueado(url)
            if dominio_bloqueado:
                msg_bloq = 'Site bloqueado para datasheet: ' + dominio_bloqueado
                registrar_erro_modulo("GERENCIADOR", msg_bloq, url=url)
                return {'sucesso': False, 'erro': msg_bloq}
            site_nome, modulo_nome, classe_nome = identificar_site(url)
            
            if not site_nome:
                if not config.UNIVERSAL_ATIVO:
                    msg_nao_cfg = 'Site não configurado ou URL inválida'
                    registrar_erro_modulo("GERENCIADOR", msg_nao_cfg, url=url)
                    return {'sucesso': False, 'erro': msg_nao_cfg}
                site_nome, modulo_nome, classe_nome = 'UNIVERSAL', 'universal', 'UniversalScraper'
                dominio = (urlparse(url).hostname or "URL invalida").encode("ascii", "backslashreplace").decode("ascii")
                print(f"   --> Iniciando scraper: UNIVERSAL (site sem adapter: {dominio})")
                registrar_modulo_ligado(site_nome, modulo_nome, classe_nome, url, detalhe=f"Site sem módulo específico ({dominio})")
            else:
                registrar_modulo_ligado(site_nome, modulo_nome, classe_nome, url)
            
            mod_id = identificar_modulo_scraper(site_nome=site_nome, modulo_nome=modulo_nome, classe_nome=classe_nome)
            definir_contexto_execucao(modulo=mod_id, url=url)
            ClasseScraper = self.carregar_scraper(modulo_nome, classe_nome)
            
            # Instancia o scraper
            scraper = ClasseScraper(url)
            scraper.output_folder = output_folder
            scraper.site_nome = site_nome
            scraper.modulo_nome = modulo_nome
            
            registrar_log(f"Iniciando execução de '{classe_nome}.executar()' | Pasta destino: {output_folder}", nivel="EXECUCAO", modulo=mod_id)
            print(f"   --> Iniciando scraper: {site_nome}")
            resultado = scraper.executar()
            duracao = time.time() - inicio

            if isinstance(resultado, dict):
                if resultado.get('sucesso'):
                    problemas = getattr(scraper, 'problemas_detectados', [])
                    arqs = resultado.get('arquivos', {}) or {}
                    info_arqs = f"Word={arqs.get('word_nome', 'N/A')} | PDF={arqs.get('pdf_nome', 'N/A')}"
                    if problemas:
                        registrar_log(
                            f"Execução concluída em {duracao:.2f}s COM PROBLEMAS NOS DADOS DO ITEM: {'; '.join(problemas)} | {info_arqs} | URL: {url}",
                            nivel="AVISO",
                            modulo=mod_id,
                        )
                    else:
                        registrar_log(
                            f"Execução concluída com SUCESSO COMPLETO em {duracao:.2f}s | {info_arqs} | URL: {url}",
                            nivel="SUCESSO",
                            modulo=mod_id,
                        )
                else:
                    erro_msg = resultado.get('erro', 'Erro desconhecido')
                    registrar_erro_modulo(
                        mod_id,
                        f"Falha na execução do módulo após {duracao:.2f}s: {erro_msg}",
                        url=url,
                    )
            return resultado
            
        except Exception as e:
            duracao = time.time() - inicio
            mod_id = identificar_modulo_scraper(site_nome=site_nome, modulo_nome=modulo_nome, classe_nome=classe_nome)
            registrar_erro_modulo(
                mod_id,
                f"Exceção crítica no módulo após {duracao:.2f}s: {e}",
                url=url,
                incluir_traceback=True,
            )
            # Retorna o erro detalhado para aparecer no log da API
            return {'sucesso': False, 'erro': str(e)}
