# scrapers/mercado_livre.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class MercadoLivreScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [ML] Iniciando Scraper (Motor de Extração HTML + Imagens Alta Resolução)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            
            options.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")}')
            
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)
            
            print(f"   [ML] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            # --- VERIFICAÇÃO DE CAPTCHA INTERATIVA ---
            time.sleep(3) 
            if "verifique que você não é um robô" in driver.page_source.lower() or "recaptcha" in driver.page_source.lower():
                print("   🚨 [ALERTA] MERCADO LIVRE PEDIU CAPTCHA!")
                print("   ⏳ O robô vai pausar por 25 SEGUNDOS. Resolva o Captcha na janela do Chrome AGORA!")
                time.sleep(25)
                print("   ▶️ Retomando a extração...")
            
            print("   [ML] Aguardando renderização inicial...")
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .ui-pdp-title")))
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. Tentando continuar.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [ML] Vasculhando a página para acionar o Lazy Load...")
            for i in range(8):
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(1.5)
            
            # --- DESTRUIDOR DE BOTÕES (Abre as Características Ocultas) ---
            print("   [ML] Forçando a renderização de elementos ocultos...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('.ui-pdp-action-modal__link, [data-testid="action-modal-link"], .ui-pdp-collapsable__action');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var txt = botoes[i].innerText.toLowerCase();
                        if(txt.includes('características') || txt.includes('descrição') || txt.includes('ver mais')) {
                            // Bloqueia a navegação para impedir que o site fuja da página
                            botoes[i].addEventListener('click', function(e){ e.preventDefault(); });
                            try { botoes[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(3)
            
            driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(0.5)

            # Usa o código-fonte cru para ignorar problemas de visibilidade CSS
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Mercado Livre"
            h1 = soup.find('h1', class_=re.compile(r'ui-pdp-title'))
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO (EXTRATOR DIRETO DO HTML) ---
            print("   [ML] Extraindo Descrição...")
            descricao = "Descrição indisponível."
            descricao_bruta = ""
            
            desc_tag = soup.find(class_=re.compile(r'ui-pdp-description__content'))
            if not desc_tag:
                desc_tag = soup.find('div', id='description')
                
            if desc_tag:
                for br in desc_tag.find_all("br"): br.replace_with("\n")
                descricao_bruta = desc_tag.get_text(separator="\n", strip=True)

            if not descricao_bruta or len(descricao_bruta.strip()) < 15:
                descricao_bruta = driver.execute_script("""
                    var desc = document.querySelector('.ui-pdp-description__content, #description');
                    if (desc) return desc.textContent;
                    return '';
                """)

            if descricao_bruta and len(descricao_bruta.strip()) > 15:
                descricao = self.limpar_lixo_comercial(descricao_bruta.strip())
                print("   ✅ Descrição capturada com sucesso.")
            else:
                print("   ⚠️ Aviso: Mercado Livre não renderizou a descrição nesta página.")

            # --- CARACTERÍSTICAS TÉCNICAS (EXTRATOR DE TABELAS 'andes-table') ---
            print("   [ML] Extraindo Ficha Técnica...")
            specs = {}
            
            tabelas = soup.find_all('table', class_=re.compile(r'andes-table|ui-vpp-striped-specs'))
            for tabela in tabelas:
                linhas = tabela.find_all('tr')
                for linha in linhas:
                    th = linha.find('th')
                    td = linha.find('td')
                    if th and td:
                        chave = self.limpar_texto(th.get_text(separator=" ", strip=True))
                        valor = self.limpar_texto(td.get_text(separator=" ", strip=True))
                        if chave and valor:
                            specs[chave] = valor
            
            if not specs:
                try:
                    specs_dict = driver.execute_script("""
                        var specs = {};
                        var rows = document.querySelectorAll('tr.andes-table__row, tr.ui-vpp-striped-specs__row');
                        rows.forEach(r => {
                            var th = r.querySelector('th');
                            var td = r.querySelector('td');
                            if(th && td) {
                                var key = th.textContent.trim();
                                var val = td.textContent.trim();
                                if(key && val && key !== val) {
                                    specs[key] = val;
                                }
                            }
                        });
                        return specs;
                    """)
                    if specs_dict:
                        for k, v in specs_dict.items():
                            chave_limpa = self.limpar_texto(k)
                            valor_limpo = self.limpar_texto(v)
                            if chave_limpa and valor_limpo:
                                specs[chave_limpa] = valor_limpo
                except: pass

            specs_limpas = {}
            termos_proibidos = ["garantia", "devolução", "frete", "prazo"]
            for k, v in specs.items():
                if not any(t in k.lower() for t in termos_proibidos):
                    specs_limpas[k] = v
                    
            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs_limpas)
            else:
                specs = specs_limpas
                
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- IMAGEM DE ALTA RESOLUÇÃO ---
            print("   [ML] Extraindo Imagem em Alta Resolução...")
            url_img = None
            caminho_imagem = None
            
            # 1. Procura as imagens principais e tenta capturar a versão com "Zoom" (Alta Qualidade)
            imagens = soup.find_all('img', class_=re.compile(r'ui-pdp-image|ui-pdp-gallery__figure__image'))
            for img in imagens:
                src = img.get('data-zoom') or img.get('src')
                # Ignora os quadrados cinzas em base64 que o ML carrega primeiro
                if src and not src.startswith("data:image"):
                    url_img = src
                    break
                
            # 2. Tenta pelo meta tag caso não ache
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                # 3. TRUQUE DO MERCADO LIVRE:
                # O ML utiliza o último caractere antes da extensão para definir o tamanho da foto.
                # Exemplo: -I (Pequena), -F (Média/Full), -V (Variação).
                # Vamos substituir a letra final por -O.jpg, que força o servidor a devolver o tamanho "Original"!
                url_img = re.sub(r'-[a-zA-Z]\.(jpg|jpeg|png|webp)$', '-O.jpg', url_img)
                
                print(f"   [ML] URL da imagem GIGANTE encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [ML] Apelando para o Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "figure.ui-pdp-gallery__figure img, img.ui-pdp-image")
                    if el_img:
                        filename = f"temp_img_ml_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except:
                    pass

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [ML] Gerando arquivos PDF/Word...")
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
            print(f"   ❌ [ERRO ML] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass