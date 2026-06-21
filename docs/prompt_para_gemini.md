# Instrucciones para el usuario humano (leer ANTES de pegar este prompt en Gemini)

Este archivo contiene un prompt completo y autocontenido, listo para copiar y
pegar **tal cual** en una sesión nueva de Google Gemini (fuera de este
repositorio). Gemini construirá la aplicación web descrita usando Bun.

**Antes de pegar el prompt, sube a la conversación de Gemini estos archivos**
(todos están en `outputs/` o `docs/` de este proyecto):

| Archivo a subir | Por qué |
|---|---|
| `outputs/predictions_muestra_gemini.geojson` | Muestra liviana (99 predios, ~135 KB) con la estructura EXACTA de `predictions.geojson`. Se usa solo para que Gemini vea el esquema real sin necesitar subir el archivo completo (que pesa ~35 MB y tiene 24,097 predios). Una vez Gemini genere el proyecto, **copia el archivo completo `outputs/predictions.geojson` dentro de la carpeta de datos del proyecto generado**, reemplazando la muestra. |
| `outputs/pipeline_steps.json` | Pasos del pipeline con ejemplos reales de limpieza (ya está embebido completo más abajo también, pero súbelo igual para que Gemini pueda leerlo directo). |
| `outputs/model_comparison.json` | Tabla comparativa de los 5 modelos (embebida también más abajo). |
| `outputs/shap_global.json` | Importancia global de variables del modelo ganador (embebida también más abajo). |
| `docs/data_dictionary.md` | Ficha completa de las 13 fuentes de datos reales, con reglas de limpieza, embudos de descarte y limitaciones. |
| `docs/resumen.md` (opcional pero recomendado) | Hallazgos territoriales narrativos (qué variable pesa más, en qué comunas predice mejor/peor) — útil para que Gemini redacte los textos explicativos de la vista B. |

Con esto, Gemini no necesita adivinar ninguna estructura de datos: todo el
esquema, unidades, ejemplos de fila y glosario de variables están explícitos
en el prompt y en los archivos adjuntos.

---

# PROMPT — copiar todo lo que sigue desde aquí hacia abajo y pegarlo en Gemini

Vas a construir una aplicación web con **Bun** llamada **"Prediusly"**, que
visualiza los resultados de un modelo de predicción de avalúo fiscal de
predios habitacionales en la Región Metropolitana de Chile (RM). Todos los
datos que necesitas ya están calculados y adjuntos a esta conversación — no
debes inventar ni asumir ninguna estructura de datos, columna, unidad o
valor que no esté explícita en este prompt o en los archivos adjuntos.

## 0. Contexto del proyecto (para que redactes los textos explicativos con criterio)

"Prediusly" predice el avalúo fiscal de predios habitacionales urbanos en la
RM a partir de variables geoespaciales de accesibilidad y equipamiento
urbano. El marco teórico detrás del análisis (cítalo en las explicaciones de
la vista B, en lenguaje simple, sin jerga académica):

- El suelo urbano es un **bien heterogéneo**: no hay dos predios iguales,
  cada uno ocupa una posición irrepetible en la ciudad.
- **Renta de localización / bid-rent**: el valor del suelo decae con la
  distancia a centros de actividad, y ese decaimiento no es necesariamente
  lineal (un modelo de árboles de decisión como el ganador de este proyecto
  captura mejor esa no linealidad que una regresión lineal clásica).
- **Economías de aglomeración**: la concentración de equipamiento (p.ej.
  muchos jardines infantiles cerca, no solo el más cercano) genera plusvalía
  adicional más allá de la simple distancia al equipamiento más próximo.

El equipo de ciencia de datos procesó 13 fuentes geoespaciales reales de la
RM (predios del SII, educación por nivel, salud, metro, microbuses,
aeropuertos, red vial, zonificación PRMS y topografía), las limpió con
reglas específicas y documentadas por fuente, calculó ~21 variables
geoespaciales por predio, entrenó y comparó 5 modelos con validación
cruzada **espacial** (por comuna, nunca aleatoria), afinó los 3 modelos de
árboles con una búsqueda de hiperparámetros con **Optuna**, y generó
explicaciones SHAP globales y por predio. Tu trabajo es construir la
interfaz que cuenta esa historia, no rehacer el análisis.

