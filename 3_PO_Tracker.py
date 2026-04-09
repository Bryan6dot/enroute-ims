import streamlit as st
import pandas as pd
import uuid
from datetime import date, datetime
from shopify_mock import shopify_preview

st.set_page_config(page_title="PO Tracker · Enroute IMS", layout="wide")

if not st.session_state.get("user_role"):
    st.warning("⚠️ Inicia sesión desde la página principal.")
    st.stop()

with st.sidebar:
    st.markdown("### 🚲 Enroute IMS")
    st.caption(f"**{st.session_state.user_name}** · {st.session_state.user_role}")
    st.divider()
    st.caption("🧪 Modo prueba — Shopify en preview")
    st.divider()
    if st.button("Sign Out", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

LOCATIONS = ["Central / Warehouse", "Store 1 · Cycling", "Store 2 · Running"]
LOC_KEY   = {"Central / Warehouse": "Central", "Store 1 · Cycling": "Store1", "Store 2 · Running": "Store2"}

st.title("📋 PO Tracker")
st.caption("Gestión de órdenes de compra — Crear · Seguimiento · Recepción")
st.divider()

tab_create, tab_transit, tab_receive = st.tabs(["➕ Crear PO", "🔵 En tránsito", "📥 Recibir mercancía"])

# ── TAB 1: CREAR PO ──────────────────────────────────────────────────────────
with tab_create:
    st.markdown("#### Nueva Orden de Compra")
    st.caption("Completa los datos del pedido. El inventario se actualiza cuando se confirme la recepción.")

    col_a, col_b = st.columns(2)
    with col_a:
        supplier  = st.text_input("Proveedor *", placeholder="Ej. Trek Bikes México")
        reference = st.text_input("# Referencia proveedor", placeholder="Ej. INV-2025-8841")
    with col_b:
        eta      = st.date_input("ETA (fecha estimada de llegada) *", min_value=date.today())
        dest_loc = st.selectbox("Location de destino *", LOCATIONS)

    st.markdown("#### Artículos del pedido")
    if "po_items" not in st.session_state:
        st.session_state.po_items = [{"SKU": "", "Descripción": "", "Qty Ordenada": 1}]

    edited = st.data_editor(
        pd.DataFrame(st.session_state.po_items),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "SKU":          st.column_config.TextColumn("SKU *"),
            "Descripción":  st.column_config.TextColumn("Descripción *"),
            "Qty Ordenada": st.column_config.NumberColumn("Qty Ordenada *", min_value=1, step=1),
        },
        hide_index=True,
    )
    st.session_state.po_items = edited.to_dict("records")

    st.divider()
    if st.button("✅ Registrar PO", type="primary"):
        valid_items = [r for r in st.session_state.po_items if r.get("SKU") and r.get("Descripción")]
        if not supplier:
            st.error("El campo Proveedor es obligatorio.")
        elif not valid_items:
            st.error("Agrega al menos un artículo con SKU y Descripción.")
        else:
            po_id = f"PO-{date.today().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
            po = {
                "id":          po_id,
                "supplier":    supplier,
                "reference":   reference,
                "eta":         str(eta),
                "destination": dest_loc,
                "status":      "En tránsito",
                "created_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
                "total_units": sum(r.get("Qty Ordenada", 0) for r in valid_items),
                "skus": [
                    {"SKU": r["SKU"].strip().upper(), "Descripción": r["Descripción"],
                     "Qty Ordenada": r.get("Qty Ordenada", 0), "Qty Recibida": 0}
                    for r in valid_items
                ],
            }
            st.session_state.pos.append(po)
            st.session_state.po_items = [{"SKU": "", "Descripción": "", "Qty Ordenada": 1}]
            st.success(f"✅ **{po_id}** registrado. Visible en 'En tránsito'.")
            st.rerun()

# ── TAB 2: EN TRÁNSITO ───────────────────────────────────────────────────────
with tab_transit:
    st.markdown("#### Órdenes en tránsito")
    pos = st.session_state.get("pos", [])

    if not pos:
        st.info("No hay POs registrados. Crea uno en la pestaña 'Crear PO'.")
    else:
        STATUS_ICON = {"En tránsito": "🔵", "Parcial": "🟡", "Recibido": "🟢", "Discrepancia": "🔴"}
        for po in pos:
            icon = STATUS_ICON.get(po["status"], "⚪")
            with st.expander(f"{icon} **{po['id']}** — {po['supplier']} · ETA: {po['eta']} · {po['total_units']} uds. · {po['status']}"):
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Proveedor", po["supplier"])
                c2.metric("ETA",       po["eta"])
                c3.metric("Destino",   po["destination"])
                c4.metric("Estado",    po["status"])
                if po.get("reference"):
                    st.caption(f"Ref. proveedor: {po['reference']}")
                st.dataframe(pd.DataFrame(po["skus"]), use_container_width=True, hide_index=True)

