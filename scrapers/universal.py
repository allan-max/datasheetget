import ipaddress
import html as html_lib
import json
import os
import re
import socket
import threading
import time
from io import BytesIO
from itertools import islice
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString
from PIL import Image

from .base import BaseScraper
from utils.logger import identificar_modulo_scraper, registrar_erro_modulo, registrar_log


CHROME_VAGAS = threading.Semaphore(1)
# Sinais de pagina de bloqueio/desafio anti-bot (Cloudflare, Akamai, Loja Integrada, NOC, Sucuri...).
BLOQUEIOS = ("cf-chl", "just a moment", "access denied", "acesso negado",
             "sec-if-cpt-container", "powered and protected by",
             "checking your browser", "verifique se voce e humano",
             "acesso bloqueado", "request foi bloqueado", "verificação de segurança",
             "verificacao de seguranca", "verifying your browser", "noc_verification",
             "/challenge.js", "attention required", "please enable javascript and cookies")
TITULOS_INVALIDOS = ("404", "nao encontrada", "não encontrada", "not found",
                    "access denied", "just a moment", "login", "entrar na conta",
                    "pagina inicial", "página inicial", "acesso bloqueado", "ops :(",
                    "something went wrong", "verificação de segurança", "verifying your browser",
                    "página não existe", "pagina nao existe", "erro", "error")
LIXO_SPEC = ("preço", "preco", "frete", "parcel", "estoque", "quantidade", "avalia", "compartilh",
             "vendido por", "entrega", "calcul", "cep", "pagamento", "cupom", "comprar", "carrinho",
             "favorit", "whatsapp", "telefone", "e-mail", "email", "sku do vendedor", "price", "vat",
             "delivery", "quantity", "shipping", "pedido", "ajuda", "dúvida", "duvida", "pergunta",
             "resposta", "horário", "horario", "clube", "conheça", "conheca", "cartão presente",
             "cartao presente", "selecione", "escolha", "rastre", "newsletter", "cadastr", "login")
# Pares de cabecalho de tabela que nao sao especificacao ("Propriedade | Especificacao").
CABECALHOS = ("propriedade", "característica", "caracteristica", "especificação", "especificacao",
              "item", "descrição", "descricao", "valor", "atributo", "detalhe", "informação", "informacao",
              "código", "codigo", "referência", "referencia", "modelo", "nome", "produto", "unidade")
# Linhas de descricao que sao avisos e nao especificacao ("Atencao: nao use...").
CHAVES_AVISO = ("atenção", "atencao", "obs", "observação", "observacao", "importante", "nota", "cuidado",
                "aviso", "dica", "ps", "imagem", "imagens", "foto", "fotos", "aproveite", "saiba mais",
                "download", "downloads", "informações complementares", "informacoes complementares")
# Lixo comercial com fronteira de palavra: "sac" nao derruba "Saco de lixo", "troca" nao derruba "trocador".
TERMOS_LIXO = ("garantia", "devolução", "devolucao", "reembolso", "troca", "trocas",
               "frete", "envio", "envios", "entrega", "entregas", "postagem", "rastreio",
               "estoque", "pronta entrega", "parcele", "parcelamento", "parcelas", "juros",
               "cartão de crédito", "cartao de credito", "cartões", "boleto", "pagamento", "pix",
               "clique aqui", "veja mais", "confira", "acesse", "visite", "nosso site", "nossa loja",
               "loja virtual", "vendedor", "comprar", "compre", "oferta", "ofertas", "promoção",
               "promocao", "cupom", "desconto", "whatsapp", "atendimento", "sac", "dúvidas", "duvidas",
               "mercadolivre", "mercado livre", "amazon", "magalu", "meramente ilustrativa",
               "meramente ilustrativas", "estar logado", "faça login", "faca login", "fazer login",
               "cadastre-se", "carrinho", "lista de desejos", "compartilhe", "cookies")
RE_LIXO = re.compile(r"(?<!\w)(?:%s)(?!\w)" % "|".join(re.escape(t) for t in TERMOS_LIXO), re.I)
# Titulos que abrem um bloco de ficha tecnica.
RE_TITULO_SPEC = re.compile(
    r"^(?:especifica[cç](?:[õo]es|[ãa]o)(?: t[ée]cnicas?)?|ficha t[ée]cnica|caracter[ií]sticas(?: t[ée]cnicas| do produto| gerais)?"
    r"|dados t[ée]cnicos|informa[cç][õo]es t[ée]cnicas|detalhes t[ée]cnicos|technical (?:data|specifications|details)"
    r"|specifications?|specs|atributos)\s*:?$", re.I)
RE_TITULO_DESC = re.compile(r"^(?:descri[cç][ãa]o(?: do produto| geral| completa)?|sobre o produto|detalhes do produto"
                            r"|informa[cç][õo]es do produto|apresenta[cç][ãa]o|description|product details)\s*:?$", re.I)
# Imagens que nunca sao a foto do produto.
RE_IMG_RUIM = re.compile(r"logo|icon|sprite|banner|marketplace|placeholder|loading|selo|pagamento|bandeira|whatsapp"
                         r"|avatar|og-default|[/_-]default\.|youtube\.com|ytimg\.com|facebook\.com/tr|statcounter"
                         r"|/pixel|spacer\.|blank\.(?:gif|png)|/cc-[a-z]+\.|/flags?/|/difer/"
                         r"|/(?:instagram|facebook|twitter|linkedin|tiktok|pinterest|youtube|visa|master(?:card)?|amex"
                         r"|american-express|diners|elo|hipercard|boleto|pix|ebit|comodo|buscape|reclame)[\w-]*\.", re.I)
# Miniaturas: perdem pontos mas continuam como reserva.
RE_IMG_PEQUENA = re.compile(r"small_image|thumbnail|/255x/|/small/|[-_]thumb|/thumbs?/|\b\d{2}x\d{2}\b|-50x50|-100x100"
                            r"|-150x150|[?&](?:width|w)=\d{2,3}(?:&|$)", re.I)
# Galeria do produto (classe/id da imagem ou dos pais).
RE_IMG_GALERIA = re.compile(r"galler|zoom|fotorama|product.?(?:image|photo|media|img|foto)|produto.?(?:imagem|foto)"
                            r"|imagem.?produto|foto.?produto|img.?principal|main.?(?:image|photo|img)|principal", re.I)
# Parametros de redimensionamento que podem ser tirados da URL para ter a foto original.
PARAMS_TAMANHO = ("width", "height", "w", "h", "fit", "canvas", "resize", "size", "crop", "optimize", "bg-color")
# Titulo de secao que encerra o conteudo do produto (vitrines, avaliacoes, rodape).
RE_FIM_CONTEUDO = re.compile(r"^(?:produtos? (?:relacionados|similares|complementares|recomendados)|vistos recentemente"
                             r"|quem (?:viu|comprou)|voc[eê] (?:tamb[eé]m )?pode (?:gostar|se interessar)|compre junto"
                             r"|outros produtos|veja tamb[eé]m|aproveite tamb[eé]m|avalia[cç][õo]es|perguntas"
                             r"|mais vendidos?|related products|you may also like|customers also)\b", re.I)
# Linha de loja/contato/preco no meio do conteudo principal.
RE_LINHA_LOJA = re.compile(r"R\$\s*\d|\bde:\s.*\bpor:|vendido por|mais vendido|©|copyright|\d{2}\.\d{3}\.\d{3}/\d{4}"
                           r"|\b\d{5}-\d{3}\b|@[\w-]+\.\w|\(\d{2}\)\s*\d{4}|\bseg(?:unda)?\.? (?:a|à) sex|pol[ií]tica de"
                           r"|termos de uso|todos os direitos|ampliar|ilustrativ|no cart[ãa]o|loja f[ií]sica"
                           r"|e-?mail d[oe]|indique|indicar|cota[cç][ãa]o", re.I)
BLOCOS_TEXTO = ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "section",
                "article", "table", "ul", "ol", "summary", "details", "blockquote", "pre")
MARCADORES = " \t-–—•*·>✓✔▪►●◆■□○➤→"
MAPA_PDF = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                         "–": "-", "—": "-", "™": "TM", "®": "(R)",
                         "€": "EUR", "•": "-", "…": "...", "\xa0": " "})


