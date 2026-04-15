"""
Enroute IMS — app.py
Single-file Streamlit app. Requires data_engine.py in the same folder.
"""

import streamlit as st
import pandas as pd
import uuid
from datetime import date, datetime

st.set_page_config(
    page_title="Enroute IMS",
    page_icon="🚲",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Import data engine ────────────────────────────────────────────────────────
try:
    from data_engine import (
        parse_inventory, parse_orders,
        inventory_by_sku, orders_summary,
        check_fulfillability, inventory_match,
        validate_inventory_file, validate_orders_file,
    )
    ENGINE_OK = True
except ImportError:
    ENGINE_OK = False

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
USERS = {
    "admin":      {"password": "enroute2026", "role": "Admin",      "name": "Admin"},
    "warehouse":  {"password": "wh2026",      "role": "Warehouse",  "name": "Warehouse"},
    "purchasing": {"password": "po2026",      "role": "Purchasing", "name": "Purchasing"},
}

LOCATIONS = ["In Store", "Online", "SLG", "Enroute Richmond", "SLG Hong Kong"]
WAREHOUSE_LOCATION = "In Store"   # physical warehouse location for match analysis
CARRIERS  = ["DHL", "FedEx", "UPS", "Canada Post", "Purolator", "Other"]

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
_defaults = {
    "page":        "📊 Dashboard",
    "pos":         [],
    "po_items":    [{"SKU": "", "Description": "", "Qty": 1}],
    "inv_df":      None,   # parsed inventory DataFrame
    "ord_df":      None,   # parsed orders DataFrame
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("user_role"):
    _, col, _ = st.columns([1, 1.1, 1])
    with col:
        st.markdown("## 🚲 Enroute IMS")
        st.markdown("##### Inventory Management System")
        st.divider()
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Sign In", use_container_width=True, type="primary"):
            u = USERS.get(username)
            if u and u["password"] == password:
                st.session_state.user_role = u["role"]
                st.session_state.user_name = u["name"]
                st.rerun()
            else:
                st.error("Invalid credentials.")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(f"### 🚲 Enroute IMS")
    st.caption(f"**{st.session_state.user_name}** · {st.session_state.user_role}")
    st.divider()

    pages = ["📊 Dashboard", "📦 Inventory Control", "📋 PO Tracker"]
    for p in pages:
        if st.button(p, use_container_width=True,
                     type="primary" if st.session_state.page == p else "secondary"):
            st.session_state.page = p
            st.rerun()

    st.divider()
    if st.button("🚪 Sign Out", use_container_width=True):
        for k in ["user_role", "user_name"]:
            st.session_state.pop(k, None)
        st.rerun()

    # Data status indicator
    st.divider()
    st.caption("**Data status**")
    if st.session_state.inv_df is not None:
        st.success(f"✅ Inventory loaded  \n{len(st.session_state.inv_df):,} rows")
    else:
        st.warning("⚠️ No inventory file")
    if st.session_state.ord_df is not None:
        st.success(f"✅ Orders loaded  \n{len(st.session_state.ord_df):,} rows")
    else:
        st.warning("⚠️ No orders file")

page = st.session_state.page

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def kpi(col, label, value, delta=None, delta_color="normal", help=None):
    col.metric(label=label, value=value, delta=delta,
               delta_color=delta_color, help=help)

def shopify_preview(endpoint, method, payload, description=""):
    with st.container(border=True):
        st.markdown("#### 📡 Shopify API — Preview")
        if description:
            st.caption(description)
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"**Method:** `{method}`")
            st.code(endpoint, language="text")
            st.caption(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        with c2:
            st.markdown("**Payload:**")
            st.json(payload)
        st.warning("⚠️ **Test mode** — This payload was NOT sent to Shopify.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    st.title("📊 Dashboard")

    if not ENGINE_OK:
        st.error("❌ `data_engine.py` not found. Place it in the same folder as `app.py`.")
        st.stop()

    # ── File upload ────────────────────────────────────────────────────────
    with st.expander("📂 Upload Shopify Export Files", expanded=(st.session_state.inv_df is None)):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Inventory Export**")
            st.caption("Admin → Products → Inventory → Export")
            inv_file = st.file_uploader("Inventory CSV", type=["csv"], key="inv_upload",
                                         label_visibility="collapsed")
            if inv_file:
                try:
                    df = parse_inventory(inv_file)
                    warns = validate_inventory_file(df)
                    if warns:
                        for w in warns: st.warning(w)
                    else:
                        st.session_state.inv_df = df
                        st.success(f"✅ Loaded — {len(df):,} rows · {df['SKU'].nunique():,} SKUs")
                except Exception as e:
                    st.error(f"Error parsing inventory file: {e}")

        with c2:
            st.markdown("**Orders Export**")
            st.caption("Admin → Orders → Export")
            ord_file = st.file_uploader("Orders CSV", type=["csv"], key="ord_upload",
                                         label_visibility="collapsed")
            if ord_file:
                try:
                    df = parse_orders(ord_file)
                    warns = validate_orders_file(df)
                    if warns:
                        for w in warns: st.warning(w)
                    else:
                        st.session_state.ord_df = df
                        st.success(f"✅ Loaded — {len(df):,} rows · {df['Order_ID'].nunique():,} orders")
                except Exception as e:
                    st.error(f"Error parsing orders file: {e}")

    inv_df = st.session_state.inv_df
    ord_df = st.session_state.ord_df

    if inv_df is None and ord_df is None:
        st.info("Upload at least one file above to see the dashboard.")
        st.stop()

    # ── SECTION 1: INVENTORY MATCH ─────────────────────────────────────────
    if inv_df is not None:
        st.markdown("---")
        st.markdown("### 📦 Inventory — Shopify vs Warehouse")

        match = inventory_match(inv_df, warehouse_location=WAREHOUSE_LOCATION)
        by_sku = inventory_by_sku(inv_df)

        c1, c2, c3, c4, c5 = st.columns(5)
        kpi(c1, "Match Rate (In Store)",
            f"{match['match_pct']}%",
            help="% of active SKUs where On Hand = Available in 'In Store' location")
        kpi(c2, "Active SKUs (have stock)",
            f"{match['active_skus']:,}",
            help="SKUs with at least 1 unit on hand")
        kpi(c3, "✅ Matched",
            f"{match['matched_skus']:,}")
        kpi(c4, "🔴 Discrepancies",
            f"{match['discrepancy_skus']:,}",
            delta=f"-{match['discrepancy_skus']} to resolve" if match['discrepancy_skus'] else None,
            delta_color="inverse")
        kpi(c5, "Total SKUs in Catalog",
            f"{match['total_skus']:,}")

        # Stock by location
        st.markdown("#### Stock Distribution by Location")
        locs = [c for c in by_sku.columns if c in LOCATIONS]
        if locs:
            loc_totals = {loc: int(by_sku[loc].sum()) for loc in locs}
            grand_total = sum(loc_totals.values())
            cols = st.columns(len(locs) + 1)
            for i, (loc, total) in enumerate(loc_totals.items()):
                pct = round(total / grand_total * 100, 1) if grand_total else 0
                kpi(cols[i], loc, f"{total:,} units", delta=f"{pct}%", delta_color="off")
            kpi(cols[-1], "Total On Hand", f"{grand_total:,} units")

        # Discrepancy detail
        detail = match["detail_df"]
        disc = detail[detail["Status"] == "🔴 Discrepancy"]
        if not disc.empty:
            with st.expander(f"🔴 View {len(disc)} discrepancies"):
                st.dataframe(
                    disc[["SKU", "Title", "Variant", "On_Hand", "Available", "Committed", "Difference", "Status"]],
                    use_container_width=True, hide_index=True
                )

        # Full inventory table
        with st.expander("📋 Full inventory by SKU (all locations)"):
            display_cols = ["SKU", "Title", "Variant", "Total_OnHand", "Total_Available", "Total_Committed", "Total_Incoming"] + locs
            display_cols = [c for c in display_cols if c in by_sku.columns]
            st.dataframe(
                by_sku[by_sku["Total_OnHand"] > 0][display_cols].sort_values("Total_OnHand", ascending=False),
                use_container_width=True, hide_index=True
            )

    # ── SECTION 2: ORDERS ─────────────────────────────────────────────────
    if ord_df is not None:
        st.markdown("---")
        st.markdown("### 🚚 Orders")

        summary = orders_summary(ord_df)

        # KPI row 1 — fulfillment
        c1, c2, c3, c4 = st.columns(4)
        kpi(c1, "Total Orders",      f"{summary['total_orders']:,}")
        kpi(c2, "✅ Fulfilled",       f"{summary['fulfilled']:,}",
            delta=f"{round(summary['fulfilled']/summary['total_orders']*100,1)}%", delta_color="off")
        kpi(c3, "⏳ Unfulfilled",     f"{summary['unfulfilled']:,}",
            delta="paid, not shipped" if summary['unfulfilled'] else None, delta_color="inverse")
        kpi(c4, "🔀 Partial",         f"{summary['partial']:,}")

        # KPI row 2 — processing time
        c1, c2, c3, c4 = st.columns(4)
        kpi(c1, "Avg Processing Time", f"{summary['avg_processing_hrs']} hrs",
            help="From Created At to Fulfilled At")
        kpi(c2, "Fastest Fulfillment", f"{summary['min_processing_hrs']} hrs")
        kpi(c3, "Slowest Fulfillment", f"{summary['max_processing_hrs']} hrs")
        kpi(c4, "Refunded / Cancelled",
            f"{summary['refunded']} / {summary['cancelled']}",
            delta_color="off")

        # ── SECTION 3: FULFILLABILITY (needs both files) ───────────────────
        if inv_df is not None:
            st.markdown("---")
            st.markdown("### 🎯 Can We Fulfill Open Orders?")
            st.caption("Checks available stock against each open order line item")

            fulf = check_fulfillability(ord_df, inv_df)
            total_lines = len(fulf)
            can         = int(fulf["Can_Fulfill"].sum())
            cannot      = total_lines - can
            pct         = round(can / total_lines * 100, 1) if total_lines else 0

            c1, c2, c3, c4 = st.columns(4)
            kpi(c1, "Open Order Lines",     f"{total_lines:,}")
            kpi(c2, "✅ Can Fulfill",        f"{can:,}",
                delta=f"{pct}%", delta_color="off")
            kpi(c3, "❌ Stock Insufficient", f"{cannot:,}",
                delta=f"{round(100-pct,1)}% of lines",
                delta_color="inverse" if cannot > 0 else "off")
            kpi(c4, "Units Short (total gap)",
                f"{int(fulf['Gap'].sum()):,}",
                help="Total units missing across all unfulfillable lines")

            # Table — can NOT fulfill
            cant_df = fulf[~fulf["Can_Fulfill"]].sort_values("Gap", ascending=False)
            if not cant_df.empty:
                with st.expander(f"❌ {len(cant_df)} lines that cannot be fulfilled"):
                    st.dataframe(
                        cant_df[["Order_ID", "SKU", "Item_Name", "Qty_Ordered",
                                 "Available_Stock", "Gap", "Financial_Status"]],
                        use_container_width=True, hide_index=True
                    )

            # Table — CAN fulfill
            can_df = fulf[fulf["Can_Fulfill"]].sort_values("Order_ID")
            if not can_df.empty:
                with st.expander(f"✅ {len(can_df)} lines ready to ship"):
                    st.dataframe(
                        can_df[["Order_ID", "SKU", "Item_Name", "Qty_Ordered",
                                "Available_Stock", "Financial_Status"]],
                        use_container_width=True, hide_index=True
                    )

        # Orders status table
        with st.expander("📋 All orders detail"):
            order_level = ord_df.drop_duplicates("Order_ID")[[
                "Order_ID", "Financial_Status", "Fulfillment_Status",
                "Created_At", "Fulfilled_At", "Subtotal", "Total",
                "Shipping_Method", "Vendor"
            ]].copy()
            order_level["Created_At"]  = order_level["Created_At"].dt.strftime("%Y-%m-%d %H:%M")
            order_level["Fulfilled_At"] = order_level["Fulfilled_At"].dt.strftime("%Y-%m-%d %H:%M").fillna("—")
            st.dataframe(order_level, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: INVENTORY CONTROL
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📦 Inventory Control":
    st.title("📦 Inventory Control")
    tab1, tab2 = st.tabs(["📥 Receive PO", "🔄 Move Stock"])

    # ── TAB 1: RECEIVE PO ─────────────────────────────────────────────────
    with tab1:
        st.markdown("#### Receive a Purchase Order")
        pos_in_transit = [p for p in st.session_state.pos if p.get("status") == "In Transit"]

        if not pos_in_transit:
            st.info("No POs in transit. Create one in **PO Tracker** first.")
        else:
            po_options = {f"{p['id']} — {p['brand']} (ETA: {p['eta']})": p for p in pos_in_transit}
            selected_label = st.selectbox("Select PO to receive", list(po_options.keys()))
            po = po_options[selected_label]

            st.markdown(f"**PO:** `{po['id']}` · Brand: **{po['brand']}** · Destination: **{po.get('location','—')}**")
            st.divider()

            if not po.get("skus"):
                st.warning("This PO has no line items. Add SKUs in PO Tracker.")
            else:
                st.markdown("**Line items — enter received quantities:**")
                rows = []
                for item in po["skus"]:
                    c1, c2, c3, c4 = st.columns([2, 3, 1, 1])
                    c1.text(item["sku"])
                    c2.text(item["desc"])
                    c3.text(f"Ordered: {item['qty']}")
                    received = c4.number_input("Rcvd", min_value=0,
                                               max_value=item["qty"] * 2,
                                               value=item["qty"],
                                               key=f"rcv_{po['id']}_{item['sku']}")
                    rows.append({"sku": item["sku"], "ordered": item["qty"], "received": received})

                scenario = None
                for r in rows:
                    if r["received"] == 0:
                        continue
                    if r["received"] == r["ordered"]:
                        scenario = "full"
                    elif r["received"] < r["ordered"]:
                        scenario = "partial"
                    elif r["received"] != r["ordered"]:
                        scenario = "discrepancy"

                if scenario == "partial":
                    st.warning("⚠️ **Partial receipt** — Some quantities are below ordered amounts.")
                elif scenario == "discrepancy":
                    st.error("🔴 **Discrepancy** — Received quantity differs from ordered.")

                notes = st.text_area("Notes (optional)", placeholder="Damage, shortages, etc.")

                if st.button("✅ Confirm Receipt", type="primary"):
                    payload = {
                        "po_id": po["id"],
                        "location": po.get("location", "—"),
                        "received_at": datetime.now().isoformat(),
                        "scenario": scenario or "full",
                        "line_items": [{"sku": r["sku"], "qty": r["received"]} for r in rows],
                        "notes": notes,
                    }
                    shopify_preview(
                        endpoint=f"/admin/api/2024-01/inventory_levels/adjust.json",
                        method="POST",
                        payload=payload,
                        description="Each line item would be adjusted individually via Shopify Inventory API."
                    )
                    po["status"] = "Received"

    # ── TAB 2: MOVE STOCK ─────────────────────────────────────────────────
    with tab2:
        st.markdown("#### Move Stock Between Locations")

        c1, c2 = st.columns(2)
        origin = c1.selectbox("From", LOCATIONS, key="move_from")
        destination = c2.selectbox("To", [l for l in LOCATIONS if l != origin], key="move_to")

        st.markdown("---")
        move_method = st.radio("Add items by:", ["SKU search", "Upload Excel"], horizontal=True)

        move_items = []

        if move_method == "SKU search":
            sku_input = st.text_input("SKU", placeholder="e.g. MB4501AR-5240")
            qty_input = st.number_input("Quantity", min_value=1, value=1)
            if sku_input:
                move_items = [{"sku": sku_input, "qty": qty_input}]

        else:
            tmpl_df = pd.DataFrame(columns=["SKU", "Descripción", "Cantidad"])
            excel_file = st.file_uploader("Upload Excel", type=["xlsx","xls"], key="move_excel")
            if excel_file:
                try:
                    move_df = pd.read_excel(excel_file)
                    sku_col  = next((c for c in move_df.columns if "sku" in c.lower()), None)
                    qty_col  = next((c for c in move_df.columns if any(k in c.lower() for k in ["qty","cantidad","quantity"])), None)
                    desc_col = next((c for c in move_df.columns if any(k in c.lower() for k in ["desc","descripcion","descripción","title","nombre"])), None)
                    if sku_col and qty_col:
                        move_df = move_df.rename(columns={sku_col: "SKU", qty_col: "Qty"})
                        if desc_col:
                            move_df = move_df.rename(columns={desc_col: "Description"})
                        st.markdown("**Preview:**")
                        st.dataframe(move_df[["SKU", "Qty"] + (["Description"] if "Description" in move_df.columns else [])],
                                     use_container_width=True, hide_index=True)
                        move_items = move_df[["SKU", "Qty"]].to_dict("records")
                    else:
                        st.error("Could not detect SKU / Qty columns.")
                except Exception as e:
                    st.error(f"Error reading file: {e}")

        if move_items:
            if st.button("🚚 Move Stock", type="primary"):
                payload = {
                    "from_location": origin,
                    "to_location": destination,
                    "moved_at": datetime.now().isoformat(),
                    "items": move_items,
                }
                shopify_preview(
                    endpoint="/admin/api/2024-01/inventory_levels/adjust.json",
                    method="POST",
                    payload=payload,
                    description=f"Deduct from '{origin}', add to '{destination}' for each SKU."
                )

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: PO TRACKER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 PO Tracker":
    st.title("📋 PO Tracker")
    tab1, tab2 = st.tabs(["➕ Create PO", "📄 All POs"])

    # ── TAB 1: CREATE PO ──────────────────────────────────────────────────
    with tab1:
        st.markdown("#### New Purchase Order")
        c1, c2 = st.columns(2)
        brand     = c1.text_input("Brand / Vendor")
        supplier  = c2.text_input("Distributor (optional)")
        c1, c2 = st.columns(2)
        eta      = c1.date_input("Expected Arrival", value=date.today())
        location = c2.selectbox("Destination", LOCATIONS)

        st.markdown("**Line items:**")
        items = st.session_state.po_items

        for i, item in enumerate(items):
            c1, c2, c3, c4 = st.columns([2, 4, 1, 0.5])
            items[i]["SKU"]         = c1.text_input("SKU",         value=item["SKU"],         key=f"po_sku_{i}", label_visibility="collapsed", placeholder="SKU")
            items[i]["Description"] = c2.text_input("Description", value=item["Description"], key=f"po_desc_{i}", label_visibility="collapsed", placeholder="Description")
            items[i]["Qty"]         = c3.number_input("Qty",        value=item["Qty"],         key=f"po_qty_{i}", min_value=1, label_visibility="collapsed")
            if c4.button("🗑", key=f"del_{i}") and len(items) > 1:
                st.session_state.po_items.pop(i)
                st.rerun()

        if st.button("+ Add line"):
            st.session_state.po_items.append({"SKU": "", "Description": "", "Qty": 1})
            st.rerun()

        st.divider()
        attach = st.file_uploader("Attach invoice (PDF or Excel, optional)", type=["pdf","xlsx","xls"])

        if st.button("🚀 Publish PO", type="primary"):
            if not brand:
                st.error("Brand is required.")
            elif not any(i["SKU"].strip() for i in items):
                st.error("Add at least one line item with a SKU.")
            else:
                new_id = f"PO-{datetime.now().strftime('%Y%m%d')}-{len(st.session_state.pos)+1:03d}"
                new_po = {
                    "id":       new_id,
                    "brand":    brand,
                    "supplier": supplier or "—",
                    "eta":      str(eta),
                    "location": location,
                    "status":   "In Transit",
                    "created":  datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "skus":     [{"sku": i["SKU"], "desc": i["Description"], "qty": i["Qty"]}
                                 for i in items if i["SKU"].strip()],
                }
                st.session_state.pos.append(new_po)
                st.session_state.po_items = [{"SKU": "", "Description": "", "Qty": 1}]
                st.success(f"✅ **{new_id}** published — visible in Inventory Control → Receive PO.")
                st.rerun()

    # ── TAB 2: ALL POs ────────────────────────────────────────────────────
    with tab2:
        st.markdown("#### Purchase Orders")

        if not st.session_state.pos:
            st.info("No POs yet. Create one in the tab above.")
        else:
            status_filter = st.selectbox("Filter by status",
                                         ["All", "In Transit", "Received", "Cancelled"])
            filtered = st.session_state.pos if status_filter == "All" \
                       else [p for p in st.session_state.pos if p["status"] == status_filter]

            for po in filtered:
                status_icon = {"In Transit": "🚚", "Received": "✅", "Cancelled": "❌"}.get(po["status"], "📋")
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                    c1.markdown(f"**{po['id']}**  \n{po['brand']} · {po['supplier']}")
                    c2.markdown(f"**ETA:** {po['eta']}  \n**Dest:** {po['location']}")
                    c3.markdown(f"**Status:** {status_icon} {po['status']}  \n**Created:** {po['created']}")
                    c4.markdown(f"**Lines:** {len(po.get('skus', []))}")

                    if po.get("skus"):
                        with st.expander("View items"):
                            st.dataframe(
                                pd.DataFrame(po["skus"]).rename(columns={"sku":"SKU","desc":"Description","qty":"Qty"}),
                                use_container_width=True, hide_index=True
                            )
