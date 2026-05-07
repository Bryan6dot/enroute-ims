# ═══════════════════════════════════════════════════════
# app.py — PATCH INSTRUCTIONS (3 changes)
# ═══════════════════════════════════════════════════════

# ── CHANGE 1: Import (replace existing from data_engine import block) ──────
from data_engine import (
    parse_inventory, parse_orders,
    inventory_by_sku, orders_summary,
    check_fulfillability,
    validate_inventory_file, validate_orders_file,
    parse_warehouse, validate_warehouse_file,
    cross_reference, _loc_stats,
)

# ── CHANGE 2: Session state defaults (add inside _defaults dict) ───────────
# Add this line to _defaults:
"wh_df": None,   # warehouse master file

# ── CHANGE 3: Warehouse uploader + cross-reference section ────────────────
# Location: inside the Dashboard page (page == "📊 Dashboard"),
# AFTER the existing file uploader expander and BEFORE the HTML dashboard render.
# Replace the comment "# ── ANIMATED HTML DASHBOARD ────────────────────────"
# with the block below:

# ── WAREHOUSE UPLOAD + CROSS-REFERENCE ──────────────────────────────────
with st.expander("🏭 Upload Warehouse Master File", expanded=(st.session_state.wh_df is None)):
    st.caption("Format: Brand · Type · Description · Gender · Color · Size · SKU# · UPC/EAN# · Location · Stock Qty")
    wh_file = st.file_uploader(
        "wh", type=["xlsx", "xls", "csv"],
        key="wh_upload", label_visibility="collapsed"
    )
    if wh_file:
        try:
            wh_parsed = parse_warehouse(wh_file)
            warns = validate_warehouse_file(wh_parsed)
            for w in warns:
                st.warning(w)
            if not warns:
                st.session_state.wh_df = wh_parsed
                st.success(
                    f"✅ {wh_parsed['SKU'].nunique():,} SKUs loaded · "
                    f"{int(wh_parsed['Stock_Qty'].sum()):,} total units"
                )
        except Exception as e:
            st.error(f"Error reading warehouse file: {e}")
    elif st.session_state.wh_df is not None:
        wh = st.session_state.wh_df
        st.success(
            f"✅ Loaded — {wh['SKU'].nunique():,} SKUs · "
            f"{int(wh['Stock_Qty'].sum()):,} total units"
        )

# Cross-reference section (only shown when WH file is loaded)
if st.session_state.wh_df is not None and (inv_df is not None):
    st.divider()
    st.markdown("### 🔀 Warehouse ↔ Shopify Cross-Reference")

    xref = cross_reference(
        wh_df = st.session_state.wh_df,
        cc_df = st.session_state.inv_store.get("CC"),
        rr_df = st.session_state.inv_store.get("RR"),
    )
    s = xref["summary"]

    # ── KPI row 1: Shopify ────────────────────────────────────────────
    st.caption("SHOPIFY — items with On Hand > 0")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("CC valued SKUs",        f"{s['shopify_cc_skus_valued']:,}")
    k2.metric("RR valued SKUs",        f"{s['shopify_rr_skus_valued']:,}")
    k3.metric("Combined valued SKUs",  f"{s['shopify_total_valued']:,}")
    k4.metric("Total units (all locs)",f"{s['shopify_total_units']:,}")
    k5.metric("Units in Online loc",   f"{s['shopify_online_units']:,}",
              help="'Online' location = shared warehouse in Shopify")

    st.divider()

    # ── KPI row 2: Warehouse ─────────────────────────────────────────
    st.caption("WAREHOUSE MASTER FILE")
    w1, w2, w3 = st.columns(3)
    w1.metric("Total SKUs in file",   f"{s['wh_total_skus']:,}")
    w2.metric("SKUs with stock > 0",  f"{s['wh_skus_with_stock']:,}")
    w3.metric("Total physical units", f"{s['wh_total_units']:,}")

    st.divider()

    # ── KPI row 3: Cross-reference ───────────────────────────────────
    st.caption("CROSS-REFERENCE RESULTS")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "✅ In both Shopify & WH",
        f"{s['matched_skus']:,}",
        help="SKUs with On_Hand > 0 in Shopify AND present in warehouse file",
    )
    c2.metric(
        "⚠️ Shopify only (not in WH)",
        f"{s['shopify_only_skus']:,}",
        help="Shopify has stock but SKU missing from warehouse master file",
        delta=f"-{s['shopify_only_skus']:,}" if s['shopify_only_skus'] else None,
        delta_color="inverse",
    )
    c3.metric(
        "🏭 WH only (not in Shopify)",
        f"{s['wh_only_skus']:,}",
        help="Warehouse has stock > 0 but SKU has no On_Hand in Shopify",
        delta=f"-{s['wh_only_skus']:,}" if s['wh_only_skus'] else None,
        delta_color="inverse",
    )

    # ── Discrepancy sub-row (matched SKUs only) ───────────────────────
    st.caption("DISCREPANCY — matched SKUs: WH Stock vs Shopify Online units")
    d1, d2, d3 = st.columns(3)
    d1.metric("✅ Exact match",    f"{s['delta_exact']:,}")
    d2.metric("⬆ WH > Shopify",   f"{s['delta_wh_higher']:,}", delta_color="normal")
    d3.metric("⬇ WH < Shopify",   f"{s['delta_wh_lower']:,}",  delta_color="inverse")

    st.divider()

    # ── Detail expanders ──────────────────────────────────────────────
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        with st.expander(f"🔍 {s['matched_skus']:,} matched SKUs — discrepancy detail"):
            st.dataframe(xref["matched"], use_container_width=True, hide_index=True)

    with col_b:
        with st.expander(f"⚠️ {s['shopify_only_skus']:,} Shopify-only SKUs"):
            st.caption("Have On_Hand in Shopify but are absent from the warehouse master file.")
            st.dataframe(xref["shopify_only"], use_container_width=True, hide_index=True)

    with col_c:
        with st.expander(f"🏭 {s['wh_only_skus']:,} Warehouse-only SKUs"):
            st.caption("Have physical stock in warehouse but no On_Hand recorded in Shopify.")
            st.dataframe(xref["wh_only"], use_container_width=True, hide_index=True)
