# Resumen — Prediusly

## 1. Problema sustantivo

Predecir el **avalúo fiscal** de predios habitacionales urbanos en la Región
Metropolitana de Chile a partir de variables geoespaciales de accesibilidad
y equipamiento urbano, y explicar qué tan bien (y dónde) ese avalúo puede
anticiparse solo con la posición del predio en la ciudad.

El problema no es solo "ajustar un modelo de ML a datos catastrales": el
suelo urbano es un **bien heterogéneo** — no hay dos predios idénticos,
cada uno ocupa una posición irrepetible en el espacio — y la teoría de
**renta de localización** (von Thünen) y **bid-rent** (Alonso) predice que
el valor decae con la distancia a centros de actividad, probablemente de
forma no lineal, y que la concentración de equipamiento genera plusvalía
adicional por **economías de aglomeración** más allá de la simple
distancia. El objetivo es verificar empíricamente, a escala de predio
individual y con datos reales de la RM, si esa teoría se sostiene y cuánto
poder predictivo aporta.

## 2. Preguntas medibles

1. ¿Qué proporción de la varianza del avalúo fiscal de un predio habitacional
   urbano puede explicarse solo con variables de accesibilidad (educación,
   salud, transporte, aeropuertos, red vial), uso de suelo, topografía y
   superficie — sin variables de la edificación misma?
2. ¿El efecto de la distancia a equipamiento es lineal o decae de forma no
   lineal (consistente con bid-rent)? — respondida por el modelo ganador
   (LightGBM, no lineal por construcción) vs. el baseline OLS (lineal).
3. ¿El efecto de cada variable de accesibilidad es **espacialmente
   estacionario** (mismo efecto en toda la RM) o varía por zona? — respondida
   con GWR sobre una muestra representativa.
4. ¿Qué variable de accesibilidad pesa más en la predicción (SHAP), y es
   consistente con la jerarquía teórica esperada (metro > microbuses,
   aeropuerto con efecto negativo)?
5. ¿En qué comunas el modelo predice mejor y en cuáles peor, y por qué?

## 3. Datos usados

13 fuentes geoespaciales reales (ver ficha completa de cada una, con
origen/fecha/cobertura/CRS/manejo de calidad, en `docs/data_dictionary.md`):
SII_2025 (fuente principal: predios + avalúo + geometría), SII_2020 (variable
temporal, nivel manzana), educación escolar/parvularia/superior, salud,
metro, paradas de micro, aeropuertos, red vial, IPT Metropolitana (PRMS uso
de suelo + límite urbano), topografía (curvas de nivel) y RM.gpkg
(referencia, sin atributos, no usado como feature).

Todas las capas se reproyectaron a **EPSG:32719** antes de cualquier cálculo
de distancia/área/buffer.

## 4. Reglas de limpieza aplicadas (resumen — detalle completo en data_dictionary.md)

- **Predios (SII_2025)**: filtro secuencial — atributos no nulos → destino
  HABITACIONAL → ubicación URBANA → superficie 50-20,000 m² → reparación de
  geometrías inválidas (170 casos) → remoción de outliers de avalúo por
  percentil 1-99 **dentro de cada comuna**. De 3,789,659 predios crudos
  quedan **2,212,777** predios habitacionales urbanos analizados.
- **Educación** (escolar/parvularia/superior, por separado): clustering
  espacial por homonimia (DBSCAN, 1.5 km) — el caso más relevante es
  "Universidad de Chile", con 55 puntos del mismo nombre fusionados en un
  solo punto representativo, lo que explica por qué educación superior pasa
  de 526 puntos en RM a solo 193 finales.
- **Salud**: exclusión de 18 categorías sin atención presencial general
  (1,189 de 5,159 registros excluidos — dental, laboratorios, diálisis,
  vacunatorios, etc.), quedando 3,970 establecimientos relevantes para
  accesibilidad.
- **SII_2020**: se descubrió que esta fuente está agregada a nivel de
  manzana censal, no de predio individual, por lo que el cruce temporal con
  SII_2025 se resolvió espacialmente (point-in-polygon), no por ID. La
  variable resultante (`variacion_avaluo_pct_2020_2025`) se reporta como
  hallazgo de análisis territorial (sección 6) pero **no se usó como
  predictor del modelo** por su fuerte inferencia ecológica y riesgo de fuga
  de información.

## 5. Modelo elegido

Se entrenaron y compararon 5 modelos sobre el mismo set de ~21 features
(distancias/conteos por categoría, uso de suelo, pendiente/elevación,
superficie, coordenadas), con **validación cruzada espacial (5-fold por
comuna, nunca k-fold aleatorio puro)**:

