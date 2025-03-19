#!/usr/bin/env python
# coding: utf-8

# # ETL version 2

# In[18]:


import os
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
from dateutil.relativedelta import relativedelta
import boto3
import json


# In[19]:


# 📌 Cargar variables de entorno
load_dotenv()

# 📌 Obtener los tokens desde .env
BANXICO_TOKEN = os.getenv("BANXICO_TOKEN")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

if not BANXICO_TOKEN:
    raise ValueError("❌ Error: BANXICO_TOKEN no encontrado en .env")

print("✅ Token de Banxico cargado correctamente.")

# 📌 Configurar fechas desde 2020 hasta hoy
initial_date = "2015-01-01"
final_date = datetime.today().strftime("%Y-%m-%d")

# 📌 Configurar cliente de Amazon S3
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)


# ## Extract 

# In[20]:


def extract_banxico_data(serie_id, initial_date, final_date):
    """
    Extrae datos de la API de Banxico y los devuelve en un DataFrame.
    """
    url = f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{serie_id}/datos/{initial_date}/{final_date}?token={BANXICO_TOKEN}"
    response = requests.get(url)

    if response.status_code != 200:
        print(f"❌ Error {response.status_code}: {response.text}")
        return None

    data = response.json()
    
    if "bmx" not in data or "series" not in data["bmx"] or not data["bmx"]["series"]:
        print("⚠️ No se encontraron datos en la respuesta de Banxico.")
        return None

    series_data = data["bmx"]["series"][0]["datos"]

    if not series_data:
        print("⚠️ No hay datos disponibles en este rango de fechas.")
        return None

    # 📌 Convertir datos a DataFrame
    df = pd.DataFrame(series_data)
    df.columns = ["timestamp", "value"]

    # 📌 Convertir fechas correctamente
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%d/%m/%Y", dayfirst=True)

    # 📌 Convertir valores a numérico
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    return df


# In[21]:


# 📌 Extraer Tipo de Cambio
df_tipo_cambio = extract_banxico_data("SF43718", initial_date, final_date)
df_tipo_cambio.to_csv("tipo_de_cambio.csv", index=False)

# 📌 Extraer Tasa de Interés
df_tasa_interes = extract_banxico_data("SF282", initial_date, final_date)
df_tasa_interes.to_csv("tasa_de_interes.csv", index=False)

# 📌 Extraer INPC desde Banxico
df_inpc = extract_banxico_data("SP1", initial_date, final_date)
df_inpc.to_csv("inpc.csv", index=False)

print("✅ Datos guardados localmente en CSV.")


# ---

# ## Transform

# In[22]:


print(df_inpc.head())
print(df_tasa_interes.head())
print(df_tipo_cambio.head())


# In[23]:


print(df_inpc.dtypes)
print(df_tasa_interes.dtypes)
print(df_tipo_cambio.dtypes)


# In[24]:


# 📌 Renombrar columnas para coherencia
df_tipo_cambio.rename(columns={"timestamp": "date", "value": "tipo_de_cambio"}, inplace=True)
df_tasa_interes.rename(columns={"timestamp": "date", "value": "tasa_de_interes"}, inplace=True)
df_inpc.rename(columns={"timestamp": "date", "value": "inpc"}, inplace=True)


# In[25]:


# 📌 Crear la columna con el INPC rezagado 12 meses
df_inpc["inpc_lag_12"] = df_inpc["inpc"].shift(12)

# 📌 Calcular la inflación anualizada en porcentaje
df_inpc["inflacion"] = 100 * (df_inpc["inpc"] / df_inpc["inpc_lag_12"] - 1)

# 📌 Eliminar filas con valores NaN (primeros 12 meses no tienen inpc_lag_12)
df_inpc = df_inpc.dropna()

print("✅ Inflación anualizada calculada correctamente")


# In[26]:


# 📌 Convertir las fechas a formato datetime estándar
df_tipo_cambio["date"] = pd.to_datetime(df_tipo_cambio["date"], format="%Y-%m-%d")
df_tasa_interes["date"] = pd.to_datetime(df_tasa_interes["date"], format="%Y-%m-%d")
df_inpc["date"] = pd.to_datetime(df_inpc["date"], format="%Y-%m-%d")

