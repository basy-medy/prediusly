import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import numpy as np
import requests
import time
import os
import re


archivo_csv = "datos_yapo_crudos.csv"

def iniciar_navegador():
    opciones = uc.ChromeOptions()
    return uc.Chrome(options=opciones, version_main=149)

def guardar_progreso(df_nuevo):
    if os.path.exists(archivo_csv):
        df_nuevo.to_csv(archivo_csv, mode='a', header=False, index=False, encoding='utf-8')
    else:
        df_nuevo.to_csv(archivo_csv, mode='w', header=True, index=False, encoding='utf-8')

print("Iniciando navegador indetectable...")
driver = iniciar_navegador()

url_base_yapo = "https://www.yapo.cl/searchresult/bienes-raices-venta-de-propiedades?regionslug=region-metropolitana&q=withcat.bienes-raices-venta-de-propiedades-apartamentos,bienes-raices-venta-de-propiedades-casas,bienes-raices-venta-de-propiedades-comercios,bienes-raices-venta-de-propiedades-oficinas,bienes-raices-venta-de-propiedades-fincas"

publicaciones_base = []
limite_paginas = 1

try:

    print("\n[FASE 1] Recolectando datos base y URLs...")
    for numero_pagina in range(1, limite_paginas + 1):
        print(f"Escaneando página {numero_pagina}...")
        
        if numero_pagina == 1:
            driver.get(f"{url_base_yapo}")
        else:
            driver.get(f"{url_base_yapo}.{numero_pagina}")
        time.sleep(4)
        
        xpath_tarjetas = "//*[@id='currentlistings']/div[2]/div"
        
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpath_tarjetas)))
            tarjetas = driver.find_elements(By.XPATH, xpath_tarjetas)
            
            if len(tarjetas) == 0: break

            for tarjeta in tarjetas:
                pub = {}
                try:
                    xpath_enlace = ".//div[2]/a"
                    pub["URL"] = tarjeta.find_element(By.XPATH, xpath_enlace).get_attribute("href")
                except:
                    continue
                try:
                    precio_texto = tarjeta.find_element(By.XPATH, ".//div[2]/a/div[4]").text
                    pub["Precio"] = precio_texto.replace('$', '').replace('.', '').replace('UF', '').strip()
                except: pub["Precio"] = "No especificado"

                try:
                    ubicacion = tarjeta.find_element(By.XPATH, ".//div[2]/a/div[2]/span").text
                    pub["Comuna"] = ubicacion.split(',')[0].strip()
                except: pub["Comuna"] = "No especificado"

                try:
                    m2_texto = tarjeta.find_element(By.XPATH, ".//div[2]/a/div[5]/ul/li[1]").text
                    pub["Metros Cuadrados"] = m2_texto.replace('m²', '').strip()
                except: pub["Metros Cuadrados"] = "No especificado"

                if pub["Precio"] != "No especificado":
                    publicaciones_base.append(pub)
                    
        except Exception as e:
            print("Fin de las tarjetas o error en la página.")
            break

    print(f"\n¡Fase 1 completada! {len(publicaciones_base)} propiedades encontradas.")
    print("\n[FASE 2] Entrando a cada publicación para extraer Latitud y Longitud...")
    
    datos_lote = []
    casas_por_sesion = 30
    
    for i, propiedad in enumerate(publicaciones_base):
        print(f"Geocodificando {i+1}/{len(publicaciones_base)}...")
        
        driver.get(propiedad["URL"])
        time.sleep(2) 
        try:
            iframe_mapa = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src, 'maps')]"))
            )
            driver.switch_to.frame(iframe_mapa)
            html_mapa = driver.page_source
            patron = r'\[(-\d+\.\d+),\s*(-\d+\.\d+)\]'
            coordenadas = re.search(patron, html_mapa)
            
            if coordenadas:
                propiedad["Latitud"] = coordenadas.group(1)
                propiedad["Longitud"] = coordenadas.group(2)
            else:
                propiedad["Latitud"] = "Sin mapa"
                propiedad["Longitud"] = "Sin mapa"
                
        except:
            propiedad["Latitud"] = "Sin mapa"
            propiedad["Longitud"] = "Sin mapa"
            
        finally:
            try: driver.switch_to.default_content()
            except: pass
        datos_lote.append(propiedad)

        if len(datos_lote) >= 10 or i == len(publicaciones_base) - 1:
            guardar_progreso(pd.DataFrame(datos_lote))
            datos_lote = [] 
        if (i + 1) % casas_por_sesion == 0 and i != len(publicaciones_base) - 1:
            print("\n[!] Refrescando sesión para evitar bloqueos...")
            driver.quit()
            time.sleep(20)
            driver = iniciar_navegador()

finally:
    print("\nCerrando navegador...")
    try:
        if 'driver' in locals():
            driver.quit()
            time.sleep(1)
            del driver
    except: pass

print("\nCargando datos crudos para limpieza final")
if os.path.exists(archivo_csv):
    df = pd.read_csv(archivo_csv)
    
    cantidad_original = len(df)
    print(f"Registros antes de la limpieza: {cantidad_original}")
    if 'URL' in df.columns:
        df = df.drop_duplicates(subset=['URL'], keep='last')
    else:
        df = df.drop_duplicates(keep='last')
        
    df = df.reset_index(drop=True)
    print(f"Se eliminaron {cantidad_original - len(df)} propiedades repetidas.")
    df['Precio'] = df['Precio'].astype(str).str.extract(r'([\d\.,]+)')
    df['Precio'] = df['Precio'].str.replace(',', '.').astype(float)
    
    df['Metros Cuadrados'] = df['Metros Cuadrados'].astype(str).str.extract(r'([\d\.,]+)')
    df.rename(columns={'Metros Cuadrados': 'Metros Cuadrados (m²)'}, inplace=True)

    try:
        data = requests.get('https://mindicador.cl/api/uf').json()
        uf_hoy = data['serie'][0]['valor']
    except:
        uf_hoy = 39000.00
    df['Precio_CLP'] = np.where(df['Precio'] < 200000, df['Precio'] * uf_hoy, df['Precio']).round(0)
    df['Precio_UF'] = np.where(df['Precio'] >= 200000, df['Precio'] / uf_hoy, df['Precio']).round(2)

    df = df[(df['Latitud'] != 'Sin mapa') & (df['Latitud'].notna())]

    df.to_csv("datos_yapo_sin_duplicados.csv", index=False, encoding='utf-8')
    df.to_excel("dataset_prediusly_final.xlsx", index=False)
    
    print("¡Base de datos geoespacial completada y guardada en Excel y CSV!")
else:
    print("No se generaron datos.")