| Modelo | R² | RMSE (CLP) | MAPE | Comentario |
|---|---:|---:|---:|---|
| OLS (baseline hedónico) | 0.429 | $196.8M | 46.9% | Lineal, interpretable, pero con error 4x mayor que el ganador |
| Random Forest | 0.401 | $54.0M | 47.5% | Peor R² que LightGBM/XGBoost con este set de hiperparámetros |
| **LightGBM (tuneado con Optuna)** | **0.587** | **$51.2M** | **37.6%** | 🏆 **Ganador** |
| XGBoost | 0.526 | $50.3M | 42.9% | Muy cercano a LightGBM en RMSE, pero R² y MAPE algo peores |
| GWR (mgwr, muestra n=3,034) | 0.161 (test espacial) | $302.4M | 84.2% | Ver nota de escala abajo |

**Justificación del ganador (LightGBM)**: mejor R² y MAPE de los cinco, con
RMSE muy similar al de XGBoost. Frente a OLS, confirma que la relación entre
accesibilidad y avalúo **no es lineal** (consistente con bid-rent no
lineal): un modelo de árboles con interacciones captura mucho mejor la
heterogeneidad del suelo urbano que una combinación lineal de distancias.
Se sacrifica interpretabilidad directa de coeficientes, pero se recupera con
SHAP (importancia global y por predio).

