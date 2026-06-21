"""
05_modelos.py — Entrenamiento y validación de modelos.

Entrena y compara:
  1. OLS (baseline hedónico)
  2. Random Forest
  3. Gradient Boosting (LightGBM)
  4. XGBoost

Con validación cruzada espacial y SHAP values.

Exporta:
  - models/modelo_final.joblib
  - outputs/model_comparison.json
  - outputs/shap_global.json
  - outputs/predictions.parquet (con SHAP values por predio)
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
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_percentage_error
from sklearn.preprocessing import LabelEncoder
import joblib

BASE = Path(__file__).resolve().parent.parent

# Feature columns for modeling.
# NOTA: "variacion_avaluo_pct_2020_2025" se calcula en 04_feature_engineering.py
# pero se EXCLUYE deliberadamente como predictor: (a) es una comparación
# predio-vs-promedio-de-su-manzana 2020 con fuerte inferencia ecológica
# (rango observado: -99.99% a +21,857%), y (b) al estar derivada en parte
# del propio avalúo 2025 que se busca predecir, introduciría fuga de
# información trivial. Se reporta como variable de análisis territorial
# separada en docs/resumen.md, no como feature del modelo.
FEATURE_COLS_NUMERIC = [
    "superficie_m2",
    "log_superficie",
    "dist_edu_escolar_m",
    "count_edu_escolar_1km",
    "dist_edu_parvularia_m",
    "count_edu_parvularia_1km",
    "dist_edu_superior_m",
    "count_edu_superior_1km",
    "dist_salud_m",
    "count_salud_1km",
    "dist_metro_m",
    "count_metro_1km",
    "dist_micro_m",
    "count_micro_500m",
    "count_micro_1km",
    "dist_aeropuerto_m",
    "dist_red_vial_m",
    "elevacion_m",
    "pendiente_pct",
    "centroid_x",
    "centroid_y",
]

FEATURE_COLS_CAT = [
    "nombre_comuna",
    "uso_suelo_ipt",
]

TARGET = "log_avaluo"


def preparar_features(gdf: gpd.GeoDataFrame) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Prepara matriz de features y target."""
    # Select available numeric features
    available_num = [c for c in FEATURE_COLS_NUMERIC if c in gdf.columns]
    available_cat = [c for c in FEATURE_COLS_CAT if c in gdf.columns]
    
    df = gdf[available_num + available_cat + [TARGET]].copy()
    
    # Drop rows with any NaN in features or target
    df = df.dropna(subset=available_num + [TARGET])
    
    # Encode categorical variables
    label_encoders = {}
    for cat in available_cat:
        le = LabelEncoder()
        df[cat + "_enc"] = le.fit_transform(df[cat].fillna("SIN_DATO").astype(str))
        label_encoders[cat] = le
    
    feature_names = available_num + [c + "_enc" for c in available_cat]
    
    X = df[feature_names]
    y = df[TARGET]
    
    print(f"  Features: {len(feature_names)} columnas")
    print(f"  Registros para modelado: {len(X):,}")
    
    return X, y, feature_names


def spatial_kfold(gdf: gpd.GeoDataFrame, n_splits: int = 5) -> list[tuple]:
    """
    Genera folds espaciales basados en la comuna.
    Cada fold tiene comunas disjuntas para train/test.
    """
    comunas = gdf["nombre_comuna"].unique()
    np.random.seed(42)
    np.random.shuffle(comunas)
    
    folds = []
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    
    for train_comunas_idx, test_comunas_idx in kf.split(comunas):
        train_comunas = set(comunas[train_comunas_idx])
        test_comunas = set(comunas[test_comunas_idx])
        
        train_idx = gdf.index[gdf["nombre_comuna"].isin(train_comunas)].tolist()
        test_idx = gdf.index[gdf["nombre_comuna"].isin(test_comunas)].tolist()
        
        folds.append((train_idx, test_idx))
    
    return folds


