# api.py
from flask import Flask, request, jsonify, send_from_directory
import threading
import uuid
import os
import requests
import json
from datetime import datetime
from scraper_manager import ScraperManager

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
print(f"📁 ARQUIVOS SERÃO SALVOS EM: {OUTPUT_DIR}")

URL_CALLBACK_API_NOVA = "http://127.0.0.1:3000/api/datasheet/webhook"

# ==============================================================================

scraper_manager = ScraperManager()
pedidos = {}

def processar_pedido_background(request_id_interno, url, webhook_url, origem="PADRAO", codigo_tarefa_externo=None, custom_id=None):
    try:
        pasta_pedido = OUTPUT_DIR 
        
        print(f"\n🔧 [PROCESSANDO] UUID Interno: {request_id_interno}")
        
        # Define qual ID será enviado de volta.
        # Se o bot mandou um custom_id, usamos ele como PRINCIPAL.
        # Se não mandou, usamos o UUID interno gerado pelo Python.
        id_final_para_bot = custom_id if custom_id else request_id_interno

        if custom_id:
            print(f"   🔖 ID DO CLIENTE: {custom_id}")
        
        # Executa o Scraper
        resultado = scraper_manager.executar_scraping(url, pasta_pedido)
        
        base_url = "http://localhost:6004"
        files = resultado.get('arquivos', {})
        
        link_word = f"{base_url}/download/{files.get('word_nome')}" if files.get('word_nome') else None
        link_pdf = f"{base_url}/download/{files.get('pdf_nome')}" if files.get('pdf_nome') else None

        payload_final = {}

        if resultado.get('sucesso'):
            print("   ✅ Sucesso! Preparando webhook...")

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
            print(f"   ❌ Falha: {msg_erro}")

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
            print(f"   📤 Enviando para Webhook: {webhook_url}")
            try:
                requests.post(webhook_url, json=payload_final, timeout=10)
            except Exception as e:
                print(f"   ❌ Erro ao chamar Webhook: {e}")

    except Exception as e:
        print(f"   💥 Erro Crítico na Thread: {str(e)}")
        pedidos[request_id_interno]['status'] = 'erro_critico'

# --- ROTAS DA API ---

@app.route('/api/datasheet/processar', methods=['POST'])
def iniciar_scraping():
    dados = request.get_json()
    
    lista_processamento = [] 
    
    # 1. API NOVA
    if 'codigoTarefa' in dados:
        codigo_tarefa = dados.get('codigoTarefa')
        bloco_dados = dados.get('dados', {})
        url = bloco_dados.get('url')
        if url:
            lista_processamento.append({
                "url": url,
                "webhook": URL_CALLBACK_API_NOVA, 
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
        return jsonify({"error": "Nenhuma URL fornecida"}), 400

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
        return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({"error": "Arquivo não encontrado"}), 404

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "online",
        "pasta": OUTPUT_DIR,
        "pedidos_ativos": sum(1 for p in pedidos.values() if p['status'] == 'processando')
    })

if __name__ == '__main__':
    print("="*60)
    print("🚀 API V7 - UNIVERSAL ID RESPONSE")
    print("   O Bot receberá o ID em: 'request_id', 'custom_id', 'id'")
    print("="*60)
    app.run(host='0.0.0.0', port=6004, threaded=True, debug=False)