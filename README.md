# Prediusly - Predicción de Precios de Viviendas y Predios

**Proyecto Final - Curso de Introducción a la Ciencia de Datos (Grupo 5)**

Este repositorio contiene el proyecto "Prediusly", enfocado en la integración de datos territoriales de múltiples fuentes para analizar el mercado inmobiliario del Gran Santiago y predecir el precio del suelo mediante la incorporación de variables geoespaciales.

## Contexto y Objetivos

A partir de nuestra propuesta inicial detallada en `informe.tex` y considerando el feedback recibido en `comentarios.tex`, hemos refinado los objetivos de nuestro estudio. El proyecto evolucionó desde una integración de bases de datos espaciales hacia un análisis territorial aplicado, buscando responder preguntas medibles y concretas:
- ¿Cómo se distribuyen los predios en relación con la accesibilidad a equipamientos clave (educación, salud, transporte)?
- ¿Qué zonas muestran mayor concentración de servicios e infraestructura?
- ¿Existen brechas territoriales cuantificables que impacten la valoración económica del suelo?

## Procesamiento y Modelamiento de Datos

Para responder a estas preguntas, llevamos a cabo un flujo de trabajo que incluyó:

1. **Limpieza e Integración:** Unificamos diversas bases de datos vectoriales y tabulares (SII, INE, MINSAL, IDE Chile, Metro, etc.). Se resolvieron problemas de consistencia espacial estandarizando los sistemas de coordenadas (WGS84 / UTM Zona 19S), se trataron valores nulos, y se limpiaron datos duplicados.
2. **Ingeniería de Características Geoespaciales:** Calculamos distancias euclidianas y de red vial hacia puntos de interés (estaciones de metro, paraderos, centros de salud y educación) y generamos indicadores de densidad y concentración urbana en distintos radios de influencia.
3. **Modelamiento Matemático-Computacional:** Implementamos modelos para cuantificar el impacto y la relación entre nuestras variables de accesibilidad territorial y el valor de los predios, evaluando heterogeneidades espaciales.

## Sitio Web en GitHub Pages

Como parte del proyecto, construimos un sitio web sencillo para visualizar de manera interactiva parte de nuestro trabajo y hallazgos.
El sitio web está configurado para desplegarse utilizando **GitHub Pages** y puede visualizarse directamente desde el entorno de producción de este repositorio.

## Equipo Prediusly (Grupo 5)

- Giovanni Alexander Jimenez Andrade
- Bastián Marcelo Medina Gómez
- Cristobal Daniel Robinson Morales
- Nicole Alejandra Russo Martínez

## Estructura del Repositorio

- `informe.tex` y `comentarios.tex`: Documentos principales que definen y refinan los objetivos y la problemática del proyecto.
- `prediusly/`: Código fuente del sitio web.
- `src/` / `scripts/`: Scripts orientados a la limpieza, preparación de datos geoespaciales y modelamiento.
- `docs/`: Documentación y diccionarios de datos asociados.
- Directorios de datos (ej. `salud`, `red_vial`, `topografia`, `SII_2020`): Archivos crudos y procesados.
- `models/` y `outputs/`: Resultados, visualizaciones y modelos generados durante el análisis.
