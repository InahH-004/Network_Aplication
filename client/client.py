#----- Tampilan Pengguna interaktif (CLI) -------------------------------------------------------------
"Versi Inah : revisi 2026-09-29 v3: menu interaktif, input matriks, mode otomatis kirim request acak tiap delay detik"

def read_matrix() -> list:
    """Baca 3 baris x 3 angka. Fraction() dipakai sebagai validator (menerima 2, 1.5, 3/2)."""
    rows = []
    for i in range(3):
        while True:
            parts = input(f"  Baris {r + 1} (3 angka dipisah spasi): ").split()
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

def run_outo(client: Client, delay: float) :
    """Mode otomatis: kirim request acak tiap `delay` detik, sampai server shutdown."""
    samples = ["Hello World", "KOMB JAYA", "DIKE To The World"
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