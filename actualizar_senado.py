#!/usr/bin/env python3
"""Euthyna - descarga los datos abiertos del Senado (legislatura XV) SIN tocarlos.

Fuente: https://www.senado.es/web/relacionesciudadanos/datosabiertos/  (licencia CC-BY 4.0)
Solo usa la libreria estandar de Python 3.8+.   Uso:  python3 actualizar_senado.py [legislatura]

Que hace, paso a paso:
 1. Descarga la lista de iniciativas legislativas (tipoFich=9) y la guarda tal cual.
 2. Descarga la ficha de cada ley (tipos 621 ley ordinaria, 624 organica, 625 otras).
 3. Descarga el XML de cada sesion plenaria con votaciones (ses_N.xml).
    Solo baja las sesiones nuevas: las ya guardadas no se piden otra vez.
    Las sesiones que el Senado no publica devuelven error 500: se saltan sin parar.
    Las sesiones ya descargadas NO se vuelven a bajar (el original no se toca).
 4. Guarda la huella SHA-256 de cada fichero en datos/senado/manifiesto.json,
    con la fecha de descarga y la fuente (la licencia pide citar fuente y fecha).
 5. Si un fichero nuevo pesa menos de la mitad que el que ya tenias, NO lo sobrescribe
    y lo anota en 'avisos' (puede ser una descarga rota).
Normas del robots.txt del Senado (leido el 5 oct 2026): espera de 60 segundos entre peticiones y visitas
solo entre las 02:00 y las 06:00 (hora de Madrid). Este script las cumple: pausa de 60 s, se niega a
empezar fuera de ese horario y se para solo cuando se acaba la ventana (continua la noche siguiente,
porque no vuelve a pedir lo que ya tiene). Solo usa rutas permitidas (datos abiertos oficiales).
Los originales van a datos/senado/originales/ (se conservan en el repositorio, asi cada dia solo se baja lo nuevo); el procesado (sin nombres de personas) es otro paso.
"""
import hashlib, json, os, re, sys, time, urllib.error, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

LEGIS = sys.argv[1] if len(sys.argv) > 1 else "15"
BASE = "https://www.senado.es"
FICH = BASE + "/web/ficopendataservlet"
RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "datos" / "senado"
CRUDO = SALIDA / "originales" / f"legis{LEGIS}"   # dentro de datos/ para que GitHub los conserve entre dias
CONTACTO = "https://github.com/alethe-ia/Euthyna"
GUARDA = ("PONER_" in CONTACTO)
UA = {"User-Agent": f"Mozilla/5.0 (compatible; Euthyna/0.4; proyecto ciudadano de datos abiertos CC-BY 4.0; +{CONTACTO})",
      "Accept": "application/xml,text/xml,*/*;q=0.8", "Accept-Language": "es-ES,es;q=0.9"}
TIPOS_LEY = {"621", "624", "625"}
PAUSA = 60.0         # robots.txt del Senado: Crawl-delay 60 (un minuto entre peticiones)
FALLOS_SEGUIDOS = 6   # tras la ultima sesion buena, cuantos huecos seguidos se toleran
VENTANA = (2, 6)      # robots.txt del Senado: Visit-time 0200-0600 (hora de Madrid)
REFRESCO_FICHAS_DIAS = 7   # las fichas de las leyes se vuelven a pedir como mucho una vez por semana
MADRID = ZoneInfo("Europe/Madrid")

avisos = []
cortado = False
bloqueado = False     # el Senado ha contestado 403/429: se para todo
BLOQUEO_DIAS = 7      # tras un 403/429 no se vuelve a pedir nada en 7 dias (revisar a mano)
MAX_PETICIONES = 200  # tope de seguridad por ejecucion (la primera descarga completa son unas 120)
peticiones = 0
YA_HECHO_HORAS = 20   # si la ultima descarga completa fue hace menos de 20 h, los turnos siguientes no piden nada


def dentro_de_horario():
    h = datetime.now(MADRID).hour
    return VENTANA[0] <= h < VENTANA[1] or os.environ.get("EUTHYNA_FUERA_DE_HORARIO") == "1"


def esperar():
    """Pausa entre peticiones (la que pide el Senado)."""
    time.sleep(PAUSA)


