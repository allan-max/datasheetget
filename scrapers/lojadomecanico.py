# scrapers/lojadomecanico.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import re
import os
from .base import BaseScraper

class LojaDoMecanicoScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [LojaDoMecanico] Iniciando Scraper (V4 - Motor de Descrição Atualizado)...")
            
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

            # Mantemos invisível (minimize) como nos outros scrapers para não atrapalhar
            driver = uc.Chrome(options=opts, version_main=109)
            driver.minimize_window()

            print(f"   [LojaDoMecanico] Acessando: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)

            # 1. Espera Título
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "product-name"))
                )
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. Tentando continuar.")

            # Rolagem para garantir Lazy Load
            print("   [LojaDoMecanico] Vasculhando a página...")
            for i in range(4):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Loja do Mecânico"
            h1 = soup.find("h1", class_="product-name")
            if h1:
                titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- IMAGEM ---
            print("   [LojaDoMecanico] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            img_tag = soup.find("img", class_="product-zoom")
            
            if img_tag:
                url_img = img_tag.get("data-image") or img_tag.get("src")

            if url_img:
                if not url_img.startswith("http"):
                     url_img = "https:" + url_img if url_img.startswith("//") else "https://www.lojadomecanico.com.br" + url_img
                
                print(f"   [LojaDoMecanico] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [LojaDoMecanico] Apelando para o Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img.product-zoom")
                    if el_img:
                        filename = f"temp_img_lojadomec_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except:
                    pass

            # --- DESCRIÇÃO ---
            print("   [LojaDoMecanico] Extraindo Descrição...")
            descricao_bruta = ""
            
            # ATUALIZAÇÃO: Agora procura pela nova classe e novo ID
            desc_container = soup.find("div", id=re.compile(r"product-description|descricao"))
            if desc_container:
                # Transforma as tags HTML em formatação de texto bonito
                for li in desc_container.find_all("li"):
                    li.insert_before("\n- ")
                for br in desc_container.find_all("br"):
                    br.replace_with("\n")
                for p in desc_container.find_all("p"):
                    p.insert_before("\n\n")

                descricao_bruta = desc_container.get_text(separator=" ", strip=True)
                # Limpa espaços e quebras de linha em excesso
                descricao_bruta = re.sub(r' {2,}', ' ', descricao_bruta)
                descricao_bruta = re.sub(r'\n{3,}', '\n\n', descricao_bruta).strip()
            
            # Aplica a limpeza aprimorada (Remove Garantia e FAQs)
            descricao = self.limpar_descricao_loja(descricao_bruta)
            
            if descricao and descricao != "Descrição indisponível.":
                print("   ✅ Descrição capturada e limpa com sucesso.")
            else:
                print("   ⚠️ Aviso: Mercado Livre não renderizou a descrição nesta página.")

            # --- FICHA TÉCNICA ---
            print("   [LojaDoMecanico] Extraindo Ficha Técnica...")
            specs = {}
            linhas = soup.find_all("tr")
            for linha in linhas:
                chave_td = linha.find("td", class_=lambda c: c and "text-description" in c)
                valor_td = linha.find("td", class_=lambda c: c and "text-value" in c)
                
                if chave_td and valor_td:
                    chave = self.limpar_texto(chave_td.get_text())
                    valor = self.limpar_texto(valor_td.get_text())
                    if chave and valor:
                        specs[chave] = valor

            specs = self.filtrar_specs_loja(specs)
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

            print("   [LojaDoMecanico] Gerando arquivos PDF/Word...")
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
            print(f"   ❌ [ERRO LOJA DO MECANICO] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_loja(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        # Frases que, se aparecerem na linha, matam a linha inteira
        frases_banidas = [
            "imagens meramente ilustrativas",
            "todas as informações divulgadas",
            "responsabilidade do fabricante",
            "marca.:",
            "ref.:"
        ]
        
        pular_proxima = False
        modo_faq = False
        
        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean: 
                if linhas_limpas and linhas_limpas[-1] != "": linhas_limpas.append("")
                continue
            
            linha_lower = linha_clean.lower()
            
            # --- NOVIDADE: Cortar o lixo do FAQ ---
            if "perguntas frequentes" in linha_lower:
                modo_faq = True
                
            if modo_faq:
                continue # Se estiver no FAQ, ignora a linha e não guarda
                
            if pular_proxima:
                pular_proxima = False
                continue

            # Se for apenas o título "Garantia" ou "Código de barras", pula esta linha e a próxima (o valor)
            if linha_lower in ["garantia", "código de barras"]:
                pular_proxima = True
                continue
            
            # FILTRO DE FRASES BANIDAS
            if any(banida in linha_lower for banida in frases_banidas):
                continue

            # FILTRO DE MARCA SOLTA (Ex: "WBERTOLO" ou "MTX")
            if len(linha_clean) < 15 and linha_clean.isupper() and " " not in linha_clean:
                continue

            linhas_limpas.append(linha_clean)

        return "\n".join(linhas_limpas).strip()

    def filtrar_specs_loja(self, specs):
        specs_limpas = {}
        ignorar = ["garantia", "ver parcelas"]
        for k, v in specs.items():
            k_lower = k.lower()
            if not any(x in k_lower for x in ignorar):
                specs_limpas[k] = v
        return specs_limpas