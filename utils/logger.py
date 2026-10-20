# utils/logger.py
import os
import re
import sys
import threading
from datetime import datetime

LOG_DIR_SERVIDOR = r"\\SERVIDOR2\Publico\ALLAN\Logs"
LOG_FILE_NAME = "datasheet.txt"
LOG_PATH_SERVIDOR = os.path.join(LOG_DIR_SERVIDOR, LOG_FILE_NAME)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR_LOCAL = os.path.join(BASE_DIR, "logs")
LOG_PATH_LOCAL = os.path.join(LOG_DIR_LOCAL, LOG_FILE_NAME)

_LOG_LOCK = threading.RLock()
_ORIG_STDOUT = sys.__stdout__ or sys.stdout
_ORIG_STDERR = sys.__stderr__ or sys.stderr
_CAPTURA_ATIVA = False

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


def _gravar_no_arquivo(texto):
    if not texto:
        return
    if not texto.endswith("\n"):
        texto += "\n"
    with _LOG_LOCK:
        gravou_servidor = False
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
    """Intercepta sys.stdout / sys.stderr para gravar tudo em tempo real no datasheet.txt."""

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
            _gravar_no_arquivo("")
            return
        if _PADRAO_TIMESTAMP.match(linha_limpa.lstrip()):
            _gravar_no_arquivo(linha_limpa.lstrip())
        else:
            prefixo = "[STDERR] " if self.is_err else ""
            _gravar_no_arquivo(f"[{_agora()}] {prefixo}{linha_limpa}")

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
    """Ativa a captura de todos os prints e logs do Python para o datasheet.txt."""
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


def registrar_log(mensagem, nivel="INFO", modulo="SISTEMA"):
    linha = f"[{_agora()}] [{nivel}] [MÓDULO: {modulo}] {mensagem}"
    _gravar_no_arquivo(linha)
    _escrever_console(linha + "\n", erro=(nivel in ("ERRO", "CRITICO", "ERRO DO MODULO")))


def registrar_modulo_ligado(site_nome, modulo_nome, classe_nome, url, detalhe=None):
    mod_id = identificar_modulo_scraper(site_nome=site_nome, modulo_nome=modulo_nome, classe_nome=classe_nome)
    extra = f" | Detalhe: {detalhe}" if detalhe else ""
    msg = f"Módulo ligado: {mod_id} acionado para processar a URL: {url}{extra}"
    registrar_log(msg, nivel="MODULO LIGADO", modulo=mod_id)


def registrar_erro_modulo(modulo, descricao_problema, url=None, titulo=None):
    partes = [
        f"Módulo que apresentou problema: {modulo}",
        f"Descrição do problema: {descricao_problema}",
    ]
    if titulo:
        partes.append(f"Título do item: {titulo}")
    if url:
        partes.append(f"URL: {url}")
    registrar_log(" | ".join(partes), nivel="ERRO DO MODULO", modulo=modulo)


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
    Verifica se o item extraído pelo módulo veio sem imagem, sem descrição,
    sem título ou sem ficha técnica, e grava no log datasheet.txt qual módulo
    apresentou o problema e a descrição detalhada do que ocorreu.
    Retorna lista de descrições dos problemas detectados.
    """
    mod_id = modulo or identificar_modulo_scraper(scraper=scraper)
    url_item = url or getattr(scraper, "url", None) or "URL não informada"
    dados = dados or {}

    titulo = dados.get("titulo")
    descricao = dados.get("descricao")
    specs = dados.get("caracteristicas")
    caminho_imagem = dados.get("caminho_imagem_temp")

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
        registrar_log(f"Imagem extraída e validada com sucesso ({caminho_imagem}).", nivel="INFO", modulo=mod_id)

    # 3. Validação de Descrição
    sem_desc, motivo_desc = descricao_esta_ausente(descricao)
    if sem_desc:
        desc_prob = f"Item veio SEM DESCRIÇÃO ({motivo_desc})."
        problemas.append(desc_prob)
        registrar_erro_modulo(mod_id, desc_prob, url=url_item, titulo=titulo)
    else:
        tam_desc = len(str(descricao).strip())
        registrar_log(f"Descrição extraída com sucesso ({tam_desc} caracteres).", nivel="INFO", modulo=mod_id)

    # 4. Validação de Ficha Técnica (Características)
    sem_specs, motivo_specs = specs_estao_ausentes(specs)
    if sem_specs:
        desc_prob = f"Item veio SEM FICHA TÉCNICA / ESPECIFICAÇÕES ({motivo_specs})."
        problemas.append(desc_prob)
        registrar_erro_modulo(mod_id, desc_prob, url=url_item, titulo=titulo)
    else:
        qtd_specs = len(specs) if hasattr(specs, "__len__") else 1
        registrar_log(f"Ficha técnica extraída com sucesso ({qtd_specs} características).", nivel="INFO", modulo=mod_id)

    return problemas
