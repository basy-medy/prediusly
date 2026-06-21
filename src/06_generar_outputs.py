"""
06_generar_outputs.py — Genera los archivos JSON de salida para la web.

Produce:
  - outputs/pipeline_steps.json — ejemplos REALES (no genéricos) de cada
    regla de limpieza, tomados de los JSON que cada script de limpieza
    capturó durante su ejecución (ejemplos_limpieza_predios.json,
    educacion_stats.json, ejemplos_limpieza_salud.json).
  - outputs/predictions.geojson — muestra de predicciones con geometría,
    incluyendo el top-3 de variables SHAP por predio.

Este script se ejecuta DESPUÉS de 05_modelos.py (y opcionalmente 05b_gwr.py).
"""
from __future__ import annotations
import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import geopandas as gpd
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent


def _cargar_json(rel_path: str) -> dict | None:
    path = BASE / "outputs" / rel_path
    if not path.exists():
        print(f"  ⚠ No encontrado: {path}")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generar_pipeline_steps() -> dict:
    """Genera ejemplos concretos (reales, no genéricos) de cada regla de limpieza."""
    embudo = _cargar_json("embudo_predios.json") or {}
    ejemplos_predios = _cargar_json("ejemplos_limpieza_predios.json") or {}
    edu_stats = _cargar_json("educacion_stats.json") or {}
    ejemplo_salud = _cargar_json("ejemplos_limpieza_salud.json") or {}
    salud_stats = _cargar_json("salud_stats.json") or {}
    model_comparison = _cargar_json("model_comparison.json") or {}

    n_crudo = embudo.get("01_total_cargados", 0)

    steps = {
        "etapas": [
            {
                "nombre": "Datos crudos",
                "descripcion": f"{n_crudo:,} registros de predios del SII (54 comunas de la Región Metropolitana)",
                "n_registros": n_crudo,
            },
            {
                "nombre": "Limpieza de predios",
                "descripcion": "Filtrado secuencial: atributos válidos → habitacional → urbano → superficie 50-20,000 m² → sin outliers de avalúo",
                "embudo": embudo,
                "reglas": [],
            },
            {
                "nombre": "Feature engineering geoespacial",
                "descripcion": "Cálculo de distancias y conteos a equipamiento urbano, uso de suelo, topografía y variable temporal para cada predio",
                "features_calculadas": [],
            },
            {
                "nombre": "Modelo",
                "descripcion": "Entrenamiento de 5 modelos (OLS, Random Forest, LightGBM, XGBoost, GWR) con validación cruzada espacial por comuna",
                "comparacion_modelos": model_comparison,
            },
            {
                "nombre": "Predicción",
                "descripcion": "Avalúo fiscal predicho para cada predio, con el top-3 de variables SHAP que más influyeron en su predicción individual",
            },
        ],
        "ejemplos_limpieza": {},
    }

    # ── Reglas de limpieza de predios, con ejemplos REALES capturados ──
    def _ej(paso_key, default_motivo):
        e = ejemplos_predios.get(paso_key)
        if not e:
            return default_motivo
        v = e["valores"]
        partes = [f"{k}={val}" for k, val in v.items() if val is not None]
        return f"Caso real — rol {v.get('rol', '?')} ({v.get('nombreComuna', '?')}): " + ", ".join(partes)

    if embudo:
        steps["etapas"][1]["reglas"] = [
            {
                "paso": 1,
                "nombre": "Atributos válidos",
                "descripcion": "Descartar predios sin destinoDescripcion, ubicacion o pol_area_m2",
                "descartados": embudo["01_total_cargados"] - embudo["02_con_atributos_validos"],
                "ejemplo": _ej("01_atributos_nulos", "Un predio sin destino ni superficie no puede clasificarse ni evaluarse"),
            },
            {
                "paso": 2,
                "nombre": "Filtro Habitacional",
                "descripcion": "Solo predios con destinoDescripcion == 'HABITACIONAL'",
                "descartados": embudo["02_con_atributos_validos"] - embudo["03_habitacional"],
                "ejemplo": _ej("02_no_habitacional", "Se excluyen predios agrícolas, comerciales, industriales, etc."),
            },
            {
                "paso": 3,
                "nombre": "Filtro Urbano",
                "descripcion": "Solo predios con ubicacion == 'URBANA'",
                "descartados": embudo["03_habitacional"] - embudo["04_urbana"],
                "ejemplo": _ej("03_no_urbano", "Predios rurales quedan fuera porque su avalúo responde a lógica agrícola, no urbana"),
            },
            {
                "paso": 4,
                "nombre": "Rango de superficie",
                "descripcion": "50 ≤ superficie ≤ 20,000 m²",
                "descartados": embudo["04_urbana"] - embudo["05_rango_superficie"],
                "ejemplo": _ej("04_fuera_rango_superficie", "Predios fuera de rango suelen ser errores de digitalización catastral"),
            },
            {
                "paso": 5,
                "nombre": "Outliers de avalúo",
                "descripcion": "Remoción de avalúos extremos (percentil 1-99 POR COMUNA, no a nivel RM)",
                "descartados": embudo["05_rango_superficie"] - embudo["07_sin_outliers_avaluo"],
                "ejemplo": _ej("05_outlier_avaluo", "Avalúos extremos dentro de su propia comuna se consideran atípicos"),
            },
        ]

    # ── Educación: ejemplo real de fusión por homonimia ──────────────
    if edu_stats:
        steps["ejemplos_limpieza"]["educacion"] = {
            "regla": "Clustering espacial por homonimia (DBSCAN, threshold 1.5 km) — aplicado por separado en cada nivel",
            "niveles": {},
        }
        for nivel, stats in edu_stats.items():
            ej_fusion = stats.get("_ejemplo_fusion")
            ejemplo_txt = None
            if ej_fusion:
                n_pts = ej_fusion["n_puntos_originales"]
                ejemplo_txt = (
                    f"\"{ej_fusion['nombre_institucion'].title()}\": {n_pts} puntos con el mismo "
                    f"nombre dentro de 1.5 km se fusionaron en un solo punto representativo "
                    f"(centroide en UTM19S: {ej_fusion['centroide_resultante_utm19s']['x']:.0f}, "
                    f"{ej_fusion['centroide_resultante_utm19s']['y']:.0f})."
                )
            steps["ejemplos_limpieza"]["educacion"]["niveles"][nivel] = {
                "original": stats.get("n_original", 0),
                "en_rm": stats.get("n_rm", 0),
                "grupos_homonimos": stats.get("n_grupos_homonimos", 0),
                "fusionados": stats.get("n_fusionados", 0),
                "final": stats.get("n_final", 0),
                "ejemplo": ejemplo_txt or f"En educación {nivel}, {stats.get('n_fusionados', 0)} puntos fueron fusionados por homonimia.",
            }

    # ── Salud: ejemplo real de exclusión por categoría ───────────────
    if salud_stats:
        ejemplo_txt = "Se excluyen establecimientos sin atención presencial general relevante para accesibilidad."
        if ejemplo_salud:
            ejemplo_txt = (
                f"\"{ejemplo_salud['nombre_establecimiento']}\" (tipo original: "
                f"\"{ejemplo_salud['tipo_original']}\") — excluido por pertenecer a la categoría "
                f"'{ejemplo_salud['categoria_normalizada']}', la más numerosa entre las excluidas "
                f"({ejemplo_salud['n_registros_en_categoria']} casos)."
            )
        steps["ejemplos_limpieza"]["salud"] = {
            "regla": "Exclusión por categoría de tipo (18 categorías excluidas)",
            "original": salud_stats.get("n_original"),
            "excluidos": salud_stats.get("n_excluidos_categoria"),
            "final": salud_stats.get("n_final"),
            "conteo_excluidos": salud_stats.get("conteo_excluidos"),
            "ejemplo": ejemplo_txt,
        }

    # ── Descripción de features (incluye las nuevas: red_vial, topografía, temporal) ──
    steps["etapas"][2]["features_calculadas"] = [
        {"nombre": "dist_edu_escolar_m", "descripcion": "Distancia euclidiana al establecimiento escolar más cercano (metros)"},
        {"nombre": "count_edu_escolar_1km", "descripcion": "Cantidad de establecimientos escolares dentro de 1 km"},
        {"nombre": "dist_edu_parvularia_m", "descripcion": "Distancia al jardín infantil/parvulario más cercano"},
        {"nombre": "count_edu_parvularia_1km", "descripcion": "Cantidad de parvularios dentro de 1 km"},
        {"nombre": "dist_edu_superior_m", "descripcion": "Distancia a la institución de educación superior más cercana"},
        {"nombre": "count_edu_superior_1km", "descripcion": "Cantidad de instituciones superiores dentro de 1 km"},
        {"nombre": "dist_salud_m", "descripcion": "Distancia al establecimiento de salud más cercano (filtrado, sin categorías excluidas)"},
        {"nombre": "count_salud_1km", "descripcion": "Cantidad de establecimientos de salud dentro de 1 km"},
        {"nombre": "dist_metro_m", "descripcion": "Distancia a la estación de Metro más cercana (solo existentes, no proyectadas)"},
        {"nombre": "count_metro_1km", "descripcion": "Cantidad de estaciones de Metro dentro de 1 km"},
        {"nombre": "dist_micro_m", "descripcion": "Distancia a la parada de micro/bus más cercana"},
        {"nombre": "count_micro_500m", "descripcion": "Cantidad de paradas de micro dentro de 500 m"},
        {"nombre": "count_micro_1km", "descripcion": "Cantidad de paradas de micro dentro de 1 km"},
        {"nombre": "dist_aeropuerto_m", "descripcion": "Distancia al aeropuerto/aeródromo más cercano (efecto negativo esperado)"},
        {"nombre": "dist_red_vial_m", "descripcion": "Distancia euclidiana al eje de la red vial clasificada más cercano (no es distancia por red, ver limitación documentada)"},
        {"nombre": "uso_suelo_ipt", "descripcion": "Uso de suelo dominante según Plan Regulador Metropolitano (buffer 250m)"},
        {"nombre": "elevacion_m", "descripcion": "Elevación interpolada desde curvas de nivel (cobertura 98.5% de la RM)"},
        {"nombre": "pendiente_pct", "descripcion": "Pendiente local estimada por diferencias finitas sobre la elevación interpolada"},
        {"nombre": "superficie_m2", "descripcion": "Superficie del polígono del predio en m²"},
        {"nombre": "centroid_x", "descripcion": "Coordenada X del centroide (UTM zona 19S, metros)"},
        {"nombre": "centroid_y", "descripcion": "Coordenada Y del centroide (UTM zona 19S, metros)"},
        {"nombre": "variacion_avaluo_pct_2020_2025", "descripcion": "Variación % de avalúo entre 2020 (manzana) y 2025 (predio). Variable de análisis territorial, NO usada como predictor del modelo (ver limitación en data_dictionary.md)."},
    ]

    return steps


