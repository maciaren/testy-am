import json
import math
import os
import random
import tempfile
import uuid
from datetime import datetime, date

from flask import Flask, jsonify, request, render_template, send_file, abort

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTANIA_PATH = os.path.join(BASE_DIR, "pytania_AM.json")
STAN_PATH = os.path.join(BASE_DIR, "stan.json")
MEDIA_DIR = os.path.join(BASE_DIR, "media")
MEDIA_WEB_DIR = os.path.join(BASE_DIR, "media_web")

CZAS_LIMIT_S = 25 * 60
PROG_WSP = 68 / 74  # współczynnik progu zdania, zgodny z egzaminem 68/74

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Dane pytań (statyczne, wczytywane raz)
# ---------------------------------------------------------------------------

with open(PYTANIA_PATH, "r", encoding="utf-8") as f:
    _dane = json.load(f)

PYTANIA = {q["id"]: q for q in _dane["pytania"]}
WSZYSTKIE_PODSTAWOWE_IDS = [q["id"] for q in _dane["pytania"] if q["zakres"] == "podstawowy"]
WSZYSTKIE_SPECJALISTYCZNE_IDS = [q["id"] for q in _dane["pytania"] if q["zakres"] == "specjalistyczny"]
LICZBA_PYTAN_LACZNIE = len(PYTANIA)


def pytanie_publiczne(q):
    """Wersja pytania bez poprawnej odpowiedzi, do wysłania klientowi w trakcie testu."""
    dane = {
        "id": q["id"],
        "pytanie": q["pytanie"],
        "typ": q["typ"],
        "zakres": q["zakres"],
        "punkty": q["punkty"],
        "media": q["media"],
        "media_typ": q["media_typ"],
    }
    if q["typ"] == "abc":
        dane["odpowiedzi"] = q["odpowiedzi"]
    return dane


# ---------------------------------------------------------------------------
# Stan na dysku
# ---------------------------------------------------------------------------

def stan_domyslny():
    return {
        "wersja": 1,
        "utworzono": datetime.now().isoformat(),
        "pula_wejsciowa": {
            "podstawowe": list(WSZYSTKIE_PODSTAWOWE_IDS),
            "specjalistyczne": list(WSZYSTKIE_SPECJALISTYCZNE_IDS),
        },
        "bledne_odpowiedzi": [],
        "niezdane_testy": [],
        "historia_testow": [],
        "statystyki_pytan": {},
        "test_w_toku": None,
    }


