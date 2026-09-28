import argparse
import json
import random
import socket
import time
from fractions import Fraction

import protocol as P
import verifier as V

LABELS = {
    P.CHAR_COUNT: "Jumlah karakter",
    P.WORD_COUNT: "Jumlah kata",
    P.REVERSE: "Balik string",
    P.REMOVE_VOWELS: "Hapus huruf vokal",
    P.MATRIX: "Determinan & invers matriks 3x3",
}


class ConnectionClosed(Exception):
    """Server menutup koneksi (EOF)."""


class ServerShutdown(Exception):
    """Server mengirim server_shutdown atau semua layanan nonaktif."""


class ProtocolError(Exception):
    """Pesan dari server melanggar aturan protokol."""


class MessageTooLarge(Exception):
    """Pesan yang akan dikirim melebihi 64 KiB."""


class Client:
    def __init__(self, host: str, port: int, timeout: float = 10.0):
        # create_connection: resolve nama host + TCP handshake
        self.sock = socket.create_connection((host, port), timeout=timeout)
        # makefile("r") membungkus socket agar bisa readline(): satu panggilan = satu
        # pesan utuh (framing per baris), berapa pun TCP memecah/menggabung paket
        self.rfile = self.sock.makefile("r", encoding=P.ENCODING, newline="\n")
        self.next_id = 1                  # penghitung untuk membentuk request_id unik
        self.active = set()               # layanan aktif (diisi dari server_hello)
        self.disabled = set()
        try:
            self._read_hello()            # server langsung mengirim server_hello
        except Exception:
            self.close()
            raise

    def close(self):
        try:
            self.rfile.close()
        finally:
            self.sock.close()

    # I/O tingkat rendah
    def _send(self, msg: dict):
        data = P.encode(msg)
        if len(data) > P.MAX_MESSAGE_BYTES:
            raise MessageTooLarge(f"{len(data)} byte > {P.MAX_MESSAGE_BYTES} byte")
        self.sock.sendall(data)           # sendall: pastikan SEMUA byte terkirim

    def _recv(self) -> dict:
        line = self.rfile.readline()
        if not line:                      # string kosong = EOF, server menutup koneksi
            raise ConnectionClosed("Server menutup koneksi.")
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"Pesan bukan JSON valid: {exc}") from exc
        if not isinstance(msg, dict) or "type" not in msg:
            raise ProtocolError(f"Pesan tanpa field 'type': {msg!r}")
        if msg["type"] == P.SERVER_SHUTDOWN:   # bisa datang kapan saja -> tangani di satu tempat
            raise ServerShutdown(msg.get("message") or msg.get("reason", ""))
        return msg

    def _update_services(self, msg: dict):
        known = set(P.SERVICES)
        self.active = set(msg.get("active_services", [])) & known
        self.disabled = set(msg.get("disabled_services", [])) & known

    def _read_hello(self):
        hello = self._recv()
        if hello["type"] != P.SERVER_HELLO:
            raise ProtocolError(f"Diharapkan server_hello, diterima: {hello!r}")
        self._update_services(hello)
        print(f"Server: {hello.get('protocol')} v{hello.get('version')} | "
              f"error_injection={hello.get('error_injection_enabled')}")
        print(f"Layanan aktif: {sorted(self.active)}")

    # Satu transaksi lengkap
    def call(self, service: str, payload: dict):
        req_id = f"req-{self.next_id:03d}"
        self.next_id += 1

        # 1) kirim request
        try:
            self._send({"type": P.REQUEST, "request_id": req_id,
                        "service": service, "payload": payload})
        except MessageTooLarge as exc:
            print(f"  [DITOLAK KLIEN] Pesan terlalu besar ({exc}).")
            return

        # 2) terima response/error
        msg = self._recv()
        if msg["type"] == P.ERROR:
            print(f"  [ERROR server] {msg.get('code')}: {msg.get('message', '')}")
            return                        # error tidak menonaktifkan layanan & tidak perlu ACK
        if msg["type"] != P.RESPONSE or msg.get("request_id") != req_id:
            raise ProtocolError(f"Respons tidak terduga: {msg!r}")

        status = msg.get("status")
        if status == P.STATUS_SERVICE_DISABLED:   # layanan dinonaktifkan, jadi proses dihentikan tanpa ACK
            self._update_services(msg)
            print(f"  [INFO] Layanan {service} sudah dinonaktifkan server.")
            print(f"  Layanan aktif: {sorted(self.active) or '-'}")
            return
        if status != P.STATUS_OK:
            raise ProtocolError(f"Status response tidak dikenal: {status!r}")

        # 3) periksa hasil dengan implementasi referensi klien (dari input asli)
        result = msg.get("result")
        ok, reason = V.verify(service, payload, result)
        shown = repr(result)
        print(f"  Hasil server : {shown if len(shown) <= 200 else shown[:200] + '...'}")
        print(f"  Pemeriksaan  : {'BENAR' if ok else 'SALAH (' + reason + ')'}")

        # 4) kirim ack sebelum request berikutnya
        self._send({"type": P.ACK, "request_id": req_id, "correct": ok})

        # 5) terima hasil ACK lalu perbarui daftar layanan
        reply = self._recv()
        if reply["type"] != P.ACK_RESULT or reply.get("request_id") != req_id:
            raise ProtocolError(f"Diharapkan ack_result, diterima: {reply!r}")
        self._update_services(reply)
        if reply.get("action") == P.ACTION_SERVICE_DISABLED:
            print(f"  [INFO] Server menonaktifkan layanan {service}.")
        print(f"  Layanan aktif: {sorted(self.active) or '-'}")

        # 6) jika layanan terakhir mati, maka server mengirim server_shutdown lalu berhenti
        if not self.active:
            try:
                self._recv()              # menunggu server shutdown/koneksi ditutup
            except (ServerShutdown, ConnectionClosed):
                pass
            raise ServerShutdown("Semua layanan server nonaktif.")

    def status(self):
        # Minta status server (hanya boleh saat tidak ada ACK yang tertunda).
        self._send({"type": P.STATUS_REQUEST})
        msg = self._recv()
        if msg["type"] != P.SERVER_STATUS:
            raise ProtocolError(f"Diharapkan server_status, diterima: {msg!r}")
        self._update_services(msg)
        print(f"  Aktif   : {sorted(self.active) or '-'}")
        print(f"  Nonaktif: {sorted(self.disabled) or '-'}")
