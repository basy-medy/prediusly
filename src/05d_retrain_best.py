"""
05d_retrain_best.py — Reentrena el modelo+hiperparámetros ganador de la
grilla de Optuna (05c_optuna_tuning.py) sobre el dataset COMPLETO de
predios (2.2M), con la misma validación cruzada espacial 5-fold por comuna
usada en 05_modelos.py.

Actualiza:
  - outputs/model_comparison.json — reemplaza la entrada del modelo ganador
    de Optuna con sus métricas a escala completa, marca tuned_optuna=true,
    y mueve la bandera "ganador" si el modelo tuneado supera al ganador
    anterior (fijo, sin tuning).
  - outputs/shap_global.json, outputs/predictions.parquet (avaluo_predicho,
    residual, residual_pct, shap_top3) — solo si el modelo tuneado pasa a
    ser el ganador.
  - models/modelo_final.joblib, models/metricas.json — solo si gana.

Ejecutar DESPUÉS de 05_modelos.py (baseline fijo) y 05c_optuna_tuning.py.
"""
from __future__ import annotations
import sys
import time
import json
import warnings
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import geopandas as gpd
import joblib

BASE = Path(__file__).resolve().parent.parent

import importlib.util
spec = importlib.util.spec_from_file_location("m05", BASE / "src" / "05_modelos.py")
m05 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m05)


def construir_modelo(model_name: str, params: dict):
    params = {k: v for k, v in params.items()}
    if model_name == "Random Forest":
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(**params)
    elif model_name == "LightGBM":
        import lightgbm as lgb
        return lgb.LGBMRegressor(**params)
    elif model_name == "XGBoost":
        import xgboost as xgb
        return xgb.XGBRegressor(**params)
    raise ValueError(model_name)


