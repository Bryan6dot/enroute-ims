import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Enroute IMS", page_icon="🚲", layout="wide", initial_sidebar_state="expanded")

USERS = {
    "admin":      {"password": "enroute2026", "role": "admin",      "name": "Admin"},
    "warehouse":  {"password": "wh2026",      "role": "warehouse",  "name": "Warehouse"},
    "purchasing": {"password": "po2026",      "role": "purchasing", "name": "Purchasing"},
    "store1":     {"password": "s1cycling",   "role": "store",      "name": "Store 1 · Cycling"},
    "store2":     {"password": "s2running",   "role": "store",      "name": "Store 2 · Running"},
}

INVENTORY = {
    "TRK-FX3-L":  {"desc": "Trek FX3 Disc Large",         "Central": 12, "Store1": 2, "Store2": 0},
    "TRK-FX3-M":  {"desc": "Trek FX3 Disc Medium",        "Central": 8,  "Store1": 3, "Store2": 1},
    "TRK-FX3-S":  {"desc": "Trek FX3 Disc Small",         "Central": 5,  "Store1": 1, "Store2": 0},
    "SHM-XT-M8":  {"desc": "Shimano XT M8100 Derailleur", "Central": 2,  "Store1": 0, "Store2": 1},
    "ASS-GEL-P":  {"desc": "Gel Saddle Pro",               "Central": 8,  "Store1": 3, "Store2": 2},
    "HELM-GV-M":  {"desc": "Giro Vantage Helmet M",        "Central": 0,  "Store1": 4, "Store2": 1},
    "HELM-GV-L":  {"desc": "Giro Vantage Helmet L",        "Central": 3,  "Store1": 1, "Store2": 0},
    "RUN-NK-9":   {"desc": "Nike Pegasus 9",               "Central": 15, "Store1": 0, "Store2": 6},
    "RUN-BK-GT":  {"desc": "Brooks Ghost 16",              "Central": 10, "Store1": 0, "Store2": 4},
    "ACC-PUMP-F": {"desc": "Topeak Floor Pump",            "Central": 6,  "Store1": 2, "Store2": 1},
}

LOCATIONS = ["Central / Warehouse", "Store 1 · Cycling", "Store 2 · Running"]

DEMO_POS = [
    {
        "id": "PO-2026-041", "brand": "Trek Bikes", "supplier": "QBP Distributor",
        "units": 24, "eta": "2026-04-08", "status": "In Transit", "location": "Central / Warehouse",
        "skus": [
            {"SKU": "TRK-FX3-L", "Description": "Trek FX3 Disc Large",  "Ordered": 4,  "Received": 0},
            {"SKU": "TRK-FX3-M", "Description": "Trek FX3 Disc Medium", "Ordered": 6,  "Received": 0},
            {"SKU": "TRK-FX3-S", "Description": "Trek FX3 Disc Small",  "Ordered": 4,  "Received": 0},
            {"SKU": "TRK-ACC",   "Description": "Trek Accessory Bundle", "Ordered": 10, "Received": 0},
        ],
    },
    {
        "id": "PO-2026-039", "brand": "Shimano", "supplier": "Shimano Direct",
        "units": 60, "eta": "2026-04-12", "status": "In Transit", "location": "Central / Warehouse",
        "skus": [
            {"SKU": "SHM-XT-M8", "Description": "Shimano XT M8100 Derailleur", "Ordered": 20, "Received": 0},
            {"SKU": "SHM-CS-M8", "Description": "Shimano CS-M8100 Cassette",   "Ordered": 40, "Received": 0},
        ],
    },
    {
        "id": "PO-2026-037", "brand": "Garmin", "supplier": "CDN Cycling Supply",
        "units": 15, "eta": "2026-04-18", "status": "In Transit", "location": "Central / Warehouse",
        "skus": [
            {"SKU": "GAR-530",  "Description": "Garmin Edge 530",  "Ordered": 5, "Received": 0},
            {"SKU": "GAR-1040", "Description": "Garmin Edge 1040", "Ordered": 5, "Received": 0},
            {"SKU": "GAR-HRM",  "Description": "Garmin HRM-Dual",  "Ordered": 5, "Received": 0},
        ],
    },
    {
        "id": "PO-2026-034", "brand": "Giro Helmets", "supplier": "Sport Systems",
        "units": 18, "eta": "2026-04-01", "status": "Received", "location": "Central / Warehouse",
        "skus": [
            {"SKU": "HELM-GV-M", "Description": "Giro Vantage Helmet M", "Ordered": 9, "Received": 9},
            {"SKU": "HELM-GV-L", "Description": "Giro Vantage Helmet L", "Ordered": 9, "Received": 9},
        ],
    },
]

