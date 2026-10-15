#!/usr/bin/env python3
"""Euthyna - descarga TODA la actividad (iniciativas) de una legislatura del Congreso. (version 6)

Fuente: buscador de iniciativas del Congreso (datos abiertos oficiales):
https://www.congreso.es/es/busqueda-de-iniciativas
Solo usa la libreria estandar de Python 3.8+.
Uso:  python3 actualizar_congreso_actividad.py            (legislatura 15 = XV)
      python3 actualizar_congreso_actividad.py 14         (otra legislatura)

Que hace, paso a paso:
 1. Entra en la pagina del buscador (para recibir la "cookie" de sesion, como un navegador).
 2. Pide los resultados de 100 en 100 hasta que una pagina viene con menos de 100.
    Espera 2 segundos entre peticiones (se ejecuta una vez por semana) para no cargar el servidor del Congreso.
 3. Guarda el original sin tocar, comprimido, en crudo/ (con su huella SHA-256).
 4. Genera datos/actividad_legXX.csv (una fila por iniciativa, ordenada por expediente)
    y datos/actividad_legXX_resumen.json (cuantas hay de cada tipo, fecha de descarga).
 5. Si una pagina concreta viene vacia (pasa: el servidor del Congreso a veces falla en una),
    la anota en "paginas_fallidas" y sigue. Si algo grave falla o el resultado es sospechosamente pequeno, NO toca los archivos anteriores.
"""
import csv, gzip, hashlib, http.cookiejar, json, sys, time, urllib.error, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

LEG = sys.argv[1] if len(sys.argv) > 1 else "15"
BASE = "https://www.congreso.es"
PAGINA = BASE + "/es/busqueda-de-iniciativas?p_p_id=iniciativas&_iniciativas_statusOpenData=true"
EXPORT = (BASE + "/es/busqueda-de-iniciativas?p_p_id=iniciativas&p_p_lifecycle=2&p_p_state=normal"
          "&p_p_mode=view&p_p_resource_id=resourceIDopendataExport&p_p_cacheability=cacheLevelPage"
          "&_iniciativas_statusOpenData=true")
RAIZ = Path(__file__).resolve().parent
DATOS = RAIZ / "datos"
CRUDO = RAIZ / "crudo"
CONTACTO = "https://github.com/alethe-ia/Euthyna"
GUARDA = ("PONER_" in CONTACTO)
PAUSA = 2.0   # segundos entre peticiones (antes 1)
MAX_PETICIONES = 800   # tope de seguridad por ejecucion (lo normal son unas 660); si se supera, se para todo
peticiones = 0
UA = {"User-Agent": f"Euthyna/0.5 (proyecto ciudadano; datos abiertos; +{CONTACTO})"}
COLUMNAS = ["id_iniciativa", "codigo_tipo", "legislatura", "titulo", "autor", "fecha_presentado",
            "fecha_calificado", "resultado_tram", "comision_competente", "tipo_tramitacion",
            "tramitacion_seguida", "fase", "iniciativas_origen", "enlaces_bocg", "enlaces_ds"]

class Bloqueado(Exception):
    """El Congreso ha contestado 403 (prohibido) o 429 (demasiadas peticiones): se para TODO, sin insistir."""


jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def pedir(url, datos=None):
    global peticiones
    peticiones += 1
    if peticiones > MAX_PETICIONES:
        raise Bloqueado(f"Tope de {MAX_PETICIONES} peticiones alcanzado en esta ejecucion. Paramos.")
    req = urllib.request.Request(url, headers=UA)
    if datos is not None:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(datos).encode(), headers={
            **UA, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    with opener.open(req, timeout=120) as r:
        return r.read()


def pagina(n):
    datos = {"_iniciativas_legislatura": LEG, "_iniciativas_titulo": "", "_iniciativas_texto": "",
             "_iniciativas_autor": "", "_iniciativas_competencias": "", "_iniciativas_tipo": "",
             "_iniciativas_tramitacion": "", "_iniciativas_expedientes": "", "_iniciativas_hasta": "",
             "_iniciativas_tipoTramitacion": "", "_iniciativas_comisionCompetente": "",
             "_iniciativas_fase": "", "_iniciativas_organo": "", "_iniciativas_fechaDe": "0",
             "_iniciativas_fechaDesde": "", "_iniciativas_fechaHasta": "", "_iniciativas_materias": "",
             "_iniciativas_fileIndex": n, "_iniciativas_fileType": "json",
             "_iniciativas_lastResult": n * 100}
    ultimo = None
    for intento in range(1, 6):          # hasta 5 intentos, esperando mas cada vez
        try:
            texto = pedir(EXPORT, datos).decode("utf-8")   # la red devuelve bytes; los pasamos a texto
            lista = json.loads(texto)
            if not isinstance(lista, list):
                raise ValueError("la respuesta no es una lista")
            return texto, lista
        except Bloqueado:
            raise                        # tope de peticiones: no se reintenta
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):     # nos piden parar: paramos del todo
                raise Bloqueado(f"El Congreso respondio {e.code} en la pagina {n}. Paramos sin insistir.")
            ultimo = e
            print(f"  pagina {n}: intento {intento} fallido ({e})", flush=True)
            time.sleep(5 * intento)
        except Exception as e:           # red caida, JSON roto, etc.
            ultimo = e
            print(f"  pagina {n}: intento {intento} fallido ({e})", flush=True)
            time.sleep(5 * intento)
    raise RuntimeError(f"No se pudo bajar la pagina {n}: {ultimo}")


def main():
    if GUARDA:
        raise RuntimeError("Falta el contacto (CONTACTO) en el script. No se hace nada.")
    try:
        pedir(PAGINA)                     # recibe la cookie de sesion
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise Bloqueado(f"El Congreso respondio {e.code} al entrar en el buscador. Paramos sin insistir.")
        raise
    time.sleep(PAUSA)                     # pausa tambien antes de la primera pagina
    todas, crudas, n = {}, [], 1
    fallidas = []
    while n <= 3000:
        try:
            texto, lista = pagina(n)
        except RuntimeError as e:         # una pagina rota (el servidor devuelve vacio): se anota y se sigue
            print(f"  AVISO: {e}; la salto y la anoto", flush=True)
            fallidas.append(n)
            if len(fallidas) > 20:
                raise RuntimeError("Demasiadas paginas rotas; abortamos.")
            n += 1
            time.sleep(PAUSA)
            continue
        nuevas = 0
        for it in lista:
            if it["id_iniciativa"] not in todas:
                nuevas += 1
            todas[it["id_iniciativa"]] = it
        crudas.append(texto)
        print(f"pagina {n}: {len(lista)} filas ({nuevas} nuevas), total {len(todas)}", flush=True)
        if len(lista) < 100:
            break
        if nuevas == 0:                   # el servidor repite paginas: paramos para no entrar en bucle
            raise RuntimeError(f"La pagina {n} no trajo nada nuevo; abortamos.")
        n += 1
        time.sleep(PAUSA)

    DATOS.mkdir(exist_ok=True); CRUDO.mkdir(exist_ok=True)
    resumen_path = DATOS / f"actividad_leg{LEG}_resumen.json"
    if resumen_path.exists():             # seguro: no aceptar un resultado mucho mas pequeno que el anterior
        antes = json.loads(resumen_path.read_text(encoding="utf-8")).get("total", 0)
        if len(todas) < 0.9 * antes:
            raise RuntimeError(f"Solo {len(todas)} filas frente a {antes} la vez anterior; no guardo nada.")

    crudo = ("[" + ",".join(t.strip()[1:-1] for t in crudas if t.strip() not in ("[]", ""))
             + "]").encode("utf-8")
    sha = hashlib.sha256(crudo).hexdigest()
    (CRUDO / f"actividad_leg{LEG}.json.gz").write_bytes(gzip.compress(crudo, 9, mtime=0))

    filas = sorted(todas.values(), key=lambda x: x["id_iniciativa"])
    with open(DATOS / f"actividad_leg{LEG}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS)
        for it in filas:
            fila = dict(it, codigo_tipo=it["id_iniciativa"].split("/")[0])
            w.writerow([" ".join(str(fila.get(c, "")).split()) for c in COLUMNAS])

    resumen = {"legislatura": LEG, "fuente": PAGINA, "version_script": 6,
               "descargado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "total": len(filas), "sha256_original": sha, "paginas_fallidas": fallidas,
               "por_codigo_tipo": dict(sorted(Counter(r["id_iniciativa"].split("/")[0] for r in filas).items()))}
    resumen_path.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"LISTO: {len(filas)} iniciativas de la legislatura {LEG}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)
