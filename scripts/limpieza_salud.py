"""
Pipeline 1.2.c — Limpieza de establecimientos de salud: exclusión por categoría de "tipo".

Carga el GeoJSON de establecimientos de salud, normaliza el campo "tipo",
descarta registros con "tipo" nulo y elimina las categorías no relevantes
para el análisis de accesibilidad (servicios remotos, especializados de
baja frecuencia de visita o administrativos).

Exporta:
  - GeoJSON depurado en  salud/salud_depurado.geojson
  - Estadísticas de limpieza impresas en consola (para docs/data_dictionary.md)

Autor: equipo data-science UC 2026-1
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

# ──────────────────────────────────────────────────────────────────────
# CONSTANTE CONFIGURABLE — categorías de "tipo" a excluir
# ──────────────────────────────────────────────────────────────────────
# Cada entrada se compara en minúsculas y sin espacios extra contra el
# campo "tipo" normalizado.  Para agregar o quitar categorías basta con
# editar esta lista.
#
# Criterio de exclusión:
#   - atencion_remota  → no hay atención presencial
#   - dental           → atención dental especializada (baja frecuencia)
#   - dialisis         → tratamiento crónico especializado
#   - especialidad     → centros de especialidad / referencia
#   - ambiental        → salud ambiental (administrativa)
#   - cta              → centros de tratamiento de adicciones
#   - setm             → salas externas de toma de muestras
#   - laboratorio      → laboratorios clínicos (sin atención directa)
#   - vacunatorio      → vacunatorios (servicio puntual)
#   - radiologico      → centros radiológicos (diagnóstico)
#   - sangre_tejidos   → centros de sangre (bancos)
#   - regulacion_samu  → regulación de urgencias (administrativo)
#   - funcionarios     → unidades/policlínicos para funcionarios
#   - conin            → corporación nutrición infantil (programa específico)
#   - prais            → programa de reparación (programa específico)
#   - direccion_ss     → dirección de servicio de salud (administrativo)
#   - oficina_sanitaria→ oficina sanitaria (administrativa)
#   - movil            → unidades/clínicas móviles
# ──────────────────────────────────────────────────────────────────────

CATEGORIAS_EXCLUIDAS_SALUD: list[str] = [
    "atencion_remota",
    "dental",
    "dialisis",
    "especialidad",
    "ambiental",
    "cta",
    "setm",
    "laboratorio",
    "vacunatorio",
    "radiologico",
    "sangre_tejidos",
    "regulacion_samu",
    "funcionarios",
    "conin",
    "prais",
    "direccion_ss",
    "oficina_sanitaria",
    "movil",
]


def _normalizar_tipo(valor: str | None) -> str | None:
    """
    Convierte el valor descriptivo del campo "tipo" a una clave corta
    normalizada para poder comparar contra CATEGORIAS_EXCLUIDAS_SALUD.

    Reglas:
      1. Si es nulo/vacío → devuelve None.
      2. Pasa a minúsculas y elimina espacios extra.
      3. Busca coincidencia por subcadena con un mapa de patrones.
         Si ningún patrón coincide, devuelve el valor normalizado tal cual.
    """
    if pd.isna(valor) or str(valor).strip() == "":
        return None

    v = str(valor).strip().lower()

    # Mapa de patrones → clave corta.
    # El orden importa: patrones más específicos van primero.
    patrones: list[tuple[str, str]] = [
        ("atencion remota",           "atencion_remota"),
        ("atención remota",           "atencion_remota"),
        ("clinica dental movil",      "dental"),
        ("clínica dental móvil",      "dental"),
        ("clinica dental",            "dental"),
        ("clínica dental",            "dental"),
        ("sapu dental",               "dental"),
        ("dialisis",                  "dialisis"),
        ("diálisis",                  "dialisis"),
        ("centro de especialidades primarias", "especialidad"),
        ("centro de especialidad",    "especialidad"),
        ("centro de referencia de salud", "especialidad"),
        ("salud ambiental",           "ambiental"),
        ("tratamiento de adicciones",  "cta"),
        ("toma de muestras",          "setm"),
        ("laboratorio",               "laboratorio"),
        ("vacunatorio",               "vacunatorio"),
        ("radiologico",               "radiologico"),
        ("radiológico",               "radiologico"),
        ("sangre y tejidos",          "sangre_tejidos"),
        ("regulacion medica",         "regulacion_samu"),
        ("regulación médica",         "regulacion_samu"),
        ("funcionarios",              "funcionarios"),
        ("conin",                     "conin"),
        ("nutricion infantil",        "conin"),
        ("nutrición infantil",        "conin"),
        ("prais",                     "prais"),
        ("reparacion y atencion",     "prais"),
        ("reparación y atención",     "prais"),
        ("direccion servicio",        "direccion_ss"),
        ("dirección servicio",        "direccion_ss"),
        ("oficina sanitaria",         "oficina_sanitaria"),
        ("unidad de procedimientos movil",   "movil"),
        ("unidad de procedimientos móvil",   "movil"),
        # -- categorías que se CONSERVAN (no excluidas) --
        ("posta de salud rural",      "psr"),
        ("cesfam",                    "cesfam"),
        ("cecosf",                    "cecosf"),
        ("sapu",                      "sapu"),        # SAPU genérico (no dental)
        ("hospital de dia",           "hospital_dia"),
        ("hospital de día",           "hospital_dia"),
        ("hospital",                  "hospital"),
        ("urgencia rural",            "sur"),
        ("sar",                       "sar"),
        ("cosam",                     "cosam"),
        ("diagnostico terapeutico",   "cdt"),
        ("diagnóstico terapéutico",   "cdt"),
        ("diagnóstico terapeútico",   "cdt"),  # variante ortográfica en datos
        ("clinica",                   "clinica"),
        ("clínica",                   "clinica"),
        ("centro de salud privado",   "centro_salud_privado"),
        ("centro de salud publico",   "centro_salud_publico"),
        ("centro de salud público",   "centro_salud_publico"),
        ("centro de salud mental",    "centro_salud_mental"),
        ("consultorio general rural", "cgr"),
        ("consultorio general urbano","cgu"),
        ("rehabilitacion",            "rehabilitacion"),
        ("rehabilitación",            "rehabilitacion"),
        ("apoyo comunitario",         "apoyo_demencia"),
        ("demencia",                  "apoyo_demencia"),
        ("oftalmologica",             "uapo"),
        ("oftalmológica",             "uapo"),
        ("pame",                      "pame"),
        ("resolutividad",             "resolutividad"),
        ("salud de atencion cerrada", "atencion_cerrada"),
        ("salud de atención cerrada", "atencion_cerrada"),
        ("estacion medica rural",     "emr"),
        ("estación médica rural",     "emr"),
        ("samu",                      "regulacion_samu"),
    ]

    for patron, clave in patrones:
        if patron in v:
            return clave

    # Si no hubo coincidencia, devolver el texto normalizado
    return v


def main() -> None:
    # Evitar errores de codificación en consola Windows (cp1252 → utf-8)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # ── 0. Rutas ─────────────────────────────────────────────────────
    base = Path(__file__).resolve().parent.parent  # archivos/
    ruta_entrada = base / "salud" / "l_990_v1_establecimientos_de_salud_febrero_2026.geojson"
    ruta_salida  = base / "salud" / "salud_depurado.geojson"
    ruta_docs    = base / "docs"
    ruta_docs.mkdir(parents=True, exist_ok=True)

    # ── 1. Cargar ────────────────────────────────────────────────────
    print(f"Cargando {ruta_entrada.name} …")
    gdf_salud = gpd.read_file(ruta_entrada)
    n_original = len(gdf_salud)
    print(f"  Registros originales: {n_original}")

    # ── 2. Validar campo "tipo" ──────────────────────────────────────
    if "tipo" not in gdf_salud.columns:
        sys.exit("ERROR: el campo 'tipo' no existe en los datos.")

    n_nulos = int(gdf_salud["tipo"].isna().sum())
    print(f"  Registros con 'tipo' nulo: {n_nulos} → se descartan")

    # ── 3. Normalizar "tipo" ─────────────────────────────────────────
    gdf_salud["tipo_norm"] = gdf_salud["tipo"].apply(_normalizar_tipo)

    # Mostrar mapeo para auditoría
    print("\n  Mapeo tipo original → tipo normalizado:")
    mapeo = (
        gdf_salud[["tipo", "tipo_norm"]]
        .drop_duplicates()
        .sort_values("tipo_norm")
    )
    for _, row in mapeo.iterrows():
        print(f"    {row['tipo']!s:<80s} → {row['tipo_norm']}")

    # ── 4. Conteo por categoría excluida ─────────────────────────────
    mascara_nulo    = gdf_salud["tipo_norm"].isna()
    mascara_excluir = gdf_salud["tipo_norm"].isin(CATEGORIAS_EXCLUIDAS_SALUD)

    conteo_excluidos = (
        gdf_salud.loc[mascara_excluir, "tipo_norm"]
        .value_counts()
        .sort_index()
    )

    print("\n  Conteo por categoría excluida:")
    for cat, n in conteo_excluidos.items():
        print(f"    {cat:<25s}  {n:>5d}")
    n_excluidos_cat = int(mascara_excluir.sum())
    print(f"  Total excluidos por categoría: {n_excluidos_cat}")

    # ── 5. Filtrar ───────────────────────────────────────────────────
    gdf_salud_depurado = gdf_salud[
        gdf_salud["tipo_norm"].notna()
        & ~gdf_salud["tipo_norm"].isin(CATEGORIAS_EXCLUIDAS_SALUD)
    ].copy()

    n_final = len(gdf_salud_depurado)
    print(f"\n  Registros finales (depurados): {n_final}")
    print(f"  Resumen: {n_original} - {n_nulos} (nulos) - {n_excluidos_cat} (excluidos) = {n_final}")

    # ── 4b. Ejemplo concreto de registro excluido (categoría más numerosa) ──
    cat_mas_numerosa = conteo_excluidos.idxmax() if len(conteo_excluidos) else None
    ejemplo_excluido = None
    if cat_mas_numerosa is not None:
        fila = gdf_salud.loc[gdf_salud["tipo_norm"] == cat_mas_numerosa].iloc[0]
        cols_nombre = [c for c in ["nombre", "NOMBRE", "establecimiento"] if c in gdf_salud.columns]
        ejemplo_excluido = {
            "categoria_normalizada": cat_mas_numerosa,
            "tipo_original": str(fila["tipo"]),
            "nombre_establecimiento": str(fila[cols_nombre[0]]) if cols_nombre else None,
            "n_registros_en_categoria": int(conteo_excluidos[cat_mas_numerosa]),
        }
        ejemplos_path = base / "outputs" / "ejemplos_limpieza_salud.json"
        ejemplos_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(ejemplos_path, "w", encoding="utf-8") as f:
            json.dump(ejemplo_excluido, f, indent=2, ensure_ascii=False)
        print(f"\n  Ejemplo de exclusión guardado en {ejemplos_path}")

    # Conteo de categorías conservadas
    conteo_conservados = (
        gdf_salud_depurado["tipo_norm"]
        .value_counts()
        .sort_index()
    )
    print("\n  Categorías conservadas:")
    for cat, n in conteo_conservados.items():
        print(f"    {cat:<30s}  {n:>5d}")

    # ── 6. Exportar GeoJSON depurado ─────────────────────────────────
    # Eliminar columna auxiliar tipo_norm antes de exportar
    gdf_salud_depurado = gdf_salud_depurado.drop(columns=["tipo_norm"])
    gdf_salud_depurado.to_file(ruta_salida, driver="GeoJSON")
    print(f"\n  Exportado → {ruta_salida}")

    # ── 7. Guardar stats + sección markdown reusable (NO se escribe directo
    #       en docs/data_dictionary.md para evitar duplicar secciones en
    #       reruns; el script maestro de docs/data_dictionary.md la incorpora) ──
    stats_path = base / "outputs" / "salud_stats.json"
    import json
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump({
            "n_original": n_original,
            "n_nulos": n_nulos,
            "n_excluidos_categoria": n_excluidos_cat,
            "n_final": n_final,
            "conteo_excluidos": conteo_excluidos.to_dict(),
            "conteo_conservados": conteo_conservados.to_dict(),
        }, f, indent=2, ensure_ascii=False)
    print(f"  Stats → {stats_path}")

    dd_path = ruta_docs / "_salud_section.md"

    # Preparar tablas Markdown
    lineas: list[str] = []

    lineas.append("## 1.2.c Limpieza establecimientos de salud — exclusión por categoría de tipo\n")
    lineas.append(f"- **Archivo fuente**: `{ruta_entrada.name}`")
    lineas.append(f"- **Archivo depurado**: `{ruta_salida.name}`")
    lineas.append(f"- **Registros originales**: {n_original}")
    lineas.append(f"- **Registros con tipo nulo (descartados)**: {n_nulos}")
    lineas.append(f"- **Registros excluidos por categoría**: {n_excluidos_cat}")
    lineas.append(f"- **Registros finales**: {n_final}\n")

    lineas.append("### Conteo por categoría excluida\n")
    lineas.append("| Categoría normalizada | Tipos originales | N registros |")
    lineas.append("|---|---|---:|")

    # Para cada categoría excluida, listar los tipos originales que la componen
    for cat in sorted(conteo_excluidos.index):
        tipos_orig = sorted(
            gdf_salud.loc[
                gdf_salud["tipo_norm"] == cat, "tipo"
            ].unique()
        )
        tipos_str = "; ".join(str(t) for t in tipos_orig)
        n = conteo_excluidos[cat]
        lineas.append(f"| {cat} | {tipos_str} | {n} |")

    lineas.append(f"| **TOTAL EXCLUIDOS** | | **{n_excluidos_cat}** |")

    lineas.append("\n### Categorías conservadas\n")
    lineas.append("| Categoría normalizada | N registros |")
    lineas.append("|---|---:|")
    for cat, n in conteo_conservados.items():
        lineas.append(f"| {cat} | {n} |")
    lineas.append(f"| **TOTAL CONSERVADOS** | **{n_final}** |")

    lineas.append("\n### Criterio de exclusión\n")
    lineas.append("Se excluyen establecimientos que **no ofrecen atención presencial general**")
    lineas.append("relevante para análisis de accesibilidad. Las categorías excluidas corresponden a:\n")
    lineas.append("- Atención remota (sin presencialidad)")
    lineas.append("- Atención dental (especializada, baja frecuencia)")
    lineas.append("- Diálisis (tratamiento crónico especializado)")
    lineas.append("- Centros de especialidad / referencia")
    lineas.append("- Salud ambiental (administrativa)")
    lineas.append("- Centros de tratamiento de adicciones (CTA)")
    lineas.append("- Salas externas de toma de muestras (SETM)")
    lineas.append("- Laboratorios clínicos")
    lineas.append("- Vacunatorios")
    lineas.append("- Centros radiológicos")
    lineas.append("- Bancos de sangre y tejidos")
    lineas.append("- Regulación médica (SAMU — administrativo)")
    lineas.append("- Unidades/policlínicos para funcionarios")
    lineas.append("- CONIN (programa específico)")
    lineas.append("- PRAIS (programa específico)")
    lineas.append("- Dirección de servicio de salud (administrativa)")
    lineas.append("- Oficinas sanitarias (administrativas)")
    lineas.append("- Unidades/clínicas móviles\n")
    lineas.append("Los registros con campo `tipo` nulo se descartan porque sin categoría")
    lineas.append("no se puede aplicar la regla de exclusión de forma confiable.\n")
    lineas.append(f"Lista configurable en el código: `CATEGORIAS_EXCLUIDAS_SALUD` en `scripts/limpieza_salud.py`.\n")

    dd_path.write_text("\n".join(lineas), encoding="utf-8")
    print(f"  Diccionario de datos → {dd_path}")
    print("\n✔ Pipeline 1.2.c completado.")


if __name__ == "__main__":
    main()
