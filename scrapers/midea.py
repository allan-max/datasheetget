# scrapers/midea.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class MideaScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Midea] A iniciar Scraper (Motor de Extração React/Next.js)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")}')
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)
            
            print(f"   [Midea] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Midea] A aguardar renderização inicial...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1, [class*='ProductInfo_name']"))
                )
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. A forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Midea] A vasculhar a página para contornar o Lazy Load...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)
            
            # --- AUTO-CLICKER ---
            print("   [Midea] A expandir Descrição e Especificações Técnicas...")
            driver.execute_script("""
                // 1. Clicar no botão 'Ver mais' da descrição
                var btnDesc = document.querySelector('[class*="AccordionPdp_viewButton"], [class*="ProductInfo_moreDetails"]');
                if(btnDesc) { try { btnDesc.click(); } catch(e) {} }
                
                // 2. Clicar na tab de 'Especificações'
                var btnSpecs = document.querySelector('[aria-label="Especificações"], [data-testid="fs-accordion-button"]');
                if(btnSpecs) { try { btnSpecs.click(); } catch(e) {} }
                
                // 3. Fallback genérico para outros botões
                var botoes = document.querySelectorAll('button, span, div');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto === 'ver mais' || texto === 'especificações' || texto.includes('ver mais detalhes')) {
                            try { botoes[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(2) # Aguarda a animação de abertura
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Midea"
            h1 = soup.find('h1', class_=re.compile(r'ProductInfo_name'))
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [Midea] A extrair Descrição...")
            descricao_bruta = ""
            
            # Parte 1: Extrair os Bullets de Destaque
            bullets = soup.find('ul', class_=re.compile(r'ProductInfo_bullets'))
            if bullets:
                linhas_bullets = []
                for li in bullets.find_all('li'):
                    texto_li = li.get_text(separator=" ", strip=True)
                    # Ignorar o botão de "ver mais detalhes" que vem dentro do <li>
                    if texto_li and "ver mais detalhes" not in texto_li.lower():
                        linhas_bullets.append(f"• {texto_li}")
                if linhas_bullets:
                    descricao_bruta += "Destaques do Produto:\n" + "\n".join(linhas_bullets) + "\n\n"

            # Parte 2: Extrair a Descrição Completa
            desc_completa = soup.find('div', id='pdp-desc-full')
            if not desc_completa:
                desc_completa = soup.find('div', class_=re.compile(r'AccordionPdp_shortDescription'))
                
            if desc_completa:
                # O texto na Midea geralmente vem num <span> ou vários <span> seguidos
                texto_desc = desc_completa.get_text(separator="\n\n", strip=True)
                if texto_desc:
                    descricao_bruta += texto_desc

            descricao = self.limpar_descricao_midea(descricao_bruta)
            if descricao and descricao != "Descrição indisponível.":
                print("   ✅ Descrição capturada e limpa com sucesso.")
            else:
                print("   ⚠️ Aviso: Não foi possível extrair a descrição.")

            # --- CARACTERÍSTICAS TÉCNICAS ---
            print("   [Midea] A extrair Ficha Técnica...")
            specs = {}
            try:
                # A Midea usa um layout de tabela onde cada linha pode ter várias células de key-value
                # A chave tem classe AccordionPdp_specsName e o valor AccordionPdp_specsValue
                tds = soup.find_all('td', class_=re.compile(r'AccordionPdp_tableSpecs'))
                
                for td in tds:
                    # Ignorar colunas invisíveis de espaçamento
                    if td.get('aria-hidden') == 'true':
                        continue
                        
                    nome_tag = td.find('span', class_=re.compile(r'AccordionPdp_specsName'))
                    valor_tag = td.find('span', class_=re.compile(r'AccordionPdp_specsValue'))
                    
                    if nome_tag and valor_tag:
                        chave = self.limpar_texto(nome_tag.get_text(strip=True))
                        valor = self.limpar_texto(valor_tag.get_text(strip=True))
                        if chave and valor:
                            specs[chave] = valor
                            
                # Fallback JS se a busca HTML falhar
                if not specs:
                    specs_dict = driver.execute_script("""
                        var specs = {};
                        var names = document.querySelectorAll('[class*="AccordionPdp_specsName"]');
                        var values = document.querySelectorAll('[class*="AccordionPdp_specsValue"]');
                        for(var i = 0; i < names.length; i++) {
                            if(names[i] && values[i]) {
                                var key = names[i].innerText.trim();
                                var val = values[i].innerText.trim();
                                if(key && val) specs[key] = val;
                            }
                        }
                        return specs;
                    """)
                    if specs_dict:
                        for k, v in specs_dict.items():
                            specs[self.limpar_texto(k)] = self.limpar_texto(v)

                # Limpeza rigorosa
                specs_limpas = {}
                termos_proibidos_specs = ["garantia", "ean", "sku"]
                for k, v in specs.items():
                    k_lower = k.lower()
                    if not any(t in k_lower for t in termos_proibidos_specs):
                        specs_limpas[k] = v
                
                specs = specs_limpas
                if hasattr(self, 'filtrar_specs'):
                    specs = self.filtrar_specs(specs)
                    
                print(f"   ✅ Specs encontradas: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair specs: {e}")

            # --- IMAGEM ---
            print("   [Midea] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            # Prioriza a imagem em alta resolução (data-zoom) da galeria da Midea
            img_tag = soup.find('img', class_=re.compile(r'components_productImage'))
            if img_tag:
                url_img = img_tag.get('data-zoom') or img_tag.get('src')
                
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                print(f"   [Midea] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Midea] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "div[class*='components_imageViewerWrapper'] img")
                    if el_img:
                        filename = f"temp_img_midea_{int(time.time())}.png"
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

            print("   [Midea] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO MIDEA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_midea(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        # Filtro de regras de negócio B2B, garantias e logísticas
        termos_proibidos = [
            "para compras com cnpj", "faturamos apenas para cadastros isentos",
            "garantia", "frete", "entrega", "pagamento", "boleto", 
            "cartão", "consulte o manual"
        ]

        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean:
                continue

            linha_lower = linha_clean.lower()

            # Bloqueia a linha se detetar qualquer termo proibido
            if any(termo in linha_lower for termo in termos_proibidos):
                continue 
            
            linhas_limpas.append(linha_clean)

        return "\n\n".join(linhas_limpas)