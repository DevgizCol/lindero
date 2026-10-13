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
  
  // Evita que soltar un archivo por fuera de la caja abra el archivo en una pestaña y borre el formulario
  window.addEventListener("dragover", function (e) { e.preventDefault(); }, false);
  window.addEventListener("drop", function (e) { e.preventDefault(); }, false);

  d.querySelectorAll(".soltar").forEach(function (zona) {
    var entrada = zona.querySelector("input[type=file]"), titulo = zona.querySelector("b"), detalle = zona.querySelector("small"),
      accion = zona.querySelector(".accion"), t0 = titulo ? titulo.textContent : "", d0 = detalle ? detalle.textContent : "";
    
    var pintar = function () {
      if (!entrada) return;
      var fs = entrada.files;
      if (!fs || !fs.length) {
        zona.classList.remove("lleno");
        if (titulo) titulo.textContent = t0;
        if (detalle) detalle.textContent = d0;
        if (accion) accion.textContent = "Elegir";
        return;
      }
      var peso = 0;
      for (var i = 0; i < fs.length; i++) peso += fs[i].size;
      zona.classList.add("lleno");
      zona.classList.remove("error-falta");
      if (titulo) titulo.textContent = fs.length === 1 ? fs[0].name : fs.length + " archivos seleccionados";
      if (detalle) detalle.textContent = legible(peso) + " · Listo para procesar";
      if (accion) accion.textContent = "Cambiar";
    };

    if (entrada) {
      entrada.addEventListener("change", pintar);
    }

    // Accesibilidad por teclado: Enter o Espacio abre selector de archivos
    zona.setAttribute("tabindex", "0");
    zona.addEventListener("keydown", function (e) {
      if ((e.key === "Enter" || e.key === " ") && entrada) {
        e.preventDefault();
        entrada.click();
      }
    });
    
    // Soporte Drag and Drop completo con prevención de apertura de pestaña
    ["dragenter", "dragover"].forEach(function (ev) {
      zona.addEventListener(ev, function (e) {
        e.preventDefault();
        e.stopPropagation();
        zona.classList.add("sobre");
      });
    });
    ["dragleave"].forEach(function (ev) {
      zona.addEventListener(ev, function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (!zona.contains(e.relatedTarget)) {
          zona.classList.remove("sobre");
        }
      });
    });
    zona.addEventListener("drop", function (e) {
      e.preventDefault();
      e.stopPropagation();
      zona.classList.remove("sobre");
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length && entrada) {
        try {
          entrada.files = e.dataTransfer.files;
        } catch (err) {
          try {
            var dt = new DataTransfer();
            for (var fi = 0; fi < e.dataTransfer.files.length; fi++) dt.items.add(e.dataTransfer.files[fi]);
            entrada.files = dt.files;
          } catch (e2) {}
        }
        pintar();
        try { entrada.dispatchEvent(new Event("change", { bubbles: true })); } catch (e3) {}
      }
    });
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
        var c = campos[k];
        if (!c.checkValidity()) {
          var z = c.closest(".soltar");
          if (z) {
            z.classList.add("error-falta");
            z.scrollIntoView({ behavior: "smooth", block: "center" });
            setTimeout(function () { z.classList.remove("error-falta"); }, 2800);
          }
          try { c.reportValidity(); } catch (e) {}
          return false;
        }
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

  /* ── Visor Topográfico y Catastral CAD de Alta Precisión (Leaflet + Manzana 231) ── */
  var elMapa = d.getElementById("mapa-hero");
  if (elMapa && typeof L !== "undefined") {
    try {
      var mapaHero = L.map("mapa-hero", {
        center: [10.84772, -74.77172],
        zoom: 19,
        zoomControl: true,
        scrollWheelZoom: false,
        attributionControl: false
      });

      // Capas base: Ortofoto Satelital Esri HD y Modo CAD Oscuro
      var capaSatelite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 20
      }).addTo(mapaHero);

      var capaPlanoCAD = L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        maxZoom: 20,
        subdomains: "abcd"
      });

      // Escala gráfica métrica oficial
      L.control.scale({ metric: true, imperial: false, position: "bottomleft" }).addTo(mapaHero);

      // Grupos de capas vectoriales independientes
      var grupoManzana = L.featureGroup().addTo(mapaHero);
      var grupoTerrenos = L.featureGroup().addTo(mapaHero);
      var grupoVias = L.featureGroup().addTo(mapaHero);
      var grupoPlacas = L.featureGroup().addTo(mapaHero);
      var grupoPoligonos = L.featureGroup().addTo(mapaHero);
      var grupoDeslinde = L.featureGroup().addTo(mapaHero);
      var grupoCotas = L.featureGroup().addTo(mapaHero);
      var grupoVertices = L.featureGroup().addTo(mapaHero);
      var grupoEtiquetas = L.featureGroup().addTo(mapaHero);

      // Geodesia y transformación a CTM12
      var distMetros = function (c1, c2) {
        var R = 6371000;
        var dLat = (c2[0] - c1[0]) * Math.PI / 180;
        var dLon = (c2[1] - c1[1]) * Math.PI / 180;
        var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(c1[0] * Math.PI / 180) * Math.cos(c2[0] * Math.PI / 180) *
                Math.sin(dLon / 2) * Math.sin(dLon / 2);
        var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return (R * c).toFixed(2);
      };

      var centroPunto = function (c1, c2) {
        return [(c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2];
      };

      var aCTM12 = function (lat, lon) {
        var dN = (lat - 10.847861) * 110574;
        var dE = (lon - (-74.771648)) * 109200;
        var n = 1684218.40 + dN;
        var e = 4872204.15 + dE;
        return {
          norte: n.toLocaleString("es-CO", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
          este: e.toLocaleString("es-CO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        };
      };

      // ── CARGAR CAPAS OFICIALES DE LA BASE CATASTRAL (MANZANA 231) ──
      fetch("/static/base_manzana_231.json")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (base) {
          if (!base) return;

          // 1. Manzana Catastral
          if (base.manzana && base.manzana.features) {
            L.geoJSON(base.manzana, {
              style: {
                color: "#38bdf8",
                weight: 1.4,
                dashArray: "5, 4",
                fillColor: "#0284c7",
                fillOpacity: 0.04
              }
            }).addTo(grupoManzana);
          }

          // 2. Terrenos Catastrales Vecinos con Etiquetas Sutiles
          if (base.terrenos && base.terrenos.features) {
            base.terrenos.features.forEach(function (feat) {
              var poly = L.geoJSON(feat, {
                style: {
                  color: "#64748b",
                  weight: 0.85,
                  opacity: 0.65,
                  fillColor: "#1e293b",
                  fillOpacity: 0.18
                }
              });

              var loteNum = feat.properties.lote_num || "";
              poly.bindTooltip("<b>Predio Oficial IGAC " + loteNum + "</b><br>Código: " + feat.properties.codigo, { sticky: true });
              grupoTerrenos.addLayer(poly);

              // Etiqueta sutil de 4 dígitos (como en el plano de certificación)
              if (loteNum && feat.geometry && feat.geometry.coordinates) {
                var coords = feat.geometry.coordinates[0];
                if (coords && coords.length) {
                  var cX = 0, cY = 0, total = coords.length;
                  coords.forEach(function (pt) { cX += pt[0]; cY += pt[1]; });
                  var centro = [cY / total, cX / total];
                  // Omitir etiqueta sobre T1/T2 para no superponer
                  if (!(centro[0] > 10.8474 && centro[0] < 10.8479 && centro[1] > -74.7719 && centro[1] < -74.7715)) {
                    var loteIcon = L.divIcon({
                      className: "lote-cad-label",
                      html: "<span>" + loteNum + "</span>",
                      iconSize: [26, 12],
                      iconAnchor: [13, 6]
                    });
                    grupoTerrenos.addLayer(L.marker(centro, { icon: loteIcon }));
                  }
                }
              }
            });
          }

          // 3. Vías y Calles Adyacentes (Ejes Viales Oficiales)
          if (base.vias && base.vias.features) {
            base.vias.features.forEach(function (feat) {
              var viaLine = L.geoJSON(feat, {
                style: {
                  color: "#f43f5e",
                  weight: 1.6,
                  opacity: 0.72,
                  dashArray: "3, 3"
                }
              });
              viaLine.bindTooltip("<b>Vía Oficial:</b> " + (feat.properties.texto || "Vía Pública"), { sticky: true });
              grupoVias.addLayer(viaLine);

              var txt = feat.properties.texto;
              if (txt && feat.geometry && feat.geometry.coordinates) {
                var coordsLine = feat.geometry.coordinates;
                if (coordsLine.length >= 2) {
                  var midIdx = Math.floor(coordsLine.length / 2);
                  var midPt = [coordsLine[midIdx][1], coordsLine[midIdx][0]];
                  var viaIcon = L.divIcon({
                    className: "via-cad-label",
                    html: "<span>" + txt + "</span>",
                    iconSize: [70, 14],
                    iconAnchor: [35, 7]
                  });
                  grupoVias.addLayer(L.marker(midPt, { icon: viaIcon }));
                }
              }
            });
          }

          // 4. Placas Domiciliarias
          if (base.placas && base.placas.features) {
            base.placas.features.forEach(function (feat) {
              var txt = feat.properties.texto;
              if (txt && feat.geometry && feat.geometry.coordinates) {
                var pt = feat.geometry.coordinates;
                var latLng = Array.isArray(pt[0]) ? [pt[0][1], pt[0][0]] : [pt[1], pt[0]];
                var placaIcon = L.divIcon({
                  className: "placa-cad-label",
                  html: "<span>" + txt + "</span>",
                  iconSize: [28, 12],
                  iconAnchor: [14, 6]
                });
                grupoPlacas.addLayer(L.marker(latLng, { icon: placaIcon }));
              }
            });
          }
        })
        .catch(function (e) { console.warn("base_manzana_231:", e); });

      // ── PREDIOS CONTINUOS T1 Y T2 DEL LEVANTAMIENTO TOPOGRÁFICO ──
      var predioT1 = {
        nodo: "T1",
        color: "#00f0ff",
        fillColor: "#00f0ff",
        area: "334.18 m²",
        perimetro: "102.40 m",
        direccion: "K 1C SUR 4 94 CASA 1",
        manzana: "08433010000000231",
        puntos: [
          { id: "P1", coords: [10.847861, -74.771648], colindante: "Frente Vía / Carrera 1C Sur" },
          { id: "P2", coords: [10.847841, -74.771591], colindante: "Costado Este / Predio T3 (0053)" },
          { id: "P3", coords: [10.847707, -74.771644], colindante: "Costado Este / Predio T4 (0053)" },
          { id: "P4", coords: [10.847463, -74.771737], colindante: "Fondo Sur / Límite Manzana" },
          { id: "P5", coords: [10.847489, -74.771807], colindante: "Fondo Sur / Límite Manzana" },
          { id: "P6", coords: [10.847695, -74.771722], colindante: "Lindero Común Divisorio Lote T2" }
        ]
      };

      var predioT2 = {
        nodo: "T2",
        color: "#10b981",
        fillColor: "#10b981",
        area: "227.52 m²",
        perimetro: "88.75 m",
        direccion: "K 1C SUR 4 94 CASA 1-A",
        manzana: "08433010000000231",
        puntos: [
          { id: "P7", coords: [10.847868, -74.771692], colindante: "Frente Vía / Carrera 1C Sur" },
          { id: "P1", coords: [10.847861, -74.771648], colindante: "Lindero Común Divisorio Lote T1" },
          { id: "P6", coords: [10.847695, -74.771722], colindante: "Lindero Común Divisorio Lote T1" },
          { id: "P5", coords: [10.847489, -74.771807], colindante: "Fondo Sur / Límite Manzana" },
          { id: "P8", coords: [10.847508, -74.771849], colindante: "Costado Oeste / Predio T5 (0053)" },
          { id: "P9", coords: [10.847716, -74.771767], colindante: "Costado Oeste / Predio T5 (0053)" }
        ]
      };

      var predios = [predioT1, predioT2];
      var verticesRegistrados = {};
      var filasTabla = [];

      predios.forEach(function (pred) {
        var coordsPoli = pred.puntos.map(function (p) { return p.coords; });
        coordsPoli.push(pred.puntos[0].coords);

        // 1. Polígono del Predio
        var pol = L.polygon(coordsPoli, {
          color: pred.color,
          weight: 2.6,
          fillColor: pred.fillColor,
          fillOpacity: 0.22
        });

        pol.bindPopup(
          "<div style='font-family:sans-serif;color:#0b0f19;padding:6px;min-width:220px;line-height:1.4;'>" +
            "<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;'>" +
              "<span style='font-size:10px;font-weight:800;color:#0066ff;background:rgba(0,102,255,0.1);padding:2px 6px;border-radius:4px;'>IGAC · CTM12</span>" +
              "<span style='font-size:10px;color:#10b981;font-weight:700;'>✓ CONTINUO CERTIFICADO</span>" +
            "</div>" +
            "<div style='font-size:17px;font-weight:800;color:#0f172a;'>LOTE " + pred.nodo + "</div>" +
            "<div style='font-size:12px;color:#475569;margin-bottom:6px;'>📍 " + pred.direccion + "</div>" +
            "<div style='background:#f8fafc;padding:8px;border-radius:6px;border:1px solid #e2e8f0;font-size:11.5px;'>" +
              "<div><b>Área de Terreno:</b> <span style='color:#0f172a;font-weight:700;'>" + pred.area + "</span></div>" +
              "<div><b>Perímetro:</b> " + pred.perimetro + "</div>" +
              "<div><b>Manzana:</b> " + pred.manzana + "</div>" +
            "</div>" +
          "</div>"
        );

        pol.on("mouseover", function () { this.setStyle({ fillOpacity: 0.45, weight: 3.2 }); });
        pol.on("mouseout", function () { this.setStyle({ fillOpacity: 0.22, weight: 2.6 }); });
        grupoPoligonos.addLayer(pol);

        // 2. Cotas Métricas Sutiles
        for (var i = 0; i < pred.puntos.length; i++) {
          var pActual = pred.puntos[i];
          var pSig = pred.puntos[(i + 1) % pred.puntos.length];
          var dM = distMetros(pActual.coords, pSig.coords);
          var mPoint = centroPunto(pActual.coords, pSig.coords);

          var tramoId = [pActual.id, pSig.id].sort().join("-");
          var esComun = tramoId === "P1-P6" || tramoId === "P5-P6";

          if (!verticesRegistrados["cota_" + tramoId]) {
            verticesRegistrados["cota_" + tramoId] = true;
            var claseCota = esComun ? "cota-label dorado" : (pred.nodo === "T1" ? "cota-label" : "cota-label verde");
            var cotaIcon = L.divIcon({
              className: "marcador-cota-div",
              html: "<span class='" + claseCota + "'>" + dM + " m</span>",
              iconSize: [40, 14],
              iconAnchor: [20, 7]
            });
            grupoCotas.addLayer(L.marker(mPoint, { icon: cotaIcon }));
          }

          filasTabla.push({
            vertice: pActual.id,
            tramo: pActual.id + " → " + pSig.id,
            distancia: dM + " m",
            coords: aCTM12(pActual.coords[0], pActual.coords[1]),
            colindancia: pActual.colindante,
            lote: pred.nodo
          });
        }

        // 3. Vértices Topográficos P1..P9
        pred.puntos.forEach(function (pt) {
          if (!verticesRegistrados["v_" + pt.id]) {
            verticesRegistrados["v_" + pt.id] = true;
            var ctm = aCTM12(pt.coords[0], pt.coords[1]);
            var vIcon = L.divIcon({
              className: "marcador-vertice-div",
              html: "<div class='vertice-icono' title='Vértice " + pt.id + "'>" + pt.id.replace("P", "") + "</div>",
              iconSize: [14, 14],
              iconAnchor: [7, 7]
            });
            var markerV = L.marker(pt.coords, { icon: vIcon });
            markerV.bindTooltip(
              "<b>Vértice " + pt.id + " (CTM12)</b><br>Norte: " + ctm.norte + " m<br>Este: " + ctm.este + " m",
              { direction: "top", offset: [0, -8] }
            );
            grupoVertices.addLayer(markerV);
          }
        });

        // 4. Etiqueta Sutil del Lote
        var cLat = coordsPoli.reduce(function (s, c) { return s + c[0]; }, 0) / coordsPoli.length;
        var cLon = coordsPoli.reduce(function (s, c) { return s + c[1]; }, 0) / coordsPoli.length;
        var etiquetaIcon = L.divIcon({
          className: "marcador-etiqueta-div",
          html: "<div class='etiqueta-lote-div" + (pred.nodo === "T2" ? " verde" : "") + "'><b>LOTE " + pred.nodo + "</b><span>" + pred.area + "</span></div>",
          iconSize: [78, 28],
          iconAnchor: [39, 14]
        });
        grupoEtiquetas.addLayer(L.marker([cLat, cLon], { icon: etiquetaIcon }));
      });

      // 5. Línea de Deslinde Común (Colindancia T1 - T2)
      var coordsDeslinde = [
        [10.847861, -74.771648], // P1
        [10.847695, -74.771722], // P6
        [10.847489, -74.771807]  // P5
      ];
      var d1 = parseFloat(distMetros(coordsDeslinde[0], coordsDeslinde[1]));
      var d2 = parseFloat(distMetros(coordsDeslinde[1], coordsDeslinde[2]));
      var totalDeslinde = (d1 + d2).toFixed(2);

      var lineaDeslinde = L.polyline(coordsDeslinde, {
        color: "#f59e0b",
        weight: 3.5,
        dashArray: "7, 5",
        opacity: 0.95
      });
      lineaDeslinde.bindTooltip(
        "<b>📐 Deslinde Común T1 ↔ T2</b><br>Longitud divisoria: " + totalDeslinde + " m",
        { sticky: true }
      );
      grupoDeslinde.addLayer(lineaDeslinde);

      // 6. Rellenar Tabla del Cuadro de Construcción
      var tablaBody = d.getElementById("tabla-construccion-body");
      if (tablaBody) {
        var htmlTabla = "";
        filasTabla.forEach(function (f) {
          htmlTabla += "<tr>" +
            "<td><strong style='color:#00f0ff;'>" + f.vertice + "</strong> <span style='font-size:0.6rem;color:#64748b;'>(" + f.lote + ")</span></td>" +
            "<td>" + f.tramo + "</td>" +
            "<td><strong>" + f.distancia + "</strong></td>" +
            "<td>" + f.coords.norte + "</td>" +
            "<td>" + f.coords.este + "</td>" +
            "<td style='color:#94a3b8;font-size:0.62rem;'>" + f.colindancia + "</td>" +
          "</tr>";
        });
        tablaBody.innerHTML = htmlTabla;
      }

      // 7. Encuadre Óptimo de Zoom en los Predios T1 y T2
      var boundsLotes = grupoPoligonos.getBounds();
      mapaHero.fitBounds(boundsLotes, { padding: [35, 35], maxZoom: 19 });

      // Botones de Enfoque de Zoom
      var btnEnfocarLotes = d.getElementById("btn-enfocar-lotes");
      var btnEnfocarManzana = d.getElementById("btn-enfocar-manzana");

      if (btnEnfocarLotes) {
        btnEnfocarLotes.addEventListener("click", function () {
          btnEnfocarLotes.classList.add("activo");
          if (btnEnfocarManzana) btnEnfocarManzana.classList.remove("activo");
          mapaHero.fitBounds(boundsLotes, { padding: [35, 35], maxZoom: 19 });
        });
      }

      if (btnEnfocarManzana) {
        btnEnfocarManzana.addEventListener("click", function () {
          btnEnfocarManzana.classList.add("activo");
          if (btnEnfocarLotes) btnEnfocarLotes.classList.remove("activo");
          var bMz = grupoManzana.getBounds();
          if (bMz.isValid()) mapaHero.fitBounds(bMz, { padding: [20, 20] });
          else mapaHero.setView([10.84772, -74.77172], 18);
        });
      }

      // Control de Capas Independiente
      var bindToggle = function (id, capa) {
        var el = d.getElementById(id);
        if (el) {
          el.addEventListener("change", function () {
            if (this.checked) mapaHero.addLayer(capa);
            else mapaHero.removeLayer(capa);
          });
        }
      };

      var chkSat = d.getElementById("chk-capa-satelite");
      if (chkSat) {
        chkSat.addEventListener("change", function () {
          if (this.checked) {
            mapaHero.removeLayer(capaPlanoCAD);
            mapaHero.addLayer(capaSatelite);
          } else {
            mapaHero.removeLayer(capaSatelite);
            mapaHero.addLayer(capaPlanoCAD);
          }
        });
      }

      bindToggle("chk-capa-terrenos", grupoTerrenos);
      bindToggle("chk-capa-vias", grupoVias);
      bindToggle("chk-capa-placas", grupoPlacas);
      bindToggle("chk-capa-cotas", grupoCotas);
      bindToggle("chk-capa-vertices", grupoVertices);
      bindToggle("chk-capa-deslinde", grupoDeslinde);

    } catch (err) {
      console.warn("Leaflet visor-topografico:", err);
    }
  }


  /* ── Tooltips Interactivos y Ayudas Visuales ── */
  d.querySelectorAll("[data-tooltip]").forEach(function (el) {
    el.setAttribute("title", el.dataset.tooltip);
  });
})();