def versao_chrome():
    """Versao principal do Chrome instalado; 109 (servidor Windows 2012) se nao der para ler."""
    if os.name == "nt":
        try:
            import winreg
            for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(raiz, r"Software\Google\Chrome\BLBeacon") as chave:
                        return int(str(winreg.QueryValueEx(chave, "version")[0]).split(".")[0])
                except OSError:
                    continue
        except Exception:
            pass
    return 109


def marcador(tag):
    """Classe, id e atributos de teste/hook: onde as lojas dizem o que e cada bloco."""
    if tag.attrs is None:
        return ""
    return " ".join([" ".join(tag.get("class", []) or []), tag.get("id") or "", tag.get("data-testid") or "",
                     tag.get("data-hook") or "", tag.get("itemprop") or ""])


class UniversalScraper(BaseScraper):
    ADAPTER = "UNIVERSAL"
    exigir_imagem = False
    imagem_css = None
    espera_css = None

    def normalizar(self, texto):
        texto = str(texto or "").translate(MAPA_PDF)
        return texto.encode("latin-1", "ignore").decode("latin-1")

    def limpar_texto(self, texto):
        if texto is None or isinstance(texto, (dict, list)):
            return ""
        return re.sub(r"\s+", " ", str(texto)).strip()

    def tem_lixo(self, texto):
        return bool(RE_LIXO.search(str(texto or "")))

    def limpar_lixo_comercial(self, texto):
        """Igual a da base, mas casando palavra inteira (a base derrubava 'Saco de lixo' por causa de 'sac')."""
        if not texto:
            return "Descrição não disponível."
        linhas = []
        for linha in str(texto).split("\n"):
            if len(linha.strip()) < 3 or self.tem_lixo(linha):
                continue
            linhas.append(re.sub(r"^[\s\-\•\.\*]+", "", linha).strip())
        final = "\n".join(linhas)
        return final if len(final) >= 10 else "Informações técnicas não detalhadas."

    def filtrar_specs(self, specs_dict):
        return {k: v for k, v in specs_dict.items() if not self.tem_lixo(k)}

    def validar_url(self, url):
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
            raise ValueError("URL invalida: use http/https com dominio publico")
        host = p.hostname.rstrip(".")
        if host.lower() == "localhost" or host.lower().endswith(".localhost"):
            raise ValueError("URL aponta para endereco local")
        try:
            if not ipaddress.ip_address(host).is_global:
                raise ValueError("URL aponta para IP privado ou reservado")
        except ValueError as e:
            if str(e).startswith("URL aponta"):
                raise
        try:
            enderecos = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80),
                                           type=socket.SOCK_STREAM)
        except socket.gaierror:
            raise ValueError("Dominio nao resolve no DNS")
        if not enderecos:
            raise ValueError("Dominio nao resolve no DNS")
        for endereco in enderecos:
            ip = ipaddress.ip_address(endereco[4][0])
            if not ip.is_global:
                raise ValueError("URL aponta para IP privado ou reservado")
        return url

    def corrigir_encoding(self, resposta):
        """Sem charset no cabecalho o requests assume ISO-8859-1 e o titulo sai 'AÃ§o'."""
        try:
            tipo = (resposta.headers.get("Content-Type") or "").lower()
            if "charset" in tipo or ("html" not in tipo and "json" not in tipo):
                return
            inicio = resposta.content[:4096].decode("ascii", "ignore")
            achado = re.search(r"<meta[^>]+charset=[\"']?([\w-]+)", inicio, re.I)
            resposta.encoding = achado.group(1) if achado else (resposta.apparent_encoding or "utf-8")
        except Exception:
            pass

    def pedir(self, url, session=None, timeout=30):
        session = session or requests.Session()
        atual = url
        headers = dict(self.headers, **{"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7"})
        for _ in range(6):
            self.validar_url(atual)
            resposta = session.get(atual, headers=headers, timeout=timeout, allow_redirects=False)
            if resposta.is_redirect:
                destino = resposta.headers.get("Location")
                if not destino:
                    raise ValueError("Redirect sem destino")
                atual = urljoin(atual, destino)
                self.validar_url(atual)
                continue
            if hasattr(resposta, "headers") and hasattr(resposta, "content"):
                self.corrigir_encoding(resposta)
            return resposta
        raise ValueError("Muitos redirects")

    def guardar_falha(self, html, dominio):
        try:
            os.makedirs(self.output_folder, exist_ok=True)
            nome = "universal_falha_%s_%s.html" % (
                re.sub(r"[^a-zA-Z0-9.-]", "_", dominio), time.time_ns())
            caminho = os.path.join(self.output_folder, nome)
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(html or "")
            print("   [Universal] HTML da falha: " + caminho)
        except Exception as e:
            print("   [Universal] Falha ao salvar HTML: " + str(e).encode("ascii", "replace").decode())

    def bloqueada(self, html, status=200):
        if status in (403, 429, 503):
            return True
        h = (html or "").lower()
        if not h:
            return False
        titulo = re.search(r"<title[^>]*>(.*?)</title>", h[:20000], re.S)
        titulo = titulo.group(1) if titulo else ""
        # Paginas de desafio sao pequenas; numa pagina de produto grande o texto pode estar em script.
        return any(x in titulo for x in BLOQUEIOS) or (len(h) < 60000 and any(x in h for x in BLOQUEIOS))

    def navegar(self, url):
        import undetected_chromedriver as uc
        if not CHROME_VAGAS.acquire(timeout=45):
            raise TimeoutError("Limite de navegadores ocupado")
        try:
            driver = None
            try:
                options = uc.ChromeOptions()
                options.page_load_strategy = "eager"
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--window-size=1920,1080")
                try:
                    driver = uc.Chrome(options=options, version_main=versao_chrome())
                except (PermissionError, OSError):
                    # chromedriver.exe ainda preso pelo processo anterior; tenta de novo uma vez.
                    time.sleep(3)
                    options = uc.ChromeOptions()
                    options.page_load_strategy = "eager"
                    options.add_argument("--no-sandbox")
                    options.add_argument("--disable-dev-shm-usage")
                    options.add_argument("--window-size=1920,1080")
                    driver = uc.Chrome(options=options, version_main=versao_chrome())
                driver.set_page_load_timeout(40)
                try:
                    driver.get(url)
                except Exception as e:
                    print("   [Universal] Navegacao lenta: " + type(e).__name__)
                self.validar_url(driver.current_url)
                # Desafio anti-bot costuma resolver sozinho em alguns segundos.
                for _ in range(12):
                    if not self.bloqueada(driver.page_source):
                        break
                    time.sleep(1)
                if self.espera_css:
                    for _ in range(15):
                        if driver.execute_script("return !!document.querySelector(arguments[0])", self.espera_css):
                            break
                        time.sleep(1)
                for posicao in (0, 900, 1800, 2700):
                    driver.execute_script("window.scrollTo(0, arguments[0]);", posicao)
                    time.sleep(1)
                # Abas/acordeoes de ficha tecnica fechados escondem o conteudo em alguns temas.
                try:
                    driver.execute_script("""
                        document.querySelectorAll('details').forEach(function(d){ d.open = true; });
                        var re = /especifica|ficha|caracter|t[eé]cnic|descri/i;
                        document.querySelectorAll('a[href^="#"], button, [role=tab]').forEach(function(el){
                            var t = (el.innerText || '').trim();
                            if (t.length < 40 && re.test(t)) { try { el.click(); } catch (e) {} }
                        });
                    """)
                    time.sleep(1)
                except Exception:
                    pass
                if self.imagem_css:
                    self._foto_navegador = None
                    try:
                        foto_url = driver.execute_script("""
                            var img = document.querySelector(arguments[0]);
                            return img && (img.currentSrc || img.src);
                        """, self.imagem_css)
                        if foto_url:
                            self.validar_url(foto_url)
                            aba_produto = driver.current_window_handle
                            try:
                                driver.switch_to.new_window("tab")
                                driver.set_page_load_timeout(20)
                                driver.get(foto_url)
                                for _ in range(10):
                                    foto = driver.execute_script("""
                                        var i = document.querySelector('img');
                                        return i && i.complete && i.naturalWidth >= 300 ? i : null;
                                    """)
                                    if foto:
                                        caminho = os.path.join(self.output_folder,
                                                               "foto_%s_%s.jpg" % (self.ADAPTER.lower(), time.time_ns()))
                                        Image.open(BytesIO(foto.screenshot_as_png)).convert("RGB").save(caminho, "JPEG", quality=90)
                                        self._foto_navegador = caminho
                                        break
                                    time.sleep(1)
                            finally:
                                if driver.current_window_handle != aba_produto:
                                    driver.close()
                                driver.switch_to.window(aba_produto)
                    except Exception as e:
                        print("   [%s] Foto no navegador: %s" % (self.ADAPTER, type(e).__name__))
                return driver.page_source, driver.current_url
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
        finally:
            CHROME_VAGAS.release()

    def produto_jsonld(self, soup):
        def eh_produto(obj):
            tipos = obj.get("@type") or []
            if isinstance(tipos, str):
                tipos = [tipos]
            return any(str(t).lower().endswith(("product", "productgroup", "productmodel")) for t in tipos)

        def visitar(obj):
            if isinstance(obj, list):
                for item in obj:
                    achado = visitar(item)
                    if achado:
                        return achado
            elif isinstance(obj, dict):
                if eh_produto(obj):
                    return obj
                for chave in ("@graph", "mainEntity", "itemListElement", "item", "about"):
                    achado = visitar(obj.get(chave))
                    if achado:
                        return achado
            return None
        for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
            bruto = script.string or script.get_text() or ""
            # Alguns temas deixam virgula sobrando ou quebras de linha cruas dentro das strings.
            for texto in (bruto, re.sub(r",\s*([}\]])", r"\1", bruto.replace("\n", " ").replace("\r", " "))):
                try:
                    produto = visitar(json.loads(texto, strict=False))
                    if produto:
                        return produto
                    break
                except (ValueError, TypeError):
                    continue
        return {}

    def linhas_html(self, html):
        """Texto em linhas respeitando blocos: '<b>Peso:</b> 2 kg' vira uma linha so."""
        if not html:
            return []
        soup = BeautifulSoup(str(html), "html.parser")
        for tag in soup.find_all(["script", "style", "noscript", "svg", "button", "select", "input"]):
            tag.decompose()
        for br in soup.find_all("br"):
            # html.parser aninha o resto da pagina dentro de <br> sem barra; unwrap preserva esse conteudo.
            br.insert_before("\n")
            br.unwrap()
        for tag in soup.find_all(BLOCOS_TEXTO):
            tag.insert_before("\n")
            tag.append("\n")
        for celula in soup.find_all(["td", "th"]):
            celula.append(" \t ")
        linhas = []
        for linha in soup.get_text("").split("\n"):
            linha = re.sub(r"\s+", " ", linha.replace("\t", " ")).strip()
            if linha:
                linhas.append(linha)
        return linhas

    def texto_html(self, html):
        return "\n".join(self.linhas_html(html))

    def limpar_descricao(self, texto):
        if not texto:
            return ""
        partes, vistas = [], set()
        for linha in self.linhas_html(texto):
            linha = self.limpar_texto(linha).strip(MARCADORES)
            # Linha curta so fica se for do tipo "Chave: valor" (ex.: "Marca: Betz").
            if len(linha) < 15 and not re.match(r"^[^:]{2,40}:\s*\S", linha):
                continue
            if RE_TITULO_DESC.match(linha) or linha.lower() in vistas:
                continue
            vistas.add(linha.lower())
            # Lixo comercial sai por frase, nao o paragrafo inteiro.
            frases = [f for f in re.split(r"(?<=[.!?])\s+", linha) if not self.tem_lixo(f)]
            linha = " ".join(frases).strip()
            if len(linha) >= 15 or re.match(r"^[^:]{2,40}:\s*\S", linha):
                partes.append(linha)
        return self.normalizar("\n".join(partes)[:9000])

    def adicionar_spec(self, specs, chave, valor):
        chave = self.normalizar(self.limpar_texto(chave)).strip(MARCADORES + ":.").strip()
        # No valor so tira marcador seguido de espaco: "-16 a -20 C" e numero negativo, nao bullet.
        valor = self.normalizar(self.limpar_texto(valor))
        valor = re.sub(r"^(?:[-–—•*·>]\s+|[✓✔▪►●◆■□○➤→:]\s*)+", "", valor).strip()
        if chave and valor.lower().startswith(chave.lower() + ":"):
            valor = valor[len(chave) + 1:].strip()  # "Marca: Marca: DJI"
        if valor.endswith(".") and not valor.endswith(".."):
            valor = valor[:-1].strip()
        if not chave or len(chave) > 60 or not valor or len(valor) > 600:
            return
        # Chave precisa de palavra ("1." e "110v" sao sobra de lista/tabela) e nao pode ser outra linha "X: Y".
        if ":" in chave or len(re.findall(r"[A-Za-zÀ-ÿ]", chave)) < 2:
            return
        if chave.isupper() and len(chave) > 3:
            chave = chave.capitalize()
        if valor.lower() in ("n/a", "n/t", "-", "--", "não informado", "nao informado", "nao se aplica",
                             "não se aplica", "null", "none", "undefined", "a definir", "consulte"):
            return
        if chave.lower() == valor.lower() or (chave.lower() in CABECALHOS and valor.lower() in CABECALHOS):
            return
        if any(p in chave.lower() for p in LIXO_SPEC) or re.match(r"(?:seg|ter|qua|qui|sex|s[áa]b|dom)\b", chave, re.I):
            return
        # Valor que e titulo de aba, preco ou texto comercial ("Em estoque", "Quem paga o boleto").
        if RE_TITULO_SPEC.match(valor) or RE_TITULO_DESC.match(valor) or self.tem_lixo(valor) \
                or re.match(r"^(?:R\$|US\$|€|EUR\b|\$)\s*\d", valor, re.I):
            return
        anterior = next((k for k in specs if k.lower() == chave.lower()), None)
        if anterior:
            if valor.lower() not in specs[anterior].lower().split(" / ") and len(specs[anterior]) < 400:
                specs[anterior] += " / " + valor
        else:
            specs[chave] = valor

    def specs_texto(self, linhas, specs):
        """Extrai 'Chave: valor' de linhas de texto (descricao, blocos de ficha)."""
        grupo = ""
        if isinstance(linhas, str):
            linhas = self.linhas_html(linhas)
        linhas = [self.limpar_texto(l).strip(MARCADORES) for l in linhas]
        for i, linha in enumerate(linhas):
            if not linha:
                continue
            m = re.match(r"^([^:]{2,50}?)\s*:\s*(.+)$", linha)
            if m and not re.match(r"^https?$", m.group(1).strip(), re.I):
                chave, valor = m.group(1).strip(MARCADORES), m.group(2).strip()
                if (chave.count(" ") > 6 or not re.search(r"[A-Za-zÀ-ÿ]", chave)
                        or chave.lower() in CHAVES_AVISO or valor.lower().startswith(("http", "www."))
                        or len(valor) > 200 or (len(valor) > 120 and valor.count(". ") >= 2)):
                    continue
                self.adicionar_spec(specs, (grupo + " - " if grupo else "") + chave, valor)
                continue
            if linha.endswith(":") and len(linha) < 45:
                proxima = linhas[i + 1] if i + 1 < len(linhas) else ""
                titulo = linha[:-1].strip()
                if proxima and ":" not in proxima and len(proxima) < 80 and titulo.lower() not in CHAVES_AVISO \
                        and not RE_TITULO_SPEC.match(titulo) and not RE_TITULO_DESC.match(titulo):
                    self.adicionar_spec(specs, (grupo + " - " if grupo else "") + titulo, proxima)
                    linhas[i + 1] = ""
                    continue
                grupo = "" if RE_TITULO_SPEC.match(titulo) or RE_TITULO_DESC.match(titulo) else titulo
                continue
            if len(linha) > 60:
                grupo = ""

    def specs_tabela(self, raiz, specs):
        for tabela in raiz.find_all("table"):
            for linha in tabela.find_all("tr"):
                celulas = linha.find_all(["th", "td"], recursive=False)
                if len(celulas) == 2:
                    self.adicionar_spec(specs, celulas[0].get_text(" ", strip=True),
                                       celulas[1].get_text(" ", strip=True))
                elif len(celulas) == 4 and celulas[0].name == "th" and celulas[2].name == "th":
                    for k, v in ((celulas[0], celulas[1]), (celulas[2], celulas[3])):
                        self.adicionar_spec(specs, k.get_text(" ", strip=True), v.get_text(" ", strip=True))
        for dl in raiz.find_all("dl"):
            for dt in dl.find_all("dt"):
                dd = dt.find_next_sibling(["dd", "dt"])
                if dd and dd.name == "dd":
                    self.adicionar_spec(specs, dt.get_text(" ", strip=True), dd.get_text(" ", strip=True))

    def specs_pares(self, soup, specs, exigir_classe=True):
        """Linhas de ficha montadas com div/span: <div class=row><span class=label>X</span><span class=value>Y</span>.
        Dentro de um bloco de ficha ja identificado (exigir_classe=False) basta a linha ter 2 filhos curtos."""
        re_rotulo = re.compile(r"label|name|key|nome|titulo|title|propert|attr|spec-?k|caracteristica|termo", re.I)
        re_valor = re.compile(r"value|valor|data|desc|spec-?v|conteudo|content|info", re.I)
        # VTEX IO: <span data-specification-name="Peso" data-specification-value="2 kg">
        for valor in soup.find_all(attrs={"data-specification-value": True}):
            self.adicionar_spec(specs, valor.get("data-specification-name"), valor.get("data-specification-value"))

        def rotulo(el):
            # Classe do elemento e dos primeiros descendentes (o rotulo costuma estar num span interno).
            return " ".join([marcador(el)] + [marcador(x) for x in el.find_all(True, limit=4)])
        for linha in soup.find_all(["div", "li", "tr", "p"]):
            filhos = [f for f in linha.find_all(True, recursive=False) if f.name not in ("br", "hr", "img", "i", "svg")]
            if len(filhos) != 2:
                continue
            a, b = filhos
            if a.find(["ul", "table", "li", "h1", "h2"]) or b.find(["ul", "table", "li", "h1", "h2"]):
                continue
            if exigir_classe:
                ca, cb = rotulo(a), rotulo(b)
                if not (re_rotulo.search(ca) and re_valor.search(cb)) or re.search(r"product.?name|price|preco", ca, re.I):
                    continue
            k, v = a.get_text(" ", strip=True), b.get_text(" ", strip=True)
            if 1 < len(k) <= 60 and 0 < len(v) <= 300 and re.search(r"[A-Za-zÀ-ÿ]", k) and not k.endswith((".", "!")):
                self.adicionar_spec(specs, k, v)

    def blocos_por_titulo(self, soup, regex):
        """Conteudo que vem depois de um titulo 'Especificacoes'/'Descricao' (abas, acordeoes, secoes)."""
        blocos, vistos = [], set()
        tags = ("h2", "h3", "h4", "h5", "h6", "strong", "b", "p", "summary", "span", "div", "label", "li", "button")
        for trecho in soup.find_all(string=True):
            if isinstance(trecho, NavigableString) and type(trecho) is not NavigableString:
                continue  # comentario, CDATA etc.
            curto = trecho.strip()
            if not curto or len(curto) > 45 or not regex.match(curto):
                continue
            el = trecho.parent
            while el is not None and el.name not in tags and el.name not in ("body", "html"):
                el = el.parent
            if el is None or el.name not in tags or id(el) in vistos:
                continue
            vistos.add(id(el))
            texto = el.get_text(" ", strip=True)
            if not texto or len(texto) > 45 or not regex.match(texto):
                continue
            if el.name in ("div", "li", "span", "p") and el.find(["h2", "h3", "h4", "h5", "div", "ul"]):
                continue
            if el.find_parent("a") or el.find_parent("nav"):
                continue
            atual, bloco = el, None
            for _ in range(5):
                pai = atual.parent
                if pai is None or pai.name in ("body", "html", "[document]"):
                    break
                if len(pai.get_text(" ", strip=True)) > len(texto) + 30:
                    bloco = pai
                    break
                atual = pai
            if bloco is None:
                continue
            if len(bloco.get_text(" ", strip=True)) > 20000:
                # Container grande demais: pega so os irmaos seguintes ate o proximo titulo.
                partes = []
                for irmao in atual.find_next_siblings():
                    if irmao.name and irmao.name == atual.name and irmao.get_text(strip=True):
                        if len(irmao.get_text(" ", strip=True)) < 60:
                            break
                    partes.append(str(irmao))
                    if sum(len(p) for p in partes) > 60000:
                        break
                bloco = BeautifulSoup("<div>%s</div>" % "".join(partes), "html.parser").div
            if bloco is not None and all(bloco is not b for b in blocos):
                blocos.append(bloco)
        return blocos

    def specs_html(self, soup, specs):
        self.specs_tabela(soup, specs)
        for esq in soup.select("div.esq"):
            direita = esq.find_next_sibling("div", class_="dir")
            if direita:
                self.adicionar_spec(specs, esq.get_text(" ", strip=True),
                                   direita.get_text(" ", strip=True))
        self.specs_pares(soup, specs)
        re_bloco = re.compile(r"especific|ficha|caracter|tecnic|specs?\b|specification|attributes|atributo"
                              r"|product-details|technical|dados.tec|informac", re.I)
        for bloco in soup.find_all(["div", "section", "ul"]):
            if not re_bloco.search(marcador(bloco)):
                continue
            grupo = bloco.find(["h2", "h3", "h4"])
            prefixo = self.limpar_texto(grupo.get_text()) if grupo else ""
            if RE_TITULO_SPEC.match(prefixo) or RE_TITULO_DESC.match(prefixo) or len(prefixo) > 40:
                prefixo = ""
            for li in bloco.find_all("li"):
                txt = self.limpar_texto(li.get_text(" ", strip=True))
                if ":" in txt and not li.find("li"):
                    k, v = txt.split(":", 1)
                    self.adicionar_spec(specs, (prefixo + " - " if prefixo else "") + k, v)
            if len(str(bloco)) < 80000:
                self.specs_texto(self.linhas_html(str(bloco)), specs)
        for bloco in self.blocos_por_titulo(soup, RE_TITULO_SPEC):
            self.specs_tabela(bloco, specs)
            self.specs_pares(bloco, specs, exigir_classe=False)
            self.specs_texto(self.linhas_html(str(bloco)), specs)

    def limpar_titulo(self, titulo, site=""):
        titulo = self.limpar_texto(titulo)
        if not titulo:
            return ""
        titulo = re.sub(r"^(?:comprar|compre|oferta[:!]?)\s+", "", titulo, flags=re.I)
        titulo = re.sub(r"\s+[-|–]\s+(?:de\s+|por\s+|a partir de\s+)?R\$.*$", "", titulo, flags=re.I)
        titulo = re.sub(r"\s+(?:por|de)\s+R\$\s*[\d.,]+.*$", "", titulo, flags=re.I)
        site = (site or "").lower().strip()
        partes = [p.strip() for p in re.split(r"\s+[|]\s+|\s+[-–—]\s+(?=[^-–—]*$)", titulo) if p.strip()]
        if len(partes) > 1:
            site_junto = re.sub(r"[\W_]+", "", site)

            def eh_site(p):
                pl = p.lower()
                junto = re.sub(r"[\W_]+", "", pl)
                return bool(site) and (pl == site or pl in site or site in pl
                                       or (len(junto) >= 4 and (junto in site_junto or site_junto in junto))) or \
                    re.fullmatch(r"(?:www\.)?[\w-]+\.(?:com|net|ind|org)(?:\.br)?", pl) is not None
            restantes = [p for p in partes if not eh_site(p)]
            if restantes and len(restantes) < len(partes):
                titulo = " ".join(restantes)
            elif "|" in titulo:
                # "23200005 | Cabo CAT5E": codigo do produto na frente fica junto do nome.
                if len(partes) == 2 and re.fullmatch(r"[\w./-]*\d[\w./-]*", partes[0]):
                    titulo = " ".join(partes)
                else:
                    titulo = max(partes, key=len) if len(partes[0]) < 12 else partes[0]
        return titulo.strip(" -|")

    def escolher_titulo(self, soup, ld, meta, url):
        host = (urlparse(url).hostname or "").lower()
        rotulo = host.replace("www.", "").replace("loja.", "").split(".")[0]
        site = self.limpar_texto(meta("og:site_name")) or rotulo
        og_titulo = self.limpar_texto(meta("og:title"))
        if og_titulo and site and og_titulo.lower() == site.lower():
            og_titulo = ""  # og:title generico com o nome da loja ("Ferramentas Gedore")
        referencias = [self.limpar_texto(ld.get("name")), og_titulo,
                       self.limpar_texto(meta("twitter:title")),
                       self.limpar_texto(soup.title.get_text() if soup.title else "")]
        item = soup.find(attrs={"itemprop": "name"})
        if item and item.name != "meta":
            referencias.insert(1, self.limpar_texto(item.get_text(" ", strip=True)))
        referencias = [self.limpar_titulo(r, site) for r in referencias if r]
        referencias = [r for r in referencias if r and not any(x in r.lower() for x in TITULOS_INVALIDOS)]

        def palavras(t):
            return set(re.findall(r"\w{3,}", t.lower()))
        ref = palavras(" ".join(referencias[:2]))
        melhor, nota = "", -1.0
        for h1 in soup.find_all("h1"):
            texto = self.limpar_titulo(h1.get_text(" ", strip=True), site)
            if len(texto) < 4 or len(texto) > 250 or any(x in texto.lower() for x in TITULOS_INVALIDOS):
                continue
            p = palavras(texto)
            score = (len(p & ref) / max(len(p), 1)) if ref else 0.5
            if score > nota:
                melhor, nota = texto, score
        if melhor and (not ref or nota >= 0.3):
            return melhor
        return referencias[0] if referencias else melhor

    def descricao_html(self, soup):
        re_desc = re.compile(r"descri|description|sobre.o.produto|detalhes|product.attribute.description|"
                             r"product-info__content|tab-content|rte\b|informacoes", re.I)
        melhor_txt, melhor_bloco = "", None
        for bloco in soup.find_all(["div", "section", "article", "p"]):
            rotulo = marcador(bloco)
            if not re_desc.search(rotulo) or re.search(r"meta.?description|short|resumo", rotulo, re.I):
                continue
            if bloco.name == "p" and "description" not in rotulo:
                continue
            bruto = str(bloco)
            if len(bruto) > 400000:
                continue
            texto = self.limpar_descricao(bruto)
            if len(texto) > len(melhor_txt):
                melhor_txt, melhor_bloco = texto, bloco
        if len(melhor_txt) < 80:
            for bloco in self.blocos_por_titulo(soup, RE_TITULO_DESC):
                texto = self.limpar_descricao(str(bloco))
                if len(texto) > len(melhor_txt):
                    melhor_txt, melhor_bloco = texto, bloco
        return melhor_txt, melhor_bloco

    @staticmethod
    def raiz_arquivo(endereco):
        """Nome da foto sem tamanho/sufixo: 'x_251986' em /m/x_251986.jpg e /g/x_251986.jpg."""
        nome = os.path.basename(urlparse(endereco).path).lower()
        nome = re.sub(r"\.(?:jpe?g|png|webp|avif)$", "", nome)
        nome = re.sub(r"[-_](?:\d{2,4}x\d{2,4}|scaled|thumb|small|medium|large|grande|zoom)(?=$|[-_.])", "", nome)
        return re.sub(r"-\d$", "", nome)

    def versoes_grandes(self, endereco):
        """A mesma foto em tamanho original (Magento /cache/, WordPress -150x150, VTEX -500-500,
        Shopify _200x, ?width=265) antes da URL como veio."""
        p = urlparse(endereco)
        caminho = re.sub(r"/cache/(?:\d+/)?[0-9a-f]{32}/", "/", p.path)
        caminho = re.sub(r"-\d{2,4}x\d{2,4}(?=(?:-\d)?\.(?:jpe?g|png|webp)$)", "", caminho, flags=re.I)
        caminho = re.sub(r"(/arquivos/ids/\d+)-\d+-\d+", r"\1-1000-1000", caminho)
        caminho = re.sub(r"_(?:\d+x\d*|x\d+|small|medium|compact|thumb|pico)(?=\.(?:jpe?g|png|webp)$)", "",
                         caminho, flags=re.I)
        pares = parse_qsl(p.query, keep_blank_values=True)
        query = urlencode([(k, v) for k, v in pares if k.lower() not in PARAMS_TAMANHO])
        saida = []
        if caminho != p.path or query != urlencode(pares):
            saida.append(p._replace(path=caminho, query=query).geturl())
        return saida + [endereco]

    def imagens_pagina(self, soup, url, titulo, ld, meta):
        """Fotos candidatas, da mais provavel para a menos: JSON-LD/OG, galeria, alt parecido com o titulo,
        mesma foto da OG em tamanho maior. Cabecalho, rodape e vitrines de outros produtos perdem pontos."""
        notas, ordem = {}, []
        palavras_titulo = set(re.findall(r"\w{3,}", (titulo or "").lower()))

        def adicionar(endereco, nota):
            if not endereco or not isinstance(endereco, str):
                return
            endereco = endereco.strip().split(" ")[0]
            if not endereco or endereco.startswith(("data:", "blob:", "javascript:")):
                return
            if endereco.startswith("//"):
                endereco = "https:" + endereco
            endereco = urljoin(url, endereco)
            if urlparse(endereco).scheme not in ("http", "https") or RE_IMG_RUIM.search(endereco) \
                    or re.search(r"\.(?:svg|gif|ico)(?:[?#]|$)", endereco, re.I):
                return
            if RE_IMG_PEQUENA.search(endereco):
                nota -= 25
            if endereco not in notas:
                ordem.append(endereco)
                notas[endereco] = nota
            else:
                notas[endereco] = max(notas[endereco], nota)

        imagens_ld = ld.get("image")
        if not isinstance(imagens_ld, list):
            imagens_ld = [imagens_ld]
        for item in imagens_ld[:6]:
            if isinstance(item, dict):
                item = item.get("url") or item.get("contentUrl")
            adicionar(item if isinstance(item, str) else None, 60)
        principais = list(ordem)
        for nome in ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"):
            adicionar(meta(nome), 45)
        link = soup.find("link", rel="image_src")
        if link:
            adicionar(link.get("href"), 40)
        largura_og = re.sub(r"\D", "", meta("og:image:width") or "")
        if largura_og and int(largura_og[:5]) < 300:
            for endereco in ordem:
                notas[endereco] -= 30  # OG declarada como miniatura (ex.: 150x150)
        principais = [self.raiz_arquivo(x) for x in (principais or ordem)]
        principais = [r for r in principais if len(r) >= 4]
        for tag in soup.find_all(attrs={"itemprop": "image"}):
            adicionar(tag.get("content") or tag.get("src") or tag.get("href"), 40)

        ruido = re.compile(r"related|recommend|vitrine|shelf|similar|upsell|cross.?sell|compre.junto|buy.together"
                           r"|quem.viu|carousel-produtos|mini.?cart|(?<![a-z])menu\b|megamenu|banner", re.I)
        for n, img in enumerate(soup.find_all(["img", "source"], limit=400)):
            nota = 15 - n * 0.05
            pais = list(islice(img.parents, 7))
            if any(p.name in ("header", "nav", "footer", "aside") for p in pais):
                nota -= 50
            rotulos = " ".join([marcador(img)] + [marcador(p) for p in pais if p.attrs is not None])
            if ruido.search(rotulos):
                nota -= 35
            if RE_IMG_GALERIA.search(rotulos):
                nota += 20
            alt = set(re.findall(r"\w{3,}", (img.get("alt") or img.get("title") or "").lower()))
            comuns = alt & palavras_titulo
            if len(comuns) >= 2 and len(comuns) >= len(alt) * 0.5:
                nota += 30
            for medida in (img.get("width"), img.get("height")):
                medida = re.sub(r"\D", "", str(medida or ""))[:5]
                if medida and int(medida) < 150:
                    nota -= 30
            grandes = [img.get(a) for a in ("data-zoom-image", "data-large", "data-zoom", "data-full",
                                              "data-large_image", "data-original")]
            conjunto = img.get("srcset") or img.get("data-srcset") or ""
            maior = None
            if conjunto:
                opcoes = []
                for parte in conjunto.split(","):
                    pedacos = parte.strip().split()
                    if pedacos:
                        peso = re.sub(r"\D", "", pedacos[1]) if len(pedacos) > 1 else "1"
                        opcoes.append((int(peso[:6] or 1), pedacos[0]))
                maior = max(opcoes)[1] if opcoes else None
            pai_link = img.find_parent("a")
            href = pai_link.get("href") if pai_link else None
            if href and not re.search(r"\.(?:jpe?g|png|webp)(?:[?#]|$)", href, re.I):
                href = None
            fontes = [(x, nota + 25) for x in grandes + [href]] + [(maior, nota + 5)] + [
                (img.get(a), nota) for a in ("data-src", "data-lazy-src", "data-lazy", "src")]
            for endereco, valor in fontes:
                if endereco and isinstance(endereco, str):
                    raiz = self.raiz_arquivo(urljoin(url, endereco.strip().split(" ")[0]))
                    if raiz and raiz in principais:
                        valor += 50  # mesma foto da OG/JSON-LD, provavelmente maior
                    adicionar(endereco, valor)
        return sorted(ordem, key=lambda e: (-notas[e], ordem.index(e)))

    def linhas_principais(self, soup, titulo):
        """Linhas do conteudo principal: do h1 do produto ate o fim do container dele."""
        palavras = set(re.findall(r"\w{3,}", (titulo or "").lower()))
        h1 = None
        for candidato in soup.find_all(["h1", "h2"], limit=30):
            texto = set(re.findall(r"\w{3,}", candidato.get_text(" ", strip=True).lower()))
            if texto and palavras and len(texto & palavras) >= max(1, len(texto) * 0.5):
                h1 = candidato
                break
        if h1 is None:
            h1 = soup.find("h1")
        if h1 is None:
            return []
        atual, bloco = h1, None
        while atual.parent is not None and atual.parent.name not in ("[document]", "html"):
            pai = atual.parent
            tamanho = len(pai.get_text(" ", strip=True))
            if tamanho >= 600:
                bloco = pai if tamanho <= 40000 else None
                break
            atual = pai
        if bloco is None:
            # Container grande demais (ou o body): so o que vem depois do titulo.
            partes, total = [], 0
            for irmao in atual.find_next_siblings():
                pedaco = str(irmao)
                partes.append(pedaco)
                total += len(pedaco)
                if total > 150000:
                    break
            bloco = BeautifulSoup("<div>%s%s</div>" % (str(atual), "".join(partes)), "html.parser").div
        linhas = self.linhas_html(str(bloco))
        alvo = self.limpar_texto(h1.get_text(" ", strip=True))
        inicio = next((i for i, l in enumerate(linhas) if alvo and l == alvo), -1)
        saida = []
        for linha in linhas[inicio + 1:][:400]:
            if RE_FIM_CONTEUDO.match(linha):
                break  # dali para baixo e vitrine de outros produtos / rodape
            if RE_LINHA_LOJA.search(linha):
                continue
            # Cartao de outro produto (ou o proprio titulo repetido): quase so palavras do titulo.
            ws = set(re.findall(r"\w{3,}", linha.lower()))
            if ":" not in linha and len(ws & palavras) >= 4 and len(ws & palavras) >= len(ws) * 0.5:
                continue
            saida.append(linha)
        return saida

    def extrair_html(self, html, url):
        soup = BeautifulSoup(html or "", "html.parser")
        ld = self.produto_jsonld(soup)

        def meta(nome):
            tag = soup.find("meta", property=nome) or soup.find("meta", attrs={"name": nome})
            return tag.get("content", "") if tag else ""
        meta_desc = meta("og:description") or meta("description")
        for form in soup.find_all("form"):
            form.unwrap()  # muitas lojas colocam toda a ficha dentro do form de compra
        titulo = self.escolher_titulo(soup, ld, meta, url)
        imagens = self.imagens_pagina(soup, url, titulo, ld, meta)
        self._candidatos_imagem = list(getattr(self, "_candidatos_imagem", None) or []) + imagens
        for botao in soup.find_all(["button", "summary"]):
            # Cabecalho de aba/acordeao ("Ficha tecnica", "Descricao") vira texto; o resto sai.
            texto = botao.get_text(" ", strip=True)
            if texto and len(texto) <= 45 and (RE_TITULO_SPEC.match(texto) or RE_TITULO_DESC.match(texto)):
                botao.name = "h3"
                botao.attrs = {}
        for tag in soup.find_all(["nav", "header", "footer", "aside", "script", "style", "button",
                                  "input", "select", "noscript", "svg", "iframe"]):
            tag.decompose()
        for tag in soup.find_all(True):
            if tag.attrs is None:
                continue
            if re.search(r"cookie|related|recommend|avaliac|review|frete|shipping|installment|breadcrumb|"
                         r"newsletter|parcel|vitrine|shelf|carousel-produtos|compre.junto|buy.together|"
                         r"quem.viu|similar|upsell|cross.?sell|popup|(?<![a-z])menu\b|megamenu", marcador(tag), re.I):
                if tag.find("h1") is None:  # nunca derruba o container principal do produto
                    tag.decompose()
        specs = {}
        for origem, rotulo in (("sku", "SKU"), ("mpn", "Modelo"), ("model", "Modelo")):
            valor = ld.get(origem)
            if isinstance(valor, dict):
                valor = valor.get("name")
            if valor and not isinstance(valor, list):
                self.adicionar_spec(specs, rotulo, valor)
        for k, v in ld.items():
            if k.lower().startswith("gtin") and not isinstance(v, (dict, list)):
                self.adicionar_spec(specs, k.upper(), v)
        marca = ld.get("brand")
        if isinstance(marca, list):
            marca = marca[0] if marca else ""
        if isinstance(marca, dict):
            marca = marca.get("name")
        if marca:
            self.adicionar_spec(specs, "Marca", marca)
        for chave_ld, rotulo in (("color", "Cor"), ("material", "Material"), ("weight", "Peso"),
                                 ("width", "Largura"), ("height", "Altura"), ("depth", "Profundidade")):
            valor = ld.get(chave_ld)
            if isinstance(valor, dict):
                valor = " ".join(str(valor.get(x, "")) for x in ("value", "unitText", "unitCode")).strip()
            if valor and not isinstance(valor, list):
                self.adicionar_spec(specs, rotulo, valor)
        propriedades = ld.get("additionalProperty") or []
        if isinstance(propriedades, dict):
            propriedades = [propriedades]
        for prop in propriedades:
            if isinstance(prop, dict):
                self.adicionar_spec(specs, prop.get("name"), prop.get("value"))
        self.specs_html(soup, specs)
        for tag in soup.find_all(attrs={"itemprop": True}):
            prop = tag.get("itemprop")
            if prop in ("brand", "sku", "mpn"):
                rotulo = {"brand": "Marca", "sku": "SKU", "mpn": "Modelo"}[prop]
                self.adicionar_spec(specs, rotulo, tag.get("content") or tag.get_text(" ", strip=True))
        descricao, bloco_desc = self.descricao_html(soup)
        if bloco_desc is not None:
            self.specs_texto(self.linhas_html(str(bloco_desc)), specs)
        desc_ld = self.limpar_descricao(ld.get("description"))
        if desc_ld:
            self.specs_texto(self.linhas_html(str(ld.get("description"))), specs)
        if len(descricao) < 150 or len(specs) < 3:
            # Site sem bloco marcado de descricao/ficha: usa o texto que vem depois do h1.
            linhas = self.linhas_principais(soup, titulo)
            if linhas:
                if len(specs) < 3:
                    self.specs_texto(linhas, specs)
                if len(descricao) < 150:
                    # Frase de verdade (4+ palavras) ou "Chave: valor"; sobra de botao/rotulo fica fora.
                    frases = [l for l in linhas if len(l.split()) >= 4 or re.match(r"^[^:]{2,40}:\s*\S", l)]
                    texto = self.limpar_descricao("".join("<p>%s</p>" % html_lib.escape(l) for l in frases))
                    if len(texto) > len(descricao) + (100 if len(descricao) >= 80 else 0):
                        descricao = texto
        if len(descricao) < 80:
            descricao = max((descricao, desc_ld, self.limpar_descricao(meta_desc)), key=len)
        imagem = imagens[0] if imagens else ""
        fonte = "json-ld" if ld and (ld.get("name") or ld.get("description")) else "html"
        # Linha "Nome do produto: SKU 123" da descricao nao e especificacao.
        # Chave com o nome da loja ("Conheca o clube Angeloni") tambem nao.
        loja = (urlparse(url).hostname or "").lower().replace("www.", "").replace("loja.", "").split(".")[0]
        specs = {k: v for k, v in specs.items() if not (len(k) > 25 and titulo and k.lower() in titulo.lower())
                 and not (len(loja) >= 4 and loja in k.lower())}
        return titulo, descricao, specs, imagem, fonte

    def plataforma(self, html, url):
        caminho = urlparse(url).path
        h = (html or "").lower()
        if caminho.rstrip("/").endswith("/p") or "vteximg" in h or "vtex" in h:
            return "vtex"
        if "cdn.shopify.com" in h or "shopify.theme" in h:
            return "shopify"
        return "html"

    def produto_vtex(self, url, session):
        """Busca o produto na API publica de catalogo VTEX (slug do /p ou skuId da URL)."""
        p = urlparse(url)
        origem = "%s://%s" % (p.scheme, p.netloc)
        partes = [x for x in p.path.split("/") if x]
        consultas = []
        if len(partes) >= 2 and partes[-1] == "p":
            consultas.append("/api/catalog_system/pub/products/search/" + quote(partes[-2]) + "/p")
        query = parse_qs(p.query)
        sku = (query.get("skuId") or query.get("idsku") or query.get("skuid") or [""])[0]
        if sku.isdigit():
            consultas.append("/api/catalog_system/pub/products/search?fq=skuId:" + sku)
        for consulta in consultas:
            resposta = self.pedir(origem + consulta, session)
            produtos = resposta.json()
            if isinstance(produtos, list) and produtos:
                return produtos[0]
        return None

    def produto_vtex_io(self, html, url):
        """VTEX IO renderiza o produto no HTML (template __STATE__, cache Apollo normalizado).
        Serve quando a API publica de catalogo esta fechada (ex.: Angeloni devolve 404)."""
        achado = re.search(r'data-varname="__STATE__"[^>]*>\s*<script>(.*?)</script>', html or "", re.S)
        if not achado:
            return None
        try:
            estado = json.loads(achado.group(1))
        except ValueError:
            return None
        if not isinstance(estado, dict):
            return None

        def resolver(valor):
            if isinstance(valor, dict) and valor.get("type") == "id" and valor.get("id") in estado:
                return estado[valor["id"]]
            if isinstance(valor, dict) and valor.get("type") == "json":
                return valor.get("json")
            return valor
        raizes = [k for k, v in estado.items() if k.startswith("Product:") and "." not in k[8:]
                  and isinstance(v, dict) and v.get("productName")]
        if not raizes:
            return None
        partes = [x for x in urlparse(url).path.split("/") if x]
        slug = partes[-2] if len(partes) >= 2 and partes[-1] == "p" else ""
        chave = next((k for k in raizes if slug and estado[k].get("linkText") == slug), raizes[0])
        p = estado[chave]
        specs = {}
        grupos = [resolver(g) for g in p.get("specificationGroups") or []]
        grupos = [g for g in grupos if isinstance(g, dict)]
        # "allSpecifications" repete os outros grupos; so serve se for o unico.
        uteis = [g for g in grupos if g.get("name") != "allSpecifications"] or grupos
        props = [resolver(s) for g in uteis for s in (g.get("specifications") or [])]
        if not props:
            props = [resolver(x) for x in p.get("properties") or []]
        for prop in props:
            if not isinstance(prop, dict):
                continue
            valores = resolver(prop.get("values")) or []
            if isinstance(valores, str):
                valores = [valores]
            texto = ", ".join(str(v) for v in valores if v not in (None, ""))
            if "\n" in texto or "<" in texto:
                self.specs_texto(self.linhas_html(texto), specs)
            else:
                self.adicionar_spec(specs, prop.get("name"), texto)
        if p.get("brand"):
            self.adicionar_spec(specs, "Marca", p["brand"])
        imagem = ""
        itens = [resolver(i) for i in p.get("items") or []]
        itens = [i for i in itens if isinstance(i, dict)]
        if itens:
            item = itens[0]
            if item.get("ean"):
                self.adicionar_spec(specs, "EAN", item["ean"])
            fotos = [resolver(f) for f in item.get("images") or []]
            imagem = next((f.get("imageUrl") for f in fotos if isinstance(f, dict) and f.get("imageUrl")), "")
        if p.get("productReference"):
            self.adicionar_spec(specs, "Referência", p["productReference"])
        desc = p.get("description") or p.get("metaTagDescription") or ""
        self.specs_texto(self.linhas_html(desc), specs)
        return p.get("productName", ""), self.limpar_descricao(desc), specs, imagem, "vtex-state"

    def extrair_api(self, html, url, session):
        tipo = self.plataforma(html, url)
        origem = "%s://%s" % (urlparse(url).scheme, urlparse(url).netloc)
        if tipo == "vtex":
            estado = None
            try:
                estado = self.produto_vtex_io(html, url)
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                print("   [Universal] Estado VTEX IO ilegivel: " + type(e).__name__)
            dados = self.extrair_vtex_api(url, session)
            if dados and estado:
                return self.juntar(dados, estado)
            return dados or estado
        if tipo == "shopify":
            return self.extrair_shopify(origem, url, session)
        return None

    def extrair_vtex_api(self, url, session):
        try:
            p = self.produto_vtex(url, session)
            if not p:
                return None
            specs = {}
            for k in p.get("allSpecifications") or []:
                valores = p.get(k) or []
                if any("\n" in str(v) for v in valores):
                    grupo = ""
                    for valor in valores:
                        for linha in str(valor).splitlines():
                            linha = self.limpar_texto(linha)
                            if ":" not in linha:
                                continue
                            chave, detalhe = linha.split(":", 1)
                            if not detalhe:
                                grupo = chave if chave.lower() in ("medidas", "dimensões", "dimensoes") else ""
                                continue
                            self.adicionar_spec(specs, (grupo + " - " if grupo else "") + chave, detalhe)
                else:
                    self.adicionar_spec(specs, k, ", ".join(str(v) for v in valores))
            if p.get("brand"):
                self.adicionar_spec(specs, "Marca", p["brand"])
            itens = p.get("items") or []
            if itens:
                if itens[0].get("ean"):
                    self.adicionar_spec(specs, "EAN", itens[0]["ean"])
                ref = next((r.get("Value") for r in itens[0].get("referenceId") or [] if r.get("Value")), "")
                if ref or p.get("productReference"):
                    self.adicionar_spec(specs, "Referência", ref or p.get("productReference"))
            fotos = (itens[0].get("images") or []) if itens else []
            imagem = fotos[0].get("imageUrl", "") if fotos else ""
            desc_html = p.get("description", "")
            grupo = ""
            for linha in self.texto_html(desc_html).split("\n"):
                linha = self.limpar_texto(linha).lstrip("-• ")
                if linha.isupper() and len(linha) < 45:
                    grupo = linha.title()
                elif ":" in linha:
                    k, v = linha.split(":", 1)
                    if len(k) < 45 and len(v) > 1:
                        self.adicionar_spec(specs, (grupo + " - " if grupo else "") + k, v)
            return (p.get("productName", ""), self.limpar_descricao(desc_html),
                    specs, imagem, "vtex-api")
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as e:
            print("   [Universal] API VTEX indisponivel: " + type(e).__name__)
        return None

    def extrair_shopify(self, origem, url, session):
        api = origem + urlparse(url).path.rstrip("/") + ".js"
        try:
            p = self.pedir(api, session).json()
            if not isinstance(p, dict) or not p.get("title"):
                return None
            specs = {}
            variantes = p.get("variants") or []
            if variantes and variantes[0].get("sku"):
                self.adicionar_spec(specs, "SKU", variantes[0]["sku"])
            if variantes and variantes[0].get("barcode"):
                self.adicionar_spec(specs, "EAN", variantes[0]["barcode"])
            if p.get("vendor"):
                self.adicionar_spec(specs, "Marca", p["vendor"])
            self.specs_texto(self.linhas_html(p.get("description", "")), specs)
            fotos = p.get("images") or []
            imagem = fotos[0].get("src") if fotos and isinstance(fotos[0], dict) else (fotos[0] if fotos else "")
            if imagem and str(imagem).startswith("//"):
                imagem = "https:" + imagem
            return p["title"], self.limpar_descricao(p.get("description", "")), specs, imagem, "html"
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as e:
            print("   [Universal] API Shopify indisponivel: " + type(e).__name__)
        return None

    def abrir_imagem(self, endereco, session):
        res = self.pedir(endereco, session, timeout=15)
        tipo = (res.headers.get("Content-Type") or "").lower() if hasattr(res, "headers") else ""
        if res.status_code != 200 or len(res.content) > 12000000 or "html" in tipo:
            raise ValueError("HTTP %s, %s bytes, %s" % (res.status_code, len(res.content), tipo or "sem tipo"))
        img = Image.open(BytesIO(res.content))
        img.load()
        return img.convert("RGBA")

    def baixar_imagem(self, url, session, candidatos=None, limite=8):
        """Baixa a melhor foto: tenta a URL principal e as candidatas (versao grande primeiro).
        Foto boa = lado menor >= 300px. Sem nenhuma boa, fica a maior aceitavel (>= 250x150) em vez de nada."""
        mod_id = identificar_modulo_scraper(scraper=self)
        if getattr(self, "_foto_navegador", None):
            return self._foto_navegador
        if candidatos is None:
            candidatos = getattr(self, "_candidatos_imagem", None) or []
        lista = [x for x in [url] + list(candidatos) if x]
        if not lista:
            registrar_erro_modulo(mod_id, "Nenhuma URL de imagem encontrada na página do produto.", url=self.url)
            return None
        vistos, falhas, reserva, tentativas = set(), [], None, 0
        for candidato in lista:
            for endereco in self.versoes_grandes(candidato):
                if endereco in vistos or tentativas >= limite:
                    continue
                vistos.add(endereco)
                tentativas += 1
                try:
                    img = self.abrir_imagem(endereco, session)
                except (requests.RequestException, ValueError, OSError) as e:
                    falhas.append("%s (%s)" % (endereco, type(e).__name__))
                    continue
                largura, altura = img.size
                menor, maior = min(largura, altura), max(largura, altura)
                if menor and maior / menor <= 3 and menor >= 300:
                    return self.salvar_imagem(img)
                if menor >= 150 and maior >= 250 and maior / menor <= 3:
                    if reserva is None or largura * altura > reserva[0]:
                        reserva = (largura * altura, img)
                falhas.append("%s (%sx%spx)" % (endereco, largura, altura))
                break  # abriu e e pequena: as outras versoes desta foto nao serao maiores
            if tentativas >= limite:
                break
        if reserva:
            return self.salvar_imagem(reserva[1])
        print("   [Universal] Imagem indisponivel: %s tentativas" % len(falhas))
        registrar_erro_modulo(
            mod_id,
            "Nenhuma imagem do produto aproveitável (precisa de pelo menos 300x300px). Tentativas: " + "; ".join(falhas[:6]),
            url=self.url,
        )
        return None

    def salvar_imagem(self, img):
        fundo = Image.new("RGB", img.size, "white")
        fundo.paste(img, mask=img.getchannel("A"))
        caminho = os.path.join(self.output_folder, "universal_img_%s.jpg" % time.time_ns())
        fundo.save(caminho, "JPEG", quality=90)
        return caminho

    def pontuar(self, dados):
        titulo, descricao, specs, imagem, _ = dados
        return (600 if titulo else 0) + min(len(descricao or ""), 1500) + 60 * min(len(specs), 30) + (200 if imagem else 0)

    def juntar(self, principal, extra):
        """Completa o resultado principal com o que so o outro achou."""
        t, d, s, i, f = principal
        t2, d2, s2, i2, _ = extra
        s = dict(s)
        for k, v in s2.items():
            if not any(k.lower() == x.lower() for x in s):
                self.adicionar_spec(s, k, v)
        if len(d or "") < 80 and len(d2 or "") > len(d or ""):
            d = d2
        return t or t2, d, s, i or i2, f

    def executar(self):
        mod_id = identificar_modulo_scraper(scraper=self)
        dominio = urlparse(self.url).hostname or "url-invalida"
        html, imagem_temp = "", None
        self._candidatos_imagem = []
        try:
            self.validar_url(self.url)
            if not self.output_folder:
                raise ValueError("Pasta de saida indefinida")
            os.makedirs(self.output_folder, exist_ok=True)
            with requests.Session() as session:
                try:
                    resposta = self.pedir(self.url, session)
                    html, url, status = resposta.text, resposta.url, resposta.status_code
                except requests.RequestException as e:
                    print("   [Universal] Requisicao falhou: " + type(e).__name__)
                    url, status = self.url, 503
                dados = self.extrair_api(html, url, session)
                veio_api = bool(dados)
                if status == 404 and not veio_api:
                    raise ValueError("Pagina HTTP 404")
                if not dados:
                    dados = self.extrair_html(html, url)
                else:
                    dados = self.juntar(dados, self.extrair_html(html, url))
                titulo, descricao, specs, imagem, fonte = dados
                conteudo_ok = len(descricao) >= 80 or len(specs) >= 3
                bloqueio = self.bloqueada(html, status) and not veio_api
                if bloqueio or not titulo or not conteudo_ok:
                    try:
                        print("   [Universal] Tentando Chrome")
                        html_chrome, url_chrome = self.navegar(url)
                        dados_chrome = self.extrair_html(html_chrome, url_chrome)
                        if not self.bloqueada(html_chrome):
                            if bloqueio or self.pontuar(dados_chrome) > self.pontuar(dados):
                                principal, extra = dados_chrome, dados
                                html, url = html_chrome, url_chrome
                                fonte_final = "selenium"
                            else:
                                principal, extra, fonte_final = dados, dados_chrome, fonte
                            if bloqueio:
                                dados = principal
                            else:
                                dados = self.juntar(principal, extra)
                            titulo, descricao, specs, imagem, _ = dados
                            fonte = fonte_final
                            bloqueio = False
                    except Exception as e:
                        print("   [Universal] Chrome indisponivel: " + type(e).__name__)
                if bloqueio:
                    raise ValueError("Pagina bloqueada ou desafio anti-bot")
                titulo = self.normalizar(self.limpar_texto(titulo))
                if not titulo or any(x in titulo.lower() for x in TITULOS_INVALIDOS):
                    registrar_erro_modulo(mod_id, f"Item veio SEM TÍTULO ou com título inválido ('{titulo}').", url=self.url)
                    raise ValueError("Titulo de produto ausente ou invalido")
                specs = self.filtrar_specs(specs)
                if len(descricao) < 80 and len(specs) < 3:
                    if not descricao or not str(descricao).strip():
                        registrar_erro_modulo(mod_id, "Item veio SEM DESCRIÇÃO (descrição vazia na página).", url=self.url, titulo=titulo)
                    else:
                        registrar_erro_modulo(mod_id, f"Item veio com descrição muito curta ({len(descricao)} caracteres).", url=self.url, titulo=titulo)
                    registrar_erro_modulo(mod_id, f"Item veio com ficha técnica insuficiente ({len(specs)} especificações).", url=self.url, titulo=titulo)
                    raise ValueError("Descricao curta e menos de 3 especificacoes")
                if not veio_api and not self.produto_jsonld(BeautifulSoup(html, "html.parser")):
                    sinais = re.search(r"add.to.cart|addtocart|itemprop=['\"]price|product:price|woocommerce-product|"
                                       r"og:type['\"]\s+content=['\"]product|schema.org/Product|"
                                       r"ficha.t[eé]cnica|especifica[cç][õo]es.t[eé]cnicas|adicionar.ao.carrinho|"
                                       r"comprar.agora|solicitar.or[cç]amento", html, re.I)
                    if not sinais and len(specs) < 3:
                        raise ValueError("Pagina sem sinais suficientes de produto")
                # Subclasses sobrescrevem baixar_imagem(url, session); as candidatas vao pelo atributo.
                candidatos = self._candidatos_imagem
                imagem_temp = None
                if imagem or candidatos:
                    imagem_temp = self.baixar_imagem(urljoin(url, imagem) if imagem else "", session)
                if not imagem and not candidatos:
                    registrar_erro_modulo(mod_id, "Item veio SEM IMAGEM (nenhuma imagem encontrada no HTML/JSON-LD da página).", url=self.url, titulo=titulo)
                if self.exigir_imagem and not imagem_temp:
                    raise ValueError("Imagem do produto indisponivel")
                dados = {"titulo": titulo, "descricao": self.normalizar(descricao),
                         "caracteristicas": specs, "caminho_imagem_temp": imagem_temp}
                arquivos = self.gerar_arquivos_finais(dados)
                if not all(os.path.exists(arquivos[k]) for k in ("full_path_word", "full_path_pdf")):
                    raise ValueError("Falha ao gerar Word ou PDF")
                print("   [%s] Fonte: %s; specs: %s" % (self.ADAPTER, fonte, len(specs)))
                return {"sucesso": True, "titulo": titulo, "descricao": dados["descricao"],
                        "caracteristicas": specs, "total_imagens": int(bool(imagem_temp)),
                        "arquivos": arquivos, "adapter": self.ADAPTER, "fonte": fonte}
        except Exception as e:
            self.guardar_falha(html, dominio)
            mensagem = self.normalizar(str(e))
            print("   [Universal] Erro: " + mensagem)
            registrar_erro_modulo(mod_id, f"{mensagem} (domínio: {dominio})", url=self.url)
            return {"sucesso": False, "erro": "Universal: %s (%s)" % (mensagem, dominio)}
