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
            options.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")}')
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
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1, [data-testid='dsvia-base-div']"))
                )
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. A forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Casas Bahia] A vasculhar a página para contornar o Lazy Load...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)
            
            # --- AUTO-CLICKER DUPLO (Ver Mais + Especificações) ---
            print("   [Casas Bahia] A expandir botões e separadores da Ficha Técnica...")
            driver.execute_script("""
                // 1. Clica no botão "Ver mais" das características
                var btnVerMais = document.querySelector('[data-cy="product-characteristics-see-more"]');
                if(btnVerMais) { try { btnVerMais.click(); } catch(e) {} }
                
                // 2. Procura e clica no separador "Especificações Técnicas"
                var textos = document.querySelectorAll('p, div, button, span');
                for (var i = 0; i < textos.length; i++) {
                    if(textos[i].innerText) {
                        var textoLimpo = textos[i].innerText.trim().toLowerCase();
                        if (textoLimpo === 'especificações técnicas' || textoLimpo === 'características') {
                            try { textos[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(2) # Aguarda a animação de abertura das abas
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Casas Bahia"
            h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [Casas Bahia] A extrair Descrição...")
            descricao = "Descrição indisponível."
            try:
                descricao_bruta = ""
                # Procura a caixa principal de conteúdo especial
                container_desc = soup.find('div', attrs={"data-component": "special-content"})
                
                if container_desc:
                    # Junta todos os parágrafos e títulos, ignorando imagens
                    textos_desc = container_desc.find_all(['h2', 'h3', 'p', 'li'])
                    linhas_desc = []
                    for t in textos_desc:
                        texto = t.get_text(separator=" ", strip=True)
                        if texto and len(texto) > 3:
                            linhas_desc.append(texto)
                    descricao_bruta = "\n\n".join(linhas_desc)
                else:
                    # Fallback via Javascript caso a classe mude
                    descricao_bruta = driver.execute_script("""
                        var desc = document.querySelector('[id="descricao"], [data-component="special-content"], .product-description');
                        if (desc) return desc.innerText;
                        return '';
                    """)

                if descricao_bruta and len(descricao_bruta.strip()) > 15:
                    descricao = self.limpar_descricao_casasbahia(descricao_bruta.strip())
                    print("   ✅ Descrição capturada e limpa com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a descrição.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair descrição: {e}")

            # --- CARACTERÍSTICAS TÉCNICAS ---
            print("   [Casas Bahia] A extrair Ficha Técnica...")
            specs = {}
            try:
                # O site das Casas Bahia usa uma estrutura de Flexbox onde o <p> é a chave e o <span> é o valor
                caixas_flex = soup.find_all('div', attrs={"data-testid": "dsvia-base-div"})
                
                for caixa in caixas_flex:
                    # Verifica se tem a classe 'dsvia-flex' e não é o cabeçalho
                    if 'dsvia-flex' in caixa.get('class', []):
                        p_tag = caixa.find('p')
                        span_tag = caixa.find('span')
                        
                        if p_tag and span_tag:
                            chave = self.limpar_texto(p_tag.get_text())
                            # Substitui quebras de linha dentro do span por vírgulas ou espaços
                            for br in span_tag.find_all("br"): br.replace_with("; ")
                            valor = self.limpar_texto(span_tag.get_text(separator=" ", strip=True))
                            
                            if chave and valor:
                                specs[chave] = valor
                
                # Limpeza rigorosa
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
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair specs: {e}")

            # --- IMAGEM ---
            print("   [Casas Bahia] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            # Procura imagens na galeria
            img_tags = soup.find_all('img')
            for img in img_tags:
                src = img.get('src') or img.get('data-src')
                # Ignora logos e ícones, foca nas imagens do produto
                if src and ('casasbahia.com.br' in src) and ('/special-contents/' not in src) and ('/icon' not in src):
                    url_img = src
                    break

            if url_img:
                # TRUQUE DE ALTA RESOLUÇÃO: Remove o limitador de tamanho da Casas Bahia (?imwidth=500)
                if "?imwidth" in url_img or "?width" in url_img:
                    url_img = url_img.split("?")[0]
                    
                print(f"   [Casas Bahia] URL da imagem original encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Casas Bahia] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[alt*='Imagem do produto'], img[alt*='produto']")
                    if el_img:
                        filename = f"temp_img_cb_{int(time.time())}.png"
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