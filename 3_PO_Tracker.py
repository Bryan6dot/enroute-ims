import streamlit as st
import pandas as pd
import io, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))



DEMO_POS = [
    {
        "id": "PO-2026-041", "brand": "Trek Bikes", "supplier": "QBP Distributor",
        "items": 4, "units": 24, "eta": "2026-04-08",
        "status": "En tránsito", "location": "Central / Warehouse",
        "created_by": "purchasing", "created_at": "2026-04-01",
        "skus": [
            {"SKU": "TRK-FX3-L", "Descripción": "Trek FX3 Disc Large",  "Ordenado": 4,  "Recibido": 4},
            {"SKU": "TRK-FX3-M", "Descripción": "Trek FX3 Disc Medium", "Ordenado": 6,  "Recibido": 6},
            {"SKU": "TRK-FX3-S", "Descripción": "Trek FX3 Disc Small",  "Ordenado": 4,  "Recibido": 0},
            {"SKU": "TRK-ACC-BL","Descripción": "Trek Accessory Bundle","Ordenado": 10, "Recibido": 0},
        ],
    },
    {
        "id": "PO-2026-039", "brand": "Shimano", "supplier": "Shimano Direct",
        "items": 2, "units": 60, "eta": "2026-04-12",
        "status": "Parcialmente recibido", "location": "Central / Warehouse",
        "created_by": "purchasing", "created_at": "2026-03-28",
        "skus": [
            {"SKU": "SHM-XT-M8",  "Descripción": "Shimano XT M8100 Derailleur", "Ordenado": 20, "Recibido": 10},
            {"SKU": "SHM-CS-M8",  "Descripción": "Shimano CS-M8100 Cassette",   "Ordenado": 40, "Recibido": 0},
        ],
    },
    {
        "id": "PO-2026-037", "brand": "Garmin", "supplier": "CDN Cycling Supply",
        "items": 3, "units": 15, "eta": "2026-04-18",
        "status": "En tránsito", "location": "Central / Warehouse",
        "created_by": "purchasing", "created_at": "2026-03-25",
        "skus": [
            {"SKU": "GAR-530",  "Descripción": "Garmin Edge 530",  "Ordenado": 5,  "Recibido": 0},
            {"SKU": "GAR-1040", "Descripción": "Garmin Edge 1040", "Ordenado": 5,  "Recibido": 0},
            {"SKU": "GAR-HRM",  "Descripción": "Garmin HRM-Dual",  "Ordenado": 5,  "Recibido": 0},
        ],
    },
    {
        "id": "PO-2026-034", "brand": "Giro Helmets", "supplier": "Sport Systems",
        "items": 2, "units": 18, "eta": "2026-04-01",
        "status": "Recibido", "location": "Central / Warehouse",
        "created_by": "purchasing", "created_at": "2026-03-20",
        "skus": [
            {"SKU": "HELM-GV-M", "Descripción": "Giro Vantage Helmet M", "Ordenado": 9, "Recibido": 9},
            {"SKU": "HELM-GV-L", "Descripción": "Giro Vantage Helmet L", "Ordenado": 9, "Recibido": 9},
        ],
    },
]

STATUS_ICON = {
    "En tránsito": "🔵",
    "Parcialmente recibido": "🟡",
    "Recibido": "🟢",
    "Con discrepancia": "🔴",
}

STAGES = ["PO creada", "Confirmada", "En tránsito", "Recepción", "Shopify ✓"]
STAGE_IDX = {"En tránsito": 2, "Parcialmente recibido": 3, "Recibido": 4}

st.title("📋 PO Tracker")
st.caption("Purchase Orders · Recepción de mercancía · Validación contra packing slip · Actualización automática en Shopify")
st.divider()

# ── Summary KPIs ──────────────────────────────────────────────────────────────
transit  = sum(1 for p in DEMO_POS if p["status"] == "En tránsito")
partial  = sum(1 for p in DEMO_POS if p["status"] == "Parcialmente recibido")
received = sum(1 for p in DEMO_POS if p["status"] == "Recibido")

