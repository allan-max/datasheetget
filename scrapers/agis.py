# scrapers/agis.py
import requests
from bs4 import BeautifulSoup
import re
from .base import BaseScraper

class AgisScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [Agis] Acessando: {self.url}")
            # Headers simulando navegador
            headers = self.headers.copy()
            headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            response = requests.get(self.url, headers=headers, timeout=20)
            soup = BeautifulSoup(response.content, 'html.parser')

            # 1. TÍTULO
            titulo = "Produto Agis"
            title_tag = soup.find(class_="page-title")
            if title_tag:
                span_title = title_tag.find("span", attrs={"data-ui-id": "page-title-wrapper"})
                titulo = self.limpar_texto(span_title.get_text()) if span_title else self.limpar_texto(title_tag.get_text())

            # 2. IMAGEM
            url_img = None
            img_tag = soup.find("img", class_="fotorama__img")
            if img_tag:
                src = img_tag.get("src")
                if src: url_img = src.split('?')[0]
            
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            # 3. DESCRIÇÃO (Lógica Aprimorada)
            descricao = ""
            
            # TENTATIVA 1: Classe específica 'product attribute description' (Novo Padrão)
            desc_container = soup.find("div", class_="product attribute description")
            if desc_container:
                # Geralmente o texto está dentro de <div class="value">
                val_div = desc_container.find("div", class_="value")
                target_div = val_div if val_div else desc_container
                
                # Pega todos os parágrafos
                paragrafos = []
                for p in target_div.find_all("p"):
                    texto = self.limpar_texto(p.get_text())
                    if len(texto) > 10:
                        paragrafos.append(texto)
                
                if paragrafos:
                    descricao = "\n\n".join(paragrafos)

            # TENTATIVA 2: Fallback antigo (Blocos de conteúdo HTML genéricos)
            if not descricao:
                content_divs = soup.find_all("div", attrs={"data-content-type": "html"})
                linhas_uteis = []
                linhas_vistas = set()

                for div in content_divs:
                    if div.find('table'): continue # Pula tabelas

                    for elem in div.find_all(['p', 'span', 'strong', 'div']):
                        # Ignora se estiver dentro de tabela
                        if elem.find_parent('table'): continue
                        
                        texto = self.limpar_texto(elem.get_text())
                        if len(texto) < 15: continue
                        
                        # Filtros Agis
                        texto_lower = texto.lower()
                        ignorar = ["televendas", "(19)", "especificações técnicas", "fale conosco"]
                        if any(x in texto_lower for x in ignorar): continue

                        if texto not in linhas_vistas:
                            linhas_uteis.append(texto)
                            linhas_vistas.add(texto)
                
                if linhas_uteis:
                    descricao = "\n".join(linhas_uteis)

            if not descricao:
                descricao = "Descrição detalhada não disponível."
            else:
                descricao = self.limpar_lixo_comercial(descricao)


            # 4. CARACTERÍSTICAS (Specs com suporte a Sub-itens)
            specs = {}
            tables = soup.find_all("table")
            
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cols = row.find_all(["td", "th"])
                    if len(cols) >= 2:
                        k_main = self.limpar_texto(cols[0].get_text())
                        val_cell = cols[1]
                        
                        # Verifica se a célula de valor tem DIVs aninhadas (Ex: Tela -> Tamanho, Resolução...)
                        sub_divs = val_cell.find_all("div")
                        
                        # Se tiver muitos divs, provavelmente é uma lista de sub-propriedades
                        if len(sub_divs) > 2: 
                            current_sub_key = None
                            for div in sub_divs:
                                txt = self.limpar_texto(div.get_text())
                                if not txt: continue
                                
                                # Se estiver em negrito (strong/b), é o título da sub-propriedade
                                if div.find("strong") or div.find("b") or "strong" in str(div):
                                    current_sub_key = txt
                                else:
                                    # É o valor
                                    if current_sub_key:
                                        # Cria chave composta: "Tela - Tamanho"
                                        full_key = f"{k_main} - {current_sub_key}"
                                        specs[full_key] = txt
                                        current_sub_key = None # Reseta para o próximo
                        else:
                            # Linha simples normal
                            v = self.limpar_texto(val_cell.get_text())
                            if k_main and v:
                                specs[k_main] = v

            # Filtros finais de specs
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
            print(f"   [ERRO AGIS] {e}")
            return {'sucesso': False, 'erro': str(e)}