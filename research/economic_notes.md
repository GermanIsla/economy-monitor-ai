# Notas de teoría económica (marco del estudio)

Marco conceptual acordado con el usuario. Sirve para que interpretemos las series con el
mismo significado. Se amplía a medida que aprendemos juntos.

## Qué es "liquidez" (no es una sola serie)

La liquidez tiene **tres capas** y hay que cubrir las tres (no buscar *la* serie única):

1. **Liquidez del banco central (cantidad).** Dinero base utilizable en el sistema. Proxy:
   **reservas bancarias** (`WRESBAL`), no el balance de la Fed. `net_liquidity` (WALCL−TGA−RRP)
   también aquí. El balance de la Fed / `fed_soma` es un **driver/stock, NO liquidez**.
2. **Liquidez de financiación (fontanería) — el foco principal del usuario.** El mercado
   **repo/SOFR** e **interbancario**: donde bancos y banca en la sombra piden/prestan a corto
   con colateral y **regulan su estrés financiero**. Es lo que el usuario llama "la sangre de
   las venas financieras". Lo que importa aquí es a menudo la **escasez/estrés** (spreads que
   se tensan, p. ej. SOFR−IORB), no solo la cantidad: la sangre puede estar y no fluir.
3. **Liquidez de mercado.** Facilidad de operar sin mover el precio: profundidad, bid-ask,
   VIX/MOVE.

## Hipótesis vivas del usuario

- **Letras → repo → mercado (colateral como multiplicador).** Más emisión de T-bills → más
  colateral de alta calidad en bancos → **reutilizado (rehypothecation) en el repo** → más
  capacidad de apalancamiento de banca y banca en la sombra → más munición para el mercado.
  Estado: **abierta, no testeada bien.** Nuestro repo tri-party es el segmento equivocado
  (mide cash de MMF hacia dealers). Requiere datos de **repo bilateral/patrocinado y SOFR**
  (OFR Short-Term Funding Monitor) y financiación de primary dealers (FR2004). Ver [[research-workspace]].
  NO confundir con el RRP (facilidad de la Fed): eso es solo una pata estrecha, no el mercado repo.

## Sesgos y trampas de datos (críticas del usuario, válidas)

- **NFCI con sesgo de revisión (look-ahead).** La Chicago Fed **re-estima toda la serie**
  histórica cada semana; el valor en la DB no es el que se publicó en real-time. Nuestras
  correlaciones con NFCI están **optimistamente sesgadas**. Arreglo: vintages (ALFRED) para
  medir la degradación. Preferir indicadores **basados en precio** (HY OAS, VIX, curva): son
  precios de mercado, **no se revisan**.
- **Nivel vs cambio.** Series que ambas suben (deuda, bolsa, balance) se parecen en nivel pero
  no predicen. Correlacionar cambios (ver methodology.md §2).
- **Régimen.** La relación liquidez↔bolsa cambia por épocas (pre/post 2008 y 2020). Usar
  correlación móvil y subperiodos.
