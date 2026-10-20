# utils/logger.py
import logging
import os
import re
import socket
import sys
import threading
import traceback
from datetime import datetime

LOG_DIR_SERVIDOR = r"\\SERVIDOR2\Publico\ALLAN\Logs"
LOG_FILE_NAME = "datasheet.txt"
LOG_PATH_SERVIDOR = os.path.join(LOG_DIR_SERVIDOR, LOG_FILE_NAME)
_DEFAULT_LOG_PATH_SERVIDOR = LOG_PATH_SERVIDOR

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR_LOCAL = os.path.join(BASE_DIR, "logs")
LOG_PATH_LOCAL = os.path.join(LOG_DIR_LOCAL, LOG_FILE_NAME)

_LOG_LOCK = threading.RLock()
_ORIG_STDOUT = sys.__stdout__ or sys.stdout
_ORIG_STDERR = sys.__stderr__ or sys.stderr
_CAPTURA_ATIVA = False
_CONTEXTO_THREAD = threading.local()

_PADRAO_TIMESTAMP = re.compile(r"^\[\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\]")

DESCRICOES_INVALIDAS = (
    "descrição indisponível",
    "descricao indisponivel",
    "descrição não disponível",
    "descricao nao disponivel",
    "descrição detalhada não disponível",
    "descricao detalhada nao disponivel",
    "sem descrição disponível",
    "sem descricao disponivel",
    "sem descrição",
    "sem descricao",
    "informações técnicas não detalhadas",
    "informacoes tecnicas nao detalhadas",
    "sinopse indisponível",
    "sinopse indisponivel",
    "descrição extraída automaticamente",
    "descricao extraida automaticamente",
)


def _agora():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def obter_caminho_log():
    return LOG_PATH_SERVIDOR


def definir_contexto_execucao(modulo=None, url=None, pedido_id=None):
    """Define na thread atual qual módulo, URL e pedido estão em execução para enriquecer todos os logs."""
    if modulo is not None:
        _CONTEXTO_THREAD.modulo = modulo
    if url is not None:
        _CONTEXTO_THREAD.url = url
    if pedido_id is not None:
        _CONTEXTO_THREAD.pedido_id = pedido_id


def limpar_contexto_execucao():
    _CONTEXTO_THREAD.modulo = None
    _CONTEXTO_THREAD.url = None
    _CONTEXTO_THREAD.pedido_id = None


def obter_contexto_execucao():
    return (
        getattr(_CONTEXTO_THREAD, "modulo", None),
        getattr(_CONTEXTO_THREAD, "url", None),
        getattr(_CONTEXTO_THREAD, "pedido_id", None),
    )


def _gravar_no_arquivo(texto):
    if texto is None:
        return
    if not texto.endswith("\n"):
        texto += "\n"
    with _LOG_LOCK:
        em_teste_unitario = ("unittest" in sys.modules) and (LOG_PATH_SERVIDOR == _DEFAULT_LOG_PATH_SERVIDOR)
        gravou_servidor = False
        if not em_teste_unitario:
            try:
                os.makedirs(LOG_DIR_SERVIDOR, exist_ok=True)
                with open(LOG_PATH_SERVIDOR, "a", encoding="utf-8", errors="replace") as f:
                    f.write(texto)
                    f.flush()
                gravou_servidor = True
            except Exception:
                pass

        if not gravou_servidor:
            try:
                os.makedirs(LOG_DIR_LOCAL, exist_ok=True)
                with open(LOG_PATH_LOCAL, "a", encoding="utf-8", errors="replace") as f:
                    f.write(texto)
                    f.flush()
            except Exception:
                pass


def _escrever_console(texto, erro=False):
    stream = _ORIG_STDERR if erro else _ORIG_STDOUT
    if not stream:
        return
    try:
        stream.write(texto)
        stream.flush()
    except Exception:
        try:
            seguro = texto.encode("ascii", "replace").decode("ascii")
            stream.write(seguro)
            stream.flush()
        except Exception:
            pass


