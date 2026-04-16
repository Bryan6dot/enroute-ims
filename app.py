"""
Enroute IMS — app.py
Single-file Streamlit app. Requires data_engine.py in the same folder.
"""

import streamlit as st
import pandas as pd
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
        check_fulfillability,
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
SHOPIFY_LOCATIONS = ["In Store", "Online", "SLG", "Enroute Richmond", "SLG Hong Kong"]

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
_defaults = {
    "page":         "📊 Dashboard",
    "pos":          [],
    "po_items":     [{"SKU": "", "Description": "", "Qty": 1}],
    "inv_df":       None,   # combined inventory (all stores)
    "ord_df":       None,   # combined orders (all stores)
    "inv_store":    {},     # {"CC": df, "RR": df} — per-store raw
    "ord_store":    {},     # {"CC": df, "RR": df} — per-store raw
    "po_published": None,
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
    st.markdown("### 🚲 Enroute IMS")
    st.caption(f"**{st.session_state.user_name}** · {st.session_state.user_role}")
    st.divider()

    for p in ["📊 Dashboard", "📦 Inventory Control", "📋 PO Tracker"]:
        st.button(
            p, use_container_width=True,
            type="primary" if st.session_state.page == p else "secondary",
            on_click=lambda pg=p: st.session_state.update({"page": pg}),
        )

    st.divider()
    if st.button("🚪 Sign Out", use_container_width=True):
        for k in ["user_role", "user_name"]:
            st.session_state.pop(k, None)
        st.rerun()

    st.divider()
    st.caption("**Data loaded**")
    STORES = {"CC": "🚴 Cycling", "RR": "🏃 Running"}
    for store_code, store_label in STORES.items():
        inv_loaded = store_code in st.session_state.inv_store
        ord_loaded = store_code in st.session_state.ord_store
        inv_icon = "✅" if inv_loaded else "⚪"
        ord_icon = "✅" if ord_loaded else "⚪"
        st.caption(
            f"**{store_label}** ({store_code})  \n"
            f"{inv_icon} Inventory · {ord_icon} Orders"
        )

page = st.session_state.page

# ══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
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


def _loc_stats(inv_df):
    """Per-location totals and %. Returns (DataFrame, grand_total)."""
    grp = inv_df.groupby("Location").agg(
        On_Hand   =("On_Hand",   "sum"),
        Available =("Available", "sum"),
        Committed =("Committed", "sum"),
        Incoming  =("Incoming",  "sum"),
    ).reset_index()
    grand = grp["On_Hand"].sum()
    grp["pct_total"]     = grp["On_Hand"] / grand * 100 if grand else 0
    grp["pct_available"] = grp["Available"] / grp["On_Hand"].replace(0, 1) * 100
    grp["pct_committed"] = grp["Committed"] / grp["On_Hand"].replace(0, 1) * 100
    grp = grp[grp["On_Hand"] > 0].reset_index(drop=True)
    return grp, grand


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    st.title("📊 Dashboard")

    if not ENGINE_OK:
        st.error("❌ `data_engine.py` not found. Place it in the same folder as `app.py`.")
        st.stop()

    # ── File upload ────────────────────────────────────────────────────────
    no_data = not st.session_state.inv_store and not st.session_state.ord_store
    with st.expander("📂 Upload Shopify Export Files", expanded=no_data):

        def _rebuild_combined():
            """Merge per-store DFs → combined inv_df / ord_df with Store column."""
            if st.session_state.inv_store:
                frames = [df.copy().assign(Store=code)
                          for code, df in st.session_state.inv_store.items()]
                st.session_state.inv_df = pd.concat(frames, ignore_index=True)
            else:
                st.session_state.inv_df = None
            if st.session_state.ord_store:
                frames = [df.copy().assign(Store=code)
                          for code, df in st.session_state.ord_store.items()]
                st.session_state.ord_df = pd.concat(frames, ignore_index=True)
            else:
                st.session_state.ord_df = None

        STORE_DEFS = [("CC", "🚴 Cycling Store"), ("RR", "🏃 Running Store")]

        for store_code, store_label in STORE_DEFS:
            st.markdown(f"**{store_label} ({store_code})**")
            c1, c2, c3 = st.columns([5, 5, 1])

            with c1:
                st.caption("Inventory Export — Admin → Products → Inventory → Export")
                inv_file = st.file_uploader(
                    f"inv_{store_code}", type=["csv"],
                    key=f"inv_upload_{store_code}", label_visibility="collapsed"
                )
                if inv_file:
                    try:
                        df = parse_inventory(inv_file)
                        warns = validate_inventory_file(df)
                        for w in warns: st.warning(w)
                        if not warns:
                            st.session_state.inv_store[store_code] = df
                            _rebuild_combined()
                            st.success(f"✅ {df['SKU'].nunique():,} SKUs")
                    except Exception as e:
                        st.error(f"Error: {e}")
                elif store_code in st.session_state.inv_store:
                    n = st.session_state.inv_store[store_code]["SKU"].nunique()
                    st.success(f"✅ Loaded — {n:,} SKUs")

            with c2:
                st.caption("Orders Export — Admin → Orders → Export")
                ord_file = st.file_uploader(
                    f"ord_{store_code}", type=["csv"],
                    key=f"ord_upload_{store_code}", label_visibility="collapsed"
                )
                if ord_file:
                    try:
                        df = parse_orders(ord_file)
                        warns = validate_orders_file(df)
                        for w in warns: st.warning(w)
                        if not warns:
                            st.session_state.ord_store[store_code] = df
                            _rebuild_combined()
                            st.success(f"✅ {df['Order_ID'].nunique():,} orders")
                    except Exception as e:
                        st.error(f"Error: {e}")
                elif store_code in st.session_state.ord_store:
                    o = st.session_state.ord_store[store_code]["Order_ID"].nunique()
                    st.success(f"✅ Loaded — {o:,} orders")

            with c3:
                st.caption(" ")
                has_data = (store_code in st.session_state.inv_store
                            or store_code in st.session_state.ord_store)
                if st.button("🗑", key=f"clear_{store_code}",
                             help=f"Clear {store_code} data",
                             disabled=not has_data):
                    st.session_state.inv_store.pop(store_code, None)
                    st.session_state.ord_store.pop(store_code, None)
                    _rebuild_combined()
                    st.rerun()

            st.divider()

    inv_df = st.session_state.inv_df
    ord_df = st.session_state.ord_df

    if inv_df is None and ord_df is None:
        st.info("Upload at least one file above to see the dashboard.")
        st.stop()

    # Store filter — shown when both stores have data
    loaded_stores = list(st.session_state.inv_store.keys() or st.session_state.ord_store.keys())
    STORE_LABELS  = {"CC": "🚴 Cycling (CC)", "RR": "🏃 Running (RR)"}
    store_options = ["All Stores"] + [STORE_LABELS.get(s, s) for s in loaded_stores]
    store_code_map = {STORE_LABELS.get(s, s): s for s in loaded_stores}

    if len(loaded_stores) > 1:
        sel_store_label = st.selectbox("📍 View store", store_options, key="dash_store_filter")
        sel_store = store_code_map.get(sel_store_label)  # None = All
    else:
        sel_store = loaded_stores[0] if loaded_stores else None
        sel_store_label = STORE_LABELS.get(sel_store, "All Stores")

    # Apply store filter to working dataframes
    def _filter_store(df, store_code):
        if df is None or store_code is None:
            return df
        return df[df["Store"] == store_code].copy() if "Store" in df.columns else df

    inv_view = _filter_store(inv_df, sel_store) if sel_store else inv_df
    ord_view = _filter_store(ord_df, sel_store) if sel_store else ord_df

    # ── SECTION 1: INVENTORY BY LOCATION ──────────────────────────────────
    if inv_view is not None:
        st.markdown("---")
        st.markdown("### 📦 Shopify Inventory — Stock by Location")
        st.caption(
            "Source: Shopify Inventory Export. "
            "Physical warehouse count not yet uploaded — discrepancy comparison not available."
        )

        loc_df, grand_total = _loc_stats(inv_view)

        # One KPI card per active location
        cols = st.columns(len(loc_df))
        for i, row in loc_df.iterrows():
            with cols[i]:
                st.metric(
                    label=f"📍 {row['Location']}",
                    value=f"{row['pct_total']:.1f}%",
                    help=f"On Hand: {int(row['On_Hand']):,} units of {int(grand_total):,} total",
                )
                st.caption(
                    f"Available: **{row['pct_available']:.1f}%**  \n"
                    f"Committed: **{row['pct_committed']:.1f}%**  \n"
                    f"Incoming: **{int(row['Incoming']):,} units**"
                )

        # Summary table
        display = loc_df.copy()
        display["% of Total"]  = display["pct_total"].round(1).astype(str) + "%"
        display["% Available"] = display["pct_available"].round(1).astype(str) + "%"
        display["% Committed"] = display["pct_committed"].round(1).astype(str) + "%"
        st.dataframe(
            display[["Location","On_Hand","% of Total","Available","% Available",
                      "Committed","% Committed","Incoming"]]
            .rename(columns={"On_Hand":"On Hand"}),
            use_container_width=True, hide_index=True,
        )

        st.info(
            "ℹ️ **Discrepancy analysis** requires the physical warehouse count files "
            "(Cycling Store, Running Store, Warehouse). Upload those to compare "
            "Shopify stock against real on-hand counts."
        )

    # ── SECTION 2: ORDERS ─────────────────────────────────────────────────
    if ord_view is not None:
        st.markdown("---")
        st.markdown("### 🚚 Orders")

        summary = orders_summary(ord_view)
        total   = summary["total_orders"]

        c1, c2, c3, c4 = st.columns(4)
        kpi(c1, "Total Orders", f"{total:,}")
        kpi(c2, "✅ Fulfilled",
            f"{summary['fulfilled']:,}",
            delta=f"{round(summary['fulfilled']/total*100,1)}% of orders",
            delta_color="off")
        kpi(c3, "⏳ Unfulfilled",
            f"{summary['unfulfilled']:,}",
            delta="paid · not shipped" if summary["unfulfilled"] else None,
            delta_color="inverse" if summary["unfulfilled"] else "off")
        kpi(c4, "🔀 Partial", f"{summary['partial']:,}")

        # In-transit coverage banner — compute here so it shows in summary row
        _pos_transit = [p for p in st.session_state.pos if p.get("status") == "In Transit"]
        _transit_qty = {}
        for _p in _pos_transit:
            for _s in _p.get("skus", []):
                _k = _s["sku"].strip().upper()
                _transit_qty[_k] = _transit_qty.get(_k, 0) + int(_s.get("qty", 0))

        if _transit_qty and inv_view is not None:
            _fulf_preview = check_fulfillability(ord_view, inv_view)
            _cant         = _fulf_preview[~_fulf_preview["Can_Fulfill"]].copy()
            _cant["_up"]  = _cant["SKU"].astype(str).str.strip().str.upper()
            # Covered = transit qty >= gap needed
            _n_covered = int(_cant.apply(
                lambda r: _transit_qty.get(r["_up"], 0) >= r["Gap"], axis=1
            ).sum())
            if _n_covered:
                st.info(
                    f"🚚 **{_n_covered} open order line(s)** cannot be filled today "
                    f"but have sufficient SKU quantity arriving in an **In Transit PO**. "
                    f"See details in *Can We Fulfill Open Orders?* below."
                )

        c1, c2, c3, c4 = st.columns(4)
        kpi(c1, "Avg Processing Time",
            f"{summary['avg_processing_hrs']} hrs",
            help="Created At → Fulfilled At, fulfilled orders only")
        kpi(c2, "Fastest",  f"{summary['min_processing_hrs']} hrs")
        kpi(c3, "Slowest",  f"{summary['max_processing_hrs']} hrs")
        kpi(c4, "Refunded / Cancelled",
            f"{summary['refunded']} / {summary['cancelled']}")

        # Fulfillability — only when both files are present
        if inv_view is not None:
            st.markdown("---")
            st.markdown("### 🎯 Can We Fulfill Open Orders?")
            st.caption("Checks Shopify available stock against each open order line item")

            fulf        = check_fulfillability(ord_view, inv_view)
            total_lines = len(fulf)
            can         = int(fulf["Can_Fulfill"].sum())
            cannot      = total_lines - can
            pct_can     = round(can / total_lines * 100, 1) if total_lines else 0

            # In-transit coverage: unfulfillable lines whose SKU has ENOUGH qty in transit POs
            # Build SKU → total units in transit (sum across all In Transit POs)
            pos_in_transit = [p for p in st.session_state.pos if p.get("status") == "In Transit"]
            transit_qty = {}   # SKU (upper) → total ordered units in transit
            for p in pos_in_transit:
                for s in p.get("skus", []):
                    key = s["sku"].strip().upper()
                    transit_qty[key] = transit_qty.get(key, 0) + int(s.get("qty", 0))

            cant_df = fulf[~fulf["Can_Fulfill"]].copy()
            cant_df["_sku_up"] = cant_df["SKU"].astype(str).str.strip().str.upper()

            def _transit_status(row):
                in_t = transit_qty.get(row["_sku_up"], 0)
                if in_t == 0:
                    return "—", False
                elif in_t >= row["Gap"]:
                    return f"🚚 Yes ({in_t} units)", True
                else:
                    return f"⚠️ Partial ({in_t}/{row['Gap']} units)", False

            cant_df[["Transit_Status","_covered"]] = cant_df.apply(
                lambda r: pd.Series(_transit_status(r)), axis=1
            )
            n_covered = int(cant_df["_covered"].sum())

            c1, c2, c3, c4, c5 = st.columns(5)
            kpi(c1, "Open Lines",          f"{total_lines:,}")
            kpi(c2, "✅ Stock Sufficient",  f"{can:,}",
                delta=f"{pct_can}%", delta_color="off")
            kpi(c3, "❌ Stock Insufficient",f"{cannot:,}",
                delta=f"{round(100-pct_can,1)}%",
                delta_color="inverse" if cannot else "off")
            kpi(c4, "🚚 Coverable by PO in Transit", f"{n_covered:,}",
                delta=f"of {cannot} short lines",
                delta_color="off",
                help="Unfulfillable lines whose SKU appears in at least one In Transit PO")
            kpi(c5, "Total Units Short",   f"{int(fulf['Gap'].sum()):,}",
                help="Sum of missing units across all unfulfillable lines")

            if not cant_df.empty:
                with st.expander(f"❌ {len(cant_df)} lines that cannot be fulfilled with current stock"):
                    show = cant_df[["Order_ID","SKU","Item_Name","Qty_Ordered",
                                    "Available_Stock","Gap","Financial_Status","Transit_Status"]].copy()
                    show.columns = ["Order ID","SKU","Item","Qty Ordered",
                                    "In Stock","Gap","Financial Status","In Transit PO"]
                    st.dataframe(show, use_container_width=True, hide_index=True)

            can_df = fulf[fulf["Can_Fulfill"]].sort_values("Order_ID")
            if not can_df.empty:
                with st.expander(f"✅ {len(can_df)} lines ready to ship"):
                    st.dataframe(
                        can_df[["Order_ID","SKU","Item_Name","Qty_Ordered",
                                "Available_Stock","Financial_Status"]],
                        use_container_width=True, hide_index=True,
                    )

        with st.expander("📋 All orders"):
            order_level = ord_view.drop_duplicates("Order_ID")[[
                "Order_ID","Financial_Status","Fulfillment_Status",
                "Created_At","Fulfilled_At","Subtotal","Total",
                "Shipping_Method","Vendor",
            ]].copy()
            order_level["Created_At"]   = order_level["Created_At"].dt.strftime("%Y-%m-%d %H:%M")
            order_level["Fulfilled_At"] = order_level["Fulfilled_At"].dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(order_level, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: INVENTORY CONTROL
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📦 Inventory Control":
    st.title("📦 Inventory Control")

    tab1, tab2 = st.tabs(["📊 Inventory by Location", "📥 Receive PO"])

    # ── TAB 1: INVENTORY DETAIL ───────────────────────────────────────────
    with tab1:
        inv_df = st.session_state.inv_df

        if inv_df is None:
            st.info("No inventory file loaded. Upload it from the Dashboard.")
        else:
            st.markdown("#### Shopify Inventory — Detail by Location, grouped by Product")

            loc_df, grand_total = _loc_stats(inv_view)
            active_locs = loc_df["Location"].tolist()
            selected_loc = st.selectbox("Location", ["All Locations"] + active_locs)

            filtered = (
                inv_df.copy() if selected_loc == "All Locations"
                else inv_df[inv_df["Location"] == selected_loc].copy()
            )

            # Group by Title
            by_title = filtered.groupby("Title").agg(
                Variants  =("SKU",       "nunique"),
                On_Hand   =("On_Hand",   "sum"),
                Available =("Available", "sum"),
                Committed =("Committed", "sum"),
                Incoming  =("Incoming",  "sum"),
            ).reset_index().sort_values("On_Hand", ascending=False)

            loc_total = by_title["On_Hand"].sum()

            by_title["% of Loc"]   = (by_title["On_Hand"] / loc_total * 100
                                      ).round(1).astype(str) + "%" if loc_total else "0%"
            by_title["% Avail"]    = (by_title["Available"] /
                                      by_title["On_Hand"].replace(0, 1) * 100
                                      ).round(1).astype(str) + "%"
            by_title["% Commit"]   = (by_title["Committed"] /
                                      by_title["On_Hand"].replace(0, 1) * 100
                                      ).round(1).astype(str) + "%"

            # Summary KPIs
            c1, c2, c3, c4 = st.columns(4)
            kpi(c1, "Products",       f"{len(by_title):,}")
            kpi(c2, "Total On Hand",  f"{int(loc_total):,} units")
            kpi(c3, "Total Available",f"{int(by_title['Available'].sum()):,} units")
            kpi(c4, "Total Committed",f"{int(by_title['Committed'].sum()):,} units")

            has_stock = by_title[by_title["On_Hand"] > 0]
            no_stock  = by_title[by_title["On_Hand"] == 0]
            st.caption(
                f"**{len(has_stock)}** products with stock · "
                f"**{len(no_stock)}** with no stock in this location"
            )

            search = st.text_input("🔍 Filter by product name",
                                   placeholder="e.g. Jersey, Bib, Sock...")
            if search:
                has_stock = has_stock[
                    has_stock["Title"].str.contains(search, case=False, na=False)
                ]

            st.dataframe(
                has_stock[[
                    "Title","Variants","On_Hand","% of Loc",
                    "Available","% Avail","Committed","% Commit","Incoming"
                ]].rename(columns={"On_Hand":"On Hand"}),
                use_container_width=True, hide_index=True,
            )

            # Variant drill-down
            st.divider()
            st.markdown("#### Variant detail")
            title_list = has_stock["Title"].tolist()
            if title_list:
                sel_title = st.selectbox("Select product", title_list)
                variant_df = inv_df[inv_df["Title"] == sel_title] if selected_loc == "All Locations" \
                    else inv_df[(inv_df["Title"] == sel_title) & (inv_df["Location"] == selected_loc)]

                show_cols = [
                    "SKU",
                    "Option1_Name","Option1_Value",
                    "Option2_Name","Option2_Value",
                    "Option3_Name","Option3_Value",
                    "Location","On_Hand","Available","Committed","Incoming",
                ]
                # Only include Option columns that have data
                opt_cols = [c for c in show_cols if c.startswith("Option")]
                non_empty_opts = [c for c in opt_cols
                                  if variant_df[c].astype(str).str.strip().replace("nan","").any()]
                final_cols = ["SKU"] + non_empty_opts + \
                             ["Location","On_Hand","Available","Committed","Incoming"]
                st.dataframe(
                    variant_df[final_cols].rename(columns={"On_Hand":"On Hand"}),
                    use_container_width=True, hide_index=True,
                )

    # ── TAB 2: RECEIVE PO ─────────────────────────────────────────────────
    with tab2:
        st.markdown("#### Inbound Purchase Orders")
        st.caption("Read-only · Shopify API not connected · Sorted by ETA")

        pos_all = st.session_state.pos
        if not pos_all:
            st.info("No POs registered yet. Create one in **PO Tracker → Create PO**.")
        else:
            # Build open-orders cross-reference from orders export
            ord_df2 = st.session_state.ord_df
            sku_to_open = {}   # SKU (upper) → [{order, item, qty}]
            if ord_df2 is not None:
                open_lines = ord_df2[
                    ord_df2["Fulfillment_Status"].isin(["unfulfilled","partial",""])
                ][["Order_ID","SKU","Qty_Ordered","Item_Name"]].copy()
                open_lines["SKU"] = open_lines["SKU"].astype(str).str.strip()
                open_lines = open_lines[
                    open_lines["SKU"].ne("") & open_lines["SKU"].ne("nan") & open_lines["SKU"].ne("None")
                ]
                for _, row in open_lines.iterrows():
                    key = str(row["SKU"]).upper()
                    sku_to_open.setdefault(key, []).append({
                        "order": row["Order_ID"],
                        "item":  str(row["Item_Name"])[:50],
                        "qty":   int(row["Qty_Ordered"]),
                    })

            # Sort by ETA
            def _eta_sort(po):
                try:
                    return datetime.strptime(po["eta"], "%Y-%m-%d")
                except Exception:
                    return datetime.max

            status_filter = st.selectbox(
                "Filter by status", ["All","In Transit","Received","Cancelled"],
                key="recv_filter"
            )
            filtered_pos = sorted(
                [p for p in pos_all
                 if status_filter == "All" or p["status"] == status_filter],
                key=_eta_sort
            )

            if not filtered_pos:
                st.info(f"No POs with status '{status_filter}'.")
            else:
                for po in filtered_pos:
                    icon = {"In Transit":"🚚","Received":"✅","Cancelled":"❌"}.get(po["status"],"📋")

                    # Days until ETA
                    days_label = ""
                    try:
                        delta = (datetime.strptime(po["eta"],"%Y-%m-%d").date() - date.today()).days
                        if delta > 0:   days_label = f" · **{delta}d away**"
                        elif delta == 0: days_label = " · **Arriving today**"
                        else:            days_label = f" · **{abs(delta)}d overdue**"
                    except Exception:
                        pass

                    # Cross-reference: which open orders need SKUs from this PO
                    po_skus = {s["sku"].strip().upper() for s in po.get("skus", [])}
                    matched = []
                    for sku in po_skus:
                        for entry in sku_to_open.get(sku, []):
                            matched.append({**entry, "sku": sku})

                    with st.container(border=True):
                        c1, c2, c3 = st.columns([3, 3, 2])
                        c1.markdown(
                            f"{icon} **{po['id']}** · {po['brand']}"
                            + (f"\n\nPO#: `{po['po_number']}`"
                               if po.get("po_number","—") != "—" else "")
                        )
                        c2.markdown(
                            f"📅 ETA: **{po['eta']}**{days_label}  \n"
                            f"📍 {po.get('location','—')}  \n"
                            + (f"🚛 {po['ship_via']}"
                               if po.get("ship_via","—") != "—" else "")
                        )
                        c3.markdown(
                            f"Status: **{po['status']}**  \n"
                            f"Lines: **{len(po.get('skus',[]))}**  \n"
                            f"Created: {po['created']}"
                        )

                        # Alert banner if open orders waiting for this PO
                        if matched:
                            st.warning(
                                f"🔔 **{len(matched)} open order line(s) need items from this PO** — "
                                f"these orders can be fulfilled once this shipment arrives."
                            )

                        # Line items table with open-order tags
                        if po.get("skus"):
                            with st.expander(f"📋 {len(po['skus'])} line items"):
                                sku_df = pd.DataFrame(po["skus"]).rename(
                                    columns={"sku":"SKU","desc":"Description","qty":"Qty Ordered"}
                                )
                                def _tag(sku):
                                    hits = sku_to_open.get(sku.strip().upper(), [])
                                    return f"🔔 {len(hits)} order(s) waiting" if hits else "—"
                                sku_df["Open Orders"] = sku_df["SKU"].apply(_tag)
                                st.dataframe(sku_df, use_container_width=True, hide_index=True)

                        # Open orders detail
                        if matched:
                            with st.expander(
                                f"🔔 Open orders waiting for items in this PO ({len(matched)} lines)"
                            ):
                                st.caption(
                                    "These unfulfilled orders require SKUs arriving in this shipment. "
                                    "Once received, they can be picked and shipped."
                                )
                                mo_df = pd.DataFrame(matched)[["order","sku","item","qty"]]
                                mo_df.columns = ["Order ID","SKU","Item","Qty Needed"]
                                st.dataframe(mo_df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: PO TRACKER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 PO Tracker":
    st.title("📋 PO Tracker")
    tab1, tab2 = st.tabs(["➕ Create PO", "📄 All POs"])

    # ── INVOICE EXTRACTION — local only, no external APIs ────────────────
    SKU_KW  = ["sku","article","ref","item#","item code","code","código","referencia","part","artículo"]
    DESC_KW = ["description","descripcion","descripción","name","nombre","product","detail","concepto","titulo","title"]
    QTY_KW  = ["qty","quantity","cantidad","units","piezas","pcs","ordered","order qty","cant"]
    JUNK    = {"nan","none","null","","#","no.","#ref!"}

    def _find_col(headers_lower, kw_list):
        """Return index of first header matching any keyword."""
        for kw in kw_list:
            for j, h in enumerate(headers_lower):
                if kw in h:
                    return j
        return None

    def _clean_qty(val):
        try:
            return max(1, int(float(str(val).replace(",","").strip())))
        except Exception:
            return 1

    def _parse_table(table):
        """Parse a pdfplumber/excel table into [{SKU, Description, Qty}]."""
        if not table or len(table) < 2:
            return []
        headers = [str(h).lower().strip() if h else "" for h in table[0]]
        si = _find_col(headers, SKU_KW)
        di = _find_col(headers, DESC_KW)
        qi = _find_col(headers, QTY_KW)
        items = []
        for row in table[1:]:
            sku  = str(row[si]).strip() if si is not None and si < len(row) else ""
            desc = str(row[di]).strip() if di is not None and di < len(row) else ""
            qty  = _clean_qty(row[qi]) if qi is not None and qi < len(row) else 1
            if sku.lower() not in JUNK:
                items.append({"SKU": sku, "Description": desc, "Qty": qty})
        return items

    def _sniff_header_meta(text):
        """
        Scan raw PDF text for PO number, Ship Via, and brand clues.
        Returns dict with best guesses (empty strings if not found).
        """
        import re
        result = {"brand": "", "po_number": "", "ship_via": ""}
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        for line in lines[:30]:          # header is usually in first 30 lines
            ll = line.lower()
            if not result["po_number"]:
                m = re.search(r'(?:po|purchase order|order)[#:\s#nº]+([A-Z0-9\-]{4,20})', line, re.I)
                if m:
                    result["po_number"] = m.group(1).strip()
            if not result["ship_via"]:
                m = re.search(r'(?:ship via|via|carrier|transport)[:\s]+([A-Za-z\s]{3,20})', line, re.I)
                if m:
                    result["ship_via"] = m.group(1).strip()

        # Brand: first non-empty line that looks like a company name (short, no numbers)
        for line in lines[:10]:
            if 3 < len(line) < 50 and not any(c.isdigit() for c in line[:6]):
                result["brand"] = line
                break

        return result

    def extract_from_pdf(file_bytes):
        """
        Local PDF extraction using pdfplumber — no external APIs.

        Strategy (two-pass):
          1. Structured tables: if pdfplumber finds data-populated tables, parse them
             using column-header keyword matching.
          2. Text-line pass: for invoices where the table renders as free text (common
             in multi-column PDF layouts like ASSOS), detect item lines by:
               a. Line starts with an article code (must contain a dot to filter noise).
               b. Line contains a quantity + unit keyword (Pcs / EA / Units / each).

        Meta extraction:
          - Brand  : right-hand side of "Banking Info:" header line.
          - Invoice : pattern INV/XX/0000 or first alphanumeric document-number block.
          - Cust PO : "Customer PO No." field.
          - Ship Via: scan lines after "Ship Via:" for known carrier keywords.

        Returns: {"brand", "po_number", "ship_via", "items": [{SKU, Description, Qty}]}
        """
        import pdfplumber, io, re

        # Article code: starts alphanumeric, must contain at least one dot
        # (rules out plain words like "Series", "Total", etc.)
        ARTICLE_START = re.compile(r'^([A-Z0-9][A-Z0-9\.\-_]{5,30})\s+', re.I)
        HAS_DOT       = re.compile(r'\.')
        QTY_UNIT      = re.compile(r'\b(\d+)\s+(?:Pcs|EA|Units?|Each)\b', re.I)

        # Footer lines that signal end of item section
        FOOTER_RE = re.compile(
            r'^(Net Total|Discount|Shipping|GST|PST|Total\b|Whs Policy|Thank you)',
            re.I
        )
        # Known table column headers that mark start of item section
        ITEM_HEADER_RE = re.compile(
            r'(Article|SKU|Item|Ref)\s+(Colour|Color|Description|Desc)',
            re.I
        )

        # Meta patterns
        BRAND_RE   = re.compile(r'Banking Info:\s*(.+)',          re.I)
        INV_RE     = re.compile(r'\b(INV/[A-Z]+/\d+)\b',         re.I)
        CUST_PO_RE = re.compile(r'Customer PO No[.\s:]+([A-Za-z0-9_\-]+)', re.I)
        CARRIERS   = ["UPS","DHL","FedEx","Fedex","Canada Post","Purolator","USPS","TNT","Canpar"]

        full_text = ""
        items_text = []   # items found via text pass
        items_table = []  # items found via table pass

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                txt   = page.extract_text() or ""
                full_text += txt + "\n"
                lines = txt.splitlines()

                # ── Pass 1: structured tables ──────────────────────────
                for table in page.extract_tables():
                    parsed = _parse_table(table)
                    items_table.extend(parsed)

                # ── Pass 2: text lines ─────────────────────────────────
                in_items = False
                for line in lines:
                    if ITEM_HEADER_RE.search(line):
                        in_items = True
                        continue
                    if not in_items:
                        continue
                    if FOOTER_RE.match(line):
                        in_items = False
                        continue

                    m_start = ARTICLE_START.match(line)
                    if m_start:
                        code = m_start.group(1)
                        if not HAS_DOT.search(code):   # must have dot to be valid code
                            continue
                        rest  = line[m_start.end():]
                        m_qty = QTY_UNIT.search(rest)
                        qty   = int(m_qty.group(1)) if m_qty else 1
                        desc  = rest[:m_qty.start()].strip() if m_qty else rest.strip()
                        items_text.append({"SKU": code, "Description": desc, "Qty": qty})

        # Prefer table items if found (more structured); otherwise use text pass
        raw_items = items_table if items_table else items_text

        # Deduplicate by SKU (keep first occurrence)
        seen, items = set(), []
        for it in raw_items:
            key = it["SKU"].strip().lower()
            if key and key not in seen:
                seen.add(key)
                items.append({"SKU": it["SKU"], "Description": it["Description"],
                              "Qty": it["Qty"]})

        # ── Meta ──────────────────────────────────────────────────────
        brand = ""
        m = BRAND_RE.search(full_text)
        if m:
            raw = m.group(1).strip()
            # Trim "GmbH" parent companies → use the cleaner brand token
            brand = re.split(r'\bGmbH\b', raw)[0].strip().rstrip(",").strip()

        po_number = ""
        m = INV_RE.search(full_text)
        if m:
            po_number = m.group(1)
        # Supplement with Customer PO No if available
        m2 = CUST_PO_RE.search(full_text)
        if m2 and not po_number:
            po_number = m2.group(1).strip()

        ship_via = ""
        all_lines = full_text.splitlines()
        ship_idx = next((i for i, l in enumerate(all_lines)
                         if re.search(r'Ship Via', l, re.I)), None)
        if ship_idx is not None:
            for l in all_lines[ship_idx: ship_idx + 6]:
                for carrier in CARRIERS:
                    m = re.search(rf'({re.escape(carrier)}[\w\s]{{0,12}})', l, re.I)
                    if m:
                        # Stop at 3+ consecutive spaces (signals next column)
                        raw_sv = re.split(r'\s{3,}|\bPO\b|\bBox\b|\bRemit\b', m.group(1), flags=re.I)[0]
                        ship_via = raw_sv.strip()
                        break
                if ship_via:
                    break

        return {"brand": brand, "po_number": po_number,
                "ship_via": ship_via, "items": items}

    def extract_from_excel(file_bytes, filename):
        """Extract line items from Excel or CSV invoice — local, no API."""
        import io
        df = pd.read_csv(io.BytesIO(file_bytes)) if filename.endswith(".csv") \
             else pd.read_excel(io.BytesIO(file_bytes))

        def find_col(kw_list):
            for c in df.columns:
                if any(k in c.lower() for k in kw_list):
                    return c
            return None

        sku_col  = find_col(SKU_KW)
        desc_col = find_col(DESC_KW)
        qty_col  = find_col(QTY_KW)

        items = []
        for _, row in df.iterrows():
            sku  = str(row[sku_col]).strip()  if sku_col  else ""
            desc = str(row[desc_col]).strip() if desc_col else ""
            qty  = _clean_qty(row[qty_col])   if qty_col  else 1
            if sku.lower() not in JUNK:
                items.append({"SKU": sku, "Description": desc, "Qty": qty})

        return {"brand":"", "po_number":"", "ship_via":"", "items": items}

    # ── TAB 1: CREATE PO ─────────────────────────────────────────────────
    with tab1:

        # ── Confirmation banner — shown immediately after publish ──────
        if st.session_state.get("po_published"):
            pub = st.session_state.po_published
            st.success(
                f"✅ **PO added** — `{pub['id']}` · {pub['brand']} · "
                f"{pub['lines']} items · now visible in **Receive PO**."
            )
            st.markdown(f"""
| Field | Value |
|---|---|
| PO ID | `{pub['id']}` |
| Brand | {pub['brand']} |
| ETA | {pub['eta']} |
| Destination | {pub['location']} |
| Line items | {pub['lines']} |
| Ship Via | {pub.get('ship_via','—')} |
""")
            if st.button("➕ Create another PO", type="primary"):
                st.session_state.po_published = None
                st.rerun()
            st.stop()   # ← nothing below renders while confirmation is visible

        st.markdown("#### New Purchase Order")

        # ── STEP 1: Upload invoice ─────────────────────────────────────
        st.markdown("**Step 1 — Upload invoice** *(PDF, Excel, or CSV)*")
        invoice_file = st.file_uploader(
            "invoice", type=["pdf","xlsx","xls","csv"],
            key="invoice_upload", label_visibility="collapsed",
        )

        if invoice_file and "invoice_extracted" not in st.session_state:
            fname      = invoice_file.name.lower()
            file_bytes = invoice_file.read()

            with st.spinner("Reading invoice..."):
                try:
                    result = extract_from_pdf(file_bytes) if fname.endswith(".pdf") \
                             else extract_from_excel(file_bytes, fname)

                    st.session_state.invoice_extracted = result
                    if result["items"]:
                        st.session_state.po_items = [
                            {"SKU": it["SKU"], "Description": it["Description"], "Qty": it["Qty"]}
                            for it in result["items"]
                        ]
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not read invoice: {e}")

        # Show extraction result banner
        if "invoice_extracted" in st.session_state:
            result = st.session_state.invoice_extracted
            n = len(result.get("items", []))
            if n:
                st.success(f"✅ Extracted **{n} line items** from invoice. Review and edit below.")
            else:
                st.warning("⚠️ No line items detected automatically. Fill them in manually.")

            if st.button("🗑 Clear invoice / start over"):
                for k in ["invoice_extracted"]:
                    st.session_state.pop(k, None)
                st.session_state.po_items = [{"SKU":"","Description":"","Qty":1}]
                st.rerun()

        st.divider()

        # ── STEP 2: Header fields ──────────────────────────────────────
        st.markdown("**Step 2 — Order details**")

        extracted = st.session_state.get("invoice_extracted", {})

        c1, c2 = st.columns(2)
        brand    = c1.text_input("Brand / Vendor *",
                                  value=extracted.get("brand",""),
                                  placeholder="e.g. Specialized, MAAP")
        supplier = c2.text_input("Distributor",
                                  placeholder="optional")
        c1, c2 = st.columns(2)
        eta      = c1.date_input("Expected Arrival *", value=date.today())
        location = c2.selectbox("Destination *", SHOPIFY_LOCATIONS)

        # Optional fields
        with st.expander("Optional — PO Number, Ship Via, Tracking"):
            c1, c2, c3 = st.columns(3)
            po_number  = c1.text_input("PO Number",
                                        value=extracted.get("po_number",""),
                                        placeholder="e.g. PO-2026-001")
            ship_via   = c2.text_input("Ship Via",
                                        value=extracted.get("ship_via",""),
                                        placeholder="e.g. DHL, FedEx")
            tracking   = c3.text_input("Tracking Number", placeholder="optional")

        st.divider()

        # ── STEP 3: Line items ─────────────────────────────────────────
        st.markdown("**Step 3 — Review line items**")

        items = st.session_state.po_items
        header = st.columns([2, 5, 1, 0.5])
        header[0].caption("SKU / Article")
        header[1].caption("Description")
        header[2].caption("Qty")

        for i, item in enumerate(items):
            c1, c2, c3, c4 = st.columns([2, 5, 1, 0.5])
            items[i]["SKU"]         = c1.text_input("SKU",  value=item["SKU"],
                                                    key=f"po_sku_{i}",
                                                    placeholder="SKU",
                                                    label_visibility="collapsed")
            items[i]["Description"] = c2.text_input("Desc", value=item["Description"],
                                                    key=f"po_desc_{i}",
                                                    placeholder="Description",
                                                    label_visibility="collapsed")
            items[i]["Qty"]         = c3.number_input("Qty", value=item["Qty"],
                                                      key=f"po_qty_{i}",
                                                      min_value=1,
                                                      label_visibility="collapsed")
            if c4.button("🗑", key=f"del_{i}") and len(items) > 1:
                st.session_state.po_items.pop(i)
                st.rerun()

        if st.button("+ Add line"):
            st.session_state.po_items.append({"SKU":"","Description":"","Qty":1})
            st.rerun()

        st.divider()

        # ── PUBLISH ────────────────────────────────────────────────────
        # Show confirmation banner if a PO was just published
        if st.session_state.get("po_published"):
            pub = st.session_state.po_published
            st.success(
                f"✅ PO already added — **{pub['id']}** · {pub['brand']} · "
                f"{pub['lines']} items · visible in Inventory Control → Receive PO."
            )
            if st.button("➕ Create another PO"):
                st.session_state.po_published = None
                st.rerun()
            st.stop()

        valid_lines = [i for i in items if i["SKU"].strip()]
        if valid_lines:
            st.markdown(f"**Preview — {len(valid_lines)} line items ready to publish:**")
            st.dataframe(
                pd.DataFrame(valid_lines),
                use_container_width=True, hide_index=True,
            )

        if st.button("🚀 Publish PO", type="primary", disabled=(not brand or not valid_lines)):
            if not brand:
                st.error("Brand / Vendor is required.")
            elif not valid_lines:
                st.error("Add at least one line item with a SKU.")
            else:
                new_id = f"PO-{datetime.now().strftime('%Y%m%d')}-{len(st.session_state.pos)+1:03d}"
                st.session_state.pos.append({
                    "id":         new_id,
                    "brand":      brand,
                    "supplier":   supplier or "—",
                    "eta":        str(eta),
                    "location":   location,
                    "status":     "In Transit",
                    "created":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "po_number":  po_number or "—",
                    "ship_via":   ship_via or "—",
                    "tracking":   tracking or "—",
                    "skus": [
                        {"sku": i["SKU"], "desc": i["Description"], "qty": i["Qty"]}
                        for i in valid_lines
                    ],
                })
                # Store confirmation info, clear form
                st.session_state.po_published = {
                    "id":       new_id,
                    "brand":    brand,
                    "lines":    len(valid_lines),
                    "eta":      str(eta),
                    "location": location,
                    "ship_via": ship_via or "—",
                }
                st.session_state.po_items        = [{"SKU":"","Description":"","Qty":1}]
                st.session_state.pop("invoice_extracted", None)
                st.rerun()

    # ── TAB 2: ALL POs ────────────────────────────────────────────────────
    with tab2:
        st.markdown("#### Purchase Orders")
        if not st.session_state.pos:
            st.info("No POs yet. Create one in the tab above.")
        else:
            status_filter = st.selectbox("Filter", ["All","In Transit","Received","Cancelled"])
            filtered = (st.session_state.pos if status_filter == "All"
                        else [p for p in st.session_state.pos if p["status"] == status_filter])

            for po in filtered:
                icon = {"In Transit":"🚚","Received":"✅","Cancelled":"❌"}.get(po["status"],"📋")
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2,2,2,1])
                    c1.markdown(
                        f"**{po['id']}**  \n"
                        f"{po['brand']} · {po['supplier']}  \n"
                        + (f"PO#: `{po['po_number']}`" if po.get('po_number','—') != '—' else "")
                    )
                    c2.markdown(
                        f"**ETA:** {po['eta']}  \n**Dest:** {po['location']}  \n"
                        + (f"Ship Via: {po['ship_via']}" if po.get('ship_via','—') != '—' else "")
                    )
                    c3.markdown(
                        f"**Status:** {icon} {po['status']}  \n**Created:** {po['created']}  \n"
                        + (f"Tracking: `{po['tracking']}`" if po.get('tracking','—') != '—' else "")
                    )
                    c4.markdown(f"**Lines:** {len(po.get('skus',[]))}")
                    if po.get("skus"):
                        with st.expander("View items"):
                            st.dataframe(
                                pd.DataFrame(po["skus"]).rename(
                                    columns={"sku":"SKU","desc":"Description","qty":"Qty"}
                                ),
                                use_container_width=True, hide_index=True,
                            )
