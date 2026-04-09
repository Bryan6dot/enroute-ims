import streamlit as st
import pandas as pd
import uuid
from datetime import datetime
from shopify_mock import shopify_preview

st.set_page_config(page_title="Shipping · Enroute IMS", layout="wide")

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
CARRIERS  = ["DHL", "FedEx", "UPS", "Estafeta", "Redpack", "Otro"]

st.title("🚚 Shipping")
st.caption("Órdenes pendientes de envío · Shopify descuenta el inventario al crearse la orden — Streamlit solo confirma el envío")
st.divider()

st.info(
    "**¿Por qué Streamlit no descuenta inventario aquí?**  \n"
    "Cuando el cliente hace una orden en Shopify, Shopify descuenta el stock automáticamente.  \n"
    "Streamlit solo necesita **confirmar el despacho** con el número de rastreo. "
    "Shopify cambia la orden a `fulfilled` y notifica al cliente."
)
st.divider()

# ── Sync + agregar orden de prueba ───────────────────────────────────────────
col_sync, col_manual = st.columns([2, 1])

with col_sync:
    st.markdown("#### Órdenes pendientes")
    if st.button("🔄 Sincronizar desde Shopify", type="secondary"):
        shopify_preview(
            endpoint="/admin/api/2026-01/orders.json?fulfillment_status=unfulfilled&status=open&limit=50",
            method="GET",
            payload={
                "fulfillment_status": "unfulfilled",
                "status":             "open",
                "fields":             "id,order_number,created_at,customer,line_items,location_id,financial_status",
                "limit":              50,
            },
            description="Shopify devuelve todas las órdenes activas sin fulfillment.",
        )

with col_manual:
    st.markdown("#### Agregar orden de prueba")
    st.caption("Simula una orden para testear el flujo.")
    with st.expander("➕ Nueva orden manual"):
        m_order  = st.text_input("# Orden",      placeholder="SHP-10041",         key="m_order")
        m_client = st.text_input("Cliente",       placeholder="María González",    key="m_client")
        m_sku    = st.text_input("SKU",           placeholder="ERC-BIKE-29-BLK",  key="m_sku")
        m_desc   = st.text_input("Descripción",   placeholder="Trek Marlin 5 BLK",key="m_desc")
        m_qty    = st.number_input("Qty", min_value=1, value=1, key="m_qty")
        m_loc    = st.selectbox("Location", LOCATIONS, key="m_loc")
        if st.button("Agregar orden", key="btn_add"):
            if m_order and m_client and m_sku:
                st.session_state.shopify_orders.append({
                    "order_id":     str(uuid.uuid4())[:8].upper(),
                    "order_number": m_order,
                    "cliente":      m_client,
                    "sku":          m_sku.upper(),
                    "descripcion":  m_desc,
                    "qty":          m_qty,
                    "location":     m_loc,
                    "status":       "unfulfilled",
                    "created_at":   datetime.now().strftime("%Y-%m-%d"),
                })
                st.success("Orden agregada.")
                st.rerun()
            else:
                st.error("# Orden, Cliente y SKU son obligatorios.")

st.divider()

# ── Lista de pendientes ───────────────────────────────────────────────────────
orders = [o for o in st.session_state.get("shopify_orders", []) if o.get("status") == "unfulfilled"]

if not orders:
    st.info("No hay órdenes pendientes. Usa el botón de sincronización o agrega una orden de prueba arriba.")
else:
    st.markdown(f"**{len(orders)} orden(es) pendiente(s) de envío**")
    for order in orders:
        with st.expander(
            f"📦 **{order['order_number']}** — {order['cliente']} · {order['sku']} · {order['qty']} uds. · {order['location']}"
        ):
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("# Orden",  order["order_number"])
            c2.metric("Cliente",  order["cliente"])
            c3.metric("Location", order["location"])
            c4.metric("Fecha",    order["created_at"])

            st.markdown(f"**SKU:** `{order['sku']}` — {order.get('descripcion','—')}  |  **Qty:** {order['qty']}")
            st.caption(f"Shopify Order ID: `{order['order_id']}`")
            st.divider()

            st.markdown("##### Confirmar envío")
            ct1, ct2 = st.columns(2)
            with ct1:
                tracking = st.text_input("Número de rastreo / Label ID *",
                                         placeholder="Ej. 1Z999AA10123456784",
                                         key=f"trk_{order['order_id']}")
            with ct2:
                carrier = st.selectbox("Carrier *", CARRIERS, key=f"car_{order['order_id']}")

            notify = st.checkbox("Notificar al cliente (Shopify envía email automáticamente)",
                                 value=True, key=f"ntf_{order['order_id']}")

            if st.button(f"📡 Marcar como enviado — {order['order_number']}",
                         type="primary", key=f"ship_{order['order_id']}"):
                if not tracking:
                    st.error("El número de rastreo es obligatorio.")
                else:
                    for o in st.session_state.shopify_orders:
                        if o["order_id"] == order["order_id"]:
                            o["status"]     = "fulfilled"
                            o["tracking"]   = tracking
                            o["carrier"]    = carrier
                            o["shipped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

                    st.success(f"✅ Orden **{order['order_number']}** marcada como enviada.")
                    st.markdown("---")
                    st.markdown("### 📡 Llamada al API de Shopify")
                    shopify_preview(
                        endpoint=f"/admin/api/2026-01/orders/{order['order_id']}/fulfillments.json",
                        method="POST",
                        payload={
                            "fulfillment": {
                                "location_id":      f"← GET /locations.json → {order['location']}",
                                "tracking_number":  tracking,
                                "tracking_company": carrier,
                                "notify_customer":  notify,
                                "line_items": [{"id": f"← line_item_id de orden {order['order_id']}",
                                                "quantity": order["qty"]}],
                            }
                        },
                        description=(
                            f"Marca **{order['order_number']}** como enviada con tracking `{tracking}` via {carrier}.  \n"
                            "Shopify actualiza a `fulfilled` y notifica al cliente.  \n"
                            "**El inventario ya fue descontado por Shopify — Streamlit no hace adjust.**"
                        ),
                    )
                    st.rerun()

# ── Historial enviados ────────────────────────────────────────────────────────
fulfilled = [o for o in st.session_state.get("shopify_orders", []) if o.get("status") == "fulfilled"]
if fulfilled:
    st.divider()
    st.markdown(f"#### ✅ Órdenes enviadas esta sesión ({len(fulfilled)})")
    st.dataframe(pd.DataFrame([{
        "# Orden": o["order_number"], "Cliente": o["cliente"],
        "SKU": o["sku"], "Qty": o["qty"],
        "Carrier": o.get("carrier","—"), "Tracking": o.get("tracking","—"),
        "Enviado": o.get("shipped_at","—"), "Location": o["location"],
    } for o in fulfilled]), use_container_width=True, hide_index=True)