def main():
    t0 = time.time()
    print("=" * 80)
    print("  PIPELINE 05d — Reentrenamiento del ganador de Optuna a escala completa")
    print("=" * 80)

    best_path = BASE / "outputs" / "optuna_best.json"
    if not best_path.exists():
        sys.exit(f"ERROR: {best_path} no existe. Ejecutar 05c_optuna_tuning.py primero.")
    with open(best_path, encoding="utf-8") as f:
        optuna_best = json.load(f)

    model_name = optuna_best["mejor_modelo_global"]
    best_params = optuna_best["mejores_por_modelo"][model_name]["best_params"]
    print(f"  Modelo+hiperparámetros ganador de Optuna: {model_name}")
    print(f"  Params: {best_params}")

    # ── 1. Cargar dataset completo y preparar features ──────────────
    feat_path = BASE / "outputs" / "predios_con_features.parquet"
    gdf = gpd.read_parquet(feat_path)
    print(f"\n  Predios cargados: {len(gdf):,}")

    X, y, feature_names = m05.preparar_features(gdf)
    gdf_model = gdf.loc[X.index].copy()
    print(f"  Registros para modelado: {len(X):,}")

    # ── 2. Validación cruzada espacial 5-fold (igual a 05_modelos.py) ──
    folds = m05.spatial_kfold(gdf_model, n_splits=5)

    all_y_true, all_y_pred, fold_metrics = [], [], []
    for i, (train_idx, test_idx) in enumerate(folds):
        train_mask = X.index.isin(train_idx)
        test_mask = X.index.isin(test_idx)
        model = construir_modelo(model_name, best_params)
        model.fit(X[train_mask], y[train_mask])
        y_pred = model.predict(X[test_mask])
        metrics = m05.evaluar_modelo(y[test_mask].values, y_pred)
        fold_metrics.append(metrics)
        all_y_true.extend(y[test_mask].values.tolist())
        all_y_pred.extend(y_pred.tolist())
        print(f"    Fold {i+1}: R²={metrics['R2']:.4f}, RMSE_CLP=${metrics['RMSE_CLP']:,.0f}, MAPE={metrics['MAPE_pct']:.1f}%")

    overall = m05.evaluar_modelo(np.array(all_y_true), np.array(all_y_pred))
    print(f"\n  OVERALL {model_name} (tuned): R²={overall['R2']:.4f}, "
          f"RMSE=${overall['RMSE_CLP']:,.0f}, MAPE={overall['MAPE_pct']:.1f}%")

    # ── 3. Comparar contra el ganador anterior (fijo, sin tuning) ────
    comp_path = BASE / "outputs" / "model_comparison.json"
    with open(comp_path, encoding="utf-8") as f:
        comparison = json.load(f)

    anterior_ganador = next((k for k, v in comparison.items() if v.get("ganador")), None)
    r2_anterior_ganador = comparison.get(anterior_ganador, {}).get("R2", -1) if anterior_ganador else -1
    pasa_a_ganar = overall["R2"] > r2_anterior_ganador

    print(f"\n  Ganador anterior (fijo): {anterior_ganador} (R²={r2_anterior_ganador:.4f})")
    print(f"  {model_name} tuneado: R²={overall['R2']:.4f}")
    print(f"  ¿El modelo tuneado pasa a ser el ganador? {'SÍ' if pasa_a_ganar else 'NO'}")

    # Actualizar comparison: agregar/reemplazar entrada de este modelo
    comparison[model_name] = {
        **overall,
        "ganador": pasa_a_ganar,
        "tuned_optuna": True,
        "optuna_best_params": {k: v for k, v in best_params.items() if k not in ("n_jobs", "random_state", "verbose", "verbosity")},
    }
    if pasa_a_ganar and anterior_ganador and anterior_ganador != model_name:
        comparison[anterior_ganador]["ganador"] = False

    with open(comp_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    print(f"\n  model_comparison.json actualizado → {comp_path}")

    if not pasa_a_ganar:
        print("\n  El modelo tuneado NO supera al ganador anterior; no se regeneran "
              "predictions/shap/modelo final. Solo se registró su métrica en la "
              "tabla comparativa.")
        elapsed = time.time() - t0
        print(f"\n  Tiempo total: {elapsed:.1f} segundos")
        print("\n✔ Pipeline 05d completado (sin cambio de ganador).")
        return

    # ── 4. Es el nuevo ganador: entrenar final sobre TODO el dataset ──
    print("\n  Entrenando modelo final (tuned) sobre el dataset completo...")
    model_final = construir_modelo(model_name, best_params)
    model_final.fit(X, y)

    y_pred_final = model_final.predict(X)
    gdf_model["avaluo_predicho_log"] = np.nan
    gdf_model.loc[X.index, "avaluo_predicho_log"] = y_pred_final
    gdf_model["avaluo_predicho"] = np.expm1(gdf_model["avaluo_predicho_log"])
    gdf_model["residual"] = gdf_model["avaluo_fiscal"] - gdf_model["avaluo_predicho"]
    gdf_model["residual_pct"] = (gdf_model["residual"] / gdf_model["avaluo_fiscal"]) * 100

    # ── 5. SHAP global + por predio (misma muestra estratificada que 05) ──
    shap_global, explainer = m05.calcular_shap(model_final, X, feature_names, model_name)
    print("\n  Top 10 SHAP (modelo tuneado):")
    for feat, val in list(shap_global.items())[:10]:
        print(f"    {feat:<35s}  {val:.4f}")

    gdf_model["shap_top3"] = None
    if explainer is not None:
        sample_idx_parts = []
        for comuna, grupo in gdf_model.loc[X.index].groupby("nombre_comuna"):
            n = min(500, len(grupo))
            sample_idx_parts.append(grupo.sample(n, random_state=42).index)
        sample_idx = pd.Index(np.concatenate(sample_idx_parts))
        X_sample_shap = X.loc[X.index.intersection(sample_idx)]
        print(f"  Predios en muestra SHAP: {len(X_sample_shap):,}")
        top3_list = m05.calcular_shap_top3_por_predio(explainer, X_sample_shap, feature_names)
        shap_series = pd.Series(top3_list, index=X_sample_shap.index)
        gdf_model.loc[shap_series.index, "shap_top3"] = shap_series.apply(json.dumps)

    # ── 6. Exportar ────────────────────────────────────────────────
    output_dir = BASE / "outputs"
    models_dir = BASE / "models"

    shap_path = output_dir / "shap_global.json"
    with open(shap_path, "w", encoding="utf-8") as f:
        json.dump(shap_global, f, indent=2, ensure_ascii=False)
    print(f"\n  SHAP global → {shap_path}")

    pred_path = output_dir / "predictions.parquet"
    gdf_model.to_parquet(pred_path)
    print(f"  Predicciones → {pred_path}")

    model_path = models_dir / "modelo_final.joblib"
    joblib.dump(model_final, model_path)
    print(f"  Modelo guardado → {model_path}")

    metrics_path = models_dir / "metricas.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump({
            "modelo_ganador": model_name,
            "tuned_optuna": True,
            "optuna_best_params": {k: v for k, v in best_params.items() if k not in ("n_jobs", "random_state", "verbose", "verbosity")},
            "metricas": overall,
            "feature_names": feature_names,
            "n_registros_train": len(X),
        }, f, indent=2, ensure_ascii=False)
    print(f"  Métricas → {metrics_path}")

    elapsed = time.time() - t0
    print(f"\n  Tiempo total: {elapsed:.1f} segundos")
    print("\n✔ Pipeline 05d completado (nuevo ganador, outputs regenerados).")


if __name__ == "__main__":
    main()
