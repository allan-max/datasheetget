# scrapers/kabum.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class KabumScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [KaBuM!] Iniciando Scraper (V4 - Descrição Preservada e Filtro Inteligente)...")
            
            # --- SETUP ---
            if not hasattr(self, 'pasta_saida'): self.pasta_saida = "output"
            if not os.path.exists(self.pasta_saida): os.makedirs(self.pasta_saida)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)
            
            # 1. ACESSO
            print(f"   [KaBuM!] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
            except:
                print("   ⚠️ Timeout título.")

            # Scroll progressivo para forçar o Lazy Load
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)
            
            # Destruidor de Botões de "Ver Mais"
            driver.execute_script("""
                var botoes = document.querySelectorAll('button, a, span');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText && (botoes[i].innerText.toLowerCase().includes('mostrar descrição') || botoes[i].innerText.toLowerCase().includes('ver mais'))) {
                        try { botoes[i].click(); } catch(e) {}
                    }
                }
            """)
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 400);")

            # 2. EXTRAÇÃO
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto KaBuM!"
            h1 = soup.find("h1")
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [KaBuM!] Extraindo Descrição...")
            descricao = "Descrição indisponível."
            
            div_desc = soup.find("div", id="description") or soup.find("div", id="iframeContainer")
            if not div_desc:
                div_desc = soup.find('div', class_=re.compile(r'\[&_\*\]:text-sm|text-gray-800'))
            
            if div_desc:
                # Usa separator="\n" para garantir que cada tag HTML (como H2, H3, P) vai para a sua própria linha
                texto_bruto = div_desc.get_text(separator="\n", strip=True)
                descricao = self.limpar_descricao_promocional(texto_bruto)
                print("   ✅ Descrição processada.")

            # --- SPECS (FICHA TÉCNICA) ---
            specs = {}
            print("   [KaBuM!] Lendo especificações do novo layout...")
            
            info_divs = soup.find_all('div', attrs={"data-testid": re.compile(r"^Info")})
            for div in info_divs:
                ps = div.find_all(['p', 'span'])
                if len(ps) >= 2:
                    chave = self.limpar_texto(ps[0].get_text()).rstrip(':')
                    valor = self.limpar_texto(ps[1].get_text())
                    if chave and valor:
                        specs[chave] = valor

            divs_texto = soup.find_all('div', class_=re.compile(r'text-gray-800|\[&_\*\]'))
            for div in divs_texto:
                ps = div.find_all('p')
                for p in ps:
                    txt = self.limpar_texto(p.get_text(separator=" ", strip=True))
                    if not txt or txt == '-': continue
                    
                    if ':' in txt:
                        partes = txt.split(':', 1)
                        chave = self.limpar_texto(partes[0].lstrip('-').strip())
                        valor = self.limpar_texto(partes[1].strip())
                        
                        if chave and valor and len(chave) < 45:
                            specs[chave] = valor

            if not specs:
                blocos_specs = soup.find_all("div", class_=lambda c: c and "sc-" in c)
                for bloco in blocos_specs:
                    texto_bloco = bloco.get_text(separator=" ", strip=True)
                    if "garantia" in texto_bloco.lower(): continue
                    
                    paragrafos = bloco.find_all("p")
                    chave_atual = None
                    for p in paragrafos:
                        txt = self.limpar_texto(p.get_text())
                        if not txt: continue
                        
                        strong = p.find("strong") or p.find("b")
                        if strong:
                            chave_atual = self.limpar_texto(strong.get_text()).rstrip(":")
                        elif chave_atual:
                            specs[chave_atual] = txt
                            chave_atual = None

            specs_finais = {k: v for k, v in specs.items() if "garantia" not in k.lower()}
            
            if hasattr(self, 'filtrar_specs'):
                specs_finais = self.filtrar_specs(specs_finais)
                
            print(f"   ✅ Specs encontradas: {len(specs_finais)} itens.")

            # --- IMAGEM DE ALTA RESOLUÇÃO ---
            print("   [KaBuM!] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            slide_ativo = soup.find('div', class_=re.compile(r'swiper-slide-active'))
            if slide_ativo:
                img_tag = slide_ativo.find('img')
                if img_tag: url_img = img_tag.get('src')
            
            if not url_img:
                img_tag = soup.find('img', class_=re.compile(r'object-contain'))
                if img_tag: url_img = img_tag.get('src')
                
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                print(f"   [KaBuM!] URL da imagem encontrada: {url_img}")
                try:
                    caminho_imagem = self.baixar_imagem_temp(url_img)
                except AttributeError:
                    pass

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [KaBuM!] Recorrendo ao Screenshot...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    seletores_img = [
                        ".swiper-slide-active img",
                        "img.object-contain",
                        "figure img"
                    ]
                    el_img = None
                    for seletor in seletores_img:
                        elementos = driver.find_elements(By.CSS_SELECTOR, seletor)
                        for el in elementos:
                            if el.is_displayed() and el.size['width'] > 200:
                                el_img = el
                                break
                        if el_img: break
                    
                    if el_img:
                        filename = f"temp_img_kabum_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.pasta_saida, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print(f"   ✅ Imagem salva: {filename}")
                except:
                    pass

            # --- ARQUIVOS ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs_finais,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [KaBuM!] Gerando arquivos PDF/Word...")
            arquivos = self.gerar_arquivos_finais(dados)
            
            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs_finais,
                'total_imagens': 1 if caminho_imagem else 0,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO KABUM] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_promocional(self, texto):
        if not texto: return ""
        
        # Filtro de CTA (Call to Action) calibrado para ser menos agressivo
        ctas_proibidos = [
            "adquira o", "compre o", "no kabum", "na kabum", "acesse o site", 
            "clique aqui", "confira as ofertas", "aproveite as ofertas", "estoque", 
            "entrega rápida", "www.", ".com.br", "atendimento", "sac:", 
            "boleto bancário", "cartão de crédito", "parcelamento", "direitos reservados"
        ]
        
        linhas_limpas = []
        for linha in texto.splitlines():
            linha_clean = linha.strip()
            linha_lower = linha_clean.lower()
            
            if len(linha_lower) < 2: continue
            
            # Se for apenas a palavra kabum isolada ou um CTA agressivo
            if linha_lower == "kabum!" or linha_lower == "kabum": continue
            if any(bad in linha_lower for bad in ctas_proibidos):
                continue
                
            if linha_clean.startswith("- "):
                linha_clean = "• " + linha_clean[2:]
                
            linhas_limpas.append(linha_clean)
            
        # O \n\n garante que haverá espaçamento adequado entre os diferentes parágrafos e títulos
        return "\n\n".join(linhas_limpas)