#!/usr/bin/env python3
"""Euthyna - descarga y cuenta las iniciativas de la legislatura actual del Congreso.

Fuente: https://www.congreso.es/es/datos-abiertos (datos abiertos oficiales).
Solo usa la libreria estandar de Python 3.8+. Uso:  python3 actualizar_congreso_iniciativas_legislativas.py   (version 3)

Que hace, paso a paso:
 1. Lee la pagina de iniciativas y encuentra los 4 enlaces JSON (el nombre lleva una
    marca de fecha que cambia, por eso no se puede fijar la URL).
 2. Guarda los archivos originales SIN tocar, con su huella SHA-256 (verificacion).
 3. Calcula recuentos y los guarda en resumen.json / resumen.csv, con la fecha de descarga.
 4. Guarda la lista de normas aprobadas, una por fila, en normas_aprobadas.csv para poder
    revisarla a mano.
 5. Guarda iniciativas.csv: una fila por proyecto/proposicion con el texto OFICIAL completo.
 6. Anota en 'sin_clasificar' todo lo que no sabe clasificar, para revisarlo a mano.
"""
import csv, hashlib, json, re, sys, time, urllib.error, urllib.request
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

PAGINA = "https://www.congreso.es/es/opendata/iniciativas"
BASE = "https://www.congreso.es"
NOMBRES = ["IniciativasLegislativasAprobadas", "ProyectosDeLey",
           "ProposicionesDeLey", "PropuestasDeReforma"]
RAIZ = Path(__file__).resolve().parent
CONTACTO = "https://github.com/alethe-ia/Euthyna"
GUARDA = ("PONER_" in CONTACTO)
UA = {"User-Agent": f"Euthyna/0.4 (proyecto ciudadano; datos abiertos; +{CONTACTO})"}


MAX_PETICIONES = 12   # tope de seguridad por ejecucion (lo normal son 5)
peticiones = 0


def descargar(url):
    global peticiones
    peticiones += 1
    if peticiones > MAX_PETICIONES:
        sys.exit(f"Tope de {MAX_PETICIONES} peticiones alcanzado. Paramos.")
    time.sleep(2)   # pausa de cortesia entre peticiones
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):   # nos piden parar: paramos del todo, sin reintentar
            sys.exit(f"El Congreso respondio {e.code} en {url}. Paramos sin insistir.")
        raise


def limpiar(texto):
    """Quita saltos de linea y espacios repetidos."""
    return re.sub(r"\s+", " ", texto or "").strip()


def registros(datos):
    """El JSON puede ser una lista o un objeto que contiene la lista."""
    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict):
        for v in datos.values():
            if isinstance(v, list):
                return v
    return []


def enlaces_json(html):
    out = {}
    for m in re.finditer(r'href="([^"]*?/opendata/iniciativas/(\w+?)__\d+\.json)"', html):
        href, nombre = m.group(1), m.group(2)
        if nombre in NOMBRES:
            out[nombre] = href if href.startswith("http") else BASE + href
    return out


def clase_fila(titulo):
    """Clasifica cada FILA de aprobadas. Una fila no es una norma.
    Solo cuenta como 'resolucion' o 'correccion' si el titulo EMPIEZA asi
    (asi una ley que menciona 'resoluciones judiciales' no se confunde)."""
    t = limpiar(titulo).lower()
    if t.startswith("corrección de errores") or t.startswith("correccion de errores"):
        return "correccion_de_errores"
    if t.startswith("resolución") or t.startswith("resolucion"):
        if "derogaci" in t:
            return "resolucion_derogacion"
        if "convalidaci" in t:
            return "resolucion_convalidacion"
        return "sin_clasificar"
    return "norma"


def subtipo(titulo):
    """Tipo exacto segun como EMPIEZA el titulo oficial."""
    t = limpiar(titulo).lower()
    for pref, nombre in [("real decreto-ley", "Real Decreto-ley"),
                         ("real decreto legislativo", "Real Decreto Legislativo"),
                         ("ley orgánica", "Ley Orgánica"),
                         ("ley", "Ley"),
                         ("real decreto", "Real Decreto")]:
        if t.startswith(pref):
            return nombre
    return "otro"


def anio(fecha):
    m = re.search(r"(\d{4})", fecha or "")
    return m.group(1) if m else "?"


def resumen_aprobadas(regs):
    filas = Counter(); normas = {}; sin = []; lista = []
    for r in regs:
        tipo = r.get("TIPO", "?")
        titulo = limpiar(r.get("TITULO_LEY"))
        c = clase_fila(titulo)
        filas[(tipo, c)] += 1
        lista.append([tipo, r.get("NUMERO_LEY"), anio(r.get("FECHA_LEY")),
                      r.get("FECHA_LEY"), c, subtipo(titulo), titulo])
        if c == "norma":
            normas[(tipo, r.get("NUMERO_LEY"), anio(r.get("FECHA_LEY")))] = subtipo(titulo)
        elif c == "sin_clasificar":
            sin.append(titulo)
    por_tipo = Counter(t for t, _, _ in normas)
    por_subtipo = Counter(normas.values())
    return ({"filas_total": len(regs),
             "normas_distintas_por_tipo": dict(por_tipo),
             "normas_distintas_por_subtipo_segun_titulo": dict(por_subtipo),
             "filas_por_tipo_y_clase": {f"{t} | {c}": n for (t, c), n in filas.items()},
             "sin_clasificar": sin}, lista)