print("✅ Fechas convertidas correctamente")

# 📌 Convertir las fechas a solo "AAAA-MM" (a nivel mensual)
df_tipo_cambio["date"] = df_tipo_cambio["date"].dt.to_period("M")
df_tasa_interes["date"] = df_tasa_interes["date"].dt.to_period("M")
df_inpc["date"] = df_inpc["date"].dt.to_period("M")

print("✅ Fechas convertidas a nivel mensual")


# In[27]:


# 📌 Para el tipo de cambio, tomamos el promedio mensual
df_tipo_cambio = df_tipo_cambio.groupby("date").agg({"tipo_de_cambio": "mean"}).reset_index()

print("✅ Tipo de cambio agregado a nivel mensual")


# In[28]:


df_inpc


# In[29]:


df_tasa_interes


# In[30]:


df_tipo_cambio


# In[31]:


# 📌 Convertir 'date' de Period[M] a datetime64 antes de exportar
df_inpc["date"] = df_inpc["date"].astype("datetime64[ns]")
df_tasa_interes["date"] = df_tasa_interes["date"].astype("datetime64[ns]")
df_tipo_cambio["date"] = df_tipo_cambio["date"].astype("datetime64[ns]")

# 📌 Convertir 'date' a string en formato YYYY-MM-DD (Athena requiere este formato en CSV)
df_inpc["date"] = df_inpc["date"].dt.strftime('%Y-%m-%d')
df_tasa_interes["date"] = df_tasa_interes["date"].dt.strftime('%Y-%m-%d')
df_tipo_cambio["date"] = df_tipo_cambio["date"].dt.strftime('%Y-%m-%d')

# 📌 Verificar cambios (date debe ser de tipo object/string)
print(df_inpc.dtypes)         
print(df_tasa_interes.dtypes)
print(df_tipo_cambio.dtypes)

# 📌 Guardar en CSV sin índice para evitar problemas con Glue/Athena
# 📌 Eliminar la columna 'inpc_lag_12' antes de guardar en CSV
df_inpc = df_inpc[["date", "inpc", "inflacion"]]
df_inpc.to_csv("inpc.csv", index=False)
df_tasa_interes.to_csv("tasa_de_interes.csv", index=False)
df_tipo_cambio.to_csv("tipo_de_cambio.csv", index=False)

print("✅ Archivos CSV guardados con éxito en formato correcto.")


# In[32]:


df_inpc


# In[ ]:


print(df_inpc.dtypes) 


# ---

# ## Load 

# In[33]:


# 📌 Subir a S3
s3_client = boto3.client("s3")

# Probar conexión
response = s3_client.list_buckets()
for bucket in response["Buckets"]:
    print(f"✅ Bucket encontrado: {bucket['Name']}")
# 📌 Probar conexión
try:
    response = s3_client.list_objects_v2(Bucket="banxico-hw", Prefix="raw/")
    for obj in response.get("Contents", []):
        print(f"📂 Archivo en S3: {obj['Key']} - Tamaño: {obj['Size']} bytes")
except Exception as e:
    print(f"❌ Error al conectar con S3: {e}")


# In[34]:


def upload_to_s3(file_name, bucket, folder):
    """
    Sube un archivo local a Amazon S3 en la carpeta especificada.
    """
    object_name = f"{folder}/{file_name}"
    try:
        s3_client.upload_file(file_name, bucket, object_name)
        print(f"✅ Archivo {file_name} subido a S3 en {object_name}")
    except Exception as e:
        print(f"❌ Error al subir {file_name}: {e}")

# 📌 Subir los archivos a S3
upload_to_s3("tipo_de_cambio.csv", "banxico-hw", "tipo_de_cambio")
upload_to_s3("tasa_de_interes.csv", "banxico-hw", "tasa_de_interes")
upload_to_s3("inpc.csv", "banxico-hw", "inflacion")

print("✅ Todos los archivos han sido subidos a S3 en la carpeta 'raw/'.")