def reciente(manifiesto_previo, ruta, dias):
    """True si ese fichero se descargo hace menos de 'dias' dias (segun el manifiesto)."""
    f = manifiesto_previo.get(str(ruta.relative_to(RAIZ)), {}).get("descargado_utc")
    if not f or not ruta.exists():
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(f) < timedelta(days=dias)


def pedir(url, intentos=4):
    """Devuelve bytes, o None si el servidor dice que no existe (404/500). Reintenta si falla la red.
    Si contesta 403 o 429 (prohibido / demasiadas peticiones) NO reintenta: marca 'bloqueado' y se para todo."""
    global bloqueado, cortado, peticiones
    for i in range(intentos):
        if peticiones >= MAX_PETICIONES:
            cortado = True
            avisos.append(f"Tope de {MAX_PETICIONES} peticiones alcanzado en esta ejecucion. Se para; sigue la noche siguiente.")
            return None
        peticiones += 1
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 500):      # el Senado usa 500 para "no existe"
                return None
            if e.code in (403, 429):
                bloqueado = True
                avisos.append(f"El Senado respondio {e.code} en {url}. Se detiene todo.")
                return None
            err = f"HTTP {e.code} {e.reason}"
        except Exception as e:             # red caida, tiempo agotado...
            err = f"{type(e).__name__}: {e}"
        print(f"  intento {i + 1} fallido en {url}: {err}", flush=True)
        time.sleep(PAUSA)          # tambien entre reintentos: el Senado pide 60 s entre peticiones
        if i < intentos - 1 and not dentro_de_horario():   # no reintentar pasadas las 06:00
            cortado = True
            avisos.append(f"Se acabo la ventana horaria del Senado antes de reintentar {url}: {err}")
            return None
    avisos.append(f"No se pudo bajar {url}: {err}")
    return None


