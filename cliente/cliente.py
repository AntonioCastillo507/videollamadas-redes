"""Cliente de videollamadas - V1: conexion al servidor, lista de usuarios y chat."""
import json
import socket
import sys
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPushButton, QTextEdit, QVBoxLayout,
                               QWidget)

PUERTO_TCP = 5000
PUERTO_UDP = 5001
CLAVE_BUSQUEDA = b"BUSCAR_SERVIDOR_VIDEO"
TODOS = "* Todos"


def buscar_servidor(espera=2.0):
    """Envia un broadcast UDP y devuelve (ip, puerto) del primer servidor que responda."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(espera)
    for destino in ("255.255.255.255", "192.168.56.255"):
        try:
            s.sendto(CLAVE_BUSQUEDA, (destino, PUERTO_UDP))
        except OSError:
            pass
    try:
        datos, origen = s.recvfrom(1024)
    except socket.timeout:
        return None
    finally:
        s.close()
    if datos.startswith(b"SERVIDOR_VIDEO:"):
        return origen[0], int(datos.split(b":")[1])
    return None


class Conexion(QObject):
    recibido = Signal(dict)
    cerrada = Signal()

    def __init__(self):
        super().__init__()
        self.sock = None

    def conectar(self, host, puerto, usuario):
        self.sock = socket.create_connection((host, puerto), timeout=5)
        self.sock.settimeout(None)
        self.enviar({"tipo": "login", "usuario": usuario})
        threading.Thread(target=self._leer, args=(self.sock,), daemon=True).start()

    def enviar(self, mensaje):
        self.sock.sendall((json.dumps(mensaje) + "\n").encode("utf-8"))

    def _leer(self, sock):
        try:
            with sock.makefile("r", encoding="utf-8") as entrada:
                for linea in entrada:
                    self.recibido.emit(json.loads(linea))
        except (OSError, ValueError):
            pass
        self.cerrada.emit()

    def cerrar(self):
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()
            self.sock = None


class Ventana(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Videollamadas - V1")
        self.resize(640, 480)
        self.red = Conexion()
        self.red.recibido.connect(self.al_recibir)
        self.red.cerrada.connect(self.al_cerrarse)

        self.host = QLineEdit("192.168.56.20")
        self.usuario = QLineEdit()
        self.usuario.setPlaceholderText("Tu nombre de usuario")
        self.btn_buscar = QPushButton("Buscar (broadcast)")
        self.btn_conectar = QPushButton("Conectar")
        self.estado = QLabel("Desconectado")
        self.usuarios = QListWidget()
        self.usuarios.setMaximumWidth(160)
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.texto = QLineEdit()
        self.texto.setEnabled(False)
        self.btn_enviar = QPushButton("Enviar")
        self.btn_enviar.setEnabled(False)

        arriba = QHBoxLayout()
        for w in (QLabel("Servidor:"), self.host, self.btn_buscar,
                  self.usuario, self.btn_conectar):
            arriba.addWidget(w)
        centro = QHBoxLayout()
        centro.addWidget(self.chat)
        centro.addWidget(self.usuarios)
        abajo = QHBoxLayout()
        abajo.addWidget(self.texto)
        abajo.addWidget(self.btn_enviar)
        capa = QVBoxLayout(self)
        capa.addLayout(arriba)
        capa.addLayout(centro)
        capa.addLayout(abajo)
        capa.addWidget(self.estado)

        self.btn_buscar.clicked.connect(self.buscar)
        self.btn_conectar.clicked.connect(self.alternar_conexion)
        self.btn_enviar.clicked.connect(self.enviar_chat)
        self.texto.returnPressed.connect(self.enviar_chat)

    def buscar(self):
        self.estado.setText("Buscando servidor por broadcast...")
        QApplication.processEvents()
        encontrado = buscar_servidor()
        if encontrado:
            self.host.setText(encontrado[0])
            self.estado.setText("Servidor encontrado en %s" % encontrado[0])
        else:
            self.estado.setText("No hubo respuesta. Escribe la IP a mano.")

    def alternar_conexion(self):
        if self.red.sock:
            self.red.cerrar()
            return
        nombre = self.usuario.text().strip()
        if not nombre:
            self.estado.setText("Escribe un nombre de usuario")
            return
        try:
            self.red.conectar(self.host.text().strip(), PUERTO_TCP, nombre)
        except OSError as e:
            self.estado.setText("No se pudo conectar: %s" % e)
            return
        self.estado.setText("Conectando...")

    def al_recibir(self, msg):
        tipo = msg.get("tipo")
        if tipo == "ok":
            self.estado.setText("Conectado como %s" % self.usuario.text().strip())
            self.btn_conectar.setText("Desconectar")
            self.texto.setEnabled(True)
            self.btn_enviar.setEnabled(True)
        elif tipo == "error":
            self.estado.setText("Error: %s" % msg.get("msg"))
            self.red.cerrar()
        elif tipo == "usuarios":
            self.usuarios.clear()
            self.usuarios.addItem(TODOS)
            self.usuarios.addItems(msg["lista"])
            self.usuarios.setCurrentRow(0)
        elif tipo == "chat":
            privado = " (privado)" if msg["para"] != "*" else ""
            self.chat.append("<b>%s</b>%s: %s" % (msg["de"], privado, msg["texto"]))

    def al_cerrarse(self):
        self.red.sock = None
        self.btn_conectar.setText("Conectar")
        self.texto.setEnabled(False)
        self.btn_enviar.setEnabled(False)
        self.usuarios.clear()
        if not self.estado.text().startswith("Error"):
            self.estado.setText("Desconectado")

    def enviar_chat(self):
        texto = self.texto.text().strip()
        if not texto or not self.red.sock:
            return
        item = self.usuarios.currentItem()
        para = "*" if item is None or item.text() == TODOS else item.text()
        self.red.enviar({"tipo": "chat", "para": para, "texto": texto})
        self.texto.clear()

    def closeEvent(self, evento):
        self.red.cerrar()
        evento.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ventana = Ventana()
    ventana.show()
    sys.exit(app.exec())
