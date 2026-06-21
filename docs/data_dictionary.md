# Diccionario de datos — Prediusly

Predicción del avalúo fiscal de predios habitacionales urbanos en la Región
Metropolitana de Chile (RM), a partir de variables geoespaciales de
accesibilidad y equipamiento urbano.

**Unidad de análisis: el predio individual** (no la comuna ni la manzana).
La excepción documentada es `SII_2020`, que se usa únicamente como insumo
agregado para una variable de análisis temporal (ver sección 14).

Todas las capas se reproyectan a **EPSG:32719 (WGS 84 / UTM zona 19S)** antes
de cualquier cálculo de distancia, área o buffer, para que esas operaciones
sean correctas en metros.

---

## Índice de fuentes

| # | Fuente | Tipo | Rol en el pipeline |
|---|---|---|---|
| 1 | SII_2025 | Predios + avalúo | Variable objetivo + geometría + atributos propios |
| 2 | SII_2020 | Manzanas + avalúo agregado | Variable temporal de análisis (no feature de modelo) |
| 3 | educacion_escolar | Puntos | Feature de accesibilidad |
| 4 | educacion_parvularia | Puntos | Feature de accesibilidad |
| 5 | educacion_superior | Puntos | Feature de accesibilidad |
| 6 | salud | Puntos | Feature de accesibilidad |
| 7 | metro.geojson | Puntos | Feature de accesibilidad (transporte) |
| 8 | Paradas_micro | Puntos | Feature de accesibilidad (transporte) |
| 9 | Aeropuertos | Puntos | Feature de accesibilidad (efecto negativo esperado) |
| 10 | red_vial | Líneas | Feature de accesibilidad vial estructurante |
| 11 | IPT_Metropolitana (PRMS / LU) | Polígonos | Feature de uso de suelo / zonificación |
| 12 | topografia | Líneas (curvas de nivel) | Feature de pendiente / elevación |
| 13 | RM.gpkg | Polígono | Referencia de área de estudio (no usado como feature) |

---

## 1. SII_2025 — Predios y avalúo fiscal (fuente principal)

- **Origen**: Servicio de Impuestos Internos (SII) de Chile, datos administrativos de avalúo fiscal de predios a nivel nacional.
- **Fecha / período**: campo `periodo` = "PRIMER SEMESTRE DE 2026" en todos los registros de muestra — es decir, el avalúo vigente corresponde al período de cobro de contribuciones del primer semestre de 2026, que reutiliza el reavalúo no agrícola más reciente (2022/2024 según `eacsDescripcion`). Se documenta esta discrepancia entre el nombre de la carpeta ("2025") y el período de cobro real para que no se interprete erróneamente como un error.
- **Cobertura**: Región Metropolitana completa, 54 archivos parquet (uno por comuna).
- **Formato**: Parquet, geometría como WKB en la columna `geometry`, CRS de origen EPSG:4326.
- **Variables clave usadas**: `destinoDescripcion`, `ubicacion`, `pol_area_m2`, `dc_avaluo_fiscal`, `rol`, `nombreComuna`, `comuna`.
- **Unidad de observación**: predio individual (rol de avalúo).
- **Volumen**: 86 columnas, 3,789,659 registros crudos.
- **Manejo de nulos**: 26.4%-89.2% de nulos según columna (muchas columnas son condicionales, p.ej. `ah_*` solo aplica a predios con área homogénea agrícola). Las columnas usadas en el filtro estructural (`destinoDescripcion`, `ubicacion`, `pol_area_m2`) tienen 17.0%-26.5% de nulos.
- **Geometrías inválidas**: 170 detectadas tras reproyección, reparadas con `make_valid`.
- **Duplicados**: no se detectaron filas duplicadas por `rol`.

### 1.1 Filtro estructural secuencial (regla 1.2.a, aplicado en orden — cada predio se descarta en el primer paso que falla)

