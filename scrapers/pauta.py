# scrapers/pauta.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class PautaScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Pauta] Iniciando Scraper (Motor Avançado e Busca Específica)...")
            
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

            print(f"   [Pauta] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            try:
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. Tentando continuar.")

            # --- ROLAGEM PROGRESSIVA (Lazy Load) ---
            print("   [Pauta] Vasculhando a página...")
            for i in range(4):
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)
                
            driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Pauta"
            h1 = soup.find("h1", class_=re.compile(r"title|nome-produto"))
            if not h1: h1 = soup.find("h1")
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO (BUSCA CIRÚRGICA JS E BS4) ---
            print("   [Pauta] Extraindo Descrição...")
            descricao = "Descrição indisponível."
            try:
                descricao_bruta = driver.execute_script("""
                    // Aponta diretamente para a classe que a Pauta usa
                    var desc = document.querySelector('.full-desc-Pro, .descricao, #descricao-produto');
                    if(desc && desc.innerText.length > 15) return desc.innerText;
                    
                    // Fallback
                    var headers = document.querySelectorAll('h2, h3, h4');
                    for(var i=0; i<headers.length; i++) {
                        var t = headers[i].innerText.toLowerCase().trim();
                        if(t === 'descrição' || t === 'sobre o produto' || t === 'características') {
                            var next = headers[i].nextElementSibling;
                            if(next && next.innerText.length > 15) return next.innerText;
                        }
                    }
                    return '';
                """)
                
                # Fallback em Python se o JS não pegar
                if not descricao_bruta or len(descricao_bruta) < 15:
                    desc_tag = soup.find(class_=re.compile(r"full-desc-Pro"))
                    if desc_tag:
                        for br in desc_tag.find_all("br"): br.replace_with("\n")
                        descricao_bruta = desc_tag.get_text(separator="\n", strip=True)

                if descricao_bruta and len(descricao_bruta.strip()) > 10:
                    descricao = self.limpar_descricao_cirurgica(descricao_bruta.strip())
                    print("   ✅ Descrição capturada e limpa com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a descrição.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair descrição via JS: {e}")

            # --- IMAGEM ---
            print("   [Pauta] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            img = soup.find("img", id="cloudZoomImage")
            if not img: img = soup.find("img", class_=re.compile(r"imagem-produto|product-image"))
            
            if img: 
                url_img = img.get("src") or img.get("data-src")
                
            if url_img:
                if url_img.startswith("/"): url_img = "https://www.pauta.com.br" + url_img
                print(f"   [Pauta] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Pauta] Apelando para o Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img#cloudZoomImage, img[class*='product-image']")
                    if el_img:
                        filename = f"temp_img_pauta_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except:
                    pass

            # --- FICHA TÉCNICA ---
            print("   [Pauta] Extraindo Ficha Técnica...")
            specs = {}
            table = soup.find("table", class_=re.compile(r"features-list|table"))
            
            if not table:
                for tb in soup.find_all("table"):
                    if len(tb.find_all("tr")) > 3:
                        table = tb
                        break
            
            if table:
                for row in table.find_all("tr"):
                    cols = row.find_all(["th", "td"])
                    if len(cols) >= 2:
                        k = self.limpar_texto(cols[0].get_text())
                        v = self.limpar_texto(cols[1].get_text())
                        if k and v:
                            specs[k] = v
            
            # Executa o JS como plano B para apanhar as tabelas
            if not specs:
                specs_dict = driver.execute_script("""
                    var specs = {};
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
                        k_limpo = self.limpar_texto(k)
                        v_limpo = self.limpar_texto(v)
                        if k_limpo and v_limpo:
                            specs[k_limpo] = v_limpo

            # Limpeza cirúrgica de specs
            specs_limpas = {}
            ignorar = ["garantia", "ncm", "ean", "conteudo", "dimensao", "peso", "código"]
            for k, v in specs.items():
                k_lower = k.lower()
                if not any(x in k_lower for x in ignorar):
                    specs_limpas[k] = v

            specs = specs_limpas
            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)
                
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [Pauta] Gerando arquivos PDF/Word...")
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
            print(f"   ❌ [ERRO CRÍTICO PAUTA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_cirurgica(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        texto_limpo = re.sub(r'\s+', ' ', texto_bruto).strip()
        
        # Divide por pontuação para analisar frase a frase
        frases = re.split(r'(?<=[.!?])\s+', texto_limpo)
        frases_uteis_finais = []
        
        # Lista Negra de termos
        termos_proibidos_frase = [
            "garantia", "devolução", "troca", "frete", "entrega", 
            "condição de venda", "pagamento", "boleto", "cartão",
            "preço", "oferta", "promoção", "estoque", "disponível",
            "pauta", "loja", "site", "fale conosco", "televendas", 
            "atendimento", "sac", "telefone", "(19)", "cnpj", 
            "endereço", "horário", "segunda à sexta", "segunda a sexta",
            "todos os direitos", "copyright", "aviso legal"
        ]

        for frase in frases:
            frase_lower = frase.lower()
            tem_lixo = False
            
            # Ignora frases muito curtas
            if len(frase) < 10:
                continue

            for termo in termos_proibidos_frase:
                if termo in frase_lower:
                    tem_lixo = True
                    break 
            
            if not tem_lixo:
                frases_uteis_finais.append(frase.strip())

        return "\n\n".join(frases_uteis_finais)