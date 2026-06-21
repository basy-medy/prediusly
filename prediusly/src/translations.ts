export const glossary: Record<string, { label: string; unit: string }> = {
  superficie_m2: { label: "Tamaño del terreno", unit: "m²" },
  log_superficie: { label: "Tamaño del terreno (log)", unit: "" },
  dist_edu_escolar_m: { label: "Distancia al colegio más cercano", unit: "m" },
  count_edu_escolar_1km: { label: "Cantidad de colegios cerca (en 1 km)", unit: "" },
  dist_edu_parvularia_m: { label: "Distancia al jardín infantil más cercano", unit: "m" },
  count_edu_parvularia_1km: { label: "Cantidad de jardines infantiles cerca (en 1 km)", unit: "" },
  dist_edu_superior_m: { label: "Distancia a la universidad/instituto más cercano", unit: "m" },
  count_edu_superior_1km: { label: "Cantidad de universidades/institutos cerca (en 1 km)", unit: "" },
  dist_salud_m: { label: "Distancia al centro de salud más cercano", unit: "m" },
  count_salud_1km: { label: "Cantidad de centros de salud cerca (en 1 km)", unit: "" },
  dist_metro_m: { label: "Distancia a la estación de Metro más cercana", unit: "m" },
  count_metro_1km: { label: "Cantidad de estaciones de Metro cerca (en 1 km)", unit: "" },
  dist_micro_m: { label: "Distancia al paradero de micro más cercano", unit: "m" },
  count_micro_500m: { label: "Cantidad de paraderos de micro muy cerca (500 m)", unit: "" },
  count_micro_1km: { label: "Cantidad de paraderos de micro cerca (1 km)", unit: "" },
  dist_aeropuerto_m: { label: "Distancia al aeropuerto/aeródromo más cercano", unit: "m" },
  dist_red_vial_m: { label: "Distancia a una vía principal clasificada", unit: "m" },
  elevacion_m: { label: "Altura sobre el nivel del mar del sector", unit: "m" },
  pendiente_pct: { label: "Inclinación del terreno", unit: "%" },
  centroid_x: { label: "Ubicación del predio dentro de la ciudad (E-W)", unit: "" },
  centroid_y: { label: "Ubicación del predio dentro de la ciudad (N-S)", unit: "" },
  nombre_comuna_enc: { label: "La comuna donde está el predio", unit: "" },
  uso_suelo_ipt_enc: { label: "El tipo de zona urbana donde está el predio", unit: "" },
  uso_suelo_ipt: { label: "El tipo de zona urbana donde está el predio", unit: "" },
};

export function translateVariable(variable: string) {
  return glossary[variable] || { label: variable, unit: "" };
}