class TeeLogStream:
    """Intercepta sys.stdout / sys.stderr para gravar toda a execução em tempo real no datasheet.txt."""

    def __init__(self, orig_stream, is_err=False):
        self.orig_stream = orig_stream
        self.is_err = is_err
        self._local = threading.local()
        self.encoding = getattr(orig_stream, "encoding", "utf-8") or "utf-8"

    def _get_buffer(self):
        if not hasattr(self._local, "buffer"):
            self._local.buffer = ""
        return self._local.buffer

    def _set_buffer(self, val):
        self._local.buffer = val

    def write(self, data):
        if not data:
            return 0
        texto = str(data)
        _escrever_console(texto, erro=self.is_err)

        buf = self._get_buffer() + texto
        while "\n" in buf:
            linha, buf = buf.split("\n", 1)
            self._registrar_linha_capturada(linha)
        self._set_buffer(buf)
        return len(texto)

    def _registrar_linha_capturada(self, linha):
        linha_limpa = linha.rstrip("\r")
        if not linha_limpa.strip():
            return
        if _PADRAO_TIMESTAMP.match(linha_limpa.lstrip()):
            _gravar_no_arquivo(linha_limpa.lstrip())
            return

        mod_ctx, _, pedido_ctx = obter_contexto_execucao()
        nivel = "STDERR" if self.is_err else "EXECUCAO"
        mod_tag = f" [MÓDULO: {mod_ctx}]" if mod_ctx else ""
        id_tag = f" [ID: {pedido_ctx}]" if pedido_ctx else ""
        _gravar_no_arquivo(f"[{_agora()}] [{nivel}]{mod_tag}{id_tag} {linha_limpa.strip()}")

    def flush(self):
        buf = self._get_buffer()
        if buf.strip():
            self._registrar_linha_capturada(buf)
            self._set_buffer("")
        if self.orig_stream:
            try:
                self.orig_stream.flush()
            except Exception:
                pass

    def reconfigure(self, *args, **kwargs):
        if hasattr(self.orig_stream, "reconfigure"):
            try:
                self.orig_stream.reconfigure(*args, **kwargs)
            except Exception:
                pass

    def isatty(self):
        if hasattr(self.orig_stream, "isatty"):
            try:
                return self.orig_stream.isatty()
            except Exception:
                pass
        return False

    def __getattr__(self, name):
        return getattr(self.orig_stream, name)


def ativar_captura_global():
    """Ativa a captura de todos os prints, erros e logs do Python/Flask para o datasheet.txt."""
    global _CAPTURA_ATIVA, _ORIG_STDOUT, _ORIG_STDERR
    with _LOG_LOCK:
        if _CAPTURA_ATIVA:
            return
        if not isinstance(sys.stdout, TeeLogStream):
            _ORIG_STDOUT = sys.stdout
            sys.stdout = TeeLogStream(_ORIG_STDOUT, is_err=False)
        if not isinstance(sys.stderr, TeeLogStream):
            _ORIG_STDERR = sys.stderr
            sys.stderr = TeeLogStream(_ORIG_STDERR, is_err=True)

        # Redireciona handlers de logging já criados para o TeeLogStream
        loggers = [logging.getLogger(), logging.getLogger("werkzeug")]
        for lg in loggers:
            for h in getattr(lg, "handlers", []):
                if isinstance(h, logging.StreamHandler):
                    if h.stream is _ORIG_STDOUT:
                        h.stream = sys.stdout
                    elif h.stream is _ORIG_STDERR:
                        h.stream = sys.stderr

        _CAPTURA_ATIVA = True


def identificar_modulo_scraper(scraper=None, site_nome=None, modulo_nome=None, classe_nome=None):
    if scraper is not None:
        site_nome = site_nome or getattr(scraper, "site_nome", None) or getattr(scraper, "ADAPTER", None)
        modulo_nome = modulo_nome or getattr(scraper, "modulo_nome", None)
        if not modulo_nome:
            mod_full = getattr(scraper.__class__, "__module__", "")
            modulo_nome = mod_full.split(".")[-1] if mod_full else "desconhecido"
        classe_nome = classe_nome or getattr(scraper.__class__, "__name__", "Scraper")
        if not site_nome:
            site_nome = modulo_nome.upper()

    site_str = str(site_nome or modulo_nome or "DESCONHECIDO").upper()
    if modulo_nome and classe_nome:
        return f"{site_str} (scrapers.{modulo_nome}.{classe_nome})"
    elif modulo_nome:
        return f"{site_str} (scrapers.{modulo_nome})"
    return site_str