def wczytaj_stan():
    if not os.path.exists(STAN_PATH):
        stan = stan_domyslny()
        zapisz_stan(stan)
        return stan
    with open(STAN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def zapisz_stan(stan):
    dirpath = os.path.dirname(STAN_PATH) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dirpath, prefix=".stan_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(stan, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STAN_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


# ---------------------------------------------------------------------------
# Generowanie testów
# ---------------------------------------------------------------------------

def grupuj_wg_waga(ids):
    grupy = {1: [], 2: [], 3: []}
    for qid in ids:
        grupy[PYTANIA[qid]["punkty"]].append(qid)
    return grupy


def wybierz_wg_wagi(ids, cele):
    """Losuje pytania z `ids` próbując zachować rozkład punktowy `cele` (np. {3:10,2:6,1:4}).
    Gdy brakuje pytań o danej wadze, dobiera z najbliższej dostępnej."""
    grupy = grupuj_wg_waga(ids)
    for g in grupy.values():
        random.shuffle(g)
    wybrane = []
    deficyt = 0
    for w in (3, 2, 1):
        potrzeba = cele.get(w, 0)
        dostepne = grupy[w]
        bierz = min(potrzeba, len(dostepne))
        wybrane.extend(dostepne[:bierz])
        del dostepne[:bierz]
        deficyt += potrzeba - bierz
    if deficyt > 0:
        reszta = grupy[3] + grupy[2] + grupy[1]
        random.shuffle(reszta)
        wybrane.extend(reszta[:deficyt])
    return wybrane


def generuj_test_normalny(stan):
    podst_pool = stan["pula_wejsciowa"]["podstawowe"]
    spec_pool = stan["pula_wejsciowa"]["specjalistyczne"]

    if len(podst_pool) <= 20:
        wybrane_podst = list(podst_pool)
    else:
        wybrane_podst = wybierz_wg_wagi(podst_pool, {3: 10, 2: 6, 1: 4})

    if len(spec_pool) == 0:
        wybrane_spec = []
    elif len(spec_pool) <= 12:
        wybrane_spec = list(spec_pool)
    else:
        wybrane_spec = wybierz_wg_wagi(spec_pool, {3: 6, 2: 4, 1: 2})

    for qid in wybrane_podst:
        podst_pool.remove(qid)
    for qid in wybrane_spec:
        spec_pool.remove(qid)

    pytania_ids = wybrane_podst + wybrane_spec
    random.shuffle(pytania_ids)
    return pytania_ids


def generuj_test_bledne(stan):
    pool = stan["bledne_odpowiedzi"]
    n = min(32, len(pool))
    return random.sample(pool, n)


def maks_punktow(ids):
    return sum(PYTANIA[qid]["punkty"] for qid in ids)


def prog_zdania(max_pkt):
    return math.ceil(PROG_WSP * max_pkt)


# ---------------------------------------------------------------------------
# Statystyki pytań
# ---------------------------------------------------------------------------

def aktualizuj_statystyke(stan, qid, ok):
    klucz = str(qid)
    s = stan["statystyki_pytan"].setdefault(klucz, {"razy_pokazane": 0, "razy_poprawnie": 0})
    s["razy_pokazane"] += 1
    if ok:
        s["razy_poprawnie"] += 1


def zarejestruj_odpowiedz(stan, qid, ok, test_w_toku):
    """Aktualizuje bledne_odpowiedzi zgodnie z regułami 4.3. Zapisuje też ślad
    zmian w test_w_toku, żeby można je było wycofać przy przerwaniu testu."""
    tryb = test_w_toku["tryb"]
    if not ok:
        if qid not in stan["bledne_odpowiedzi"]:
            stan["bledne_odpowiedzi"].append(qid)
            test_w_toku["bledne_dodane"].append(qid)
    else:
        if tryb == "bledne" and qid in stan["bledne_odpowiedzi"]:
            stan["bledne_odpowiedzi"].remove(qid)
            test_w_toku["bledne_usuniete"].append(qid)
    aktualizuj_statystyke(stan, qid, ok)


def przerwij_test(stan, test_w_toku):
    """Wycofuje wszystkie zmiany dokonane w trakcie testu i kasuje go bez zapisu do historii."""
    for o in test_w_toku["odpowiedzi"]:
        klucz = str(o["id"])
        s = stan["statystyki_pytan"].get(klucz)
        if s:
            s["razy_pokazane"] -= 1
            if o["ok"]:
                s["razy_poprawnie"] -= 1
            if s["razy_pokazane"] <= 0:
                del stan["statystyki_pytan"][klucz]

    for qid in test_w_toku["bledne_dodane"]:
        if qid in stan["bledne_odpowiedzi"]:
            stan["bledne_odpowiedzi"].remove(qid)
    for qid in test_w_toku["bledne_usuniete"]:
        if qid not in stan["bledne_odpowiedzi"]:
            stan["bledne_odpowiedzi"].append(qid)

    if test_w_toku["tryb"] == "normalny":
        for qid in test_w_toku["pytania_ids"]:
            podpula = "podstawowe" if PYTANIA[qid]["zakres"] == "podstawowy" else "specjalistyczne"
            stan["pula_wejsciowa"][podpula].append(qid)

    stan["test_w_toku"] = None


# ---------------------------------------------------------------------------
# Routes - widoki
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/media/<path:nazwa>")
def media(nazwa):
    nazwa = os.path.basename(nazwa)
    if nazwa.lower().endswith(".wmv"):
        mp4_nazwa = os.path.splitext(nazwa)[0] + ".mp4"
        mp4_path = os.path.join(MEDIA_WEB_DIR, mp4_nazwa)
        if os.path.exists(mp4_path):
            return send_file(mp4_path)
    sciezka = os.path.join(MEDIA_DIR, nazwa)
    if os.path.exists(sciezka):
        return send_file(sciezka)
    abort(404)


# ---------------------------------------------------------------------------
# Routes - API stanu / dashboard
# ---------------------------------------------------------------------------

@app.route("/api/dashboard")
def api_dashboard():
    stan = wczytaj_stan()
    return jsonify(oblicz_dashboard(stan))


def oblicz_dashboard(stan):
    podst_zostalo = len(stan["pula_wejsciowa"]["podstawowe"])
    spec_zostalo = len(stan["pula_wejsciowa"]["specjalistyczne"])
    zrobione = LICZBA_PYTAN_LACZNIE - podst_zostalo - spec_zostalo

    historia = stan["historia_testow"]
    odpowiedzi_wszystkie = [o for t in historia for o in t["odpowiedzi"]]
    n_odp = len(odpowiedzi_wszystkie)
    n_odp_ok = sum(1 for o in odpowiedzi_wszystkie if o["ok"])

    odp_podst = [o for o in odpowiedzi_wszystkie if PYTANIA[o["id"]]["zakres"] == "podstawowy"]
    odp_spec = [o for o in odpowiedzi_wszystkie if PYTANIA[o["id"]]["zakres"] == "specjalistyczny"]

    def proc(ok_list):
        if not ok_list:
            return None
        return round(100 * sum(1 for o in ok_list if o["ok"]) / len(ok_list), 1)

    testy_normalne = [t for t in historia if t["typ"] == "normalny"]
    n_testy_normalne = len(testy_normalne)
    n_testy_zdane = sum(1 for t in testy_normalne if t["zdany"])

    testy_pozostale = math.ceil(podst_zostalo / 20) if podst_zostalo > 0 else 0
    pozostalo_testow = testy_pozostale + len(stan["niezdane_testy"])

    prognoza = oblicz_prognoze(testy_normalne, n_testy_zdane, pozostalo_testow)

    ukonczone = (
        podst_zostalo == 0
        and spec_zostalo == 0
        and len(stan["niezdane_testy"]) == 0
        and len(stan["bledne_odpowiedzi"]) == 0
    )

    return {
        "postep_pytan": {
            "zrobione": zrobione,
            "wszystkie": LICZBA_PYTAN_LACZNIE,
            "procent": round(100 * zrobione / LICZBA_PYTAN_LACZNIE, 1),
            "podstawowe_zostalo": podst_zostalo,
            "specjalistyczne_zostalo": spec_zostalo,
        },
        "skutecznosc": {
            "procent_lacznie": proc(odpowiedzi_wszystkie),
            "procent_podstawowe": proc(odp_podst),
            "procent_specjalistyczne": proc(odp_spec),
            "liczba_odpowiedzi": n_odp,
        },
        "testy": {
            "zrobione": n_testy_normalne,
            "procent_zdanych": round(100 * n_testy_zdane / n_testy_normalne, 1) if n_testy_normalne else None,
            "zostalo_do_konca": testy_pozostale,
        },
        "pule_naprawcze": {
            "bledne_odpowiedzi": len(stan["bledne_odpowiedzi"]),
            "niezdane_testy": len(stan["niezdane_testy"]),
        },
        "prognoza": prognoza,
        "ukonczone": ukonczone,
        "pozostalo_testow_total": pozostalo_testow,
    }


def oblicz_prognoze(testy_normalne, n_testy_zdane, pozostalo_testow):
    if not testy_normalne:
        return {"status": "brak_danych", "tempo_dziennie": None, "data_zakonczenia": None}

    daty = sorted(set(datetime.fromisoformat(t["data"]).date() for t in testy_normalne))
    pierwszy = daty[0]
    dzis = date.today()
    dni_aktywne = (dzis - pierwszy).days + 1
    if len(daty) < 2 and dni_aktywne < 2:
        return {"status": "brak_danych", "tempo_dziennie": None, "data_zakonczenia": None}

    tempo = n_testy_zdane / max(dni_aktywne, 1)
    if tempo <= 0:
        return {"status": "brak_tempa", "tempo_dziennie": 0, "data_zakonczenia": None}

    dni_potrzebne = math.ceil(pozostalo_testow / tempo) if pozostalo_testow > 0 else 0
    from datetime import timedelta

    data_konca = dzis + timedelta(days=dni_potrzebne)
    return {
        "status": "ok",
        "tempo_dziennie": round(tempo, 3),
        "data_zakonczenia": data_konca.isoformat(),
    }


@app.route("/api/kalkulator_tempa")
def api_kalkulator_tempa():
    data_str = request.args.get("data")
    if not data_str:
        return jsonify({"error": "brak parametru data"}), 400
    try:
        cel = date.fromisoformat(data_str)
    except ValueError:
        return jsonify({"error": "niepoprawny format daty"}), 400

    stan = wczytaj_stan()
    dash = oblicz_dashboard(stan)
    pozostalo = dash["pozostalo_testow_total"]
    dzis = date.today()
    dni_do_daty = (cel - dzis).days

    if dni_do_daty <= 0:
        return jsonify({"error": "data w przeszłości lub dzisiejsza"}), 200

    testy_dziennie = math.ceil(pozostalo / dni_do_daty) if pozostalo > 0 else 0
    return jsonify({"testy_dziennie": testy_dziennie, "pozostalo_testow": pozostalo, "dni_do_daty": dni_do_daty})


# ---------------------------------------------------------------------------
# Routes - API testów
# ---------------------------------------------------------------------------

@app.route("/api/niezdane")
def api_niezdane():
    stan = wczytaj_stan()
    wynik = []
    for t in stan["niezdane_testy"]:
        max_pkt = maks_punktow(t["pytania"])
        wynik.append({
            "test_id": t["test_id"],
            "liczba_pytan": len(t["pytania"]),
            "max_punkty": max_pkt,
            "prog": prog_zdania(max_pkt),
            "utworzono": t["utworzono"],
            "ostatnia_proba": t["ostatnia_proba"],
            "ostatni_wynik": t["ostatni_wynik"],
        })
    return jsonify(wynik)


@app.route("/api/test/start", methods=["POST"])
def api_test_start():
    body = request.get_json(force=True) or {}
    tryb = body.get("tryb")
    stan = wczytaj_stan()

    if stan.get("test_w_toku"):
        return jsonify({"error": "test już w toku"}), 409

    if tryb == "normalny":
        if not stan["pula_wejsciowa"]["podstawowe"] and not stan["pula_wejsciowa"]["specjalistyczne"]:
            return jsonify({"error": "pula wejściowa jest pusta"}), 400
        ids = generuj_test_normalny(stan)
        powiazany_test_id = None
    elif tryb == "bledne":
        if not stan["bledne_odpowiedzi"]:
            return jsonify({"error": "brak błędnych odpowiedzi do powtórki"}), 400
        ids = generuj_test_bledne(stan)
        powiazany_test_id = None
    elif tryb == "powtorka":
        niezdany_id = body.get("test_id")
        rekord = next((t for t in stan["niezdane_testy"] if t["test_id"] == niezdany_id), None)
        if not rekord:
            return jsonify({"error": "nie znaleziono niezdanego testu"}), 404
        ids = list(rekord["pytania"])
        powiazany_test_id = niezdany_id
    else:
        return jsonify({"error": "nieznany tryb"}), 400

    if not ids:
        return jsonify({"error": "brak pytań dla wybranego trybu"}), 400

    test_w_toku = {
        "test_id": str(uuid.uuid4()),
        "tryb": tryb,
        "powiazany_niezdany_test_id": powiazany_test_id,
        "pytania_ids": ids,
        "odpowiedzi": [],
        "started_at": datetime.now().isoformat(),
        "bledne_dodane": [],
        "bledne_usuniete": [],
    }
    stan["test_w_toku"] = test_w_toku
    zapisz_stan(stan)

    return jsonify(test_stan_klienta(test_w_toku))


def test_stan_klienta(test_w_toku, dokonczony=False):
    idx = len(test_w_toku["odpowiedzi"])
    total = len(test_w_toku["pytania_ids"])
    tryb = test_w_toku["tryb"]

    if tryb == "bledne":
        # Tryb błędnych jest bez limitu czasu - to ćwiczenie naprawcze, nie egzamin.
        pozostalo_s = None
    else:
        started = datetime.fromisoformat(test_w_toku["started_at"])
        uplynelo = (datetime.now() - started).total_seconds()
        pozostalo_s = max(0, CZAS_LIMIT_S - uplynelo)

    dane = {
        "test_id": test_w_toku["test_id"],
        "tryb": tryb,
        "numer": idx + 1 if not dokonczony and idx < total else total,
        "wszystkie": total,
        "pozostalo_sekund": round(pozostalo_s) if pozostalo_s is not None else None,
        "zakonczony": dokonczony or idx >= total or (pozostalo_s is not None and pozostalo_s <= 0),
    }
    if not dane["zakonczony"]:
        qid = test_w_toku["pytania_ids"][idx]
        dane["pytanie"] = pytanie_publiczne(PYTANIA[qid])
    return dane


@app.route("/api/test/current")
def api_test_current():
    stan = wczytaj_stan()
    test_w_toku = stan.get("test_w_toku")
    if not test_w_toku:
        return jsonify(None)
    dane = test_stan_klienta(test_w_toku)
    if dane["zakonczony"] and len(test_w_toku["odpowiedzi"]) < len(test_w_toku["pytania_ids"]):
        wynik = finalizuj_test(stan, test_w_toku)
        zapisz_stan(stan)
        return jsonify(wynik)
    return jsonify(dane)


@app.route("/api/test/answer", methods=["POST"])
def api_test_answer():
    body = request.get_json(force=True) or {}
    odpowiedz = body.get("odpowiedz")
    stan = wczytaj_stan()
    test_w_toku = stan.get("test_w_toku")
    if not test_w_toku:
        return jsonify({"error": "brak testu w toku"}), 400

    idx = len(test_w_toku["odpowiedzi"])
    total = len(test_w_toku["pytania_ids"])
    if idx >= total:
        return jsonify({"error": "test już zakończony"}), 400

    tryb = test_w_toku["tryb"]

    if tryb != "bledne":
        started = datetime.fromisoformat(test_w_toku["started_at"])
        if (datetime.now() - started).total_seconds() > CZAS_LIMIT_S:
            wynik = finalizuj_test(stan, test_w_toku)
            zapisz_stan(stan)
            return jsonify(wynik)

    qid = test_w_toku["pytania_ids"][idx]
    poprawna = PYTANIA[qid]["poprawna"]
    ok = (odpowiedz == poprawna)

    test_w_toku["odpowiedzi"].append({"id": qid, "udzielona": odpowiedz, "poprawna": poprawna, "ok": ok})
    zarejestruj_odpowiedz(stan, qid, ok, test_w_toku)

    if tryb == "bledne":
        # Tryb naprawczy: natychmiastowa informacja zwrotna, bez punktacji i historii.
        # Poprawna odpowiedź trwale usuwa pytanie z puli błędnych (już zrobione w zarejestruj_odpowiedz).
        odpowiedz_info = {"ok": ok, "poprawna": poprawna, "udzielona": odpowiedz}
        if len(test_w_toku["odpowiedzi"]) >= total:
            stan["test_w_toku"] = None
            zapisz_stan(stan)
            return jsonify({
                "tryb": "bledne",
                "zakonczony": True,
                "ostatnia_odpowiedz": odpowiedz_info,
                "pozostalo_w_puli": len(stan["bledne_odpowiedzi"]),
            })
        zapisz_stan(stan)
        dane = test_stan_klienta(test_w_toku)
        dane["ostatnia_odpowiedz"] = odpowiedz_info
        return jsonify(dane)

    if len(test_w_toku["odpowiedzi"]) >= total:
        wynik = finalizuj_test(stan, test_w_toku)
        zapisz_stan(stan)
        return jsonify(wynik)

    zapisz_stan(stan)
    return jsonify(test_stan_klienta(test_w_toku))


@app.route("/api/test/finish", methods=["POST"])
def api_test_finish():
    stan = wczytaj_stan()
    test_w_toku = stan.get("test_w_toku")
    if not test_w_toku:
        return jsonify({"error": "brak testu w toku"}), 400
    wynik = finalizuj_test(stan, test_w_toku)
    zapisz_stan(stan)
    return jsonify(wynik)


@app.route("/api/test/abort", methods=["POST"])
def api_test_abort():
    stan = wczytaj_stan()
    test_w_toku = stan.get("test_w_toku")
    if not test_w_toku:
        return jsonify({"error": "brak testu w toku"}), 400
    if test_w_toku["tryb"] == "bledne":
        # Tryb naprawczy nie ma punktacji do wycofania - odpowiedzi już udzielone
        # zostają trwałe (poprawne zniknęły z puli błędnych), po prostu przerywamy.
        stan["test_w_toku"] = None
    else:
        przerwij_test(stan, test_w_toku)
    zapisz_stan(stan)
    return jsonify({"ok": True})


def finalizuj_test(stan, test_w_toku):
    """Kończy test: dolicza nieodpowiedziane jako błędne, liczy punkty, aktualizuje pule."""
    odpowiedziane_ids = {o["id"] for o in test_w_toku["odpowiedzi"]}
    for qid in test_w_toku["pytania_ids"]:
        if qid not in odpowiedziane_ids:
            poprawna = PYTANIA[qid]["poprawna"]
            test_w_toku["odpowiedzi"].append({"id": qid, "udzielona": None, "poprawna": poprawna, "ok": False})
            zarejestruj_odpowiedz(stan, qid, False, test_w_toku)

    punkty = sum(PYTANIA[o["id"]]["punkty"] for o in test_w_toku["odpowiedzi"] if o["ok"])
    max_pkt = maks_punktow(test_w_toku["pytania_ids"])
    prog = prog_zdania(max_pkt)
    zdany = punkty >= prog
    teraz = datetime.now().isoformat()

    historia_rekord = {
        "test_id": test_w_toku["test_id"],
        "typ": test_w_toku["tryb"],
        "data": teraz,
        "liczba_pytan": len(test_w_toku["pytania_ids"]),
        "punkty": punkty,
        "max_punkty": max_pkt,
        "prog": prog,
        "zdany": zdany,
        "odpowiedzi": test_w_toku["odpowiedzi"],
    }
    stan["historia_testow"].append(historia_rekord)

    if test_w_toku["tryb"] == "normalny":
        if not zdany:
            stan["niezdane_testy"].append({
                "test_id": test_w_toku["test_id"],
                "pytania": list(test_w_toku["pytania_ids"]),
                "utworzono": teraz,
                "ostatnia_proba": teraz,
                "ostatni_wynik": punkty,
            })
    elif test_w_toku["tryb"] == "powtorka":
        rekord_id = test_w_toku["powiazany_niezdany_test_id"]
        rekord = next((t for t in stan["niezdane_testy"] if t["test_id"] == rekord_id), None)
        if rekord:
            if zdany:
                stan["niezdane_testy"].remove(rekord)
            else:
                rekord["ostatnia_proba"] = teraz
                rekord["ostatni_wynik"] = punkty

    stan["test_w_toku"] = None

    odpowiedzi_zwrotne = []
    for o in historia_rekord["odpowiedzi"]:
        q = PYTANIA[o["id"]]
        odpowiedzi_zwrotne.append({
            "id": o["id"],
            "pytanie": q["pytanie"],
            "udzielona": o["udzielona"],
            "poprawna": o["poprawna"],
            "ok": o["ok"],
            "punkty": q["punkty"],
        })

    return {
        "zakonczony": True,
        "wynik": {
            "punkty": punkty,
            "max_punkty": max_pkt,
            "prog": prog,
            "zdany": zdany,
            "odpowiedzi": odpowiedzi_zwrotne,
        },
    }


# ---------------------------------------------------------------------------
# Routes - reset / eksport / import
# ---------------------------------------------------------------------------

@app.route("/api/reset", methods=["POST"])
def api_reset():
    stan = stan_domyslny()
    zapisz_stan(stan)
    return jsonify({"ok": True})


@app.route("/api/export")
def api_export():
    return send_file(STAN_PATH, as_attachment=True, download_name="stan.json")


@app.route("/api/import", methods=["POST"])
def api_import():
    if "plik" not in request.files:
        return jsonify({"error": "brak pliku"}), 400
    plik = request.files["plik"]
    try:
        dane = json.load(plik.stream)
    except Exception:
        return jsonify({"error": "niepoprawny plik JSON"}), 400

    wymagane = {"pula_wejsciowa", "bledne_odpowiedzi", "niezdane_testy", "historia_testow", "statystyki_pytan"}
    if not wymagane.issubset(dane.keys()):
        return jsonify({"error": "plik nie wygląda na poprawny stan.json"}), 400

    dane.setdefault("test_w_toku", None)
    zapisz_stan(dane)
    return jsonify({"ok": True})


if __name__ == "__main__":
    wczytaj_stan()
    app.run(host="0.0.0.0", port=5000, debug=False)
