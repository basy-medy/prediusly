"""
04_feature_engineering.py — Feature engineering geoespacial.

Para cada predio limpio de SII_2025, calcula:
  - Distancia y conteo a establecimientos educacionales (escolar, parvularia, superior)
  - Distancia y conteo a establecimientos de salud
  - Distancia y conteo a estaciones de metro
  - Distancia y conteo a paradas de micro
  - Distancia a aeropuerto más cercano
  - Uso de suelo dominante (IPT)
  - Atributos propios del predio

Exporta: outputs/predios_con_features.parquet
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
from scipy.spatial import cKDTree
from shapely.geometry import Point

BASE = Path(__file__).resolve().parent.parent
CRS_PROJ = "EPSG:32719"


def cargar_capa_puntos(path: str | Path, crs_target: str = CRS_PROJ) -> gpd.GeoDataFrame:
    """Carga una capa de puntos y la reproyecta."""
    gdf = gpd.read_file(path)
    if gdf.crs and gdf.crs.to_epsg() != int(crs_target.split(":")[1]):
        gdf = gdf.to_crs(crs_target)
    return gdf


def distancia_y_conteo_kdtree(
    predios_xy: np.ndarray,
    puntos_xy: np.ndarray,
    buffer_m: float = 1000,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Calcula distancia al punto más cercano y conteo dentro de buffer.
    Usa cKDTree para eficiencia con millones de predios.
    
    Returns:
        dist_min: array de distancias mínimas en metros
        count_buffer: array de conteos dentro del buffer
    """
    if len(puntos_xy) == 0:
        return np.full(len(predios_xy), np.nan), np.zeros(len(predios_xy), dtype=int)
    
    tree = cKDTree(puntos_xy)
    
    # Distancia mínima
    dist_min, _ = tree.query(predios_xy, k=1)
    
    # Conteo en buffer
    count_buffer = tree.query_ball_point(predios_xy, r=buffer_m, return_length=True)
    
    return dist_min, np.array(count_buffer, dtype=int)


def features_educacion(predios_xy: np.ndarray, nivel: str) -> dict:
    """Calcula features de educación para un nivel."""
    path = BASE / "outputs" / f"educacion_{nivel}_depurado.parquet"
    if not path.exists():
        print(f"  ⚠ No encontrado: {path}")
        return {}
    
    gdf = gpd.read_parquet(path)
    if gdf.crs.to_epsg() != 32719:
        gdf = gdf.to_crs(CRS_PROJ)
    
    xy = np.column_stack([gdf.geometry.x.values, gdf.geometry.y.values])
    
    dist, count = distancia_y_conteo_kdtree(predios_xy, xy, buffer_m=1000)
    
    return {
        f"dist_edu_{nivel}_m": dist,
        f"count_edu_{nivel}_1km": count,
    }


def features_salud(predios_xy: np.ndarray) -> dict:
    """Calcula features de salud."""
    path = BASE / "salud" / "salud_depurado.geojson"
    if not path.exists():
        print(f"  ⚠ No encontrado: {path}")
        return {}
    
    gdf = gpd.read_file(path).to_crs(CRS_PROJ)
    xy = np.column_stack([gdf.geometry.x.values, gdf.geometry.y.values])
    
    dist, count = distancia_y_conteo_kdtree(predios_xy, xy, buffer_m=1000)
    
    return {
        "dist_salud_m": dist,
        "count_salud_1km": count,
    }


