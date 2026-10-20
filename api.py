# api.py
from flask import Flask, request, jsonify, send_from_directory
import threading
import uuid
import os
import logging
import sys
import time
import requests
import json
from datetime import datetime
from scraper_manager import ScraperManager
from utils.logger import (
    ativar_captura_global,
    definir_contexto_execucao,
    limpar_contexto_execucao,
    obter_caminho_log,
    registrar_erro_modulo,
    registrar_log,
    registrar_separador,
)

# --- FORÇAR EXIBIÇÃO DE LOGS NO TERMINAL ---
os.environ["PYTHONUNBUFFERED"] = "1" 
os.environ["PYTHONIOENCODING"] = "utf-8"

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except:
    pass

# Ativa a gravação contínua de tudo no arquivo \\SERVIDOR2\Publico\ALLAN\Logs\datasheet.txt
ativar_captura_global()

# --- CONFIGURAÇÃO DO NOVO SISTEMA DE LOGS ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(threadName)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==============================================================================
# ⚙️ CONFIGURAÇÃO DA PASTA DE SAÍDA
# ==============================================================================

CAMINHO_PERSONALIZADO = r"\\SERVIDOR2\Publico\Datasheet"

if CAMINHO_PERSONALIZADO:
    OUTPUT_DIR = CAMINHO_PERSONALIZADO
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_DIR = os.path.join(BASE_DIR, 'output')

os.makedirs(OUTPUT_DIR, exist_ok=True)
registrar_separador("=")
registrar_log("ROBO DATASHEET INICIADO!", nivel="INFO", modulo="SISTEMA")
registrar_log(f"ARQUIVOS DE DATASHEET SERÃO SALVOS EM: {OUTPUT_DIR}", nivel="INFO", modulo="SISTEMA")
registrar_log(f"ARQUIVO DE LOG ATIVO EM TEMPO REAL: {obter_caminho_log()}", nivel="INFO", modulo="SISTEMA")
registrar_separador("=")

URL_CALLBACK_API_NOVA = "http://127.0.0.1:3000/api/datasheet/webhook"

# ==============================================================================

scraper_manager = ScraperManager()
pedidos = {}

