# run.py
from api import app

if __name__ == '__main__':
    print("="*60)
    print(" Robô Iniciado | Porta ")
    print(" Modo Multi-Thread Ativado")
    print("="*60)
    
    # O parâmetro threaded=True é ESSENCIAL para que o robô 
    # consiga processar várias URLs ao mesmo tempo sem travar.
    app.run(host='0.0.0.0', port=6004, threaded=True)