def features_metro(predios_xy: np.ndarray) -> dict:
    """
    Calcula features de metro.

    NOTA: se usan TODAS las estaciones de la capa, sin filtrar por el
    atributo `estacion` (EXISTENTE/CONSTRUCCION/PROYECTADO). Ese atributo
    quedó desactualizado en la fuente: todas las estaciones de la red están
    operativas hoy, incluidas las que la capa todavía marca como en
    construcción o proyectadas.
    """
    path = BASE / "metro.geojson"
    if not path.exists():
        print(f"  ⚠ No encontrado: {path}")
        return {}

    gdf = gpd.read_file(path).to_crs(CRS_PROJ)
    print(f"    Metro: {len(gdf)} estaciones (todas operativas, sin filtrar por estado)")

    xy = np.column_stack([gdf.geometry.x.values, gdf.geometry.y.values])
    
    dist, count = distancia_y_conteo_kdtree(predios_xy, xy, buffer_m=1000)
    
    return {
        "dist_metro_m": dist,
        "count_metro_1km": count,
    }


def features_micro(predios_xy: np.ndarray) -> dict:
    """Calcula features de paradas de micro."""
    micro_dir = BASE / "Paradas_micro"
    shp_files = list(micro_dir.glob("*.shp"))
    if not shp_files:
        print(f"  ⚠ No encontrado shapefile en {micro_dir}")
        return {}
    
    gdf = gpd.read_file(shp_files[0]).to_crs(CRS_PROJ)
    xy = np.column_stack([gdf.geometry.x.values, gdf.geometry.y.values])
    
    dist, count_500 = distancia_y_conteo_kdtree(predios_xy, xy, buffer_m=500)
    _, count_1000 = distancia_y_conteo_kdtree(predios_xy, xy, buffer_m=1000)
    
    return {
        "dist_micro_m": dist,
        "count_micro_500m": count_500,
        "count_micro_1km": count_1000,
    }


def features_aeropuertos(predios_xy: np.ndarray) -> dict:
    """Calcula distancia al aeropuerto más cercano."""
    aero_dir = BASE / "Aeropuertos"
    shp_files = list(aero_dir.glob("*.shp"))
    if not shp_files:
        return {}
    
    gdf = gpd.read_file(shp_files[0]).to_crs(CRS_PROJ)
    xy = np.column_stack([gdf.geometry.x.values, gdf.geometry.y.values])
    
    dist, _ = distancia_y_conteo_kdtree(predios_xy, xy, buffer_m=5000)
    
    return {
        "dist_aeropuerto_m": dist,
    }


def features_red_vial(gdf_predios: gpd.GeoDataFrame) -> pd.Series:
    """
    Distancia euclidiana del centroide del predio al segmento de red vial
    clasificada más cercano (red_vial/Clasificación_Red_Vial_RM.shp).

    LIMITACIÓN DOCUMENTADA: la capa contiene solo 479 segmentos de vías
    clasificadas (red arterial/estructurante regional), no la totalidad de
    calles locales. No es una malla suficientemente densa para un cálculo de
    distancia por red (routing) realista a nivel de predio individual: la
    mayoría de los predios estarían conectados a la red mediante calles
    locales que esta capa no contiene. Por eso se usa distancia euclidiana
    al eje clasificado más cercano como proxy de accesibilidad a la red
    vial estructurante, en vez de distancia por red.
    """
    vial_dir = BASE / "red_vial"
    shp_files = list(vial_dir.glob("*.shp"))
    if not shp_files:
        print(f"  ⚠ No encontrado shapefile en {vial_dir}")
        return pd.Series(np.nan, index=gdf_predios.index)

    gdf_vial = gpd.read_file(shp_files[0])
    if gdf_vial.crs and gdf_vial.crs.to_epsg() != 32719:
        gdf_vial = gdf_vial.to_crs(CRS_PROJ)

    centroids = gpd.GeoDataFrame(geometry=gdf_predios.geometry.centroid, crs=CRS_PROJ)
    centroids["idx_predio"] = centroids.index

    joined = gpd.sjoin_nearest(centroids, gdf_vial[["geometry"]], distance_col="dist_red_vial_m")
    joined = joined.drop_duplicates(subset="idx_predio")
    dist = pd.Series(np.nan, index=gdf_predios.index)
    dist.loc[joined["idx_predio"]] = joined["dist_red_vial_m"].values
    return dist


