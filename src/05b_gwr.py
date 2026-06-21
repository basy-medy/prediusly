"""
05b_gwr.py — Regresión Geográficamente Ponderada (GWR) vía mgwr.

GWR estima un set de coeficientes LOCALES (uno por ubicación), capturando
no-estacionariedad espacial (ej. el efecto de dist_metro_m puede ser distinto
en Las Condes que en Puente Alto) — esto es justamente lo que predice el
marco teórico de bid-rent/renta de localización: el gradiente de precio vs.
distancia no es necesariamente constante en el espacio.

LIMITACIÓN DE ESCALA (documentada): mgwr.GWR tiene complejidad O(n²) en el
número de observaciones de calibración (matriz de pesos n×n) y la búsqueda
de bandwidth (Sel_BW) reentrena el modelo ~20-30 veces. Esto es intratable
para los ~2.2M predios del dataset completo. Por eso GWR se entrena y valida
sobre una MUESTRA representativa estratificada por comuna (~3,000 predios),
y se reporta como modelo complementario interpretativo (para entender
no-estacionariedad espacial), no como el modelo de producción usado para
generar predictions.geojson a escala completa.

Validación: split espacial único 80/20 por comuna (no k-fold completo, por
costo computacional de repetir la búsqueda de bandwidth 5 veces).

Exporta:
  - outputs/gwr_results.json (métricas + resumen de coeficientes locales)
  - Actualiza outputs/model_comparison.json agregando la entrada "GWR"
    (ejecutar DESPUÉS de 05_modelos.py, que regenera ese archivo).
"""
from __future__ import annotations
import sys
import time
import json
import warnings
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_percentage_error

BASE = Path(__file__).resolve().parent.parent

N_MUESTRA_OBJETIVO = 3000
RANDOM_STATE = 42

# Predictores continuos para GWR (se excluyen categóricas: mgwr.GWR
# trabaja mejor con covariables numéricas; uso_suelo_ipt/nombre_comuna no
# se incluyen para mantener la búsqueda de bandwidth tratable).
GWR_FEATURES = [
    "log_superficie",
    "dist_edu_escolar_m",
    "dist_edu_parvularia_m",
    "dist_edu_superior_m",
    "dist_salud_m",
    "dist_metro_m",
    "dist_micro_m",
    "dist_aeropuerto_m",
    "dist_red_vial_m",
    "pendiente_pct",
]
TARGET = "log_avaluo"


def muestreo_estratificado_por_comuna(gdf: gpd.GeoDataFrame, n_objetivo: int) -> gpd.GeoDataFrame:
    """Muestra proporcional por comuna, con mínimo de 10 predios por comuna si están disponibles."""
    n_total = len(gdf)
    partes = []
    for comuna, grupo in gdf.groupby("nombre_comuna"):
        n_prop = max(10, round(n_objetivo * len(grupo) / n_total))
        n = min(n_prop, len(grupo))
        partes.append(grupo.sample(n, random_state=RANDOM_STATE))
    return pd.concat(partes)


def split_espacial_por_comuna(gdf: gpd.GeoDataFrame, frac_test: float = 0.2):
    """Separa un 20% de las COMUNAS (no de los predios) como test espacial."""
    comunas = sorted(gdf["nombre_comuna"].unique())
    rng = np.random.RandomState(RANDOM_STATE)
    comunas_shuffled = rng.permutation(comunas)
    n_test = max(1, round(len(comunas) * frac_test))
    comunas_test = set(comunas_shuffled[:n_test])
    mask_test = gdf["nombre_comuna"].isin(comunas_test)
    return gdf[~mask_test].copy(), gdf[mask_test].copy(), sorted(comunas_test)


