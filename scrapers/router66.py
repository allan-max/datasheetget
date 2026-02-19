# scrapers/router66.py
import requests
import re
from bs4 import BeautifulSoup
from .base import BaseScraper
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Router66Scraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [Route66] Iniciando Scraper (V5 - Pontuação e Regex)...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Referer": "https://www.google.com/"
            }

            response = requests.get(self.url, headers=headers, timeout=20, verify=False)
            response.encoding = response.apparent_encoding
            
            if response.status_code != 200:
                raise Exception(f"Erro HTTP {response.status_code}")

            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Route66"
            h1_div = soup.find("div", class_=lambda c: c and "text-2xl" in c and "font-bold" in c)
            if h1_div:
                titulo = self.limpar_texto_especial(h1_div.get_text())

            # --- IMAGEM ---
            url_img = None
            img_tag = soup.find("img", itemprop="thumbnail")
            
            if img_tag:
                url_img = img_tag.get("src")
                if url_img:
                    url_img = re.sub(r'/\d{3}/', '/1000/', url_img)

            # --- DESCRIÇÃO (ESTRATÉGIA DE PONTUAÇÃO) ---
            descricao_bruta = ""
            
            # Pega todas as divs
            divs = soup.find_all("div")
            melhor_candidato = None
            maior_pontuacao = 0

            for div in divs:
                classes = div.get("class", [])
                if not classes: continue
                
                classes_str = " ".join(classes)
                pontos = 0
                
                # Pontua baseada nas classes conhecidas do site (conforme seu arquivo router66.txt)
                if "border-t" in classes_str: pontos += 2
                if "border-border" in classes_str: pontos += 2
                if "p-4" in classes_str: pontos += 1
                
                # Se tiver pontuação relevante, verifica o texto
                if pontos >= 2:
                    texto = div.get_text(separator="\n", strip=True)
                    
                    # Ignora se for ficha técnica (que tem código numérico curto ou label "Código")
                    # A Ficha técnica costuma estar dentro de x-show, mas aqui olhamos texto bruto
                    if len(texto) < 40: continue # Texto muito curto não é descrição
                    
                    # A descrição real geralmente é longa
                    if len(texto) > 100: pontos += 5
                    
                    if pontos > maior_pontuacao:
                        maior_pontuacao = pontos
                        melhor_candidato = texto

            if melhor_candidato:
                descricao_bruta = melhor_candidato
            
            # --- FALLBACK: REGEX BRUTO ---
            # Se a estratégia de classes falhou, tenta achar no HTML bruto a tag específica
            # Padrão: <div class="twcss:p-4 twcss:border-t twcss:border-border">
            if not descricao_bruta:
                print("   [DEBUG] Tentando Fallback Regex na descrição...")
                match = re.search(r'<div[^>]*class=["\'][^"\']*border-t[^"\']*border-border[^"\']*["\'][^>]*>(.*?)</div>', html_content, re.DOTALL | re.IGNORECASE)
                if match:
                    conteudo_html = match.group(1)
                    # Limpa tags HTML do resultado do regex
                    cleaner = BeautifulSoup(conteudo_html, "html.parser")
                    descricao_bruta = cleaner.get_text(separator="\n")

            descricao = self.limpar_descricao_route66(descricao_bruta)

            # --- FICHA TÉCNICA ---
            specs = {}
            ficha_container = soup.find("div", attrs={"x-show": lambda x: x and 'ficha-tecnica' in x})
            
            if ficha_container:
                grid_container = ficha_container.find("div", class_=lambda c: c and "space-y" in c)
                if grid_container:
                    linhas = grid_container.find_all("div", recursive=False)
                    for linha in linhas:
                        colunas = linha.find_all("div", class_=lambda c: c and "w-1/2" in c)
                        if len(colunas) >= 2:
                            k = self.limpar_texto_especial(colunas[0].get_text())
                            v = self.limpar_texto_especial(colunas[1].get_text())
                            if k and v:
                                specs[k] = v

            specs = self.filtrar_specs_route66(specs)

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
            print(f"   [ERRO ROUTE66] {e}")
            return {'sucesso': False, 'erro': str(e)}

    def limpar_texto_especial(self, texto):
        if not texto: return ""
        txt = texto.replace("»", "").replace("?", " ")
        txt = " ".join(txt.split())
        return txt

    def limpar_descricao_route66(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean: 
                if linhas_limpas and linhas_limpas[-1] != "": linhas_limpas.append("")
                continue
            if linha_clean.startswith("»"):
                linha_clean = linha_clean.replace("»", "").strip()
            linha_clean = linha_clean.replace("?", " ")
            linhas_limpas.append(linha_clean)
        return "\n".join(linhas_limpas)

    def filtrar_specs_route66(self, specs):
        specs_limpas = {}
        ignorar = ["ncm", "ean", "código fabricante"]
        for k, v in specs.items():
            k_lower = k.lower()
            if not any(x in k_lower for x in ignorar):
                specs_limpas[k] = v
        return specs_limpas