# scrapers/ingrammicro.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import time
import os
import re
import requests
from .base import BaseScraper

class IngramMicroScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Ingram Micro] Iniciando Scraper (V19 - Timeout Tático)...")
            
            # --- SETUP ---
            # A pasta certa é a do pedido (o output_folder da base). O 'pasta_saida'
            # não existe no BaseScraper e criava uma pasta 'output' à parte.
            if self.output_folder and not os.path.exists(self.output_folder):
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            # NÃO usar --headless: em headless a Ingram nunca chega a carregar
            # (fica em "Nova guia" até ao timeout). Sem headless vem completa.
            # Eager: Espera o HTML carregar, mas não imagens pesadas
            options.page_load_strategy = 'eager' 
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.add_argument("--window-size=1920,1080")

            # CRÍTICO: Versão 109 para rodar no Windows Server 2012 R2
            driver = uc.Chrome(options=options, version_main=109)
            
            # 1. ACESSO COM TIMEOUT CONTROLADO
            print(f"   [Ingram] Acessando: {self.url}")
            
            # Define limite rígido de 15 segundos
            driver.set_page_load_timeout(15)
            
            try:
                driver.get(self.url)
            except TimeoutException:
                print("   ⚠️ Timeout de 15s atingido (Isso é bom! Cortamos scripts lentos).")
                # O comando stop garante que o navegador pare de girar
                try: driver.execute_script("window.stop();")
                except: pass
            
            # 2. DADOS PELA API DA PRÓPRIA PÁGINA
            # No servidor (Chrome 109) o React nunca chega a montar a página: fica
            # só o esqueleto de 19 KB com o spinner. Mas o HTML e os cookies do
            # Akamai chegam, e a página vai buscar o produto a um endereço JSON.
            # Chamamos esse endereço de dentro do browser e não dependemos do React.
            print("   [Ingram] Lendo o produto pela API interna da página...")
            time.sleep(2)   # dá tempo ao script do Akamai de deixar os cookies
            dados_api = self.ler_api(driver)
            caminho_imagem = None
            if dados_api:
                titulo, url_img, descricao, specs = dados_api
            else:
                print("   [Ingram] API não respondeu; a tentar pela página montada...")
                titulo, url_img, descricao, specs = self.extrair_do_html(driver)

            if url_img:
                if url_img.startswith("//"): url_img = "https:" + url_img
                # DOWNLOAD COM COOKIES DO SELENIUM
                caminho_imagem = self.baixar_imagem_com_cookies(driver, url_img)
                if caminho_imagem:
                    print(f"   ✅ Imagem salva: {os.path.basename(caminho_imagem)}")
            else:
                print("   ⚠️ URL da imagem não encontrada.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            arquivos = self.gerar_arquivos_finais(dados)
            
            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs,
                'total_imagens': 1 if caminho_imagem else 0,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO INGRAM] {e}")
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    # Cabeçalhos que a própria página manda ao endereço JSON (vistos no browser).
    # Sem IM-SiteCode/IM-Environment/IM-CorrelationID a API devolve 400.
    JS_LER_API = """
        var sku = arguments[0], cb = arguments[1];
        var id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, function (c) {
            return (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16);
        });
        var cab = {"IM-SiteCode": "br", "IM-Environment": "prodChicago", "IM-CountryCode": "BR",
                   "IM-AcceptLanguage": "pt-BR", "IM-SenderID": "IMCEP", "IM-ApiKey": "X4C@p!keypro$",
                   "IM-MicroFrontendID": "cep_app_productdetails", "IM-CorrelationID": id,
                   "IM-DDSessionId": id, "IM-CustomerNumber": "", "IM-ResellerID": "", "IM-UserID": "",
                   "correlationId": id, "countryCode": "BR", "isoCountryCode": "BR", "customerNumber": "",
                   "accept": "application/json", "accept-language": "pt-BR", "content-type": "application/json"};
        function pedir(q) {
            var u = "https://br.ingrammicro.com/api/product-details/v1/product-summaries/" + sku +
                    "/attributes?q=" + q + "&includeRecentlyViewed=false&enableClientSidePna=true&isBundleProduct=false";
            return fetch(u, {credentials: "include", headers: cab}).then(function (r) { return r.json(); });
        }
        Promise.all([pedir("basic"), pedir("details")])
            .then(function (r) { cb({basic: r[0], details: r[1]}); })
            .catch(function (e) { cb({erro: String(e)}); });
    """

    def ler_api(self, driver):
        """Lê título, imagem, descrição e ficha do JSON que a página usa.
        Devolve (titulo, url_img, descricao, specs) ou None se não der."""
        m = re.search(r"[?&]id=([A-Za-z0-9]+)", self.url)
        if not m:
            print("   [Ingram] Não há id= no link; não dá para usar a API.")
            return None
        sku = m.group(1)
        try:
            driver.set_script_timeout(40)
            r = driver.execute_async_script(self.JS_LER_API, sku) or {}
        except Exception as e:
            print(f"   [Ingram] Falha a chamar a API: {e}")
            return None
        if r.get("erro"):
            print(f"   [Ingram] API devolveu erro: {r['erro']}")
            return None
        basico = ((r.get("basic") or {}).get("additionalAttributes") or [{}])[0]
        detalhe = ((r.get("details") or {}).get("additionalAttributes") or [{}])[0]
        titulo = self.limpar_texto(basico.get("shortDescription") or "")
        if not titulo:
            print(f"   [Ingram] API sem produto: {str(r)[:200]}")
            return None

        url_img = basico.get("imageURL") or ""
        galeria = ((basico.get("extendedRichMediaSummaries") or [{}])[0].get("galleryImages") or {})
        grande = (galeria.get("image500") or "").split(",")[0].strip()
        if grande: url_img = grande

        descricao = "Descrição indisponível."
        bruta = detalhe.get("marketingText") or ""
        if bruta:
            texto = BeautifulSoup(bruta, "html.parser").get_text(separator="\n", strip=True)
            if len(texto) > 20: descricao = self.limpar_lixo_comercial(texto)

        # A ficha vem como lista plana; o grupo "Basic" é uma cópia dos outros.
        # Valores repetidos da mesma chave (ex.: várias interfaces) juntam-se.
        specs = {}
        itens = detalhe.get("specifications") or []
        grupos = {i.get("headername") for i in itens}
        for i in itens:
            if i.get("headername") == "Basic" and len(grupos) > 1: continue
            k = self.limpar_texto(i.get("attributename") or "")
            v = self.limpar_texto(i.get("attributevalue") or "")
            if not k or not v: continue
            if k in specs:
                if v not in specs[k]: specs[k] = specs[k] + ", " + v
            else:
                specs[k] = v
        specs.pop("Endereço do website do fabricante", None)
        print(f"   [Ingram] API OK: {len(specs)} specs, imagem {'sim' if url_img else 'não'}.")
        return titulo, url_img, descricao, specs


    def extrair_do_html(self, driver):
        """Caminho de reserva: lê a página já montada pelo React. Só serve
        quando o React chega a arrancar, o que não acontece com o Chrome 109."""
        # Espera inteligente pelo Título (garante que o conteúdo útil carregou).
        # A página é React e não tem <h1>: o título vem em data-testid=pdp_ProductTitle
        # e demora uns 10-15 s a aparecer depois do HTML.
        print("   [Ingram] Aguardando renderização do conteúdo...")
        try:
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='pdp_ProductTitle']"))
            )
        except:
            print("   ⚠️ Aviso: Título principal demorou a aparecer.")

        # A ficha técnica só é montada uns 2 s depois do título; se se ler
        # a página logo a seguir vem com 0 specs.
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='TechnicalSpecification'] table tr"))
            )
        except:
            print("   ⚠️ Aviso: Especificações técnicas não apareceram.")

        # 2. INTERAÇÃO: as specs já vêm no HTML; só a descrição completa
        # fica atrás do "Ver todos os detalhes do produto".
        try:
            for link in driver.find_elements(By.CSS_SELECTOR, "[data-testid='pdp_fullDescpLink']"):
                if link.is_displayed():
                    driver.execute_script("arguments[0].click();", link)
                    time.sleep(1.5)
        except: pass

        # 3. EXTRAÇÃO
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # --- TÍTULO ---
        titulo = None
        el_titulo = soup.find(attrs={"data-testid": "pdp_ProductTitle"})
        if el_titulo:
            titulo = self.limpar_texto(el_titulo.get_text())

        if not titulo:
            # Sem título não vale a pena continuar: antes saía um datasheet
            # vazio chamado "Produto Ingram" e mesmo assim com sucesso=True.
            html = driver.page_source
            self.guardar_pagina(driver)
            try: texto = driver.execute_script("return document.body.innerText.slice(0, 200)")
            except Exception: texto = ""
            texto = self.limpar_texto(texto)
            if "Não é possível acessar esse site" in html or "ERR_" in html:
                raise Exception(f"A página da Ingram não carregou (erro de rede do Chrome): {texto}")
            raise Exception(f"Título não encontrado (página com {len(html)} bytes, "
                            f"endereço final {driver.current_url}, texto: '{texto}')")

        print(f"   [DEBUG] Título: {titulo}")

        # --- IMAGEM (Download Autenticado) ---
        url_img = None
        
        print("   [Ingram] Buscando imagem...")
        # A foto do produto tem data-testid="<SKU>-0-slideImg" e vem do
        # inquirecontent2.ingrammicro.com; o resto são ícones e logos.
        imgs = soup.find_all("img")
        for img in imgs:
            src = img.get("src", "")
            testid = img.get("data-testid", "")
            if testid.endswith("-slideImg") or "inquirecontent" in src \
                    or "pimcontent" in src or "assets/images/product" in src:
                url_img = src
                break

        if not url_img:
            # Fallback: pega a maior imagem da tela
            try:
                imgs_el = driver.find_elements(By.TAG_NAME, "img")
                for el in imgs_el:
                    if el.size['width'] > 250:
                        url_img = el.get_attribute("src")
                        break
            except: pass


        # --- DESCRIÇÃO ---
        descricao = "Descrição indisponível."
        # A descrição está em blocos próprios. O "maior div da página" que
        # se usava antes apanhava o centro de preferências de cookies.
        for testid in ["OverviewDescription", "pdp_ProductDescription"]:
            bloco = soup.find(attrs={"data-testid": testid})
            if bloco and len(bloco.get_text(strip=True)) > 20:
                descricao = self.limpar_lixo_comercial(bloco.get_text(separator="\n", strip=True))
                break

        # --- SPECS ---
        specs = {}
        # Só as tabelas da aba "Especificações técnicas". Linhas com a chave
        # vazia são continuação da anterior (ex.: vários dispositivos).
        bloco_specs = soup.find(attrs={"data-testid": "TechnicalSpecification"}) or soup
        tabelas = bloco_specs.find_all("table")
        for t in tabelas:
            ultima = None   # a continuação nunca atravessa tabelas
            rows = t.find_all("tr")
            for r in rows:
                cols = r.find_all(["td", "th"], recursive=False)
                if len(cols) != 2: continue
                # A linha de fora, cujas células embrulham sub-tabelas inteiras,
                # não é uma spec: é a moldura.
                if r.find("table"): continue
                k = self.limpar_texto(cols[0].get_text())
                v = self.limpar_texto(cols[1].get_text())
                if not v: continue
                if not k and ultima:
                    specs[ultima] = specs[ultima] + ", " + v
                elif k and k not in specs:
                    specs[k] = v
                    ultima = k
        specs.pop("Endereço do website do fabricante", None)

        # Se não achou tabelas, tenta listas LI
        if not specs:
            lis = soup.find_all("li")
            for li in lis:
                txt = li.get_text()
                if ":" in txt and len(txt) < 100:
                    parts = txt.split(":", 1)
                    specs[parts[0].strip()] = parts[1].strip()

        print(f"   ✅ Specs encontradas: {len(specs)} itens.")
        return titulo, url_img, descricao, specs

    def guardar_pagina(self, driver):
        """Guarda o HTML e uma foto do que a Ingram mostrou, para se poder ver
        no servidor porque é que o título não apareceu."""
        if not self.output_folder: return
        base = os.path.join(self.output_folder, f"ingram_falha_{int(time.time())}")
        try:
            with open(base + ".html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            driver.save_screenshot(base + ".png")
            print(f"   [Ingram] Página guardada em {base}.html (e .png)")
        except Exception as e:
            print(f"   [Ingram] Não deu para guardar a página: {e}")

    # Função auxiliar para baixar imagem usando a sessão do Selenium
    def baixar_imagem_com_cookies(self, driver, url):
        try:
            # Pega cookies do navegador e passa para o Requests
            s = requests.Session()
            selenium_cookies = driver.get_cookies()
            for cookie in selenium_cookies:
                s.cookies.set(cookie['name'], cookie['value'])
            
            # Tenta simular um User-Agent real
            s.headers.update({
                "User-Agent": driver.execute_script("return navigator.userAgent;")
            })
            
            resp = s.get(url, timeout=10)
            if resp.status_code == 200:
                ext = "jpg" if ".jpg" in url else "png"
                filename = f"temp_img_ingram.{ext}"
                caminho = os.path.join(self.output_folder, filename)
                with open(caminho, 'wb') as f:
                    f.write(resp.content)
                return caminho
        except: return None
        return None