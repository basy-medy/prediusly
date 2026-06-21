"""
02_limpieza_predios.py — Limpieza de predios SII_2025 (y join con SII_2020).

Pipeline secuencial de filtrado de predios SII_2025 según las reglas exactas
del prompt (sección 1.2.a). Registra el embudo de descarte.

Exporta:
  - outputs/predios_limpios.parquet — Predios filtrados con geometría y avalúo
  - docs/ actualización del data_dictionary.md con embudo de descarte
"""
from __future__ import annotations
import sys
import time
import warnings
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import wkb
from shapely.validation import make_valid

BASE = Path(__file__).resolve().parent.parent  # archivos/
CRS_PROJ = "EPSG:32719"  # UTM Zone 19S — official for central Chile

def cargar_sii_2025() -> gpd.GeoDataFrame:
    """Carga todos los parquet de SII_2025 y construye GeoDataFrame."""
    sii_dir = BASE / "SII_2025"
    archivos = sorted(sii_dir.glob("*.parquet"))
    print(f"  Cargando {len(archivos)} archivos parquet de SII_2025...")
    
    dfs = []
    for f in archivos:
        df = pd.read_parquet(f)
        # Extract comuna name from filename
        nombre_archivo = f.stem  # e.g. "Las_Condes_15108"
        df["_archivo_origen"] = nombre_archivo
        dfs.append(df)
    
    df_all = pd.concat(dfs, ignore_index=True)
    print(f"  Total registros cargados: {len(df_all):,}")
    
    # Convert WKB geometry to shapely
    print("  Convirtiendo geometría WKB...")
    n_geom_null = df_all["geometry"].isna().sum()
    print(f"  Registros sin geometría (null): {n_geom_null:,}")
    
    # Parse WKB for non-null geometries
    geom_series = df_all["geometry"].apply(
        lambda x: wkb.loads(x) if isinstance(x, bytes) else None
    )
    
    gdf = gpd.GeoDataFrame(df_all, geometry=geom_series, crs="EPSG:4326")
    
    return gdf


COLS_EJEMPLO = ["rol", "nombreComuna", "destinoDescripcion", "ubicacion", "pol_area_m2", "dc_avaluo_fiscal"]


def _capturar_ejemplo(gdf_descartados: pd.DataFrame, paso: str, motivo: str, ejemplos: dict) -> None:
    """Guarda un registro concreto descartado en este paso, con sus valores reales."""
    if len(gdf_descartados) == 0:
        return
    fila = gdf_descartados.iloc[0]
    cols_disp = [c for c in COLS_EJEMPLO if c in gdf_descartados.columns]
    valores = {}
    for c in cols_disp:
        v = fila[c]
        valores[c] = None if pd.isna(v) else (float(v) if isinstance(v, (np.floating, float)) else str(v))
    ejemplos[paso] = {"motivo": motivo, "valores": valores}


def filtrado_secuencial(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict, dict]:
    """
    Filtrado secuencial de predios según reglas 1.2.a.
    Cada paso descarta inmediatamente los que no cumplen.
    Retorna el GDF filtrado, un dict con conteos del embudo, y ejemplos concretos descartados.
    """
    embudo = {}
    ejemplos: dict = {}
    n_total = len(gdf)
    embudo["01_total_cargados"] = n_total
    print(f"\n  Paso 0: Total cargados = {n_total:,}")

    # Paso 1: Validar que existan y no sean nulos: destinoDescripcion, ubicacion, pol_area_m2
    mask_atributos = (
        gdf["destinoDescripcion"].notna() &
        gdf["ubicacion"].notna() &
        gdf["pol_area_m2"].notna()
    )
    _capturar_ejemplo(gdf[~mask_atributos], "01_atributos_nulos",
                       "Descartado por tener destinoDescripcion, ubicacion o pol_area_m2 nulos", ejemplos)
    gdf = gdf[mask_atributos].copy()
    embudo["02_con_atributos_validos"] = len(gdf)
    print(f"  Paso 1: Con atributos válidos (destino, ubicacion, area no nulos) = {len(gdf):,}  (descartados: {n_total - len(gdf):,})")

    # Paso 2: destinoDescripcion == "HABITACIONAL"
    n_antes = len(gdf)
    _capturar_ejemplo(gdf[gdf["destinoDescripcion"] != "HABITACIONAL"], "02_no_habitacional",
                       "Descartado por destinoDescripcion distinto de HABITACIONAL", ejemplos)
    gdf = gdf[gdf["destinoDescripcion"] == "HABITACIONAL"].copy()
    embudo["03_habitacional"] = len(gdf)
    print(f"  Paso 2: Habitacional = {len(gdf):,}  (descartados: {n_antes - len(gdf):,})")

    # Paso 3: ubicacion == "URBANA"
    n_antes = len(gdf)
    _capturar_ejemplo(gdf[gdf["ubicacion"] != "URBANA"], "03_no_urbano",
                       "Descartado por ubicacion distinta de URBANA (predio rural)", ejemplos)
    gdf = gdf[gdf["ubicacion"] == "URBANA"].copy()
    embudo["04_urbana"] = len(gdf)
    print(f"  Paso 3: Urbana = {len(gdf):,}  (descartados: {n_antes - len(gdf):,})")

    # Paso 4: 50 <= pol_area_m2 <= 20000
    n_antes = len(gdf)
    fuera_rango = gdf[(gdf["pol_area_m2"] < 50) | (gdf["pol_area_m2"] > 20000)]
    _capturar_ejemplo(fuera_rango, "04_fuera_rango_superficie",
                       "Descartado por superficie fuera del rango 50-20,000 m²", ejemplos)
    gdf = gdf[(gdf["pol_area_m2"] >= 50) & (gdf["pol_area_m2"] <= 20000)].copy()
    embudo["05_rango_superficie"] = len(gdf)
    print(f"  Paso 4: Superficie 50-20000 m² = {len(gdf):,}  (descartados: {n_antes - len(gdf):,})")

    # Paso 5: Validar geometría no nula
    n_antes = len(gdf)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    embudo["06_con_geometria"] = len(gdf)
    print(f"  Paso 5: Con geometría válida = {len(gdf):,}  (descartados: {n_antes - len(gdf):,})")

    return gdf, embudo, ejemplos


