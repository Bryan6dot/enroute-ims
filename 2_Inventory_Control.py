import streamlit as st
import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.shopify_mock import shopify_preview

st.set_page_config(page_title="Inventory Control · Enroute IMS", layout="wide")

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

st.title("📦 Inventory Control")
st.caption("Existencias por location · Traspasos entre ubicaciones")
st.divider()

tab_stock, tab_transfer = st.tabs(["📊 Existencias actuales", "🔄 Traspaso entre locations"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — EXISTENCIAS ACTUALES
# ══════════════════════════════════════════════════════════════════════════════
with tab_stock:
    inv = st.session_state.get("inventory", {})

    if not inv:
        st.info("Sin datos de inventario. Las existencias se registran al recibir un PO en el módulo **PO Tracker**.")
    else:
        # Filters
        col_f1, col_f2 = st.columns([1, 2])
        with col_f1:
            loc_filter = st.selectbox("Filtrar por location", ["Todas"] + LOCATIONS)
        with col_f2:
            search = st.text_input("Buscar SKU o descripción", placeholder="Ej. TREK o ERC-BIKE")

        rows = []
        for sku, data in inv.items():
            if search and search.upper() not in sku.upper() and search.lower() not in data.get("desc","").lower():
                continue
            total = data.get("Central",0)+data.get("Store1",0)+data.get("Store2",0)
            row = {
                "SKU":          sku,
                "Descripción":  data.get("desc","—"),
                "Central 🏭":  data.get("Central",0),
                "Store 1 🚲":  data.get("Store1",0),
                "Store 2 🏃":  data.get("Store2",0),
                "Total":        total,
                "Estado":       "🚫 Stockout" if total==0 else ("🔴 Low" if total<5 else ("🟡 Watch" if total<10 else "🟢 OK")),
            }
            if loc_filter != "Todas":
                lk = LOC_KEY[loc_filter]
                if data.get(lk,0) == 0:
                    continue
            rows.append(row)

        if not rows:
            st.warning("No hay artículos que coincidan con el filtro.")
        else:
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Estado": st.column_config.TextColumn("Estado"),
                },
            )
            st.caption(f"Mostrando {len(rows)} SKU(s) · {sum(r['Total'] for r in rows)} unidades totales")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — TRASPASO
# ══════════════════════════════════════════════════════════════════════════════
with tab_transfer:
    st.markdown("#### Traspaso entre locations")
    st.caption("Mueve unidades de una ubicación a otra. Shopify recibe dos ajustes: resta en origen y suma en destino.")

    inv = st.session_state.get("inventory", {})

    if not inv:
        st.info("Sin datos de inventario. Recibe al menos un PO para habilitar traspasos.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            origin = st.selectbox("📍 Location origen", LOCATIONS, key="trf_origin")
        with col2:
            dest_options = [l for l in LOCATIONS if l != origin]
            destination  = st.selectbox("📍 Location destino", dest_options, key="trf_dest")

        st.markdown("#### Artículos a traspasar")

        origin_key = LOC_KEY[origin]
        available_skus = {sku: data for sku, data in inv.items() if data.get(origin_key, 0) > 0}

        if not available_skus:
            st.warning(f"No hay existencias en **{origin}** para traspasar.")
        else:
            trf_items = []
            for sku, data in available_skus.items():
                avail = data.get(origin_key, 0)
                col_a, col_b, col_c, col_d = st.columns([2, 2, 1, 1])
                with col_a:
                    st.text(sku)
                with col_b:
                    st.text(data.get("desc","—"))
                with col_c:
                    st.caption(f"Disponible: {avail}")
                with col_d:
                    qty = st.number_input(
                        "Qty",
                        min_value=0,
                        max_value=avail,
                        value=0,
                        key=f"trf_{sku}",
                    )
                if qty > 0:
                    trf_items.append({"sku": sku, "desc": data.get("desc","—"), "qty": qty})

            st.divider()
            notes_trf = st.text_area("Notas del traspaso (opcional)", key="trf_notes")

            if st.button("📡 Ejecutar traspaso y enviar a Shopify", type="primary"):
                if not trf_items:
                    st.error("Selecciona al menos un artículo con cantidad mayor a 0.")
                else:
                    dest_key = LOC_KEY[destination]
                    for item in trf_items:
                        st.session_state.inventory[item["sku"]][origin_key] -= item["qty"]
                        st.session_state.inventory[item["sku"]][dest_key]   += item["qty"]
                        st.session_state.transfers.append({
                            "Fecha":       datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "SKU":         item["sku"],
                            "Descripción": item["desc"],
                            "Qty":         item["qty"],
                            "Origen":      origin,
                            "Destino":     destination,
                            "Notas":       notes_trf,
                        })

                    st.success(f"✅ Traspaso registrado — {len(trf_items)} SKU(s) movidos de {origin} a {destination}.")
                    st.markdown("---")
                    st.markdown("### 📡 Llamadas al API de Shopify")
                    st.caption(f"En producción se ejecutarían **{len(trf_items) * 2} llamadas** (–origen / +destino por cada SKU):")

                    for item in trf_items:
                        shopify_preview(
                            endpoint="/admin/api/2026-01/inventory_levels/adjust.json",
                            method="POST",
                            payload={
                                "inventory_level": {
                                    "inventory_item_id":    f"← GET /variants.json?sku={item['sku']}",
                                    "location_id":          f"← GET /locations.json → {origin}",
                                    "available_adjustment": -item["qty"],
                                    "reason":               "movement_created",
                                }
                            },
                            description=f"**RESTA {item['qty']} uds.** de `{item['sku']}` en {origin}",
                        )
                        shopify_preview(
                            endpoint="/admin/api/2026-01/inventory_levels/adjust.json",
                            method="POST",
                            payload={
                                "inventory_level": {
                                    "inventory_item_id":    f"← GET /variants.json?sku={item['sku']}",
                                    "location_id":          f"← GET /locations.json → {destination}",
                                    "available_adjustment": +item["qty"],
                                    "reason":               "movement_received",
                                }
                            },
                            description=f"**SUMA {item['qty']} uds.** de `{item['sku']}` en {destination}",
                        )
