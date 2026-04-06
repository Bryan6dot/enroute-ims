import streamlit as st
import pandas as pd
import io, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.shopify import (
    require_auth, build_template_df, validate_excel,
    TEMPLATE_COLUMNS, DEMO_INVENTORY, DEMO_MOVEMENTS, ShopifyClient
)

require_auth()

st.title("📦 Inventory Control")
st.caption("Entradas · Salidas · Traslados · Ajustes")

client = ShopifyClient()

# ── Download template ────────────────────────────────────────────────────────
with st.expander("📥 Descargar template Excel", expanded=False):
    df_tpl = build_template_df()
    buf = io.BytesIO()
    df_tpl.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        "⬇ Descargar template.xlsx",
        data=buf.getvalue(),
        file_name="enroute_inventory_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.dataframe(df_tpl, use_container_width=True, hide_index=True)
    st.caption("Tipos válidos: `entrada` · `salida` · `traslado` · `recepcion`")

st.divider()

# ── Upload & validate ────────────────────────────────────────────────────────
st.subheader("↑ Subir Excel de movimientos")

uploaded = st.file_uploader(
    "Selecciona el archivo Excel (formato template)",
    type=["xlsx", "xls"],
    key="inv_upload",
)

if uploaded:
    try:
        df_raw = pd.read_excel(uploaded, engine="openpyxl")
        df_validated, errors = validate_excel(df_raw)

        valid_count   = df_validated["Estado"].str.startswith("✅").sum()
        warning_count = df_validated["Estado"].str.startswith("⚠").sum()
        error_count   = df_validated["Estado"].str.startswith("❌").sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("✅ Válidos",         valid_count)
        c2.metric("⚠️ Con advertencia", warning_count)
        c3.metric("❌ Con error",        error_count)

        st.markdown("**Previsualización — revisión antes de aplicar**")
        st.dataframe(df_validated, use_container_width=True, hide_index=True)

        if errors:
            with st.expander("Ver detalle de errores"):
                for e in errors:
                    st.error(e)

        apply_count = valid_count + warning_count
        if apply_count > 0:
            col_btn, col_note = st.columns([1, 3])
            with col_btn:
                if st.button(
                    f"🚀 Aplicar {apply_count} filas válidas → Shopify",
                    type="primary",
                    use_container_width=True,
                ):
                    with st.spinner("Enviando a Shopify..."):
                        applied = 0
                        for _, row in df_validated.iterrows():
                            if not row["Estado"].startswith("❌"):
                                # In production: call client.adjust_inventory(...)
                                # Demo: just count
                                applied += 1
                        st.success(f"✅ {applied} movimientos aplicados en Shopify (modo demo).")
            with col_note:
                if client.demo:
                    st.info("ℹ️ Modo demo activo. Configura las credenciales de Shopify en `.streamlit/secrets.toml` para escribir datos reales.")

    except Exception as e:
        st.error(f"Error leyendo el archivo: {e}")

st.divider()

# ── Live inventory table ─────────────────────────────────────────────────────
st.subheader("📊 Existencias actuales — Shopify live")

search = st.text_input("🔍 Filtrar por SKU", placeholder="Ej: TRK-FX3")

rows = []
for sku, locs in DEMO_INVENTORY.items():
    if search and search.upper() not in sku.upper():
        continue
    row = {"SKU": sku}
    row.update(locs)
    row["Total"] = sum(locs.values())
    row["Estado"] = (
        "🔴 Bajo"  if row["Total"] < 5  else
        "🟡 Watch" if row["Total"] < 10 else
        "🟢 OK"
    )
    rows.append(row)

if rows:
    df_inv = pd.DataFrame(rows)
    st.dataframe(df_inv, use_container_width=True, hide_index=True)
else:
    st.info("No se encontraron SKUs con ese filtro.")

st.divider()

# ── Movement history ─────────────────────────────────────────────────────────
st.subheader("📋 Historial de movimientos")
df_mov = pd.DataFrame(DEMO_MOVEMENTS)
df_mov.columns = ["Fecha", "Referencia", "Tipo", "Location", "Units", "Usuario"]
st.dataframe(df_mov, use_container_width=True, hide_index=True)