| Paso | Regla | Predios resultantes | Descartados en este paso |
|---|---|---:|---:|
| 0 | Total cargado | 3,789,659 | — |
| 1 | `destinoDescripcion`, `ubicacion`, `pol_area_m2` no nulos | 3,623,879 | 165,780 |
| 2 | `destinoDescripcion == "HABITACIONAL"` | 2,405,025 | 1,218,854 |
| 3 | `ubicacion == "URBANA"` | 2,320,806 | 84,219 |
| 4 | `50 ≤ pol_area_m2 ≤ 20,000` | 2,254,999 | 65,807 |
| 5 | Geometría no nula/vacía | 2,254,999 | 0 |
| 6 | Reparación de geometrías inválidas (make_valid) | 2,254,999 | 0 reparadas en este conteo (170 inválidas reparadas, no descartadas) |
| 7 | Outliers de avalúo fiscal (percentil 1-99 **por comuna**) | **2,212,777** | 42,222 |

**Criterio de outliers (paso 7)**: se calculan los percentiles 1% y 99% de `avaluo_fiscal` **dentro de cada comuna** (no a nivel RM completo), porque el nivel de precios varía fuertemente entre comunas (p.ej. Vitacura vs. La Pintana); un umbral único de RM habría eliminado desproporcionadamente comunas de menor avalúo. Se descartan además avalúos nulos o ≤ 0 (0 casos en este dataset).

**Total final de predios habitacionales urbanos analizados: 2,212,777** (54 comunas).

### 1.2 Ejemplos concretos de descarte (registros reales)

- **Paso 1 (atributos nulos)**: predio rol `00044-00001` en ALHUÉ — tiene `destinoDescripcion`/`ubicacion` válidos pero `pol_area_m2` nulo (sin geometría asociada) → descartado.
- **Paso 2 (no habitacional)**: predio rol `00046-00001` en ALHUÉ, `destinoDescripcion = "AGRICOLA"`, `ubicacion = "RURAL"`, superficie 7,677 m² → descartado por no ser habitacional.
- **Paso 3 (no urbano)**: predio rol `00045-00002` en ALHUÉ, habitacional pero `ubicacion = "RURAL"`, avalúo $40,066,464 → descartado por ser rural (su valor responde a lógica de suelo agrícola, no urbana).
- **Paso 4 (fuera de rango de superficie)**: predio rol `00045-00007` en ALHUÉ, habitacional y urbano, pero `pol_area_m2 = 4.04 m²` → descartado (probable error de digitalización o subdivisión catastral incompleta).
- **Paso 7 (outlier de avalúo)**: predio rol `00205-00031` en LAS CONDES, avalúo fiscal $11,110,645,935 — muy por sobre el percentil 99 de Las Condes ($807,904,858) → descartado como outlier (probable predio de uso mixto/error de registro mal clasificado como habitacional puro).

---

## 2. educacion_escolar, educacion_parvularia, educacion_superior

- **Origen**: Centro de Estudios MINEDUC (registro de establecimientos educacionales reconocidos), capas nacionales filtradas a Región Metropolitana (código de región 13).
- **Formato**: Shapefile, CRS de origen EPSG:4326, geometría de puntos.
- **Unidad de observación**: establecimiento/sede educacional individual (punto).
- **Regla de limpieza (1.2.b)**: por nivel, separadamente — (1) descartar nombre nulo, (2) normalizar nombre (minúsculas, sin tildes/espacios extra), (3) agrupar por nombre normalizado, (4) dentro de cada grupo de nombre, aplicar DBSCAN espacial (umbral 1.5 km) para NO fusionar sedes homónimas que están realmente lejos, (5) cada cluster con 2+ puntos se reemplaza por su centroide geométrico.

| Nivel | Columna de nombre | Original (Chile) | En RM | Nombres nulos | Grupos homónimos | Fusionados | Final |
|---|---|---:|---:|---:|---:|---:|---:|
| Escolar | `NOM_RBD` | 11,285 | 2,918 | 0 | 2,897 | 2 | 2,916 |
| Parvularia | `NOM_ESTAB` | 11,951 | 3,254 | 0 | 3,133 | 2 | 3,252 |
| Superior | `NOMBRE_INS` | 1,297 | 526 | 0 | 89 | 333 | 193 |

