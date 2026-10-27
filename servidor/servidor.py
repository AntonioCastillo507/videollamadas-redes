"""Servidor de videollamadas - V1.

- TCP 5000: inicio de sesion, lista de usuarios y chat (senalizacion).
- UDP 5001: responde a la busqueda por broadcast de los clientes.
- SQLite: tablas usuarios y llamadas.
"""
import json
import socket
import sqlite3
import threading
from datetime import datetime

TCP_PORT = 5000
UDP_PORT = 5001
DB_ARCHIVO = "videollamadas.db"
CLAVE_BUSQUEDA = b"BUSCAR_SERVIDOR_VIDEO"

bd = sqlite3.connect(DB_ARCHIVO, check_same_thread=False)
bd_lock = threading.Lock()
conectados = {}  # nombre -> socket
conectados_lock = threading.Lock()


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def iniciar_bd():
    with bd_lock:
        bd.executescript(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_usuario TEXT UNIQUE NOT NULL,
                fecha_creacion TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS llamadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_origen_id INTEGER NOT NULL REFERENCES usuarios(id),
                usuario_destino_id INTEGER NOT NULL REFERENCES usuarios(id),
                inicio TEXT,
                fin TEXT,
                estado TEXT NOT NULL
            );
            """
        )
        bd.commit()


def registrar_usuario(nombre):
    with bd_lock:
        bd.execute(
            "INSERT OR IGNORE INTO usuarios (nombre_usuario, fecha_creacion) VALUES (?, ?)",
            (nombre, ahora()),
        )
        bd.commit()


def enviar(sock, mensaje):
    try:
        sock.sendall((json.dumps(mensaje) + "\n").encode("utf-8"))
    except OSError:
        pass


def difundir_usuarios():
    with conectados_lock:
        lista = sorted(conectados)
        destinos = list(conectados.values())
    for s in destinos:
        enviar(s, {"tipo": "usuarios", "lista": lista})


def atender_cliente(sock, addr):
    nombre = None
    try:
        with sock.makefile("r", encoding="utf-8") as entrada:
            for linea in entrada:
                msg = json.loads(linea)
                tipo = msg.get("tipo")

                if nombre is None:
                    usuario = str(msg.get("usuario", "")).strip()
                    if tipo != "login" or not usuario or usuario == "*":
                        enviar(sock, {"tipo": "error", "msg": "Usuario no valido"})
                        return
                    with conectados_lock:
                        if usuario in conectados:
                            enviar(sock, {"tipo": "error", "msg": "Ese usuario ya esta conectado"})
                            return
                        conectados[usuario] = sock
                    nombre = usuario
                    registrar_usuario(nombre)
                    print("[+] %s conectado desde %s" % (nombre, addr[0]))
                    enviar(sock, {"tipo": "ok"})
                    difundir_usuarios()

                elif tipo == "chat":
                    para = msg.get("para", "*")
                    paquete = {"tipo": "chat", "de": nombre, "para": para,
                               "texto": str(msg.get("texto", ""))}
                    with conectados_lock:
                        if para == "*":
                            destinos = list(conectados.values())
                        else:
                            destinos = [conectados[n] for n in (para, nombre) if n in conectados]
                    for s in destinos:
                        enviar(s, paquete)
    except (OSError, ValueError):
        pass
    finally:
        if nombre:
            with conectados_lock:
                conectados.pop(nombre, None)
            print("[-] %s desconectado" % nombre)
            difundir_usuarios()
        sock.close()


def responder_broadcast():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", UDP_PORT))
    while True:
        datos, origen = s.recvfrom(1024)
        if datos == CLAVE_BUSQUEDA:
            print("[?] Busqueda recibida de %s" % origen[0])
            s.sendto(b"SERVIDOR_VIDEO:%d" % TCP_PORT, origen)


def main():
    iniciar_bd()
    threading.Thread(target=responder_broadcast, daemon=True).start()
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(("", TCP_PORT))
    servidor.listen()
    print("Servidor listo: TCP %d, UDP %d (Ctrl+C para salir)" % (TCP_PORT, UDP_PORT))
    try:
        while True:
            sock, addr = servidor.accept()
            threading.Thread(target=atender_cliente, args=(sock, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nServidor detenido")


if __name__ == "__main__":
    main()
