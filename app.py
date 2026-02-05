# app.py
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
Import os
# ---------------------------
# CONFIG
# ---------------------------
st.set_page_config(page_title="Dashboard Presupuesto", layout="wide")

RUTA = os.path.join(os.getcwd(), "BD Presupuesto Final.xlsx")

# ---------------------------
# HELPERS
# ---------------------------
def to_datetime_safe(s):
    # Convierte fechas; si falla, deja NaT
    return pd.to_datetime(s, errors="coerce", dayfirst=True)

def normalize_text(s):
    if pd.isna(s):
        return s
    return str(s).strip()

def month_start(dt):
    # Fecha al primer día del mes
    return pd.to_datetime(dt).dt.to_period("M").dt.to_timestamp()

def fmt_mil(x):
    # Formato tipo "115.05 mil"
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "0"
    x = float(x)
    if abs(x) >= 1_000_000:
        return f"{x/1_000_000:,.2f} M".replace(",", "X").replace(".", ",").replace("X", ".")
    if abs(x) >= 1_000:
        return f"{x/1_000:,.2f} mil".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_data
def extract(ruta):
    # EXTRACTION
    xls = pd.ExcelFile(ruta)

    df_costo = pd.read_excel(xls, sheet_name="Fact_Costo")
    df_ing = pd.read_excel(xls, sheet_name="Fact_Ingresos")
    df_gas = pd.read_excel(xls, sheet_name="Fact_Gastos")
    df_ppt = pd.read_excel(xls, sheet_name="Fact_Presupuesto")

    return df_costo, df_ing, df_gas, df_ppt

def transform(df_costo, df_ing, df_gas, df_ppt):
    # ---------------------------
    # TRANSFORM: COSTO
    # ---------------------------
    df_costo = df_costo.copy()
    df_costo.columns = [c.strip() for c in df_costo.columns]
    df_costo["Fecha Ingreso"] = to_datetime_safe(df_costo["Fecha Ingreso"])
    df_costo["Producto"] = df_costo["Producto"].apply(normalize_text)
    df_costo["Cantidades"] = pd.to_numeric(df_costo["Cantidades"], errors="coerce")
    df_costo["Costo Unit"] = pd.to_numeric(df_costo["Costo Unit"], errors="coerce")
    df_costo["Total_Costo"] = df_costo["Cantidades"] * df_costo["Costo Unit"]
    df_costo["Mes"] = month_start(df_costo["Fecha Ingreso"])

    # ---------------------------
    # TRANSFORM: INGRESOS
    # ---------------------------
    df_ing = df_ing.copy()
    df_ing.columns = [c.strip() for c in df_ing.columns]
    df_ing["Fecha Venta"] = to_datetime_safe(df_ing["Fecha Venta"])
    df_ing["Producto"] = df_ing["Producto"].apply(normalize_text)
    df_ing["Cantidades"] = pd.to_numeric(df_ing["Cantidades"], errors="coerce")
    df_ing["Venta Unit"] = pd.to_numeric(df_ing["Venta Unit"], errors="coerce")
    df_ing["Total_Ingreso"] = df_ing["Cantidades"] * df_ing["Venta Unit"]
    df_ing["Mes"] = month_start(df_ing["Fecha Venta"])

    # ---------------------------
    # TRANSFORM: GASTOS
    # ---------------------------
    df_gas = df_gas.copy()
    df_gas.columns = [c.strip() for c in df_gas.columns]
    df_gas["Fecha Gasto"] = to_datetime_safe(df_gas["Fecha Gasto"])
    df_gas["Gasto"] = df_gas["Gasto"].apply(normalize_text)
    df_gas["Total"] = pd.to_numeric(df_gas["Total"], errors="coerce")
    df_gas["Mes"] = month_start(df_gas["Fecha Gasto"])

    # ---------------------------
    # TRANSFORM: PRESUPUESTO
    # ---------------------------
    df_ppt = df_ppt.copy()
    df_ppt.columns = [c.strip() for c in df_ppt.columns]
    df_ppt["Fecha Presupuesto"] = to_datetime_safe(df_ppt["Fecha Presupuesto"])
    df_ppt["PPT_Costos"] = pd.to_numeric(df_ppt["PPT_Costos"], errors="coerce")
    df_ppt["PPT_Ingresos"] = pd.to_numeric(df_ppt["PPT_Ingresos"], errors="coerce")
    df_ppt["PPT_Gastos"] = pd.to_numeric(df_ppt["PPT_Gastos"], errors="coerce")
    df_ppt["Mes"] = month_start(df_ppt["Fecha Presupuesto"])

    # ---------------------------
    # LOAD (TABLAS AGREGADAS)
    # ---------------------------
    costo_mes = df_costo.groupby("Mes", as_index=False)["Total_Costo"].sum()
    ingreso_mes = df_ing.groupby("Mes", as_index=False)["Total_Ingreso"].sum()
    gasto_mes = df_gas.groupby("Mes", as_index=False)["Total"].sum().rename(columns={"Total": "Total_Gasto"})
    ppt_mes = df_ppt.groupby("Mes", as_index=False)[["PPT_Costos","PPT_Ingresos","PPT_Gastos"]].sum()

    # Merge mensual
    mensual = (pd.DataFrame({"Mes": pd.date_range(
                    start=min(costo_mes["Mes"].min(), ingreso_mes["Mes"].min(), gasto_mes["Mes"].min(), ppt_mes["Mes"].min()),
                    end=max(costo_mes["Mes"].max(), ingreso_mes["Mes"].max(), gasto_mes["Mes"].max(), ppt_mes["Mes"].max()),
                    freq="MS"
                )})
               .merge(ingreso_mes, on="Mes", how="left")
               .merge(costo_mes, on="Mes", how="left")
               .merge(gasto_mes, on="Mes", how="left")
               .merge(ppt_mes, on="Mes", how="left")
              )

    # Fill NaN
    for col in ["Total_Ingreso","Total_Costo","Total_Gasto","PPT_Costos","PPT_Ingresos","PPT_Gastos"]:
        if col in mensual.columns:
            mensual[col] = mensual[col].fillna(0)

    mensual["Utilidad"] = mensual["Total_Ingreso"] - mensual["Total_Costo"] - mensual["Total_Gasto"]
    mensual["PPT_Utilidad"] = mensual["PPT_Ingresos"] - mensual["PPT_Costos"] - mensual["PPT_Gastos"]

    return df_costo, df_ing, df_gas, df_ppt, mensual

