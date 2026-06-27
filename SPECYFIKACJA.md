# Aplikacja: Trener egzaminu teoretycznego prawo jazdy kat. AM (w pełni lokalna)

To jest specyfikacja dla Claude Code. Zbuduj w pełni lokalną aplikację webową
emulującą państwowy egzamin teoretyczny kategorii AM. Bez chmury, bez CDN, bez
zewnętrznych API. Wszystko działa offline z plików na dysku.

## 1. Stos technologiczny (preferencja: najprostszy możliwy)

- **Backend:** Python 3 + Flask (jeden plik `app.py`). Serwuje stronę, API stanu
  i pliki multimedialne z lokalnego dysku.
- **Frontend:** czysty HTML + JS + CSS (bez frameworków, bez bundlera). Jeden
  `index.html` + `app.js` + `style.css`.
- **Uruchomienie:** `python app.py`, otwiera `http://localhost:5000`.
- Uzasadnienie wyboru Flaska zamiast czystego frontu: **stan musi być zapisywany
  w pliku na dysku** (wymóg), a przeglądarka nie zapisuje plików bez backendu.
  Flask zapisuje `stan.json` na dysku przy każdej zmianie.

## 2. Pliki wejściowe (dostarczone, są w repo)

- `pytania_AM.json` — komplet 1516 pytań AM. **Nie parsuj XLSX**, użyj tego pliku.
- `media/` — folder z plikami multimedialnymi (`.wmv`, `.jpg`). Nazwy plików
  odpowiadają polu `media` w JSON. Listę oczekiwanych plików masz w
  `lista_multimediow_AM.txt` (1266 unikalnych plików).

### Struktura `pytania_AM.json`
```json
{
  "meta": { "liczba_pytan": 1516, "podstawowe": 1407, "specjalistyczne": 109, ... },
  "pytania": [ { ...rekord... } ]
}
```

Rekord typu TAK/NIE (część podstawowa):
```json
{
  "id": 99, "pytanie": "Czy ...?", "typ": "tak_nie",
  "zakres": "podstawowy", "punkty": 3, "poprawna": "T",
  "media": "AK_D05_06_org.wmv", "media_typ": "video"
}
```

Rekord typu ABC (część specjalistyczna):
```json
{
  "id": 4614, "pytanie": "Czy ...?", "typ": "abc",
  "zakres": "specjalistyczny", "punkty": 3, "poprawna": "A",
  "media": "3A257.jpg", "media_typ": "image",
  "odpowiedzi": { "A": "...", "B": "...", "C": "..." }
}
```

### Pola — uwagi krytyczne
- `typ`: `"tak_nie"` → przyciski TAK / NIE; `"abc"` → przyciski A / B / C.
  **Steruj UI polem `typ`, nie polem `zakres`.** W danych jest kilka pytań
  podstawowych typu ABC i kilka specjalistycznych typu TAK/NIE — to celowe,
  zgodne z oryginalną bazą. `typ` zawsze mówi prawdę o formie odpowiedzi.
- `poprawna`: dla TAK/NIE wartość `"T"` lub `"N"`; dla ABC wartość `"A"`/`"B"`/`"C"`.
- `media`: może być `null` (66 pytań bez multimediów) — wtedy nie renderuj pola media.
- `media_typ`: `"video"` (odtwarzacz `<video>`), `"image"` (`<img>`), lub `null`.

### Multimedia — ważne
- Pliki `.wmv` to format Windows Media. Przeglądarki **nie odtwarzają natywnie .wmv**.
  Zaimplementuj jedno z dwóch (preferowane: pierwsze):
  1. **Konwersja przy starcie:** skrypt `convert_media.py` (ffmpeg) tworzy
     `media_web/` z plikami `.mp4` (H.264) odpowiadającymi każdemu `.wmv`.
     Aplikacja serwuje wersje `.mp4`. Mapowanie nazw: `AK_D05_06_org.wmv` →
     `AK_D05_06_org.mp4`. Jeśli `.mp4` istnieje, użyj go; w przeciwnym razie podaj
     oryginał i pokaż komunikat „zainstaluj ffmpeg i uruchom convert_media.py".
  2. Fallback: link „pobierz/odtwórz w zewnętrznym odtwarzaczu".
