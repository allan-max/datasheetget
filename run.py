import os
import sys

# Desativa o buffer do Python para os prints não ficarem presos na memória
os.environ["PYTHONUNBUFFERED"] = "1" 

# Força o Windows a entender acentos sem travar o terminal
os.environ["PYTHONIOENCODING"] = "utf-8"

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except:
    pass

from api import app

if __name__ == '__main__':
    print("\n" + "="*60)
    print(" 🚀 SISTEMA DE DATASHEET ONLINE | PORTA 6005") # Atualize o texto
    print(" 🛡️ Motor do Chrome Liberado e Estável")
    print("="*60 + "\n")
    # Mude a porta aqui para 6005:
    app.run(host='0.0.0.0', port=6005, threaded=True, debug=False)