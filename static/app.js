(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const ekrany = {
    dashboard: $("ekran-dashboard"),
    test: $("ekran-test"),
    wynik: $("ekran-wynik"),
  };

  let timerInterval = null;
  let pozostaloSekund = 0;
  let wybranaOdpowiedz = null;
  let trybBiezacegoTestu = null;

  function pokazEkran(nazwa) {
    Object.values(ekrany).forEach((el) => el.classList.add("hidden"));
    ekrany[nazwa].classList.remove("hidden");
  }

  async function api(url, opts) {
    const resp = await fetch(url, opts);
    const dane = await resp.json().catch(() => null);
    if (!resp.ok) {
      throw new Error((dane && dane.error) || `Błąd ${resp.status}`);
    }
    return dane;
  }

  // ---------------- Dashboard ----------------

  async function odswiezDashboard() {
    const d = await api("/api/dashboard");
    renderDashboard(d);
  }

  function renderDashboard(d) {
    const p = d.postep_pytan;
    $("hero-zrobione").textContent = p.zrobione;
    $("hero-wszystkie").textContent = p.wszystkie;
    $("hero-procent").textContent = `${p.procent}%`;
    $("hero-podst").textContent = p.podstawowe_zostalo;
    $("hero-spec").textContent = p.specjalistyczne_zostalo;
    $("hero-route-fill").style.width = `${p.procent}%`;
    $("hero-route-marker").style.left = `${p.procent}%`;

    const s = d.skutecznosc;
    $("sk-lacznie").textContent = s.procent_lacznie === null ? "—" : `${s.procent_lacznie}%`;
    $("sk-podst").textContent = s.procent_podstawowe === null ? "—" : `${s.procent_podstawowe}%`;
    $("sk-spec").textContent = s.procent_specjalistyczne === null ? "—" : `${s.procent_specjalistyczne}%`;

    const t = d.testy;
    $("t-zrobione").textContent = t.zrobione;
    $("t-zdane").textContent = t.procent_zdanych === null ? "—" : `${t.procent_zdanych}%`;
    $("t-zostalo").textContent = t.zostalo_do_konca;

    const pn = d.pule_naprawcze;
    $("p-bledne").textContent = pn.bledne_odpowiedzi;
    $("p-niezdane").textContent = pn.niezdane_testy;

    const prog = d.prognoza;
    const progEl = $("prog-tekst");
    if (prog.status === "ok") {
      progEl.textContent = `Przy tempie ~${prog.tempo_dziennie} zdanych testów/dzień, koniec puli ok. ${prog.data_zakonczenia}.`;
    } else if (prog.status === "brak_tempa") {
      progEl.textContent = "Jeszcze żaden test nie został zdany — prognoza pojawi się po pierwszym zdanym teście.";
    } else {
      progEl.textContent = "Za mało danych — zrób kilka testów w różnych dniach, żeby zobaczyć prognozę.";
    }

    $("banner-ukonczone").classList.toggle("hidden", !d.ukonczone);
    $("btn-nowy-test").disabled = p.podstawowe_zostalo === 0 && p.specjalistyczne_zostalo === 0;
    $("btn-test-bledne").disabled = pn.bledne_odpowiedzi === 0;
    $("btn-powtorki").disabled = pn.niezdane_testy === 0;
  }

  $("btn-kalkulator").addEventListener("click", async () => {
    const data = $("input-data-cel").value;
    const wynikEl = $("kalkulator-wynik");
    if (!data) { wynikEl.textContent = "Wybierz datę."; return; }
    try {
      const r = await api(`/api/kalkulator_tempa?data=${data}`);
      if (r.error) {
        wynikEl.textContent = r.error === "data w przeszłości lub dzisiejsza" ? "Wybrana data już minęła." : r.error;
      } else {
        wynikEl.textContent = `${r.testy_dziennie} test(y)/dzień przez ${r.dni_do_daty} dni.`;
      }
    } catch (e) {
      wynikEl.textContent = e.message;
    }
  });

  // ---------------- Eksport / import / reset ----------------

  $("btn-eksport").addEventListener("click", () => {
    window.location.href = "/api/export";
  });

  $("btn-import-open").addEventListener("click", () => $("input-import").click());
  $("input-import").addEventListener("change", async (ev) => {
    const plik = ev.target.files[0];
    if (!plik) return;
    const fd = new FormData();
    fd.append("plik", plik);
    try {
      await api("/api/import", { method: "POST", body: fd });
      await odswiezDashboard();
      alert("Stan zaimportowany.");
    } catch (e) {
      alert(`Import nie powiódł się: ${e.message}`);
    }
    ev.target.value = "";
  });

  $("btn-reset-open").addEventListener("click", () => $("modal-reset").classList.remove("hidden"));
  $("btn-reset-cancel").addEventListener("click", () => $("modal-reset").classList.add("hidden"));
  $("btn-reset-confirm").addEventListener("click", async () => {
    await api("/api/reset", { method: "POST" });
    $("modal-reset").classList.add("hidden");
    await odswiezDashboard();
  });

  async function wyjdzZTestu() {
    clearInterval(timerInterval);
    try {
      await api("/api/test/abort", { method: "POST" });
    } catch (e) {
      alert(`Nie można wyjść z testu: ${e.message}`);
    }
    pokazEkran("dashboard");
    await odswiezDashboard();
  }

  $("btn-przerwij-test").addEventListener("click", () => {
    if (trybBiezacegoTestu === "bledne") {
      wyjdzZTestu();
    } else {
      $("modal-przerwij").classList.remove("hidden");
    }
  });
  $("btn-przerwij-cancel").addEventListener("click", () => $("modal-przerwij").classList.add("hidden"));
  $("btn-przerwij-confirm").addEventListener("click", async () => {
    $("modal-przerwij").classList.add("hidden");
    await wyjdzZTestu();
  });

  // ---------------- Lista niezdanych ----------------

  $("btn-powtorki").addEventListener("click", async () => {
    const lista = await api("/api/niezdane");
    const cont = $("lista-niezdanych");
    cont.innerHTML = "";
    if (lista.length === 0) {
      cont.textContent = "Brak niezdanych testów.";
    } else {
      lista.forEach((t) => {
        const div = document.createElement("div");
        div.className = "niezdany-item";
        const data = new Date(t.ostatnia_proba).toLocaleString("pl-PL");
        div.innerHTML = `<span>${t.liczba_pytan} pytań · wynik ${t.ostatni_wynik}/${t.max_punkty} (próg ${t.prog}) · ${data}</span>`;
        const btn = document.createElement("button");
        btn.className = "btn btn--primary";
        btn.textContent = "Powtórz";
        btn.addEventListener("click", () => uruchomTest("powtorka", t.test_id));
        div.appendChild(btn);
        cont.appendChild(div);
      });
    }
    $("modal-niezdane").classList.remove("hidden");
  });
  $("btn-niezdane-zamknij").addEventListener("click", () => $("modal-niezdane").classList.add("hidden"));

  $("btn-nowy-test").addEventListener("click", () => uruchomTest("normalny"));
  $("btn-test-bledne").addEventListener("click", () => uruchomTest("bledne"));

  // ---------------- Test ----------------

  async function uruchomTest(tryb, test_id) {
    try {
      const dane = await api("/api/test/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tryb, test_id }),
      });
      $("modal-niezdane").classList.add("hidden");
      pokazEkran("test");
      renderPytanie(dane);
    } catch (e) {
      alert(`Nie można uruchomić testu: ${e.message}`);
    }
  }

  async function wznowTestWToku() {
    const dane = await api("/api/test/current");
    if (!dane) return false;
    if (dane.zakonczony && dane.wynik) {
      renderWynik(dane.wynik);
      return true;
    }
    pokazEkran("test");
    renderPytanie(dane);
    return true;
  }

  function renderPytanie(dane) {
    clearInterval(timerInterval);
    wybranaOdpowiedz = null;
    trybBiezacegoTestu = dane.tryb;

    $("test-numer").textContent = `${dane.numer} / ${dane.wszystkie}`;
    const q = dane.pytanie;
    $("test-czesc").textContent = q.zakres === "podstawowy" ? "Podstawowa" : "Specjalistyczna";
    $("test-punkty").textContent = `${q.punkty} pkt`;
    $("test-pytanie-tekst").textContent = q.pytanie;
    $("test-feedback").classList.add("hidden");

    renderMedia(q.media, q.media_typ);
    renderOdpowiedzi(q.typ, q.odpowiedzi);

    const btnPrzerwij = $("btn-przerwij-test");
    if (dane.tryb === "bledne") {
      btnPrzerwij.textContent = "Wróć do ekranu głównego";
      $("timer-disc").classList.add("hidden");
    } else {
      btnPrzerwij.textContent = "Przerwij test";
      $("timer-disc").classList.remove("hidden");
      pozostaloSekund = dane.pozostalo_sekund;
      aktualizujTimer();
      timerInterval = setInterval(() => {
        pozostaloSekund -= 1;
        aktualizujTimer();
        if (pozostaloSekund <= 0) {
          clearInterval(timerInterval);
          zakonczTest();
        }
      }, 1000);
    }
  }

  function aktualizujTimer() {
    const m = Math.max(0, Math.floor(pozostaloSekund / 60));
    const s = Math.max(0, pozostaloSekund % 60);
    $("timer-tekst").textContent = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    $("timer-disc").classList.toggle("timer-low", pozostaloSekund <= 120);
  }

  function renderMedia(media, media_typ) {
    const cont = $("test-media");
    cont.innerHTML = "";
    if (!media) return;

    const url = `/media/${encodeURIComponent(media)}`;

    if (media_typ === "image") {
      const img = document.createElement("img");
      img.src = url;
      img.alt = "Materiał do pytania";
      img.onerror = () => {
        cont.innerHTML = `<div class="media-placeholder">Brak pliku: ${media}</div>`;
      };
      cont.appendChild(img);
    } else if (media_typ === "video") {
      const video = document.createElement("video");
      video.controls = true;
      video.src = url;
      video.onerror = () => {
        cont.innerHTML = `<div class="media-placeholder">
          Nie można odtworzyć wideo w przeglądarce.<br>
          Zainstaluj ffmpeg i uruchom <code>convert_media.py</code>, aby przekonwertować pliki .wmv na .mp4.<br>
          <a href="${url}" target="_blank">Pobierz / odtwórz w zewnętrznym odtwarzaczu</a>
        </div>`;
      };
      cont.appendChild(video);
    }
  }

  function renderOdpowiedzi(typ, odpowiedzi) {
    const cont = $("test-odpowiedzi");
    cont.innerHTML = "";
    const btnZatwierdz = $("btn-zatwierdz");
    btnZatwierdz.disabled = true;
    btnZatwierdz.onclick = () => zatwierdzOdpowiedz();

    const jestAbc = typ === "abc";
    const opcje = jestAbc ? ["A", "B", "C"] : [["T", "Tak"], ["N", "Nie"]];

    if (jestAbc) {
      opcje.forEach((litera) => {
        const btn = document.createElement("button");
        btn.className = "odp-btn odp-btn-abc";
        btn.dataset.wartosc = litera;
        btn.innerHTML = `<span class="litera">${litera}</span><span>${odpowiedzi[litera] ?? ""}</span>`;
        btn.addEventListener("click", () => wybierz(litera, btn));
        cont.appendChild(btn);
      });
    } else {
      opcje.forEach(([val, etykieta]) => {
        const btn = document.createElement("button");
        btn.className = "odp-btn";
        btn.dataset.wartosc = val;
        btn.textContent = etykieta;
        btn.addEventListener("click", () => wybierz(val, btn));
        cont.appendChild(btn);
      });
    }

    function wybierz(val, btn) {
      wybranaOdpowiedz = val;
      cont.querySelectorAll(".odp-btn").forEach((b) => b.classList.remove("wybrana"));
      btn.classList.add("wybrana");
      btnZatwierdz.disabled = false;
    }
  }

  async function zatwierdzOdpowiedz() {
    if (wybranaOdpowiedz === null) return;
    clearInterval(timerInterval);
    $("btn-zatwierdz").disabled = true;
    try {
      const dane = await api("/api/test/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ odpowiedz: wybranaOdpowiedz }),
      });
      if (dane.tryb === "bledne") {
        pokazFeedbackBledne(dane);
      } else if (dane.zakonczony) {
        renderWynik(dane.wynik);
      } else {
        renderPytanie(dane);
      }
    } catch (e) {
      alert(`Błąd: ${e.message}`);
    }
  }

  function pokazFeedbackBledne(dane) {
    const info = dane.ostatnia_odpowiedz;

    document.querySelectorAll(".odp-btn").forEach((b) => {
      b.disabled = true;
      if (b.dataset.wartosc === info.poprawna) b.classList.add("poprawna");
      if (b.dataset.wartosc === info.udzielona && !info.ok) b.classList.add("zla");
    });

    const feedback = $("test-feedback");
    feedback.classList.remove("hidden", "feedback--ok", "feedback--bledna");
    feedback.classList.add(info.ok ? "feedback--ok" : "feedback--bledna");
    feedback.textContent = info.ok
      ? "Poprawna odpowiedź — pytanie zostało usunięte z puli błędnych."
      : `Niepoprawna odpowiedź. Poprawna: ${info.poprawna}. Pytanie zostaje w puli błędnych.`;

    const btn = $("btn-zatwierdz");
    btn.disabled = false;
    if (dane.zakonczony) {
      btn.textContent = "Zakończ";
      btn.onclick = () => {
        pokazEkran("dashboard");
        odswiezDashboard();
      };
    } else {
      btn.textContent = "Dalej";
      btn.onclick = () => renderPytanie(dane);
    }
  }

  async function zakonczTest() {
    try {
      const dane = await api("/api/test/finish", { method: "POST" });
      renderWynik(dane.wynik);
    } catch (e) {
      alert(`Błąd: ${e.message}`);
    }
  }

  function renderWynik(w) {
    pokazEkran("wynik");
    const banner = $("wynik-banner");
    banner.classList.toggle("niezdany", !w.zdany);
    $("wynik-status").textContent = w.zdany ? "ZDANY" : "NIEZDANY";
    $("wynik-punkty").textContent = w.punkty;
    $("wynik-max").textContent = w.max_punkty;
    $("wynik-prog").textContent = w.prog;

    const lista = $("wynik-lista");
    lista.innerHTML = "";
    w.odpowiedzi.forEach((o, i) => {
      const div = document.createElement("div");
      div.className = `wynik-item${o.ok ? "" : " bledna"}`;
      div.innerHTML = `
        <div class="wynik-item__pytanie">${i + 1}. ${o.pytanie}</div>
        <div class="wynik-item__odp">Twoja odpowiedź: ${o.udzielona ?? "(brak)"} · Poprawna: ${o.poprawna} · ${o.punkty} pkt</div>
      `;
      lista.appendChild(div);
    });
  }

  $("btn-wynik-dashboard").addEventListener("click", async () => {
    pokazEkran("dashboard");
    await odswiezDashboard();
  });

  // ---------------- Start ----------------

  (async () => {
    const wznowiono = await wznowTestWToku();
    if (!wznowiono) {
      pokazEkran("dashboard");
      await odswiezDashboard();
    }
  })();
})();