def main():
    t0 = time.time()
    print("=" * 80)
    print("  PIPELINE 05b — Regresión Geográficamente Ponderada (GWR)")
    print("=" * 80)

    from mgwr.gwr import GWR
    from mgwr.sel_bw import Sel_BW

    # ── 1. Cargar datos y preparar muestra ──────────────────────────
    feat_path = BASE / "outputs" / "predios_con_features.parquet"
    gdf = gpd.read_parquet(feat_path)

    cols_necesarias = GWR_FEATURES + [TARGET, "nombre_comuna", "centroid_x", "centroid_y"]
    gdf = gdf.dropna(subset=cols_necesarias).copy()
    print(f"  Predios con datos completos para GWR: {len(gdf):,}")

    muestra = muestreo_estratificado_por_comuna(gdf, N_MUESTRA_OBJETIVO)
    print(f"  Muestra estratificada por comuna: {len(muestra):,} predios, "
          f"{muestra['nombre_comuna'].nunique()} comunas")

    train, test, comunas_test = split_espacial_por_comuna(muestra, frac_test=0.2)
    print(f"  Train: {len(train):,} predios  |  Test (comunas excluidas): {len(test):,} predios")
    print(f"  Comunas en test: {comunas_test}")

    # ── 2. Estandarizar predictores (z-score con medias/std del train) ──
    means = train[GWR_FEATURES].mean()
    stds = train[GWR_FEATURES].std().replace(0, 1)

    X_train = ((train[GWR_FEATURES] - means) / stds).values
    X_test = ((test[GWR_FEATURES] - means) / stds).values
    y_train = train[TARGET].values.reshape(-1, 1)
    y_test = test[TARGET].values.reshape(-1, 1)
    coords_train = list(zip(train["centroid_x"].values, train["centroid_y"].values))
    coords_test = list(zip(test["centroid_x"].values, test["centroid_y"].values))

    # ── 3. Búsqueda de bandwidth y ajuste ───────────────────────────
    print("\n  Buscando bandwidth óptimo (Sel_BW)...")
    sel = Sel_BW(coords_train, y_train, X_train)
    bw = sel.search()
    print(f"  Bandwidth óptimo: {bw:.1f} predios vecinos")

    print("  Ajustando GWR sobre el set de entrenamiento...")
    gwr_model = GWR(coords_train, y_train, X_train, bw)
    gwr_results = gwr_model.fit()
    print(f"  R² (in-sample, train): {gwr_results.R2:.4f}")
    print(f"  R² local — media: {gwr_results.localR2.mean():.4f}, "
          f"min: {gwr_results.localR2.min():.4f}, max: {gwr_results.localR2.max():.4f}")

    # ── 4. Predicción fuera de muestra (comunas excluidas) ──────────
    print("\n  Prediciendo en comunas excluidas (test espacial)...")
    pred_results = gwr_model.predict(np.array(coords_test), X_test)
    y_pred_log = pred_results.predictions.flatten()

    r2_test = r2_score(y_test.flatten(), y_pred_log)
    rmse_log = np.sqrt(mean_squared_error(y_test.flatten(), y_pred_log))
    y_true_orig = np.expm1(y_test.flatten())
    y_pred_orig = np.expm1(y_pred_log)
    rmse_clp = np.sqrt(mean_squared_error(y_true_orig, y_pred_orig))
    mask_pos = y_true_orig > 0
    mape = mean_absolute_percentage_error(y_true_orig[mask_pos], y_pred_orig[mask_pos]) * 100

    print(f"  R² (test espacial): {r2_test:.4f}")
    print(f"  RMSE (CLP): ${rmse_clp:,.0f}")
    print(f"  MAPE: {mape:.1f}%")

    # ── 5. Resumen de no-estacionariedad de coeficientes locales ────
    coef_summary = {}
    for i, feat in enumerate(GWR_FEATURES):
        local_coefs = gwr_results.params[:, i + 1]  # columna 0 es el intercepto
        coef_summary[feat] = {
            "media": round(float(local_coefs.mean()), 4),
            "std": round(float(local_coefs.std()), 4),
            "min": round(float(local_coefs.min()), 4),
            "max": round(float(local_coefs.max()), 4),
        }

    # ── 6. Exportar resultados ───────────────────────────────────────
    output_dir = BASE / "outputs"
    resultado = {
        "bandwidth_optimo": float(bw),
        "n_train": len(train),
        "n_test": len(test),
        "comunas_test": comunas_test,
        "R2_train_local_media": round(float(gwr_results.localR2.mean()), 4),
        "R2_test_espacial": round(float(r2_test), 4),
        "RMSE_CLP_test": round(float(rmse_clp), 0),
        "MAPE_pct_test": round(float(mape), 2),
        "coeficientes_locales_resumen": coef_summary,
        "nota": (
            "GWR evaluado sobre muestra estratificada por comuna "
            f"(n={len(muestra)}) por restricciones de escala computacional "
            "(O(n^2) en mgwr). No participa como candidato a 'modelo ganador' "
            "de producción para las 2.2M predicciones completas; se usa para "
            "analizar no-estacionariedad espacial de los coeficientes "
            "(evidencia de bid-rent no lineal/heterogéneo en el espacio)."
        ),
    }
    gwr_path = output_dir / "gwr_results.json"
    with open(gwr_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    print(f"\n  Resultados GWR → {gwr_path}")

    # ── 7. Agregar entrada "GWR" a model_comparison.json ────────────
    comp_path = output_dir / "model_comparison.json"
    if comp_path.exists():
        with open(comp_path, encoding="utf-8") as f:
            comparison = json.load(f)
    else:
        comparison = {}

    comparison["GWR"] = {
        "R2": round(float(r2_test), 4),
        "RMSE_log": round(float(rmse_log), 4),
        "RMSE_CLP": round(float(rmse_clp), 0),
        "MAPE_pct": round(float(mape), 2),
        "ganador": False,
        "nota": resultado["nota"],
        "n_muestra": len(muestra),
    }
    with open(comp_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    print(f"  Entrada GWR agregada a → {comp_path}")

    elapsed = time.time() - t0
    print(f"\n  Tiempo total: {elapsed:.1f} segundos")
    print("\n✔ Pipeline 05b completado.")


if __name__ == "__main__":
    main()
