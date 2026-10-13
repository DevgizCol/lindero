/* Lindero · comportamiento de la interfaz. Sin dependencias; todo funciona también sin JavaScript. */
(function () {
  "use strict";
  var d = document, raiz = d.documentElement;
  raiz.classList.add("js");

  /* cabecera con borde al bajar */
  var cab = d.querySelector(".cab");
  if (cab) {
    var marcar = function () { cab.classList.toggle("fija", window.scrollY > 8); };
    marcar();
    window.addEventListener("scroll", marcar, { passive: true });
  }

  /* aparición de bloques al entrar en pantalla */
  var bloques = d.querySelectorAll("[data-ver]");
  if ("IntersectionObserver" in window && bloques.length) {
    var obs = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("visto"); obs.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    bloques.forEach(function (b) { obs.observe(b); });
  } else {
    bloques.forEach(function (b) { b.classList.add("visto"); });
  }

  var pesos = function (n) { return "$ " + Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "."); };

  /* calculadora de precio */
  var calc = d.querySelector("[data-calc]");
  if (calc) {
    var unidad = +calc.dataset.unidad, minimo = +calc.dataset.minimo;
    var rango = calc.querySelector("input[type=range]"), cuantos = calc.querySelector("[data-cuantos]"),
      total = calc.querySelector("[data-total]"), nota = calc.querySelector("[data-nota]");
    var pintar = function () {
      var n = +rango.value, bruto = n * unidad, t = Math.max(minimo, bruto);
      cuantos.textContent = n;
      total.textContent = pesos(t);
      nota.textContent = bruto < minimo ? "Pedido mínimo " + pesos(minimo) : n + " × " + pesos(unidad);
    };
    rango.addEventListener("input", pintar);
    pintar();
  }

  /* zonas para soltar archivos */
  var legible = function (b) { return b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB"; };
  d.querySelectorAll(".soltar").forEach(function (zona) {
    var entrada = zona.querySelector("input[type=file]"), titulo = zona.querySelector("b"), detalle = zona.querySelector("small"),
      accion = zona.querySelector(".accion"), t0 = titulo.textContent, d0 = detalle.textContent;
    var pintar = function () {
      var fs = entrada.files;
      if (!fs || !fs.length) { zona.classList.remove("lleno"); titulo.textContent = t0; detalle.textContent = d0; accion.textContent = "Elegir"; return; }
      var peso = 0;
      for (var i = 0; i < fs.length; i++) peso += fs[i].size;
      zona.classList.add("lleno");
      titulo.textContent = fs.length === 1 ? fs[0].name : fs.length + " archivos";
      detalle.textContent = legible(peso) + " · listo";
      accion.textContent = "Cambiar";
    };
    entrada.addEventListener("change", pintar);
    ["dragenter", "dragover"].forEach(function (ev) { zona.addEventListener(ev, function () { zona.classList.add("sobre"); }); });
    ["dragleave", "drop"].forEach(function (ev) { zona.addEventListener(ev, function () { zona.classList.remove("sobre"); }); });
    pintar();
  });

  /* formulario por pasos */
  var form = d.querySelector("[data-pasos]");
  if (form) {
    var pasos = [].slice.call(form.querySelectorAll(".paso-form")), etapas = [].slice.call(form.querySelectorAll(".etapas li")), actual = 0;
    var mostrar = function (i, enfocar) {
      actual = i;
      pasos.forEach(function (p, k) { p.classList.toggle("activo", k === i); });
      etapas.forEach(function (e, k) {
        e.classList.toggle("hecha", k < i);
        e.classList.toggle("actual", k === i);
        if (k === i) e.setAttribute("aria-current", "step"); else e.removeAttribute("aria-current");
      });
      if (enfocar) {
        var leyenda = pasos[i].querySelector("legend");
        if (leyenda) { leyenda.setAttribute("tabindex", "-1"); leyenda.focus({ preventScroll: true }); }
        form.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    };
    var valido = function (i) {
      var campos = pasos[i].querySelectorAll("input, select, textarea");
      for (var k = 0; k < campos.length; k++) {
        if (!campos[k].checkValidity()) { campos[k].reportValidity(); return false; }
      }
      return true;
    };
    form.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-ir]");
      if (!b) return;
      ev.preventDefault();
      if (b.dataset.ir === "sig") { if (valido(actual)) mostrar(Math.min(actual + 1, pasos.length - 1), true); }
      else mostrar(Math.max(actual - 1, 0), true);
    });
    form.addEventListener("submit", function (ev) {
      for (var i = 0; i < pasos.length; i++) {
        var campos = pasos[i].querySelectorAll("input, select, textarea"), mal = false;
        for (var k = 0; k < campos.length; k++) if (!campos[k].checkValidity()) { mal = true; break; }
        if (mal) { ev.preventDefault(); mostrar(i, true); valido(i); return; }
      }
      var enviar = form.querySelector("[type=submit]");
      enviar.disabled = true;
      enviar.textContent = "Subiendo archivos…";
    });
    mostrar(form.dataset.inicio ? +form.dataset.inicio : 0, false);
  }

  /* estado del pedido: consulta cada pocos segundos y recarga cuando cambia */
  var seg = d.querySelector("[data-estado-url]");
  if (seg) {
    var previo = seg.dataset.estado;
    /* pide al servidor que procese lo pendiente; la respuesta llega cuando el motor termina */
    if (seg.dataset.procesarUrl) {
      var cuerpo = new URLSearchParams();
      cuerpo.set("csrf", seg.dataset.csrf);
      fetch(seg.dataset.procesarUrl, { method: "POST", body: cuerpo, credentials: "same-origin" }).catch(function () {});
    }
    var consultar = function () {
      fetch(seg.dataset.estadoUrl, { headers: { Accept: "application/json" }, cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          if (j && j.estado !== previo) { window.location.reload(); return; }
          setTimeout(consultar, 4000);
        })
        .catch(function () { setTimeout(consultar, 8000); });
    };
    setTimeout(consultar, 3000);
    var frases = seg.querySelectorAll("[data-frase]"), turno = 0;
    if (frases.length > 1) {
      setInterval(function () {
        frases[turno].hidden = true;
        turno = (turno + 1) % frases.length;
        frases[turno].hidden = false;
      }, 3600);
    }
  }

  /* ── Visor Satelital Interactivo (Leaflet + Ortofoto Esri + Predios Malambo) ── */
  var elMapa = d.getElementById("mapa-hero");
  if (elMapa && typeof L !== "undefined") {
    try {
      var mapaHero = L.map("mapa-hero", {
        center: [10.8584, -74.7738],
        zoom: 18,
        zoomControl: true,
        scrollWheelZoom: false,
        attributionControl: false
      });

      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 19
      }).addTo(mapaHero);

      var predios = [
        {
          nodo: "T1",
          area: "201.64 m²",
          coords: [[10.85868, -74.77395], [10.85874, -74.77372], [10.85818, -74.77360], [10.85812, -74.77383]],
          colindantes: "Norte: Predio 0019 · Sur: Calle 12 · Oriente: Predio 0044"
        },
        {
          nodo: "T2",
          area: "198.50 m²",
          coords: [[10.85874, -74.77372], [10.85880, -74.77349], [10.85824, -74.77337], [10.85818, -74.77360]],
          colindantes: "Norte: Predio 0020 · Sur: Calle 12 · Poniente: T1"
        },
        {
          nodo: "T3",
          area: "215.10 m²",
          coords: [[10.85880, -74.77349], [10.85886, -74.77326], [10.85830, -74.77314], [10.85824, -74.77337]],
          colindantes: "Norte: Predio 0021 · Sur: Calle 12 · Poniente: T2"
        },
        {
          nodo: "T4",
          area: "206.80 m²",
          coords: [[10.85886, -74.77326], [10.85892, -74.77303], [10.85836, -74.77291], [10.85830, -74.77314]],
          colindantes: "Norte: Predio 0022 · Sur: Calle 12 · Poniente: T3"
        }
      ];

      var grupo = L.featureGroup();
      predios.forEach(function (p) {
        var pol = L.polygon(p.coords, {
          color: "#00f0ff",
          weight: 2.5,
          fillColor: "#0066ff",
          fillOpacity: 0.35,
          dashArray: "3, 3"
        });

        pol.bindPopup(
          "<div style='font-family:sans-serif;color:#0b0f19;padding:6px 2px;min-width:180px;'>" +
            "<div style='font-size:11px;font-weight:700;color:#0066ff;letter-spacing:1px;'>PREDIO CATASTRAL</div>" +
            "<div style='font-size:18px;font-weight:800;color:#0f172a;'>NODO " + p.nodo + "</div>" +
            "<div style='font-size:13px;margin:4px 0 6px;'><b>Área:</b> " + p.area + " · <b>Sistema:</b> CTM12</div>" +
            "<div style='font-size:11px;color:#64748b;border-top:1px solid #e2e8f0;padding-top:4px;'>" + p.colindantes + "</div>" +
          "</div>"
        );

        pol.on("mouseover", function () {
          this.setStyle({ fillOpacity: 0.65, color: "#ffffff", weight: 3 });
        });
        pol.on("mouseout", function () {
          this.setStyle({ fillOpacity: 0.35, color: "#00f0ff", weight: 2.5 });
        });

        grupo.addLayer(pol);
      });

      grupo.addTo(mapaHero);
      mapaHero.fitBounds(grupo.getBounds(), { padding: [35, 35] });
    } catch (err) {
      console.warn("Leaflet mapa-hero:", err);
    }
  }
})();
