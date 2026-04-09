import streamlit as st
import pandas as pd

st.set_page_config(page_title="Dashboard · Enroute IMS", layout="wide")

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

st.title("📊 Dashboard")
st.caption("Vista general de inventario · KPIs en tiempo real")
st.divider()

inv  = st.session_state.get("inventory", {})
pos  = st.session_state.get("pos", [])
trfs = st.session_state.get("transfers", [])

total_skus  = len(inv)
total_units = sum(v.get("Central",0)+v.get("Store1",0)+v.get("Store2",0) for v in inv.values())
low_stock   = sum(1 for v in inv.values() if 0 < v.get("Central",0)+v.get("Store1",0)+v.get("Store2",0) < 5)
stockouts   = sum(1 for v in inv.values() if v.get("Central",0)+v.get("Store1",0)+v.get("Store2",0) == 0)
pos_transit = sum(1 for p in pos if p.get("status") == "En tránsito")
pos_partial = sum(1 for p in pos if p.get("status") == "Parcial")

k1,k2,k3,k4,k5,k6 = st.columns(6)
k1.metric("📦 SKUs en sistema",   total_skus  or "—")
k2.metric("🔢 Unidades totales",  total_units or "—")
k3.metric("🚚 POs en tránsito",   pos_transit or "—")
k4.metric("⚠️ Recepción parcial", pos_partial or "—")
k5.metric("🔴 Low stock",         low_stock   or "—", delta_color="inverse")
k6.metric("🚫 Stockouts",         stockouts   or "—", delta_color="inverse")

st.divider()
st.markdown("#### Distribución por Location")

if not inv:
    c1,c2,c3 = st.columns(3)
    for col, loc in zip([c1,c2,c3], ["Central / Warehouse","Store 1 · Cycling","Store 2 · Running"]):
        with col:
            with st.container(border=True):
                st.markdown(f"**{loc}**")
                st.markdown("### — unidades")
                st.caption("Sin datos. Recibe un PO para registrar existencias.")
else:
    central_u = sum(v.get("Central",0) for v in inv.values())
    store1_u  = sum(v.get("Store1",0)  for v in inv.values())
    store2_u  = sum(v.get("Store2",0)  for v in inv.values())
    all_u     = max(central_u + store1_u + store2_u, 1)
    c1,c2,c3 = st.columns(3)
    for col, label, val in zip(
        [c1,c2,c3],
        ["🏭 Central / Warehouse","🚲 Store 1 · Cycling","🏃 Store 2 · Running"],
        [central_u, store1_u, store2_u]
    ):
        with col:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.markdown(f"### {val} unidades")
                st.progress(val / all_u)
                st.caption(f"{val/all_u*100:.1f}% del total")

st.divider()
left, right = st.columns(2)

with left:
    st.markdown("#### ⚠️ Alertas activas")
    if not inv:
        st.info("Los alertas aparecerán aquí una vez se registren existencias.")
    else:
        alerted = False
        for sku, data in inv.items():
            total = data.get("Central",0)+data.get("Store1",0)+data.get("Store2",0)
            if total == 0:
                st.error(f"**{sku}** — {data.get('desc','—')} · STOCKOUT")
                alerted = True
            elif total < 5:
                st.warning(f"**{sku}** — {data.get('desc','—')} · Low stock ({total} uds.)")
                alerted = True
        if not alerted:
            st.success("Sin alertas activas.")

    st.markdown("#### 🚚 POs activos")
    if not pos:
        st.info("No hay POs. Crea uno en PO Tracker.")
    else:
        for p in pos:
            if p.get("status") == "En tránsito":
                st.info(f"**{p['id']}** — {p.get('supplier','—')} · ETA: {p.get('eta','—')}")
            elif p.get("status") == "Parcial":
                st.warning(f"**{p['id']}** — {p.get('supplier','—')} · Recepción parcial")

with right:
    st.markdown("#### 📋 Inventario completo")
    if not inv:
        st.info("Sin datos de inventario aún.")
    else:
        rows = []
        for sku, data in inv.items():
            total = data.get("Central",0)+data.get("Store1",0)+data.get("Store2",0)
            rows.append({
                "SKU": sku, "Descripción": data.get("desc","—"),
                "Central 🏭": data.get("Central",0),
                "Store 1 🚲": data.get("Store1",0),
                "Store 2 🏃": data.get("Store2",0),
                "Total": total,
                "Estado": "🚫 Stockout" if total==0 else ("🔴 Low" if total<5 else ("🟡 Watch" if total<10 else "🟢 OK")),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("#### 🔄 Últimos traspasos")
    if not trfs:
        st.info("No se han registrado traspasos.")
    else:
        st.dataframe(pd.DataFrame(trfs[-10:]), use_container_width=True, hide_index=True)