### Ejemplos concretos de fusión por homonimia

- **Escolar/Parvularia**: "Colegio El Redentor" — 2 puntos a ~1.1 km de distancia (dentro del umbral de 1.5 km) se fusionan en un único centroide en UTM19S (336,704; 6,291,635).
- **Superior**: "Universidad de Chile" — **55 puntos** con el mismo nombre (correspondientes a distintas facultades/sedes del campus Beauchef/Juan Gómez Millas registradas como entradas separadas) se fusionan en un solo punto representativo en UTM19S (346,463; 6,298,396), porque todos caen dentro del umbral de 1.5 km. Este es el caso de fusión más grande del dataset y explica por qué educación superior pasa de 526 puntos en RM a solo 193 finales: las universidades grandes registran múltiples entradas por campus/facultad bajo el mismo nombre institucional.

---

## 3. Salud — Establecimientos de salud

- **Origen**: `l_990_v1_establecimientos_de_salud_febrero_2026.geojson` — registro de establecimientos de salud (MINSAL/observatorio georreferenciado), corte de febrero de 2026.
- **Formato**: GeoJSON, geometría de puntos.
- **Unidad de observación**: establecimiento de salud individual.
- **Regla de limpieza (1.2.c)**: validar `tipo` no nulo (normalizado a minúsculas/sin espacios), excluir 18 categorías que no representan atención presencial general (dental, diálisis, laboratorios, vacunatorios, atención remota, administrativas, etc. — ver `CATEGORIAS_EXCLUIDAS_SALUD` en `scripts/limpieza_salud.py`).

| | N |
|---|---:|
| Registros originales | 5,159 |
| Con `tipo` nulo (descartados) | 0 |
| Excluidos por categoría | 1,189 |
| **Finales** | **3,970** |

### Categorías excluidas (con conteo)

| Categoría | N | Categoría | N |
|---|---:|---|---:|
| dental | 330 | dialisis | 108 |
| laboratorio | 366 | vacunatorio | 112 |
| setm | 85 | movil | 48 |
| funcionarios | 47 | direccion_ss | 29 |
| prais | 29 | especialidad | 19 |
| conin | 5 | oficina_sanitaria | 3 |
| atencion_remota | 2 | cta | 2 |
| ambiental | 1 | radiologico | 1 |
| regulacion_samu | 1 | sangre_tejidos | 1 |

**Ejemplo concreto**: "Laboratorio Clínico de Agostini y Cia. Ltda." (`tipo` original = "Laboratorio Clínico") — excluido por pertenecer a la categoría `laboratorio` (la más numerosa entre las excluidas, 366 casos), ya que un laboratorio clínico no ofrece atención de salud presencial general relevante para accesibilidad residencial.

**Categorías conservadas (3,970)**: predominan `psr` (postas de salud rural, 1,115), `centro_salud_privado` (816), `cesfam` (605), `cecosf` (297), `hospital` (227), `sapu` (232), entre otras 17 categorías de atención presencial general.

---

## 4. metro.geojson — Estaciones de Metro de Santiago

- **Origen**: capa de estaciones de Metro de Santiago (incluye estaciones existentes, en construcción y proyectadas).
- **Formato**: GeoJSON, CRS EPSG:4326, geometría de puntos (NO líneas — ya son puntos de estación, no fue necesario derivarlos de un trazado).
- **Unidad de observación**: estación de Metro.
- **Volumen**: 124 registros totales. El atributo `estacion` (`EXISTENTE`/`EXSTENTE`/`CONSTRUCCION`/`PROYECTADO`) está **desactualizado en la fuente**: a la fecha de este análisis todas las estaciones de la red están operativas, incluidas las que la capa todavía marca como en construcción o proyectadas. Por eso se usan las **124 estaciones completas** para el cálculo de `dist_metro_m`/`count_metro_1km`, sin aplicar el filtro por estado (decisión confirmada por el equipo del proyecto, no un valor por defecto del pipeline).
- **Variables**: `linea` (Línea 1 a 6, incluida 4A), `nombre`, `estacion` (no usado como filtro, ver nota anterior), `especial` (intermodalidad).
- **Manejo de nulos**: 7 registros (5.6%) con metadatos nulos pero geometría válida; no afectan el cálculo de distancia.