def kpi_vs_ppt(real, ppt):
    if ppt == 0:
        return None
    return (real - ppt) / ppt

# ---------------------------
# APP
# ---------------------------
st.title("📊 Dashboard: Ingresos, Costos, Gastos y Presupuesto (ETL)")

try:
    df_costo_raw, df_ing_raw, df_gas_raw, df_ppt_raw = extract(RUTA)
except FileNotFoundError:
    st.error(f"No encontré el archivo en la ruta:\n{RUTA}\n\nVerifica la ruta o el nombre del archivo.")
    st.stop()
except ValueError as e:
    st.error(f"Error leyendo hojas. Revisa que existan estas hojas: Fact_Costo, Fact_Ingresos, Fact_Gastos, Fact_Presupuesto.\n\nDetalle: {e}")
    st.stop()

df_costo, df_ing, df_gas, df_ppt, mensual = transform(df_costo_raw, df_ing_raw, df_gas_raw, df_ppt_raw)

# ---------------------------
# FILTROS
# ---------------------------
st.sidebar.header("🎛️ Filtros")

# Filtro por rango de meses
meses = mensual["Mes"].sort_values().unique()
if len(meses) == 0:
    st.warning("No hay datos para mostrar.")
    st.stop()

mes_min = meses[0]
mes_max = meses[-1]

rango = st.sidebar.slider(
    "Rango de meses",
    min_value=pd.to_datetime(mes_min).to_pydatetime(),
    max_value=pd.to_datetime(mes_max).to_pydatetime(),
    value=(pd.to_datetime(mes_min).to_pydatetime(), pd.to_datetime(mes_max).to_pydatetime()),
)

mes_ini = pd.to_datetime(rango[0]).to_period("M").to_timestamp()
mes_fin = pd.to_datetime(rango[1]).to_period("M").to_timestamp()

mensual_f = mensual[(mensual["Mes"] >= mes_ini) & (mensual["Mes"] <= mes_fin)].copy()

# Filtro por producto (afecta ingresos y costos + tabla)
productos = sorted(set(df_ing["Producto"].dropna().unique()).union(set(df_costo["Producto"].dropna().unique())))
producto_sel = st.sidebar.multiselect("Producto (opcional)", options=productos, default=[])

if producto_sel:
    ing_f = df_ing[df_ing["Producto"].isin(producto_sel)].copy()
    costo_f = df_costo[df_costo["Producto"].isin(producto_sel)].copy()
else:
    ing_f = df_ing.copy()
    costo_f = df_costo.copy()

# recalcular mensual con filtro producto
ing_mes_f = ing_f.groupby("Mes", as_index=False)["Total_Ingreso"].sum()
costo_mes_f = costo_f.groupby("Mes", as_index=False)["Total_Costo"].sum()
mensual_pf = (mensual[["Mes","Total_Gasto","PPT_Costos","PPT_Ingresos","PPT_Gastos"]]
              .merge(ing_mes_f, on="Mes", how="left")
              .merge(costo_mes_f, on="Mes", how="left"))
mensual_pf["Total_Ingreso"] = mensual_pf["Total_Ingreso"].fillna(0)
mensual_pf["Total_Costo"] = mensual_pf["Total_Costo"].fillna(0)
mensual_pf["Utilidad"] = mensual_pf["Total_Ingreso"] - mensual_pf["Total_Costo"] - mensual_pf["Total_Gasto"]
mensual_pf["PPT_Utilidad"] = mensual_pf["PPT_Ingresos"] - mensual_pf["PPT_Costos"] - mensual_pf["PPT_Gastos"]
mensual_pf = mensual_pf[(mensual_pf["Mes"] >= mes_ini) & (mensual_pf["Mes"] <= mes_fin)].copy()

