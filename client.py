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

#----- Tampilan Pengguna interaktif (CLI) -------------------------------------------------------------
"Versi Inah : revisi 2024-06-05: menu interaktif, input matriks, mode otomatis kirim request acak tiap delay detik"

def read_matrix() -> list:
    """Baca 3 baris x 3 angka. Fraction() dipakai sebagai validator (menerima 2, 1.5, 3/2)."""
    rows = []
    for i in range(3):
        while True:
            parts = input(f"  Baris {i + 1} (3 angka dipisah spasi): ").split()   # versi mei: sebelumnya {r + 1} (r tidak didefinisikan)
            try:
                if len(parts) != 3:
                    raise ValueError
                row = [Fraction(p) for p in parts]
                break
            except (ValueError, ZeroDivisionError):
                print("  Input tidak valid, ulangi.")
        rows.append(row)
            # kirim int bila bulat, float bila pecahan (JSON tidak punya tipe Fraction)
    return [[int(x) if x.denominator == 1 else float(x) for x in row] for row in rows]

def run_main(client: Client): 
    status_no = len(P.SERVICES) + 1
    while True:
        print("\n=== Menu Klien ===")
        for n, svc in enumerate(P.SERVICES, 1):
            mark = "" if svc in client.active else " (NONAKTIF)"
            print(f"{n}. {LABELS[svc]}{mark}")
        print(f"{status_no}. Status server")
        print("0. Keluar")
        choice = input("Pilih: ").strip()
        if choice == "0":
            return
        if choice == str(status_no):
            client.status()
            continue
        if not choice.isdigit() or not (1 <= int(choice) <= len(P.SERVICES)):
            print("Pilihan tidak valid.")
            continue
        svc = P.SERVICES[int(choice) - 1]
        if svc not in client.active:
            print(f"Layanan ini sudah dinonaktifkan server.")
            continue
        payload = {"matrix": read_matrix()} if svc == P.MATRIX else {"text": input("Teks : ")}
        client.call(svc, payload)

def run_auto(client: Client, delay: float) :
    """Mode otomatis: kirim request acak tiap `delay` detik, sampai server shutdown."""
    samples = ["Hello World", "KOMB JAYA", "DIKE To The World",   # versi mei: koma ditambahkan (sebelumnya hilang)
               "Pecinta  Jamu", "MIPA Alim", "Kopi \u2615 enak", ""]

    n = 0
    while client.active:
        svc = random.choice(list(client.active))
        if svc == P.MATRIX:
            payload = {"matrix": [[random.randint(-3, 3) for _ in range(3)] for _ in range(3)]}
        else:
            payload = {"text": random.choice(samples)} 
        n += 1
        print(f"\n#{n} {LABELS[svc]}  payload={payload}")
        client.call(svc, payload)
        time.sleep(delay)


# Versi Mei: Menambahkan fungsi main()
def main() -> int:
    # main() mengembalikan kode keluar (exit code) program:
    #   0 = normal (keluar biasa / server shutdown), 1 = masalah jaringan, 2 = pelanggaran protokol
    # 1) Baca argumen dari command line
    ap = argparse.ArgumentParser(description="Klien protokol layanan string & matriks (NDJSON over TCP)")
    ap.add_argument("--host", default="127.0.0.1", help="alamat server (default: 127.0.0.1)")
    ap.add_argument("--port", type=int, default=P.DEFAULT_PORT, help="port server (default: dari protocol.py)")
    ap.add_argument("--timeout", type=float, default=10.0, help="timeout socket dalam detik (default: 10)")
    ap.add_argument("--auto", action="store_true", help="kirim permintaan acak otomatis")
    ap.add_argument("--delay", type=float, default=0.2, help="jeda antar permintaan mode auto (default: 0.2)")
    args = ap.parse_args()
 
    # 2) Validasi argumen; ap.error() mencetak pesan lalu keluar dengan kode 2
    if not (1 <= args.port <= 65535):
        ap.error("--port harus di antara 1 dan 65535")
    if args.delay < 0 or args.timeout <= 0:
        ap.error("--delay tidak boleh negatif dan --timeout harus > 0")
 
    # client diisi None dulu supaya blok `finally` aman dipakai walau koneksi gagal dibuat
    client = None
    try:
        # 3) Hubungkan ke server (di sini server_hello langsung dibaca oleh Client.__init__)
        client = Client(args.host, args.port, timeout=args.timeout)
        print(f"Terhubung ke {args.host}:{args.port}")
        # 4) Pilih mode: otomatis (request acak) atau menu interaktif
        if args.auto:
            run_auto(client, args.delay)
        else:
            run_main(client)
    # 5) Penanganan error; urutan except penting (yang lebih spesifik ditulis lebih dulu)
    except ServerShutdown as exc:         # server berhenti / semua layanan nonaktif -> bukan error, exit 0
        print(f"\n[SERVER BERHENTI] {exc}")
    except ConnectionClosed as exc:       # server menutup koneksi (EOF) di tengah jalan
        print(f"\n[KONEKSI TERPUTUS] {exc}")
        return 1
    except ProtocolError as exc:          # pesan server melanggar aturan protokol
        print(f"\n[PELANGGARAN PROTOKOL] {exc}")
        return 2
    except ConnectionRefusedError:        # port tertutup / server belum dijalankan
        print(f"\n[DITOLAK] Tidak ada server di {args.host}:{args.port}. Pastikan server sudah jalan.")
        return 1
    except TimeoutError:                  # HARUS sebelum OSError (TimeoutError adalah subclass-nya)
        print("\n[TIMEOUT] Server tidak merespons.")
        return 1
    except (KeyboardInterrupt, EOFError): # Ctrl+C, atau Ctrl+D saat input() di menu
        print("\nKeluar.")
    except OSError as exc:                # sisa kesalahan jaringan lain (mis. koneksi direset)
        print(f"\n[KESALAHAN JARINGAN] {exc}")
        return 1
    finally:
        # 6) Selalu tutup socket, apa pun yang terjadi di atas (hanya jika koneksi sempat terbentuk)
        if client:
            client.close()
            print("Koneksi ditutup.")
    return 0
 
 
# SystemExit meneruskan return value main() sebagai exit code proses
if __name__ == "__main__":
    raise SystemExit(main())