---

## 5. Paradas_micro — Paraderos de la Red Metropolitana de Movilidad

- **Origen**: `SerFrec_Layer` — capa de paraderos con información de frecuencia de servicios de buses (RED Metropolitana).
- **Formato**: Shapefile, geometría de puntos. CRS de origen declarado como "unknown" en los metadatos del shapefile, pero sus parámetros (Transverse Mercator, meridiano central -69°, factor de escala 0.9996, falso este 500,000) son idénticos a UTM zona 19S — se asume y fuerza EPSG:32719.
- **Unidad de observación**: paradero de transporte público.
- **Volumen**: 12,096 registros, 39 comunas representadas, sin geometrías inválidas ni duplicadas.
- **Variables relevantes**: `FREPMA`/`FREPTA` (frecuencia punta mañana/tarde), `NSERVICIOS`/`SERVICIOS` (cantidad y listado de recorridos que pasan por el paradero), `N_ZP` (zona paga, 97.6% nula — solo aplica a corredores con zona paga).

---

## 6. Aeropuertos

- **Origen**: catastro nacional de aeródromos y aeropuertos de Chile (DGAC).
- **Formato**: Shapefile, CRS de origen EPSG:3857 (Web Mercator), geometría de puntos.
- **Unidad de observación**: aeródromo/aeropuerto individual, a nivel **nacional** (no solo RM) — 318 registros, categorías "Aeropuerto" y "Aeródromo".
- **Decisión de cobertura**: se usa la capa completa (no se filtra a la RM) porque el aeródromo más cercano a un predio en una comuna fronteriza con otra región podría estar fuera de la RM y aun así ser el relevante para el efecto de cercanía esperado.
- **Efecto esperado**: negativo sobre el avalúo (ruido, restricciones de altura de edificación, percepción de menor calidad ambiental), consistente con el marco de renta de localización.
- **Manejo de nulos**: `cod_iata` nulo en 84.9% de los registros (solo aeropuertos comerciales tienen código IATA); no afecta el cálculo de distancia.

---

## 7. red_vial — Clasificación de la Red Vial de la RM

- **Origen**: capa de clasificación funcional de la red vial estructurante de la Región Metropolitana (vías nacionales/regionales principales y secundarias).
- **Formato**: Shapefile, CRS de origen EPSG:3857, geometría de líneas.
- **Unidad de observación**: segmento de vía clasificada.
- **Volumen**: 479 segmentos, longitud total ≈ 3,016 km. Variables: `CARPETA` (tipo de pavimento: Pavimento, Pavimento Básico, Pavimento Doble Calzada, Ripio, Suelo Natural), `ROL`, `NOMBRE`, indicadores jerárquicos (`c_ppal`, `c_secund`, `nacional`, `reg_ppal`, `reg_prov`).
- **LIMITACIÓN DOCUMENTADA — por qué se usa distancia euclidiana y no distancia por red**: esta capa contiene solo 479 segmentos de vías clasificadas como estructurantes/arteriales regionales, **no la malla completa de calles locales**. La inmensa mayoría de los predios se conectan a la red mediante calles locales que esta capa no incluye, por lo que un cálculo de distancia por red (routing) sobre esta capa daría una falsa sensación de precisión: el "camino más corto" calculado ignoraría toda la red local real. Se usa entonces distancia euclidiana del centroide del predio al eje clasificado más cercano (`dist_red_vial_m`) como proxy de accesibilidad a la red vial estructurante, no como distancia de viaje real.

---

## 8. IPT_Metropolitana — Instrumento de Planificación Territorial

### 8.1 PRMS — Uso de Suelo (`IPT_13_PRMS_USO_Suelo.shp`)

