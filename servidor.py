# servidor.py
import os
import threading
import requests
from flask import Flask, request, jsonify, send_from_directory
from scraper_manager import ScraperManager

app = Flask(__name__)
scraper_manager = ScraperManager()

# 1. CONFIGURAÇÃO DE PASTAS DEFINITIVA
OUTPUT_DIR = r"\\SERVIDOR2\Publico\Datasheet"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Webhook padrão caso o WhatsApp não mande um específico na requisição
WEBHOOK_PADRAO = "http://127.0.0.1:3000/api/datasheet/webhook"

# ==============================================================================
# 🛠️ O TRABALHADOR DE FUNDO (A Mágica)
# ==============================================================================
def processar_e_avisar(url, webhook_url, custom_id):
    try:
        # 1. Manda o scraper fazer o trabalho pesado
        resultado = scraper_manager.executar_scraping(url, OUTPUT_DIR)
        
        # 2. Prepara os links de download se der certo
        base_url = "http://127.0.0.1:6004"
        link_pdf = None
        link_word = None
        
        if resultado.get('sucesso') and 'arquivos' in resultado:
            link_pdf = f"{base_url}/download/{resultado['arquivos'].get('pdf_nome')}"
            link_word = f"{base_url}/download/{resultado['arquivos'].get('word_nome')}"

        # 3. Monta o pacote de resposta exatamente como o WhatsApp gosta
        if resultado.get('sucesso'):
            payload = {
                "status": "Feito",
                "request_id": custom_id,
                "custom_id": custom_id,
                "id": custom_id,
                "download": {
                    "pdf": link_pdf,
                    "word": link_word
                }
            }
        else:
            payload = {
                "status": "Erro",
                "request_id": custom_id,
                "custom_id": custom_id,
                "mensagem": resultado.get('erro', 'Erro interno ao processar o site.')
            }

        # 4. Atira a resposta de volta (Webhook)
        url_alvo = webhook_url if webhook_url else WEBHOOK_PADRAO
        requests.post(url_alvo, json=payload, timeout=10)

    except Exception:
        pass # Se der erro catastrófico, ele morre em silêncio sem derrubar o servidor

# ==============================================================================
# 🚪 AS PORTAS DA API
# ==============================================================================

@app.route('/api/datasheet/processar', methods=['POST'])
def receber_pedido():
    dados = request.get_json() or {}
    
    # Caça a URL de todas as formas possíveis que o bot possa mandar
    url = dados.get('url') or dados.get('link')
    urls = dados.get('urls', [])
    if url: 
        urls.append(url)
        
    webhook = dados.get('webhook_url')
    
    # Caça o ID do pedido
    custom_id = dados.get('custom_id') or dados.get('pedido_id') or dados.get('id') or "ID_DESCONHECIDO"

    if not urls:
        return jsonify({"success": False, "error": "Nenhuma URL fornecida"}), 400

    # Pega as URLs (removendo repetidas) e joga para as threads de segundo plano
    for u in set(urls):
        thread = threading.Thread(target=processar_e_avisar, args=(u, webhook, custom_id))
        thread.daemon = True
        thread.start()

    return jsonify({
        "success": True,
        "message": "Processamento iniciado no novo servidor!"
    }), 202

@app.route('/download/<path:filename>', methods=['GET'])
def baixar_arquivo(filename):
    # Permite que o C#/Node faça o download do arquivo que está no Servidor 2
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

# ==============================================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print(" 🚀 SERVIDOR NOVO E LIMPO INICIADO | PORTA 6004")
    print(" 📂 Salvando em:", OUTPUT_DIR)
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=6004, threaded=True, debug=False)