def processar_pedido_background(request_id_interno, url, webhook_url, origem="PADRAO", codigo_tarefa_externo=None, custom_id=None):
    inicio_pedido = time.time()
    id_final_para_bot = custom_id or codigo_tarefa_externo or request_id_interno
    definir_contexto_execucao(modulo="API", url=url, pedido_id=id_final_para_bot)
    try:
        pasta_pedido = OUTPUT_DIR 

        registrar_separador("-")
        registrar_log(
            f"INÍCIO DE EXECUÇÃO DO PEDIDO | ID: {id_final_para_bot} | UUID Interno: {request_id_interno} | Origem: {origem} | URL: {url}",
            nivel="INFO",
            modulo="API",
        )
        
        # Executa o Scraper
        resultado = scraper_manager.executar_scraping(url, pasta_pedido)
        duracao_total = time.time() - inicio_pedido
        
        base_url = "http://localhost:6004"
        files = resultado.get('arquivos', {})
        
        link_word = f"{base_url}/download/{files.get('word_nome')}" if files.get('word_nome') else None
        link_pdf = f"{base_url}/download/{files.get('pdf_nome')}" if files.get('pdf_nome') else None

        payload_final = {}

        if resultado.get('sucesso'):
            registrar_log(
                f"Datasheet finalizado em {duracao_total:.2f}s para o pedido {id_final_para_bot} | PDF: {link_pdf} | Word: {link_word}",
                nivel="SUCESSO",
                modulo="API",
            )

            if origem == "API_NOVA":
                payload_final = {
                    "codigoTarefa": codigo_tarefa_externo,
                    "status": "CONCLUIDO",
                    "sucesso": True,
                    "resultado": {
                        "arquivos": { "pdf": link_pdf, "word": link_word }
                    }
                }
            else:
                # --- RESPOSTA UNIVERSAL (AQUI ESTÁ A CORREÇÃO) ---
                # Enviamos o ID em VÁRIOS campos para garantir que o Bot entenda
                payload_final = {
                    "status": "Feito",
                    
                    # O Bot vai achar o ID dele aqui, não importa onde procure:
                    "request_id": id_final_para_bot,  
                    "custom_id": id_final_para_bot,
                    "id": id_final_para_bot,
                    "pedido_id": id_final_para_bot,

                    "download": {
                        "pdf": link_pdf,
                        "word": link_word
                    }
                }
        else:
            msg_erro = resultado.get('erro', 'Erro desconhecido')
            registrar_erro_modulo("API", f"Pedido {id_final_para_bot} falhou após {duracao_total:.2f}s: {msg_erro}", url=url)

            if origem == "API_NOVA":
                payload_final = {
                    "codigoTarefa": codigo_tarefa_externo,
                    "status": "ERRO",
                    "sucesso": False,
                    "erro": msg_erro
                }
            else:
                payload_final = {
                    "status": "Erro",
                    # Devolvemos o ID mesmo no erro
                    "request_id": id_final_para_bot,
                    "custom_id": id_final_para_bot,
                    "id": id_final_para_bot,
                    
                    "mensagem": msg_erro
                }

        # Atualiza status interno
        pedidos[request_id_interno]['resultado'] = payload_final
        pedidos[request_id_interno]['status'] = 'concluido' if resultado.get('sucesso') else 'erro'

        # --- ENVIO DO WEBHOOK ---
        if webhook_url:
            registrar_log(
                f"Enviando retorno para Webhook: {webhook_url} | Payload: {json.dumps(payload_final, ensure_ascii=False)}",
                nivel="INFO",
                modulo="WEBHOOK",
            )
            try:
                resp_wh = requests.post(webhook_url, json=payload_final, timeout=10)
                registrar_log(f"Webhook respondeu HTTP {resp_wh.status_code} para ID {id_final_para_bot}", nivel="INFO", modulo="WEBHOOK")
            except Exception as e:
                registrar_erro_modulo("WEBHOOK", f"Erro ao enviar callback para Webhook ({webhook_url}): {e}", url=url)

        registrar_log(
            f"FIM DE EXECUÇÃO DO PEDIDO {id_final_para_bot} | Status: {pedidos[request_id_interno]['status'].upper()} | Tempo Total: {duracao_total:.2f}s",
            nivel="INFO",
            modulo="API",
        )
        registrar_separador("-")

    except Exception as e:
        registrar_erro_modulo("API_THREAD", f"Erro crítico na thread de processamento: {str(e)}", url=url, incluir_traceback=True)
        pedidos[request_id_interno]['status'] = 'erro_critico'
    finally:
        limpar_contexto_execucao()

# --- ROTAS DA API ---