**Resultado final del modelamiento**: el modelo ganador es **LightGBM
afinado con Optuna** (R²=0.587, mejor que OLS, Random Forest, XGBoost y GWR
— ver tabla completa en la sección 2.2, incluida la nota de que superó por
un margen real al LightGBM con hiperparámetros fijos gracias al tuning). El
dataset final tiene 2,212,777 predios habitacionales urbanos analizados (de
3,789,659 predios crudos del SII), de los cuales una muestra de 24,097 (con
su top-3 de variables SHAP ya calculado) se exporta para la web en
`predictions.geojson`.

---

## 1. Requisitos técnicos generales

- Inicializa el proyecto con `bun init`. Backend con `Bun.serve` o **Hono**
  (tu elección — justifícala brevemente en el README). Frontend con **Vite +
  React** o vanilla + Tailwind (tu elección, justifícala en el README).
- **Sin base de datos externa**: los 4 archivos JSON/GeoJSON adjuntos se
  leen directamente desde disco (carpeta `data/` del proyecto) y se sirven
  vía endpoints simples del servidor Bun (p.ej. `GET /api/predictions`,
  `GET /api/pipeline-steps`, `GET /api/model-comparison`,
  `GET /api/shap-global`). El frontend consume esos endpoints, no lee los
  archivos directamente.
- Responsive (debe verse bien en notebook y en tablet como mínimo).
- Código comentado donde la lógica no sea obvia.
- README con instrucciones de instalación y ejecución: `bun install && bun
  run dev`, más una nota explicando dónde poner el `predictions.geojson`
  completo (carpeta `data/`) reemplazando la muestra liviana.
- Mapa interactivo: usa **Leaflet** o **MapLibre GL** (tu elección).

---

## 2. Esquema EXACTO de los datos (no asumas nada fuera de esto)

### 2.1 `predictions.geojson` (GeoJSON FeatureCollection, EPSG:4326 / WGS84)

Cada `Feature` tiene `geometry` de tipo **Polygon** (el polígono real del
predio, no un punto) y estas propiedades:

