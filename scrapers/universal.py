import ipaddress
import json
import os
import re
import socket
import threading
import time
from io import BytesIO
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image

from .base import BaseScraper


CHROME_VAGAS = threading.Semaphore(1)
BLOQUEIOS = ("cf-chl", "just a moment", "access denied", "acesso negado",
             "sec-if-cpt-container", "powered and protected by",
             "checking your browser", "verifique se voce e humano")
TITULOS_INVALIDOS = ("404", "nao encontrada", "não encontrada", "not found",
                    "access denied", "just a moment", "login", "entrar na conta",
                    "pagina inicial", "página inicial")
LIXO_SPEC = ("preço", "preco", "frete", "parcelamento", "estoque")
MAPA_PDF = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                         "–": "-", "—": "-", "™": "TM", "®": "(R)",
                         "€": "EUR", "•": "-", "…": "...", "\xa0": " "})


class UniversalScraper(BaseScraper):
    ADAPTER = "UNIVERSAL"
    exigir_imagem = False
    imagem_css = None
    espera_css = None
    def normalizar(self, texto):
        texto = str(texto or "").translate(MAPA_PDF)
        return texto.encode("latin-1", "ignore").decode("latin-1")

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

    def pedir(self, url, session=None):
        session = session or requests.Session()
        atual = url
        headers = dict(self.headers, **{"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7"})
        for _ in range(6):
            self.validar_url(atual)
            resposta = session.get(atual, headers=headers, timeout=30, allow_redirects=False)
            if resposta.is_redirect:
                destino = resposta.headers.get("Location")
                if not destino:
                    raise ValueError("Redirect sem destino")
                atual = urljoin(atual, destino)
                self.validar_url(atual)
                continue
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
        h = (html or "").lower()
        return status in (403, 429, 503) or any(x in h for x in BLOQUEIOS)

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
                driver = uc.Chrome(options=options, version_main=109)
                driver.set_page_load_timeout(40)
                try:
                    driver.get(url)
                except Exception as e:
                    print("   [Universal] Navegacao lenta: " + type(e).__name__)
                self.validar_url(driver.current_url)
                if self.espera_css:
                    for _ in range(15):
                        if driver.execute_script("return !!document.querySelector(arguments[0])", self.espera_css):
                            break
                        time.sleep(1)
                for posicao in (0, 900, 1800):
                    driver.execute_script("window.scrollTo(0, arguments[0]);", posicao)
                    time.sleep(1)
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
                    driver.quit()
        finally:
            CHROME_VAGAS.release()

    def produto_jsonld(self, soup):
        def visitar(obj):
            if isinstance(obj, list):
                for item in obj:
                    achado = visitar(item)
                    if achado:
                        return achado
            elif isinstance(obj, dict):
                tipos = obj.get("@type") or []
                if isinstance(tipos, str):
                    tipos = [tipos]
                if any(str(t).lower().endswith("product") for t in tipos):
                    return obj
                for chave in ("@graph", "mainEntity", "itemListElement"):
                    achado = visitar(obj.get(chave))
                    if achado:
                        return achado
            return None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                produto = visitar(json.loads(script.string or script.get_text()))
                if produto:
                    return produto
            except (ValueError, TypeError):
                continue
        return {}

    def texto_html(self, html):
        if not html:
            return ""
        soup = BeautifulSoup(str(html), "html.parser")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        return soup.get_text("\n", strip=True)

    def limpar_descricao(self, texto):
        frases = re.split(r"(?<=[.!?])\s+|\n+", self.texto_html(texto))
        partes = []
        for frase in frases:
            frase = self.limpar_texto(frase)
            if len(frase) < 15:
                continue
            limpo = self.limpar_lixo_comercial(frase)
            if limpo not in ("Descrição não disponível.", "Informações técnicas não detalhadas."):
                partes.append(limpo)
        return self.normalizar("\n".join(partes)[:9000])

    def adicionar_spec(self, specs, chave, valor):
        chave = self.normalizar(self.limpar_texto(chave))
        valor = self.normalizar(self.limpar_texto(valor))
        if not chave or len(chave) > 60 or not valor or len(valor) > 600:
            return
        if valor.lower() in ("n/a", "n/t", "-", "não informado", "nao informado"):
            return
        if any(p in chave.lower() for p in LIXO_SPEC):
            return
        anterior = next((k for k in specs if k.lower() == chave.lower()), None)
        if anterior:
            if valor not in specs[anterior].split(" / "):
                specs[anterior] += " / " + valor
        else:
            specs[chave] = valor

    def specs_html(self, soup, specs):
        for tabela in soup.find_all("table"):
            for linha in tabela.find_all("tr"):
                celulas = linha.find_all(["th", "td"], recursive=False)
                if len(celulas) == 2:
                    self.adicionar_spec(specs, celulas[0].get_text(" ", strip=True),
                                       celulas[1].get_text(" ", strip=True))
        for dl in soup.find_all("dl"):
            for dt in dl.find_all("dt"):
                dd = dt.find_next_sibling("dd")
                if dd:
                    self.adicionar_spec(specs, dt.get_text(" ", strip=True),
                                       dd.get_text(" ", strip=True))
        for esq in soup.select("div.esq"):
            direita = esq.find_next_sibling("div", class_="dir")
            if direita:
                self.adicionar_spec(specs, esq.get_text(" ", strip=True),
                                   direita.get_text(" ", strip=True))
        for bloco in soup.find_all(["div", "section", "ul"]):
            marcador = " ".join(bloco.get("class", [])) + " " + (bloco.get("id") or "")
            if not re.search(r"especific|ficha|caracter|tecnic|specs|attributes|product-details", marcador, re.I):
                continue
            grupo = bloco.find(["h2", "h3", "h4"])
            prefixo = self.limpar_texto(grupo.get_text()) if grupo else ""
            for li in bloco.find_all("li"):
                txt = self.limpar_texto(li.get_text(" ", strip=True))
                if ":" in txt:
                    k, v = txt.split(":", 1)
                    self.adicionar_spec(specs, (prefixo + " - " if prefixo else "") + k, v)

    def extrair_html(self, html, url):
        soup = BeautifulSoup(html or "", "html.parser")
        ld = self.produto_jsonld(soup)
        def meta(nome):
            tag = soup.find("meta", property=nome) or soup.find("meta", attrs={"name": nome})
            return tag.get("content", "") if tag else ""
        fotos_pagina = [(img.get("data-zoom-image"), img.get("data-large"),
                         img.get("data-src"), img.get("src")) for img in soup.find_all("img")]
        for form in soup.find_all("form"):
            form.unwrap()  # muitas lojas colocam toda a ficha dentro do form de compra
        for tag in soup.find_all(["nav", "header", "footer", "aside", "script", "style", "button", "input"]):
            tag.decompose()
        for tag in soup.find_all(True):
            if tag.attrs is None:
                continue
            marcador = " ".join(tag.get("class", [])) + " " + (tag.get("id") or "")
            if re.search(r"cookie|related|recommend|avaliac|review|frete|shipping|installment", marcador, re.I):
                tag.decompose()
        titulo = ""
        h1 = soup.find("h1")
        if h1:
            titulo = self.limpar_texto(h1.get_text(" ", strip=True))
        titulo = titulo or self.limpar_texto(ld.get("name")) or self.limpar_texto(meta("og:title"))
        titulo = re.split(r"\s+\|\s+", titulo)[0].strip()
        specs = {}
        for origem, rotulo in (("sku", "SKU"), ("mpn", "Modelo")):
            if ld.get(origem):
                self.adicionar_spec(specs, rotulo, ld[origem])
        for k, v in ld.items():
            if k.lower().startswith("gtin"):
                self.adicionar_spec(specs, k.upper(), v)
        marca = ld.get("brand")
        if isinstance(marca, dict):
            marca = marca.get("name")
        if marca:
            self.adicionar_spec(specs, "Marca", marca)
        for prop in ld.get("additionalProperty") or []:
            if isinstance(prop, dict):
                self.adicionar_spec(specs, prop.get("name"), prop.get("value"))
        self.specs_html(soup, specs)
        item = soup.find(attrs={"itemprop": "name"})
        titulo = titulo or (self.limpar_texto(item.get_text()) if item else "")
        for tag in soup.find_all(attrs={"itemprop": True}):
            prop = tag.get("itemprop")
            if prop in ("brand", "sku", "mpn"):
                self.adicionar_spec(specs, prop.upper(), tag.get("content") or tag.get_text())
        descricao = ""
        for bloco in soup.find_all(["div", "section", "article"]):
            marcador = " ".join(bloco.get("class", [])) + " " + (bloco.get("id") or "")
            if re.search(r"descri|description|sobre.o.produto|detalhes|product.attribute.description", marcador, re.I):
                texto = self.limpar_descricao(str(bloco))
                if len(texto) > len(descricao):
                    descricao = texto
        descricao = descricao or self.limpar_descricao(ld.get("description"))
        descricao = descricao or self.limpar_descricao(meta("og:description") or meta("description"))
        imagem = ld.get("image")
        if isinstance(imagem, list):
            imagem = imagem[0] if imagem else ""
        if isinstance(imagem, dict):
            imagem = imagem.get("url") or imagem.get("contentUrl")
        candidatos = [imagem, meta("og:image")]
        grandes = []
        for foto in fotos_pagina:
            grandes += list(foto[:2])
            candidatos += list(foto[2:])
        # Miniaturas de JSON-LD/OG perdem para a imagem ampliada da galeria.
        pequenos = r"small_image|thumbnail|/255x/|/small/"
        candidatos = [c for c in candidatos[:2] if c and not re.search(pequenos, str(c), re.I)] + grandes + candidatos
        imagem = next((urljoin(url, str(i)) for i in candidatos if i and not str(i).startswith("data:")
                       and not re.search(r"logo|icon|sprite|banner|marketplace", str(i), re.I)), "")
        fonte = "json-ld" if ld and (ld.get("name") or ld.get("description")) else "html"
        return titulo, descricao, specs, imagem, fonte

    def plataforma(self, html, url):
        caminho = urlparse(url).path
        h = (html or "").lower()
        if caminho.rstrip("/").endswith("/p") or "vteximg" in h or "vtex" in h:
            return "vtex"
        if "cdn.shopify.com" in h or "shopify.theme" in h:
            return "shopify"
        return "html"

    def extrair_api(self, html, url, session):
        tipo = self.plataforma(html, url)
        origem = "%s://%s" % (urlparse(url).scheme, urlparse(url).netloc)
        if tipo == "vtex":
            slug = urlparse(url).path.strip("/").removesuffix("/p")
            if "/" in slug or not slug:
                return None
            api = origem + "/api/catalog_system/pub/products/search/" + slug + "/p"
            try:
                resposta = self.pedir(api, session)
                produtos = resposta.json()
                if not isinstance(produtos, list) or not produtos:
                    return None
                p = produtos[0]
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
                itens = p.get("items") or []
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
            except (requests.RequestException, ValueError, KeyError, TypeError) as e:
                print("   [Universal] API VTEX indisponivel: " + type(e).__name__)
        if tipo == "shopify":
            api = origem + urlparse(url).path.rstrip("/") + ".js"
            try:
                p = self.pedir(api, session).json()
                if not isinstance(p, dict) or not p.get("title"):
                    return None
                specs = {}
                variantes = p.get("variants") or []
                if variantes and variantes[0].get("sku"):
                    self.adicionar_spec(specs, "SKU", variantes[0]["sku"])
                fotos = p.get("images") or []
                imagem = fotos[0].get("src") if fotos and isinstance(fotos[0], dict) else (fotos[0] if fotos else "")
                return p["title"], self.limpar_descricao(p.get("description", "")), specs, imagem, "html"
            except (requests.RequestException, ValueError, KeyError, TypeError) as e:
                print("   [Universal] API Shopify indisponivel: " + type(e).__name__)
        return None

    def baixar_imagem(self, url, session):
        if getattr(self, "_foto_navegador", None):
            return self._foto_navegador
        if not url:
            return None
        try:
            res = self.pedir(url, session)
            if res.status_code != 200 or len(res.content) > 12000000:
                return None
            img = Image.open(BytesIO(res.content)).convert("RGBA")
            if img.width < 300 or img.height < 300:
                return None
            fundo = Image.new("RGB", img.size, "white")
            fundo.paste(img, mask=img.getchannel("A"))
            caminho = os.path.join(self.output_folder, "universal_img_%s.jpg" % time.time_ns())
            fundo.save(caminho, "JPEG", quality=90)
            return caminho
        except (requests.RequestException, ValueError, OSError) as e:
            print("   [Universal] Imagem indisponivel: " + type(e).__name__)
            return None

    def executar(self):
        dominio = urlparse(self.url).hostname or "url-invalida"
        html, imagem_temp = "", None
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
                    titulo_h, descricao_h, specs_h, imagem_h, _ = self.extrair_html(html, url)
                    t, d, s, i, f = dados
                    if not t:
                        t = titulo_h
                    if len(d) < 80:
                        d = descricao_h
                    for k, v in specs_h.items():
                        if k not in s:
                            self.adicionar_spec(s, k, v)
                    dados = t, d, s, i or imagem_h, f
                titulo, descricao, specs, imagem, fonte = dados
                conteudo_ok = len(descricao) >= 80 or len(specs) >= 3
                bloqueio = self.bloqueada(html, status) and not veio_api
                if bloqueio or not titulo or not conteudo_ok:
                    try:
                        print("   [Universal] Tentando Chrome 109")
                        html, url = self.navegar(url)
                        dados = self.extrair_html(html, url)
                        titulo, descricao, specs, imagem, fonte = dados
                        fonte = "selenium"
                        bloqueio = self.bloqueada(html)
                    except Exception as e:
                        print("   [Universal] Chrome indisponivel: " + type(e).__name__)
                if bloqueio:
                    raise ValueError("Pagina bloqueada ou desafio anti-bot")
                titulo = self.normalizar(self.limpar_texto(titulo))
                if not titulo or any(x in titulo.lower() for x in TITULOS_INVALIDOS):
                    raise ValueError("Titulo de produto ausente ou invalido")
                specs = self.filtrar_specs(specs)
                if len(descricao) < 80 and len(specs) < 3:
                    raise ValueError("Descricao curta e menos de 3 especificacoes")
                if not veio_api and not self.produto_jsonld(BeautifulSoup(html, "html.parser")):
                    sinais = re.search(r"add.to.cart|addtocart|itemprop=['\"]price|product:price|woocommerce-product", html, re.I)
                    if not sinais and len(specs) < 3:
                        raise ValueError("Pagina sem sinais suficientes de produto")
                imagem_temp = self.baixar_imagem(urljoin(url, imagem), session) if imagem else None
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
            return {"sucesso": False, "erro": "Universal: %s (%s)" % (mensagem, dominio)}