- Jeśli pliku media brakuje na dysku, pokaż placeholder „brak pliku: <nazwa>",
  ale **nie blokuj** pytania — pozwól odpowiedzieć.

## 3. Schemat egzaminu AM (sztywny, zgodny z państwowym)

Pojedynczy test = **32 pytania**: **20 podstawowych + 12 specjalistycznych**.

| Część | Liczba pytań | Punktacja za pytanie | Suma pkt |
|---|---|---|---|
| Podstawowa | 20 | 10×3 + 6×2 + 4×1 | 46 |
| Specjalistyczna | 12 | 6×3 + 4×2 + 2×1 | 28 |
| **Razem** | **32** | — | **74** |

- Dobór punktacji: w każdym teście losuj tak, by liczba pytań za 3/2/1 pkt
  odpowiadała tabeli (10/6/4 podstawowe, 6/4/2 specjalistyczne). Jeśli w puli
  zabraknie pytań o danej wadze, dobierz najbliższą dostępną wagą i licz
  faktyczne `punkty` pytania.
- **Próg zdania: 68 / 74 pkt.**
- **Limit czasu: 25 minut** (licznik widoczny; po przekroczeniu test kończy się
  automatycznie i jest oceniany ze stanu bieżącego).
- Część podstawowa jest **przed** specjalistyczną (jak na prawdziwym egzaminie).
  Na prawdziwym egzaminie pytania podstawowe mają osobny limit czasu na przeczytanie,
  ale **nie wymagamy** tego odwzorowania — wystarczy łączny licznik 25 min.

## 4. Pule i przepływ danych (sedno aplikacji)

Utrzymuj w stanie następujące, rozłączne pule. Wszystkie trwałe (`stan.json`).

### 4.1 Pula wejściowa (`pula_wejsciowa`)
- Start: wszystkie 1516 pytań (1407 podstawowych + 109 specjalistycznych),
  rozdzielone na dwie podpule: `wejsciowa_podstawowe` i `wejsciowa_specjalistyczne`.
