import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

st.set_page_config(page_title="Dashboard · Enroute IMS", layout="wide")

if not st.session_state.get("user_role"):
    st.warning("⚠️ Inicia sesión desde la página principal.")
    st.stop()

INVENTORY = {
    "TRK-FX3-L":  {"desc": "Trek FX3 Disc Large",        "Central": 12, "Store1": 2, "Store2": 0},
    "TRK-FX3-M":  {"desc": "Trek FX3 Disc Medium",       "Central": 8,  "Store1": 3, "Store2": 1},
    "TRK-FX3-S":  {"desc": "Trek FX3 Disc Small",        "Central": 5,  "Store1": 1, "Store2": 0},
    "SHM-XT-M8":  {"desc": "Shimano XT M8100 Derailleur","Central": 2,  "Store1": 0, "Store2": 1},
    "ASS-GEL-P":  {"desc": "Gel Saddle Pro",              "Central": 8,  "Store1": 3, "Store2": 2},
    "HELM-GV-M":  {"desc": "Giro Vantage Helmet M",       "Central": 0,  "Store1": 4, "Store2": 1},
    "HELM-GV-L":  {"desc": "Giro Vantage Helmet L",       "Central": 3,  "Store1": 1, "Store2": 0},
    "RUN-NK-9":   {"desc": "Nike Pegasus 9",              "Central": 15, "Store1": 0, "Store2": 6},
    "RUN-BK-GT":  {"desc": "Brooks Ghost 16",             "Central": 10, "Store1": 0, "Store2": 4},
    "ACC-PUMP-F": {"desc": "Topeak Floor Pump",           "Central": 6,  "Store1": 2, "Store2": 1},
}

MOVEMENTS = [
    {"Fecha": "2026-04-05", "Referencia": "PO-2026-041", "Tipo": "entrada",  "Location": "Central",    "Units": "+18", "Usuario": "warehouse"},
    {"Fecha": "2026-04-04", "Referencia": "TRF-021",     "Tipo": "traslado", "Location": "Central→S1", "Units": "±6",  "Usuario": "store1"},
    {"Fecha": "2026-04-03", "Referencia": "ADJ-019",     "Tipo": "salida",   "Location": "Store 2",    "Units": "-3",  "Usuario": "store2"},
    {"Fecha": "2026-04-02", "Referencia": "PO-2026-038", "Tipo": "entrada",  "Location": "Central",    "Units": "+42", "Usuario": "warehouse"},
    {"Fecha": "2026-04-01", "Referencia": "TRF-020",     "Tipo": "traslado", "Location": "Central→S2", "Units": "±4",  "Usuario": "store2"},
]

all_units = sum(v["Central"] + v["Store1"] + v["Store2"] for v in INVENTORY.values())
central_u = sum(v["Central"] for v in INVENTORY.values())
store1_u  = sum(v["Store1"]  for v in INVENTORY.values())
store2_u  = sum(v["Store2"]  for v in INVENTORY.values())
low_stock = sum(1 for v in INVENTORY.values() if v["Central"] + v["Store1"] + v["Store2"] < 5)

st.title("📊 Dashboard")
st.caption(f"Sesión: **{st.session_state.user_name}** · Última sincronización: hoy 10:42 AM · Shopify live")
st.divider()

st.markdown("#### Indicadores clave de inventario")
st.caption("Datos en tiempo real desde Shopify. Se actualizan con cada movimiento registrado.")

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("📦 Total unidades", f"{all_units:,}", "+142 esta semana",
              help="Suma de todas las unidades en las 3 locations.")
with k2:
    st.metric("🔴 SKUs bajo stock", str(low_stock), "+2 vs semana pasada", delta_color="inverse",
              help="SKUs con menos de 5 unidades en total. Genera alerta automática.")
with k3:
    st.metric("🚚 POs en tránsito", "4", "ETA más próximo: Apr 8",
              help="Purchase Orders confirmadas pendientes de recibir.")
with k4:
    st.metric("✅ Precisión inventario", "98.2%", "+0.4% vs baseline",
              help="Coincidencia entre conteo físico y registros en Shopify.")

st.divider()
st.markdown("#### Distribución de stock por location")
st.caption("Shopify gestiona cada ubicación de forma independiente.")

c1, c2, c3 = st.columns(3)
with c1:
    pct = central_u / all_units * 100
    st.markdown("**🏭 Central / Warehouse**")
    st.markdown(f"### {central_u} units")
    st.progress(pct / 100, text=f"{pct:.1f}% del stock total")
    st.caption("Recibe todas las POs y gestiona envíos.")
with c2:
    pct = store1_u / all_units * 100
    st.markdown("**🚲 Store 1 · Cycling**")
    st.markdown(f"### {store1_u} units")
    st.progress(pct / 100, text=f"{pct:.1f}% del stock total")
    st.caption("Tienda de ciclismo. Inventario de piso.")
with c3:
    pct = store2_u / all_units * 100
    st.markdown("**🏃 Store 2 · Running**")
    st.markdown(f"### {store2_u} units")
    st.progress(pct / 100, text=f"{pct:.1f}% del stock total")
    st.caption("Tienda de running. Inventario de piso.")

st.divider()
left, right = st.columns(2)

with left:
    st.markdown("#### ⚠️ Alertas activas")
    st.caption("El sistema detecta automáticamente situaciones que requieren atención.")
    for sku, data in INVENTORY.items():
        total = data["Central"] + data["Store1"] + data["Store2"]
        if total < 5:
            st.error(f"**{sku}** — {data['desc']}  |  {total} units · Reorder urgente")
    st.info("📦 **Trek Bikes PO-2026-041** — ETA Apr 8 · 24 units en camino")
    st.warning("🔄 **Traslado TRF-021** pendiente de confirmar — Central → Store1 · 6 units")

with right:
    st.markdown("#### 📋 Movimientos recientes")
    st.caption("Cada entrada, salida o traslado queda registrado con usuario y referencia.")
    st.dataframe(pd.DataFrame(MOVEMENTS), use_container_width=True, hide_index=True)

st.divider()
st.markdown("#### 📦 Existencias completas — todas las locations")
st.caption("Vista consolidada desde Shopify. Cada fila es un SKU activo.")

rows = []
for sku, data in INVENTORY.items():
    total = data["Central"] + data["Store1"] + data["Store2"]
    rows.append({
        "SKU": sku, "Descripción": data["desc"],
        "Central 🏭": data["Central"], "Store1 🚲": data["Store1"], "Store2 🏃": data["Store2"],
        "Total": total,
        "Estado": "🔴 Bajo" if total < 5 else ("🟡 Watch" if total < 10 else "🟢 OK"),
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
