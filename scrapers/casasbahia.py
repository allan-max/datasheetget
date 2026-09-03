# scrapers/casasbahia.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class CasasBahiaScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Casas Bahia] A iniciar Scraper (Motor de Auto-Click Duplo)...")

            if not hasattr(self, 'output_folder') or not self.output_folder:
                self.output_folder = "output"
            if not os.path.exists(self.output_folder):
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            # NÃO forjar o User-Agent: o Akamai da Casas Bahia compara o UA com os
            # client hints (sec-ch-ua) do Chrome real e devolve a página de bloqueio
            # 'customdeny' de 3 KB. Sem o override a página abre normalmente.
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            # NÃO usar --disable-http2 aqui: o Chrome 109 real fala sempre HTTP/2 com
            # o Akamai. Forçar HTTP/1.1 faz o navegador dizer que é Chrome mas negociar
            # como outra coisa, e a assinatura HTTP/2 em falta é ela própria um sinal.
            # Perfil novo arranca em inglês; um comprador brasileiro manda pt-BR.
            options.add_argument("--lang=pt-BR")
            options.add_argument("--window-size=1920,1080")

            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)

            driver.set_page_load_timeout(60)

            # O undetected_chromedriver arranca sempre num perfil vazio. Entrar
            # direto no link do produto com um navegador sem cookies nem histórico
            # é o padrão que o Akamai nega de imediato ('customdeny'), sem sequer
            # dar o desafio. Passar primeiro pela homepage deixa o sensor do Akamai
            # correr e validar os cookies da sessão (_abck), tal como acontece
            # quando se abre o site à mão.
            print("   [Casas Bahia] A aquecer a sessão pela página inicial...")
            try:
                driver.get("https://www.casasbahia.com.br/")
                time.sleep(8)
                # Saber se a inicial passou é o que distingue 'sessão recusada logo
                # à entrada' de 'o sensor do Akamai correu e reprovou o navegador'.
                print(f"   [Casas Bahia] Estado da página inicial: {self.diagnosticar_bloqueio(driver.page_source)}")
            except Exception as e:
                print(f"   ⚠️ Aviso: não foi possível abrir a página inicial: {e}")

            print(f"   [Casas Bahia] A aceder a: {self.url}")

            # O Akamai da Casas Bahia devolve primeiro um interstício de desafio em JS.
            # Num servidor lento / com IP de datacenter esse desafio demora mais e às
            # vezes só passa ao recarregar. Mesmo padrão da Tambasa: detetar, esperar
            # e recarregar, em vez de desistir logo à primeira.
            pagina_ok = False
            for tentativa in range(1, 4):
                try:
                    if tentativa == 1:
                        # Navegar a partir da própria página envia o Referer da Casas
                        # Bahia. O driver.get() entra sem Referer nenhum, que é
                        # precisamente o que um robô faz e uma pessoa não.
                        driver.execute_script("window.location.href = arguments[0];", self.url)
                        time.sleep(3)
                    else:
                        driver.get(self.url)
                except TimeoutException:
                    print("   [Casas Bahia] Aviso: a página demorou muito. A continuar com o que carregou.")
                except Exception as e:
                    print(f"   [Casas Bahia] Erro de rede: {e}")

                print(f"   [Casas Bahia] A aguardar renderização (tentativa {tentativa}/3)...")
                try:
                    # Não basta haver um <h1>: a página inicial também tem um. Se o
                    # produto demorar a carregar, o <h1> "Casas Bahia - Página Inicial"
                    # dava a página por boa e o datasheet saía vazio. Exige-se o
                    # endereço do produto (/p/) além do título.
                    WebDriverWait(driver, 40).until(
                        lambda d: "/p/" in d.current_url and d.find_elements(By.CSS_SELECTOR, "h1")
                    )
                    pagina_ok = True
                    break
                except:
                    pass

                if "/p/" not in driver.current_url:
                    print(f"   ⚠️ Ainda na página inicial ({driver.current_url[:60]}); a entrar direto no produto.")
                    if tentativa < 3:
                        time.sleep(3)
                    continue

                estado = self.diagnosticar_bloqueio(driver.page_source)
                print(f"   ⚠️ H1 não apareceu. Estado: {estado}")

                # Bloqueio de IP não passa a recarregar: cada nova tentativa só
                # reforça a marcação do Akamai. Desiste já em vez de insistir.
                if "acesso negado" in estado:
                    print("   [Casas Bahia] Bloqueio permanente — a desistir sem insistir.")
                    break

                if tentativa < 3:
                    time.sleep(10)

            if not pagina_ok:
                print(f"   [Casas Bahia] Sensor do Akamai: {self.estado_sensor(driver)}")
                self.guardar_pagina(driver)

            # --- ROLAGEM PROGRESSIVA ---
            print("   [Casas Bahia] A vasculhar a página para contornar o Lazy Load...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)

            # --- AUTO-CLICKER: ABRE O MODAL "VER MAIS" ---
            # A ficha técnica completa só existe dentro do modal. O botão precisa de
            # scrollIntoView antes do clique, senão o React ignora o evento.
            print("   [Casas Bahia] A expandir a Ficha Técnica (botão 'Ver mais')...")
            modal_aberto = False
            try:
                driver.execute_script("""
                    var btnVerMais = document.querySelector('[data-cy="product-characteristics-see-more"]');
                    if(btnVerMais) {
                        btnVerMais.scrollIntoView({block: 'center'});
                        btnVerMais.click();
                    }
                """)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='product-details-content']"))
                )
                modal_aberto = True
                print("   ✅ Modal de características aberto.")
            except:
                print("   ⚠️ Aviso: modal não abriu. A usar o bloco resumido da página.")

            # --- FICHA TÉCNICA (percorre os separadores do modal) ---
            print("   [Casas Bahia] A extrair Ficha Técnica...")
            specs = {}
            try:
                if modal_aberto:
                    # Cada separador só é renderizado depois de ser clicado
                    total_abas = len(driver.find_elements(By.CSS_SELECTOR, "[role='tab']"))
                    for i in range(max(total_abas, 1)):
                        try:
                            abas = driver.find_elements(By.CSS_SELECTOR, "[role='tab']")
                            nome_aba = self.limpar_texto(abas[i].text)
                            # A aba de contacto do fabricante é lixo comercial
                            if "contato" in nome_aba.lower() or "contacto" in nome_aba.lower():
                                continue
                            driver.execute_script("arguments[0].click();", abas[i])
                            time.sleep(1.5)
                            print(f"      ↳ Separador: {nome_aba}")
                        except:
                            pass
                        specs.update(self.extrair_specs_modal(BeautifulSoup(driver.page_source, 'html.parser')))
            except Exception as e:
                print(f"   ⚠️ Erro ao percorrer os separadores: {e}")

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = None
            h1 = soup.find('h1')
            if h1:
                titulo = self.limpar_texto(h1.get_text())
            if not titulo:
                raise Exception(f"Título não encontrado — {self.diagnosticar_bloqueio(driver.page_source)}")
            if "/p/" not in driver.current_url or "página inicial" in titulo.lower():
                raise Exception(f"O navegador não saiu da página inicial (ficou em {driver.current_url[:80]})")
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [Casas Bahia] A extrair Descrição...")
            descricao = "Descrição indisponível."
            try:
                # A caixa 'special-content' costuma vir vazia (é só o banner de imagens);
                # o texto real do produto fica em #product-description
                container_desc = soup.find('div', id='product-description')
                if not container_desc:
                    container_desc = soup.find('div', attrs={"data-component": "special-content"})

                descricao_bruta = ""
                if container_desc:
                    for tag in container_desc(["script", "style"]):
                        tag.decompose()
                    for br in container_desc.find_all("br"):
                        br.replace_with("\n")
                    for li in container_desc.find_all("li"):
                        li.insert_before("\n")
                    descricao_bruta = container_desc.get_text()

                if descricao_bruta and len(descricao_bruta.strip()) > 15:
                    descricao = self.limpar_descricao_casasbahia(descricao_bruta.strip())
                    print("   ✅ Descrição capturada e limpa com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a descrição.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair descrição: {e}")

            # --- FICHA TÉCNICA: PLANO B E LIMPEZA ---
            if not specs:
                specs = self.extrair_specs_pagina(soup)

            specs_limpas = {}
            termos_proibidos_specs = [
                "garantia", "entrega do produto", "conteúdo da embalagem",
                "cód. item", "outros produtos"
            ]
            for k, v in specs.items():
                k_lower = k.lower()
                if not any(t in k_lower for t in termos_proibidos_specs):
                    specs_limpas[k] = v

            specs = specs_limpas
            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)

            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # Sem descrição e sem ficha técnica o datasheet sairia vazio: falha explícita
            if descricao == "Descrição indisponível." and not specs:
                raise Exception("Nenhum conteúdo extraído (descrição e ficha técnica vazias)")

            # --- IMAGEM ---
            print("   [Casas Bahia] A extrair Imagem...")
            url_img = None
            caminho_imagem = None

            # Fecha o modal para não tapar a galeria no screenshot
            try:
                driver.execute_script("""
                    var fechar = document.querySelector('[role="dialog"] button[aria-label="Fechar"]');
                    if(fechar) { fechar.click(); }
                """)
                time.sleep(1)
            except:
                pass

            # A galeria vive em imgs.casasbahia.com.br/<codigo>/<n>xg.jpg. O logótipo e os
            # selos estão no mesmo domínio, por isso o filtro é pelo alt e pelo padrão do link.
            img_tag = soup.find('img', alt=re.compile(r'Imagem do produto', re.IGNORECASE))
            if not img_tag:
                for img in soup.find_all('img'):
                    src = img.get('src') or img.get('data-src') or ""
                    if re.search(r'imgs\.casasbahia\.com\.br/\d+/', src):
                        img_tag = img
                        break

            if img_tag:
                url_img = img_tag.get('src') or img_tag.get('data-src')

            if url_img:
                # TRUQUE DE ALTA RESOLUÇÃO: Remove o limitador de tamanho da Casas Bahia (?imwidth=500)
                url_img = url_img.split("?")[0]
                print(f"   [Casas Bahia] URL da imagem original encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Casas Bahia] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_imgs = driver.find_elements(By.CSS_SELECTOR, "img[alt*='Imagem do produto'], img[alt*='produto']")
                    if el_imgs:
                        el_img = el_imgs[0]
                        filename = f"temp_img_cb_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)

                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                    else:
                        print("   ⚠️ Imagem não encontrada no DOM para screenshot.")
                except Exception as e:
                    print(f"   ⚠️ Erro inesperado ao salvar imagem: {type(e).__name__}")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [Casas Bahia] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO CASAS BAHIA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def diagnosticar_bloqueio(self, html):
        """Diz porque é que a página não veio, em vez do genérico 'layout mudou'."""
        if not html:
            return "o navegador não devolveu nada (o Chrome não chegou a abrir a página)"
        if "sec-if-cpt-container" in html or "Powered and protected by" in html:
            return "parou no desafio anti-bot do Akamai (a verificação não foi ultrapassada)"
        if "customdeny" in html or "Access Denied" in html:
            return "acesso negado pelo Akamai (página customdeny; ver a linha do sensor)"
        if "Too Many Requests" in html or "429" == html.strip():
            return "bloqueio por excesso de pedidos (429)"
        if len(html) < 5000:
            return f"a página veio praticamente vazia ({len(html)} bytes)"
        return f"a página carregou ({len(html)} bytes) mas sem H1 — o layout pode ter mudado"

    def estado_sensor(self, driver):
        """O cookie _abck diz se o sensor do Akamai aprovou o navegador: termina em
        '~0~' quando aprovou e em '~-1~' quando o marcou como robô. É esta linha
        que separa 'IP bloqueado' de 'navegador reprovado' quando corre no servidor."""
        try:
            for c in driver.get_cookies():
                if c.get("name") == "_abck":
                    v = c.get("value", "")
                    if "~-1~" in v: return "reprovou o navegador (_abck ~-1~)"
                    if "~0~" in v: return "aprovou o navegador (_abck ~0~)"
                    return f"_abck presente mas sem veredicto ({v[:40]}...)"
            return "sem cookie _abck (o sensor nem chegou a correr)"
        except Exception as e:
            return f"não foi possível ler os cookies ({e})"

    def guardar_pagina(self, driver):
        """Guarda o HTML e uma foto do que o navegador está a mostrar, para se
        poder ver o que o servidor apanhou quando a página não vem."""
        try:
            base = os.path.join(self.output_folder, f"casasbahia_falha_{int(time.time())}")
            with open(base + ".html", "w", encoding="utf-8") as f:
                f.write(driver.page_source or "")
            driver.save_screenshot(base + ".png")
            print(f"   [Casas Bahia] Página guardada em: {base}.html / .png")
        except Exception as e:
            print(f"   ⚠️ Não foi possível guardar a página da falha: {e}")

    def extrair_specs_modal(self, soup):
        """Ficha técnica completa: <p>Chave</p><span>Valor</span> dentro do modal."""
        specs = {}
        painel = soup.find("div", attrs={"data-testid": "product-details-content"})
        if not painel:
            return specs

        modal = painel.find_parent(attrs={"role": "dialog"}) or painel

        for caixa in modal.find_all("div", attrs={"data-testid": "dsvia-base-div"}):
            if 'dsvia-flex' not in (caixa.get('class') or []):
                continue

            # recursive=False evita apanhar a caixa exterior (o rótulo do separador)
            p_tag = caixa.find('p', recursive=False)
            span_tag = caixa.find('span', recursive=False)

            if p_tag and span_tag:
                chave = self.limpar_texto(p_tag.get_text())
                # Substitui quebras de linha dentro do span por ponto e vírgula
                for br in span_tag.find_all("br"): br.replace_with("; ")
                valor = self.limpar_texto(span_tag.get_text(separator=" ", strip=True))

                if chave and valor:
                    specs[chave] = valor
        return specs

    def extrair_specs_pagina(self, soup):
        """Plano B: bloco resumido da página, onde a chave é um <p> dentro do <p> do valor."""
        specs = {}
        bloco = soup.find(attrs={"data-cy": "product-characteristics"})
        if not bloco:
            return specs

        for p_externo in bloco.find_all("p"):
            p_interno = p_externo.find("p")
            if not p_interno:
                continue

            chave = self.limpar_texto(p_interno.get_text())
            p_interno.extract()
            for br in p_externo.find_all("br"): br.replace_with("; ")
            valor = self.limpar_texto(p_externo.get_text(separator=" ", strip=True))

            if chave and valor:
                specs[chave] = valor
        return specs

    def limpar_descricao_casasbahia(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        linhas = texto_bruto.splitlines()
        linhas_limpas = []

        termos_proibidos = [
            "garantia", "entrega", "frete", "pagamento", "boleto",
            "cartão", "consulte o manual", "não nos responsabilizamos",
            "montagem", "içamento", "elevadores", "conteúdo da embalagem"
        ]

        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean:
                continue

            linha_lower = linha_clean.lower()

            if any(termo in linha_lower for termo in termos_proibidos):
                continue

            linhas_limpas.append(linha_clean)

        return "\n\n".join(linhas_limpas)
