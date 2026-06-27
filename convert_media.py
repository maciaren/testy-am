"""Konwertuje pliki .wmv z media/ do .mp4 (H.264) w media_web/, do odtwarzania w przeglądarce.
Idempotentny: pomija pliki, które już istnieją po stronie wyjściowej.
Wymaga ffmpeg dostępnego w PATH (na Windows: winget install ffmpeg lub pobierz z ffmpeg.org).
"""
import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
MEDIA_WEB_DIR = os.path.join(BASE_DIR, "media_web")


def main():
    if shutil.which("ffmpeg") is None:
        print("BŁĄD: ffmpeg nie jest zainstalowany lub nie jest w PATH.")
        print("Zainstaluj ffmpeg (Windows: winget install ffmpeg, Linux: sudo apt-get install ffmpeg)"
              " i uruchom ten skrypt ponownie.")
        sys.exit(1)

    os.makedirs(MEDIA_WEB_DIR, exist_ok=True)

    wmv_pliki = [f for f in os.listdir(MEDIA_DIR) if f.lower().endswith(".wmv")]
    print(f"Znaleziono {len(wmv_pliki)} plików .wmv.")

    przekonwertowano = 0
    pominieto = 0
    bledy = 0

    for i, nazwa in enumerate(wmv_pliki, 1):
        nazwa_mp4 = os.path.splitext(nazwa)[0] + ".mp4"
        sciezka_in = os.path.join(MEDIA_DIR, nazwa)
        sciezka_out = os.path.join(MEDIA_WEB_DIR, nazwa_mp4)

        if os.path.exists(sciezka_out):
            pominieto += 1
            continue

        print(f"[{i}/{len(wmv_pliki)}] Konwertuję: {nazwa}")
        wynik = subprocess.run(
            [
                "ffmpeg", "-y", "-i", sciezka_in,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-movflags", "+faststart",
                sciezka_out,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if wynik.returncode != 0:
            bledy += 1
            print(f"  BŁĄD konwersji {nazwa}: {wynik.stderr.decode(errors='ignore')[-300:]}")
        else:
            przekonwertowano += 1

    print(f"\nGotowe. Przekonwertowano: {przekonwertowano}, pominięto (już istniały): {pominieto}, błędy: {bledy}.")


if __name__ == "__main__":
    main()
