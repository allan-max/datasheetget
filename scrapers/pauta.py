# scrapers/pauta.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import re
from .base import BaseScraper

class PautaScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Pauta] Iniciando método 'Cirurgião' (Limpeza Frase por Frase)...")
            
            opts = Options()
            opts.add_argument("--headless=new") 
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument('--ignore-certificate-errors')
            opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

            driver = webdriver.Chrome(options=opts)
            driver.get(self.url)

            # Espera carregar e rola a página
            time.sleep(8)
            driver.execute_script("window.scrollTo(0, 1000);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- 1. TÍTULO ---
            titulo = "Produto Pauta"
            h1 = soup.find("h1", class_="title")
            if h1: titulo = self.limpar_texto(h1.get_text())

            # --- 2. IMAGEM ---
            url_img = None
            img = soup.find("img", id="cloudZoomImage")
            if img: url_img = img.get("src")
            if url_img and url_img.startswith("/"): url_img = "https://www.pauta.com.br" + url_img

            # --- 3. DESCRIÇÃO (MÉTODO CIRURGICO) ---
            descricao = ""
            todos_paragrafos = soup.find_all("p")
            frases_uteis_finais = []

            # Lista de termos que condenam UMA FRASE (não o texto todo)
            termos_proibidos_frase = [
                # Garantia e Venda
                "garantia", "devolução", "troca", "frete", "entrega", 
                "condição de venda", "pagamento", "boleto", "cartão",
                "preço", "oferta", "promoção", "estoque", "disponível",
                
                # Loja / Site / Contato
                "pauta", "loja", "site", "fale conosco", "televendas", 
                "atendimento", "sac", "telefone", "(19)", "cnpj", 
                "endereço", "horário", "segunda à sexta", "segunda a sexta",
                "todos os direitos", "copyright", "aviso legal"
            ]

            for p in todos_paragrafos:
                texto_bruto = self.limpar_texto(p.get_text())
                
                # Ignora textos muito curtos (menus, botões)
                if len(texto_bruto) < 50: continue

                # DIVIDE O TEXTO EM FRASES (Pelo ponto final)
                # O regex abaixo separa por ponto seguido de espaço ou fim de linha
                frases = re.split(r'(?<=[.!?])\s+', texto_bruto)
                
                for frase in frases:
                    frase_lower = frase.lower()
                    
                    # Verifica se essa frase específica tem algo proibido
                    tem_lixo = False
                    for termo in termos_proibidos_frase:
                        if termo in frase_lower:
                            tem_lixo = True
                            break # Condena a frase
                    
                    # Se a frase estiver limpa, salva ela
                    if not tem_lixo and len(frase) > 10:
                        frases_uteis_finais.append(frase)

            if frases_uteis_finais:
                # Reconstrói o texto
                descricao = "\n\n".join(frases_uteis_finais)
                print(f"   [DEBUG] Descrição cirúrgica gerada! ({len(descricao)} caracteres)")
            else:
                print("   [DEBUG] ❌ Nenhum texto restou após a cirurgia.")
                descricao = "Informações detalhadas indisponíveis."

            # --- 4. FICHA TÉCNICA ---
            specs = {}
            table = soup.find("table", class_="features-list")
            
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
                            k_lower = k.lower()
                            ignorar = ["garantia", "ncm", "ean", "conteudo", "dimensao", "peso", "código"]
                            if not any(x in k_lower for x in ignorar):
                                specs[k] = v
            
            specs = self.filtrar_specs(specs)

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": self.baixar_imagem_temp(url_img)
            }

            arquivos = self.gerar_arquivos_finais(dados)

            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs,
                'total_imagens': 1,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   [ERRO CRÍTICO PAUTA] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                driver.quit()