def evaluar_modelo(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """
    Calcula métricas de evaluación.

    NOTA METODOLÓGICA: antes de invertir la predicción de escala log a CLP
    (expm1), se recorta (clip) y_pred al rango [min(y_true)-2, max(y_true)+2]
    en escala log (~7x de margen multiplicativo). Esto evita que un único
    error de extrapolación de un modelo lineal (p.ej. OLS prediciendo un
    log_avaluo absurdamente alto para un predio atípico) se amplifique
    exponencialmente al invertir y domine por completo el RMSE/MAPE en
    pesos, lo que oscurecería la comparación real entre modelos. El recorte
    usa el rango del propio y_true del fold de evaluación solo como cota de
    plausibilidad física del dominio (avalúos conocidos), no se usa para
    mejorar la predicción ni se retroalimenta al entrenamiento.
    """
    r2 = r2_score(y_true, y_pred)
    rmse_log = np.sqrt(mean_squared_error(y_true, y_pred))

    y_pred_clipped = np.clip(y_pred, y_true.min() - 2, y_true.max() + 2)

    # Back-transform for RMSE and MAPE in escala original
    y_true_orig = np.expm1(y_true)
    y_pred_orig = np.expm1(y_pred_clipped)
    
    rmse_orig = np.sqrt(mean_squared_error(y_true_orig, y_pred_orig))
    
    # MAPE with handling for zeros
    mask = y_true_orig > 0
    if mask.sum() > 0:
        mape = mean_absolute_percentage_error(y_true_orig[mask], y_pred_orig[mask]) * 100
    else:
        mape = float("nan")
    
    return {
        "R2": round(r2, 4),
        "RMSE_log": round(rmse_log, 4),
        "RMSE_CLP": round(rmse_orig, 0),
        "MAPE_pct": round(mape, 2),
    }


def entrenar_ols(X_train, y_train, X_test, y_test):
    """OLS regression."""
    model = LinearRegression()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    return model, y_pred


def entrenar_rf(X_train, y_train, X_test, y_test):
    """Random Forest."""
    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=20,
        min_samples_leaf=10,
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    return model, y_pred


def entrenar_lgbm(X_train, y_train, X_test, y_test):
    """LightGBM."""
    try:
        import lightgbm as lgb
    except ImportError:
        print("  ⚠ LightGBM no disponible, se omite")
        return None, None
    
    model = lgb.LGBMRegressor(
        n_estimators=500,
        max_depth=12,
        learning_rate=0.05,
        num_leaves=63,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        n_jobs=-1,
        random_state=42,
        verbose=-1,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    return model, y_pred


def entrenar_xgb(X_train, y_train, X_test, y_test):
    """XGBoost."""
    try:
        import xgboost as xgb
    except ImportError:
        print("  ⚠ XGBoost no disponible, se omite")
        return None, None
    
    model = xgb.XGBRegressor(
        n_estimators=500,
        max_depth=10,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        n_jobs=-1,
        random_state=42,
        verbosity=0,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    return model, y_pred


def calcular_shap(model, X: pd.DataFrame, feature_names: list, model_name: str):
    """Calcula SHAP values globales. Retorna (shap_global_dict, explainer) para reuso."""
    try:
        import shap
    except ImportError:
        print("  ⚠ SHAP no disponible")
        return {}, None

    print(f"  Calculando SHAP values para {model_name}...")

    # Use a sample for speed
    sample_size = min(5000, len(X))
    X_sample = X.sample(sample_size, random_state=42)

    if model_name in ["LightGBM", "XGBoost", "Random Forest"]:
        explainer = shap.TreeExplainer(model)
    else:
        explainer = shap.LinearExplainer(model, X_sample)

    shap_values = explainer.shap_values(X_sample)

    # Global importance (mean absolute SHAP)
    importance = np.abs(shap_values).mean(axis=0)
    shap_global = dict(zip(feature_names, [round(float(v), 4) for v in importance]))
    shap_global = dict(sorted(shap_global.items(), key=lambda x: x[1], reverse=True))

    return shap_global, explainer


def calcular_shap_top3_por_predio(explainer, X: pd.DataFrame, feature_names: list) -> list:
    """
    Calcula, para cada fila de X, las 3 variables con mayor |SHAP value|.
    Retorna una lista (alineada con X.index) de listas de dicts
    [{"feature": ..., "shap_value": ..., "direccion": "sube"/"baja"}, ...]
    """
    shap_values = explainer.shap_values(X)
    feat_arr = np.array(feature_names)

    resultados = []
    for row in shap_values:
        order = np.argsort(-np.abs(row))[:3]
        top3 = [
            {
                "feature": str(feat_arr[i]),
                "shap_value": round(float(row[i]), 4),
                "direccion": "sube" if row[i] > 0 else "baja",
            }
            for i in order
        ]
        resultados.append(top3)
    return resultados


def main():
    t0 = time.time()
    print("=" * 80)
    print("  PIPELINE 05 — Modelamiento y Validación")
    print("=" * 80)
    
    # ── 1. Cargar datos ────────────────────────────────────────────
    feat_path = BASE / "outputs" / "predios_con_features.parquet"
    if not feat_path.exists():
        sys.exit(f"ERROR: {feat_path} no existe. Ejecutar 04_feature_engineering.py primero.")
    
    print("  Cargando datos con features...")
    gdf = gpd.read_parquet(feat_path)
    print(f"  Registros cargados: {len(gdf):,}")
    
    # ── 2. Preparar features ──────────────────────────────────────
    X, y, feature_names = preparar_features(gdf)
    
    # For spatial k-fold, we need the original gdf aligned
    gdf_model = gdf.loc[X.index].copy()
    
    # ── 3. Spatial K-Fold ─────────────────────────────────────────
    print("\n  Generando folds espaciales (5-fold por comuna)...")
    folds = spatial_kfold(gdf_model, n_splits=5)
    for i, (train_idx, test_idx) in enumerate(folds):
        print(f"    Fold {i+1}: train={len(train_idx):,}, test={len(test_idx):,}")
    
    # ── 4. Entrenar modelos ────────────────────────────────────────
    modelos = {
        "OLS": entrenar_ols,
        "Random Forest": entrenar_rf,
        "LightGBM": entrenar_lgbm,
        "XGBoost": entrenar_xgb,
    }
    
    resultados = {}
    mejores_modelos = {}
    predictions_all = {}
    
    for nombre, fn_entrenar in modelos.items():
        print(f"\n  {'─'*60}")
        print(f"  Entrenando: {nombre}")
        print(f"  {'─'*60}")
        
        all_y_true = []
        all_y_pred = []
        fold_metrics = []
        
        for i, (train_idx, test_idx) in enumerate(folds):
            # Align indices with X
            train_mask = X.index.isin(train_idx)
            test_mask = X.index.isin(test_idx)
            
            X_train = X[train_mask]
            y_train = y[train_mask]
            X_test = X[test_mask]
            y_test = y[test_mask]
            
            model, y_pred = fn_entrenar(X_train, y_train, X_test, y_test)
            
            if model is None:
                break
            
            metrics = evaluar_modelo(y_test.values, y_pred)
            fold_metrics.append(metrics)
            all_y_true.extend(y_test.values.tolist())
            all_y_pred.extend(y_pred.tolist())
            
            print(f"    Fold {i+1}: R²={metrics['R2']:.4f}, RMSE=${metrics['RMSE_CLP']:,.0f}, MAPE={metrics['MAPE_pct']:.1f}%")
        
        if not fold_metrics:
            continue
        
        # Overall metrics
        overall = evaluar_modelo(np.array(all_y_true), np.array(all_y_pred))
        resultados[nombre] = {
            "overall": overall,
            "folds": fold_metrics,
        }
        
        predictions_all[nombre] = {
            "y_true": all_y_true,
            "y_pred": all_y_pred,
        }
        
        print(f"  OVERALL {nombre}: R²={overall['R2']:.4f}, RMSE=${overall['RMSE_CLP']:,.0f}, MAPE={overall['MAPE_pct']:.1f}%")
        
        # Train final model on all data
        model_final, _ = fn_entrenar(X, y, X, y)
        mejores_modelos[nombre] = model_final
    
    # ── 5. Comparar y elegir ganador ───────────────────────────────
    print(f"\n  {'='*60}")
    print(f"  TABLA COMPARATIVA DE MODELOS")
    print(f"  {'='*60}")
    print(f"  {'Modelo':<20s}  {'R²':>8s}  {'RMSE (CLP)':>15s}  {'MAPE (%)':>10s}")
    print(f"  {'─'*55}")
    
    best_name = None
    best_r2 = -1
    
    for nombre, res in resultados.items():
        o = res["overall"]
        marker = ""
        if o["R2"] > best_r2:
            best_r2 = o["R2"]
            best_name = nombre
        print(f"  {nombre:<20s}  {o['R2']:>8.4f}  {o['RMSE_CLP']:>15,.0f}  {o['MAPE_pct']:>10.1f}")
    
    print(f"\n  🏆 Modelo ganador: {best_name} (R²={best_r2:.4f})")
    
    # ── 6. SHAP sobre el ganador ───────────────────────────────────
    shap_global = {}
    explainer = None
    if best_name and best_name in mejores_modelos:
        shap_global, explainer = calcular_shap(mejores_modelos[best_name], X, feature_names, best_name)
        if shap_global:
            print(f"\n  Top 10 SHAP importancias ({best_name}):")
            for feat, val in list(shap_global.items())[:10]:
                print(f"    {feat:<35s}  {val:.4f}")

    # ── 7. Generar predicciones finales ────────────────────────────
    print("\n  Generando predicciones finales con modelo ganador...")
    model_ganador = mejores_modelos.get(best_name)

    if model_ganador:
        y_pred_final = model_ganador.predict(X)
        gdf_model["avaluo_predicho_log"] = np.nan
        gdf_model.loc[X.index, "avaluo_predicho_log"] = y_pred_final
        gdf_model["avaluo_predicho"] = np.expm1(gdf_model["avaluo_predicho_log"])
        gdf_model["residual"] = gdf_model["avaluo_fiscal"] - gdf_model["avaluo_predicho"]
        gdf_model["residual_pct"] = (gdf_model["residual"] / gdf_model["avaluo_fiscal"]) * 100

    # ── 7b. SHAP por predio para la muestra que se exporta a la web ──
    # Se usa la MISMA muestra estratificada por comuna (hasta 500/comuna)
    # que 06_generar_outputs.py exporta a predictions.geojson, para que
    # cada predio de la web tenga su top-3 de variables SHAP explicadas.
    gdf_model["shap_top3"] = None
    if explainer is not None:
        print("\n  Calculando SHAP por predio para la muestra de exportación web...")
        sample_idx_parts = []
        for comuna, grupo in gdf_model.loc[X.index].groupby("nombre_comuna"):
            n = min(500, len(grupo))
            sample_idx_parts.append(grupo.sample(n, random_state=42).index)
        sample_idx = pd.Index(np.concatenate(sample_idx_parts))
        X_sample_shap = X.loc[X.index.intersection(sample_idx)]
        print(f"    Predios en muestra SHAP: {len(X_sample_shap):,}")
        top3_list = calcular_shap_top3_por_predio(explainer, X_sample_shap, feature_names)
        shap_series = pd.Series(top3_list, index=X_sample_shap.index)
        gdf_model.loc[shap_series.index, "shap_top3"] = shap_series.apply(json.dumps)
    
    # ── 8. Exportar resultados ─────────────────────────────────────
    output_dir = BASE / "outputs"
    models_dir = BASE / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    
    # a) Modelo serializado
    if model_ganador:
        model_path = models_dir / "modelo_final.joblib"
        joblib.dump(model_ganador, model_path)
        print(f"  Modelo guardado → {model_path}")
    
    # b) Tabla comparativa
    comparison = {}
    for nombre, res in resultados.items():
        comparison[nombre] = {
            **res["overall"],
            "ganador": nombre == best_name,
        }
    
    comp_path = output_dir / "model_comparison.json"
    with open(comp_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    print(f"  Comparación → {comp_path}")
    
    # c) SHAP global
    shap_path = output_dir / "shap_global.json"
    with open(shap_path, "w", encoding="utf-8") as f:
        json.dump(shap_global, f, indent=2, ensure_ascii=False)
    print(f"  SHAP global → {shap_path}")
    
    # d) Predicciones
    pred_path = output_dir / "predictions.parquet"
    gdf_model.to_parquet(pred_path)
    print(f"  Predicciones → {pred_path}")
    
    # e) Métricas del modelo ganador
    metrics_path = models_dir / "metricas.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump({
            "modelo_ganador": best_name,
            "metricas": resultados[best_name]["overall"] if best_name else {},
            "feature_names": feature_names,
            "n_registros_train": len(X),
        }, f, indent=2, ensure_ascii=False)
    
    elapsed = time.time() - t0
    print(f"\n  Tiempo total: {elapsed:.1f} segundos")
    print("\n✔ Pipeline 05 completado.")


if __name__ == "__main__":
    main()