- Przy generowaniu testu losuj 20 z podstawowych i 12 ze specjalistycznych.
- **Wylosowane pytanie jest USUWANE z puli wejściowej** (nie wróci jako „nowe").

### 4.2 Reguła wyczerpywania pul (rozstrzygnięte)
Pule wyczerpują się w różnym tempie (specjalistyczna 109 → ~10 testów; podstawowa
1407 → ~71 testów). Zachowanie:
- Dopóki są pytania specjalistyczne: test = 20 podst. + 12 spec.
- **Gdy pula specjalistyczna pusta, a podstawowa nie:** generuj testy z **samych
  20 pytań podstawowych** (max 46 pkt, próg zdania przeskaluj proporcjonalnie:
  patrz 4.6).
- **Ostatni test może być krótszy** niż 20, jeśli w puli podstawowej zostało < 20
  pytań (np. końcowa resztka 7). Oceniaj proporcjonalnie.

### 4.3 Pula błędnych odpowiedzi (`bledne_odpowiedzi`)
- Za każdym razem, gdy użytkownik odpowie **błędnie** na pytanie (w dowolnym
  trybie testu), **to pytanie trafia do `bledne_odpowiedzi`** (zbiór unikalny po `id`).
- Tryb „Test błędnych": użytkownik może w dowolnym momencie uruchomić test złożony
  **wyłącznie z pytań z `bledne_odpowiedzi`**. Rozmiar takiego testu: do 32 pytań
  (lub mniej, jeśli błędnych jest mniej). Nie stosuje schematu 20+12 — bierz co jest.
- W teście błędnych: **poprawna odpowiedź usuwa pytanie z `bledne_odpowiedzi`**.
  Ponowny błąd zostawia je w puli.

### 4.4 Pula niezdanych testów (`niezdane_testy`)
- Każdy **ukończony test z wynikiem < próg** trafia do `niezdane_testy` jako rekord
  z dokładnym zestawem pytań (lista `id`), które w nim były.
- Użytkownik może w dowolnym momencie **powtórzyć** konkretny niezdany test (ten sam
  zestaw pytań, ta sama punktacja).
- **Zdanie powtórki usuwa** ten test z `niezdane_testy`. Niezdanie — zostaje
  (zaktualizuj datę ostatniej próby).
- Uwaga: pytania z niezdanego testu **nie wracają** do puli wejściowej (zostały już
  „zużyte"); powtarzasz dokładnie ten sam zestaw.

### 4.5 Relacja między pulami
- Błędne pojedyncze pytania (4.3) i niezdane całe testy (4.4) to **niezależne**
  mechanizmy. Pytanie może być jednocześnie w `bledne_odpowiedzi` i należeć do testu
  w `niezdane_testy`.
- Test „błędnych" i powtórki „niezdanych testów" **nie zużywają** puli wejściowej
  i **nie tworzą** nowych wpisów w `niezdane_testy` (to treningi naprawcze).
  Wyjątek: jeśli chcesz, powtórka niezdanego testu MOŻE go usunąć z puli po zdaniu —
  to jest wymagane (4.4). Ale nie dodawaj jej wyniku jako nowego „niezdanego testu".

### 4.6 Punktacja testów skróconych
- Test 32-pyt.: próg 68/74.
- Test z samych 20 podstawowych: max 46 pkt, próg = `ceil(68/74 * 46)` = **43/46**.
- Test krótszej resztki / test błędnych: próg = `ceil(0.9189 * max_pkt)`
  (0.9189 = 68/74). Zaokrąglaj w górę. Pokaż próg użytkownikowi przed startem.

## 5. Warunki zakończenia całości (definicja „ukończone")

Aplikacja sygnalizuje pełne ukończenie, gdy **jednocześnie**:
1. `pula_wejsciowa` (podstawowe + specjalistyczne) jest **pusta** — każde pytanie
   trafiło kiedyś do jakiegoś testu,
2. `niezdane_testy` jest **pusta**,
3. `bledne_odpowiedzi` jest **pusta**.

Dopóki którykolwiek warunek niespełniony — pokazuj, czego brakuje.

## 6. Stan na dysku (`stan.json`)

Zapisuj atomowo (zapis do pliku tymczasowego + rename) po **każdej** zmianie.
Wczytuj przy starcie; jeśli brak — inicjalizuj z `pytania_AM.json`.

Proponowany kształt:
```json
{
  "wersja": 1,
  "utworzono": "ISO-8601",
  "pula_wejsciowa": { "podstawowe": [id...], "specjalistyczne": [id...] },
  "bledne_odpowiedzi": [id...],
  "niezdane_testy": [
    { "test_id": "uuid", "pytania": [id...], "utworzono": "ISO",
      "ostatnia_proba": "ISO", "ostatni_wynik": 41 }
  ],
  "historia_testow": [
    { "test_id": "uuid", "typ": "normalny|bledne|powtorka",
      "data": "ISO", "liczba_pytan": 32, "punkty": 70, "max_punkty": 74,
      "zdany": true, "odpowiedzi": [ {"id":99,"udzielona":"T","poprawna":"T","ok":true} ] }
  ],
  "statystyki_pytan": {
    "99": { "razy_pokazane": 2, "razy_poprawnie": 1 }
  }
}
```
- `historia_testow` jest źródłem prawdy dla dashboardu (liczby, tempo, daty).
- Dodaj endpoint/przycisk **Reset** (kasuje `stan.json` po potwierdzeniu).
- Dodaj **eksport/import** `stan.json` (przyciski) — kopia zapasowa postępu.

## 7. Dashboard (ekran główny)

Pokaż na bieżąco (wszystko liczone ze stanu):

**Postęp pytań**
- Pytań zrobionych (unikalnych, które opuściły pulę wejściową) / 1516 + %.
- Pytań zostało w puli wejściowej (podstawowe / specjalistyczne osobno).

**Skuteczność**
- % odpowiedzi poprawnych łącznie (wszystkie udzielone odpowiedzi w historii).
- % poprawnych osobno dla części podstawowej i specjalistycznej.

**Testy**
- Liczba testów zrobionych (typ „normalny").
- % testów zdanych.
- Ile testów zostało do końca (szacunek): `ceil(pozostałe_podstawowe/20)` przy
  uwzgl. reguły 4.2 (po wyczerpaniu spec. testy z 20 podst.).

**Pule naprawcze**
- Liczba pytań w `bledne_odpowiedzi` (do powtórki).
- Liczba testów w `niezdane_testy` (do powtórki).

**Prognoza**
- **Oczekiwana data zakończenia** na podstawie dotychczasowego tempa:
  - tempo = liczba testów „normalnych" zdanych / liczba dni od pierwszego testu
    (licz dni kalendarzowe z `historia_testow`; jeśli < 2 dni danych, pokaż
    „za mało danych");
  - pozostało_testów = szacunek z sekcji „Testy" + liczba `niezdane_testy`;
  - data = dziś + ceil(pozostało_testów / tempo_na_dzień).
- **Kalkulator tempa:** pole „chcę skończyć do <data>" → wylicz i pokaż
  **ile testów dziennie** trzeba robić (zakładając, że wszystkie zdasz za 1. razem):
  `ceil(pozostało_testów / dni_do_daty)`. Jeśli data w przeszłości → komunikat.

Uwaga do prognozy: „zakładając że wszystkie zdam" oznacza, że do pozostałych
testów **nie** doliczasz hipotetycznych przyszłych powtórek — tylko realnie
istniejące `niezdane_testy` + testy potrzebne do wyczerpania puli wejściowej.

## 8. Ekran testu

- Pasek: numer pytania / wszystkie, część (Podstawowa/Specjalistyczna), punkty
  pytania, licznik czasu (25:00 w dół).
- Obszar media: `<video controls>` dla wideo, `<img>` dla obrazka, nic gdy brak.
- Treść pytania + przyciski odpowiedzi zależne od `typ`.
- Nawigacja: dalej / wstecz (lub auto-przejście po odpowiedzi — Twój wybór,
  ale pozwól wrócić i zmienić przed zatwierdzeniem testu, jak na egzaminie:
  faktycznie egzamin nie pozwala wracać — **zablokuj cofanie**, zatwierdzenie
  odpowiedzi jest ostateczne).
- Po teście: ekran wyniku (punkty/max, zdany/niezdany, lista pytań z oznaczeniem
  poprawnych/błędnych i podglądem poprawnej odpowiedzi).

## 9. Tryby uruchamiania testu (menu)

1. **Nowy test egzaminacyjny** — z puli wejściowej wg reguł 3 i 4.2.
2. **Test błędnych odpowiedzi** — z `bledne_odpowiedzi` (4.3).
3. **Powtórka niezdanego testu** — wybór z listy `niezdane_testy` (4.4).

## 10. Kryteria akceptacji (przetestuj to)

- [ ] Start bez `stan.json` inicjalizuje 1516 pytań w puli wejściowej.
- [ ] Nowy test ma 20+12 i poprawny rozkład punktów; po teście te 32 pytania
      znikają z puli wejściowej.
- [ ] Błędna odpowiedź dodaje pytanie do `bledne_odpowiedzi`; poprawna w trybie
      „błędnych" je usuwa.
- [ ] Niezdany test ląduje w `niezdane_testy`; zdana powtórka go usuwa.
- [ ] Po wyczerpaniu puli specjalistycznej testy mają 20 pytań (sam podst.),
      próg 43/46.
- [ ] Stan przeżywa restart serwera (zapis na dysk działa).
- [ ] Dashboard liczby zgadzają się z `historia_testow`.
- [ ] Prognoza daty i kalkulator „testów na dzień" liczą się poprawnie.
- [ ] `.wmv` da się odtworzyć (po konwersji do `.mp4`) lub jest sensowny fallback.
- [ ] Reset i eksport/import stanu działają.

## 11. Struktura repo (proponowana)
```
/
├── app.py                  # Flask: routing, API stanu, serwowanie media
├── convert_media.py        # ffmpeg .wmv -> .mp4 (idempotentny)
├── pytania_AM.json         # dane (dostarczone)
├── lista_multimediow_AM.txt
├── stan.json               # tworzony przy pierwszym uruchomieniu
├── media/                  # oryginały .wmv/.jpg (dostarczone)
├── media_web/              # .mp4 po konwersji (generowane)
├── static/
│   ├── app.js
│   └── style.css
└── templates/
    └── index.html
```

## 12. Czego NIE robić
- Nie używaj CDN ani zewnętrznych bibliotek ładowanych po sieci (ma działać offline).
- Nie parsuj XLSX — dane są w `pytania_AM.json`.
- Nie pozwalaj na cofanie odpowiedzi w trakcie testu egzaminacyjnego.
- Nie zliczaj treningów naprawczych (błędne / powtórki) jako „testów zrobionych"
  w głównym liczniku postępu testów egzaminacyjnych.