# ── TAB 3: RECIBIR MERCANCÍA ─────────────────────────────────────────────────
with tab_receive:
    st.markdown("#### Recepción de mercancía")
    pos_open = [p for p in st.session_state.get("pos", []) if p["status"] in ("En tránsito", "Parcial")]

    if not pos_open:
        st.info("No hay POs pendientes de recepción.")
    else:
        selected_id = st.selectbox("Selecciona el PO a recibir", [p["id"] for p in pos_open])
        po = next(p for p in pos_open if p["id"] == selected_id)

        st.markdown(f"**Proveedor:** {po['supplier']}  |  **ETA:** {po['eta']}  |  **Destino:** {po['destination']}")
        st.divider()

        has_slip = st.radio(
            "¿El paquete llegó con packing slip?",
            ["✅ Sí, tengo packing slip", "❌ No, sin packing slip"],
            horizontal=True,
        )

        if "❌" in has_slip:
            st.warning("Sin packing slip. Exporta la lista de artículos esperados para revisar el paquete.")
            csv = pd.DataFrame([
                {"SKU": s["SKU"], "Descripción": s["Descripción"],
                 "Qty Esperada": s["Qty Ordenada"], "Qty Recibida": ""}
                for s in po["skus"]
            ]).to_csv(index=False).encode("utf-8")
            st.download_button("📥 Exportar CSV para revisión", data=csv,
                               file_name=f"{po['id']}_revision.csv", mime="text/csv")
            st.info("Después de revisar el paquete con el CSV, selecciona '✅ Sí' para continuar.")
        else:
            st.markdown("#### Captura las cantidades recibidas")
            received_inputs = {}
            for s in po["skus"]:
                sku = s["SKU"]
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1: st.text(f"{sku} — {s['Descripción']}")
                with c2: st.caption(f"Ordenado: {s['Qty Ordenada']}")
                with c3:
                    received_inputs[sku] = st.number_input(
                        "Recibido", min_value=0,
                        max_value=int(s["Qty Ordenada"]) * 2,
                        value=int(s.get("Qty Recibida", 0)),
                        key=f"recv_{po['id']}_{sku}",
                    )

            st.divider()
            st.text_area("Notas de recepción (opcional)", key="recv_notes")

            if st.button("📡 Confirmar recepción → Shopify", type="primary"):
                adjustments = []
                new_status  = "Recibido"
                loc_key     = LOC_KEY.get(po["destination"], "Central")

                for s in po["skus"]:
                    sku     = s["SKU"]
                    qty_ord = int(s["Qty Ordenada"])
                    qty_rec = int(received_inputs.get(sku, 0))

                    if sku not in st.session_state.inventory:
                        st.session_state.inventory[sku] = {"desc": s["Descripción"], "Central": 0, "Store1": 0, "Store2": 0}
                    st.session_state.inventory[sku][loc_key] += qty_rec
                    st.session_state.inventory[sku]["desc"]   = s["Descripción"]

                    adjustments.append({"sku": sku, "qty": qty_rec})

                    if qty_rec < qty_ord:
                        new_status = "Parcial" if new_status == "Recibido" else new_status
                    elif qty_rec > qty_ord:
                        new_status = "Discrepancia"

                for p in st.session_state.pos:
                    if p["id"] == po["id"]:
                        p["status"] = new_status
                        for s in p["skus"]:
                            s["Qty Recibida"] = received_inputs.get(s["SKU"], 0)

                st.success(f"✅ Recepción registrada. Estado PO: **{new_status}**")
                st.markdown("---")
                st.markdown(f"### 📡 Llamadas al API de Shopify ({len(adjustments)} total)")

                for adj in adjustments:
                    shopify_preview(
                        endpoint="/admin/api/2026-01/inventory_levels/adjust.json",
                        method="POST",
                        payload={
                            "inventory_level": {
                                "inventory_item_id":    f"← GET /variants.json?sku={adj['sku']}",
                                "location_id":          f"← GET /locations.json → {po['destination']}",
                                "available_adjustment": adj["qty"],
                                "reason":               "received",
                            }
                        },
                        description=f"Suma **+{adj['qty']} uds.** de `{adj['sku']}` en {po['destination']}",
                    )