STATUS_ICON = {"In Transit": "🔵", "Partially Received": "🟡", "Received": "🟢", "Discrepancy": "🔴"}

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("user_role"):
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
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
                st.session_state.page = "📊 Dashboard"
                st.rerun()
            else:
                st.error("Invalid credentials")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🚲 Enroute IMS")
    st.caption(f"**{st.session_state.user_name}**")
    st.caption(f"Role: {st.session_state.user_role}")
    st.divider()
    if "page" not in st.session_state:
        st.session_state.page = "📊 Dashboard"
    for p in ["📊 Dashboard", "📦 Inventory Control", "📋 PO Tracker"]:
        if st.button(p, use_container_width=True,
                     type="primary" if st.session_state.page == p else "secondary"):
            st.session_state.page = p
            st.session_state.pop("receiving_po", None)
            st.rerun()
    st.divider()
    if st.button("Sign Out", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

page = st.session_state.page

# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    low_stock   = sum(1 for v in INVENTORY.values() if v["Central"]+v["Store1"]+v["Store2"] < 5)
    pos_transit = sum(1 for p in DEMO_POS if p["status"] == "In Transit")
    stockouts   = sum(1 for v in INVENTORY.values() if v["Central"]+v["Store1"]+v["Store2"] == 0)
    best_seller = max(INVENTORY.items(), key=lambda x: x[1]["Central"]+x[1]["Store1"]+x[1]["Store2"])

    st.title("📊 Dashboard")
    st.caption(f"Signed in as **{st.session_state.user_name}** · Last sync: today 10:42 AM · Shopify live")
    st.divider()

    st.markdown("#### Key Indicators")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔴 Low Stock SKUs", str(low_stock), "+2 vs last week", delta_color="inverse",
              help="SKUs with fewer than 5 total units across all locations.")
    k2.metric("🚚 POs In Transit", str(pos_transit), "Next ETA: Apr 8",
              help="Confirmed Purchase Orders pending receipt at warehouse.")
    k3.metric("⚠️ Stockouts", str(stockouts), "SKUs at 0 units",
              delta_color="inverse", help="SKUs with zero units in all locations combined.")
    k4.metric("🏆 Top SKU", best_seller[0],
              f"{best_seller[1]['Central']+best_seller[1]['Store1']+best_seller[1]['Store2']} units",
              help="SKU with highest total units across all locations.")

    st.divider()
    st.markdown("#### Stock Distribution by Location")
    all_u     = sum(v["Central"]+v["Store1"]+v["Store2"] for v in INVENTORY.values())
    central_u = sum(v["Central"] for v in INVENTORY.values())
    store1_u  = sum(v["Store1"]  for v in INVENTORY.values())
    store2_u  = sum(v["Store2"]  for v in INVENTORY.values())
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**🏭 Central / Warehouse**")
        st.markdown(f"### {central_u} units")
        st.progress(central_u/all_u, text=f"{central_u/all_u*100:.1f}% of total stock")
        st.caption("Main location. Receives all POs and manages outbound shipments.")
    with c2:
        st.markdown("**🚲 Store 1 · Cycling**")
        st.markdown(f"### {store1_u} units")
        st.progress(store1_u/all_u, text=f"{store1_u/all_u*100:.1f}% of total stock")
        st.caption("Cycling specialty store. Floor inventory only.")
    with c3:
        st.markdown("**🏃 Store 2 · Running**")
        st.markdown(f"### {store2_u} units")
        st.progress(store2_u/all_u, text=f"{store2_u/all_u*100:.1f}% of total stock")
        st.caption("Running specialty store. Floor inventory only.")

    st.divider()
    left, right = st.columns(2)
    with left:
        st.markdown("#### ⚠️ Active Alerts")
        alerted = False
        for sku, data in INVENTORY.items():
            total = data["Central"]+data["Store1"]+data["Store2"]
            if total == 0:
                st.error(f"**{sku}** — {data['desc']}  |  STOCKOUT · 0 units")
                alerted = True
            elif total < 5:
                st.warning(f"**{sku}** — {data['desc']}  |  {total} units · Low stock")
                alerted = True
        if not alerted:
            st.success("No active alerts.")
        st.info("📦 **Trek Bikes PO-2026-041** — ETA Apr 8 · 24 units incoming")

    with right:
        st.markdown("#### 📦 Full Inventory — All Locations")
        rows = []
        for sku, data in INVENTORY.items():
            total = data["Central"]+data["Store1"]+data["Store2"]
            rows.append({
                "SKU": sku, "Description": data["desc"],
                "Central 🏭": data["Central"], "Store1 🚲": data["Store1"], "Store2 🏃": data["Store2"],
                "Total": total,
                "Status": "🔴 Stockout" if total==0 else ("🔴 Low" if total<5 else ("🟡 Watch" if total<10 else "🟢 OK")),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY CONTROL
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📦 Inventory Control":
    st.title("📦 Inventory Control")
    st.caption("Receive POs · Move inventory between locations · View current stock")
    st.divider()

    ic_tab1, ic_tab2, ic_tab3 = st.tabs(["📥 Receive PO", "🔄 Move Inventory", "📊 Current Stock"])

    # ── TAB 1: RECEIVE PO ────────────────────────────────────────────────────
    with ic_tab1:
        transit_pos = [p for p in DEMO_POS if p["status"] == "In Transit"]

        # Sub-state: are we inside a PO or on the list?
        if "receiving_po" not in st.session_state:
            st.session_state.receiving_po = None

        if st.session_state.receiving_po is None:
            # PO LIST
            st.markdown("#### Purchase Orders In Transit")
            st.caption("Select a PO to open the receiving workflow. Once confirmed, Shopify inventory updates automatically.")

            if not transit_pos:
                st.info("No POs currently in transit.")
            else:
                for po in transit_pos:
                    col_info, col_btn = st.columns([4, 1])
                    with col_info:
                        st.markdown(f"**{po['id']}** — {po['brand']}  ·  {po['supplier']}")
                        st.caption(f"ETA: {po['eta']}  ·  {po['units']} units  ·  Destination: {po['location']}")
                    with col_btn:
                        if st.button("Receive →", key=f"recv_btn_{po['id']}", type="primary", use_container_width=True):
                            st.session_state.receiving_po = po["id"]
                            st.rerun()
                    st.divider()
        else:
            # PO DETAIL — RECEIVING WORKFLOW
            po = next((p for p in DEMO_POS if p["id"] == st.session_state.receiving_po), None)
            if not po:
                st.session_state.receiving_po = None
                st.rerun()

            if st.button("← Back to PO list"):
                st.session_state.receiving_po = None
                st.rerun()

            st.markdown(f"## Receiving: {po['id']}")
            st.markdown(f"**{po['brand']}** · {po['supplier']}  |  ETA: {po['eta']}  |  Destination: {po['location']}")
            st.divider()

            # Download PO
            buf = io.BytesIO()
            pd.DataFrame(po["skus"]).to_excel(buf, index=False, engine="openpyxl")
            st.download_button(f"⬇ Download {po['id']}.xlsx", data=buf.getvalue(),
                               file_name=f"{po['id']}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            st.markdown("#### Validate received quantities against packing slip")
            st.caption("Review each line item. Adjust the 'Received' quantity if there are discrepancies.")

            df_recv = pd.DataFrame(po["skus"]).copy()
            edited = st.data_editor(
                df_recv,
                column_config={
                    "SKU":         st.column_config.TextColumn("SKU", disabled=True),
                    "Description": st.column_config.TextColumn("Description", disabled=True),
                    "Ordered":     st.column_config.NumberColumn("Ordered", disabled=True),
                    "Received":    st.column_config.NumberColumn("Received ✏️", min_value=0,
                                   help="Edit this column to match what was physically received"),
                },
                use_container_width=True,
                hide_index=True,
                key=f"editor_{po['id']}",
            )

            edited["Difference"] = edited["Received"] - edited["Ordered"]
            edited["Status"] = edited["Difference"].apply(
                lambda d: "✅ Complete" if d == 0 else ("⏳ Short" if d < 0 else "⚠️ Excess"))

            has_discrepancy = any(edited["Difference"] != 0)
            if has_discrepancy:
                st.warning("⚠️ Discrepancies detected. Review before confirming.")
            else:
                st.success("✅ All quantities match the PO.")

            st.dataframe(edited[["SKU", "Ordered", "Received", "Difference", "Status"]],
                         use_container_width=True, hide_index=True)

            st.divider()
            col_cancel, col_confirm = st.columns([1, 1])
            with col_cancel:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.receiving_po = None
                    st.rerun()
            with col_confirm:
                label = "Confirm & Update Shopify" if not has_discrepancy else "Confirm with discrepancies → Shopify"
                if st.button(label, type="primary", use_container_width=True):
                    st.error("🔌 Not connected to Shopify. Configure API credentials in `.streamlit/secrets.toml` to apply changes.")
                    st.code("""[shopify]
shop_url    = "your-store.myshopify.com"
admin_token = "shpat_xxxxxxxxxxxxxxxxxxxx" """, language="toml")

    # ── TAB 2: MOVE INVENTORY ────────────────────────────────────────────────
    with ic_tab2:
        st.markdown("#### Move Inventory Between Locations")
        st.caption("Select origin, destination, and items to move. Changes are applied in Shopify.")

        col_from, col_to = st.columns(2)
        with col_from:
            origin = st.selectbox("📤 From location", LOCATIONS, key="mv_from")
        with col_to:
            dest_options = [l for l in LOCATIONS if l != origin]
            destination  = st.selectbox("📥 To location", dest_options, key="mv_to")

        st.divider()
        move_method = st.radio("How do you want to specify items?",
                               ["🔍 Search by SKU (single or few items)",
                                "📄 Upload Excel (multiple items)"],
                               horizontal=True)

        if move_method.startswith("🔍"):
            loc_key = origin.split("/")[0].strip().split(" ")[0]
            loc_map = {"Central": "Central", "Store": "Store1" if "1" in origin else "Store2"}
            inv_key = "Central" if "Central" in origin else ("Store1" if "1" in origin else "Store2")

            search_term = st.text_input("Search SKU or description", placeholder="e.g. TRK-FX3 · Shimano · Helmet")
            matching = {
                sku: data for sku, data in INVENTORY.items()
                if (not search_term or search_term.upper() in sku.upper()
                    or search_term.lower() in data["desc"].lower())
                and data[inv_key] > 0
            }

            if search_term and not matching:
                st.warning(f"No SKUs found in **{origin}** matching '{search_term}'.")
            elif matching:
                st.caption(f"Available in **{origin}** · {len(matching)} SKU(s) found")
                selected_sku = st.selectbox(
                    "Select SKU to move",
                    options=list(matching.keys()),
                    format_func=lambda s: f"{s} — {matching[s]['desc']} ({matching[s][inv_key]} available)"
                )
                max_qty = matching[selected_sku][inv_key]
                qty = st.number_input(f"Quantity to move (max {max_qty})", min_value=1, max_value=max_qty, value=1)
                notes = st.text_input("Reference / Notes (optional)", placeholder="e.g. TRF-022")

                st.divider()
                st.markdown("**Movement Summary**")
                c1, c2, c3 = st.columns(3)
                c1.metric("SKU", selected_sku)
                c2.metric("Quantity", qty)
                c3.metric("Route", f"{origin.split('/')[0].strip()} → {destination.split('·')[0].strip()}")

                if st.button("🚀 Move → Shopify", type="primary"):
                    st.error("🔌 Not connected to Shopify. Configure API credentials to apply this movement.")
                    st.code("""[shopify]
shop_url    = "your-store.myshopify.com"
admin_token = "shpat_xxxxxxxxxxxxxxxxxxxx" """, language="toml")

        else:
            st.markdown("**Upload Excel with items to move**")
            tpl = pd.DataFrame([
                ["TRK-FX3-L", "Trek FX3 Disc Large", 2],
                ["SHM-XT-M8", "Shimano XT M8100",    4],
            ], columns=["SKU", "Description", "Quantity"])
            buf = io.BytesIO()
            tpl.to_excel(buf, index=False, engine="openpyxl")
            st.download_button("⬇ Download movement template", data=buf.getvalue(),
                               file_name="movement_template.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            uploaded = st.file_uploader("Upload Excel", type=["xlsx", "xls"])
            if uploaded:
                df = pd.read_excel(uploaded, engine="openpyxl")
                inv_key = "Central" if "Central" in origin else ("Store1" if "1" in origin else "Store2")
                statuses = []
                for _, row in df.iterrows():
                    sku = str(row.get("SKU", ""))
                    if sku not in INVENTORY:
                        statuses.append("❌ SKU not found")
                    elif INVENTORY[sku][inv_key] < int(row.get("Quantity", 0)):
                        statuses.append(f"⚠️ Insufficient stock ({INVENTORY[sku][inv_key]} available)")
                    else:
                        statuses.append("✅ Valid")
                df["Status"] = statuses

                st.markdown("**Preview**")
                st.dataframe(df, use_container_width=True, hide_index=True)

                valid = sum(1 for s in statuses if s.startswith("✅"))
                c1, c2 = st.columns(2)
                c1.metric("✅ Valid rows", valid)
                c2.metric("❌ Errors", len(statuses)-valid, delta_color="inverse")

                if valid > 0:
                    if st.button(f"🚀 Move {valid} items → Shopify", type="primary"):
                        st.error("🔌 Not connected to Shopify. Configure API credentials to apply this movement.")
                        st.code("""[shopify]
shop_url    = "your-store.myshopify.com"
admin_token = "shpat_xxxxxxxxxxxxxxxxxxxx" """, language="toml")

    # ── TAB 3: CURRENT STOCK ─────────────────────────────────────────────────
    with ic_tab3:
        st.markdown("#### Current Stock by Location")
        st.caption("Live data from Shopify Inventory API. Refreshed on every page load.")

        col_s, col_f = st.columns([2, 1])
        with col_s:
            search = st.text_input("🔍 Filter by SKU or description", placeholder="e.g. Trek · Shimano · RUN")
        with col_f:
            status_f = st.selectbox("Status filter", ["All", "🔴 Low / Stockout", "🟡 Watch", "🟢 OK"])

        rows = []
        for sku, data in INVENTORY.items():
            total  = data["Central"]+data["Store1"]+data["Store2"]
            status = "🔴 Stockout" if total==0 else ("🔴 Low" if total<5 else ("🟡 Watch" if total<10 else "🟢 OK"))
            if search and search.upper() not in sku.upper() and search.lower() not in data["desc"].lower():
                continue
            if status_f == "🔴 Low / Stockout" and "🔴" not in status:
                continue
            if status_f == "🟡 Watch" and status != "🟡 Watch":
                continue
            if status_f == "🟢 OK" and status != "🟢 OK":
                continue
            rows.append({"SKU": sku, "Description": data["desc"],
                         "Central 🏭": data["Central"], "Store1 🚲": data["Store1"], "Store2 🏃": data["Store2"],
                         "Total": total, "Status": status})
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption(f"Showing {len(rows)} of {len(INVENTORY)} active SKUs")
        else:
            st.info("No SKUs match the current filter.")

# ══════════════════════════════════════════════════════════════════════════════
# PO TRACKER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 PO Tracker":
    st.title("📋 PO Tracker")
    st.caption("Purchase Orders visibility for the purchasing team · Reception is handled in Inventory Control")
    st.divider()

    transit  = sum(1 for p in DEMO_POS if p["status"] == "In Transit")
    partial  = sum(1 for p in DEMO_POS if p["status"] == "Partially Received")
    received = sum(1 for p in DEMO_POS if p["status"] == "Received")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔵 In Transit",          transit)
    k2.metric("🟡 Partially Received",  partial)
    k3.metric("🟢 Fully Received",      received)
    k4.metric("📦 Total PO Units",      sum(p["units"] for p in DEMO_POS))
    st.divider()

    tab_list, tab_new = st.tabs(["📋 All POs", "➕ New PO"])

    STAGES    = ["PO Created", "Confirmed", "In Transit", "Reception", "Shopify ✓"]
    STAGE_IDX = {"In Transit": 2, "Partially Received": 3, "Received": 4}

    with tab_list:
        search   = st.text_input("🔍 Search by brand, supplier or PO #",
                                 placeholder="e.g. Trek · Shimano · PO-2026-041")
        status_f = st.selectbox("Filter by status", ["All", "In Transit", "Partially Received", "Received"])

        filtered = [
            p for p in DEMO_POS
            if (not search or search.lower() in p["brand"].lower()
                           or search.lower() in p["id"].lower()
                           or search.lower() in p["supplier"].lower())
            and (status_f == "All" or p["status"] == status_f)
        ]

        for po in filtered:
            icon = STATUS_ICON.get(po["status"], "⚪")
            with st.expander(
                f"{icon} **{po['id']}** — {po['brand']}  ·  {po['supplier']}  |  ETA: {po['eta']}  |  {po['status']}",
                expanded=(po["status"] != "Received"),
            ):
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Supplier",    po["supplier"])
                m2.metric("ETA",         po["eta"])
                m3.metric("Total Units", po["units"])
                m4.metric("Status",      po["status"])

                st.markdown("**PO Progress**")
                current  = STAGE_IDX.get(po["status"], 2)
                cols_tl  = st.columns(len(STAGES))
                for i, (col, stage) in enumerate(zip(cols_tl, STAGES)):
                    with col:
                        marker = "🟢" if i < current else ("🟡" if i == current else "⚪")
                        bold   = "**" if i <= current else ""
                        st.markdown(f"{marker} {bold}{stage}{bold}")

                st.divider()
                if po["skus"]:
                    df_sku = pd.DataFrame(po["skus"])
                    st.markdown("**Line Items**")
                    st.dataframe(df_sku, use_container_width=True, hide_index=True)
                    buf = io.BytesIO()
                    df_sku.to_excel(buf, index=False, engine="openpyxl")
                    st.download_button(f"⬇ Download {po['id']}.xlsx", data=buf.getvalue(),
                                       file_name=f"{po['id']}.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       key=f"dl_{po['id']}")

                if po["status"] == "In Transit":
                    st.info("📦 Reception is handled by warehouse in **Inventory Control → Receive PO**")

    with tab_new:
        if st.session_state.user_role not in ["purchasing", "admin"]:
            st.warning("⚠️ Only the purchasing team can create new POs.")
        else:
            st.markdown("#### Create New Purchase Order")
            st.caption("The PO will appear in Inventory Control for warehouse to receive once it arrives.")
            c1, c2 = st.columns(2)
            with c1:
                brand    = st.text_input("Brand / Vendor *",  placeholder="e.g. Trek Bikes")
                supplier = st.text_input("Distributor",        placeholder="e.g. QBP Distributor")
                location = st.selectbox("Destination Location *", LOCATIONS)
            with c2:
                eta   = st.date_input("Expected ETA *")
                notes = st.text_area("Notes for warehouse", height=100)
            st.markdown("**PO File**")
            st.caption("Attach the vendor PDF or Excel. Warehouse downloads it to validate against packing slip.")
            po_file = st.file_uploader("Upload PO file", type=["pdf", "xlsx", "xls"], key="new_po")
            if po_file:
                st.success(f"📎 File attached: `{po_file.name}` — {po_file.size:,} bytes")
            st.divider()
            if st.button("📤 Publish PO", type="primary"):
                if not brand:
                    st.error("Brand / Vendor is required.")
                elif not po_file:
                    st.error("Please attach the PO file before publishing.")
                else:
                    new_id = f"PO-2026-{len(DEMO_POS)+42:03d}"
                    st.success(f"""
                    ✅ **{new_id}** published successfully.
                    - Brand: **{brand}**  |  Distributor: **{supplier or '—'}**
                    - ETA: **{eta}**  |  Destination: **{location}**
                    - Warehouse will see this PO in **Inventory Control → Receive PO**.
                    """)