def generar_predictions_geojson():
    """
    Genera un GeoJSON con muestra de predicciones para la web.
    Usa exactamente la muestra para la que 05_modelos.py calculó SHAP por
    predio (columna shap_top3 no nula), para que cada predio del GeoJSON
    tenga su explicación SHAP disponible.
    """
    pred_path = BASE / "outputs" / "predictions.parquet"
    if not pred_path.exists():
        print("  ⚠ predictions.parquet no existe, se omite geojson")
        return

    gdf = gpd.read_parquet(pred_path)

    if "shap_top3" in gdf.columns and gdf["shap_top3"].notna().any():
        gdf_sample = gdf[gdf["shap_top3"].notna()].copy()
        print(f"  Muestra con SHAP por predio disponible: {len(gdf_sample):,}")
    else:
        # Fallback: muestreo estratificado por comuna si no hubiese SHAP por predio
        sample_dfs = []
        for comuna, grupo in gdf.groupby("nombre_comuna"):
            n = min(500, len(grupo))
            sample_dfs.append(grupo.sample(n, random_state=42))
        gdf_sample = pd.concat(sample_dfs)
        print(f"  ⚠ Sin columna shap_top3; muestra estratificada sin SHAP: {len(gdf_sample):,}")

    cols = [
        "rol", "nombre_comuna", "superficie_m2", "avaluo_fiscal",
        "avaluo_predicho", "residual", "residual_pct",
        "dist_metro_m", "dist_salud_m", "dist_edu_escolar_m",
        "dist_edu_parvularia_m", "dist_edu_superior_m",
        "dist_micro_m", "dist_aeropuerto_m", "dist_red_vial_m",
        "count_metro_1km", "count_salud_1km",
        "uso_suelo_ipt", "elevacion_m", "pendiente_pct",
        "variacion_avaluo_pct_2020_2025",
        "shap_top3",
        "geometry",
    ]
    available_cols = [c for c in cols if c in gdf_sample.columns]

    gdf_out = gdf_sample[available_cols].copy()
    gdf_out = gdf_out.to_crs("EPSG:4326")

    out_path = BASE / "outputs" / "predictions.geojson"
    gdf_out.to_file(out_path, driver="GeoJSON")
    print(f"  Exportado → {out_path} ({len(gdf_out):,} predios)")


def main():
    print("=" * 80)
    print("  PIPELINE 06 — Generación de outputs para la web")
    print("=" * 80)

    print("\n  Generando pipeline_steps.json...")
    steps = generar_pipeline_steps()
    steps_path = BASE / "outputs" / "pipeline_steps.json"
    with open(steps_path, "w", encoding="utf-8") as f:
        json.dump(steps, f, indent=2, ensure_ascii=False)
    print(f"  → {steps_path}")

    print("\n  Generando predictions.geojson...")
    generar_predictions_geojson()

    print("\n✔ Pipeline 06 completado.")


if __name__ == "__main__":
    main()
