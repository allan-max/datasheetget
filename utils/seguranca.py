# utils/seguranca.py
"""Validações compartilhadas pela API (api.py / run.py) e pelos scrapers."""
import hmac
import ipaddress
import os
import uuid
from urllib.parse import urlparse

# Token opcional da API. Vazio = API aberta (comportamento antigo).
# Defina a variável de ambiente DATASHEET_API_TOKEN no servidor e envie o mesmo
# valor no cabeçalho "X-Api-Token" (ou "Authorization: Bearer <token>").
ENV_TOKEN = "DATASHEET_API_TOKEN"
# Lista opcional de hosts aceitos como webhook, separados por vírgula
# (ex.: "127.0.0.1,localhost"). Vazio = qualquer host http/https.
ENV_WEBHOOK_HOSTS = "DATASHEET_WEBHOOK_HOSTS"


def host_da_url(url):
    """Hostname em minúsculas, aceitando URL sem esquema ("www.site.com/x")."""
    texto = str(url or "").strip()
    try:
        host = urlparse(texto).hostname
        if not host and "://" not in texto:
            host = urlparse("//" + texto).hostname
    except ValueError:
        return ""
    return (host or "").lower().rstrip(".")


def validar_url_produto(url):
    """Recusa URLs que não sejam http/https públicas, sem consultar o DNS.

    O UniversalScraper ainda resolve o DNS e recusa IP interno; aqui o
    objetivo é impedir que um adapter dedicado receba um endereço interno.
    """
    try:
        p = urlparse(str(url or "").strip())
        host = (p.hostname or "").rstrip(".").lower()
        p.port  # porta inválida levanta ValueError
    except ValueError:
        raise ValueError("URL invalida")
    if p.scheme not in ("http", "https") or not host or p.username or p.password:
        raise ValueError("URL invalida: use http/https com dominio publico")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("URL aponta para endereco local")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return url
    if not ip.is_global:
        raise ValueError("URL aponta para IP privado ou reservado")
    return url


def webhook_permitido(url):
    """True quando o webhook pode receber o retorno do pedido."""
    try:
        p = urlparse(str(url or "").strip())
        host = (p.hostname or "").lower()
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not host or p.username or p.password:
        return False
    permitidos = [h.strip().lower() for h in os.environ.get(ENV_WEBHOOK_HOSTS, "").split(",") if h.strip()]
    return not permitidos or host in permitidos


def token_valido(headers):
    """True quando a API está sem token ou o pedido trouxe o token certo."""
    esperado = os.environ.get(ENV_TOKEN, "")
    if not esperado:
        return True
    recebido = headers.get("X-Api-Token") or ""
    auth = headers.get("Authorization") or ""
    if not recebido and auth.lower().startswith("bearer "):
        recebido = auth[7:].strip()
    return hmac.compare_digest(recebido.encode("utf-8"), esperado.encode("utf-8"))


def nome_temporario(prefixo, extensao="jpg"):
    """Nome único para arquivos temporários (pedidos simultâneos não se sobrescrevem)."""
    return "%s_%s.%s" % (prefixo, uuid.uuid4().hex, extensao)
