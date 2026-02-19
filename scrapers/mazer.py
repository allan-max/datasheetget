# scrapers/mazer.py
import requests
import re
import html as html_lib
from bs4 import BeautifulSoup
from .base import BaseScraper
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class MazerScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [Mazer] Iniciando Scraper (V23 - Limpeza de Interface)...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Referer": "https://www.google.com/"
            }

            # 1. Download
            response = requests.get(self.url, headers=headers, timeout=20, verify=False)
            response.encoding = response.apparent_encoding
            
            if response.status_code != 200:
                raise Exception(f"Erro HTTP {response.status_code}")

            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Mazer"
            h1 = soup.find("h1", class_="tt-produto-principal")
            if h1:
                cite = h1.find("cite")
                if cite: titulo = self.limpar_texto(cite.get_text())
                else: titulo = self.limpar_texto(h1.get_text())

            # --- IMAGEM ---
            url_img = None
            imgs = soup.find_all("img")
            if titulo and titulo != "Produto Mazer":
                palavras_chaves = titulo.lower().split()[:3]
                busca = " ".join(palavras_chaves)
                for img in imgs:
                    alt = str(img.get("alt", "")).lower()
                    src = str(img.get("src", ""))
                    if busca in alt and ("mazer-img" in src or "f1cdn" in src):
                         url_img = src
                         break
            if not url_img:
                for img in imgs:
                    src = img.get("src", "")
                    if "mazer-img" in src or "f1cdn.com.br" in src:
                        if "width/266" in src or "normalize" in src:
                             url_img = src
                             break
            if url_img:
                url_img = re.sub(r'width/\d+', 'width/1200', url_img)
                url_img = re.sub(r'height/\d+', 'height/1200', url_img)
                if not url_img.startswith("http"):
                    if url_img.startswith("//"): url_img = "https:" + url_img
                    else: url_img = "https://www.mazer.com.br" + url_img

            # --- DESCRIÇÃO (FATIADOR V2) ---
            descricao_bruta = ""
            
            marcadores_inicio = [
                r'class=["\']txt-detalhe-produto["\']',
                r'>\s*Detalhes do Produto\s*<',
                r'class=["\']tt-produto-principal["\']'
            ]
            
            # Adicionei "Produtos Relacionados" e "Avaliações" como fim
            marcadores_fim = [
                r'class=["\']lista-atributos["\']',
                r'>\s*Ficha T&eacute;cnica\s*<',
                r'>\s*Ficha Técnica\s*<',
                r'>\s*Produtos Relacionados\s*<',
                r'id=["\']aba-caracteristicas["\']' 
            ]

            pos_ini = -1
            pos_fim = -1

            for m in marcadores_inicio:
                match = re.search(m, html_content, re.IGNORECASE)
                if match:
                    pos_ini = match.end()
                    break
            
            if pos_ini != -1:
                for m in marcadores_fim:
                    match = re.search(m, html_content[pos_ini:], re.IGNORECASE)
                    if match:
                        pos_fim = pos_ini + match.start()
                        break

            if pos_ini != -1 and pos_fim != -1:
                trecho_bruto = html_content[pos_ini:pos_fim]
                if len(trecho_bruto) > 20:
                    descricao_bruta = self.html_to_text_manual(trecho_bruto)

            # Fallback
            if not descricao_bruta:
                container = soup.find(class_="txt-detalhe-produto")
                if container:
                    descricao_bruta = container.get_text(separator="\n")

            # LIMPEZA REFINADA (Aqui removemos o lixo visual)
            descricao = self.limpar_descricao_preservando_specs(descricao_bruta)

            # --- FICHA TÉCNICA ---
            specs = {}
            specs_dl = soup.find("dl", class_="lista-atributos")
            if specs_dl:
                dts = specs_dl.find_all("dt")
                for dt in dts:
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        k = self.limpar_texto(dt.get_text())
                        v = self.limpar_texto(dd.get_text())
                        if k and v: specs[k] = v

            specs = self.filtrar_specs_mazer(specs)

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
            print(f"   [ERRO MAZER] {e}")
            return {'sucesso': False, 'erro': str(e)}

    def html_to_text_manual(self, html_raw):
        if not html_raw: return ""
        txt = html_raw
        
        # Remove Comentários (Corrige o "-->")
        txt = re.sub(r'', '', txt, flags=re.DOTALL)
        
        # Remove Scripts, Styles e Botões
        txt = re.sub(r'<script.*?>.*?</script>', '', txt, flags=re.DOTALL | re.IGNORECASE)
        txt = re.sub(r'<style.*?>.*?</style>', '', txt, flags=re.DOTALL | re.IGNORECASE)
        txt = re.sub(r'<button.*?>.*?</button>', '', txt, flags=re.DOTALL | re.IGNORECASE)
        
        # Trata quebras
        txt = re.sub(r'<br\s*/?>', '\n', txt, flags=re.IGNORECASE)
        txt = re.sub(r'</p>', '\n\n', txt, flags=re.IGNORECASE)
        txt = re.sub(r'</div>', '\n', txt, flags=re.IGNORECASE)
        txt = re.sub(r'</li>', '\n', txt, flags=re.IGNORECASE)
        
        # Remove tags restantes
        txt = re.sub(r'<[^>]+>', '', txt)
        
        return html_lib.unescape(txt)

    def limpar_descricao_preservando_specs(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        
        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        # Lista Negra de UI (Interface do Usuário)
        lixo_visual = [
            "+ mais detalhes", 
            "indique para um amigo", 
            "indique para o amigo", 
            "comprar", 
            "características", 
            "informações", 
            "×", 
            "-->",
            "fechar"
        ]
        
        termos_proibidos = ["sac:", "loja:", "preço:", "código:", "atendimento ao cliente", "fale conosco", "part number", "ean", "boleto"]

        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean:
                if linhas_limpas and linhas_limpas[-1] != "": linhas_limpas.append("")
                continue
            
            linha_lower = linha_clean.lower()
            
            # --- FILTRO 1: Lixo Visual Exato ---
            # Se a linha for EXATAMENTE uma dessas frases ou muito parecida
            if linha_lower in lixo_visual:
                continue
                
            # Se a linha começar com símbolos estranhos
            if linha_clean.startswith("-->") or linha_clean == "×":
                continue

            # --- PROTEÇÃO DE SPECS ---
            eh_spec = False
            if ":" in linha_clean and len(linha_clean) < 80:
                partes = linha_clean.split(":", 1)
                chave = partes[0].lower().strip()
                palavras_tecnicas = ["peso", "dimensão", "altura", "largura", "profundidade", "conexão", "porta", "compatibilidade", "níveis", "cooler", "iluminação", "material", "cor", "teclas", "resolução"]
                if any(p in chave for p in palavras_tecnicas):
                    eh_spec = True
            
            if eh_spec:
                linhas_limpas.append(linha_clean)
                continue 
            
            # --- FILTROS COMERCIAIS ---
            if "garantia" in linha_lower and "meses" in linha_lower and len(linha_clean) < 50: continue

            contem_proibido = False
            for termo in termos_proibidos:
                if termo in linha_lower:
                    contem_proibido = True
                    break
            
            if not contem_proibido:
                linhas_limpas.append(linha_clean)

        return "\n".join(linhas_limpas)

    def filtrar_specs_mazer(self, specs):
        specs_limpas = {}
        ignorar = ["ean", "part number", "garantia", "bruto", "largura (bruto)", "profundidade (bruto)", "altura (bruto)", "peso (bruto)"]
        for k, v in specs.items():
            k_clean = k.replace(":", "").strip()
            k_lower = k_clean.lower()
            if not any(x in k_lower for x in ignorar):
                specs_limpas[k_clean] = v
        return specs_limpas