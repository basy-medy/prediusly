"""
05c_optuna_tuning.py — Grilla de hiperparámetros con Optuna para Random
Forest, LightGBM y XGBoost.

Por qué una muestra y no las 2.2M filas completas: cada trial de Optuna
reentrena el modelo desde cero; correr 30 trials x 3 modelos sobre el
dataset completo (cada fit ya toma minutos, ver outputs/model_comparison.json)
sería intratable en tiempo. Se usa una muestra estratificada por comuna de
~100,000 predios — suficiente para que el RANKING relativo de
hiperparámetros sea representativo, sin pagar el costo de escala completa
en cada trial.

Validación dentro de cada trial: 3-fold espacial por comuna (folds con
comunas disjuntas), consistente con el principio de "nunca k-fold aleatorio
puro" usado en el resto del proyecto. Métrica optimizada: R² medio en
escala log (TARGET = log_avaluo) entre los 3 folds.

Exporta:
  - outputs/optuna_trials.json — TODOS los trials (hiperparámetros + score)
    de los 3 estudios, para poder graficar/inspeccionar la grilla completa.
  - outputs/optuna_best.json — mejor combinación de cada modelo + la mejor
    combinación global (modelo, hiperparámetros, score), que
    05d_retrain_best.py usa para reentrenar sobre el dataset completo.
  - docs/_optuna_grid.md — tabla markdown resumen para incluir en la
    documentación.
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
import optuna
from optuna.samplers import TPESampler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score

BASE = Path(__file__).resolve().parent.parent

N_MUESTRA = 100_000
N_TRIALS = 30
N_FOLDS = 3
RANDOM_STATE = 42

sys.path.insert(0, str(BASE / "src"))
import importlib.util
spec = importlib.util.spec_from_file_location("m05", BASE / "src" / "05_modelos.py")
m05 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m05)


def muestreo_estratificado(gdf: gpd.GeoDataFrame, n_objetivo: int) -> gpd.GeoDataFrame:
    n_total = len(gdf)
    partes = []
    for comuna, grupo in gdf.groupby("nombre_comuna"):
        n = max(1, round(n_objetivo * len(grupo) / n_total))
        n = min(n, len(grupo))
        partes.append(grupo.sample(n, random_state=RANDOM_STATE))
    return pd.concat(partes)


def spatial_folds_for_sample(gdf_sample: pd.DataFrame, n_splits: int = N_FOLDS):
    comunas = gdf_sample["nombre_comuna"].unique()
    rng = np.random.RandomState(RANDOM_STATE)
    comunas_shuffled = rng.permutation(comunas)
    splits = np.array_split(comunas_shuffled, n_splits)
    folds = []
    for i in range(n_splits):
        test_comunas = set(splits[i])
        train_comunas = set(comunas) - test_comunas
        train_idx = gdf_sample.index[gdf_sample["nombre_comuna"].isin(train_comunas)]
        test_idx = gdf_sample.index[gdf_sample["nombre_comuna"].isin(test_comunas)]
        folds.append((train_idx, test_idx))
    return folds


def cv_r2(model_fn, X: pd.DataFrame, y: pd.Series, folds) -> float:
    scores = []
    for train_idx, test_idx in folds:
        train_mask = X.index.isin(train_idx)
        test_mask = X.index.isin(test_idx)
        model = model_fn()
        model.fit(X[train_mask], y[train_mask])
        y_pred = model.predict(X[test_mask])
        scores.append(r2_score(y[test_mask], y_pred))
    return float(np.mean(scores))


def make_objective(model_name: str, X, y, folds):
    def objective(trial: optuna.Trial) -> float:
        if model_name == "Random Forest":
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
                "max_depth": trial.suggest_int("max_depth", 6, 30),
                "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 30),
                "max_features": trial.suggest_float("max_features", 0.3, 1.0),
                "n_jobs": -1,
                "random_state": RANDOM_STATE,
            }
            model_fn = lambda: RandomForestRegressor(**params)

        elif model_name == "LightGBM":
            import lightgbm as lgb
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 800, step=50),
                "max_depth": trial.suggest_int("max_depth", 3, 16),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "num_leaves": trial.suggest_int("num_leaves", 15, 255),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
                "n_jobs": -1,
                "random_state": RANDOM_STATE,
                "verbose": -1,
            }
            model_fn = lambda: lgb.LGBMRegressor(**params)

        elif model_name == "XGBoost":
            import xgboost as xgb
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 800, step=50),
                "max_depth": trial.suggest_int("max_depth", 3, 16),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
                "n_jobs": -1,
                "random_state": RANDOM_STATE,
                "verbosity": 0,
            }
            model_fn = lambda: xgb.XGBRegressor(**params)
        else:
            raise ValueError(model_name)

        score = cv_r2(model_fn, X, y, folds)
        trial.set_user_attr("params", params)
        return score

    return objective


def main():
    t0 = time.time()
    print("=" * 80)
    print("  PIPELINE 05c — Grilla de hiperparámetros con Optuna")
    print("=" * 80)

    feat_path = BASE / "outputs" / "predios_con_features.parquet"
    gdf = gpd.read_parquet(feat_path)
    print(f"  Predios disponibles: {len(gdf):,}")

    muestra = muestreo_estratificado(gdf, N_MUESTRA)
    print(f"  Muestra estratificada por comuna: {len(muestra):,} predios, "
          f"{muestra['nombre_comuna'].nunique()} comunas")

    X, y, feature_names = m05.preparar_features(muestra)
    muestra = muestra.loc[X.index]
    folds = spatial_folds_for_sample(muestra, N_FOLDS)
    for i, (tr, te) in enumerate(folds):
        print(f"    Fold {i+1}: train={len(tr):,}  test={len(te):,}")

    todos_los_trials = {}
    mejores = {}

    for model_name in ["Random Forest", "LightGBM", "XGBoost"]:
        print(f"\n  {'─'*60}")
        print(f"  Optuna study: {model_name} ({N_TRIALS} trials)")
        print(f"  {'─'*60}")

        study = optuna.create_study(
            direction="maximize",
            sampler=TPESampler(seed=RANDOM_STATE),
        )
        objective = make_objective(model_name, X, y, folds)
        study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=False)

        trials_info = [
            {
                "trial": t.number,
                "value_r2": t.value,
                "params": t.user_attrs.get("params", t.params),
            }
            for t in study.trials
        ]
        todos_los_trials[model_name] = trials_info
        mejores[model_name] = {
            "best_r2_cv_muestra": study.best_value,
            "best_params": study.best_trial.user_attrs.get("params", study.best_params),
        }
        print(f"  Mejor R² (CV muestra, {model_name}): {study.best_value:.4f}")
        print(f"  Mejores params: {mejores[model_name]['best_params']}")

    # ── Determinar la mejor combinación global ──────────────────────
    mejor_modelo_global = max(mejores, key=lambda k: mejores[k]["best_r2_cv_muestra"])
    print(f"\n  🏆 Mejor combinación global: {mejor_modelo_global} "
          f"(R²={mejores[mejor_modelo_global]['best_r2_cv_muestra']:.4f})")

    # ── Exportar ─────────────────────────────────────────────────────
    output_dir = BASE / "outputs"
    with open(output_dir / "optuna_trials.json", "w", encoding="utf-8") as f:
        json.dump(todos_los_trials, f, indent=2, ensure_ascii=False)
    print(f"\n  Todos los trials → {output_dir / 'optuna_trials.json'}")

    resultado_best = {
        "n_muestra": len(muestra),
        "n_trials_por_modelo": N_TRIALS,
        "n_folds_espaciales": N_FOLDS,
        "mejores_por_modelo": mejores,
        "mejor_modelo_global": mejor_modelo_global,
        "nota": (
            f"Búsqueda de hiperparámetros realizada sobre una muestra "
            f"estratificada por comuna de {len(muestra):,} predios (no el "
            f"dataset completo de 2.2M) por costo computacional de repetir "
            f"el entrenamiento {N_TRIALS} veces por modelo. El modelo+"
            f"params ganador se reentrena sobre el dataset completo en "
            f"05d_retrain_best.py."
        ),
    }
    with open(output_dir / "optuna_best.json", "w", encoding="utf-8") as f:
        json.dump(resultado_best, f, indent=2, ensure_ascii=False)
    print(f"  Mejor combinación → {output_dir / 'optuna_best.json'}")

    # ── Tabla markdown resumen ───────────────────────────────────────
    docs_dir = BASE / "docs"
    lineas = [
        "## Grilla de hiperparámetros (Optuna)\n",
        f"Búsqueda sobre muestra estratificada por comuna (n={len(muestra):,}), "
        f"{N_TRIALS} trials por modelo, validación cruzada espacial "
        f"({N_FOLDS}-fold por comuna). Métrica: R² en escala log.\n",
        "| Modelo | Mejor R² (CV muestra) | Mejores hiperparámetros |",
        "|---|---:|---|",
    ]
    for model_name, info in mejores.items():
        params_str = ", ".join(f"{k}={v}" for k, v in info["best_params"].items() if k not in ("n_jobs", "random_state", "verbose", "verbosity"))
        marker = " 🏆" if model_name == mejor_modelo_global else ""
        lineas.append(f"| {model_name}{marker} | {info['best_r2_cv_muestra']:.4f} | {params_str} |")
    with open(docs_dir / "_optuna_grid.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))
    print(f"  Tabla resumen → {docs_dir / '_optuna_grid.md'}")

    elapsed = time.time() - t0
    print(f"\n  Tiempo total: {elapsed:.1f} segundos")
    print("\n✔ Pipeline 05c completado.")


if __name__ == "__main__":
    main()
