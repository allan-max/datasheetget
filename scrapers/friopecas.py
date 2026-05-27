# scrapers/friopecas.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class FrioPecasBot(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [FrioPecas] Iniciando Scraper (Motor Avançado e Expansão de Specs)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            opts = uc.ChromeOptions()
            opts.page_load_strategy = 'eager'
            opts.add_argument("--no-first-run")
            opts.add_argument("--password-store=basic")
            opts.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")}')
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            
            driver = uc.Chrome(options=opts, version_main=109)
            driver.minimize_window()

            print(f"   [FrioPecas] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. Tentando continuar.")
            
            # --- 1. ROLAGEM PROGRESSIVA (Lazy Load) ---
            print("   [FrioPecas] Vasculhando a página para carregar as secções...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)

            # --- 2. CLICAR NO BOTÃO DE CARACTERÍSTICAS (Sinal de +) ---
            print("   [FrioPecas] Abrindo painéis de Ficha Técnica...")
            driver.execute_script("""
                // Procura botões e painéis com a palavra Características ou Especificações
                var triggers = document.querySelectorAll('div, button, span, h2, h3');
                for (var i = 0; i < triggers.length; i++) {
                    var text = triggers[i].innerText ? triggers[i].innerText.toLowerCase().trim() : "";
                    if (text === 'características' || text === 'especificações' || text === 'especificações técnicas' || text === 'detalhes do produto') {
                        try { triggers[i].click(); } catch(e) {}
                    }
                }
                
                // Clica forçadamente em SVGs que servem de expansão nos layouts da VTEX
                var svgs = document.querySelectorAll('svg');
                for (var j = 0; j < svgs.length; j++) {
                    var parent = svgs[j].closest('[class*="disclosure"], [class*="accordion"]');
                    if (parent) {
                        try { parent.click(); } catch(e) {}
                    }
                }
            """)
            time.sleep(2) # Espera a animação de deslize abrir a lista
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- 3. TÍTULO ---
            title_div = soup.find(class_=re.compile(r"productName|vtex-store-components-3-x-productNameContainer"))
            if not title_div: title_div = soup.find('h1')
            titulo = self.limpar_texto(title_div.get_text()) if title_div else "Produto FrioPeças"
            print(f"   ✅ Título capturado: {titulo}")

            # --- 4. DESCRIÇÃO ---
            print("   [FrioPecas] Extraindo Descrição...")
            descricao = "Descrição indisponível."
            desc_div = soup.find(class_=re.compile(r"productDescriptionText|productDescription|fluid-text"))
            if desc_div:
                for br in desc_div.find_all("br"): br.replace_with("\n")
                desc_texto = desc_div.get_text(separator='\n', strip=True)
                if len(desc_texto) > 10:
                    descricao = self.limpar_lixo_comercial(desc_texto)
                    print("   ✅ Descrição capturada.")

            # --- 5. FICHA TÉCNICA (EXTRAÇÃO AVANÇADA JS) ---
            print("   [FrioPecas] Extraindo Ficha Técnica...")
            specs = {}
            try:
                specs_dict = driver.execute_script("""
                    var specs = {};
                    
                    // Estratégia A: Estrutura <ul><li><span>Chave</span><span>Valor</span></li></ul> que a FrioPeças usa
                    var listItems = document.querySelectorAll('ul > li, [class*="specifications"] li, [class*="characteristics"] li');
                    listItems.forEach(li => {
                        // Pega os span que são filhos diretos do li
                        var spans = li.querySelectorAll(':scope > span');
                        if(spans.length >= 2) {
                            var key = spans[0].innerText.trim();
                            var val = spans[1].innerText.trim();
                            if(key && val && key !== val) specs[key] = val;
                        }
                    });
                    
                    // Estratégia B: Estrutura de Tabelas Clássica VTEX (Garante compatibilidade com outras páginas)
                    var rows = document.querySelectorAll('tr');
                    rows.forEach(r => {
                        var th = r.querySelector('th');
                        var td = r.querySelector('td');
                        if(th && td) {
                            var key = th.innerText.trim();
                            var val = td.innerText.trim();
                            if(key && val && key !== val) specs[key] = val;
                        }
                    });
                    return specs;
                """)
                
                if specs_dict:
                    for k, v in specs_dict.items():
                        chave_limpa = self.limpar_texto(k)
                        valor_limpo = self.limpar_texto(v)
                        
                        # Filtro de Lixo Comercial
                        ignorar = False
                        termos_proibidos_specs = ["garantia", "manutenção", "sac", "nota fiscal", "assistência", "pagamento"]
                        if any(t in chave_limpa.lower() or t in valor_limpo.lower() for t in termos_proibidos_specs):
                            ignorar = True
                            
                        if not ignorar and chave_limpa and valor_limpo:
                            specs[chave_limpa] = valor_limpo
                            
                if hasattr(self, 'filtrar_specs'):
                    specs = self.filtrar_specs(specs)
                    
                print(f"   ✅ Specs encontradas: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair specs via JS: {e}")

            # --- 6. IMAGEM ---
            print("   [FrioPecas] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            img = soup.find("img", class_=re.compile(r"productImageTag--main"))
            if img: url_img = img.get("src")
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                caminho_imagem = self.baixar_imagem_temp(url_img)
                
            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [FrioPecas] Apelando para o Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[class*='productImageTag--main'], img[class*='productImage']")
                    if el_img:
                        filename = f"temp_img_friopecas_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1.5)
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

            print("   [FrioPecas] Gerando arquivos PDF/Word...")
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
            print(f"   ❌ [ERRO FRIOPECAS] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver: driver.quit()