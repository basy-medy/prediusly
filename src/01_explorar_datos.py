"""
01_explorar_datos.py — Exploración inicial de todas las fuentes de datos.

Inspecciona cada fuente para determinar:
  - Formato y extensión real
  - CRS detectado
  - Número de registros
  - Columnas y tipos
  - % de nulos por columna
  - Tipo de geometría
  - Valores únicos de campos clave (primeros 10)
  - Duplicados

Imprime un reporte completo para informar las decisiones de limpieza.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import geopandas as gpd
import pandas as pd
import pyogrio

BASE = Path(__file__).resolve().parent.parent  # archivos/

def separador(titulo: str) -> None:
    print(f"\n{'='*80}")
    print(f"  {titulo}")
    print(f"{'='*80}")

def explorar_gdf(gdf: gpd.GeoDataFrame, nombre: str, max_unique: int = 10) -> dict:
    """Explora un GeoDataFrame e imprime estadísticas."""
    info = {}
    n = len(gdf)
    info["n_registros"] = n
    info["crs"] = str(gdf.crs) if gdf.crs else "SIN CRS"
    info["geom_types"] = gdf.geometry.geom_type.value_counts().to_dict() if gdf.geometry is not None else {}
    
    print(f"\n  Fuente: {nombre}")
    print(f"  Registros: {n:,}")
    print(f"  CRS: {info['crs']}")
    print(f"  Tipos de geometría: {info['geom_types']}")
    
    # Columnas
    print(f"\n  Columnas ({len(gdf.columns)}):")
    for col in gdf.columns:
        if col == "geometry":
            continue
        n_null = int(gdf[col].isna().sum())
        pct_null = (n_null / n * 100) if n > 0 else 0
        dtype = str(gdf[col].dtype)
        n_unique = gdf[col].nunique()
        print(f"    {col:<40s}  tipo={dtype:<15s}  nulos={n_null:>6d} ({pct_null:.1f}%)  únicos={n_unique}")
        
        # Mostrar primeros valores únicos para campos clave
        if n_unique <= max_unique and n_unique > 0:
            try:
                vals = sorted(gdf[col].dropna().unique().tolist()[:max_unique], key=str)
                print(f"      Valores: {vals}")
            except:
                pass
    
    # Geometrías inválidas
    if gdf.geometry is not None and not gdf.geometry.isna().all():
        try:
            n_invalid = int((~gdf.geometry.is_valid).sum())
        except:
            n_invalid = -1
        n_empty = int(gdf.geometry.is_empty.sum())
        print(f"\n  Geometrías inválidas: {n_invalid}")
        print(f"  Geometrías vacías: {n_empty}")
    
    # Duplicados
    cols_no_geom = [c for c in gdf.columns if c != "geometry"]
    if cols_no_geom:
        n_dup = int(gdf[cols_no_geom].duplicated().sum())
        print(f"  Filas duplicadas (sin geometría): {n_dup}")
    
    # Bounds
    try:
        bounds = gdf.total_bounds
        print(f"  Extensión (minx, miny, maxx, maxy): {bounds}")
    except:
        pass
    
    return info

def main():
    
    # ═══════════════════════════════════════════════════════════════════
    # 1. SII_2025 (Parquet files por comuna)
    # ═══════════════════════════════════════════════════════════════════
    separador("SII_2025 — Predios con avalúo fiscal 2025")
    sii25_dir = BASE / "SII_2025"
    archivos_2025 = sorted(sii25_dir.glob("*.parquet"))
    print(f"  Archivos parquet encontrados: {len(archivos_2025)}")
    
    # Leer un archivo de muestra para ver esquema
    if archivos_2025:
        muestra = pd.read_parquet(archivos_2025[0])
        print(f"\n  Muestra: {archivos_2025[0].name}")
        print(f"  Registros en muestra: {len(muestra):,}")
        print(f"  Columnas ({len(muestra.columns)}):")
        for col in muestra.columns:
            n_null = int(muestra[col].isna().sum())
            pct_null = (n_null / len(muestra) * 100) if len(muestra) > 0 else 0
            dtype = str(muestra[col].dtype)
            n_unique = muestra[col].nunique()
            print(f"    {col:<40s}  tipo={dtype:<15s}  nulos={n_null:>6d} ({pct_null:.1f}%)  únicos={n_unique}")
            if n_unique <= 15 and n_unique > 0:
                try:
                    vals = sorted(muestra[col].dropna().unique().tolist()[:15], key=str)
                    print(f"      Valores: {vals}")
                except:
                    pass
        
        # Check if geometry column exists
        geom_cols = [c for c in muestra.columns if 'geom' in c.lower() or 'wkt' in c.lower() or 'polygon' in c.lower() or 'shape' in c.lower()]
        print(f"\n  Columnas con posible geometría: {geom_cols}")
        
        # Show first row as example
        print(f"\n  Primera fila de ejemplo:")
        for col in muestra.columns:
            val = muestra.iloc[0][col]
            val_str = str(val)
            if len(val_str) > 200:
                val_str = val_str[:200] + "..."
            print(f"    {col}: {val_str}")
        
        # Count total records across all files
        total = 0
        for f in archivos_2025:
            df_temp = pd.read_parquet(f, columns=[muestra.columns[0]])
            total += len(df_temp)
        print(f"\n  Total registros SII_2025 (todos los archivos): {total:,}")

    # ═══════════════════════════════════════════════════════════════════
    # 2. SII_2020 (Shapefile)
    # ═══════════════════════════════════════════════════════════════════
    separador("SII_2020 — Predios con avalúo fiscal 2020")
    sii20_dir = BASE / "SII_2020"
    shp_2020 = list(sii20_dir.glob("*.shp"))
    print(f"  Shapefiles encontrados: {[f.name for f in shp_2020]}")
    
    if shp_2020:
        # Read only first N records for exploration
        gdf_20 = gpd.read_file(shp_2020[0], rows=1000)
        explorar_gdf(gdf_20, f"SII_2020/{shp_2020[0].name} (primeras 1000 filas)")
        
        # Total count using pyogrio
        info = pyogrio.read_info(shp_2020[0])
        print(f"\n  Total registros SII_2020: {info['features']:,}")
        print(f"  CRS según pyogrio: {info.get('crs', 'N/A')}")

    # ═══════════════════════════════════════════════════════════════════
    # 3. Educación Escolar
    # ═══════════════════════════════════════════════════════════════════
    separador("Educación Escolar")
    edu_esc = BASE / "educacion_escolar"
    shp_files = list(edu_esc.glob("*.shp"))
    if shp_files:
        gdf = gpd.read_file(shp_files[0])
        explorar_gdf(gdf, f"educacion_escolar/{shp_files[0].name}")

    # ═══════════════════════════════════════════════════════════════════
    # 4. Educación Parvularia
    # ═══════════════════════════════════════════════════════════════════
    separador("Educación Parvularia")
    edu_parv = BASE / "educacion_parvularia"
    shp_files = list(edu_parv.glob("*.shp"))
    if shp_files:
        gdf = gpd.read_file(shp_files[0])
        explorar_gdf(gdf, f"educacion_parvularia/{shp_files[0].name}")

    # ═══════════════════════════════════════════════════════════════════
    # 5. Educación Superior
    # ═══════════════════════════════════════════════════════════════════
    separador("Educación Superior")
    edu_sup = BASE / "educacion_superior"
    shp_files = list(edu_sup.glob("*.shp"))
    if shp_files:
        gdf = gpd.read_file(shp_files[0])
        explorar_gdf(gdf, f"educacion_superior/{shp_files[0].name}")

    # ═══════════════════════════════════════════════════════════════════
    # 6. Salud (depurado - already cleaned)
    # ═══════════════════════════════════════════════════════════════════
    separador("Salud (depurado)")
    salud_dep = BASE / "salud" / "salud_depurado.geojson"
    if salud_dep.exists():
        gdf = gpd.read_file(salud_dep)
        explorar_gdf(gdf, "salud/depurado")

    # ═══════════════════════════════════════════════════════════════════
    # 7. Metro
    # ═══════════════════════════════════════════════════════════════════
    separador("Metro")
    metro_file = BASE / "metro.geojson"
    if metro_file.exists():
        gdf = gpd.read_file(metro_file)
        explorar_gdf(gdf, "metro.geojson")
        print(f"\n  Primeras 5 filas (nombre/tipo):")
        for _, row in gdf.head(5).iterrows():
            cols_show = [c for c in gdf.columns if c != 'geometry']
            for c in cols_show:
                print(f"    {c}: {row[c]}")
            print(f"    geom_type: {row.geometry.geom_type}")
            print()

    # ═══════════════════════════════════════════════════════════════════
    # 8. Paradas de micro
    # ═══════════════════════════════════════════════════════════════════
    separador("Paradas de micro")
    micro_dir = BASE / "Paradas_micro"
    shp_files = list(micro_dir.glob("*.shp"))
    if shp_files:
        gdf = gpd.read_file(shp_files[0])
        explorar_gdf(gdf, f"Paradas_micro/{shp_files[0].name}")

    # ═══════════════════════════════════════════════════════════════════
    # 9. Aeropuertos
    # ═══════════════════════════════════════════════════════════════════
    separador("Aeropuertos")
    aero_dir = BASE / "Aeropuertos"
    shp_files = list(aero_dir.glob("*.shp"))
    if shp_files:
        gdf = gpd.read_file(shp_files[0])
        explorar_gdf(gdf, f"Aeropuertos/{shp_files[0].name}")

    # ═══════════════════════════════════════════════════════════════════
    # 10. Red Vial
    # ═══════════════════════════════════════════════════════════════════
    separador("Red Vial")
    vial_dir = BASE / "red_vial"
    shp_files = list(vial_dir.glob("*.shp"))
    if shp_files:
        gdf = gpd.read_file(shp_files[0])
        explorar_gdf(gdf, f"red_vial/{shp_files[0].name}")

    # ═══════════════════════════════════════════════════════════════════
    # 11. IPT Metropolitana — PRMS USO_Suelo (la principal)
    # ═══════════════════════════════════════════════════════════════════
    separador("IPT Metropolitana — PRMS USO Suelo")
    ipt_uso = BASE / "IPT_Metropolitana" / "PRMS" / "IPT_13_PRMS_USO_Suelo.shp"
    if ipt_uso.exists():
        gdf = gpd.read_file(ipt_uso)
        explorar_gdf(gdf, "IPT_PRMS_USO_Suelo")

    # ═══════════════════════════════════════════════════════════════════
    # 12. IPT LU (Límite Urbano)
    # ═══════════════════════════════════════════════════════════════════
    separador("IPT LU (Límite Urbano)")
    ipt_lu = BASE / "IPT_Metropolitana" / "LU" / "IPT_13_LU.shp"
    if ipt_lu.exists():
        gdf = gpd.read_file(ipt_lu)
        explorar_gdf(gdf, "IPT_LU")

    # ═══════════════════════════════════════════════════════════════════
    # 13. Topografía
    # ═══════════════════════════════════════════════════════════════════
    separador("Topografía")
    topo_dir = BASE / "topografia"
    shp_files = list(topo_dir.glob("*.shp"))
    if shp_files:
        # This may be large - read only 500 rows
        gdf = gpd.read_file(shp_files[0], rows=500)
        explorar_gdf(gdf, f"topografia/{shp_files[0].name} (primeras 500 filas)")
        info = pyogrio.read_info(shp_files[0])
        print(f"\n  Total registros topografía: {info['features']:,}")

    # ═══════════════════════════════════════════════════════════════════
    # 14. RM.gpkg
    # ═══════════════════════════════════════════════════════════════════
    separador("RM.gpkg")
    rm_file = BASE / "RM.gpkg"
    if rm_file.exists():
        layers = pyogrio.list_layers(rm_file)
        print(f"  Capas en RM.gpkg: {layers}")
        for layer_info in layers:
            layer_name = layer_info[0] if isinstance(layer_info, (list, tuple)) else str(layer_info)
            gdf = gpd.read_file(rm_file, layer=layer_name)
            explorar_gdf(gdf, f"RM.gpkg / {layer_name}")

    print("\n\n✔ Exploración completada.")


if __name__ == "__main__":
    main()
