# scrapers/kabum.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
from .base import BaseScraper

class KabumScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [KaBuM!] Iniciando Scraper (V2 - Limpeza de Marketing)...")
            
            # --- SETUP ---
            if not hasattr(self, 'pasta_saida'): self.pasta_saida = "output"
            if not os.path.exists(self.pasta_saida): os.makedirs(self.pasta_saida)

            options = uc.ChromeOptions()
            options.add_argument("--headless=new") 
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--disable-http2")
            options.add_argument("--window-size=1920,1080")

            driver = uc.Chrome(options=options, version_main=144)
            
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

            # Scroll para carregar
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1200);")
            time.sleep(1)

            # 2. EXTRAÇÃO
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto KaBuM!"
            h1 = soup.find("h1")
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   [DEBUG] Título: {titulo}")

            # --- IMAGEM (SCREENSHOT) ---
            caminho_imagem = None
            try:
                print("   [KaBuM!] Buscando imagem...")
                seletores_img = [
                    "figure img", 
                    "img.object-contain",
                    "img[title*='Fones']",
                    ".carousel__inner img"
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
                    filename = "temp_img_kabum.png"
                    caminho_imagem = os.path.join(self.pasta_saida, filename)
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                    time.sleep(1)
                    el_img.screenshot(caminho_imagem)
                    print(f"   ✅ Imagem salva: {filename}")

            except Exception as e:
                print(f"   ⚠️ Erro Imagem: {e}")

            # --- DESCRIÇÃO (COM LIMPEZA DE MARKETING) ---
            descricao = "Descrição indisponível."
            div_desc = soup.find("div", id="description")
            if not div_desc: div_desc = soup.find("div", id="iframeContainer")

            if div_desc:
                texto_bruto = div_desc.get_text(separator="\n", strip=True)
                # Aplica o filtro removedor de "Lixo Promocional"
                descricao = self.limpar_descricao_promocional(texto_bruto)

            # --- SPECS (SEM GARANTIA) ---
            specs = {}
            print("   [KaBuM!] Lendo especificações...")
            
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

            # Filtro de segurança final nas chaves
            specs_finais = {k: v for k, v in specs.items() if "garantia" not in k.lower()}
            print(f"   ✅ Specs encontradas: {len(specs_finais)} itens.")

            # --- ARQUIVOS ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs_finais,
                "caminho_imagem_temp": caminho_imagem
            }
            
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
            if driver: driver.quit()
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_promocional(self, texto):
        """Remove frases de marketing e CTAs do site"""
        if not texto: return ""
        
        # Palavras que, se encontradas na frase, eliminam a frase inteira
        palavras_proibidas = [
            "adquira", "compre", "kabum", "loja", "acesse", 
            "clique", "confira", "aproveite", "estoque", 
            "entrega", "garantia", "site", "www.", ".com.br",
            "atendimento", "sac", "boleto", "cartão", "parcelamento"
        ]
        
        linhas_limpas = []
        for linha in texto.splitlines():
            linha_lower = linha.lower().strip()
            
            # Se a linha for muito curta (lixo) ou tiver palavra proibida, pula
            if len(linha_lower) < 2: continue
            if any(bad in linha_lower for bad in palavras_proibidas):
                continue
                
            linhas_limpas.append(linha.strip())
            
        return "\n".join(linhas_limpas)