**Tuning de hiperparámetros (Optuna)**: se corrió una búsqueda de 30 trials
por modelo (Random Forest, LightGBM, XGBoost) con `optuna` sobre una
muestra estratificada por comuna de ~100,000 predios, usando validación
cruzada espacial de 3 folds dentro de cada trial (mismo principio de "nunca
k-fold aleatorio puro"). LightGBM tuneado fue la mejor combinación
(`n_estimators=600, max_depth=12, learning_rate=0.0203, num_leaves=65,
min_child_samples=41, subsample=0.995, colsample_bytree=0.646,
reg_alpha=1.49, reg_lambda=0.027`), y al reentrenarlo sobre el dataset
completo de 2.2M predios con 5-fold espacial superó al LightGBM con
hiperparámetros fijos (R²=0.587 vs. 0.576), por lo que pasó a ser el modelo
de producción. El detalle completo de los 90 trials está en
`outputs/optuna_trials.json` y el resumen en `docs/_optuna_grid.md`.

**Nota sobre GWR**: por la complejidad O(n²) de `mgwr` (matriz de pesos n×n
y búsqueda de bandwidth con ~20-30 reentrenamientos), GWR se evaluó sobre
una muestra estratificada de 3,034 predios, con un split espacial único
(80/20 por comuna, no 5-fold completo) por costo computacional. Su R² alto
**dentro** de la muestra de entrenamiento (0.72 in-sample) pero bajo en
comunas excluidas (0.16) es en sí mismo un hallazgo: la regresión
geográficamente ponderada ajusta muy bien localmente pero generaliza mal a
ubicaciones sin vecinos de entrenamiento cercanos — el clásico trade-off
interpretabilidad-espacial vs. capacidad de generalización. GWR no se usó
para las 2.2M predicciones de producción; se usó para estudiar
no-estacionariedad de coeficientes (punto 6.3).

## 6. Hallazgos territoriales

### 6.1 Importancia de variables (SHAP global, modelo LightGBM)

Top variables por importancia SHAP del modelo final (LightGBM tuneado con
Optuna, `outputs/shap_global.json`):

1. `centroid_x` (0.137) y `centroid_y` (0.065) — la **posición misma**
   dentro de la RM es el predictor más fuerte, lo esperado bajo bid-rent: el
   "dónde" domina sobre cualquier variable de accesibilidad individual.
2. `count_edu_parvularia_1km` (0.120) — concentración de oferta de
   parvularios en el entorno inmediato, evidencia de **economías de
   aglomeración** (no solo la distancia al más cercano importa, sino la
   densidad de oferta).
3. `superficie_m2` (0.112) — atributo propio del predio.
4. `dist_edu_superior_m` (0.060) y `elevacion_m` (0.055) — accesibilidad a
   educación superior y altura del sector (comunas precordilleranas/altas
   como Las Condes, Lo Barnechea, La Reina tienden a mayor valor).
5. **Transporte — hallazgo revisado tras corregir la capa de Metro**: con
   las 124 estaciones completas (ver sección de limpieza de datos), la
   importancia individual de `dist_metro_m` (0.035) ya no supera
   claramente a la de microbuses: sumando sus tres variables
   (`dist_micro_m` + `count_micro_500m` + `count_micro_1km` = 0.058) el
   conjunto de variables de microbuses pesa **más** que el conjunto de
   variables de metro (`dist_metro_m` + `count_metro_1km` = 0.049). Esto
   matiza la hipótesis inicial: con la red de Metro ya consolidada (más
   estaciones contando como accesibles), su efecto marginal se diluye un
   poco porque hay menos variabilidad espacial en "estar cerca o lejos" de
   una estación — mientras que la densidad de paraderos de microbuses sigue
   siendo muy heterogénea entre comunas y por eso retiene más poder
   predictivo.
6. `dist_aeropuerto_m` (0.035) — con signo consistente con el efecto
   negativo esperado de la cercanía a aeropuertos, y ahora ligeramente por
   sobre la importancia de `dist_metro_m` individual.

### 6.2 Dónde predice mejor y peor el modelo (MAPE mediano por comuna, ≥1,000 predios)

**Mejor predicho** (menor error, comunas grandes y relativamente
homogéneas en su parque habitacional): Quilicura (10.1%), Puente Alto
(10.3%), Maipú (11.2%), Paine (12.8%), Colina (13.1%).

**Peor predicho**: San José de Maipo (32.7% — comuna rural-cordillerana,
poca muestra y cobertura topográfica parcial en sus bordes), Providencia
(26.0%), El Monte (25.2%), Santiago Oeste (22.7%), Lo Barnechea (22.3%),
Santiago (22.2%), San Ramón (21.7%), Ñuñoa (21.6%).

**Patrón sistemático**: en las comunas peor predichas y de mayor densidad
(Providencia, Santiago, Ñuñoa, San Ramón) el residual medio es
**negativo** (el modelo **subestima** el avalúo real, entre -5.1% y -8.3%
en promedio). La explicación más plausible: estas comunas concentran
edificación en altura (departamentos), y las features de este modelo son
casi todas de **accesibilidad y terreno** — no se incluyeron variables de la
edificación (`pisos_max`, `sup_construida_total`, antigüedad), que sí están
disponibles en SII_2025 pero no se incorporaron en esta iteración. La
plusvalía de un edificio en altura no se explica solo por su ubicación y el
tamaño de su lote, sino por cuántos m² construidos contiene — variable que
el modelo actual no ve directamente. **Próxima iteración recomendada**:
incorporar `pisos_max`/`sup_construida_total`/antigüedad como features para
reducir este sesgo sistemático en comunas de alta densidad vertical.

### 6.3 No-estacionariedad espacial (GWR)

Los coeficientes locales de GWR muestran alta variabilidad espacial,
especialmente en `dist_metro_m` (media -0.32, pero rango de -7.61 a +6.86
entre las distintas ubicaciones de la muestra) y `dist_micro_m` (media
+1.08, rango -7.50 a +9.16). Esto es evidencia directa de que el efecto de
la accesibilidad de transporte **no es constante en el espacio**: en
algunas zonas la cercanía al metro se asocia fuertemente con mayor valor, en
otras el efecto se diluye o incluso se invierte (zonas donde la cercanía al
metro coincide con ejes de alta congestión/comercio denso, percibidos como
menos deseables residencialmente). Esto confirma empíricamente, para esta
ciudad, la intuición de bid-rent heterogéneo del marco teórico: la pendiente
de la curva de renta de localización no es la misma en todas las
direcciones desde el centro.

### 6.4 Variación temporal de avalúo 2020→2025 (análisis separado, no feature del modelo)

La variación nominal mediana de avalúo por m² entre la manzana 2020 y el
predio 2025 es de **+142%**, consistente con el reavalúo no agrícola de
2022 que produjo alzas nominales importantes en gran parte de la RM. La
distribución es muy amplia (rango -99.99% a +21,857%) por la combinación de
inferencia ecológica (predio vs. promedio de su manzana) y falta de ajuste
por inflación — se reporta como contexto, no como conclusión cuantitativa
fina.

## Anexo — Grilla completa de hiperparámetros (Optuna)

Búsqueda sobre una muestra estratificada por comuna de 98,495 predios
(`outputs/predios_con_features.parquet` con datos completos), 30 trials por
modelo, validación cruzada espacial de 3 folds por comuna dentro de cada
trial. Métrica optimizada: R² en escala log. Los 90 trials completos (todas
las combinaciones probadas, no solo la mejor) están en
`outputs/optuna_trials.json`.

| Modelo | Mejor R² (CV muestra) | Mejores hiperparámetros |
|---|---:|---|
| Random Forest | 0.5513 | `n_estimators=500, max_depth=15, min_samples_leaf=15, max_features=0.303` |
| **LightGBM** 🏆 | **0.5595** | `n_estimators=600, max_depth=12, learning_rate=0.0203, num_leaves=65, min_child_samples=41, subsample=0.995, colsample_bytree=0.646, reg_alpha=1.490, reg_lambda=0.027` |
| XGBoost | 0.5560 | `n_estimators=600, max_depth=4, learning_rate=0.0839, subsample=0.695, colsample_bytree=0.647, reg_alpha=0.373, reg_lambda=3.743` |

LightGBM fue la mejor combinación tanto en la muestra de búsqueda (0.5595)
como, de forma consistente, al reentrenarse sobre el dataset completo de
2.2M predios (R²=0.587, sección 5) — por eso es el modelo de producción
final, reemplazando al LightGBM con hiperparámetros fijos usado en la
primera iteración del proyecto.