def features_topografia(gdf_predios: gpd.GeoDataFrame) -> dict:
    """
    Pendiente y elevación aproximadas a partir de curvas de nivel
    (topografia/S34W071.shp — LineString con atributo `elevation`, NO es
    un raster DEM).

    Método: se extraen los vértices de cada curva de nivel (heredando la
    elevación de su línea), se interpola linealmente (triangulación de
    Delaunay) sobre esos vértices, y se evalúa la elevación en el centroide
    de cada predio y en 4 puntos desplazados ±30m (N/S/E/O) para estimar la
    pendiente local por diferencias finitas.

    LIMITACIÓN DOCUMENTADA: el archivo cubre solo la celda SRTM S34W071
    (lat -34 a -33, lon -71 a -70). Comunas al oeste de lon -71.0 (p.ej.
    Melipilla, María Pinto, San Pedro, Curacaví, Alhué) o al sur de
    lat -34.0 (p.ej. San José de Maipo) quedan parcial o totalmente fuera
    de cobertura y reciben NaN en elevación/pendiente. El % de cobertura
    real se reporta en docs/data_dictionary.md.
    """
    topo_dir = BASE / "topografia"
    shp_files = list(topo_dir.glob("*.shp"))
    if not shp_files:
        print(f"  ⚠ No encontrado shapefile en {topo_dir}")
        return {}

    print("    Cargando curvas de nivel y extrayendo vértices...")
    gdf_topo = gpd.read_file(shp_files[0])  # EPSG:4326

    xs, ys, zs = [], [], []
    for geom, elev in zip(gdf_topo.geometry, gdf_topo["elevation"]):
        coords = np.asarray(geom.coords)
        # Sub-muestrear cada 3er vértice para mantener la triangulación tratable
        coords = coords[::3]
        xs.append(coords[:, 0])
        ys.append(coords[:, 1])
        zs.append(np.full(len(coords), elev))
    xs = np.concatenate(xs)
    ys = np.concatenate(ys)
    zs = np.concatenate(zs)
    print(f"    Vértices usados para interpolación: {len(xs):,}")

    # Reproyectar vértices de EPSG:4326 a CRS_PROJ (metros) para que la
    # interpolación y el cálculo de pendiente sean en metros reales
    from pyproj import Transformer
    transformer = Transformer.from_crs("EPSG:4326", CRS_PROJ, always_xy=True)
    xs_m, ys_m = transformer.transform(xs, ys)

    from scipy.interpolate import LinearNDInterpolator
    interp = LinearNDInterpolator(np.column_stack([xs_m, ys_m]), zs)

    centroids = gdf_predios.geometry.centroid
    cx = centroids.x.values
    cy = centroids.y.values

    d = 30.0  # metros, desplazamiento para diferencias finitas
    print("    Evaluando elevación en centroides y puntos desplazados...")
    z0 = interp(cx, cy)
    z_e = interp(cx + d, cy)
    z_w = interp(cx - d, cy)
    z_n = interp(cx, cy + d)
    z_s = interp(cx, cy - d)

    dzdx = (z_e - z_w) / (2 * d)
    dzdy = (z_n - z_s) / (2 * d)
    pendiente_pct = np.sqrt(dzdx**2 + dzdy**2) * 100  # % de pendiente

    n_cobertura = int(np.isfinite(z0).sum())
    print(f"    Predios con cobertura topográfica: {n_cobertura:,}/{len(gdf_predios):,} "
          f"({100*n_cobertura/len(gdf_predios):.1f}%)")

    return {
        "elevacion_m": z0,
        "pendiente_pct": pendiente_pct,
    }


