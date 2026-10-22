# scrapers/base.py
import os
import requests
import re
from datetime import datetime
from PIL import Image
from io import BytesIO
from utils.generator import DocGenerator
from utils.seguranca import nome_temporario
from utils.logger import (
    definir_contexto_execucao,
    identificar_modulo_scraper,
    registrar_log,
    registrar_erro_modulo,
    validar_e_reportar_dados_item,
)

class BaseScraper:
    def __init__(self, url):
        self.url = url
        self.output_folder = ""
        self.site_nome = None
        self.modulo_nome = None
        self.problemas_detectados = []
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
        mod_id = identificar_modulo_scraper(scraper=self)
        definir_contexto_execucao(modulo=mod_id, url=self.url)
        if not url_imagem:
            registrar_erro_modulo(
                mod_id,
                "Não foi possível baixar a imagem porque nenhuma URL de imagem foi encontrada pelo módulo.",
                url=self.url,
            )
            return None
        if not self.output_folder:
            registrar_erro_modulo(
                mod_id,
                "Pasta de saída não definida ao tentar baixar a imagem do item.",
                url=self.url,
            )
            return None
        try:
            if url_imagem.startswith("//"): url_imagem = "https:" + url_imagem
            registrar_log(f"Iniciando download da imagem do produto: {url_imagem}", nivel="INFO", modulo=mod_id)
            res = requests.get(url_imagem, headers=self.headers, stream=True, timeout=10)
            if res.status_code == 200:
                # Nome único: com nome fixo, pedidos simultâneos trocavam a foto um do outro
                filename = os.path.join(self.output_folder, nome_temporario("temp_img"))
                img = Image.open(BytesIO(res.content)).convert("RGB")
                largura, altura = img.size
                img.save(filename, "JPEG", quality=90)
                tamanho_kb = os.path.getsize(filename) / 1024.0 if os.path.exists(filename) else 0
                registrar_log(
                    f"Download da imagem concluído: {largura}x{altura}px ({tamanho_kb:.1f} KB) salva em {filename}",
                    nivel="INFO",
                    modulo=mod_id,
                )
                return filename
            else:
                registrar_erro_modulo(
                    mod_id,
                    f"Falha ao baixar imagem do item (HTTP {res.status_code}) na URL de imagem: {url_imagem}",
                    url=self.url,
                )
        except Exception as e:
            registrar_erro_modulo(
                mod_id,
                f"Erro ao baixar ou processar a imagem do item ({url_imagem}): {e}",
                url=self.url,
            )
        return None

    def gerar_arquivos_finais(self, dados):
        mod_id = identificar_modulo_scraper(scraper=self)
        definir_contexto_execucao(modulo=mod_id, url=self.url)
        if not self.output_folder:
            registrar_erro_modulo(mod_id, "Pasta de saída indefinida ao gerar arquivos finais.", url=self.url)
            raise Exception("Pasta de saída indefinida")

        # Valida se o item veio sem imagem, sem descrição, sem título ou sem ficha técnica
        # (antes de injetar a garantia padrão para não mascarar ficha técnica vazia)
        self.problemas_detectados = validar_e_reportar_dados_item(dados, scraper=self, modulo=mod_id, url=self.url)

        # 1. Procurar e extrair o modelo
        modelo_encontrado = None
        
        # A) Procurar nas características (specs)
        specs = dados.get('caracteristicas', {})
        if isinstance(specs, dict):
            for k, v in specs.items():
                if str(k).strip().lower() == 'modelo':
                    modelo_encontrado = str(v).strip()
                    break
        elif isinstance(specs, list):
            for item in specs:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    if str(item[0]).strip().lower() == 'modelo':
                        modelo_encontrado = str(item[1]).strip()
                        break
                        
        # B) Se não achou nas specs, procurar na descrição
        if not modelo_encontrado:
            descricao = dados.get('descricao', '')
            if descricao:
                match = re.search(r'(?i)modelo\s*[:\-]+\s*([A-Za-z0-9\-\/]+)', str(descricao))
                if match:
                    modelo_encontrado = match.group(1).strip()

        if modelo_encontrado:
            registrar_log(f"Modelo identificado para o item: '{modelo_encontrado}'", nivel="INFO", modulo=mod_id)
        else:
            registrar_log("Nenhum código de modelo explícito encontrado nas especificações ou descrição.", nivel="INFO", modulo=mod_id)
                    
        # 2. Atualizar o título com o modelo
        if 'titulo' in dados and dados['titulo']:
            if modelo_encontrado:
                if modelo_encontrado.upper() not in str(dados['titulo']).upper():
                    dados['titulo'] = f"{str(dados['titulo']).strip()} {modelo_encontrado.upper()}"
            dados['titulo'] = str(dados['titulo']).upper()
            registrar_log(f"Título final padronizado para o documento: '{dados['titulo']}'", nivel="INFO", modulo=mod_id)

        # 3. Adicionar Garantia Padronizada
        if 'caracteristicas' not in dados:
            dados['caracteristicas'] = {}
            
        if isinstance(dados['caracteristicas'], dict):
            dados['caracteristicas']['Garantia'] = '12 MESES'
        elif isinstance(dados['caracteristicas'], list):
            # Tentar remover garantia antiga se existir e adicionar nova
            dados['caracteristicas'] = [item for item in dados['caracteristicas'] if not (isinstance(item, (list, tuple)) and len(item) == 2 and str(item[0]).strip().lower() == 'garantia')]
            dados['caracteristicas'].append(('Garantia', '12 MESES'))

        if not dados.get('titulo'):
            dados['titulo'] = 'PRODUTO'
        safe_title = re.sub(r'(?u)[^-\w.]', '', str(dados['titulo']).replace(' ', '_'))[:100]
        timestamp = datetime.now().strftime("%H%M%S")
        
        nome_word = f"{safe_title}_{timestamp}.docx"
        nome_pdf = f"{safe_title}_{timestamp}.pdf"
        
        path_word = os.path.join(self.output_folder, nome_word)
        path_pdf = os.path.join(self.output_folder, nome_pdf)

        registrar_log(f"Iniciando geração dos arquivos Word ({nome_word}) e PDF ({nome_pdf}) em {self.output_folder}...", nivel="INFO", modulo=mod_id)
        gen = DocGenerator()
        ok_word = gen.create_word(dados, path_word)
        ok_pdf = gen.create_pdf(dados, path_pdf)

        if not ok_word:
            registrar_erro_modulo(mod_id, f"Falha ao gerar arquivo Word ({path_word}).", url=self.url, titulo=dados.get('titulo'))
        if not ok_pdf:
            registrar_erro_modulo(mod_id, f"Falha ao gerar arquivo PDF ({path_pdf}).", url=self.url, titulo=dados.get('titulo'))

        if dados.get("caminho_imagem_temp") and os.path.exists(dados["caminho_imagem_temp"]):
            try:
                os.remove(dados["caminho_imagem_temp"])
                registrar_log(f"Imagem temporária removida após inclusão nos documentos: {dados['caminho_imagem_temp']}", nivel="INFO", modulo=mod_id)
            except:
                pass

        return {
            'word_nome': nome_word,
            'pdf_nome': nome_pdf,
            'full_path_word': path_word,
            'full_path_pdf': path_pdf
        }

    def executar(self):
        raise NotImplementedError