# ---------------------------
# KPIs (tarjetas)
# ---------------------------
total_ingreso = mensual_pf["Total_Ingreso"].sum()
total_costo = mensual_pf["Total_Costo"].sum()
total_gasto = mensual_pf["Total_Gasto"].sum()
total_utilidad = total_ingreso - total_costo - total_gasto

ppt_ingreso = mensual_pf["PPT_Ingresos"].sum()
ppt_costo = mensual_pf["PPT_Costos"].sum()
ppt_gasto = mensual_pf["PPT_Gastos"].sum()
ppt_utilidad = ppt_ingreso - ppt_costo - ppt_gasto

delta_util = kpi_vs_ppt(total_utilidad, ppt_utilidad)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Ingreso", fmt_mil(total_ingreso))
c2.metric("Costo", fmt_mil(total_costo))
c3.metric("Gasto", fmt_mil(total_gasto))
c4.metric("Utilidad", fmt_mil(total_utilidad))

# KPI vs Presupuesto (como el cuadro verde de tu imagen)
st.markdown("### 🎯 Utilidad vs Presupuesto")
col_a, col_b = st.columns([1, 2])
with col_a:
    if delta_util is None:
        st.info(f"Presupuesto utilidad = 0 (no se puede calcular %).")
        st.write(f"**Utilidad:** {fmt_mil(total_utilidad)}")
        st.write(f"**Objetivo:** {fmt_mil(ppt_utilidad)}")
    else:
        st.success(
            f"**{fmt_mil(total_utilidad)}**\n\n"
            f"Objetivo: **{fmt_mil(ppt_utilidad)}**  "
            f"({(delta_util*100):.2f}%)"
        )

# ---------------------------
# GRÁFICOS PRINCIPALES
# ---------------------------
g1, g2 = st.columns([1, 2])

with g1:
    st.markdown("### 🥧 Costo, Gasto e Ingreso (total)")
    pie_df = pd.DataFrame({
        "Tipo": ["Ingreso", "Costo", "Gasto"],
        "Monto": [total_ingreso, total_costo, total_gasto]
    })
    fig_pie = px.pie(pie_df, names="Tipo", values="Monto", hole=0.45)
    st.plotly_chart(fig_pie, use_container_width=True)

with g2:
    st.markdown("### 📈 Costo e Ingreso por Año y Mes")
    line_df = mensual_pf[["Mes","Total_Costo","Total_Ingreso"]].copy()
    line_df = line_df.melt(id_vars="Mes", var_name="Tipo", value_name="Monto")
    line_df["Tipo"] = line_df["Tipo"].replace({"Total_Costo":"Costo", "Total_Ingreso":"Ingreso"})
    fig_line = px.line(line_df, x="Mes", y="Monto", color="Tipo", markers=True)
    st.plotly_chart(fig_line, use_container_width=True)

st.markdown("### 📉 Utilidad por Año y Mes")
util_df = mensual_pf[["Mes","Utilidad"]].copy()
fig_util = px.area(util_df, x="Mes", y="Utilidad")
st.plotly_chart(fig_util, use_container_width=True)

# ---------------------------
# TABLA POR PRODUCTO (como la de tu imagen)
# ---------------------------
st.markdown("### 🧾 Tabla por Producto (Ingreso, Costo y Utilidad)")

ing_prod = ing_f.groupby("Producto", as_index=False)["Total_Ingreso"].sum()
costo_prod = costo_f.groupby("Producto", as_index=False)["Total_Costo"].sum()

tabla_prod = ing_prod.merge(costo_prod, on="Producto", how="outer").fillna(0)
tabla_prod["Utilidad"] = tabla_prod["Total_Ingreso"] - tabla_prod["Total_Costo"]
tabla_prod = tabla_prod.sort_values("Total_Ingreso", ascending=False)

# Formato
tabla_show = tabla_prod.copy()
tabla_show.rename(columns={
    "Total_Ingreso":"Ingreso",
    "Total_Costo":"Costo"
}, inplace=True)

st.dataframe(tabla_show, use_container_width=True)

# ---------------------------
# DATA QUALITY (opcional pero útil)
# ---------------------------
with st.expander("🔎 Verificación rápida de calidad de datos (ETL)"):
    st.write("**Filas leídas:**")
    st.write({
        "Fact_Costo": int(len(df_costo_raw)),
        "Fact_Ingresos": int(len(df_ing_raw)),
        "Fact_Gastos": int(len(df_gas_raw)),
        "Fact_Presupuesto": int(len(df_ppt_raw)),
    })

    st.write("**Nulos por hoja (post-transform):**")
    st.write({
        "Costo - Fecha NaT": int(df_costo["Fecha Ingreso"].isna().sum()),
        "Ingresos - Fecha NaT": int(df_ing["Fecha Venta"].isna().sum()),
        "Gastos - Fecha NaT": int(df_gas["Fecha Gasto"].isna().sum()),
        "PPT - Fecha NaT": int(df_ppt["Fecha Presupuesto"].isna().sum()),
    })

st.caption("Hecho en Python (ETL + Dashboard) con pandas + streamlit + plotly.")