- **Origen**: Plan Regulador Metropolitano de Santiago (PRMS), capa de uso de suelo normado.
- **Formato**: Shapefile, CRS de origen EPSG:32719 (ya proyectado), geometría de polígonos/multipolígonos.
- **Unidad de observación**: zona normativa de uso de suelo.
- **Volumen**: 1,750 polígonos. Variable usada: `UPREF` (uso preferente: Habitacional - Mixto, Equipamiento, Área Verde, Actividad Productiva, Hidrografía, Riesgo — 6 categorías, 9 valores nulos).
- **Geometrías inválidas**: 14, reparadas con `make_valid` antes del spatial join.
- **Uso en el pipeline**: se calcula la categoría `UPREF` dominante (moda) en un buffer de 250 m alrededor del centroide de cada predio → `uso_suelo_ipt`.

### 8.2 LU — Límite Urbano (`IPT_13_LU.shp`)

- **Origen**: límite urbano oficial vigente por comuna (PRMS y planes reguladores comunales).
- **Formato**: Shapefile, CRS EPSG:32719, polígonos. 65 registros, 1 geometría inválida.
- **Uso en el pipeline**: capa de referencia documental (la condición "urbana" del predio ya se obtiene directamente del atributo `ubicacion` de SII_2025, por lo que esta capa no se usa como filtro adicional, para evitar doble criterio de urbanidad).

---

## 9. topografia — Curvas de nivel (S34W071)

- **Origen**: curvas de nivel derivadas de modelo de elevación (probable SRTM, a juzgar por la convención de nombre de tile `S34W071`).
- **Formato**: Shapefile, CRS EPSG:4326, geometría de **líneas** (curvas de nivel con atributo `elevation`) — **NO es un raster DEM**, a pesar de que el nombre sugiere una celda SRTM; se verificó con `geom_type` antes de elegir el método de cálculo.
- **Cobertura**: una sola celda de 1°×1°, lat -34° a -33°, lon -71° a -70°. Rango de elevación 200-6,050 m (cubre desde el valle central hasta la precordillera andina).
- **Volumen**: 23,810 curvas de nivel, 2,262,073 vértices totales.
- **Método de cálculo de pendiente** (dado que es vectorial, no raster): se extraen los vértices de cada curva (heredando la elevación de su línea), se sub-muestrean a 1 de cada 3 (762,202 vértices usados) para mantener tratable la triangulación de Delaunay, se interpola linealmente (`scipy.interpolate.LinearNDInterpolator`) y se evalúa la elevación en el centroide de cada predio y en 4 puntos desplazados ±30 m (N/S/E/O) para estimar la pendiente local por diferencias finitas (`pendiente_pct`).
- **LIMITACIÓN DOCUMENTADA — cobertura parcial**: como la celda topográfica no cubre toda la RM (comunas al oeste de lon -71.0 como Melipilla, María Pinto, San Pedro, Curacaví, Alhué, o al sur de lat -34.0 como San José de Maipo quedan parcial/totalmente fuera), **2,179,436 de 2,212,777 predios (98.5%) obtienen elevación/pendiente válidas**; el resto recibe `NaN` y se documenta como dato faltante, no como cero.

---

## 10. RM.gpkg — Polígono de referencia

- **Origen**: no especificado en metadatos; geopackage con una sola capa `RM`.
- **Formato**: GeoPackage, CRS EPSG:20049 (PSAD56 / UTM zona 19S), 1 polígono, **sin atributos** (la tabla de atributos está vacía).
- **Extensión**: aproximadamente 49 km × 48 km — consistente con el área urbana del Gran Santiago, no con el límite administrativo completo de la Región Metropolitana (que es mucho mayor).
- **Uso en el pipeline**: ninguno como feature (no tiene atributos que aporten información); se documenta como posible capa de referencia del área de estudio, pero no se usa para filtrar ni enriquecer predios, dado que el filtro de "urbano" ya proviene de SII_2025 y sería redundante/menos preciso.

---

## 11. SII_2020 — Variable temporal (análisis, no feature de modelo)

