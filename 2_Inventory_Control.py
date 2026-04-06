import streamlit as st
import pandas as pd
import io, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))



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
]

VALID_SKUS = set(INVENTORY.keys())
VALID_TIPOS = ["entrada", "salida", "traslado", "recepcion"]
VALID_LOCS  = ["Central / Warehouse", "Store 1 · Cycling", "Store 2 · Running"]

st.title("📦 Inventory Control")
st.caption("Entradas · Salidas · Traslados · Ajustes — todos los movimientos se aplican directamente en Shopify")
st.divider()

# ── Template download ─────────────────────────────────────────────────────────
with st.expander("📥 Descargar template Excel", expanded=False):
    st.caption("Usa este template para registrar cualquier tipo de movimiento. Un solo formato para todas las locations.")
    tpl = pd.DataFrame([
        ["TRK-FX3-L", "Trek FX3 Disc Large",  2, "entrada",  "Central / Warehouse",  "PO-2026-041"],
        ["SHM-XT-M8", "Shimano XT M8100",      4, "traslado", "Central / Warehouse",  "TRF-021"],
        ["ASS-GEL-P", "Gel Saddle Pro",         3, "salida",   "Store 2 · Running",    ""],
    ], columns=["SKU", "Descripcion", "Cantidad", "Tipo", "Location", "Referencia"])
    st.dataframe(tpl, use_container_width=True, hide_index=True)
    buf = io.BytesIO()
    tpl.to_excel(buf, index=False, engine="openpyxl")
    st.download_button("⬇ Descargar template.xlsx", data=buf.getvalue(),
                       file_name="enroute_template.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption("**Tipos válidos:** `entrada` · `salida` · `traslado` · `recepcion`")

st.divider()

# ── Upload section ─────────────────────────────────────────────────────────────
st.markdown("#### ↑ Subir Excel de movimientos")
st.caption("La app valida cada fila antes de enviar a Shopify. Los errores se muestran en la previsualización.")

uploaded = st.file_uploader("Selecciona el archivo Excel", type=["xlsx", "xls"])

if uploaded:
    try:
        df = pd.read_excel(uploaded, engine="openpyxl")
        statuses = []
        for _, row in df.iterrows():
            issues = []
            if str(row.get("SKU","")) not in VALID_SKUS:
                issues.append("SKU no existe en Shopify")
            if str(row.get("Tipo","")).lower() not in VALID_TIPOS:
                issues.append("Tipo inválido")
            if str(row.get("Location","")) not in VALID_LOCS:
                issues.append("Location inválida")
            try:
                if int(row.get("Cantidad", 0)) <= 0:
                    issues.append("Cantidad debe ser > 0")
            except Exception:
                issues.append("Cantidad no numérica")
            statuses.append("❌ " + " · ".join(issues) if issues else "✅ Válido")
        df["Estado"] = statuses
        valid = sum(1 for s in statuses if s.startswith("✅"))
        errors = sum(1 for s in statuses if s.startswith("❌"))

        c1, c2, c3 = st.columns(3)
        c1.metric("✅ Filas válidas", valid)
        c2.metric("❌ Con error", errors, delta_color="inverse")
        c3.metric("📤 Listas para Shopify", valid)

        st.markdown("**Previsualización — revisión antes de aplicar**")
        st.dataframe(df, use_container_width=True, hide_index=True)

        if valid > 0:
            if st.button(f"🚀 Aplicar {valid} movimientos → Shopify", type="primary"):
                st.success(f"✅ {valid} movimientos aplicados en Shopify correctamente. (Modo demo)")
                st.info("ℹ️ En producción: cada fila llama a `POST /inventory_levels/adjust.json` en Shopify API.")
    except Exception as e:
        st.error(f"Error leyendo el archivo: {e}")
else:
    st.info("💡 Sube un Excel con el template para ver la previsualización y validación automática.")

st.divider()

# ── Live inventory table ──────────────────────────────────────────────────────
st.markdown("#### 📊 Existencias actuales por location")
st.caption("Datos leídos directamente desde Shopify Inventory API. Se refrescan en cada carga de página.")

col_search, col_filter = st.columns([2, 1])
with col_search:
    search = st.text_input("🔍 Filtrar por SKU o descripción", placeholder="Ej: Trek · Shimano · RUN")
with col_filter:
    estado_filter = st.selectbox("Estado", ["Todos", "🔴 Bajo", "🟡 Watch", "🟢 OK"])

rows = []
for sku, data in INVENTORY.items():
    total = data["Central"] + data["Store1"] + data["Store2"]
    estado = "🔴 Bajo" if total < 5 else ("🟡 Watch" if total < 10 else "🟢 OK")
    if search and search.upper() not in sku.upper() and search.lower() not in data["desc"].lower():
        continue
    if estado_filter != "Todos" and estado != estado_filter:
        continue
    rows.append({
        "SKU": sku, "Descripción": data["desc"],
        "Central 🏭": data["Central"], "Store1 🚲": data["Store1"], "Store2 🏃": data["Store2"],
        "Total": total, "Estado": estado,
    })

if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"Mostrando {len(rows)} de {len(INVENTORY)} SKUs activos")
else:
    st.info("No se encontraron SKUs con ese filtro.")

st.divider()

# ── Movement history ──────────────────────────────────────────────────────────
st.markdown("#### 📋 Historial de movimientos")
st.caption("Cada movimiento queda registrado con referencia, tipo, usuario y timestamp. Trazabilidad completa.")
st.dataframe(pd.DataFrame(MOVEMENTS), use_container_width=True, hide_index=True)