def situacion_general(texto):
    t = limpiar(texto).lower()
    for clave, nombre in [("cerrado", "Cerrado"), ("concluido", "Cerrado"),
                          ("comisión", "En comisión"), ("pleno", "En el Pleno"),
                          ("senado", "En el Senado"), ("mesa del congreso", "En la Mesa"),
                          ("gobierno", "Pendiente de contestación del Gobierno")]:
        if clave in t:
            return nombre
    return "Otra"


def autores(texto):
    """Un registro puede tener varios autores separados por salto de linea.
    Devuelve el conjunto de 'autores normalizados' (grupos, Senado, comunidades...)."""
    out = set()
    for parte in (texto or "").split("\n"):
        p = limpiar(parte)
        if not p:
            continue
        if re.search(r"\((G[A-Za-z]|GV|GR|GEH|GSUMAR|GMx|GS|GP|GVOX|GJ)", p) or " y " in p and "Diputados" in p:
            out.add("Diputados a título individual (varios grupos)")
        else:
            out.add(p)
    return out


def resumen_tramitacion(regs, nombre=""):
    res = Counter(); sit = Counter(); aut = Counter(); rdl = 0; filas = []
    for r in regs:
        x = limpiar(r.get("RESULTADOTRAMITACION"))
        filas.append([nombre, r.get("LEGISLATURA"), r.get("NUMEXPEDIENTE"),
                      limpiar(r.get("OBJETO")), " | ".join(sorted(autores(r.get("AUTOR") or "?"))),
                      r.get("FECHAPRESENTACION"), limpiar(r.get("TIPOTRAMITACION")),
                      limpiar(r.get("SITUACIONACTUAL")), x])
        res[re.split(r"\s+\d", x)[0] if x else "En tramitación (sin resultado)"] += 1
        sit[situacion_general(r.get("SITUACIONACTUAL"))] += 1
        for a in autores(r.get("AUTOR") or "?"):
            aut[a] += 1
        if re.search(r"procedente del Real Decreto-ley", r.get("OBJETO") or "", re.I):
            rdl += 1
    return ({"total": len(regs), "por_resultado": dict(res),
             "valores_distintos_de_resultado_oficial": sorted({f[8] for f in filas}),
             "por_situacion_general": dict(sit),
             "por_autor_una_vez_por_cada_autor": dict(aut),
             "procedentes_de_real_decreto_ley": rdl}, filas)


def main():
    if GUARDA:
        sys.exit("Falta el contacto (CONTACTO) en el script. No se hace nada.")
    hoy = date.today().isoformat()
    carpeta = RAIZ / "datos" / "originales" / hoy
    carpeta.mkdir(parents=True, exist_ok=True)
    enl = enlaces_json(descargar(PAGINA).decode("utf-8", "replace"))
    faltan = [n for n in NOMBRES if n not in enl]
    if faltan:
        sys.exit(f"No encuentro estos enlaces en la pagina: {faltan}. No se escribe nada.")
    huellas, res, lista, todas = {}, {}, [], []
    for nombre, url in enl.items():
        crudo = descargar(url)
        (carpeta / f"{nombre}.json").write_bytes(crudo)
        huellas[nombre] = {"url": url, "sha256": hashlib.sha256(crudo).hexdigest(), "bytes": len(crudo)}
        regs = registros(json.loads(crudo.decode("utf-8-sig")))
        if nombre == NOMBRES[0]:
            res[nombre], lista = resumen_aprobadas(regs)
        else:
            res[nombre], filas = resumen_tramitacion(regs, nombre)
            todas.extend(filas)
    salida = {"legislatura": "XV (actual)", "fuente": PAGINA, "version_script": 4,
              "descargado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "archivos": huellas, "resumen": res}
    (RAIZ / "datos").mkdir(exist_ok=True)
    (RAIZ / "datos" / "resumen.json").write_text(json.dumps(salida, ensure_ascii=False, indent=2), "utf-8")
    with open(RAIZ / "datos" / "normas_aprobadas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tipo_archivo", "numero", "anio", "fecha", "clase_de_fila", "subtipo_segun_titulo", "titulo"])
        w.writerows(lista)
    with open(RAIZ / "datos" / "iniciativas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["archivo", "legislatura", "expediente", "objeto", "autores", "fecha_presentacion",
                    "tipo_tramitacion", "situacion_actual_oficial", "resultado_oficial"])
        w.writerows(todas)
    with open(RAIZ / "datos" / "resumen.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["archivo", "medida", "valor", "descargado"])
        for nombre, r in res.items():
            for k, v in r.items():
                if isinstance(v, dict):
                    for kk, vv in v.items():
                        w.writerow([nombre, f"{k}: {kk}", vv, hoy])
                elif not isinstance(v, list):
                    w.writerow([nombre, k, v, hoy])
    print("Listo. Resumen en datos/resumen.json, resumen.csv, normas_aprobadas.csv e iniciativas.csv")


if __name__ == "__main__":
    main()