def guardar(ruta, crudo, manifiesto, url):
    """Escribe el original y anota su huella. No sobrescribe si el nuevo es sospechosamente pequeno."""
    if ruta.exists() and len(crudo) < ruta.stat().st_size / 2:
        avisos.append(f"{ruta.name}: el nuevo pesa {len(crudo)} B y el actual {ruta.stat().st_size} B; no se sobrescribe")
        return False
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(crudo)
    manifiesto[str(ruta.relative_to(RAIZ))] = {
        "url": url, "sha256": hashlib.sha256(crudo).hexdigest(), "bytes": len(crudo),
        "descargado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return True


def leyes_de(xml_bytes):
    """(tipo, numero) de las iniciativas que son leyes."""
    out = []
    for it in ET.fromstring(xml_bytes).iter("iniciativa"):
        t = (it.findtext("tipoExpediente") or "").strip()
        n = (it.findtext("numeroExpediente") or "").strip()
        if t in TIPOS_LEY and n:
            out.append((t, n))
    return out


def main():
    global cortado
    if GUARDA:
        sys.exit("Falta el contacto (CONTACTO) en el script. No se hace nada.")
    if not dentro_de_horario():
        print("Fuera del horario que pide el Senado (02:00-06:00, hora de Madrid). No se hace nada. "
              "(Para una prueba puntual: EUTHYNA_FUERA_DE_HORARIO=1)")
        return   # no es un error: GitHub a veces retrasa las ejecuciones programadas
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta_m = SALIDA / "manifiesto.json"
    previo = json.loads(ruta_m.read_text("utf-8")) if ruta_m.exists() else {}
    previos = previo.get("archivos", {})
    no_publicadas = previo.get("sesiones_no_publicadas", {})   # {"20": "2026-10-05", ...}
    manifiesto = {}
    ahora = datetime.now(timezone.utc)
    marca = previo.get("bloqueado_utc")
    if marca and ahora - datetime.fromisoformat(marca) < timedelta(days=BLOQUEO_DIAS):
        sys.exit(f"El Senado contesto 403/429 el {marca}. No se pide nada durante {BLOQUEO_DIAS} dias: hay que revisarlo a mano "
                 "(borrar 'bloqueado_utc' de datos/senado/manifiesto.json solo cuando se haya entendido el motivo).")
    ult = previo.get("ultima_descarga_utc")
    if previo.get("completo") and ult and ahora - datetime.fromisoformat(ult) < timedelta(hours=YA_HECHO_HORAS):
        print(f"La ultima descarga completa fue el {ult}. Hoy no se pide nada al Senado.")
        return

    # 1. lista de iniciativas (1 peticion al dia)
    url = f"{FICH}?tipoFich=9&legis={LEGIS}"
    crudo = pedir(url)
    esperar()
    if not crudo:
        if bloqueado:
            previo["bloqueado_utc"] = ahora.isoformat(timespec="seconds")
            previo["avisos"] = avisos
            ruta_m.write_text(json.dumps(previo, ensure_ascii=False, indent=2), "utf-8")
        sys.exit("No consigo la lista de iniciativas del Senado. No se escribe nada. Detalle: " + "; ".join(avisos))
    guardar(CRUDO / "iniciativas.xml", crudo, manifiesto, url)

    # 2. ficha de cada ley (como mucho una vez por semana cada una)
    leyes = leyes_de(crudo)
    for t, n in leyes:
        ruta = CRUDO / "fichas" / f"{t}-{n}.xml"
        if reciente(previos, ruta, REFRESCO_FICHAS_DIAS):
            continue
        if not dentro_de_horario():
            cortado = True; break
        url = f"{FICH}?tipoFich=3&tipoEx={t}&numEx={n}"
        c = pedir(url)
        if bloqueado or cortado:
            break
        esperar()
        if c:
            guardar(ruta, c, manifiesto, url)

    # 3. sesiones plenarias con votaciones (solo las nuevas).
    #    - Las sesiones ya bajadas no se piden otra vez.
    #    - Un hueco INTERNO (sesion no publicada, p. ej. la 20) se reintenta como mucho una vez por semana.
    #    - Mas alla de la ultima sesion publicada solo se pregunta cada dia por la SIGUIENTE; las demas, una vez por semana.
    huecos, n, buenas = 0, 0, 0
    hoy = datetime.now(MADRID).date()
    existentes = [int(p.stem.split("_")[1]) for p in (CRUDO / "votaciones").glob("ses_*.xml") if p.stem.split("_")[1].isdigit()]
    ultima = max(existentes, default=0)
    while huecos < FALLOS_SEGUIDOS and not cortado and not bloqueado:
        n += 1
        ruta = CRUDO / "votaciones" / f"ses_{n}.xml"
        if ruta.exists():
            buenas += 1; huecos = 0
            continue
        visto = no_publicadas.get(str(n))
        reciente_no = bool(visto) and (hoy - datetime.fromisoformat(visto).date()).days < 7
        if reciente_no and n != ultima + 1:
            huecos = huecos + 1 if n > ultima else 0   # hueco conocido: no se vuelve a pedir esta semana
            continue
        if not dentro_de_horario():
            cortado = True; break
        url = f"{BASE}/legis{LEGIS}/votaciones/ses_{n}.xml"
        c = pedir(url)
        if bloqueado or cortado:
            break      # cortado en pleno reintento: no es un hueco, no se apunta como 'no publicada'
        esperar()
        if c and b"<" in c[:200]:
            guardar(ruta, c, manifiesto, url)
            no_publicadas.pop(str(n), None)
            buenas += 1; huecos = 0; ultima = max(ultima, n)
        else:
            huecos += 1
            no_publicadas[str(n)] = hoy.isoformat()
    if cortado:
        avisos.append("Se acabo la ventana horaria del Senado (06:00). Lo que falta se baja la noche siguiente.")

    # 4. manifiesto (se fusiona con el anterior para no perder huellas de ficheros ya bajados)
    archivos = dict(previos); archivos.update(manifiesto)
    ruta_m.write_text(json.dumps({
        "fuente": "Senado de España, datos abiertos (CC-BY 4.0): https://www.senado.es/web/relacionesciudadanos/datosabiertos/",
        "legislatura": LEGIS, "ultima_descarga_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "leyes_encontradas": len(leyes), "sesiones_con_votaciones": sum(1 for k in archivos if "/votaciones/" in k),
        "sesiones_no_publicadas": no_publicadas, "completo": not cortado and not bloqueado,
        **({"bloqueado_utc": ahora.isoformat(timespec="seconds")} if bloqueado else {}),
        "avisos": avisos, "archivos": archivos}, ensure_ascii=False, indent=2), "utf-8")
    print(f"Listo: {len(leyes)} leyes, {buenas} sesiones con votaciones, {len(avisos)} avisos (ver manifiesto.json)")
    if bloqueado:
        sys.exit(2)   # que el flujo salga en rojo: el Senado ha dicho que paremos


if __name__ == "__main__":
    main()
