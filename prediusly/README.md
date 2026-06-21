# Prediusly

Prediusly es una aplicación web que visualiza los resultados de un modelo de predicción de avalúo fiscal de predios habitacionales en la Región Metropolitana de Chile.

## Arquitectura y Decisiones Técnicas

- **Backend:** Se utilizó **Bun.serve** nativo. Es la forma más rápida y ligera de levantar un servidor HTTP para proveer los archivos JSON estáticos, sin añadir dependencias extras (como Hono o Express) para una tarea tan directa.
- **Frontend:** Se utilizó **Vite + React**. Vite ofrece un entorno de desarrollo extremadamente rápido con HMR (Hot Module Replacement). React es ideal para manejar el estado complejo del mapa interactivo (React Leaflet) y las distintas vistas de la aplicación.
- **Estilos:** Se utilizó **Vanilla CSS** con variables personalizadas y un diseño premium basado en *Glassmorphism*, modo oscuro y fuentes modernas (Inter y Outfit), priorizando la calidad visual y la experiencia de usuario.

## Instalación y Ejecución

1. Instalar las dependencias usando Bun:
   ```bash
   bun install
   ```

2. Iniciar los servidores de desarrollo (Frontend y Backend correrán concurrentemente):
   ```bash
   bun run dev
   ```

3. Abre `http://localhost:5173` en tu navegador.

## ⚠️ Nota sobre los Datos Completos

Por defecto, la aplicación incluye una muestra liviana (`predictions.geojson`) en la carpeta `data/` para propósitos de prueba rápida.

Para ver el análisis con el dataset real de 24,097 predios:
1. Copia el archivo original completo `predictions.geojson` (que pesa ~35 MB).
2. Pégalo dentro de la carpeta `data/` de este proyecto, reemplazando la muestra existente.
3. El frontend y backend cargarán automáticamente el archivo nuevo.