@app.route('/api/datasheet/processar', methods=['POST'])
def iniciar_scraping():
    ip_cliente = request.remote_addr or "desconhecido"
    registrar_log(f"Nova requisição HTTP POST recebida em /api/datasheet/processar (IP: {ip_cliente})", nivel="INFO", modulo="API")
    
    # force=True ignora caso o bot do Node.js esqueça o header Content-Type
    # silent=True evita que o Flask quebre a aplicação se o JSON vier malformado
    dados = request.get_json(silent=True, force=True)
    
    if not dados:
        registrar_erro_modulo("API", f"Requisição de {ip_cliente} recebida sem corpo JSON ou com JSON inválido.")
        return jsonify({"error": "Nenhuma URL fornecida ou JSON inválido"}), 400

    registrar_log(f"Payload completo recebido na API: {json.dumps(dados, ensure_ascii=False)}", nivel="INFO", modulo="API")
    
    lista_processamento = [] 
    
    # 1. API NOVA
    if 'codigoTarefa' in dados:
        codigo_tarefa = dados.get('codigoTarefa')
        bloco_dados = dados.get('dados', {})
        url = bloco_dados.get('url')
        
        # Puxa o webhook que o bot mandou, se não tiver, usa o padrão
        webhook_dinamico = bloco_dados.get('webhook_url') or URL_CALLBACK_API_NOVA
        
        if url:
            lista_processamento.append({
                "url": url,
                "webhook": webhook_dinamico, 
                "origem": "API_NOVA",
                "codigo_tarefa": codigo_tarefa,
                "custom_id": None
            })
            
    # 2. PADRÃO (SEU BOT)
    else:
        urls_entrada = dados.get('urls', [])
        url_unica = dados.get('url') or dados.get('link')
        webhook_entrada = dados.get('webhook_url')
        
        # Captura o ID do Bot
        custom_id_entrada = (
            dados.get('custom_id') or 
            dados.get('pedido_id') or 
            dados.get('id') or 
            dados.get('id_externo')
        )
        
        if url_unica: urls_entrada.append(url_unica)
            
        for u in urls_entrada:
            lista_processamento.append({
                "url": u,
                "webhook": webhook_entrada,
                "origem": "PADRAO",
                "codigo_tarefa": None,
                "custom_id": custom_id_entrada
            })

    if not lista_processamento:
        registrar_erro_modulo("API", f"JSON recebido sem nenhuma URL válida: {dados}")
        return jsonify({"error": "Nenhuma URL fornecida no corpo da requisição"}), 400

    ids_gerados = []
    
    for item in lista_processamento:
        request_id_interno = str(uuid.uuid4())
        
        pedidos[request_id_interno] = {
            'url': item['url'],
            'status': 'processando',
            'origem': item['origem'],
            'custom_id': item['custom_id'],
            'criado_em': datetime.now().isoformat()
        }

        thread = threading.Thread(
            target=processar_pedido_background,
            args=(
                request_id_interno, 
                item['url'], 
                item['webhook'], 
                item['origem'], 
                item['codigo_tarefa'], 
                item['custom_id']
            )
        )
        thread.daemon = True
        thread.start()
        
        ids_gerados.append(request_id_interno)

    return jsonify({
        "success": True,
        "message": "Processamento iniciado",
        "ids_internos": ids_gerados
    }), 202

@app.route('/api/status/<request_id>', methods=['GET'])
def verificar_status(request_id):
    if request_id not in pedidos:
        return jsonify({"success": False, "message": "ID não encontrado"}), 404
    
    pedido = pedidos[request_id]
    if pedido['status'] in ['concluido', 'erro', 'erro_critico']:
        return jsonify(pedido.get('resultado', {}))
    
    return jsonify({"success": True, "status": pedido['status']})

@app.route('/download/<path:filename>', methods=['GET'])
def download_arquivo(filename):
    try:
        registrar_log(f"Download solicitado do arquivo: {filename}", nivel="INFO", modulo="API_DOWNLOAD")
        return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        registrar_erro_modulo("API_DOWNLOAD", f"Arquivo solicitado para download não encontrado: {filename}")
        return jsonify({"error": "Arquivo não encontrado"}), 404

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "online",
        "pasta": OUTPUT_DIR,
        "log_file": obter_caminho_log(),
        "pedidos_ativos": sum(1 for p in pedidos.values() if p['status'] == 'processando')
    })

if __name__ == '__main__':
    registrar_separador("=")
    registrar_log("API V7 - UNIVERSAL ID RESPONSE INICIADA NA PORTA 6004", nivel="INFO", modulo="SISTEMA")
    registrar_log(f"Monitoramento e logs salvando continuamente em: {obter_caminho_log()}", nivel="INFO", modulo="SISTEMA")
    registrar_separador("=")
    app.run(host='0.0.0.0', port=6004, threaded=True, debug=False)
