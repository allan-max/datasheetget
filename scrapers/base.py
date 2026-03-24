# scrapers/base.py
import os
import requests
import re
from datetime import datetime
from PIL import Image
from io import BytesIO
from utils.generator import DocGenerator

class BaseScraper:
    def __init__(self, url):
        self.url = url
        self.output_folder = ""
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        # LISTA DE TERMOS PARA REMOVER
        self.termos_proibidos = [
            "garantia", "devolução", "reembolso", "troca",
            "frete", "envio", "entrega", "postagem", "rastreio",
            "estoque", "pronta entrega", "disponível",
            "parcele", "juros", "cartão", "boleto", "pagamento",
            "clique aqui", "veja mais", "confira", "acesse", "visite",
            "site", "loja", "vendedor", "comprar", "oferta", "promoção",
            "whatsapp", "atendimento", "sac", "dúvidas",
            "mercadolivre", "mercado livre", "amazon", "magalu"
        ]

    def limpar_texto(self, texto):
        if not texto: return ""
        return re.sub(r'\s+', ' ', texto).strip()

    def limpar_lixo_comercial(self, texto):
        """Remove linhas que contêm informações de venda/garantia"""
        if not texto: return "Descrição não disponível."
        
        linhas = texto.split('\n')
        linhas_limpas = []
        
        for linha in linhas:
            linha_lower = linha.lower().strip()
            
            # Pula linhas vazias ou muito curtas
            if len(linha_lower) < 3: continue
            
            # Se a linha tiver termo proibido, PULA (não adiciona)
            tem_lixo = False
            for termo in self.termos_proibidos:
                if termo in linha_lower:
                    tem_lixo = True
                    break
            
            if not tem_lixo:
                # Remove caracteres estranhos no início (ex: bullets)
                linha_limpa = re.sub(r'^[\s\-\•\.\*]+', '', linha).strip()
                linhas_limpas.append(linha_limpa)
                
        # Reconstrói o texto
        texto_final = "\n".join(linhas_limpas)
        
        # Filtro extra: Se sobrou muito pouco texto, coloca aviso padrão
        if len(texto_final) < 10:
            return "Informações técnicas não detalhadas."
            
        return texto_final

    def filtrar_specs(self, specs_dict):
        """Remove chaves do dicionário de specs que sejam lixo (ex: 'Garantia': '3 meses')"""
        specs_limpas = {}
        for k, v in specs_dict.items():
            k_lower = str(k).lower()
            v_lower = str(v).lower()
            
            eh_lixo = False
            for termo in self.termos_proibidos:
                if termo in k_lower: # Remove se a chave for "Garantia do Vendedor"
                    eh_lixo = True
                    break
            
            if not eh_lixo:
                specs_limpas[k] = v
        return specs_limpas

    def baixar_imagem_temp(self, url_imagem):
        if not url_imagem or not self.output_folder: return None
        try:
            if url_imagem.startswith("//"): url_imagem = "https:" + url_imagem
            res = requests.get(url_imagem, headers=self.headers, stream=True, timeout=10)
            if res.status_code == 200:
                filename = os.path.join(self.output_folder, "temp_img.jpg")
                img = Image.open(BytesIO(res.content)).convert("RGB")
                img.save(filename, "JPEG", quality=90)
                return filename
        except: pass
        return None

    def gerar_arquivos_finais(self, dados):
        if not self.output_folder: raise Exception("Pasta de saída indefinida")

        if 'titulo' in dados and dados['titulo']:
            dados['titulo'] = str(dados['titulo']).upper()

        safe_title = re.sub(r'(?u)[^-\w.]', '', dados['titulo'].replace(' ', '_'))[:60]
        timestamp = datetime.now().strftime("%H%M%S")
        
        nome_word = f"{safe_title}_{timestamp}.docx"
        nome_pdf = f"{safe_title}_{timestamp}.pdf"
        
        path_word = os.path.join(self.output_folder, nome_word)
        path_pdf = os.path.join(self.output_folder, nome_pdf)

        gen = DocGenerator()
        gen.create_word(dados, path_word)
        gen.create_pdf(dados, path_pdf)

        if dados.get("caminho_imagem_temp") and os.path.exists(dados["caminho_imagem_temp"]):
            try: os.remove(dados["caminho_imagem_temp"])
            except: pass

        return {
            'word_nome': nome_word,
            'pdf_nome': nome_pdf,
            'full_path_word': path_word,
            'full_path_pdf': path_pdf
        }

    def executar(self):
        raise NotImplementedError