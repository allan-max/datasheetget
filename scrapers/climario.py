# scrapers/climario.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class ClimarioScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Climario] A iniciar Scraper (Motor VTEX IO - Grelha de Especificações)...")
            
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
            
            print(f"   [Climario] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Climario] A aguardar renderização inicial...")
            try:
                # Aguarda pela classe de título padrão da VTEX IO ou o h1
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .vtex-store-components-3-x-productBrand"))
                )
            except:
                print("   ⚠️ Aviso: Título principal não encontrado rapidamente. A forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Climario] A executar rolagem para carregar descrições e imagens ocultas...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)
            
            # --- AUTO-CLICKER ---
            print("   [Climario] A ativar separadores de Descrição e Especificações...")
            driver.execute_script("""
                // Procura links e botões que ativam as diferentes áreas do produto
                var botoes = document.querySelectorAll('a, button, span, div');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto === 'descrição' || 
                            texto === 'especificações técnicas' || 
                            texto === 'especificações' || 
                            texto.includes('ver mais')) {
                            
                            if(botoes[i].tagName.toLowerCase() === 'a') {
                                botoes[i].removeAttribute('href'); // Impede navegação indesejada
                            }
                            try { botoes[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(2) # Aguarda a transição das abas
            
            driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Climario"
            h1 = soup.find(['h1', 'span'], class_=re.compile(r'productBrand|productNameContainer'))
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [Climario] A extrair Descrição...")
            descricao = "Descrição indisponível."
            try:
                descricao_bruta = driver.execute_script("""
                    var desc = document.querySelector('.vtex-store-components-3-x-productDescriptionText, .vtex-store-components-3-x-productDescriptionContainer');
                    if (desc) return desc.innerText;
                    return '';
                """)
                
                # Rede de segurança (Fallback em Python)
                if not descricao_bruta or len(descricao_bruta.strip()) < 15:
                    desc_bs4 = soup.find('div', class_=re.compile(r"productDescriptionText|productDescriptionContainer"))
                    if desc_bs4:
                        # Converte tags <br> em quebras de linha para manter a formatação original em lista
                        for br in desc_bs4.find_all("br"): br.replace_with("\n")
                        descricao_bruta = desc_bs4.get_text(separator="\n", strip=True)

                if descricao_bruta and len(descricao_bruta.strip()) > 15:
                    descricao = self.limpar_descricao_climario(descricao_bruta.strip())
                    print("   ✅ Descrição capturada e limpa com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a descrição.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair descrição: {e}")

            # --- CARACTERÍSTICAS TÉCNICAS (Grelha VTEX) ---
            print("   [Climario] A extrair Ficha Técnica...")
            specs = {}
            try:
                # Extração otimizada com Javascript focada nas classes específicas da VTEX
                specs_dict = driver.execute_script("""
                    var specs = {};
                    var names = document.querySelectorAll('.vtex-product-specifications-1-x-specificationName');
                    var values = document.querySelectorAll('.vtex-product-specifications-1-x-specificationValue');
                    
                    // Emparelha as chaves com os valores correspondentes
                    for(var i = 0; i < names.length; i++) {
                        if(names[i] && values[i]) {
                            var key = names[i].innerText.trim();
                            var val = values[i].innerText.trim();
                            if(key && val && key !== val) {
                                specs[key] = val;
                            }
                        }
                    }
                    
                    // Fallback para tabelas tradicionais (caso a página utilize outro formato)
                    if (Object.keys(specs).length === 0) {
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
                    }
                    return specs;
                """)
                
                if specs_dict:
                    for k, v in specs_dict.items():
                        chave_limpa = self.limpar_texto(k)
                        valor_limpo = self.limpar_texto(v)
                        
                        # Filtro VTEX Rigoroso
                        ignorar = False
                        termos_proibidos_specs = [
                            "garantia", "código modelo", "ean", "referência", 
                            "sku", "sac", "nota fiscal", "informações fornecidas"
                        ]
                        if any(t in chave_limpa.lower() or t in valor_limpo.lower() for t in termos_proibidos_specs):
                            ignorar = True

                        if not ignorar and chave_limpa and valor_limpo:
                            specs[chave_limpa] = valor_limpo
                            
                if hasattr(self, 'filtrar_specs'):
                    specs = self.filtrar_specs(specs)
                    
                print(f"   ✅ Specs encontradas: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair specs via JS: {e}")

            # --- IMAGEM ---
            print("   [Climario] A extrair Imagem em Alta Resolução...")
            url_img = None
            caminho_imagem = None
            
            img_container = soup.find('img', class_=re.compile(r'productImageTag--main|productImageTag'))
            if img_container:
                url_img = img_container.get('src')
                
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                # TRUQUE DE ALTA RESOLUÇÃO: Remove os parâmetros de tamanho e tracking do link (tudo após o "?")
                if "?" in url_img:
                    url_img = url_img.split("?")[0]
                print(f"   [Climario] URL da imagem original encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Climario] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[class*='productImageTag--main'], img[class*='productImageTag']")
                    if el_img:
                        filename = f"temp_img_climario_{int(time.time())}.png"
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

            print("   [Climario] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO CLIMARIO] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_climario(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        termos_proibidos = [
            "informações fornecidas pelo fabricante", "garantia", 
            "frete", "entrega", "pagamento", "boleto", 
            "cartão", "consulte o manual"
        ]

        for linha in linhas:
            linha_clean = linha.strip()
            # Remove linhas vazias consecutivas
            if not linha_clean:
                if linhas_limpas and linhas_limpas[-1] != "":
                    linhas_limpas.append("")
                continue

            linha_lower = linha_clean.lower()

            # Corta informações legais ou dados irrelevantes
            if any(termo in linha_lower for termo in termos_proibidos):
                continue 
            
            linhas_limpas.append(linha_clean)

        return "\n".join(linhas_limpas).strip()