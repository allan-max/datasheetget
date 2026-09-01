# scrapers/bhphotovideo.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
from bs4 import BeautifulSoup
import time
import os
import json
import base64
from deep_translator import GoogleTranslator
from .base import BaseScraper

class BhPhotoVideoScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [B&H] Iniciando Scraper (V29 - No Specs Translation)...")
            
            # --- SETUP ---
            # O manager define 'output_folder'; 'pasta_saida' não existia e fazia a
            # imagem ir para uma pasta diferente da do Word/PDF.
            if not hasattr(self, 'output_folder') or not self.output_folder:
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            # NÃO usar --headless: em headless o B&H devolve o interstício anti-bot
            # ("Um momento…") com 27 KB e sem o produto. Sem headless a página vem
            # completa (500 KB), já com as tabelas de specs e as features.
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.page_load_strategy = 'eager'
            
            # CRÍTICO: Versão 109 para rodar no Windows Server 2012 R2
            driver = uc.Chrome(options=options, version_main=109)
            
            # =========================================================
            # ETAPA 1: PÁGINA PRINCIPAL
            # =========================================================
            print(f"   [B&H] Acessando Principal: {self.url}")
            driver.set_page_load_timeout(45)
            try:
                driver.get(self.url)
            except TimeoutException:
                print("   [B&H] Aviso: a página demorou muito. Extraindo o que já carregou.")

            # O Cloudflare mete-se à frente do produto ("Um momento…"). No servidor
            # era preciso clicar à mão na caixa de verificação; agora clica sozinho.
            self.resolver_captcha(driver)

            # Tenta fechar popups/cookies se aparecerem
            try:
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-selenium='cooc-close']"))
                ).click()
            except: pass

            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1[data-selenium='productTitle']"))
                )
            except: pass

            soup_main = BeautifulSoup(driver.page_source, 'html.parser')
            titulo = None
            h1 = soup_main.find("h1", attrs={"data-selenium": "productTitle"})
            if h1: titulo = self.limpar_texto(h1.get_text())

            # Sem título não há produto nenhum: antes ficava "Produto B&H" e o robô
            # gerava um PDF vazio a dizer que tinha corrido bem.
            if not titulo:
                html = driver.page_source
                if self.pagina_bloqueada(html):
                    raise Exception("Bloqueado pela verificação do Cloudflare (a caixa não foi ultrapassada)")
                raise Exception(f"Título não encontrado (página com {len(html)} bytes)")
            print(f"   [DEBUG] Título: {titulo}")

            # --- IMAGEM ---
            caminho_imagem = None

            # O src vem embrulhado no redimensionador do Cloudflare:
            # /cdn-cgi/image/fit=scale-down,width=500,.../https://www.bhphotovideo.com/...jpg
            # O ficheiro real é o que está depois do segundo 'http'.
            img_tag = soup_main.find("img", attrs={"data-selenium": "inlineMediaMainImage"})
            if img_tag:
                url_img = img_tag.get("src") or img_tag.get("data-src")
                # Enquanto não carrega, o src é um pixel em base64: o endereço
                # verdadeiro fica no data-src.
                if url_img and url_img.startswith("data:"):
                    url_img = img_tag.get("data-src") or ""
                if url_img:
                    if "/http" in url_img:
                        url_img = url_img[url_img.index("/http") + 1:]
                    elif url_img.startswith("//"):
                        url_img = "https:" + url_img
                    elif url_img.startswith("/"):
                        url_img = "https://www.bhphotovideo.com" + url_img
                    print(f"   [B&H] URL da imagem original: {url_img}")
                    # Pelo navegador primeiro: o requests da base.py não leva os
                    # cookies do Cloudflare e apanha 403 no servidor — foi por
                    # isso que o datasheet saiu sem foto.
                    caminho_imagem = self.baixar_imagem_navegador(driver, url_img)
                    if not caminho_imagem:
                        caminho_imagem = self.baixar_imagem_temp(url_img)

            seletores_img = [
                "img[data-selenium='inlineMediaMainImage']",
                "div[data-selenium='inlineMedia'] img",
                "img[class*='mainImage']"
            ]

            for seletor in ([] if caminho_imagem else seletores_img):
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, seletor)
                    for el in els:
                        if el.is_displayed() and el.size['width'] > 50:
                            # Nome único: a api.py cria uma thread por pedido e um nome
                            # fixo fazia dois produtos escreverem no mesmo ficheiro.
                            filename = f"temp_img_bh_{int(time.time())}.png"
                            caminho_imagem = os.path.join(self.output_folder, filename)
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                            time.sleep(0.3)
                            el.screenshot(caminho_imagem)
                            print(f"   ✅ Imagem salva.")
                            break
                    if caminho_imagem: break
                except: pass

            if not caminho_imagem:
                print("   ⚠️ Nenhuma imagem obtida — o datasheet vai sair sem foto.")

            # =========================================================
            # ETAPA 2: OVERVIEW
            # =========================================================
            # A página principal já traz as features do Overview (25 blocos no teste).
            # Só se vier vazia é que compensa navegar para /overview.
            descricao_en = self.extrair_descricao(soup_main)

            if not descricao_en:
                print("   [B&H] Overview vazio na principal. Navegando para /overview...")
                url_overview = self.url.split("?")[0].rstrip("/") + "/overview"
                driver.set_page_load_timeout(15)
                try: driver.get(url_overview)
                except: driver.execute_script("window.stop();")

                driver.execute_script("window.scrollTo(0, 600);")
                time.sleep(1)
                descricao_en = self.extrair_descricao(BeautifulSoup(driver.page_source, 'html.parser'))

            print("   [B&H] Traduzindo descrição...")
            # Apenas a descrição continua sendo traduzida
            descricao_pt = self.traduzir_texto(descricao_en)

            # =========================================================
            # ETAPA 3: SPECS (COM VERIFICAÇÃO ATIVA)
            # =========================================================
            print(f"   [B&H] Extraindo Specs...")
            
            tabela_detectada = False
            
            # TENTATIVA 1: Clique na Aba
            try:
                abas_specs = driver.find_elements(By.CSS_SELECTOR, "a[href*='/specs'], li[data-tab='specs']")
                for aba in abas_specs:
                    if "specs" in aba.text.lower() or "specifications" in aba.text.lower():
                        if aba.is_displayed():
                            print("   [B&H] Clicando na aba Specs...")
                            driver.execute_script("arguments[0].click();", aba)
                            
                            try:
                                WebDriverWait(driver, 4).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "table[data-selenium='specsItemGroupTable']"))
                                )
                                tabela_detectada = True
                            except: pass
                            break
            except: pass

            # TENTATIVA 2: Navegação Direta (Se clique falhou)
            if not tabela_detectada:
                print("   [B&H] Navegando direto para Specs (Timeout 6s)...")
                url_specs = self.url.split("?")[0].rstrip("/") + "/specs"
                driver.set_page_load_timeout(6) 
                try: 
                    driver.get(url_specs)
                except: 
                    driver.execute_script("window.stop();")
            
            # --- PARSE ---
            soup_specs = BeautifulSoup(driver.page_source, 'html.parser')
            specs = {}
            tabelas = soup_specs.find_all("table", attrs={"data-selenium": "specsItemGroupTable"})
            if not tabelas: tabelas = soup_specs.find_all("table")

            # 1. Extração Visual (Tabelas)
            if tabelas:
                print(f"   ✅ {len(tabelas)} tabelas visuais encontradas.")
                for tabela in tabelas:
                    for linha in tabela.find_all("tr"):
                        cols = linha.find_all("td")
                        if len(cols) >= 2:
                            k = self.limpar_texto(cols[0].get_text())
                            v = self.limpar_texto(cols[1].get_text())
                            if len(k) < 100 and len(v) > 0:
                                if not any(ig in k.lower() for ig in ["packaging", "box dim", "peso da emb"]):
                                    specs[k] = v
            
            # 2. Extração Oculta (JSON-LD)
            if not specs:
                print("   ⚠️ Tabelas vazias. Buscando dados ocultos (JSON-LD)...")
                try:
                    scripts = soup_specs.find_all("script", type="application/ld+json")
                    for script in scripts:
                        try:
                            txt = script.get_text()
                            if "weight" in txt or "width" in txt:
                                data = json.loads(txt)
                                if isinstance(data, list): data = data[0]
                                
                                if "width" in data: specs["Largura"] = str(data["width"])
                                if "height" in data: specs["Altura"] = str(data["height"])
                                if "depth" in data: specs["Profundidade"] = str(data["depth"])
                                if "weight" in data: specs["Peso"] = str(data["weight"])
                                if "sku" in data: specs["SKU"] = str(data["sku"])
                                if "brand" in data: 
                                    b = data["brand"]
                                    if isinstance(b, dict): specs["Marca"] = b.get("name", "")
                                    else: specs["Marca"] = str(b)
                        except: pass
                except: pass

            # A TRADUÇÃO DE SPECS FOI REMOVIDA DAQUI
            specs_final = specs
            print(f"   ✅ Specs prontas (sem tradução): {len(specs_final)} itens.")

            # Sem descrição e sem ficha técnica o datasheet sairia vazio: falha explícita
            if not descricao_pt and not specs_final:
                raise Exception("Nenhum conteúdo extraído (descrição e ficha técnica vazias)")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao_pt,
                "caracteristicas": specs_final,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [B&H] Gerando arquivos finais...")
            arquivos = self.gerar_arquivos_finais(dados)
            
            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao_pt,
                'caracteristicas': specs_final,
                'total_imagens': 1 if caminho_imagem else 0,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO B&H] {e}")
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def pagina_bloqueada(self, html):
        """Diz se o que está no ecrã é a verificação do Cloudflare e não o produto.
        Se o título do produto já lá está, não é bloqueio: o B&H também carrega
        scripts do Cloudflare em páginas normais."""
        if not html: return True
        if 'data-selenium="productTitle"' in html: return False
        marcas = ["challenges.cloudflare.com", "cf-turnstile", "cf_chl_opt",
                  "Um momento", "Just a moment", "Verify you are human",
                  "Verifique se você é humano", "cf-browser-verification"]
        return any(m in html for m in marcas)

    def elementos_visiveis(self, driver, seletor):
        try: elementos = driver.find_elements(By.CSS_SELECTOR, seletor)
        except: return []
        saida = []
        for el in elementos:
            try:
                if el.is_displayed() and el.size['width'] > 10: saida.append(el)
            except: pass
        return saida

    def localizar_widget(self, driver):
        """Encontra a caixa "Confirme que é humano".

        No desafio do B&H o iframe do Turnstile é servido pelo próprio domínio
        (/cdn-cgi/challenge-platform/...) e o título vem em português, por isso
        procurar por 'challenges.cloudflare.com' ou 'Cloudflare' não achava nada."""
        seletores = ["iframe[src*='challenge-platform']",
                     "iframe[src*='turnstile']",
                     "iframe[id^='cf-chl-widget']",
                     "iframe[title*='desafio']",
                     "iframe[title*='challenge']",
                     "div.cf-turnstile", "#cf-turnstile"]
        for seletor in seletores:
            for el in self.elementos_visiveis(driver, seletor):
                return el

        # Último recurso: qualquer iframe com o tamanho de um widget (~300x65).
        for el in self.elementos_visiveis(driver, "iframe"):
            try:
                if 150 <= el.size['width'] <= 500 and 30 <= el.size['height'] <= 150:
                    return el
            except: pass
        return None

    def clicar_widget(self, driver, el):
        # 1) Por dentro do iframe: a caixa é um <input type="checkbox"> normal.
        if el.tag_name == "iframe":
            try:
                driver.switch_to.frame(el)
                try:
                    for caixa in driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox'], label"):
                        if caixa.is_displayed():
                            caixa.click()
                            print("   [B&H] Caixa clicada dentro do iframe.")
                            return True
                finally:
                    driver.switch_to.default_content()
            except:
                try: driver.switch_to.default_content()
                except: pass

        # 2) Por coordenadas: a caixa fica encostada à esquerda do widget e o
        #    Selenium 4 mede o desvio a partir do centro do elemento.
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.5)
            dx = int(-el.size['width'] / 2) + 25
            ActionChains(driver).move_to_element_with_offset(el, dx, 0).pause(0.3).click().perform()
            print(f"   [B&H] Clique por coordenadas no widget (desvio {dx}px).")
            return True
        except Exception as e:
            print(f"   [B&H] Clique por coordenadas falhou: {e}")
            return False

    def resolver_captcha(self, driver, tentativas=3):
        """Clica na caixa "Confirme que é humano" do Cloudflare quando ela aparece."""
        for tentativa in range(1, tentativas + 1):
            try: html = driver.page_source
            except: html = ""
            if not self.pagina_bloqueada(html):
                return True

            print(f"   [B&H] Verificação do Cloudflare no ecrã ({tentativa}/{tentativas}). A clicar...")

            # O widget é desenhado depois da página, não está lá logo no início.
            el = None
            for _ in range(10):
                el = self.localizar_widget(driver)
                if el: break
                # Há desafios que passam sozinhos, sem caixa nenhuma: não vale a
                # pena ficar os 10 segundos à procura de um widget que não existe.
                try:
                    if not self.pagina_bloqueada(driver.page_source):
                        print("   [B&H] Verificação passou sozinha.")
                        return True
                except: pass
                time.sleep(1)

            if el:
                self.clicar_widget(driver, el)
            else:
                # Se voltar a falhar, o log diz que iframes existem mesmo na página.
                print("   [B&H] Widget não encontrado. Iframes presentes:")
                try:
                    for f in driver.find_elements(By.TAG_NAME, "iframe"):
                        try:
                            print(f"      - src={(f.get_attribute('src') or '')[:70]} "
                                  f"| id={f.get_attribute('id')} | tam={f.size}")
                        except: pass
                except: pass

            # A verificação demora alguns segundos e a página recarrega sozinha.
            for _ in range(20):
                time.sleep(1)
                try: html = driver.page_source
                except: continue
                if not self.pagina_bloqueada(html):
                    print("   [B&H] Verificação ultrapassada.")
                    return True

        print("   ⚠️ [B&H] A verificação do Cloudflare não foi ultrapassada.")
        return False

    def baixar_imagem_navegador(self, driver, url_imagem):
        """Baixa a imagem com o próprio Chrome, que já tem a sessão validada."""
        script = """
            var url = arguments[0], cb = arguments[arguments.length - 1];
            fetch(url, {credentials: 'include'})
                .then(function (r) { return r.blob(); })
                .then(function (b) {
                    var fr = new FileReader();
                    fr.onloadend = function () { cb(fr.result); };
                    fr.readAsDataURL(b);
                })
                .catch(function () { cb(null); });
        """
        try:
            driver.set_script_timeout(30)
            data_url = driver.execute_async_script(script, url_imagem)
            if not data_url or not data_url.startswith("data:image"):
                print("   [B&H] O navegador não devolveu uma imagem válida.")
                return None
            # Nome único: a api.py cria uma thread por pedido.
            caminho = os.path.join(self.output_folder, f"temp_img_bh_{int(time.time())}.jpg")
            with open(caminho, "wb") as f:
                f.write(base64.b64decode(data_url.split(",", 1)[1]))
            print(f"   ✅ Imagem baixada pelo navegador ({os.path.getsize(caminho)} bytes).")
            return caminho
        except Exception as e:
            print(f"   [B&H] Download pelo navegador falhou: {e}")
            return None

    def extrair_descricao(self, soup):
        """Junta os blocos de 'feature' do Overview num texto só (em inglês)."""
        blocos_desc = []

        features = soup.find_all("div", class_=lambda c: c and "feature_" in c)
        if not features:
            div_long = soup.find("div", attrs={"data-selenium": "overviewLongDescription"})
            if div_long: features = [div_long]

        seen_text = set()
        for feat in features:
            if len(feat.find_all("div", class_=lambda c: c and "feature_" in c)) > 1: continue
            header = feat.find("div", class_=lambda c: c and "featureHeader_" in c)
            body = feat.find("div", class_="js-injected-html")
            txt_h = header.get_text(strip=True) if header else ""
            txt_b = body.get_text(separator="\n", strip=True) if body else ""
            if txt_b and txt_b not in seen_text:
                seen_text.add(txt_b)
                chunk = f"### {txt_h}\n{txt_b}\n" if txt_h else f"{txt_b}\n"
                blocos_desc.append(chunk)

        if blocos_desc: return "\n".join(blocos_desc)

        div_d = soup.find("div", class_=lambda c: c and "js-injected-html" in c)
        if div_d: return div_d.get_text(separator="\n\n", strip=True)
        return ""

    def traduzir_texto(self, texto, curto=False):
        if not texto or len(texto) < 2: return texto
        try:
            limite = 4500
            translator = GoogleTranslator(source='en', target='pt')

            if len(texto) <= limite:
                return translator.translate(texto)

            # O tradutor só aceita ~5000 caracteres por pedido. Antes o resto era
            # cortado com texto[:4500] e perdia-se metade da descrição sem aviso
            # (a do Sony a7 V tem 8731). Agora traduz por blocos e volta a juntar.
            partes = []
            atual = ""
            for linha in texto.split("\n"):
                while len(linha) > limite:
                    if atual:
                        partes.append(atual)
                        atual = ""
                    partes.append(linha[:limite])
                    linha = linha[limite:]
                if len(atual) + len(linha) + 1 > limite:
                    if atual: partes.append(atual)
                    atual = linha
                else:
                    atual = f"{atual}\n{linha}" if atual else linha
            if atual: partes.append(atual)

            traduzidas = []
            for parte in partes:
                try:
                    traduzidas.append(translator.translate(parte) or parte)
                except:
                    traduzidas.append(parte)
            return "\n".join(traduzidas)
        except: return texto