| Propiedad | Tipo | Unidad / dominio | Descripción |
|---|---|---|---|
| `rol` | string | — | ID catastral del predio (formato `manzana-predio`, p.ej. `"00009-00017"`) |
| `nombre_comuna` | string | — | Comuna en mayúsculas, p.ej. `"SANTIAGO"` |
| `superficie_m2` | float | m² | Superficie del polígono del predio |
| `avaluo_fiscal` | int | CLP | Avalúo fiscal REAL (2025) del predio — el target |
| `avaluo_predicho` | float | CLP | Avalúo predicho por el modelo ganador (LightGBM) |
| `residual` | float | CLP | `avaluo_fiscal - avaluo_predicho` |
| `residual_pct` | float | % | `residual / avaluo_fiscal * 100`. Negativo = el modelo SUBESTIMÓ el valor real; positivo = lo SOBREESTIMÓ |
| `dist_metro_m` | float | metros | Distancia a la estación de Metro más cercana (las 124 estaciones de la red, sin distinguir estado de construcción — ver nota en sección 4) |
| `dist_salud_m` | float | metros | Distancia al establecimiento de salud más cercano (ya filtrado, solo atención presencial general) |
| `dist_edu_escolar_m` | float | metros | Distancia al colegio más cercano |
| `dist_edu_parvularia_m` | float | metros | Distancia al jardín infantil más cercano |
| `dist_edu_superior_m` | float | metros | Distancia a la institución de educación superior más cercana |
| `dist_micro_m` | float | metros | Distancia al paradero de microbús más cercano |
| `dist_aeropuerto_m` | float | metros | Distancia al aeropuerto/aeródromo más cercano (efecto esperado: negativo sobre el valor) |
| `dist_red_vial_m` | float | metros | Distancia euclidiana (no por red) al eje vial clasificado más cercano |
| `count_metro_1km` | int | conteo | N° de estaciones de Metro en buffer de 1 km |
| `count_salud_1km` | int | conteo | N° de establecimientos de salud en buffer de 1 km |
| `uso_suelo_ipt` | string | categoría | Uso de suelo dominante (PRMS) en buffer 250m: `"Habitacional - Mixto"`, `"Equipamiento"`, `"Área Verde"`, `"Actividad Productiva"`, `"Riesgo"`, `"Hidrografía"`, o `"SIN_DATO"` |
| `elevacion_m` | float o null | metros | Elevación interpolada desde curvas de nivel (null si el predio cae fuera de la cobertura topográfica, ~1.5% de los casos) |
| `pendiente_pct` | float o null | % | Pendiente local estimada |
| `variacion_avaluo_pct_2020_2025` | float o null | % | Variación % de avalúo entre 2020 (promedio de su manzana censal) y 2025 (el predio). **Es una variable de análisis territorial, NO fue usada como predictor del modelo** (ver nota en sección 4). Frecuentemente `null` (~32% de los casos, predios fuera de la cobertura de manzanas 2020 válidas) |
| `shap_top3` | array de objetos | — | Las 3 variables que más influyeron en la predicción de ESTE predio específico. Cada objeto: `{"feature": "<nombre_variable>", "shap_value": <float>, "direccion": "sube"|"baja"}`. `direccion` indica si esa variable empujó la predicción hacia arriba o hacia abajo respecto del promedio. `feature` puede ser cualquiera de las 23 variables del modelo — ver glosario completo en sección 3 (incluye variables como `centroid_x`/`nombre_comuna_enc` que no están como propiedad directa del GeoJSON: tradúcelas usando el glosario, no las muestres como coordenadas crudas) |

Ejemplo real de una Feature (toma este formato como verdad absoluta):

```json
{
  "type": "Feature",
  "geometry": { "type": "Polygon", "coordinates": [ ... ] },
  "properties": {
    "rol": "00611-00104",
    "nombre_comuna": "SANTIAGO",
    "superficie_m2": 2368.17,
    "avaluo_fiscal": 56063671,
    "avaluo_predicho": 60302988.19,
    "residual": -4239317.19,
    "residual_pct": -7.56,
    "dist_metro_m": 572.57,
    "dist_salud_m": 231.34,
    "dist_edu_escolar_m": 82.79,
    "dist_edu_parvularia_m": 82.79,
    "dist_edu_superior_m": 283.11,
    "dist_micro_m": 118.82,
    "dist_aeropuerto_m": 8294.53,
    "dist_red_vial_m": 1469.33,
    "count_metro_1km": 3,
    "count_salud_1km": 12,
    "uso_suelo_ipt": "Habitacional - Mixto",
    "elevacion_m": 573.28,
    "pendiente_pct": 1.43,
    "variacion_avaluo_pct_2020_2025": -98.40,
    "shap_top3": [
      {"feature": "dist_edu_superior_m", "shap_value": 0.1074, "direccion": "sube"},
      {"feature": "centroid_x", "shap_value": -0.0799, "direccion": "baja"},
      {"feature": "count_edu_superior_1km", "shap_value": 0.0701, "direccion": "sube"}
    ]
  }
}
```

El archivo completo tiene **24,097 features** (predios), repartidos entre
las 54 comunas de la RM. La muestra adjunta (`predictions_muestra_gemini.geojson`)
tiene 99 features con esta misma estructura exacta.

### 2.2 `model_comparison.json` (contenido COMPLETO — úsalo tal cual, no lo resumas de memoria)

