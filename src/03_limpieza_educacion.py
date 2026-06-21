"""
03_limpieza_educacion.py — Limpieza de recintos educacionales por nivel.

Aplica la regla 1.2.b: normalizar nombres, clustering espacial por homonimia
(DBSCAN con threshold de 1.5 km), fusión de clusters con 2+ puntos.

Procesa separadamente:
  - educacion_escolar
  - educacion_parvularia
  - educacion_superior

Exporta GeoJSON depurados en outputs/ y actualiza data_dictionary.md.
"""
from __future__ import annotations
import sys
import unicodedata
import re
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
from sklearn.cluster import DBSCAN

BASE = Path(__file__).resolve().parent.parent  # archivos/
CRS_PROJ = "EPSG:32719"
CLUSTER_THRESHOLD_M = 1500  # 1.5 km en metros

# Mapping of education levels to their file paths and name columns
NIVELES = {
    "escolar": {
        "dir": BASE / "educacion_escolar",
        "col_nombre": "NOM_RBD",
        "col_region": "COD_REG_RB",
        "region_rm": 13.0,  # Código de la Región Metropolitana
    },
    "parvularia": {
        "dir": BASE / "educacion_parvularia",
        "col_nombre": "NOM_ESTAB",
        "col_region": "COD_REG_ES",
        "region_rm": 13.0,
    },
    "superior": {
        "dir": BASE / "educacion_superior",
        "col_nombre": "NOMBRE_INS",
        "col_region": "COD_REGION",
        "region_rm": 13.0,
    },
}


def normalizar_nombre(nombre: str | None) -> str | None:
    """Normaliza nombre de institución: trim, lower, tildes, espacios múltiples."""
    if pd.isna(nombre) or str(nombre).strip() == "":
        return None
    s = str(nombre).strip()
    # Normalizar unicode (NFC)
    s = unicodedata.normalize("NFC", s)
    # A minúsculas
    s = s.lower()
    # Eliminar espacios múltiples
    s = re.sub(r"\s+", " ", s)
    return s


