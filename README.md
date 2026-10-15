# Euthyna

Datos abiertos del Congreso de los Diputados y del Senado, descargados cada día y publicados **sin alterar**. Proyecto ciudadano, sin ánimo de lucro.

> **Euthyna no está respaldado, patrocinado ni apoyado por el Congreso de los Diputados ni por el Senado.** Es una iniciativa independiente que reutiliza la información pública que ambas instituciones publican.

## Qué es

Euthyna quiere que cualquier persona pueda ver, con datos oficiales, qué hacen el Congreso y el Senado: qué leyes se proponen y se aprueban, a qué dedican su actividad y cómo votan los grupos.

Este repositorio es la primera pieza: **la descarga automática y ordenada de los datos oficiales**. La web que los muestra se construye aparte y leerá estos archivos.

## De dónde salen los datos

| Fuente | Qué descargamos | Con qué frecuencia |
|---|---|---|
| **Congreso de los Diputados**, datos abiertos (<https://www.congreso.es/es/datos-abiertos>) | Leyes aprobadas, proyectos de ley, proposiciones de ley y propuestas de reforma | Cada día |
| **Congreso de los Diputados**, buscador de iniciativas con exportación abierta (<https://www.congreso.es/es/busqueda-de-iniciativas>) | Toda la actividad de la legislatura XV (leyes, proposiciones no de ley, preguntas, etc.) | Cada lunes |
| **Senado de España**, datos abiertos (<https://www.senado.es/web/relacionesciudadanos/datosabiertos/>) | Iniciativas legislativas, ficha de cada ley y votaciones de cada sesión del Pleno, legislatura XV | Cada noche, solo lo nuevo |

Cada archivo de resumen indica la **fecha y hora de la descarga**: `datos/resumen.json`, `datos/actividad_leg15_resumen.json` y `datos/senado/manifiesto.json`.

## Cómo respetamos las normas de cada web

- **No alteramos los datos.** Guardamos el original tal como llega, con su huella SHA-256 para poder comprobar que no se ha modificado. Los archivos CSV y los resúmenes se generan aparte, sin tocar el original.
- **Citamos siempre la fuente y la fecha de actualización**, como piden las condiciones de reutilización de ambas instituciones.
- **Leemos el `robots.txt` de cada web antes de descargar nada** y cumplimos sus reglas:
  - Congreso: no bloquea las rutas que usamos. Aun así, solo hacemos 5 peticiones al día y unas 660 una vez por semana, con 2 segundos de pausa entre ellas.
  - Senado: espera de **60 segundos** entre peticiones y descargas **solo entre las 02:00 y las 06:00** (hora de Madrid). Usamos únicamente sus datos abiertos oficiales, nunca sus buscadores ni las rutas bloqueadas.
- **Nos identificamos.** Nuestros programas se presentan como Euthyna e indican esta dirección de contacto. Si una institución detecta algún problema, puede avisarnos aquí.
- Si un archivo nuevo llega sospechosamente pequeño, no sobrescribimos el anterior y dejamos un aviso.

## Cómo funciona

Todo se ejecuta con GitHub Actions, sin servidores propios. Los programas solo usan la biblioteca estándar de Python.

| Archivo | Qué hace |
|---|---|
| `actualizar_congreso_iniciativas_legislativas.py` | Descarga las iniciativas legislativas del Congreso |
| `actualizar_congreso_actividad.py` | Descarga toda la actividad de la legislatura XV del Congreso |
| `actualizar_senado.py` | Descarga los datos abiertos del Senado |
| `.github/workflows/actualizar_congreso.yml` | Programa las descargas del Congreso |
| `.github/workflows/actualizar_senado.yml` | Programa las descargas del Senado |

Los datos descargados se guardan en la carpeta `datos/`.

## Licencias

- **Código de Euthyna:** [GNU Affero General Public License v3.0](LICENSE). Cualquier copia o versión modificada, incluida una web, debe mantenerse abierta con la misma licencia.
- **Datos del Congreso de los Diputados:** se reutilizan conforme a su [aviso legal](https://www.congreso.es/es/cem/aviso-legal) y a la Ley 37/2007 de reutilización de la información del sector público. Fuente: Congreso de los Diputados.
- **Datos del Senado de España:** [Creative Commons Reconocimiento 4.0 (CC BY 4.0)](https://www.senado.es/web/relacionesciudadanos/datosabiertos/reutilizacion/index.html). Fuente: Senado de España.

Los datos conservan la licencia y las condiciones de la institución que los publica. La licencia del código no se aplica a ellos.

## Contacto

Para cualquier duda o aviso sobre este proyecto, abre una *issue* en este repositorio.
