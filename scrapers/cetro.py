# scrapers/cetro.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class CetroScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Cetro] A iniciar Scraper (Motor VTEX IO com Escudo de Rodapé Máximo)...")
            
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
            
            print(f"   [Cetro] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Cetro] A aguardar renderização inicial...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .vtex-store-components-3-x-productBrand"))
                )
            except:
                print("   ⚠️ Aviso: H1 principal não encontrado rapidamente. A forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Cetro] A executar rolagem para carregar descrições e módulos ocultos...")
            for i in range(6):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)
            
            # --- AUTO-CLICKER ---
            print("   [Cetro] A expandir abas de Especificações e Descrição...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('button, a, span, div, h2, h3');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto === 'especificações' || 
                            texto === 'especificações técnicas' || 
                            texto.includes('ver mais') || 
                            texto === 'descrição') {
                            
                            if(botoes[i].tagName.toLowerCase() === 'a') {
                                botoes[i].removeAttribute('href');
                            }
                            try { botoes[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(2)
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Cetro"
            h1 = soup.find(['h1', 'span'], class_=re.compile(r'productBrand|productNameContainer'))
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [Cetro] A extrair Descrição Limpa...")
            descricao = "Descrição indisponível."
            try:
                descricao_bruta = driver.execute_script("""
                    var text = '';
                    
                    // 1. Apanha a descrição principal
                    var desc = document.querySelector('.vtex-store-components-3-x-productDescriptionText, .productDescription');
                    if (desc && desc.innerText.trim().length > 15) {
                        text += desc.innerText.trim() + '\\n\\n';
                    }
                    
                    // 2. Apanha blocos de Rich Text, IGNORANDO os que pertencem à Ficha Técnica
                    var richTexts = document.querySelectorAll('.vtex-rich-text-0-x-paragraph');
                    richTexts.forEach(p => {
                        var pText = p.innerText.trim();
                        var pClass = p.className || "";
                        
                        // Impede que características técnicas (ex: Voltagem, Peso) contaminem a descrição
                        if (pClass.includes('-title') || pClass.includes('-description')) {
                            if (!pClass.includes('special-details')) {
                                return; // É uma spec técnica, ignora!
                            }
                        }
                        
                        if (pText.length > 4 && !text.includes(pText)) {
                            if (pText.length < 60) {
                                text += '• ' + pText + '\\n';
                            } else {
                                text += pText + '\\n\\n';
                            }
                        }
                    });
                    
                    return text.trim();
                """)
                
                # Fallback em Python
                if not descricao_bruta or len(descricao_bruta.strip()) < 15:
                    desc_bs4 = soup.find('div', class_=re.compile(r"productDescriptionText"))
                    if desc_bs4:
                        for br in desc_bs4.find_all("br"): br.replace_with("\n")
                        descricao_bruta = desc_bs4.get_text(separator="\n", strip=True)

                if descricao_bruta and len(descricao_bruta.strip()) > 10:
                    descricao = self.limpar_descricao_cetro(descricao_bruta.strip())
                    print("   ✅ Descrição formatada com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a descrição.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair descrição: {e}")

            # --- CARACTERÍSTICAS TÉCNICAS (Híbridas) ---
            print("   [Cetro] A extrair Ficha Técnica Dupla...")
            specs = {}
            try:
                specs_dict = driver.execute_script("""
                    var specs = {};
                    
                    // 1. Extrai a Tabela VTEX Tradicional
                    var names = document.querySelectorAll('.vtex-product-specifications-1-x-specificationName');
                    var values = document.querySelectorAll('.vtex-product-specifications-1-x-specificationValue');
                    for(var i = 0; i < names.length; i++) {
                        if(names[i] && values[i]) {
                            specs[names[i].innerText.trim()] = values[i].innerText.trim().replace(/\\n/g, '; ');
                        }
                    }
                    
                    // 2. Extrai as Especificações "Escondidas" nos blocos Visuais (Ex: Tensão, Consumo, etc)
                    var gridTitles = document.querySelectorAll('p[class*="-title"]');
                    gridTitles.forEach(t => {
                        var key = t.innerText.trim();
                        // Ignora títulos muito longos que são na verdade subtítulos de marketing
                        if(key.length > 40) return; 
                        
                        // Procura o valor correspondente dentro da mesma coluna
                        var container = t.closest('.vtex-flex-layout-0-x-flexCol');
                        if(container) {
                            var desc = container.querySelector('p[class*="-description"]');
                            if(desc) {
                                specs[key] = desc.innerText.trim().replace(/\\n/g, '; ');
                            }
                        }
                    });
                    
                    return specs;
                """)
                
                if specs_dict:
                    for k, v in specs_dict.items():
                        chave_limpa = self.limpar_texto(k)
                        valor_limpo = self.limpar_texto(v)
                        
                        ignorar = False
                        termos_proibidos_specs = ["garantia", "ean", "referência", "sku", "sac", "vídeo"]
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
            print("   [Cetro] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_container = soup.find('img', class_=re.compile(r'productImageTag--main|productImageTag'))
            if img_container:
                url_img = img_container.get('src')
                
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                if "?" in url_img:
                    url_img = url_img.split("?")[0]
                print(f"   [Cetro] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Cetro] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[class*='productImageTag--main'], img[class*='productImageTag']")
                    if el_img:
                        filename = f"temp_img_cetro_{int(time.time())}.png"
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

            print("   [Cetro] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO CETRO] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_cetro(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        # A LISTA NEGRA MAXIMIZADA DA CETRO (Elimina Rodapés, Marketing e Lojas)
        termos_proibidos = [
            "garantia", "frete", "entrega", "pagamento", "boleto", 
            "cartão", "consulte o manual", "assistência técnica",
            "fale com um consultor", "compre agora",
            "fale com um vendedor", "suporte e assistência",
            "compre nas lojas", "produtos relacionados",
            "matriz bauru", "loja são paulo", "loja rio de janeiro",
            "loja belo horizonte", "telefone:", "cetro machines",
            "china office", "compromisso permanente com o planeta",
            "energia 100% limpa", "iniciativas são apenas o começo",
            "próximas gerações", "newton prado", "professor luiz ignácio",
            "são januário", "r. manaus", "zipcode", "danan street",
            "china factory", "0800", "@cetro.com.br", "de segunda à sexta",
            "atendimento filiais", "quem somos", "nossas lojas", "carreiras",
            "blog da cetro", "programa de afiliados", "cetrox", "cetro duty",
            "packblox", "suprême", "c-office", "c-res7", "privacidade de uso",
            "a cetro valoriza a privacidade", "pague com segurança",
            "compre com tranquilidade", "rastreamento de pedidos", 
            "São Paulo: (11) 3514-2600", "Rio de Janeiro: (21) 3952-5970",
            "Belo Horizonte: (31) 2116 2300"
        ]

        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean:
                # Mantém apenas um espaço em branco para dividir parágrafos
                if linhas_limpas and linhas_limpas[-1] != "":
                    linhas_limpas.append("")
                continue

            linha_lower = linha_clean.lower()

            if any(termo in linha_lower for termo in termos_proibidos):
                continue 
            
            linhas_limpas.append(linha_clean)

        # Junta tudo e remove espaços em branco excessivos (limita a 2 quebras de linha no máximo)
        resultado = "\n".join(linhas_limpas)
        resultado = re.sub(r'\n{3,}', '\n\n', resultado)
        
        return resultado.strip()