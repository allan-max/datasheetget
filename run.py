# run.py
import sys
import os

from api import app

if __name__ == '__main__':
    print("="*60)
    print(" Robô Iniciado | Porta 3001 ")
    print(" Modo Simples (Erros direto no ecrã) ")
    print("="*60)
    app.run(host='0.0.0.0', port=3001, threaded=True)