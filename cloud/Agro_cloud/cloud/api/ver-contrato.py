#uso: python ver-contrato.py   (abre el contrato en swagger ui, local)
import http.server
import os
import socketserver
import threading
import webbrowser

carpeta = os.path.dirname(os.path.abspath(__file__))
os.chdir(carpeta)
puerto = 8088
socketserver.TCPServer.allow_reuse_address = True


class Manejador(http.server.SimpleHTTPRequestHandler):
    def log_message(self, formato, *args):
        pass


with socketserver.TCPServer(("127.0.0.1", puerto), Manejador) as srv:
    url = "http://127.0.0.1:%d/portal/" % puerto
    print("contrato en " + url + "  (ctrl+c para salir)")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("cerrado")
