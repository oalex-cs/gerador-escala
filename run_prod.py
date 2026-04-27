import sys
from waitress import serve
from app import app

if __name__ == "__main__":
    print("=" * 60)
    print("Iniciando Servidor de Produção (Waitress)")
    print("Escala de Culto - Gestão de Membros")
    print("Acesse: http://0.0.0.0:8000")
    print("Para parar, pressione Ctrl+C")
    print("=" * 60)
    
    # Executa a aplicação na porta 8000 escutando em todas as interfaces de rede
    serve(app, host="0.0.0.0", port=8000, threads=6)
