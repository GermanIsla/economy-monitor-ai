# research/ — Espacio de trabajo de análisis (mantenido por Claude)

Esta carpeta es el **espacio de conocimiento y eficiencia** del estudio, separado del
código del programa. Su objetivo es que cada sesión arranque desde un mapa conocido en
lugar de re-explorar el repo. La mantengo yo (Claude) viva a medida que avanzamos.

## EMPIEZA AQUÍ (orden de lectura para retomar el análisis)

1. **[data_dictionary.md](data_dictionary.md)** — Catálogo de todas las series: qué son,
   fuente, frecuencia, unidad, **dirección/signo**, cadencia de publicación, rango de fechas
   y trampas conocidas. Consultar ANTES de tocar cualquier serie.
2. **[methodology.md](methodology.md)** — Convenciones fijas del estudio: resampleo,
   alineación de frecuencias, signo del lead/lag, transformaciones. Deben ser estables entre
   sesiones o las correlaciones no son comparables.
3. **[research_log.md](research_log.md)** — Bitácora fechada: hipótesis probadas, método,
   resultado y conclusión. La memoria intelectual del estudio.
4. **[economic_notes.md](economic_notes.md)** — Marco de teoría económica acordado con el
   usuario: qué es "liquidez" (3 capas), hipótesis vivas, sesgos de datos. Para interpretar
   con el mismo significado.
5. **[analysis/](analysis/)** — Motor de análisis reutilizable (código): cargar cualquier
   serie a un DataFrame semanal alineado + primitivas de correlación lead/lag.
6. **[data_backlog.md](data_backlog.md)** — Series/fuentes valiosas aún no descargadas (OFR
   repo bilateral, NFCI vintage, etc.) y lo ya estudiado-descartado.

## Tema del estudio

Relación entre **liquidez** (balance de la Fed, repo, condiciones financieras, y —pendiente—
liquidez neta = Balance − TGA − RRP) y la **bolsa** (S&P 500, Bitcoin), y cómo usarla para
tomar decisiones. Objetivo práctico: identificar si la liquidez **adelanta** al mercado y con
qué retardo.

## Reglas de mantenimiento (para mí)

- Actualizo `data_dictionary.md` cada vez que se añade/cambia una serie o pipeline.
- Registro en `research_log.md` cada hipótesis que probamos y su resultado (aunque sea nulo).
- Si cambio una convención, la fijo en `methodology.md` y anoto por qué.
- El código de `analysis/` es la única fuente de verdad para *cómo* cargo y alineo series;
  el diccionario describe *qué* son.