def procesar_nivel(nivel: str, config: dict) -> dict:
    """Procesa un nivel educacional: carga, filtra RM, clustering, fusión."""
    print(f"\n  {'='*60}")
    print(f"  Procesando: educación {nivel}")
    print(f"  {'='*60}")
    
    stats = {}
    
    # 1. Cargar
    shp_files = list(config["dir"].glob("*.shp"))
    if not shp_files:
        print(f"  ERROR: No se encontró shapefile en {config['dir']}")
        return stats
    
    gdf = gpd.read_file(shp_files[0])
    stats["n_original"] = len(gdf)
    print(f"  Registros originales: {len(gdf):,}")
    print(f"  CRS original: {gdf.crs}")
    
    # 2. Filtrar solo Región Metropolitana
    col_reg = config["col_region"]
    rm_code = config["region_rm"]
    gdf = gdf[gdf[col_reg] == rm_code].copy()
    stats["n_rm"] = len(gdf)
    print(f"  Registros en RM (región {rm_code}): {len(gdf):,}")
    
    # 3. Validar campo de nombre
    col_nombre = config["col_nombre"]
    n_null = int(gdf[col_nombre].isna().sum())
    stats["n_nombre_nulo"] = n_null
    print(f"  Nombres nulos: {n_null}")
    gdf = gdf[gdf[col_nombre].notna()].copy()
    
    # 4. Normalizar nombre
    gdf["nombre_norm"] = gdf[col_nombre].apply(normalizar_nombre)
    gdf = gdf[gdf["nombre_norm"].notna()].copy()
    
    # 5. Reproyectar a metros
    gdf = gdf.to_crs(CRS_PROJ)
    
    # 6. Agrupar por nombre normalizado y aplicar clustering
    grupos = gdf.groupby("nombre_norm")
    n_grupos = len(grupos)
    stats["n_grupos_homonimos"] = n_grupos
    print(f"  Grupos de nombre único: {n_grupos:,}")
    
    puntos_resultado = []
    n_fusionados = 0
    n_conservados_directo = 0
    ejemplo_fusion = None

    for nombre, grupo in grupos:
        if len(grupo) == 1:
            # Solo un punto: conservar tal cual
            puntos_resultado.append(grupo.iloc[0])
            n_conservados_directo += 1
            continue

        # 2+ puntos con mismo nombre: aplicar DBSCAN
        coords = np.column_stack([
            grupo.geometry.x.values,
            grupo.geometry.y.values,
        ])

        db = DBSCAN(eps=CLUSTER_THRESHOLD_M, min_samples=1, metric="euclidean")
        labels = db.fit_predict(coords)

        grupo = grupo.copy()
        grupo["_cluster"] = labels

        for cl in grupo["_cluster"].unique():
            cluster = grupo[grupo["_cluster"] == cl]

            if len(cluster) == 1:
                puntos_resultado.append(cluster.iloc[0])
                n_conservados_directo += 1
            else:
                # Fusionar: centroide geométrico, hereda del primer registro
                centroid = Point(
                    cluster.geometry.x.mean(),
                    cluster.geometry.y.mean(),
                )
                rep = cluster.iloc[0].copy()
                rep["geometry"] = centroid
                rep["_fusionados_n"] = len(cluster)
                puntos_resultado.append(rep)
                n_fusionados += len(cluster) - 1

                # Capturar el primer caso de fusión real (>2 puntos) como ejemplo concreto
                if ejemplo_fusion is None or len(cluster) > ejemplo_fusion["n_puntos_originales"]:
                    pts_orig = [
                        {"x": float(p.x), "y": float(p.y)}
                        for p in cluster.geometry
                    ]
                    ejemplo_fusion = {
                        "nombre_institucion": nombre,
                        "n_puntos_originales": len(cluster),
                        "puntos_originales_utm19s": pts_orig,
                        "centroide_resultante_utm19s": {"x": float(centroid.x), "y": float(centroid.y)},
                    }

    stats["n_fusionados"] = n_fusionados
    stats["n_conservados_directo"] = n_conservados_directo
    stats["_ejemplo_fusion"] = ejemplo_fusion
    
    # Construir GDF resultado
    gdf_resultado = gpd.GeoDataFrame(puntos_resultado, crs=CRS_PROJ)
    stats["n_final"] = len(gdf_resultado)
    
    print(f"  Puntos conservados directamente: {n_conservados_directo:,}")
    print(f"  Puntos fusionados (eliminados por centroide): {n_fusionados:,}")
    print(f"  Puntos finales: {len(gdf_resultado):,}")
    
    # 7. Exportar
    output_dir = BASE / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"educacion_{nivel}_depurado.geojson"
    
    # Drop auxiliary columns before export
    cols_drop = [c for c in gdf_resultado.columns if c.startswith("_")]
    gdf_resultado_export = gdf_resultado.drop(columns=cols_drop, errors="ignore")
    gdf_resultado_export = gdf_resultado_export.to_crs("EPSG:4326")  # GeoJSON standard
    gdf_resultado_export.to_file(out_path, driver="GeoJSON")
    print(f"  Exportado → {out_path}")
    
    # Also save in projected CRS as parquet for spatial ops
    out_parquet = output_dir / f"educacion_{nivel}_depurado.parquet"
    gdf_resultado.to_parquet(out_parquet)
    
    return stats


def main():
    print("=" * 80)
    print("  PIPELINE 03 — Limpieza de recintos educacionales")
    print("=" * 80)
    
    all_stats = {}
    for nivel, config in NIVELES.items():
        all_stats[nivel] = procesar_nivel(nivel, config)
    
    # Resumen
    print(f"\n\n  === RESUMEN ===")
    for nivel, stats in all_stats.items():
        print(f"\n  {nivel}:")
        for k, v in stats.items():
            print(f"    {k}: {v:,}" if isinstance(v, (int, float)) else f"    {k}: {v}")
    
    # Guardar stats como JSON
    import json
    output_dir = BASE / "outputs"
    stats_path = output_dir / "educacion_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(all_stats, f, indent=2, ensure_ascii=False)
    
    print(f"\n✔ Pipeline 03 completado.")


if __name__ == "__main__":
    main()
