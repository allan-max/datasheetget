# run.py
import sys
import os
import builtins

# 1. Proíbe o Python de segurar texto na memória
os.environ["PYTHONUNBUFFERED"] = "1"

# 2. O PRINT "TANQUE DE GUERRA"
def print_direto_na_veia(*args, **kwargs):
    texto = " ".join(str(a) for a in args)
    
    # A MÁGICA: Converte emojis e acentos que travam o CMD em "?"
    texto_seguro = texto.encode('ascii', errors='replace').decode('ascii')
    
    # Escreve direto na porta física do monitor (sys.__stdout__), pulando o Flask
    try:
        sys.__stdout__.write(texto_seguro + "\n")
        sys.__stdout__.flush()
    except:
        pass

# Obriga todos os scrapers e a API a usarem o nosso print
builtins.print = print_direto_na_veia

from api import app

if __name__ == '__main__':
    print("="*60)
    print(" >>> ROBO INICIADO | PORTA 6004 <<< ")
    print(" MODO TAGARELA: Mostrando absolutamente tudo na tela! ")
    print("="*60)
    app.run(host='0.0.0.0', port=6004, threaded=True, debug=False)