import os
import sys
import re
import uuid
import json
import time
import threading
import requests
import importlib
import config
from urllib.parse import urlparse
from datetime import datetime
from io import BytesIO
from flask import Flask, request, jsonify, send_from_directory

# Garante que o Python veja a pasta atual para importar 'scrapers' e 'utils'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.seguranca import host_da_url, token_valido, validar_url_produto, webhook_permitido
from utils.logger import (
    ativar_captura_global,
    definir_contexto_execucao,
    identificar_modulo_scraper,
    limpar_contexto_execucao,
    obter_caminho_log,
    registrar_erro_modulo,
    registrar_log,
    registrar_modulo_ligado,
    registrar_separador,
)

# --- CONFIGURAÇÕES DE AMBIENTE (Antigo run.py) ---
os.environ["PYTHONUNBUFFERED"] = "1" 
os.environ["PYTHONIOENCODING"] = "utf-8"

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except:
    pass

# Ativa a gravação em tempo real de tudo para \\SERVIDOR2\Publico\ALLAN\Logs\datasheet.txt
ativar_captura_global()

# --- DEPENDÊNCIAS DE TERCEIROS ---
# Certifique-se de ter instalado: pip install flask requests python-docx fpdf pillow
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from fpdf import FPDF
from PIL import Image

# ==============================================================================
# 📋 CONFIGURAÇÕES E SITES (Antigo config.py)
# ==============================================================================

LOGO_PATH = r"C:\Users\Administrator\Desktop\datasheetget\utils\ventura.png"
# Altere para a pasta onde os arquivos finais devem cair:
OUTPUT_DIR = r"\\SERVIDOR2\Publico\Datasheet" 

HEADER_INFO = {
    "empresa": "VENTURA COMERCIO DE INFORMÁTICA EIRELI",
    "cnpj": "CNPJ: 08.310.365/0001-24",
    "endereco": "RUA SETE 560 COCAL VILA VELHA – ES I 29105-770"
}

URL_CALLBACK_PADRAO = "http://127.0.0.1:3000/api/datasheet/webhook"

SITES_CONFIG = {
    'MERCADO_LIVRE': {'padroes_url': [r'mercadolivre\.com', r'produto\.mercadolivre'], 'modulo': 'mercado_livre', 'classe': 'MercadoLivreScraper'},
    'AMAZON': {'padroes_url': [r'amazon\.com', r'amzn\.to'], 'modulo': 'amazon', 'classe': 'AmazonScraper'},
    'DELL': {'padroes_url': [r'dell\.com'], 'modulo': 'dell', 'classe': 'DellScraper'},
    'KABUM': {'padroes_url': [r'kabum\.com\.br'], 'modulo': 'kabum', 'classe': 'KabumScraper'},
    'BHPHOTOVIDEO': {'padroes_url': [r'bhphotovideo\.com'], 'modulo': 'bhphotovideo', 'classe': 'BhPhotoVideoScraper'},
    'FRIGELAR': {'padroes_url': [r'frigelar\.com\.br'], 'modulo': 'frigelar', 'classe': 'FrigelarScraper'},
    'samsung': {'padroes_url': [r'samsung\.com'], 'modulo': 'samsung', 'classe': 'SamsungScraper'}
    # Adicione os outros sites aqui conforme sua lista do config.py original
}

def identificar_site(url):
    # Mesmo critério de config.identificar_site: compara só o domínio.
    host = host_da_url(url)
    if not host:
        return None, None, None
    for site_nome, cfg in SITES_CONFIG.items():
        for padrao in cfg['padroes_url']:
            if re.search(r'(?:^|\.)' + padrao, host, re.IGNORECASE):
                return site_nome, cfg['modulo'], cfg['classe']
    return None, None, None

# ==============================================================================
# 🎨 GERADOR DE DOCUMENTOS (Antigo generator.py)
# ==============================================================================

