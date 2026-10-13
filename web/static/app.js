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
      nota.textContent = bruto < minimo ? "Pedido mínimo protegido " + pesos(minimo) : n + " × " + pesos(unidad);
      
      // Neuropsicología de Anclaje de Valor: Comparar contra cadista tradicional ($40.000 COP/plano y 45 min/plano)
      var costoCadista = n * 45000;
      var ahorroDinero = Math.max(0, costoCadista - t);
      var horasAhorradas = Math.max(1, Math.round((n * 40) / 60));
      var badgeAhorro = calc.querySelector("[data-ahorro]");
      if (badgeAhorro) {
        badgeAhorro.innerHTML = "⚡ <b>Ahorras aprox. " + pesos(ahorroDinero) + " COP</b> y <b>" + horasAhorradas + " horas</b> de dibujo manual en CAD";
      }
    };
    rango.addEventListener("input", pintar);
    pintar();
  }

  /* ── Animación Neuropsicológica Count-Up para las Cifras ── */
  var animarContador = function (el, valorFinal, esMoneda, esDecimal, sufijo) {
    var duracion = 1400; // ms
    var inicio = null;
    var paso = function (timestamp) {
      if (!inicio) inicio = timestamp;
      var progreso = Math.min((timestamp - inicio) / duracion, 1);
      // Easing suave (easeOutExpo)
      var ease = progreso === 1 ? 1 : 1 - Math.pow(2, -10 * progreso);
      var valorActual = ease * valorFinal;
      
      if (esMoneda) {
        el.textContent = "$" + Math.round(valorActual).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".") + sufijo;
      } else if (esDecimal) {
        el.textContent = valorActual.toFixed(1).replace(".", ",") + sufijo;
      } else {
        el.textContent = Math.round(valorActual) + sufijo;
      }
      
      if (progreso < 1) {
        window.requestAnimationFrame(paso);
      }
    };
    window.requestAnimationFrame(paso);
  };

  var contenedorCifras = d.querySelector(".cifras");
  if (contenedorCifras && "IntersectionObserver" in window) {
    var obsCifras = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (e) {
        if (e.isIntersecting) {
          contenedorCifras.querySelectorAll("[data-contador]").forEach(function (el) {
            var val = parseFloat(el.dataset.valor);
            var esMoneda = el.dataset.moneda === "true";
            var esDecimal = el.dataset.decimal === "true";
            var sufijo = el.dataset.sufijo || "";
            animarContador(el, val, esMoneda, esDecimal, sufijo);
          });
          obsCifras.unobserve(e.target);
        }
      });
    }, { threshold: 0.25 });
    obsCifras.observe(contenedorCifras);
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
      }, 3  /* ── Visor Satelital Interactivo Real (Leaflet + Ortofoto Esri + Predios El Tesoro, Malambo) ── */
  var elMapa = d.getElementById("mapa-hero");
  if (elMapa && typeof L !== "undefined") {
    try {
      var mapaHero = L.map("mapa-hero", {
        center: [10.84786, -74.77180],
        zoom: 18.5,
        zoomControl: true,
        scrollWheelZoom: false,
        attributionControl: false
      });

      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 19
      }).addTo(mapaHero);

      // Predios reales embebidos (Barrio El Tesoro, Malambo - CTM12 EPSG:9377 a WGS84)
      var prediosRealesBase = [
        {
          nodo: "T1",
          area: "334.18 m²",
          direccion: "K 1C SUR 4 94 CASA 1",
          codigo: "084330100000002310053000000000",
          manzana: "08433010000000231",
          coords: [[10.847861,-74.771648],[10.847841,-74.771591],[10.847707,-74.771644],[10.847463,-74.771737],[10.847489,-74.771807],[10.847695,-74.771722],[10.847861,-74.771648]]
        },
        {
          nodo: "T2",
          area: "227.52 m²",
          direccion: "K 1C SUR 4 94 CASA 1-A",
          codigo: "084330100000002310053000000000",
          manzana: "08433010000000231",
          coords: [[10.847868,-74.771692],[10.847861,-74.771648],[10.847695,-74.771722],[10.847489,-74.771807],[10.847508,-74.771849],[10.847716,-74.771767],[10.847868,-74.771692]]
        },
        {
          nodo: "T3",
          area: "361.37 m²",
          direccion: "K 1C SUR 4 94 CASA 1-B",
          codigo: "084330100000002310053000000000",
          manzana: "08433010000000231",
          coords: [[10.84789,-74.771786],[10.847868,-74.771692],[10.847716,-74.771767],[10.847508,-74.771849],[10.847527,-74.771887],[10.847715,-74.771885],[10.847897,-74.771821],[10.84789,-74.771786]]
        },
        {
          nodo: "T5",
          area: "217.31 m²",
          direccion: "K 1C SUR 4 94 CASA 2",
          codigo: "084330100000002310053000000000",
          manzana: "08433010000000231",
          coords: [[10.847904,-74.771871],[10.847897,-74.771821],[10.847715,-74.771885],[10.847544,-74.771948],[10.847558,-74.771991],[10.847704,-74.771979],[10.847904,-74.771871]]
        },
        {
          nodo: "T6",
          area: "152.16 m²",
          direccion: "K 1C SUR 4 94 CASA 3",
          codigo: "084330100000002310053000000000",
          manzana: "08433010000000231",
          coords: [[10.847704,-74.771979],[10.847558,-74.771991],[10.847572,-74.772033],[10.847721,-74.772023],[10.847919,-74.771948],[10.847904,-74.771871],[10.847704,-74.771979]]
        },
        {
          nodo: "T7",
          area: "314.89 m²",
          direccion: "K 1C SUR 4 94 CASA 4",
          codigo: "084330100000002310053000000000",
          manzana: "08433010000000231",
          coords: [[10.847971,-74.772163],[10.847942,-74.772051],[10.847752,-74.772138],[10.847625,-74.772199],[10.847653,-74.772266],[10.847805,-74.772233],[10.847971,-74.772163]]
        }
      ];

      var renderizarPredios = function (lista) {
        var grupo = L.featureGroup();
        lista.forEach(function (p) {
          var pol = L.polygon(p.coords, {
            color: "#00f0ff",
            weight: 2.4,
            fillColor: "#0066ff",
            fillOpacity: 0.38,
            dashArray: "4, 4"
          });

          pol.bindPopup(
            "<div style='font-family:sans-serif;color:#0b0f19;padding:8px 4px;min-width:210px;line-height:1.4;'>" +
              "<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;'>" +
                "<span style='font-size:10px;font-weight:800;color:#0066ff;letter-spacing:1px;background:rgba(0,102,255,0.1);padding:2px 6px;border-radius:4px;'>IGAC · CTM12</span>" +
                "<span style='font-size:10px;color:#10b981;font-weight:700;'>✓ GEORREFERENCIADO</span>" +
              "</div>" +
              "<div style='font-size:18px;font-weight:800;color:#0f172a;'>PREDIO NODO " + p.nodo + "</div>" +
              "<div style='font-size:12px;color:#475569;margin-bottom:6px;'>📍 " + (p.direccion || "El Tesoro, Malambo") + "</div>" +
              "<div style='background:#f8fafc;padding:6px 8px;border-radius:6px;border:1px solid #e2e8f0;font-size:11px;margin-bottom:6px;'>" +
                "<div><b>Área Oficial:</b> <span style='color:#0f172a;font-weight:700;'>" + p.area + "</span></div>" +
                "<div><b>Manzana:</b> " + (p.manzana || "08433010000000231") + "</div>" +
                (p.codigo ? "<div style='font-family:monospace;font-size:9.5px;color:#64748b;margin-top:2px;'>CP: " + p.codigo.slice(0, 16) + "...</div>" : "") +
              "</div>" +
              "<div style='font-size:10.5px;color:#64748b;'><b>Colindantes:</b> Ajustados automáticamente sobre base oficial.</div>" +
            "</div>"
          );

          pol.on("mouseover", function () {
            this.setStyle({ fillOpacity: 0.75, color: "#ffffff", weight: 3.2 });
          });
          pol.on("mouseout", function () {
            this.setStyle({ fillOpacity: 0.38, color: "#00f0ff", weight: 2.4 });
          });

          grupo.addLayer(pol);
        });

        grupo.addTo(mapaHero);
        mapaHero.fitBounds(grupo.getBounds(), { padding: [30, 30] });
      };

      // Intentar cargar todos los 23 predios desde el JSON oficial; si no, usar la base embebida
      fetch("/static/predios_reales_hero.json")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (datos) {
          if (datos && datos.length) {
            renderizarPredios(datos);
          } else {
            renderizarPredios(prediosRealesBase);
          }
        })
        .catch(function () {
          renderizarPredios(prediosRealesBase);
        });

    } catch (err) {
      console.warn("Leaflet mapa-hero:", err);
    }
  }

  /* ── Tooltips Interactivos y Ayudas Visuales ── */
  d.querySelectorAll("[data-tooltip]").forEach(function (el) {
    el.setAttribute("title", el.dataset.tooltip);
  });
})();

