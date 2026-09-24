# scrapers/creativecopias.py
import requests
from bs4 import BeautifulSoup
import re
import os
import time
from .base import BaseScraper

class CreativeCopiasScraper(BaseScraper):
    # A loja é Magento 1 e entrega a página completa no HTML, sem JavaScript.
    # Por isso basta o requests: não depende do Chrome 109 do servidor.
    def executar(self):
        try:
            print(f"   [Creative Cópias] Acessando: {self.url}")
            response = requests.get(self.url, headers=self.headers, timeout=30)
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            # 1. TÍTULO
            titulo = None
            h1 = soup.select_one("div.product-name h1") or soup.find("h1")
            if h1:
                titulo = self.limpar_texto(h1.get_text())

            if not titulo:
                # Sem título não vale a pena continuar: guarda o que veio para se ver depois
                self.guardar_pagina(html)
                raise Exception(f"Título não encontrado (HTTP {response.status_code}, página com {len(html)} bytes)")
            print(f"   [DEBUG] Título: {titulo}")

            # 2. IMAGEM
            # O data-zoom-image é a foto grande (1800px); o src é a média e o
            # og:image é a miniatura de 255px, que só serve de último recurso.
            url_img = None
            img_tag = soup.find("img", id="image-main")
            if img_tag:
                url_img = img_tag.get("data-zoom-image") or img_tag.get("src")
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")
            print(f"   [Creative Cópias] Imagem: {url_img}")

            # 3. DESCRIÇÃO (caixa "Detalhes")
            descricao = "Descrição indisponível."
            box_desc = soup.find("div", class_="box-description")
            if box_desc:
                cabecalho = box_desc.find(id="product-description")
                if cabecalho: cabecalho.decompose()
                paragrafos = []
                for bloco in box_desc.get_text("\n", strip=True).split("\n"):
                    # A descrição costuma vir num único parágrafo com a garantia no
                    # meio. Filtrar por frase evita que o parágrafo inteiro caia.
                    frases = re.split(r'(?<=[.!?])\s+', bloco)
                    limpo = self.limpar_lixo_comercial("\n".join(frases))
                    if limpo not in ("Descrição não disponível.", "Informações técnicas não detalhadas."):
                        paragrafos.append(limpo.replace("\n", " "))
                if paragrafos:
                    descricao = "\n\n".join(paragrafos)

            # 4. FICHA TÉCNICA
            specs = {}

            # 4a. Folha de especificações do fabricante (ex.: Brother): pares esq/dir
            for esq in soup.select("div.esq"):
                dir_ = esq.find_next_sibling("div", class_="dir")
                if not dir_: continue
                k = self.limpar_texto(esq.get_text())
                v = self.limpar_texto(dir_.get_text(" ", strip=True))
                if k and v and k not in specs:
                    specs[k] = v

            # 4b. Caixa "Especificação": linhas "Chave: Valor" e frases soltas
            box_espec = soup.find("div", class_="box-especificacao")
            if box_espec:
                soltas = []
                for linha in box_espec.get_text("\n", strip=True).split("\n")[1:]:
                    linha = self.limpar_texto(linha)
                    if ":" in linha:
                        k, v = linha.split(":", 1)
                        if k.strip() and v.strip(): specs[k.strip()] = v.strip()
                    elif linha.lower().startswith("rendimento"):
                        specs["Rendimento"] = linha[len("rendimento"):].strip()
                    elif linha.lower().startswith("produto "):
                        specs["Condição"] = linha[len("produto "):].strip()
                    elif linha and not any(t in linha.lower() for t in self.termos_proibidos):
                        soltas.append(linha)
                if soltas:
                    specs["Características"] = "; ".join(soltas)

            # 4c. Caixa "Compatibilidade": lista de modelos. Nas Brother esta caixa
            # traz a folha do fabricante, que já foi lida em 4a.
            box_compat = soup.find("div", class_="box-compatibilidade")
            if box_compat and not box_compat.select("div.esq"):
                modelos = []
                for linha in box_compat.get_text("\n", strip=True).split("\n")[1:]:
                    linha = self.limpar_texto(linha)
                    # Frase de introdução ("...modelos:") e o aviso legal ("*Marcas...") não entram
                    if not linha or linha.endswith(":") or linha.startswith("*"): continue
                    modelos.append(linha)
                if modelos:
                    specs["Compatibilidade"] = ", ".join(modelos)

            specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            if descricao == "Descrição indisponível." and not specs:
                self.guardar_pagina(html)
                raise Exception("Nenhum conteúdo extraído (descrição e ficha técnica vazias)")

            caminho_imagem = self.baixar_imagem_temp(url_img)
            if caminho_imagem:
                print("   ✅ Imagem salva.")
            else:
                print("   ⚠️ Não foi possível baixar a imagem.")

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

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
            print(f"   ❌ [ERRO CREATIVE COPIAS] {e}")
            return {'sucesso': False, 'erro': str(e)}

    def guardar_pagina(self, html):
        """Guarda o HTML recebido para se poder ver o que o servidor apanhou."""
        try:
            if not self.output_folder: return
            caminho = os.path.join(self.output_folder, f"creativecopias_falha_{int(time.time())}.html")
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(html or "")
            print(f"   [Creative Cópias] Página guardada em: {caminho}")
        except Exception as e:
            print(f"   ⚠️ Não foi possível guardar a página da falha: {e}")