```json
{
  "OLS": {
    "R2": 0.4294,
    "RMSE_log": 0.5379,
    "RMSE_CLP": 196840799.0,
    "MAPE_pct": 46.88,
    "ganador": false
  },
  "Random Forest": {
    "R2": 0.4013,
    "RMSE_log": 0.551,
    "RMSE_CLP": 54011885.0,
    "MAPE_pct": 47.52,
    "ganador": false
  },
  "LightGBM": {
    "R2": 0.5866,
    "RMSE_log": 0.4579,
    "RMSE_CLP": 51188469.0,
    "MAPE_pct": 37.64,
    "ganador": true,
    "tuned_optuna": true,
    "optuna_best_params": {
      "n_estimators": 600,
      "max_depth": 12,
      "learning_rate": 0.02030605783687948,
      "num_leaves": 65,
      "min_child_samples": 41,
      "subsample": 0.9954888318934102,
      "colsample_bytree": 0.645833212546373,
      "reg_alpha": 1.490139026340029,
      "reg_lambda": 0.027307649113289003
    }
  },
  "XGBoost": {
    "R2": 0.5257,
    "RMSE_log": 0.4905,
    "RMSE_CLP": 50298857.0,
    "MAPE_pct": 42.91,
    "ganador": false
  },
  "GWR": {
    "R2": 0.1611,
    "RMSE_log": 0.7982,
    "RMSE_CLP": 302396675.0,
    "MAPE_pct": 84.16,
    "ganador": false,
    "nota": "GWR evaluado sobre muestra estratificada por comuna (n=3034) por restricciones de escala computacional (O(n^2) en mgwr). No participa como candidato a 'modelo ganador' de producción para las 2.2M predicciones completas; se usa para analizar no-estacionariedad espacial de los coeficientes (evidencia de bid-rent no lineal/heterogéneo en el espacio).",
    "n_muestra": 3034
  }
}
```

