# run.py
import os
import sys
import builtins
import logging

# 1. FORÇA O SISTEMA OPERACIONAL A NÃO GUARDAR TEXTO NA MEMÓRIA
os.environ["PYTHONUNBUFFERED"] = "1"

# 2. RECONECTA OS CANAIS DIRETAMENTE AO MONITOR FÍSICO DO WINDOWS
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

# 3. O HACK DO PRINT: Obriga qualquer print no código a ir para a tela instantaneamente
_print_original = builtins.print

def print_forçado(*args, **kwargs):
    kwargs['file'] = sys.__stdout__
    kwargs['flush'] = True
    _print_original(*args, **kwargs)

builtins.print = print_forçado

# 4. FORÇA A API (FLASK/WERKZEUG) A ANUNCIAR AS REQUISIÇÕES
log_api = logging.getLogger('werkzeug')
log_api.setLevel(logging.INFO)
if not log_api.handlers:
    handler = logging.StreamHandler(sys.__stdout__)
    log_api.addHandler(handler)

# Só importamos a API depois de blindar os logs
from api import app

if __name__ == '__main__':
    print("\n" + "="*60)
    print(" 🤖 Robô Iniciado com Sucesso | Porta 3001 ")
    print(" 📡 MODO RAIO-X NÍVEL MÁXIMO ATIVADO! ")
    print(" Nenhuma biblioteca conseguirá ocultar os logs agora.")
    print(" Aguardando chamadas na API...")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=3001, threaded=True)