k1, k2, k3, k4 = st.columns(4)
k1.metric("🔵 En tránsito",           transit,  help="POs confirmadas esperando llegada al warehouse.")
k2.metric("🟡 Parcialmente recibidas", partial,  help="POs con recepción incompleta. Quedan items pendientes.")
k3.metric("🟢 Recibidas completo",    received, help="POs totalmente recibidas y aplicadas en Shopify.")
k4.metric("📦 Total unidades en POs", sum(p["units"] for p in DEMO_POS), help="Suma de unidades en todas las POs activas.")

st.divider()

tab_list, tab_new = st.tabs(["📋 POs Activas", "➕ Nueva PO"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — LIST
# ══════════════════════════════════════════════════════════════════════════════
with tab_list:
    search = st.text_input("🔍 Buscar por marca, proveedor o # PO",
                           placeholder="Ej: Trek · Shimano · PO-2026-041")
    status_f = st.selectbox("Filtrar por estado",
                             ["Todos", "En tránsito", "Parcialmente recibido", "Recibido"])

    filtered = [
        p for p in DEMO_POS
        if (not search or search.lower() in p["brand"].lower()
                       or search.lower() in p["id"].lower()
                       or search.lower() in p["supplier"].lower())
        and (status_f == "Todos" or p["status"] == status_f)
    ]

    if not filtered:
        st.info("No se encontraron POs con ese criterio.")
    else:
        for po in filtered:
            icon = STATUS_ICON.get(po["status"], "⚪")
            with st.expander(
                f"{icon} **{po['id']}** — {po['brand']}  ·  {po['supplier']}  |  ETA: {po['eta']}  |  {po['status']}",
                expanded=(po["status"] != "Recibido"),
            ):
                # Meta row
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Proveedor",      po["supplier"])
                m2.metric("ETA",            po["eta"])
                m3.metric("Unidades",       po["units"])
                m4.metric("Status",         po["status"])

                # Timeline
                st.markdown("**Progreso de la PO**")
                current = STAGE_IDX.get(po["status"], 2)
                cols_tl = st.columns(len(STAGES))
                for i, (col, stage) in enumerate(zip(cols_tl, STAGES)):
                    with col:
                        if i < current:
                            st.markdown(f"🟢 **{stage}**")
                        elif i == current:
                            st.markdown(f"🟡 **{stage}**")
                        else:
                            st.markdown(f"⚪ {stage}")

                st.divider()

                # SKU table
                if po["skus"]:
                    df_sku = pd.DataFrame(po["skus"])
                    df_sku["Diferencia"] = df_sku["Recibido"] - df_sku["Ordenado"]
                    df_sku["Estado"] = df_sku["Diferencia"].apply(
                        lambda d: "✅ Completo" if d == 0 else ("⏳ Pendiente" if d < 0 else "⚠️ Exceso")
                    )
                    st.markdown("**Items de la PO**")
                    st.dataframe(df_sku, use_container_width=True, hide_index=True)

                    # Download PO
                    buf = io.BytesIO()
                    df_sku.to_excel(buf, index=False, engine="openpyxl")
                    st.download_button(
                        f"⬇ Descargar {po['id']}.xlsx",
                        data=buf.getvalue(),
                        file_name=f"{po['id']}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_{po['id']}",
                    )

                # Reception form — warehouse / admin only
                if st.session_state.user_role in ["warehouse", "admin"]:
                    if po["status"] in ["En tránsito", "Parcialmente recibido"]:
                        st.divider()
                        st.markdown("**📥 Registrar recepción**")
                        st.caption("Valida la mercancía recibida contra el packing slip. Shopify se actualiza al confirmar.")

                        method = st.radio(
                            "Método de validación",
                            ["✅ Checklist manual (marcar items recibidos)",
                             "📄 Subir Excel de recepción"],
                            horizontal=True,
                            key=f"method_{po['id']}",
                        )

                        if method.startswith("✅"):
                            received_items = {}
                            for item in po["skus"]:
                                if item["Recibido"] < item["Ordenado"]:
                                    checked = st.checkbox(
                                        f"**{item['SKU']}** — {item['Descripción']}  "
                                        f"(Ordenado: {item['Ordenado']}  |  "
                                        f"Pendiente: {item['Ordenado'] - item['Recibido']})",
                                        key=f"chk_{po['id']}_{item['SKU']}",
                                    )
                                    if checked:
                                        received_items[item["SKU"]] = item["Ordenado"] - item["Recibido"]
                            if received_items:
                                total_units = sum(received_items.values())
                                if st.button(
                                    f"🚀 Confirmar recepción de {len(received_items)} SKUs ({total_units} units) → Shopify",
                                    key=f"confirm_{po['id']}",
                                    type="primary",
                                ):
                                    st.success(f"✅ Recepción confirmada. {total_units} unidades actualizadas en Shopify. (Modo demo)")
                        else:
                            recv_file = st.file_uploader(
                                "Excel de recepción (mismo template universal)",
                                type=["xlsx", "xls"],
                                key=f"recv_{po['id']}",
                            )
                            if recv_file:
                                df_r = pd.read_excel(recv_file, engine="openpyxl")
                                st.dataframe(df_r, use_container_width=True, hide_index=True)
                                if st.button(
                                    "🚀 Confirmar recepción → Shopify",
                                    key=f"confirm_xl_{po['id']}",
                                    type="primary",
                                ):
                                    st.success("✅ Recepción confirmada. Shopify actualizado. (Modo demo)")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — NEW PO
# ══════════════════════════════════════════════════════════════════════════════
with tab_new:
    if st.session_state.user_role not in ["purchasing", "admin"]:
        st.warning("⚠️ Solo el equipo de compras puede crear nuevas POs.")
        st.stop()

    st.markdown("#### Crear nueva Purchase Order")
    st.caption("La PO quedará visible para el equipo de warehouse con el ETA asignado.")

    c1, c2 = st.columns(2)
    with c1:
        brand    = st.text_input("Marca / Proveedor *",  placeholder="Ej: Trek Bikes")
        supplier = st.text_input("Distribuidor",          placeholder="Ej: QBP Distributor")
        location = st.selectbox("Location destino *",
                                ["Central / Warehouse", "Store 1 · Cycling", "Store 2 · Running"])
    with c2:
        eta      = st.date_input("ETA esperado *")
        notes    = st.text_area("Notas para warehouse", height=100,
                                placeholder="Instrucciones especiales, condiciones de entrega, etc.")

    st.markdown("**Archivo de la PO**")
    st.caption("Adjunta el PDF o Excel de la orden del proveedor. Warehouse lo descargará para validar contra el packing slip.")
    po_file = st.file_uploader("Sube el archivo de la PO", type=["pdf", "xlsx", "xls"], key="new_po")

    if po_file:
        st.success(f"📎 Archivo adjunto: `{po_file.name}` — {po_file.size:,} bytes")

    st.divider()
    if st.button("📤 Publicar PO", type="primary"):
        if not brand:
            st.error("El campo Marca / Proveedor es obligatorio.")
        elif not po_file:
            st.error("Adjunta el archivo de la PO antes de publicar.")
        else:
            new_id = f"PO-2026-{len(DEMO_POS) + 42:03d}"
            st.success(f"""
            ✅ **{new_id}** publicada correctamente.

            - Marca: **{brand}**  |  Distribuidor: **{supplier or '—'}**
            - ETA: **{eta}**  |  Destino: **{location}**
            - Estado inicial: **En tránsito**
            - Warehouse ha sido notificado automáticamente.
            """)
