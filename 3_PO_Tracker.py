import streamlit as st
import pandas as pd
import io, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.shopify import (
    require_auth, role_allowed, DEMO_POS, STATUS_COLORS,
    build_template_df, validate_excel, ShopifyClient
)

require_auth()

st.title("📋 PO Tracker")
st.caption("Purchase Orders · Recepción · Validación")

client = ShopifyClient()

# ── Tabs: list vs new PO ────────────────────────────────────────────────────
tab_list, tab_new = st.tabs(["📋 POs Activas", "➕ Nueva PO"])

# ═══════════════════════════════════════════════════════════════════════
# TAB 1 — PO LIST
# ═══════════════════════════════════════════════════════════════════════
with tab_list:
    search = st.text_input("🔍 Buscar por marca o # PO", placeholder="Ej: Trek · Shimano · PO-2026-041")

    filtered = [
        p for p in DEMO_POS
        if not search or
           search.lower() in p["brand"].lower() or
           search.lower() in p["id"].lower()
    ]

    if not filtered:
        st.info("No se encontraron POs con ese criterio.")
    else:
        for po in filtered:
            icon = STATUS_COLORS.get(po["status"], "⚪")
            with st.expander(
                f"{icon} **{po['id']}** — {po['brand']}  |  ETA: {po['eta']}  |  {po['status']}",
                expanded=False,
            ):
                # Meta
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Proveedor",       po["supplier"])
                m2.metric("ETA",             po["eta"])
                m3.metric("Total unidades",  po["units"])
                m4.metric("Status",          po["status"])

                # Timeline
                stages = ["PO creada", "Confirmada", "En tránsito", "Recepción", "Shopify ✓"]
                status_map = {
                    "En tránsito":           2,
                    "Parcialmente recibido": 3,
                    "Recibido":              4,
                }
                current_stage = status_map.get(po["status"], 2)
                cols_tl = st.columns(len(stages))
                for i, (col, stage) in enumerate(zip(cols_tl, stages)):
                    with col:
                        if i < current_stage:
                            st.markdown(f"🟢 **{stage}**")
                        elif i == current_stage:
                            st.markdown(f"🟡 **{stage}**")
                        else:
                            st.markdown(f"⚪ {stage}")

                st.divider()

                # Download PO button
                col_dl, col_recv = st.columns([1, 3])
                with col_dl:
                    # Build a simple PO PDF/Excel for download
                    df_po = pd.DataFrame(po.get("skus", []))
                    if not df_po.empty:
                        buf = io.BytesIO()
                        df_po.to_excel(buf, index=False, engine="openpyxl")
                        st.download_button(
                            "⬇ Descargar PO",
                            data=buf.getvalue(),
                            file_name=f"{po['id']}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                        )

                # SKU table with check / reception
                if po.get("skus"):
                    st.markdown("**Items de la PO**")
                    df_skus = pd.DataFrame(po["skus"])
                    df_skus.columns = ["SKU", "Descripción", "Ordenado", "Recibido"]
                    df_skus["Diferencia"] = df_skus["Recibido"] - df_skus["Ordenado"]
                    df_skus["Estado"] = df_skus["Diferencia"].apply(
                        lambda d: "✅ Completo" if d == 0
                        else ("⏳ Pendiente" if d < 0 else "⚠️ Exceso")
                    )
                    st.dataframe(df_skus, use_container_width=True, hide_index=True)

                # Reception form — only warehouse/admin
                if st.session_state.user_role in ["warehouse", "admin"]:
                    if po["status"] in ["En tránsito", "Parcialmente recibido"]:
                        st.markdown("---")
                        st.markdown("**📥 Registrar recepción**")
                        recv_method = st.radio(
                            "Método",
                            ["Subir Excel de recepción", "Validar manualmente (checklist)"],
                            horizontal=True,
                            key=f"method_{po['id']}",
                        )

                        if recv_method == "Subir Excel de recepción":
                            recv_file = st.file_uploader(
                                "Excel de recepción (mismo template universal)",
                                type=["xlsx", "xls"],
                                key=f"recv_{po['id']}",
                            )
                            if recv_file:
                                df_recv = pd.read_excel(recv_file, engine="openpyxl")
                                df_v, errs = validate_excel(df_recv)
                                st.dataframe(df_v, use_container_width=True, hide_index=True)
                                valid = df_v["Estado"].str.startswith("✅").sum()
                                if valid > 0:
                                    if st.button(
                                        f"✅ Confirmar recepción → Shopify ({valid} items)",
                                        key=f"confirm_{po['id']}",
                                        type="primary",
                                    ):
                                        st.success(f"Recepción confirmada. Shopify actualizado (modo demo).")
                        else:
                            if po.get("skus"):
                                st.markdown("Marca los items recibidos:")
                                received = {}
                                for item in po["skus"]:
                                    checked = st.checkbox(
                                        f"{item['sku']} — {item['desc']} (Ordenado: {item['ordered']})",
                                        key=f"chk_{po['id']}_{item['sku']}",
                                    )
                                    if checked:
                                        received[item["sku"]] = item["ordered"]

                                if received:
                                    if st.button(
                                        f"✅ Confirmar {len(received)} items → Shopify",
                                        key=f"confirm_chk_{po['id']}",
                                        type="primary",
                                    ):
                                        st.success(f"Recepción confirmada. {len(received)} SKUs actualizados en Shopify (modo demo).")

# ═══════════════════════════════════════════════════════════════════════
# TAB 2 — NEW PO (purchasing / admin only)
# ═══════════════════════════════════════════════════════════════════════
with tab_new:
    if st.session_state.user_role not in ["purchasing", "admin"]:
        st.warning("Solo el equipo de compras puede crear nuevas POs.")
        st.stop()

    st.subheader("Crear nueva Purchase Order")

    c1, c2 = st.columns(2)
    with c1:
        po_brand    = st.text_input("Marca / Proveedor *", placeholder="Ej: Trek Bikes")
        po_supplier = st.text_input("Distribuidor",        placeholder="Ej: QBP Distributor")
        po_location = st.selectbox(
            "Location destino *",
            ["Central / Warehouse", "Store 1 · Cycling", "Store 2 · Running"],
        )
    with c2:
        po_eta   = st.date_input("ETA esperado *")
        po_notes = st.text_area("Notas / instrucciones", height=100)

    st.markdown("**Archivo de la PO**")
    po_file = st.file_uploader(
        "Sube el PDF o Excel de la PO del proveedor",
        type=["pdf", "xlsx", "xls"],
        key="new_po_file",
    )

    if po_file:
        st.success(f"Archivo cargado: `{po_file.name}` ({po_file.size:,} bytes)")

    st.divider()

    if st.button("📤 Publicar PO", type="primary", use_container_width=False):
        if not po_brand:
            st.error("El campo Marca / Proveedor es obligatorio.")
        elif not po_file:
            st.error("Adjunta el archivo de la PO.")
        else:
            new_id = f"PO-2026-{len(DEMO_POS)+42:03d}"
            st.success(f"""
            ✅ PO **{new_id}** publicada correctamente.
            - Marca: **{po_brand}**
            - ETA: **{po_eta}**
            - Destino: **{po_location}**
            - Warehouse ha sido notificado.
            """)