class DocGenerator:
    def _redimensionar_imagem(self, image_path):
        try:
            img = Image.open(image_path)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                alpha = img.convert('RGBA').split()[-1]
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=alpha)
                img = bg
            else:
                img = img.convert("RGB")
            MAX_SIZE = 500
            img.thumbnail((MAX_SIZE, MAX_SIZE), Image.Resampling.LANCZOS)
            square = Image.new('RGB', (MAX_SIZE, MAX_SIZE), (255, 255, 255))
            square.paste(img, ((MAX_SIZE - img.width) // 2, (MAX_SIZE - img.height) // 2))
            square.save(image_path, "JPEG", quality=95)
            return True
        except Exception as e:
            print(f"   ⚠️ Erro PIL: {e}", flush=True)
            registrar_erro_modulo("GERADOR_DOCUMENTOS", f"Erro PIL ao redimensionar imagem ({image_path}): {e}")
            return False

    def create_word(self, data, filepath):
        try:
            doc = Document()
            # Cabeçalho
            p = doc.add_paragraph()
            p.add_run(HEADER_INFO["empresa"] + "\n").bold = True
            p.add_run(f"{HEADER_INFO['cnpj']}\n{HEADER_INFO['endereco']}").font.size = Pt(9)
            
            doc.add_heading(data.get("titulo", "Produto"), 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            img_path = data.get("caminho_imagem_temp")
            if img_path and os.path.exists(img_path):
                self._redimensionar_imagem(img_path)
                doc.add_picture(img_path, width=Inches(3.2))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            doc.add_heading('Descrição', level=1)
            doc.add_paragraph(data.get("descricao", "Sem descrição disponível."))
            
            specs = data.get("caracteristicas", {})
            if specs:
                doc.add_heading('Ficha Técnica', level=1)
                table = doc.add_table(rows=0, cols=2)
                table.style = 'Table Grid'
                for k, v in (specs.items() if isinstance(specs, dict) else specs):
                    row = table.add_row().cells
                    row[0].text = str(k)
                    row[1].text = str(v)
            doc.save(filepath)
            registrar_log(f"Arquivo Word gerado com sucesso: {filepath}", nivel="INFO", modulo="GERADOR_DOCUMENTOS")
            return True
        except Exception as e:
            print(f"   [ERRO WORD] {e}", flush=True)
            registrar_erro_modulo("GERADOR_DOCUMENTOS", f"Erro ao gerar arquivo Word ({filepath}): {e}", titulo=data.get("titulo"))
            return False

    def create_pdf(self, data, filepath):
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_auto_page_break(auto=True, margin=15)
            def txt(s): return str(s).encode('latin-1', 'replace').decode('latin-1')

            pdf.set_font("Helvetica", 'B', 10)
            pdf.cell(0, 5, txt(HEADER_INFO["empresa"]), ln=True)
            pdf.set_font("Helvetica", '', 8)
            pdf.cell(0, 4, txt(HEADER_INFO["cnpj"]), ln=True)
            pdf.cell(0, 4, txt(HEADER_INFO["endereco"]), ln=True)
            pdf.ln(10)

            pdf.set_font("Helvetica", 'B', 14)
            pdf.multi_cell(0, 8, txt(data.get("titulo", "Produto")), align='C')
            
            img_path = data.get("caminho_imagem_temp")
            if img_path and os.path.exists(img_path):
                pdf.image(img_path, x=65, w=80)
                pdf.ln(5)

            pdf.set_font("Helvetica", 'B', 11)
            pdf.cell(0, 8, txt("Descrição"), ln=True)
            pdf.set_font("Helvetica", '', 10)
            pdf.multi_cell(0, 5, txt(data.get("descricao", "")[:3000]))
            
            specs = data.get("caracteristicas", {})
            if specs:
                pdf.ln(5)
                pdf.set_font("Helvetica", 'B', 11)
                pdf.cell(0, 8, txt("Ficha Técnica"), ln=True)
                for k, v in (specs.items() if isinstance(specs, dict) else specs):
                    pdf.set_font("Helvetica", 'B', 9)
                    pdf.cell(0, 6, txt(str(k)), ln=True, fill=True)
                    pdf.set_font("Helvetica", '', 9)
                    pdf.multi_cell(0, 5, txt(str(v)), border='B')
            pdf.output(filepath)
            registrar_log(f"Arquivo PDF gerado com sucesso: {filepath}", nivel="INFO", modulo="GERADOR_DOCUMENTOS")
            return True
        except Exception as e:
            print(f"   [ERRO PDF] {e}", flush=True)
            registrar_erro_modulo("GERADOR_DOCUMENTOS", f"Erro ao gerar arquivo PDF ({filepath}): {e}", titulo=data.get("titulo"))
            return False

# ==============================================================================
# 🚀 GERENCIADOR E API (Antigo scraper_manager.py e api.py)
# ==============================================================================

app = Flask(__name__)
pedidos = {}
LIMITE_PEDIDOS_GUARDADOS = 1000


def guardar_pedido(req_id, dados_pedido):
    # Mantém só os pedidos mais recentes; os em andamento nunca são descartados.
    pedidos[req_id] = dados_pedido
    excesso = len(pedidos) - LIMITE_PEDIDOS_GUARDADOS
    if excesso > 0:
        for antigo in [k for k, v in list(pedidos.items()) if v.get('status') != 'processando'][:excesso]:
            pedidos.pop(antigo, None)


def enviar_webhook(webhook_url, payload, id_bot, url):
    registrar_log(
        f"Enviando callback para Webhook: {webhook_url} | Payload: {json.dumps(payload, ensure_ascii=False)}",
        nivel="INFO",
        modulo="WEBHOOK",
    )
    try:
        resp_wh = requests.post(webhook_url, json=payload, timeout=10)
        registrar_log(f"Webhook respondeu HTTP {resp_wh.status_code} para ID {id_bot}", nivel="INFO", modulo="WEBHOOK")
    except Exception as wh_err:
        registrar_erro_modulo("WEBHOOK", f"Erro ao enviar callback para Webhook ({webhook_url}): {wh_err}", url=url)

class ScraperManager:
    def executar_scraping(self, url, pasta_pedido):
        site_nome, modulo_nome, classe_nome = None, None, None
        inicio = time.time()
        try:
            definir_contexto_execucao(modulo="GERENCIADOR", url=url)
            registrar_log(f"Analisando URL recebida para seleção de módulo: {url}", nivel="INFO", modulo="GERENCIADOR")
            dominio_bloqueado = config.site_bloqueado(url)
            if dominio_bloqueado:
                msg_bloq = 'Site bloqueado para datasheet: ' + dominio_bloqueado
                registrar_erro_modulo("GERENCIADOR", msg_bloq, url=url)
                return {'sucesso': False, 'erro': msg_bloq}
            try:
                validar_url_produto(url)
            except ValueError as e:
                registrar_erro_modulo("GERENCIADOR", f"URL recusada: {e}", url=url)
                return {'sucesso': False, 'erro': str(e)}
            site_nome, modulo_nome, classe_nome = identificar_site(url)
            if not site_nome:
                # O cadastro completo fica em config.py; esta copia tem poucos sites.
                site_nome, modulo_nome, classe_nome = config.identificar_site(url)
            if not site_nome:
                if not config.UNIVERSAL_ATIVO:
                    msg_nao_cfg = 'Site não configurado'
                    registrar_erro_modulo("GERENCIADOR", msg_nao_cfg, url=url)
                    return {'sucesso': False, 'erro': msg_nao_cfg}
                site_nome, modulo_nome, classe_nome = 'UNIVERSAL', 'universal', 'UniversalScraper'
                dominio = (urlparse(url).hostname or "URL invalida").encode("ascii", "backslashreplace").decode("ascii")
                print(f"   --> Iniciando scraper: UNIVERSAL (site sem adapter: {dominio})", flush=True)
                registrar_modulo_ligado(site_nome, modulo_nome, classe_nome, url, detalhe=f"Site sem módulo específico ({dominio})")
            else:
                registrar_modulo_ligado(site_nome, modulo_nome, classe_nome, url)
            
            mod_id = identificar_modulo_scraper(site_nome=site_nome, modulo_nome=modulo_nome, classe_nome=classe_nome)
            definir_contexto_execucao(modulo=mod_id, url=url)
            # Importa dinamicamente da pasta /scrapers
            modulo = importlib.import_module(f"scrapers.{modulo_nome}")
            ClasseScraper = getattr(modulo, classe_nome)
            
            scraper = ClasseScraper(url)
            scraper.output_folder = pasta_pedido
            scraper.site_nome = site_nome
            scraper.modulo_nome = modulo_nome
            registrar_log(f"Iniciando execução de '{classe_nome}.executar()' | Pasta destino: {pasta_pedido}", nivel="EXECUCAO", modulo=mod_id)
            if site_nome == 'UNIVERSAL':
                print("   [ROBO] Iniciando: UNIVERSAL", flush=True)
            else:
                print(f"   [ROBO] Iniciando: {site_nome}", flush=True)
            resultado = scraper.executar()
            duracao = time.time() - inicio

            if isinstance(resultado, dict):
                if resultado.get('sucesso'):
                    problemas = getattr(scraper, 'problemas_detectados', [])
                    arqs = resultado.get('arquivos', {}) or {}
                    info_arqs = f"Word={arqs.get('word_nome', 'N/A')} | PDF={arqs.get('pdf_nome', 'N/A')}"
                    if problemas:
                        registrar_log(
                            f"Execução concluída em {duracao:.2f}s COM PROBLEMAS NOS DADOS DO ITEM: {'; '.join(problemas)} | {info_arqs} | URL: {url}",
                            nivel="AVISO",
                            modulo=mod_id,
                        )
                    else:
                        registrar_log(
                            f"Execução concluída com SUCESSO COMPLETO em {duracao:.2f}s | {info_arqs} | URL: {url}",
                            nivel="SUCESSO",
                            modulo=mod_id,
                        )
                else:
                    erro_msg = resultado.get('erro', 'Erro desconhecido')
                    registrar_erro_modulo(
                        mod_id,
                        f"Falha na execução do módulo após {duracao:.2f}s: {erro_msg}",
                        url=url,
                    )
            return resultado
        except Exception as e:
            duracao = time.time() - inicio
            mod_id = identificar_modulo_scraper(site_nome=site_nome, modulo_nome=modulo_nome, classe_nome=classe_nome)
            registrar_erro_modulo(
                mod_id,
                f"Exceção crítica no módulo após {duracao:.2f}s: {e}",
                url=url,
                incluir_traceback=True,
            )
            return {'sucesso': False, 'erro': str(e)}

scraper_manager = ScraperManager()

def processar_pedido_background(request_id_interno, url, webhook_url, origem, codigo_tarefa, custom_id):
    inicio_pedido = time.time()
    id_bot = custom_id or codigo_tarefa or request_id_interno
    definir_contexto_execucao(modulo="API", url=url, pedido_id=id_bot)
    try:
        registrar_separador("-")
        registrar_log(
            f"INÍCIO DE EXECUÇÃO DO PEDIDO | ID: {id_bot} | UUID Interno: {request_id_interno} | Código Tarefa: {codigo_tarefa} | URL: {url}",
            nivel="INFO",
            modulo="API",
        )
        
        resultado = scraper_manager.executar_scraping(url, OUTPUT_DIR)
        duracao_total = time.time() - inicio_pedido
        
        base_url = "http://localhost:6004"
        files = resultado.get('arquivos', {})
        link_word = f"{base_url}/download/{files.get('word_nome')}" if files.get('word_nome') else None
        link_pdf = f"{base_url}/download/{files.get('pdf_nome')}" if files.get('pdf_nome') else None

        if resultado.get('sucesso'):
            registrar_log(
                f"Arquivos gerados com sucesso em {duracao_total:.2f}s para ID {id_bot} | PDF: {link_pdf} | Word: {link_word}",
                nivel="SUCESSO",
                modulo="API",
            )
            payload = {
                "status": "CONCLUIDO", "sucesso": True, "request_id": id_bot,
                "codigoTarefa": codigo_tarefa,
                "download": {"pdf": link_pdf, "word": link_word}
            }
        else:
            erro_msg = resultado.get('erro', 'Erro desconhecido')
            registrar_erro_modulo("API", f"Falha ao processar pedido {id_bot} após {duracao_total:.2f}s: {erro_msg}", url=url)
            payload = {"status": "ERRO", "sucesso": False, "request_id": id_bot,
                       "codigoTarefa": codigo_tarefa, "erro": erro_msg}

        pedidos[request_id_interno]['resultado'] = payload
        pedidos[request_id_interno]['status'] = 'concluido' if resultado.get('sucesso') else 'erro'

        if webhook_url:
            enviar_webhook(webhook_url, payload, id_bot, url)

        registrar_log(
            f"FIM DE EXECUÇÃO DO PEDIDO {id_bot} | Status: {pedidos[request_id_interno]['status'].upper()} | Tempo Total: {duracao_total:.2f}s",
            nivel="INFO",
            modulo="API",
        )
        registrar_separador("-")
    except Exception as e:
        registrar_erro_modulo("API_THREAD", f"Erro crítico no processamento em background: {e}", url=url, incluir_traceback=True)
        # Sem isto o pedido ficava 'processando' para sempre e o bot nunca recebia retorno.
        payload = {"status": "ERRO", "sucesso": False, "request_id": id_bot,
                   "codigoTarefa": codigo_tarefa, "erro": f"Erro interno: {e}"}
        pedidos[request_id_interno]['resultado'] = payload
        pedidos[request_id_interno]['status'] = 'erro_critico'
        if webhook_url:
            enviar_webhook(webhook_url, payload, id_bot, url)
    finally:
        limpar_contexto_execucao()

@app.route('/api/datasheet/processar', methods=['POST'])
def iniciar():
    ip_cliente = request.remote_addr or "desconhecido"
    registrar_log(f"Nova requisição HTTP POST recebida em /api/datasheet/processar (IP: {ip_cliente})", nivel="INFO", modulo="API")
    if not token_valido(request.headers):
        registrar_erro_modulo("API", f"Requisição de {ip_cliente} recusada: token ausente ou inválido.")
        return jsonify({"error": "Não autorizado"}), 401
    dados = request.get_json(silent=True, force=True)
    if not dados or not isinstance(dados, dict):
        registrar_erro_modulo("API", f"Requisição de {ip_cliente} recebida com JSON inválido ou vazio.")
        return jsonify({"error": "JSON inválido"}), 400

    registrar_log(f"Payload completo recebido: {json.dumps(dados, ensure_ascii=False)}", nivel="INFO", modulo="API")

    bloco = dados.get('dados') if isinstance(dados.get('dados'), dict) else {}
    url = dados.get('url') or bloco.get('url')
    # Antes, um bloco 'dados' sem webhook_url deixava o pedido sem retorno nenhum.
    webhook = dados.get('webhook_url') or bloco.get('webhook_url') or URL_CALLBACK_PADRAO
    c_tarefa = dados.get('codigoTarefa')
    c_id = dados.get('custom_id') or dados.get('id')

    if not url or not isinstance(url, str):
        registrar_erro_modulo("API", f"Requisição recebida sem URL: {dados}")
        return jsonify({"error": "URL faltando"}), 400
    if not webhook_permitido(webhook):
        registrar_erro_modulo("API", f"Webhook recusado: {webhook}")
        return jsonify({"error": "webhook_url inválido ou não permitido"}), 400

    req_id = str(uuid.uuid4())
    guardar_pedido(req_id, {'status': 'processando'})

    thread = threading.Thread(target=processar_pedido_background, args=(req_id, url, webhook, "API", c_tarefa, c_id))
    thread.daemon = True
    thread.start()

    return jsonify({"success": True, "request_id": req_id}), 202

@app.route('/download/<path:filename>')
def download(filename):
    registrar_log(f"Download solicitado do arquivo: {filename}", nivel="INFO", modulo="API_DOWNLOAD")
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

@app.route('/health')
def health():
    return jsonify({"status": "online", "pasta": OUTPUT_DIR, "log_file": obter_caminho_log(), "pedidos_ativos": sum(1 for p in list(pedidos.values()) if p.get('status') == 'processando')})

if __name__ == '__main__':
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    registrar_separador("=")
    registrar_log("[ROBO] DATASHEET MONOLITO ONLINE - PORTA 6004", nivel="INFO", modulo="SISTEMA")
    registrar_log(f"[ROBO] SALVANDO DATASHEETS EM: {OUTPUT_DIR}", nivel="INFO", modulo="SISTEMA")
    registrar_log(f"[ROBO] SALVANDO LOG EM TEMPO REAL EM: {obter_caminho_log()}", nivel="INFO", modulo="SISTEMA")
    registrar_separador("=")
    app.run(host='0.0.0.0', port=6004, threaded=True, debug=False)