def limpiar_geometrias(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Repara geometrías inválidas con make_valid."""
    n_invalid = int((~gdf.geometry.is_valid).sum())
    print(f"\n  Geometrías inválidas antes de reparación: {n_invalid}")
    
    if n_invalid > 0:
        gdf["geometry"] = gdf.geometry.apply(
            lambda g: make_valid(g) if g is not None and not g.is_valid else g
        )
        n_invalid_after = int((~gdf.geometry.is_valid).sum())
        print(f"  Geometrías inválidas después de make_valid: {n_invalid_after}")
    
    return gdf


def detectar_outliers_avaluo(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict, dict]:
    """
    Detecta outliers de avalúo fiscal por comuna usando IQR.
    Descarta predios con avalúo extremo.
    """
    # Convert avaluo to numeric
    gdf["avaluo_fiscal"] = pd.to_numeric(gdf["dc_avaluo_fiscal"], errors="coerce")

    n_antes = len(gdf)
    n_null_avaluo = int(gdf["avaluo_fiscal"].isna().sum())
    print(f"\n  Avalúo fiscal nulo: {n_null_avaluo}")

    # Drop null avaluos
    gdf = gdf[gdf["avaluo_fiscal"].notna()].copy()

    # Also drop avaluos <= 0 (meaningless)
    n_nonpos = int((gdf["avaluo_fiscal"] <= 0).sum())
    gdf = gdf[gdf["avaluo_fiscal"] > 0].copy()
    print(f"  Avalúo fiscal <= 0: {n_nonpos}")

    # IQR-based outlier detection per comuna
    # Extract comuna code
    gdf["cod_comuna"] = gdf["comuna"].astype(str)

    limites = gdf.groupby("cod_comuna")["avaluo_fiscal"].quantile([0.01, 0.99]).unstack()

    def iqr_filter(group):
        q1 = group["avaluo_fiscal"].quantile(0.01)
        q3 = group["avaluo_fiscal"].quantile(0.99)
        return group[(group["avaluo_fiscal"] >= q1) & (group["avaluo_fiscal"] <= q3)]

    gdf_filtered = gdf.groupby("cod_comuna", group_keys=False).apply(iqr_filter)

    n_outliers = n_antes - len(gdf_filtered)
    print(f"  Outliers de avalúo removidos (percentil 1-99 por comuna): {n_outliers:,}")
    print(f"  Registros finales: {len(gdf_filtered):,}")

    # Ejemplo concreto de outlier removido (el de mayor avalúo descartado)
    idx_outliers = gdf.index.difference(gdf_filtered.index)
    ejemplo_outlier = None
    if len(idx_outliers) > 0:
        outliers_df = gdf.loc[idx_outliers]
        fila = outliers_df.sort_values("avaluo_fiscal", ascending=False).iloc[0]
        q1, q99 = limites.loc[fila["cod_comuna"], 0.01], limites.loc[fila["cod_comuna"], 0.99]
        ejemplo_outlier = {
            "motivo": "Avalúo fiscal fuera del percentil 1-99 de su comuna",
            "valores": {
                "rol": str(fila.get("rol")),
                "nombreComuna": str(fila.get("nombreComuna")),
                "avaluo_fiscal": float(fila["avaluo_fiscal"]),
                "percentil_1_comuna": float(q1),
                "percentil_99_comuna": float(q99),
            },
        }

    stats = {
        "n_null_avaluo": n_null_avaluo,
        "n_nonpos_avaluo": n_nonpos,
        "n_outliers_iqr": n_antes - n_null_avaluo - n_nonpos - len(gdf_filtered),
        "n_final": len(gdf_filtered),
    }

    return gdf_filtered, stats, ejemplo_outlier


def preparar_columnas_finales(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Selecciona y renombra columnas relevantes para el análisis."""
    cols_mantener = {
        "rol": "rol",
        "comuna": "cod_comuna",
        "nombreComuna": "nombre_comuna",
        "destinoDescripcion": "destino",
        "ubicacion": "ubicacion",
        "pol_area_m2": "superficie_m2",
        "avaluo_fiscal": "avaluo_fiscal",
        "dc_avaluo_exento": "avaluo_exento",
        "dc_contribucion_semestral": "contribucion_semestral",
        "dc_sup_terreno": "sup_terreno_sii",
        "dc_direccion": "direccion",
        "n_lineas_construccion": "n_lineas_construccion",
        "sup_construida_total": "sup_construida_total",
        "anio_construccion_min": "anio_construccion_min",
        "anio_construccion_max": "anio_construccion_max",
        "materiales": "materiales",
        "calidades": "calidades",
        "pisos_max": "pisos_max",
        "lat": "lat_orig",
        "lon": "lon_orig",
        "valorComercial_clp_m2": "valor_comercial_m2",
        "_match_method": "match_method",
        "geometry": "geometry",
    }
    
    cols_disponibles = {k: v for k, v in cols_mantener.items() if k in gdf.columns}
    gdf_final = gdf[list(cols_disponibles.keys())].copy()
    gdf_final = gdf_final.rename(columns=cols_disponibles)
    
    # Convert numeric columns
    for col in ["sup_terreno_sii", "sup_construida_total", "anio_construccion_min",
                "anio_construccion_max", "pisos_max", "contribucion_semestral",
                "n_lineas_construccion", "valor_comercial_m2"]:
        if col in gdf_final.columns:
            gdf_final[col] = pd.to_numeric(gdf_final[col], errors="coerce")
    
    return gdf_final


def main():
    t0 = time.time()
    print("=" * 80)
    print("  PIPELINE 02 — Limpieza de predios SII_2025")
    print("=" * 80)
    
    # ── 1. Cargar SII_2025 ──────────────────────────────────────────
    gdf = cargar_sii_2025()
    
    # ── 2. Filtrado secuencial ──────────────────────────────────────
    gdf, embudo, ejemplos = filtrado_secuencial(gdf)

    # ── 3. Reproyectar a CRS en metros ─────────────────────────────
    print(f"\n  Reproyectando a {CRS_PROJ}...")
    gdf = gdf.to_crs(CRS_PROJ)

    # ── 4. Reparar geometrías ──────────────────────────────────────
    gdf = limpiar_geometrias(gdf)

    # ── 5. Detección de outliers de avalúo ─────────────────────────
    gdf, outlier_stats, ejemplo_outlier = detectar_outliers_avaluo(gdf)
    embudo["07_sin_outliers_avaluo"] = outlier_stats["n_final"]
    if ejemplo_outlier:
        ejemplos["05_outlier_avaluo"] = ejemplo_outlier
    
    # ── 6. Preparar columnas finales ───────────────────────────────
    gdf = preparar_columnas_finales(gdf)
    
    # Compute centroid coordinates for spatial operations
    gdf["centroid_x"] = gdf.geometry.centroid.x
    gdf["centroid_y"] = gdf.geometry.centroid.y
    
    # ── 7. Exportar ────────────────────────────────────────────────
    output_dir = BASE / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = output_dir / "predios_limpios.parquet"
    print(f"\n  Exportando a {out_path}...")
    gdf.to_parquet(out_path)
    print(f"  Registros exportados: {len(gdf):,}")
    
    # ── 8. Estadísticas finales ────────────────────────────────────
    print(f"\n  === RESUMEN DEL EMBUDO ===")
    for paso, n in embudo.items():
        print(f"    {paso}: {n:,}")
    
    print(f"\n  Comunas representadas: {gdf['nombre_comuna'].nunique()}")
    print(f"  Avalúo fiscal medio: ${gdf['avaluo_fiscal'].mean():,.0f}")
    print(f"  Avalúo fiscal mediana: ${gdf['avaluo_fiscal'].median():,.0f}")
    print(f"  Superficie media: {gdf['superficie_m2'].mean():,.1f} m²")
    
    elapsed = time.time() - t0
    print(f"\n  Tiempo total: {elapsed:.1f} segundos")
    
    # ── 9. Guardar embudo como JSON ────────────────────────────────
    import json
    embudo_path = output_dir / "embudo_predios.json"
    with open(embudo_path, "w", encoding="utf-8") as f:
        json.dump(embudo, f, indent=2, ensure_ascii=False)
    print(f"  Embudo guardado en {embudo_path}")

    # ── 10. Guardar ejemplos concretos de descarte ─────────────────
    ejemplos_path = output_dir / "ejemplos_limpieza_predios.json"
    with open(ejemplos_path, "w", encoding="utf-8") as f:
        json.dump(ejemplos, f, indent=2, ensure_ascii=False)
    print(f"  Ejemplos de descarte guardados en {ejemplos_path}")

    print("\n✔ Pipeline 02 completado.")


if __name__ == "__main__":
    main()
