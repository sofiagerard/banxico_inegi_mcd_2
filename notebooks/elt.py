#!/usr/bin/env python
# coding: utf-8

# ## ELT 

# In[22]:


import os
import requests
import pandas as pd
from dotenv import load_dotenv
import boto3
import json
import time
from io import StringIO
import streamlit as st
import statsmodels.api as sm
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score



# In[2]:


# Configurar cliente de Athena y S3
athena_client = boto3.client("athena")
s3_client = boto3.client("s3")


# In[3]:


# Base de datos en Glue
DATABASE = "econ"
S3_BUCKET = "itam-analytics-sofia"
QUERY_RESULTS = f"{S3_BUCKET}/query-results/"


# In[4]:


create_db_query = f"CREATE DATABASE IF NOT EXISTS {DATABASE};"

athena_client.start_query_execution(
    QueryString=create_db_query,
    ResultConfiguration={"OutputLocation": f"s3://{QUERY_RESULTS}"}
)
print("✅ Base de datos creada en Glue: econ")


# In[5]:


queries = [
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS {DATABASE}.tipo_de_cambio (
        date STRING,
        tipo_de_cambio DOUBLE
    )
    ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
    WITH SERDEPROPERTIES ("skip.header.line.count" = "1")
    STORED AS TEXTFILE
    LOCATION 's3://{S3_BUCKET}/raw/tipo_de_cambio/';
    """,
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS {DATABASE}.tasa_de_interes (
        date STRING,
        tasa_de_interes DOUBLE
    )
    ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
    WITH SERDEPROPERTIES ("skip.header.line.count" = "1")
    STORED AS TEXTFILE
    LOCATION 's3://{S3_BUCKET}/raw/tasa_de_interes/';
    """,
    f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS {DATABASE}.inflacion (
        date STRING,
        inpc DOUBLE,
        inflacion DOUBLE
    )
    ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
    WITH SERDEPROPERTIES ("skip.header.line.count" = "1")
    STORED AS TEXTFILE
    LOCATION 's3://{S3_BUCKET}/raw/inflacion/';
    """
]


# In[6]:


def ejecutar_query(query):
    response = athena_client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": DATABASE},
        ResultConfiguration={"OutputLocation": f"s3://{QUERY_RESULTS}"}
    )
    return response

# Crear tablas en Athena
for query in queries:
    print("Ejecutando query...")
    response = ejecutar_query(query)
    query_id = response['QueryExecutionId']
    print(f"Query Execution ID: {query_id}")
    time.sleep(5)  # Pausa para evitar conflictos

print("✅ Tablas creadas en Athena.")


# In[7]:


create_economy_table = f"""
CREATE TABLE IF NOT EXISTS {DATABASE}.economy AS
SELECT 
    t.date,
    t.tasa_de_interes,
    i.inflacion,
    c.tipo_de_cambio
FROM {DATABASE}.tasa_de_interes t
JOIN {DATABASE}.inflacion i ON t.date = i.date
JOIN {DATABASE}.tipo_de_cambio c ON t.date = c.date;
"""

economy_response = ejecutar_query(create_economy_table)
print(f"Query Execution ID para economy: {economy_response['QueryExecutionId']}")
print("✅ Tabla economy creada en Athena.")


# In[8]:


def descargar_datos():
    query = f"SELECT * FROM {DATABASE}.economy"
    response = ejecutar_query(query)
    query_id = response['QueryExecutionId']
    print(f"Descargando resultados de Query ID: {query_id}")
    
    # Esperar a que la consulta termine
    time.sleep(10)
    
    # Descargar el archivo desde S3
    result_file = f"query-results/{query_id}.csv"
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=result_file)
    file_content = response["Body"].read().decode("utf-8")
    
    # Leer el contenido en un DataFrame
    df = pd.read_csv(StringIO(file_content))
    return df

# Descargar y mostrar los datos
df_economy = descargar_datos()
print(df_economy.head())


# In[23]:


df_economy.to_csv("economy.csv", index=False)


# In[ ]:


df_economy


# ---

# ## Regressions and Streamlit 

# In[25]:


# Cargar datos
@st.cache_data
def load_data():
    df = pd.read_csv("economy.csv")  
    return df

df = load_data()

# Función para hacer regresión lineal con sklearn
def linear_regression_sklearn(x, y, df):
    X = df[x].values.reshape(-1,1)  # Convertir a matriz 2D
    Y = df[y].values.reshape(-1, 1)  # Convertir a matriz 2D
    model = LinearRegression()
    model.fit(X, Y)
    y_pred = model.predict(X)
    
    r2 = r2_score(Y, y_pred) 
    
    return model, y_pred, r2

# Definir pares de variables
regressions = {
    "tipo_de_cambio ~ tasa_de_interes": ("tasa_de_interes", "tipo_de_cambio"),
    "tasa_de_interes ~ inflacion": ("inflacion", "tasa_de_interes"),
    "tipo_de_cambio ~ inflacion": ("inflacion", "tipo_de_cambio")
}

# Crear layout en Streamlit
st.title("Regresiones Lineales con Scikit-Learn")

for title, (x, y) in regressions.items():
    st.subheader(title)
    
    # Obtener modelo, predicciones y R^2
    model, y_pred, r2 = linear_regression_sklearn(x, y, df)
    
    # Mostrar coeficientes
    st.write(f"Coeficiente: {model.coef_[0][0]:.4f}")
    st.write(f"Intercepto: {model.intercept_[0]:.4f}")
    st.write(f"R² Score: {r2:.4f}")
    
    # Graficar scatter plot con la línea de regresión
    fig, ax = plt.subplots()
    sns.scatterplot(x=df[x], y=df[y], ax=ax, alpha=0.5, label="Datos Reales")
    ax.plot(df[x], y_pred, color="red", label="Regresión Lineal")
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.set_title(title)
    ax.legend()
    st.pyplot(fig)

