import streamlit as st
import pandas as pd
import uuid
from datetime import date, datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.shopify_mock import shopify_preview

st.set_page_config(page_title="PO Tracker · Enroute IMS", layout="wide")

if not st.session_state.get("user_role"):
    st.warning("⚠️ Inicia sesión desde la página principal.")
    st.stop()

with st.sidebar:
    st.markdown("### 🚲 Enroute IMS")
    st.caption(f"**{st.session_state.user_name}** · {st.session_state.user_role}")
    st.divider()
    st.caption("Modo: **🧪 Pruebas** — Shopify en preview")
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

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — CREAR PO
# ══════════════════════════════════════════════════════════════════════════════
with tab_create:
    st.markdown("#### Nueva Orden de Compra")
    st.caption("Completa los datos del pedido. Los artículos entrarán al inventario cuando se confirme la recepción.")

    col_a, col_b = st.columns(2)
    with col_a:
        supplier  = st.text_input("Proveedor *", placeholder="Ej. Trek Bikes México")
        reference = st.text_input("# Referencia proveedor", placeholder="Ej. INV-2025-8841")
    with col_b:
        eta       = st.date_input("ETA (fecha estimada de llegada) *", min_value=date.today())
        dest_loc  = st.selectbox("Location de destino *", LOCATIONS)

    st.markdown("#### Artículos del pedido")
    st.caption("Agrega cada artículo con su SKU, descripción y cantidad ordenada.")

    if "po_items" not in st.session_state:
        st.session_state.po_items = [{"SKU": "", "Descripción": "", "Qty Ordenada": 1}]

    items_df = pd.DataFrame(st.session_state.po_items)
    edited = st.data_editor(
        items_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "SKU":          st.column_config.TextColumn("SKU *", help="Código único del artículo"),
            "Descripción":  st.column_config.TextColumn("Descripción *"),
            "Qty Ordenada": st.column_config.NumberColumn("Qty Ordenada *", min_value=1, step=1),
        },
        hide_index=True,
    )
    st.session_state.po_items = edited.to_dict("records")

    st.divider()
    if st.button("✅ Registrar PO", type="primary", use_container_width=False):
        valid_items = [r for r in st.session_state.po_items if r.get("SKU") and r.get("Descripción")]
        if not supplier:
            st.error("El campo Proveedor es obligatorio.")
        elif not valid_items:
            st.error("Agrega al menos un artículo con SKU y Descripción.")
        else:
            po_id = f"PO-{date.today().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
            total = sum(r.get("Qty Ordenada", 0) for r in valid_items)
            po = {
                "id":          po_id,
                "supplier":    supplier,
                "reference":   reference,
                "eta":         str(eta),
                "destination": dest_loc,
                "status":      "En tránsito",
                "created_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
                "total_units": total,
                "skus": [
                    {
                        "SKU":          r["SKU"].strip().upper(),
                        "Descripción":  r["Descripción"],
                        "Qty Ordenada": r.get("Qty Ordenada", 0),
                        "Qty Recibida": 0,
                    }
                    for r in valid_items
                ],
            }
            st.session_state.pos.append(po)
            st.session_state.po_items = [{"SKU": "", "Descripción": "", "Qty Ordenada": 1}]
            st.success(f"✅ PO **{po_id}** registrado correctamente. Visible en la pestaña 'En tránsito'.")
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — EN TRÁNSITO
# ══════════════════════════════════════════════════════════════════════════════
with tab_transit:
    st.markdown("#### Órdenes en tránsito")
    pos = st.session_state.get("pos", [])

    if not pos:
        st.info("No hay POs registrados. Crea uno en la pestaña 'Crear PO'.")
    else:
        STATUS_COLOR = {
            "En tránsito": "🔵",
            "Parcial":     "🟡",
            "Recibido":    "🟢",
            "Discrepancia":"🔴",
        }
        for po in pos:
            icon = STATUS_COLOR.get(po["status"], "⚪")
            with st.expander(f"{icon} **{po['id']}** — {po['supplier']} · ETA: {po['eta']} · {po['total_units']} uds. · {po['status']}"):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Proveedor", po["supplier"])
                col2.metric("ETA",       po["eta"])
                col3.metric("Destino",   po["destination"])
                col4.metric("Estado",    po["status"])
                if po.get("reference"):
                    st.caption(f"Ref. proveedor: {po['reference']}")
                st.dataframe(
                    pd.DataFrame(po["skus"]),
                    use_container_width=True,
                    hide_index=True,
                )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — RECIBIR MERCANCÍA