def registrar_log(mensagem, nivel="INFO", modulo=None):
    mod_ctx, _, pedido_ctx = obter_contexto_execucao()
    mod_final = modulo or mod_ctx or "SISTEMA"
    id_tag = f" [ID: {pedido_ctx}]" if pedido_ctx else ""
    linha = f"[{_agora()}] [{nivel}] [MÓDULO: {mod_final}]{id_tag} {mensagem}"
    _gravar_no_arquivo(linha)
    _escrever_console(linha + "\n", erro=(nivel in ("ERRO", "CRITICO", "ERRO DO MODULO")))


def registrar_separador(caractere="=", tamanho=80):
    linha = f"[{_agora()}] {caractere * tamanho}"
    _gravar_no_arquivo(linha)
    _escrever_console(linha + "\n")


def registrar_modulo_ligado(site_nome, modulo_nome, classe_nome, url, detalhe=None):
    mod_id = identificar_modulo_scraper(site_nome=site_nome, modulo_nome=modulo_nome, classe_nome=classe_nome)
    definir_contexto_execucao(modulo=mod_id, url=url)
    extra = f" | Detalhe: {detalhe}" if detalhe else ""
    msg = f"Módulo ligado: {mod_id} foi acionado para processar a URL: {url}{extra}"
    registrar_log(msg, nivel="MODULO LIGADO", modulo=mod_id)


def registrar_erro_modulo(modulo, descricao_problema, url=None, titulo=None, incluir_traceback=False):
    mod_ctx, url_ctx, _ = obter_contexto_execucao()
    mod_final = modulo or mod_ctx or "DESCONHECIDO"
    url_final = url or url_ctx
    partes = [
        f"Módulo que apresentou problema: {mod_final}",
        f"Descrição do problema: {descricao_problema}",
    ]
    if titulo:
        partes.append(f"Título do item: {titulo}")
    if url_final:
        partes.append(f"URL: {url_final}")
    registrar_log(" | ".join(partes), nivel="ERRO DO MODULO", modulo=mod_final)
    if incluir_traceback:
        tb = traceback.format_exc()
        if tb and "NoneType: None" not in tb:
            for linha_tb in tb.strip().splitlines():
                registrar_log(f"   [TRACEBACK] {linha_tb}", nivel="ERRO DO MODULO", modulo=mod_final)


def descricao_esta_ausente(descricao):
    if descricao is None:
        return True, "campo 'descricao' está nulo (None)"
    texto = str(descricao).strip()
    if not texto:
        return True, "campo 'descricao' veio vazio ('')"
    texto_lower = texto.lower().rstrip(".! ")
    for invalida in DESCRICOES_INVALIDAS:
        if texto_lower == invalida or texto_lower.startswith(invalida):
            return True, f"descrição retornou texto padrão de ausência ('{texto}')"
    if len(texto) < 10:
        return True, f"descrição muito curta / insuficiente ({len(texto)} caracteres: '{texto}')"
    return False, ""


def imagem_esta_ausente(caminho_imagem):
    if not caminho_imagem:
        return True, "nenhuma URL de imagem encontrada na página ou falha no download da imagem (caminho_imagem_temp vazio)"
    if not os.path.exists(caminho_imagem):
        return True, f"arquivo de imagem temporário não foi encontrado no disco ('{caminho_imagem}')"
    try:
        if os.path.getsize(caminho_imagem) == 0:
            return True, f"arquivo de imagem baixado está vazio (0 bytes: '{caminho_imagem}')"
    except Exception:
        pass
    return False, ""


def titulo_esta_ausente(titulo):
    if not titulo:
        return True, "título do produto veio vazio"
    t = str(titulo).strip()
    if not t:
        return True, "título do produto veio em branco"
    t_lower = t.lower()
    if t_lower in ("produto", "sem título", "sem titulo", "amazon produto", "produto kabum!", "produto agis", "produto kalunga"):
        return True, f"título específico não encontrado (usou título genérico '{t}')"
    return False, ""


def specs_estao_ausentes(specs):
    if not specs:
        return True, "nenhuma especificação / ficha técnica foi encontrada na página"
    if isinstance(specs, dict):
        chaves_reais = [
            k for k, v in specs.items()
            if str(k).strip().lower() not in ("garantia", "info")
            and str(v).strip().lower() != "verificar descrição completa"
        ]
        if not chaves_reais:
            return True, "ficha técnica veio sem especificações reais do produto"
    elif isinstance(specs, list) and len(specs) == 0:
        return True, "lista de ficha técnica veio vazia"
    return False, ""


