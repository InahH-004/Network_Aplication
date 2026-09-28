"""
verifier.py untuk memeriksa jawaban dari server

Client tidak langsung percaya pada hasil dari server.
Client akan menghitung sendiri hasil yang seharusnya,
lalu membandingkannya dengan hasil yang dikirim oleh server.

File ini hanya berisi fungsi untuk memeriksa hasil.
Tidak ada kode jaringan atau socket di dalamnya.

Jenis hasil yang diperiksa:
- char_count    : jumlah karakter
- word_count    : jumlah kata
- reverse       : membalik teks
- remove_vowels : menghapus huruf vokal
- matrix_3x3    : menghitung determinan dan invers matriks 3x3

Bentuk result menurut PROTOCOL.md dari server:
    char_count / word_count : bilangan bulat
    reverse / remove_vowels : string
    matrix_3x3              : {"determinant": x, "inverse": [[..]]|null, "invertible": bool}
"""

import math
from fractions import Fraction

import protocol as P

VOWELS = set("aeiouAEIOU")   # a i u e o, tidak membedakan huruf besar/kecil
REL_TOL = 1e-9               # toleransi relatif (menyerap galat float pada nilai besar)
ABS_TOL = 1e-9               # toleransi absolut (rekomendasi PROTOCOL.md; penting di dekat 0)


# Layanan string
def char_count(text: str) -> int:
    return len(text)                      # O(1); jumlah code point Unicode, spasi ikut dihitung


def word_count(text: str) -> int:
    return len(text.split())              # split() tanpa argumen: pisah pada whitespace berurutan


def reverse(text: str) -> str:
    return text[::-1]                     # slicing dengan langkah -1


def remove_vowels(text: str) -> str:
    return "".join(ch for ch in text if ch not in VOWELS)   # set -> pencarian O(1)


# Layanan matriks 3x3
def determinant(m):
    """Ekspansi kofaktor sepanjang baris pertama (setara aturan Sarrus untuk 3x3)."""
    (a, b, c), (d, e, f), (g, h, i) = m
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def inverse(m, det):
    """Invers = adjugate / determinan. Mengembalikan None jika matriks singular."""
    if det == 0:
        return None
    (a, b, c), (d, e, f), (g, h, i) = m
    # Matriks kofaktor: C[r][k] = (-1)^(r+k) * minor(r, k)
    cof = [
        [e * i - f * h, -(d * i - f * g), d * h - e * g],
        [-(b * i - c * h), a * i - c * g, -(a * h - b * g)],
        [b * f - c * e, -(a * f - c * d), a * e - b * d],
    ]
    # Adjugate = transpose dari matriks kofaktor, lalu dibagi determinan
    return [[cof[k][r] / det for k in range(3)] for r in range(3)]


def _matrix_result(raw):
    # Fraction(str(x)) : "0.1" menjadi tepat 1/10, jadi hitungan referensi bebas galat float
    m = [[Fraction(str(x)) for x in row] for row in raw]
    det = determinant(m)
    inv = inverse(m, det)
    return {
        "determinant": float(det),
        "inverse": None if inv is None else [[float(x) for x in row] for row in inv],
        "invertible": inv is not None,
    }


# Hasil yang seharusnya
def expected_result(service: str, payload: dict):
    """Nilai `result` yang benar, dalam bentuk yang sama dengan yang dikirim server."""
    if service == P.CHAR_COUNT:
        return char_count(payload["text"])
    if service == P.WORD_COUNT:
        return word_count(payload["text"])
    if service == P.REVERSE:
        return reverse(payload["text"])
    if service == P.REMOVE_VOWELS:
        return remove_vowels(payload["text"])
    if service == P.MATRIX:
        return _matrix_result(payload["matrix"])
    raise ValueError(f"Layanan tidak dikenal: {service}")


def _close(x, y) -> bool:
    return (
        isinstance(x, (int, float)) and not isinstance(x, bool)
        and math.isclose(x, y, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    )


def _verify_matrix(exp: dict, got: dict):
    if not _close(got["determinant"], exp["determinant"]):
        return False, f"determinan seharusnya {exp['determinant']}, server: {got['determinant']!r}"
    if got["invertible"] is not exp["invertible"]:      # `is` -> harus benar-benar boolean
        return False, f"invertible seharusnya {exp['invertible']}, server: {got['invertible']!r}"
    if exp["inverse"] is None:                          # matriks singular
        ok = got["inverse"] is None
        return ok, "" if ok else "matriks singular, invers seharusnya null"
    inv = got["inverse"]
    if not (isinstance(inv, list) and len(inv) == 3
            and all(isinstance(row, list) and len(row) == 3 for row in inv)):
        return False, "invers harus matriks 3x3"
    ok = all(_close(inv[r][k], exp["inverse"][r][k]) for r in range(3) for k in range(3))
    return ok, "" if ok else "elemen invers tidak cocok"


def verify(service: str, payload: dict, got):
    """Bandingkan `result` server (`got`) dengan hasil seharusnya.
    Mengembalikan (benar: bool, alasan: str)."""
    try:
        exp = expected_result(service, payload)
        if service in (P.CHAR_COUNT, P.WORD_COUNT):
            ok = type(got) is int and got == exp        # type(...) is int: tolak bool & float
            return ok, "" if ok else f"seharusnya {exp}, server: {got!r}"
        if service in (P.REVERSE, P.REMOVE_VOWELS):
            ok = isinstance(got, str) and got == exp
            return ok, "" if ok else f"seharusnya {exp!r}, server: {got!r}"
        return _verify_matrix(exp, got)
    except (KeyError, TypeError, IndexError, ValueError):
        # Skema hasil rusak (field hilang / tipe salah) juga dianggap SALAH
        return False, "format hasil dari server tidak sesuai protokol"