# scrapers/casasbahia.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
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
            options.add_argument("--window-size=1920,1080")

            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)

            print(f"   [Casas Bahia] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            print("   [Casas Bahia] A aguardar renderização inicial...")
            try:
                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
                )
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. A forçar a extração.")

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
                raise Exception("Título não encontrado (a página não renderizou ou o layout mudou)")
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
