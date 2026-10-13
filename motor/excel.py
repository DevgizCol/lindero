# -*- coding: utf-8 -*-
"""Lectura de los Excel del cliente: cada uno llega con encabezados distintos."""
from __future__ import annotations

import re
import unicodedata

import openpyxl

# campo canónico -> patrones de encabezado (sobre el texto normalizado), por orden de preferencia
PATRONES = {
    "NODO": [
        r"^NODO(S)?$", r"^LOTE(S)?( ?N[°O\.]?)?$", r"^PREDIO(S)?$", r"^ID(_PREDIO|_LOTE)?$",
        r"^ID$", r"^PUNTO$", r"^POLIGONO$", r"^MANZANA[ _]LOTE$", r"^MZ[ _]LOTE$", r"^CODIGO_LOTE$",
        r"^E\.? ?(MB|II+|I+ ?K)( OK)?$", r"^E\.? .*OK$", r"^ENCUESTA$", r"^NUMERO$", r"^N.? DE LOTE$",
        r"^LOTE NRO$", r"^LOTE NO\.?$", r"^PLANO$", r"^(N|NO|NUMERO)\.?\s*(DE\s*)?LOTE$"
    ],
    "NOMBRE_BEN": [
        r"^NOMBRE_BEN$", r"^(NOMBRE )?BENEFICIARIO( 1)?$", r"^PROPIETARIO( 1)?$", r"^TITULAR( 1)?$",
        r"^OCUPANTE( 1)?$", r"^NOMBRE( COMPLETO)?$", r"^ENCUESTADO$", r"^NOMBRE BENEFICIARIO 1$",
        r"^INTERESADO$", r"^RESPONSABLE$", r"^NOMBRE DE PROPIETARIO$"
    ],
    "NO_DE_IDEN": [
        r"^NO_DE_IDEN$", r"^CEDULA( BENEFICIARIO)?( 1)?$", r"^IDENTIFICACION( C\.?C\.?)?( 1)?$",
        r"^DOC(UMENTO)?( DE)? IDENTIDAD$", r"^C\.?C\.?$", r"^CC$", r"^NUMERO DE CEDULA$", r"^NIT$",
        r"^CEDULA DE CIUDADANIA$", r"^DOCUMENTO$"
    ],
    "NOMENCLATU": [
        r"^NOMENCLATU(RA)?$", r"^NOMENCATURA$", r"^DIRECCION( DEL PREDIO| ACTUAL)?$", r"^DIR\.?$",
        r"^UBICACION( DEL PREDIO)?$", r"^PLACA( DOMICILIARIA)?$", r"^DIRECCION DE TERRENO$",
        r"^NOMENCLATURA VIAL$", r"^DIR PREDIO$", r"^DIRECCION DOMICILIARIA$"
    ],
    "CODIGO": [
        r"^CODIGO$", r"^CODIGO PREDIAL$", r"^REF(ERENCIA)?\.? ?_?CAT(ASTRAL)?\.?( NACIONAL| VUR)?$",
        r"^PREDIAL$", r"^N.? PREDIAL$", r"^CEDULA CATASTRAL$", r"^CHIP$", r"^NUMERO CATASTRAL$",
        r"^NUMERO PREDIAL$", r"^NUMERO PREDIAL NACIONAL$", r"^NPN$", r"^CODIGO CATASTRAL$"
    ],
    "BARRIO_URB": [
        r"^BARRIO_URB$", r"^BARRIO( ?/ ?URBANIZACION)?$", r"^URBANIZACION$", r"^SECTOR$", r"^VEREDA$",
        r"^LOCALIDAD$", r"^BARRIO / COMUNA$"
    ],
    "_CELULAR": [r"^_?CELULAR$", r"^TELEFONO$", r"^MOVIL$", r"^CONTACTO$", r"^TEL$", r"^WHATSAPP$", r"^NUMERO CELULAR$"],
    "NOMBRE_B_1": [r"^NOMBRE_B_1$", r"^(NOMBRE )?BENEFICIARIO 2$", r"^OCUPANTE 2$", r"^PROPIETARIO 2$"],
    "NO_DE_ID_1": [r"^NO_DE_ID_1$", r"^CEDULA( BENEFICIARIO)? 2$", r"^IDENTIFICACION( C\.?C\.?)? 2$"],
}


def norm_encabezado(h) -> str:
    t = unicodedata.normalize("NFKD", str(h or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^\w\s\.\_\-\/]", " ", t)
    return re.sub(r"\s+", " ", t.upper().replace("\n", " ")).strip()


def detectar_columnas(encabezados) -> dict:
    """{campo canónico: índice de columna}. Si hay dos columnas de dirección, la segunda trae el complemento."""
    hs = [norm_encabezado(h) for h in encabezados]
    out = {}
    for campo, pats in PATRONES.items():
        for pat in pats:
            idx = [i for i, h in enumerate(hs) if re.match(pat, h) and i not in out.values()]
            if idx:
                out[campo] = idx[0]
                if campo == "NOMENCLATU" and len(idx) > 1:
                    out["_DIRECCION_COMPLETA"] = idx[1]
                break
    if "NOMENCLATU" in out and "_DIRECCION_COMPLETA" not in out:
        otros = [i for i, h in enumerate(hs) if re.match(r"^DIRECCION", h) and i != out["NOMENCLATU"]]
        if otros:
            out["_DIRECCION_COMPLETA"] = otros[0]
    return out


def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    # Limpiar caracteres invisibles, espacios no separables y saltos de línea
    s = str(v).replace("\u00a0", " ").replace("\ufeff", "").replace("\u200b", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return "" if s.lower() in ("#n/a", "none", "nan", "n/a", "null") else s


def leer_excel(ruta, hojas=None) -> list[dict]:
    """Filas del Excel con campos canónicos. Cada fila conserva hoja y número de fila de origen."""
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    filas = []
    for ws in wb.worksheets:
        if hojas and ws.title not in hojas:
            continue
        it = ws.iter_rows(values_only=True)
        enc, n_enc = None, 0
        for n_enc, row in enumerate(it, start=1):
            if row and sum(1 for c in row if c not in (None, "")) >= 3:
                enc = row
                break
        if enc is None:
            continue
        cols = detectar_columnas(enc)
        if "NOMENCLATU" not in cols and "NODO" not in cols:
            continue
        for k, row in enumerate(it, start=n_enc + 1):
            if not row or all(c in (None, "") for c in row):
                continue
            f = {c: _txt(row[i]) if i < len(row) else "" for c, i in cols.items()}
            if not f.get("NOMENCLATU") and not f.get("NODO"):
                continue
            f["_HOJA"], f["_FILA"] = ws.title, k
            if not f.get("BARRIO_URB") and len(wb.worksheets) > 1:
                f["BARRIO_URB"] = ws.title.strip()
            filas.append(f)
    return filas
