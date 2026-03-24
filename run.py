# run.py
import sys
import os
import logging

# 1. CLASSE PARA FORÇAR O PYTHON A CUSPIR O TEXTO NA TELA NA MESMA HORA
class FlushAutomatico:
    def __init__(self, stream):
        self.stream = stream
    def write(self, data):
        self.stream.write(data)
        self.stream.flush() # <--- O segredo está aqui (força a impressão imediata)
    def writelines(self, datas):
        self.stream.writelines(datas)
        self.stream.flush()
    def __getattr__(self, attr):
        return getattr(self.stream, attr)

# Substitui as saídas padrão do sistema pela nossa saída forçada
sys.stdout = FlushAutomatico(sys.stdout)
sys.stderr = FlushAutomatico(sys.stderr)

# 2. OBRIGA A API (FLASK/WERKZEUG) A MOSTRAR TODAS AS REQUISIÇÕES
log_api = logging.getLogger('werkzeug')
log_api.setLevel(logging.INFO)

# Importa a sua API
from api import app

if __name__ == '__main__':
    print("\n" + "="*60)
    print(" 🤖 Robô Iniciado com Sucesso | Porta 3001 ")
    print(" 📡 MODO RAIO-X: Todos os logs e requisições na tela! ")
    print(" Aguardando chamadas na API... ")
    print("="*60 + "\n")
    
    # Inicia o servidor
    app.run(host='0.0.0.0', port=3001, threaded=True)