def features_temporal_sii2020(gdf_predios: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Variación porcentual del avalúo fiscal entre 2020 y 2025 para cada predio.

    SII_2020/SII_USOS_SUELO.shp NO contiene predios individuales: es un
    archivo pre-agregado a nivel de MANZANA censal (40,485 manzanas en la
    RM), con sumas de superficie por destino (S_T_DEST_*) y avalúo total
    de la manzana (Avaluo_rol). No comparte un ID de predio (ROL) con
    SII_2025, por lo que el cruce temporal NO puede hacerse por ROL.

    Método de cruce espacial documentado:
      1. Filtrar manzanas 2020 con UBICACION == 'U' (urbana) y
         DESTINO == 'H' (predominantemente habitacional), S_T_TOTAL > 0
         y Avaluo_rol > 0.
      2. Calcular avaluo_2020_per_m2_manzana = Avaluo_rol / S_T_TOTAL
         (CLP/m² nominal de 2020, sin ajuste por inflación).
      3. Unir espacialmente (point-in-polygon) el centroide de cada predio
         2025 con la manzana 2020 que lo contiene.
      4. variacion_avaluo_pct = (avaluo_2025_per_m2 - avaluo_2020_per_m2_manzana)
         / avaluo_2020_per_m2_manzana * 100

    LIMITACIÓN DOCUMENTADA: esta es una comparación predio-vs-promedio de
    su manzana (inferencia ecológica), no predio-vs-mismo-predio, y es en
    pesos nominales (no corregidos por inflación 2020→2025). Predios cuyo
    centroide no cae dentro de ninguna manzana 2020 filtrada quedan en NaN.
    """
    sii2020_path = BASE / "SII_2020" / "SII_USOS_SUELO.shp"
    if not sii2020_path.exists():
        print(f"  ⚠ No encontrado: {sii2020_path}")
        return pd.DataFrame(index=gdf_predios.index)

    gdf_2020 = gpd.read_file(sii2020_path)  # ya en EPSG:32719
    if gdf_2020.crs.to_epsg() != 32719:
        gdf_2020 = gdf_2020.to_crs(CRS_PROJ)

    mask = (
        (gdf_2020["UBICACION"] == "U") &
        (gdf_2020["DESTINO"] == "H") &
        (gdf_2020["S_T_TOTAL"] > 0) &
        (gdf_2020["Avaluo_rol"] > 0)
    )
    gdf_2020_f = gdf_2020[mask].copy()
    gdf_2020_f["avaluo_2020_per_m2_manzana"] = gdf_2020_f["Avaluo_rol"] / gdf_2020_f["S_T_TOTAL"]
    print(f"    Manzanas 2020 utilizables (urbana + habitacional): {len(gdf_2020_f):,}/{len(gdf_2020):,}")

    centroids = gpd.GeoDataFrame(geometry=gdf_predios.geometry.centroid, crs=CRS_PROJ)
    centroids["idx_predio"] = centroids.index
    joined = gpd.sjoin(
        centroids,
        gdf_2020_f[["avaluo_2020_per_m2_manzana", "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined.drop_duplicates(subset="idx_predio")
    joined = joined.set_index("idx_predio").reindex(gdf_predios.index)

    n_match = int(joined["avaluo_2020_per_m2_manzana"].notna().sum())
    print(f"    Predios con manzana 2020 asociada: {n_match:,}/{len(gdf_predios):,} "
          f"({100*n_match/len(gdf_predios):.1f}%)")

    avaluo_2025_per_m2 = gdf_predios["avaluo_fiscal"] / gdf_predios["superficie_m2"]
    variacion_pct = (
        (avaluo_2025_per_m2.values - joined["avaluo_2020_per_m2_manzana"].values)
        / joined["avaluo_2020_per_m2_manzana"].values * 100
    )

    return pd.DataFrame({
        "avaluo_2020_per_m2_manzana": joined["avaluo_2020_per_m2_manzana"].values,
        "variacion_avaluo_pct_2020_2025": variacion_pct,
    }, index=gdf_predios.index)


def features_uso_suelo(gdf_predios: gpd.GeoDataFrame) -> pd.Series:
    """
    Determina uso de suelo dominante en buffer de 250m del predio.
    Usa spatial join con la capa IPT PRMS USO Suelo.
    """
    ipt_path = BASE / "IPT_Metropolitana" / "PRMS" / "IPT_13_PRMS_USO_Suelo.shp"
    if not ipt_path.exists():
        print(f"  ⚠ No encontrado: {ipt_path}")
        return pd.Series("SIN_DATO", index=gdf_predios.index)
    
    gdf_ipt = gpd.read_file(ipt_path)
    if gdf_ipt.crs.to_epsg() != 32719:
        gdf_ipt = gdf_ipt.to_crs(CRS_PROJ)
    
    # Fix invalid geometries in IPT
    from shapely.validation import make_valid
    invalid_mask = ~gdf_ipt.geometry.is_valid
    if invalid_mask.any():
        gdf_ipt.loc[invalid_mask, "geometry"] = gdf_ipt.loc[invalid_mask].geometry.apply(make_valid)
    
    # Use centroid of predios with 250m buffer
    centroids = gdf_predios.geometry.centroid
    buffers = centroids.buffer(250)
    gdf_buf = gpd.GeoDataFrame(geometry=buffers, crs=CRS_PROJ)
    gdf_buf["idx_predio"] = gdf_buf.index
    
    # Process in chunks to avoid memory issues
    chunk_size = 50000
    n = len(gdf_buf)
    uso_result = pd.Series("SIN_DATO", index=gdf_predios.index)
    
    for i in range(0, n, chunk_size):
        chunk = gdf_buf.iloc[i : i + chunk_size]
        joined = gpd.sjoin(chunk, gdf_ipt[["UPREF", "geometry"]], how="left", predicate="intersects")
        
        if not joined.empty:
            # Get dominant UPREF per predio
            dominant = (
                joined.groupby("idx_predio")["UPREF"]
                .agg(lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else "SIN_DATO")
            )
            uso_result.loc[dominant.index] = dominant
        
        if (i + chunk_size) % 200000 == 0:
            print(f"    Uso de suelo: procesados {min(i + chunk_size, n):,}/{n:,}")
    
    return uso_result


def main():
    t0 = time.time()
    print("=" * 80)
    print("  PIPELINE 04 — Feature Engineering Geoespacial")
    print("=" * 80)
    
    # ── 1. Cargar predios limpios ──────────────────────────────────
    pred_path = BASE / "outputs" / "predios_limpios.parquet"
    if not pred_path.exists():
        sys.exit(f"ERROR: {pred_path} no existe. Ejecutar 02_limpieza_predios.py primero.")
    
    print("  Cargando predios limpios...")
    gdf = gpd.read_parquet(pred_path)
    print(f"  Predios cargados: {len(gdf):,}")
    
    if gdf.crs.to_epsg() != 32719:
        gdf = gdf.to_crs(CRS_PROJ)
    
    # Coordenadas de centroides para KDTree
    centroids = gdf.geometry.centroid
    predios_xy = np.column_stack([centroids.x.values, centroids.y.values])
    
    # ── 2. Features de educación ───────────────────────────────────
    print("\n  [Educación]")
    for nivel in ["escolar", "parvularia", "superior"]:
        print(f"  Calculando features educación {nivel}...")
        feats = features_educacion(predios_xy, nivel)
        for col, vals in feats.items():
            gdf[col] = vals
        print(f"    {nivel}: dist_media={gdf[f'dist_edu_{nivel}_m'].mean():,.0f}m, count_1km_media={gdf[f'count_edu_{nivel}_1km'].mean():.1f}")
    
    # ── 3. Features de salud ───────────────────────────────────────
    print("\n  [Salud]")
    feats = features_salud(predios_xy)
    for col, vals in feats.items():
        gdf[col] = vals
    print(f"    dist_media={gdf['dist_salud_m'].mean():,.0f}m, count_1km_media={gdf['count_salud_1km'].mean():.1f}")
    
    # ── 4. Features de metro ───────────────────────────────────────
    print("\n  [Metro]")
    feats = features_metro(predios_xy)
    for col, vals in feats.items():
        gdf[col] = vals
    print(f"    dist_media={gdf['dist_metro_m'].mean():,.0f}m, count_1km_media={gdf['count_metro_1km'].mean():.1f}")
    
    # ── 5. Features de micro ───────────────────────────────────────
    print("\n  [Paradas de micro]")
    feats = features_micro(predios_xy)
    for col, vals in feats.items():
        gdf[col] = vals
    print(f"    dist_media={gdf['dist_micro_m'].mean():,.0f}m, count_500m_media={gdf['count_micro_500m'].mean():.1f}")
    
    # ── 6. Features de aeropuerto ──────────────────────────────────
    print("\n  [Aeropuertos]")
    feats = features_aeropuertos(predios_xy)
    for col, vals in feats.items():
        gdf[col] = vals
    print(f"    dist_media={gdf['dist_aeropuerto_m'].mean():,.0f}m")
    
    # ── 7. Uso de suelo (IPT) ─────────────────────────────────────
    print("\n  [Uso de suelo IPT]")
    print("    Calculando uso de suelo dominante en buffer 250m...")
    gdf["uso_suelo_ipt"] = features_uso_suelo(gdf)
    print(f"    Distribución: {gdf['uso_suelo_ipt'].value_counts().head(10).to_dict()}")

    # ── 7b. Red vial ───────────────────────────────────────────────
    print("\n  [Red vial]")
    gdf["dist_red_vial_m"] = features_red_vial(gdf)
    print(f"    dist_media={gdf['dist_red_vial_m'].mean():,.0f}m")

    # ── 7c. Topografía (pendiente y elevación) ─────────────────────
    print("\n  [Topografía]")
    feats_topo = features_topografia(gdf)
    for col, vals in feats_topo.items():
        gdf[col] = vals
    if feats_topo:
        print(f"    elevación media={gdf['elevacion_m'].mean():,.0f}m, "
              f"pendiente media={gdf['pendiente_pct'].mean():.1f}%")

    # ── 7d. Variable temporal (SII_2020 → SII_2025) ────────────────
    print("\n  [Variación temporal de avalúo 2020-2025]")
    feats_temp = features_temporal_sii2020(gdf)
    for col in feats_temp.columns:
        gdf[col] = feats_temp[col].values
    print(f"    variación media: {gdf['variacion_avaluo_pct_2020_2025'].mean():.1f}%, "
          f"mediana: {gdf['variacion_avaluo_pct_2020_2025'].median():.1f}%")

    # ── 8. Atributos propios del predio ────────────────────────────
    print("\n  [Atributos propios]")
    # Log-transform avaluo for modeling
    gdf["log_avaluo"] = np.log1p(gdf["avaluo_fiscal"])
    gdf["log_superficie"] = np.log1p(gdf["superficie_m2"])
    
    # ── 9. Estadísticas de features ────────────────────────────────
    feature_cols = [c for c in gdf.columns if c.startswith(("dist_", "count_", "log_"))]
    print(f"\n  Features calculadas ({len(feature_cols)}):")
    for col in sorted(feature_cols):
        series = gdf[col]
        print(f"    {col:<30s}  media={series.mean():>12,.1f}  mediana={series.median():>12,.1f}  nulos={series.isna().sum()}")
    
    # ── 10. Exportar ───────────────────────────────────────────────
    output_dir = BASE / "outputs"
    out_path = output_dir / "predios_con_features.parquet"
    print(f"\n  Exportando a {out_path}...")
    gdf.to_parquet(out_path)
    print(f"  Registros exportados: {len(gdf):,}")
    
    elapsed = time.time() - t0
    print(f"\n  Tiempo total: {elapsed:.1f} segundos")
    print("\n✔ Pipeline 04 completado.")


if __name__ == "__main__":
    main()
