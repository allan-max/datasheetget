# scrapers/mercadolivre.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from bs4 import BeautifulSoup
import requests
import time
import os
import re
from .base import BaseScraper

class MercadoLivreScraper(BaseScraper):
    def montar_url_translate(self, url_original):
        """
        Converte a URL do Mercado Livre para o gateway do Google Translate (translate.goog).
        Como a requisição ao Mercado Livre parte dos IPs reais do Google, o ML entrega
        a página completa de SEO sem redirecionar para 'Olá! Para continuar, acesse sua conta'.
        """
        p = urlparse(url_original)
        host = p.hostname or "www.mercadolivre.com.br"
        path = p.path or "/"

        # URLs curtas /p/MLB... sem slug fazem redirect 301 que o translate.goog barra via GET simples;
        # adicionando um slug genérico antes de /p/MLB, o ML responde 200 direto com o HTML completo.
        if re.match(r"^/p/MLB\d+", path, re.IGNORECASE):
            path = "/produto" + path

        host_tr = host.replace("-", "--").replace(".", "-") + ".translate.goog"
        query_params = dict(parse_qsl(p.query))
        query_params["_x_tr_sl"] = "auto"
        query_params["_x_tr_tl"] = "pt"
        query_params["_x_tr_hl"] = "pt-BR"

        return urlunparse(("https", host_tr, path, p.params, urlencode(query_params), ""))

    def carregar_html(self):
        url_proxy = self.montar_url_translate(self.url)

        # 1. Tentativa rápida via requests através do gateway do Google (leva ~2s e não abre navegador)
        try:
            print(f"   [Mercado Livre] Acessando via Gateway Google (sem login): {url_proxy}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            resp = requests.get(url_proxy, headers=headers, timeout=25)
            if resp.status_code == 200 and "ui-pdp-title" in resp.text:
                return resp.text
            print(f"   [Mercado Livre] Aviso: Gateway via requests retornou status {resp.status_code}. Tentando via navegador...")
        except Exception as e:
            print(f"   [Mercado Livre] Aviso: Falha no requests ({e}). Tentando via navegador...")

        # 2. Fallback via undetected_chromedriver (acessando o gateway translate.goog ou a URL original)
        driver = None
        try:
            for url_tentativa in (url_proxy, self.url):
                options = uc.ChromeOptions()
                options.page_load_strategy = 'eager'
                options.add_argument("--no-first-run")
                options.add_argument("--password-store=basic")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--window-size=1920,1080")

                if driver is None:
                    try:
                        driver = uc.Chrome(options=options, version_main=109)
                    except Exception:
                        options = uc.ChromeOptions()
                        options.page_load_strategy = 'eager'
                        options.add_argument("--no-first-run")
                        options.add_argument("--password-store=basic")
                        options.add_argument("--no-sandbox")
                        options.add_argument("--disable-dev-shm-usage")
                        options.add_argument("--disable-gpu")
                        options.add_argument("--window-size=1920,1080")
                        driver = uc.Chrome(options=options)
                    driver.set_window_size(1920, 1080)

                print(f"   [Mercado Livre] Acessando no navegador: {url_tentativa}")
                driver.get(url_tentativa)

                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "h1.ui-pdp-title"))
                    )
                except Exception:
                    pass

                driver.execute_script("window.scrollTo(0, 800);")
                time.sleep(2)

                html = driver.page_source
                if "ui-pdp-title" in html:
                    return html
            return driver.page_source if driver else ""
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def executar(self):
        try:
            print(f"   [Mercado Livre] Iniciando Scraper (Bypass Account Verification + Imagem Alta Resolução)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            html = self.carregar_html()
            soup = BeautifulSoup(html or "", 'html.parser')

            # --- 1. TÍTULO ---
            h1 = soup.find('h1', class_=re.compile(r'ui-pdp-title'))
            if not h1:
                if "account-verification" in (html or "") or "acesse sua conta" in (html or "").lower():
                    raise Exception("Mercado Livre bloqueou o acesso com tela de login (account-verification).")
                raise Exception("Não foi possível localizar os dados do anúncio no Mercado Livre.")

            titulo = self.limpar_texto(h1.get_text())
            print(f"   [OK] Título capturado: {titulo}")

            # --- 2. IMAGEM (O TRUQUE DA ALTA RESOLUÇÃO) ---
            print("   [Mercado Livre] A extrair Imagem Gigante...")
            url_img = None
            
            # Prioriza especificamente a imagem principal da galeria (evitando pegar miniaturas de variações ou ícones que também têm a classe ui-pdp-image)
            img_tag = soup.find('img', class_=re.compile(r'ui-pdp-gallery__figure__image'))
            if not img_tag:
                for cand in soup.find_all('img', class_=re.compile(r'ui-pdp-image')):
                    classes_cand = " ".join(cand.get('class', []))
                    if 'thumbnail' not in classes_cand and 'icon' not in classes_cand:
                        img_tag = cand
                        break

            if img_tag:
                url_img = img_tag.get('data-zoom') or img_tag.get('src')
                if url_img and url_img.startswith("data:"):
                    url_img = img_tag.get('data-src') or None

            if not url_img:
                og_img = soup.find('meta', property='og:image')
                if og_img:
                    url_img = og_img.get('content')

            caminho_imagem = None
            if url_img:
                # Força o prefixo de alta definição (D_NQ_NP_2X_) e o sufixo -F (Full/Zoom) ou -O
                url_img = re.sub(r'/D_Q_NP_(?:2X_)?', '/D_NQ_NP_2X_', url_img)
                url_img = re.sub(r'/D_NQ_NP_(?!2X_)', '/D_NQ_NP_2X_', url_img)
                url_img = re.sub(r'-[a-zA-Z](-[^/]+)?\.(jpg|jpeg|png|webp)$', r'-F\1.\2', url_img)
                
                print(f"   [Mercado Livre] URL da imagem forçada para Alta Resolução (2X Zoom): {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # --- 3. DESCRIÇÃO ---
            print("   [Mercado Livre] A extrair Descrição...")
            descricao_bruta = ""
            desc_tag = soup.find('p', class_=re.compile(r'ui-pdp-description__content'))
            if desc_tag:
                for br in desc_tag.find_all("br"): br.replace_with("\n")
                descricao_bruta = desc_tag.get_text(separator="\n")
            
            descricao = self.limpar_descricao_ml(descricao_bruta)

            # --- 4. FICHA TÉCNICA ---
            print("   [Mercado Livre] A extrair Ficha Técnica...")
            specs = {}
            tabelas = soup.find_all('table', class_=re.compile(r'andes-table'))
            
            for tabela in tabelas:
                linhas = tabela.find_all('tr')
                for linha in linhas:
                    th = linha.find('th')
                    td = linha.find('td')
                    
                    if th and td:
                        chave = self.limpar_texto(th.get_text())
                        valor = self.limpar_texto(td.get_text())
                        
                        ignorar = False
                        termos_proibidos = ["garantia", "código universal", "sku", "ean", "gtin", "condição", "quantidade"]
                        if any(t in chave.lower() for t in termos_proibidos):
                            ignorar = True
                            
                        if not ignorar and chave and valor:
                            specs[chave] = valor

            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)
            print(f"   [OK] Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO E CORREÇÃO DE PDF ---
            # TRUQUE PARA O PDF: Forçar o caminho absoluto e inverter as barras para o padrão Web/PDF
            if caminho_imagem and os.path.exists(caminho_imagem):
                caminho_absoluto = os.path.abspath(caminho_imagem)
                caminho_imagem = caminho_absoluto.replace("\\", "/")

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [Mercado Livre] A gerar PDF e Word instantâneos...")
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
            print(f"   [ERRO MERCADO LIVRE] {e}")
            return {'sucesso': False, 'erro': str(e)}

    def limpar_descricao_ml(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        termos_proibidos = [
            "garantia", "mercado envio", "mercado pago", "tire suas dúvidas", 
            "perguntas", "clique em comprar", "aguardamos sua compra", "frete", 
            "atendimento", "nota fiscal", "nf-e", "pronta entrega", "devolução grátis"
        ]
        
        for linha in linhas:
            linha_lower = linha.lower().strip()
            if not linha_lower: continue
            if any(termo in linha_lower for termo in termos_proibidos): continue
            linhas_limpas.append(linha.strip())
            
        return "\n\n".join(linhas_limpas)