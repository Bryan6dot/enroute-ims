import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.shopify import (
    require_auth, DEMO_INVENTORY, DEMO_MOVEMENTS, DEMO_POS, STATUS_COLORS
)

require_auth()

st.title("📊 Dashboard")
st.caption(f"Sesión: **{st.session_state.user_name}** · {st.session_state.user_role}")

# ── KPI cards ────────────────────────────────────────────────────────────────
total_units = sum(
    qty
    for skus in DEMO_INVENTORY.values()
    for qty in skus.values()
)

low_stock = sum(
    1 for skus in DEMO_INVENTORY.values()
    if sum(skus.values()) < 5
)

pos_transit = sum(1 for p in DEMO_POS if p["status"] == "En tránsito")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total unidades",     f"{total_units:,}",  "+142 esta semana")
k2.metric("SKUs bajo stock",    str(low_stock),       "+2 vs semana pasada", delta_color="inverse")
k3.metric("POs en tránsito",    str(pos_transit),     "ETA más próximo: Apr 8")
k4.metric("Precisión inventario","98.2%",             "+0.4% vs baseline")

st.divider()

# ── Location breakdown ───────────────────────────────────────────────────────
st.subheader("Distribución por location")

locations = ["Central / Warehouse", "Store 1 · Cycling", "Store 2 · Running"]
loc_totals = {loc: sum(skus.get(loc, 0) for skus in DEMO_INVENTORY.values())
              for loc in locations}
grand = max(sum(loc_totals.values()), 1)

cols = st.columns(3)
icons = ["🏭", "🚲", "🏃"]
for col, loc, icon in zip(cols, locations, icons):
    pct = loc_totals[loc] / grand * 100
    with col:
        st.markdown(f"**{icon} {loc}**")
        st.progress(pct / 100)
        st.caption(f"{loc_totals[loc]} units · {pct:.1f}% del total")

st.divider()

# ── Alerts + Recent movements ────────────────────────────────────────────────
left, right = st.columns(2)

with left:
    st.subheader("⚠️ Alertas activas")
    for sku, locs in DEMO_INVENTORY.items():
        total = sum(locs.values())
        if total < 5:
            st.warning(f"**{sku}** — {total} units en total (stock crítico)")
    next_po = min(
        (p for p in DEMO_POS if p["status"] == "En tránsito"),
        key=lambda p: p["eta"],
        default=None,
    )
    if next_po:
        st.info(f"📦 **{next_po['brand']}** — ETA {next_po['eta']} · {next_po['units']} units")

with right:
    st.subheader("📋 Movimientos recientes")
    df_mov = pd.DataFrame(DEMO_MOVEMENTS)
    df_mov.columns = ["Fecha", "Referencia", "Tipo", "Location", "Units", "Usuario"]
    st.dataframe(df_mov, use_container_width=True, hide_index=True)

st.divider()

# ── Inventory table ──────────────────────────────────────────────────────────
st.subheader("📦 Existencias actuales por location")

rows = []
for sku, locs in DEMO_INVENTORY.items():
    row = {"SKU": sku}
    row.update(locs)
    row["Total"] = sum(locs.values())
    row["Estado"] = "🔴 Bajo" if row["Total"] < 5 else ("🟡 Watch" if row["Total"] < 10 else "🟢 OK")
    rows.append(row)

df_inv = pd.DataFrame(rows)
st.dataframe(df_inv, use_container_width=True, hide_index=True)