# ══════════════════════════════════════════════════════════════════════════════
with tab_receive:
    st.markdown("#### Recepción de mercancía")

    pos_open = [p for p in st.session_state.get("pos", []) if p["status"] in ("En tránsito", "Parcial")]

    if not pos_open:
        st.info("No hay POs pendientes de recepción. Todos los POs activos están recibidos o aún no se han creado.")
    else:
        po_ids = [p["id"] for p in pos_open]
        selected_id = st.selectbox("Selecciona el PO a recibir", po_ids)
        po = next(p for p in pos_open if p["id"] == selected_id)

        st.markdown(f"**Proveedor:** {po['supplier']}  |  **ETA:** {po['eta']}  |  **Destino:** {po['destination']}")
        st.divider()

        # Packing slip option
        has_slip = st.radio(
            "¿El paquete llegó con packing slip?",
            ["✅ Sí, tengo packing slip", "❌ No, sin packing slip"],
            horizontal=True,
        )

        if "❌" in has_slip:
            st.warning("Sin packing slip. Exporta la lista de artículos esperados para revisar el paquete.")
            expected_df = pd.DataFrame([
                {"SKU": s["SKU"], "Descripción": s["Descripción"], "Qty Esperada": s["Qty Ordenada"], "Qty Recibida": ""}
                for s in po["skus"]
            ])
            csv = expected_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Exportar CSV para revisión",
                data=csv,
                file_name=f"{po['id']}_revision.csv",
                mime="text/csv",
            )
            st.info("Después de revisar el paquete con el CSV, selecciona 'Sí, tengo packing slip' para continuar con la recepción.")
        else:
            st.markdown("#### Captura las cantidades recibidas")
            st.caption("Ingresa las unidades físicamente contadas. Si hay discrepancia, el sistema la registrará.")

            received_inputs = {}
            for sku_data in po["skus"]:
                sku = sku_data["SKU"]
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.text(f"{sku} — {sku_data['Descripción']}")
                with col2:
                    st.text(f"Ordenado: {sku_data['Qty Ordenada']}")
                with col3:
                    received_inputs[sku] = st.number_input(
                        "Recibido",
                        min_value=0,
                        max_value=int(sku_data["Qty Ordenada"]) * 2,
                        value=int(sku_data.get("Qty Recibida", 0)),
                        key=f"recv_{po['id']}_{sku}",
                    )

            st.divider()
            notes = st.text_area("Notas de recepción (opcional)", placeholder="Ej. Caja dañada en SKU X, faltante justificado, etc.")

            if st.button("📡 Confirmar recepción y enviar a Shopify", type="primary"):
                adjustments = []
                new_status  = "Recibido"
                loc_key     = LOC_KEY.get(po["destination"], "Central")

                for sku_data in po["skus"]:
                    sku = sku_data["SKU"]
                    qty_ord = int(sku_data["Qty Ordenada"])
                    qty_rec = int(received_inputs.get(sku, 0))
                    diff    = qty_rec - qty_ord

                    # Update session inventory
                    if sku not in st.session_state.inventory:
                        st.session_state.inventory[sku] = {
                            "desc":    sku_data["Descripción"],
                            "Central": 0, "Store1": 0, "Store2": 0,
                        }
                    st.session_state.inventory[sku][loc_key] += qty_rec
                    st.session_state.inventory[sku]["desc"]   = sku_data["Descripción"]

                    adjustments.append({
                        "sku":                   sku,
                        "inventory_item_id":      f"← resolver via GET /variants.json?sku={sku}",
                        "location_id":            f"← GET /locations.json → {po['destination']}",
                        "available_adjustment":   qty_rec,
                        "reason":                 "received",
                    })

                    if qty_rec < qty_ord:
                        new_status = "Parcial" if new_status != "Discrepancia" else "Discrepancia"
                    elif qty_rec != qty_ord:
                        new_status = "Discrepancia"

                # Update PO
                for p in st.session_state.pos:
                    if p["id"] == po["id"]:
                        p["status"] = new_status
                        for s in p["skus"]:
                            s["Qty Recibida"] = received_inputs.get(s["SKU"], 0)

                # Show Shopify preview for each SKU
                st.success(f"✅ Recepción registrada en sistema. Estado PO: **{new_status}**")
                st.markdown("---")
                st.markdown("### 📡 Llamadas al API de Shopify")
                st.caption(f"En producción se ejecutarían {len(adjustments)} llamada(s) a Shopify:")

                for adj in adjustments:
                    shopify_preview(
                        endpoint=f"/admin/api/2026-01/inventory_levels/adjust.json",
                        method="POST",
                        payload={
                            "inventory_level": {
                                "inventory_item_id":    adj["inventory_item_id"],
                                "location_id":          adj["location_id"],
                                "available_adjustment": adj["available_adjustment"],
                                "reason":               adj["reason"],
                            }
                        },
                        description=f"Suma **{adj['available_adjustment']} unidades** de `{adj['sku']}` en {po['destination']}",
                    )