`R2` = coeficiente de determinación (más alto mejor, escala log del
avalúo). `RMSE_log` = error cuadrático medio en escala log. `RMSE_CLP` =
error cuadrático medio en pesos chilenos (escala original). `MAPE_pct` =
error porcentual absoluto medio. `ganador: true` marca el modelo elegido
para generar `predictions.geojson`. `tuned_optuna: true` y
`optuna_best_params` indican que ese modelo fue afinado con una búsqueda de
hiperparámetros con Optuna (30 trials, sobre una muestra de ~100,000
predios) y luego reentrenado a escala completa — muéstralo en la UI como un
detalle técnico relevante (p.ej. un badge "Hiperparámetros optimizados con
Optuna" en la tabla comparativa).

**Dato clave a comunicar en la UI**: GWR tiene R² bajo (0.161) porque se
evaluó con un split espacial estricto en comunas completas excluidas del
entrenamiento (para medir generalización real), mientras que dentro de su
propia muestra de entrenamiento su R² local promedio es 0.45 — esto NO es
un error de datos, es un hallazgo real sobre el trade-off entre
interpretabilidad local y capacidad de generalizar a zonas nuevas.
Coméntalo en la vista B, no lo oculte ni lo "corrijas".

### 2.3 `shap_global.json` (contenido COMPLETO)

```json
{
  "centroid_x": 0.1373,
  "count_edu_parvularia_1km": 0.1198,
  "superficie_m2": 0.1118,
  "centroid_y": 0.0649,
  "dist_edu_superior_m": 0.06,
  "elevacion_m": 0.0552,
  "nombre_comuna_enc": 0.043,
  "log_superficie": 0.0357,
  "dist_aeropuerto_m": 0.0352,
  "dist_metro_m": 0.0348,
  "dist_edu_parvularia_m": 0.0319,
  "count_edu_superior_1km": 0.0282,
  "count_micro_1km": 0.0232,
  "count_micro_500m": 0.0223,
  "count_edu_escolar_1km": 0.0186,
  "dist_salud_m": 0.0173,
  "count_metro_1km": 0.0138,
  "dist_micro_m": 0.0125,
  "dist_red_vial_m": 0.0084,
  "count_salud_1km": 0.0083,
  "dist_edu_escolar_m": 0.0082,
  "pendiente_pct": 0.0056,
  "uso_suelo_ipt_enc": 0.0037
}
```

**Nota sobre metro vs. microbuses**: sumando sus variables relacionadas,
metro (`dist_metro_m` + `count_metro_1km` = 0.049) pesa ligeramente MENOS
que microbuses (`dist_micro_m` + `count_micro_500m` + `count_micro_1km` =
0.058) en este modelo final. Coméntalo como un hallazgo matizado en la
vista B (no afirmes que el metro siempre domina sobre el transporte de
superficie), usando el texto de `docs/resumen.md` sección 6.1 como
referencia.

Es un diccionario plano `{nombre_variable: importancia_media_|SHAP|}`, ya
ordenado de mayor a menor importancia. Úsalo para el gráfico de barras
horizontal de importancia global (vista B).

### 2.4 `pipeline_steps.json`

Está adjunto completo (10 KB) — súbelo y léelo directamente; contiene:
- `etapas`: array de 5 etapas (Datos crudos → Limpieza de predios → Feature
  engineering → Modelo → Predicción), cada una con su `descripcion`. La
  etapa "Limpieza de predios" trae un objeto `embudo` (conteos paso a paso)
  y un array `reglas` con 5 reglas, cada una con `paso`, `nombre`,
  `descripcion`, `descartados` (cuántos predios se perdieron en ese paso) y
  `ejemplo` (un caso REAL con rol de predio, comuna y valores — úsalo
  textualmente en la UI, no lo inventes).
- La etapa "Feature engineering geoespacial" trae `features_calculadas`:
  array de `{nombre, descripcion}` para cada variable.
- La etapa "Modelo" trae `comparacion_modelos` (mismo contenido que
  `model_comparison.json`).
- `ejemplos_limpieza.educacion`: por nivel (escolar/parvularia/superior),
  conteos del embudo de homonimia y un `ejemplo` textual real (el caso de
  "Universidad de Chile" con 55 puntos fusionados es el más ilustrativo —
  destácalo).
- `ejemplos_limpieza.salud`: conteos de exclusión por categoría
  (`conteo_excluidos`) y un `ejemplo` textual real.

### 2.5 `data_dictionary.md` y `resumen.md`

Son texto narrativo en Markdown (no los parsees como datos estructurados).
Úsalos como fuente de verdad para redactar las fichas de fuentes de datos
de la vista B (sección 5) y los textos explicativos generales. Cada fuente
en `data_dictionary.md` sigue el mismo formato: origen, fecha/período,
cobertura, formato, CRS, variables, unidad de observación, manejo de
nulos/duplicados/geometrías inválidas, y limitaciones documentadas cuando
corresponde (p.ej. SII_2020 es a nivel de manzana, no de predio;
topografía cubre solo el 98.5% de la RM; red_vial usa distancia euclidiana
porque solo tiene 479 segmentos arteriales, no la malla local completa).

---

## 3. Glosario de variables (para traducir nombres técnicos a lenguaje simple en la UI)

Usa esta tabla para CUALQUIER variable que aparezca en `shap_top3`,
`shap_global.json` o las propiedades del GeoJSON. Nunca muestres un nombre
de variable crudo (como `dist_edu_parvularia_m` o `centroid_x`) directo al
usuario final sin pasarlo por esta traducción:

| Variable técnica | Traducción para el usuario final | Unidad |
|---|---|---|
| `superficie_m2` | Tamaño del terreno | m² |
| `log_superficie` | Tamaño del terreno (transformación logarítmica usada internamente por el modelo) | — |
| `dist_edu_escolar_m` | Distancia al colegio más cercano | metros |
| `count_edu_escolar_1km` | Cantidad de colegios cerca (en 1 km) | conteo |
| `dist_edu_parvularia_m` | Distancia al jardín infantil más cercano | metros |
| `count_edu_parvularia_1km` | Cantidad de jardines infantiles cerca (en 1 km) | conteo |
| `dist_edu_superior_m` | Distancia a la universidad/instituto más cercano | metros |
| `count_edu_superior_1km` | Cantidad de universidades/institutos cerca (en 1 km) | conteo |
| `dist_salud_m` | Distancia al centro de salud más cercano | metros |
| `count_salud_1km` | Cantidad de centros de salud cerca (en 1 km) | conteo |
| `dist_metro_m` | Distancia a la estación de Metro más cercana | metros |
| `count_metro_1km` | Cantidad de estaciones de Metro cerca (en 1 km) | conteo |
| `dist_micro_m` | Distancia al paradero de micro más cercano | metros |
| `count_micro_500m` | Cantidad de paraderos de micro muy cerca (500 m) | conteo |
| `count_micro_1km` | Cantidad de paraderos de micro cerca (1 km) | conteo |
| `dist_aeropuerto_m` | Distancia al aeropuerto/aeródromo más cercano | metros |
| `dist_red_vial_m` | Distancia a una vía principal clasificada | metros |
| `elevacion_m` | Altura sobre el nivel del mar del sector | metros |
| `pendiente_pct` | Inclinación del terreno | % |
| `centroid_x` / `centroid_y` | Ubicación del predio dentro de la ciudad (posición geográfica) | — (no mostrar coordenadas crudas; explicar como "la ubicación en sí misma") |
| `nombre_comuna_enc` | La comuna donde está el predio | — |
| `uso_suelo_ipt_enc` / `uso_suelo_ipt` | El tipo de zona urbana donde está el predio (residencial, equipamiento, área verde, etc.) | categoría |

---

## 4. Decisiones de limpieza y modelamiento que la web DEBE explicar al usuario final

1. **Por qué se descartaron ~1.58M de los 3.79M predios crudos**: el dataset
   del SII incluye predios rurales, agrícolas, comerciales e industriales —
   este proyecto se enfoca exclusivamente en predios **habitacionales
   urbanos** entre 50 y 20,000 m². Usa los datos reales del embudo
   (`pipeline_steps.json` → etapa "Limpieza de predios" → `embudo`).
2. **Por qué educación superior pasó de 526 a 193 puntos en la RM**: muchas
   universidades grandes (el caso real es "Universidad de Chile", con 55
   puntos fusionados) registran cada facultad/campus como una entrada
   separada bajo el mismo nombre; se fusionan en un solo punto cuando están
   a menos de 1.5 km entre sí, para no sobre-contar accesibilidad a la
   "misma" institución.
3. **Por qué de 5,159 establecimientos de salud solo quedaron 3,970**: se
   excluyeron 18 categorías que no son atención presencial general
   (laboratorios, dental, diálisis, vacunatorios, atención remota, etc.).
4. **Por qué GWR tiene métricas distintas/peores que los otros 4 modelos**:
   explicado en la sección 2.2 — es una limitación de escala computacional
   documentada, no un error.
4b. **Por qué `dist_metro_m` se calcula con las 124 estaciones de la red y
   no solo con las marcadas como "existentes" en la fuente**: ese atributo
   de estado quedó desactualizado — hoy todas las estaciones están
   operativas. Es una corrección de datos confirmada por el equipo, no una
   omisión.
5. **Por qué `variacion_avaluo_pct_2020_2025` no es un predictor del
   modelo**: se calculó comparando cada predio 2025 contra el promedio de
   SU MANZANA en 2020 (porque los datos de 2020 no tienen predios
   individuales, solo agregados por manzana), lo que introduce ruido e
   inferencia ecológica — se muestra como dato de contexto/análisis
   territorial en el panel del predio, pero no se presenta como algo que
   "explique" la predicción.
6. **Por qué el modelo subestima sistemáticamente el valor en comunas como
   Providencia, Santiago y Ñuñoa** (mencionar si tienes espacio en la vista
   B, usando `docs/resumen.md` sección 6.2): el modelo no incluye variables
   de la edificación (pisos, m² construidos), solo de ubicación y terreno,
   por lo que subestima sistemáticamente zonas de alta densidad en altura.

---

## 5. Vista A — "Resultados" (mapa)

- Mapa interactivo (Leaflet o MapLibre GL) centrado en la RM, con los
  24,097 polígonos de predios de `predictions.geojson` coloreados por
  `avaluo_predicho` (escala de color continua, p.ej. de amarillo a rojo
  oscuro). Toggle para cambiar a coloreado por `residual_pct` (escala
  divergente: azul = subestimado, rojo = sobreestimado, centrada en 0).
- Al hacer click en un predio: panel lateral/modal con:
  - Avalúo real (`avaluo_fiscal`) vs. predicho (`avaluo_predicho`), y el
    residual en CLP y en %.
  - Sus distancias/conteos clave por categoría, ya traducidos con el
    glosario de la sección 3 (educación por nivel, salud, metro, micro,
    aeropuerto, red vial).
  - Sus 3 variables SHAP más influyentes (`shap_top3`), traducidas a
    lenguaje simple: p.ej. "El tamaño del terreno y la cercanía a
    universidades subieron el valor predicho; la ubicación dentro de la
    ciudad lo bajó."
  - Si `variacion_avaluo_pct_2020_2025` no es null, mostrarla como dato de
    contexto aparte (con la aclaración de que es una comparación contra el
    promedio de su manzana en 2020, no del mismo predio).
- Filtro por comuna (dropdown con las comunas presentes en los datos) y por
  rango de avalúo (slider).
- Tabla comparativa de los 5 modelos (`model_comparison.json`) con
  R²/RMSE/MAPE, destacando visualmente el ganador (LightGBM).

## 6. Vista B — "Cómo se obtuvo la predicción" (storytelling del pipeline)

- Stepper horizontal o vertical con las 5 etapas de `pipeline_steps.json`:
  Datos crudos → Limpieza → Feature engineering → Modelo → Predicción.
- En la etapa de limpieza: mostrar el embudo (gráfico de funnel o barras
  decrecientes) y, para cada una de las 5 reglas, su `ejemplo` real tal
  cual viene en los datos (no reformules los números, pero sí puedes
  traducir el texto a un tono más conversacional).
- Mostrar también, en esta etapa o en una sub-sección, los casos reales de
  fusión por homonimia en educación (especialmente el de "Universidad de
  Chile") y de exclusión en salud (el de "Laboratorio Clínico de Agostini y
  Cia. Ltda.").
- Gráfico de barras horizontal con `shap_global.json` (importancia global),
  con cada variable traducida según el glosario de la sección 3, y una
  explicación breve de qué es SHAP en lenguaje simple ("cuánto empuja cada
  variable la predicción hacia arriba o abajo, en promedio, para todos los
  predios").
- Fichas tipo tarjeta por cada una de las 13 fuentes de datos (usando
  `docs/data_dictionary.md`): origen, fecha, cobertura, formato, CRS,
  variables, manejo de calidad de datos, y la limitación documentada de esa
  fuente si la tiene (destacar especialmente: SII_2020 es a nivel de
  manzana no de predio; topografía cubre 98.5% de la RM; red_vial usa
  distancia euclidiana por tener solo 479 segmentos arteriales).
- Cierra esta vista con 2-3 hallazgos territoriales tomados textualmente de
  `docs/resumen.md` sección 6 (importancia de variables, comunas mejor/peor
  predichas, no-estacionariedad espacial de GWR).

---

## 6. Checklist final antes de entregar

- [ ] `bun install && bun run dev` deja la app funcionando sin pasos manuales adicionales (salvo copiar el `predictions.geojson` completo a `data/`).
- [ ] Ningún nombre de variable técnico se muestra sin traducir al usuario final.
- [ ] El stepper de la vista B usa los ejemplos REALES de `pipeline_steps.json`, no ejemplos inventados.
- [ ] La tabla de modelos muestra el GWR con su nota explicativa, no lo omite ni lo presenta como "modelo fallido".
- [ ] El mapa funciona con la muestra de 99 predios y también con el archivo completo de 24,097.
- [ ] README explica la elección de stack (Hono vs Bun.serve, React vs vanilla) y cómo reemplazar la muestra por el GeoJSON completo.