- **Origen**: `SII_USOS_SUELO.shp`, agregación de uso de suelo del SII a nivel de **manzana censal**.
- **Hallazgo clave**: a diferencia de lo asumido inicialmente, **este archivo NO contiene predios individuales** — es un archivo pre-agregado por manzana (40,485 manzanas en la RM), con sumas de superficie por destino (`S_T_DEST_A` a `S_T_DEST_Z`) y avalúo total de la manzana (`Avaluo_rol`, `Conteo_pre` = cantidad de predios agregados). El campo `ANO_DRAW` (2013/2014/2016) indica que el levantamiento cartográfico de manzanas es de esa fecha, aunque los valores de avalúo se mantienen actualizados.
- **Por qué no se puede cruzar por ROL**: SII_2020 no tiene un identificador de predio compatible con el `rol` de SII_2025. El cruce temporal se resuelve **espacialmente**, no por ID.

### Método de cruce espacial aplicado

1. Filtrar manzanas 2020 con `UBICACION == "U"` (urbana) y `DESTINO == "H"` (predominantemente habitacional), `S_T_TOTAL > 0` y `Avaluo_rol > 0` → **36,149 de 40,485 manzanas** utilizables.
2. Calcular `avaluo_2020_per_m2_manzana = Avaluo_rol / S_T_TOTAL` (CLP/m² nominal de 2020).
3. Unir espacialmente (point-in-polygon) el centroide de cada predio 2025 con la manzana 2020 que lo contiene → **1,509,475 de 2,212,777 predios (68.2%)** logran asociarse a una manzana 2020 válida (el resto cae fuera de las manzanas filtradas o de la cobertura del shapefile).
4. `variacion_avaluo_pct_2020_2025 = (avaluo_2025_per_m2 − avaluo_2020_per_m2_manzana) / avaluo_2020_per_m2_manzana × 100`.

### Limitaciones documentadas (importantes)

- Es una comparación **predio-vs-promedio-de-su-manzana** (inferencia ecológica), no predio-contra-el-mismo-predio en el tiempo.
- Es en **pesos nominales**, sin ajuste por inflación 2020→2025.
- La distribución resultante es muy amplia y asimétrica (mediana +142%, pero rango de -99.99% a +21,857%), reflejo tanto del reavalúo no agrícola de 2022 (que produjo alzas reales de 100%+ en numerosas comunas) como de ruido propio de la agregación por manzana.
- **Por estas razones, esta variable se reporta como hallazgo de análisis territorial en `docs/resumen.md`, pero NO se usa como predictor en los modelos** (sección de modelamiento): además del ruido de inferencia ecológica, usarla como feature para predecir el avalúo 2025 introduciría fuga de información, ya que está parcialmente derivada del propio valor que se busca predecir.

---

## Resumen de features geoespaciales finales (`outputs/predios_con_features.parquet`)

| Feature | Unidad | Fuente | Cobertura (no-nulos) |
|---|---|---|---:|
| `dist_edu_escolar_m`, `count_edu_escolar_1km` | metros, conteo | educacion_escolar | 100% |
| `dist_edu_parvularia_m`, `count_edu_parvularia_1km` | metros, conteo | educacion_parvularia | 100% |
| `dist_edu_superior_m`, `count_edu_superior_1km` | metros, conteo | educacion_superior | 100% |
| `dist_salud_m`, `count_salud_1km` | metros, conteo | salud (depurado) | 100% |
| `dist_metro_m`, `count_metro_1km` | metros, conteo | metro.geojson (solo existentes) | 100% |
| `dist_micro_m`, `count_micro_500m`, `count_micro_1km` | metros, conteo | Paradas_micro | 100% |
| `dist_aeropuerto_m` | metros | Aeropuertos (nacional) | 100% |
| `dist_red_vial_m` | metros | red_vial (euclidiana, ver limitación) | 100% |
| `uso_suelo_ipt` | categoría | IPT PRMS (buffer 250m, moda) | 99.8% (0.2% SIN_DATO) |
| `elevacion_m`, `pendiente_pct` | metros, % | topografia (interpolado) | 98.5% |
| `avaluo_2020_per_m2_manzana`, `variacion_avaluo_pct_2020_2025` | CLP/m², % | SII_2020 (análisis, no feature de modelo) | 68.2% |
| `superficie_m2`, `log_superficie` | m², log(m²) | SII_2025 | 100% |
