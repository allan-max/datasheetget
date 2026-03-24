# run.py
import logging
import sys
import os
import datetime
from flask import request

# Força o terminal a não engasgar com acentos
os.environ["PYTHONIOENCODING"] = "utf-8"

# 1. PREPARANDO O ARQUIVO DE LOG EXTREMO
PASTA_DO_LOG = r"\\SERVIDOR2\Publico\ALLAN\Logs"
try:
    os.makedirs(PASTA_DO_LOG, exist_ok=True)
except:
    pass
ARQUIVO_LOG = os.path.join(PASTA_DO_LOG, "log_extremo_datasheet.txt")

# 2. CONFIGURANDO O LOGGER "DEDO-DURO"
# Ele vai gravar TUDO, nível DEBUG (o mais detalhado possível)
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(ARQUIVO_LOG, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('RoboMaster')

# Redireciona qualquer "print" antigo que ficou nos scrapers para o nosso Logger
def print_interceptado(*args, **kwargs):
    mensagem = " ".join(str(arg) for arg in args)
    logger.debug(f"[PRINT SCRIPT] {mensagem}")

import builtins
builtins.print = print_interceptado

# Importa a API
from api import app

# ==============================================================================
# 🚨 INTERCEPTADORES DE ROTA (Eles gritam antes mesmo do código processar)
# ==============================================================================

@app.before_request
def rastrear_entrada():
    logger.info(f">>> ALGUÉM BATEU NA PORTA: {request.method} {request.url}")
    try:
        corpo = request.get_json(silent=True)
        logger.debug(f">>> DADOS RECEBIDOS (JSON): {corpo}")
    except:
        logger.debug(f">>> DADOS RECEBIDOS (TEXTO): {request.get_data(as_text=True)}")

@app.after_request
def rastrear_saida(response):
    logger.info(f"<<< DEVOLVENDO RESPOSTA: Status {response.status}")
    return response

# ==============================================================================

if __name__ == '__main__':
    logger.info("="*60)
    logger.info(" ☢️  INICIANDO MODO DE RASTREAMENTO EXTREMO")
    logger.info(" 🚪 PORTA DEFINIDA PARA: 6004 (Alinhada com o seu bot)")
    logger.info("="*60)
    
    # Rodando na porta 6004 para garantir que o WhatsApp caia aqui
    app.run(host='0.0.0.0', port=6004, threaded=True, debug=False)