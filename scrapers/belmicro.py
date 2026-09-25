# scrapers/belmicro.py
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from PIL import Image
from io import BytesIO
import json
import re
import os
import time
from .base import BaseScraper

class BelmicroScraper(BaseScraper):
    # A loja é VTEX: a API pública do catálogo devolve o produto inteiro em JSON
    # (título, fotos, ficha técnica e descrição). Por isso basta o requests:
    # não depende do Chrome 109 do servidor.
    BASE = "https://www.belmicro.com.br"

    # Especificações da API que não interessam ao datasheet
    CAMPOS_IGNORADOS = ["ean", "exibir_tags", "sku", "código", "garantia"]
    VALORES_VAZIOS = ["n/t", "n/a", "-", ""]

    # Frases de venda próprias desta loja (além das do BaseScraper)
    TERMOS_EXTRA = ["oportunidade", "agarre", "aproveite", "não perca"]

    def executar(self):
        try:
            print(f"   [Belmicro] Acessando: {self.url}")
            produto = self.buscar_produto()

            # 1. TÍTULO
            titulo = self.limpar_texto(produto.get("productName") or produto.get("productTitle"))
            if not titulo:
                self.guardar_resposta(produto)
                raise Exception("Título não encontrado na resposta da API")
            print(f"   [DEBUG] Título: {titulo}")

            # 2. DESCRIÇÃO + ESPECIFICAÇÕES ESCRITAS NA DESCRIÇÃO
            descricao, specs_descricao = self.separar_descricao(produto.get("description") or "")

            # 3. FICHA TÉCNICA
            # A ficha da API às vezes está incompleta ou desatualizada (ex.: PC Gamer
            # com "Placa de vídeo: N/T"), enquanto a descrição traz a especificação
            # completa do fabricante. Fica a fonte mais completa.
            specs_api = self.ler_ficha_api(produto)
            if len(specs_descricao) > len(specs_api):
                print(f"   [Belmicro] Usando especificações da descrição ({len(specs_descricao)} itens)")
                specs = specs_descricao
                # Completa com campos da API que a descrição não cobre (ex.: "Modelo"
                # da cadeira). Se o campo já aparece como grupo na descrição
                # ("Monitor" x "[MONITOR] ..."), vale o da descrição.
                cobertos = {re.sub(r'^\[([^\]]+)\].*', r'\1', k).lower() for k in specs}
                for k, v in specs_api.items():
                    if k.lower() not in cobertos:
                        specs[k] = v
            else:
                print(f"   [Belmicro] Usando ficha técnica da API ({len(specs_api)} itens)")
                specs = specs_api

            specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            if descricao == "Descrição indisponível." and not specs:
                self.guardar_resposta(produto)
                raise Exception("Nenhum conteúdo extraído (descrição e ficha técnica vazias)")

            # 4. IMAGEM
            url_img = self.escolher_imagem(produto)
            print(f"   [Belmicro] Imagem: {url_img}")
            caminho_imagem = self.baixar_imagem_fundo_branco(url_img)
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
            print(f"   ❌ [ERRO BELMICRO] {e}")
            return {'sucesso': False, 'erro': str(e)}

    # ------------------------------------------------------------------ API

    def buscar_produto(self):
        """Busca o produto na API de catálogo da VTEX pelo slug da URL."""
        caminho = urlparse(self.url).path.strip("/")
        slug = re.sub(r'/p$', '', caminho).split("/")[-1]
        if not slug:
            raise Exception("Não foi possível identificar o produto na URL")

        api = f"{self.BASE}/api/catalog_system/pub/products/search/{slug}/p"
        res = requests.get(api, headers=self.headers, timeout=30)
        dados = res.json() if res.status_code in (200, 206) else []
        if dados:
            return dados[0]

        # Plano B: lê o productId da página e busca por ele
        print(f"   [Belmicro] API não encontrou o slug (HTTP {res.status_code}). Tentando pela página...")
        pagina = requests.get(self.url, headers=self.headers, timeout=30)
        m = re.search(r'"productId"\s*:\s*"?(\d+)', pagina.text)
        if m:
            res = requests.get(f"{self.BASE}/api/catalog_system/pub/products/search/?fq=productId:{m.group(1)}",
                               headers=self.headers, timeout=30)
            dados = res.json() if res.status_code in (200, 206) else []
            if dados:
                return dados[0]

        self.guardar_resposta(pagina.text)
        raise Exception(f"Produto não encontrado na API da loja (slug: {slug})")

    def ler_ficha_api(self, produto):
        specs = {}
        for grupo in produto.get("allSpecificationsGroups", []):
            if grupo.lower() == "geral":  # grupo interno da loja (tags de vitrine)
                continue
            for campo in produto.get(grupo, []):
                chave = self.limpar_texto(campo)
                valor = self.limpar_texto(", ".join(produto.get(campo) or []))
                if any(t == chave.lower() for t in self.CAMPOS_IGNORADOS): continue
                if valor.lower() in self.VALORES_VAZIOS: continue
                specs[chave] = valor
        return specs

    # ------------------------------------------------------------ DESCRIÇÃO

    def linhas_html(self, html):
        """Quebra o HTML da descrição em linhas, marcando as que são só negrito (títulos)."""
        partes = re.split(r'(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>|<p[^>]*>|<div[^>]*>|<h\d[^>]*>', html)
        linhas = []
        for parte in partes:
            frag = BeautifulSoup(parte, "html.parser")
            texto = self.limpar_texto(frag.get_text())
            if not texto:
                linhas.append(("", False))
                continue
            negrito = " ".join(b.get_text() for b in frag.find_all(["b", "strong"]))
            linhas.append((texto, self.limpar_texto(negrito) == texto))
        return linhas

    def separar_descricao(self, html):
        """Separa o texto de apresentação das especificações escritas na descrição."""
        linhas = self.linhas_html(html)

        texto = []
        specs = {}
        em_specs = False
        categoria = ""
        itens_categoria = []

        def fechar_categoria():
            if categoria and itens_categoria:
                specs[categoria] = "; ".join(itens_categoria)
            itens_categoria.clear()

        for linha, negrito in linhas:
            # Enfeites como "<<<>>> 3green Force <<<>>>" e ":::::Texto:::::"
            linha = re.sub(r'^[\s<>:=*~]+|[\s<>:=*~]+$', '', linha).strip() if negrito else linha

            titulo_specs = negrito and re.search(
                r'(?i)especifica[çc][õo]es|caracter[íi]sticas t[ée]cnicas|^caracter[íi]sticas$|ficha t[ée]cnica', linha)
            if titulo_specs:
                fechar_categoria()
                em_specs, categoria = True, ""
                continue

            if not em_specs:
                texto.append(linha)
                continue

            if not linha:
                # Linha em branco encerra o grupo atual (ex.: "Modelo: 72861" solto no fim)
                fechar_categoria()
                categoria = ""
                continue

            if negrito and len(linha) <= 40 and not re.search(r':\s*\S', linha):
                fechar_categoria()
                categoria = linha.rstrip(":").strip()
                continue

            item = re.sub(r'^[\s\-\•\*]+', '', linha).strip()
            if ":" in item:
                k, v = [x.strip() for x in item.split(":", 1)]
                if k.lower() in ("atenção", "atencao", "obs", "observação", "nota") or len(k) > 40 or not v:
                    texto.append(linha)
                    continue
                nome = f"[{categoria}] {k}" if categoria else k
                if nome in specs and v not in specs[nome]:
                    specs[nome] = f"{specs[nome]} / {v}"
                else:
                    specs[nome] = v
            elif categoria:
                itens_categoria.append(item)
            elif len(item) > 60:
                # Frase solta depois das specs volta para a descrição
                texto.append(item)
        fechar_categoria()

        # Categoria "Garantia" é padronizada pelo BaseScraper
        specs = {k: v for k, v in specs.items() if not k.lower().startswith(("garantia", "[garantia]"))}

        return self.montar_descricao(texto), specs

    def montar_descricao(self, linhas):
        paragrafos = []
        for linha in linhas:
            if not linha: continue
            # Filtra por frase: um parágrafo de marketing com uma frase de venda
            # no meio não deve cair inteiro
            frases = re.split(r'(?<=[.!?])\s+', linha)
            frases = [f for f in frases if not any(t in f.lower() for t in self.TERMOS_EXTRA)]
            limpo = self.limpar_lixo_comercial("\n".join(frases))
            if limpo not in ("Descrição não disponível.", "Informações técnicas não detalhadas."):
                paragrafos.append(limpo.replace("\n", " "))
        return "\n\n".join(paragrafos) if paragrafos else "Descrição indisponível."

    # --------------------------------------------------------------- IMAGEM

    def escolher_imagem(self, produto):
        """A loja mistura uma arte de marketplace ("Ajuste_imagens Marketplace")
        entre as fotos; ela não é a foto do produto e fica de fora."""
        imagens = []
        for item in produto.get("items", []):
            imagens += [i.get("imageUrl") for i in item.get("images", []) if i.get("imageUrl")]
        fotos = [u for u in imagens if not re.search(r'(?i)ajuste_imagens|marketplace', u)]
        return (fotos or imagens or [None])[0]

    def baixar_imagem_fundo_branco(self, url_imagem):
        """Baixa a foto e aplica fundo branco em PNG transparente
        (o convert("RGB") direto deixaria o fundo preto)."""
        if not url_imagem or not self.output_folder: return None
        try:
            res = requests.get(url_imagem, headers=self.headers, timeout=20)
            if res.status_code != 200: return None
            img = Image.open(BytesIO(res.content))
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img = img.convert('RGBA')
                fundo = Image.new('RGB', img.size, (255, 255, 255))
                fundo.paste(img, mask=img.split()[-1])
                img = fundo
            else:
                img = img.convert('RGB')
            # Nome único: a API roda em várias threads ao mesmo tempo
            caminho = os.path.join(self.output_folder, f"temp_img_belmicro_{int(time.time() * 1000)}.jpg")
            img.save(caminho, "JPEG", quality=95)
            return caminho
        except Exception as e:
            print(f"   ⚠️ Erro ao baixar imagem: {e}")
            return None

    # ---------------------------------------------------------- DIAGNÓSTICO

    def guardar_resposta(self, conteudo):
        """Guarda o que a loja devolveu para se poder ver depois o que falhou."""
        try:
            if not self.output_folder: return
            caminho = os.path.join(self.output_folder, f"belmicro_falha_{int(time.time())}.txt")
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False, indent=1))
            print(f"   [Belmicro] Resposta guardada em: {caminho}")
        except Exception as e:
            print(f"   ⚠️ Não foi possível guardar a resposta da falha: {e}")