def validar_e_reportar_dados_item(dados, scraper=None, modulo=None, url=None):
    """
    Inspeciona todos os dados extraídos do item e registra no log datasheet.txt
    todos os detalhes (título, imagem, descrição, ficha técnica) e qualquer erro
    ou ausência de dados, informando o módulo responsável e a descrição do problema.
    """
    mod_id = modulo or identificar_modulo_scraper(scraper=scraper)
    url_item = url or getattr(scraper, "url", None) or "URL não informada"
    dados = dados or {}

    titulo = dados.get("titulo")
    descricao = dados.get("descricao")
    specs = dados.get("caracteristicas")
    caminho_imagem = dados.get("caminho_imagem_temp")

    registrar_log(f"Iniciando validação detalhada dos dados extraídos do item | URL: {url_item}", nivel="VALIDACAO", modulo=mod_id)

    problemas = []

    # 1. Validação de Título
    sem_titulo, motivo_titulo = titulo_esta_ausente(titulo)
    if sem_titulo:
        desc_prob = f"Item veio SEM TÍTULO adequado ({motivo_titulo})."
        problemas.append(desc_prob)
        registrar_erro_modulo(mod_id, desc_prob, url=url_item, titulo=titulo)
    else:
        registrar_log(f"Título extraído com sucesso: '{titulo}'", nivel="INFO", modulo=mod_id)

    # 2. Validação de Imagem
    sem_img, motivo_img = imagem_esta_ausente(caminho_imagem)
    if sem_img:
        desc_prob = f"Item veio SEM IMAGEM ({motivo_img})."
        problemas.append(desc_prob)
        registrar_erro_modulo(mod_id, desc_prob, url=url_item, titulo=titulo)
    else:
        tamanho_kb = 0.0
        try:
            tamanho_kb = os.path.getsize(caminho_imagem) / 1024.0
        except Exception:
            pass
        registrar_log(
            f"Imagem extraída e validada com sucesso: '{caminho_imagem}' ({tamanho_kb:.1f} KB).",
            nivel="INFO",
            modulo=mod_id,
        )

    # 3. Validação de Descrição
    sem_desc, motivo_desc = descricao_esta_ausente(descricao)
    if sem_desc:
        desc_prob = f"Item veio SEM DESCRIÇÃO ({motivo_desc})."
        problemas.append(desc_prob)
        registrar_erro_modulo(mod_id, desc_prob, url=url_item, titulo=titulo)
    else:
        texto_desc = str(descricao).strip()
        tam_desc = len(texto_desc)
        previa = re.sub(r"\s+", " ", texto_desc)[:180]
        registrar_log(
            f"Descrição extraída com sucesso ({tam_desc} caracteres) | Prévia: \"{previa}...\"",
            nivel="INFO",
            modulo=mod_id,
        )

    # 4. Validação de Ficha Técnica (Características)
    sem_specs, motivo_specs = specs_estao_ausentes(specs)
    if sem_specs:
        desc_prob = f"Item veio SEM FICHA TÉCNICA / ESPECIFICAÇÕES ({motivo_specs})."
        problemas.append(desc_prob)
        registrar_erro_modulo(mod_id, desc_prob, url=url_item, titulo=titulo)
    else:
        itens_lista = list(specs.items()) if isinstance(specs, dict) else list(specs)
        qtd_specs = len(itens_lista)
        resumo_specs = ", ".join(f"{k}: {str(v)[:40]}" for k, v in itens_lista[:8])
        registrar_log(
            f"Ficha técnica extraída com sucesso ({qtd_specs} características) | Amostra: [{resumo_specs}]",
            nivel="INFO",
            modulo=mod_id,
        )

    if problemas:
        registrar_log(
            f"Validação finalizada com {len(problemas)} problema(s) detectado(s) no módulo {mod_id}: {'; '.join(problemas)}",
            nivel="AVISO",
            modulo=mod_id,
        )
    else:
        registrar_log(
            f"Validação finalizada: todos os dados do item (título, imagem, descrição e ficha técnica) estão completos.",
            nivel="INFO",
            modulo=mod_id,
        )

    return problemas


# Ativa automaticamente a captura global ao importar o módulo (fora de testes unitários)
if "unittest" not in sys.modules:
    ativar_captura_global()
