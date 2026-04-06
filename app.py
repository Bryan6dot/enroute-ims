import streamlit as st
import pandas as pd
import io

st.set_page_config(
    page_title="Enroute IMS",
    page_icon="🚲",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Users ─────────────────────────────────────────────────────────────────────
USERS = {
    "admin":      {"password": "enroute2026", "role": "admin",      "name": "Admin"},
    "warehouse":  {"password": "wh2026",      "role": "warehouse",  "name": "Warehouse"},
    "purchasing": {"password": "po2026",      "role": "purchasing", "name": "Purchasing"},
    "store1":     {"password": "s1cycling",   "role": "store",      "name": "Store 1 · Cycling"},
    "store2":     {"password": "s2running",   "role": "store",      "name": "Store 2 · Running"},
}

# ── Demo data ─────────────────────────────────────────────────────────────────
INVENTORY = {
    "TRK-FX3-L":  {"desc": "Trek FX3 Disc Large",             "Central": 12, "Store1": 2, "Store2": 0},
    "TRK-FX3-M":  {"desc": "Trek FX3 Disc Medium",            "Central": 8,  "Store1": 3, "Store2": 1},
    "TRK-FX3-S":  {"desc": "Trek FX3 Disc Small",             "Central": 5,  "Store1": 1, "Store2": 0},
    "SHM-XT-M8":  {"desc": "Shimano XT M8100 Derailleur",     "Central": 2,  "Store1": 0, "Store2": 1},
    "ASS-GEL-P":  {"desc": "Gel Saddle Pro",                   "Central": 8,  "Store1": 3, "Store2": 2},
    "HELM-GV-M":  {"desc": "Giro Vantage Helmet M",            "Central": 0,  "Store1": 4, "Store2": 1},
    "HELM-GV-L":  {"desc": "Giro Vantage Helmet L",            "Central": 3,  "Store1": 1, "Store2": 0},
    "RUN-NK-9":   {"desc": "Nike Pegasus 9",                   "Central": 15, "Store1": 0, "Store2": 6},
    "RUN-BK-GT":  {"desc": "Brooks Ghost 16",                  "Central": 10, "Store1": 0, "Store2": 4},
    "ACC-PUMP-F": {"desc": "Topeak Floor Pump",                "Central": 6,  "Store1": 2, "Store2": 1},
}

MOVEMENTS = [
    {"Date": "2026-04-05", "Reference": "PO-2026-041", "Type": "inbound",  "Location": "Central",    "Units": "+18", "User": "warehouse"},
    {"Date": "2026-04-04", "Reference": "TRF-021",     "Type": "transfer", "Location": "Central→S1", "Units": "±6",  "User": "store1"},
    {"Date": "2026-04-03", "Reference": "ADJ-019",     "Type": "outbound", "Location": "Store 2",    "Units": "-3",  "User": "store2"},
    {"Date": "2026-04-02", "Reference": "PO-2026-038", "Type": "inbound",  "Location": "Central",    "Units": "+42", "User": "warehouse"},
    {"Date": "2026-04-01", "Reference": "TRF-020",     "Type": "transfer", "Location": "Central→S2", "Units": "±4",  "User": "store2"},
]

DEMO_POS = [
    {
        "id": "PO-2026-041", "brand": "Trek Bikes", "supplier": "QBP Distributor",
        "units": 24, "eta": "2026-04-08", "status": "In Transit",
        "location": "Central / Warehouse", "created_at": "2026-04-01",
        "skus": [
            {"SKU": "TRK-FX3-L", "Description": "Trek FX3 Disc Large",   "Ordered": 4,  "Received": 4},
            {"SKU": "TRK-FX3-M", "Description": "Trek FX3 Disc Medium",  "Ordered": 6,  "Received": 6},
            {"SKU": "TRK-FX3-S", "Description": "Trek FX3 Disc Small",   "Ordered": 4,  "Received": 0},
            {"SKU": "TRK-ACC",   "Description": "Trek Accessory Bundle",  "Ordered": 10, "Received": 0},
        ],
    },
    {
        "id": "PO-2026-039", "brand": "Shimano", "supplier": "Shimano Direct",
        "units": 60, "eta": "2026-04-12", "status": "Partially Received",
        "location": "Central / Warehouse", "created_at": "2026-03-28",
        "skus": [
            {"SKU": "SHM-XT-M8", "Description": "Shimano XT M8100 Derailleur", "Ordered": 20, "Received": 10},
            {"SKU": "SHM-CS-M8", "Description": "Shimano CS-M8100 Cassette",   "Ordered": 40, "Received": 0},
        ],
    },
    {
        "id": "PO-2026-037", "brand": "Garmin", "supplier": "CDN Cycling Supply",
        "units": 15, "eta": "2026-04-18", "status": "In Transit",
        "location": "Central / Warehouse", "created_at": "2026-03-25",
        "skus": [
            {"SKU": "GAR-530",  "Description": "Garmin Edge 530",  "Ordered": 5, "Received": 0},
            {"SKU": "GAR-1040", "Description": "Garmin Edge 1040", "Ordered": 5, "Received": 0},
            {"SKU": "GAR-HRM",  "Description": "Garmin HRM-Dual",  "Ordered": 5, "Received": 0},
        ],
    },
    {
        "id": "PO-2026-034", "brand": "Giro Helmets", "supplier": "Sport Systems",
        "units": 18, "eta": "2026-04-01", "status": "Received",
        "location": "Central / Warehouse", "created_at": "2026-03-20",
        "skus": [
            {"SKU": "HELM-GV-M", "Description": "Giro Vantage Helmet M", "Ordered": 9, "Received": 9},
            {"SKU": "HELM-GV-L", "Description": "Giro Vantage Helmet L", "Ordered": 9, "Received": 9},
        ],
    },
]

STATUS_ICON = {"In Transit": "🔵", "Partially Received": "🟡", "Received": "🟢", "Discrepancy": "🔴"}
VALID_SKUS  = set(INVENTORY.keys())
VALID_TYPES = ["inbound", "outbound", "transfer", "receiving"]
VALID_LOCS  = ["Central / Warehouse", "Store 1 · Cycling", "Store 2 · Running"]

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
                st.session_state.page = "Dashboard"
                st.rerun()
            else:
                st.error("Invalid credentials")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🚲 Enroute IMS")
    st.caption(f"**{st.session_state.user_name}**")
    st.caption(f"Role: {st.session_state.user_role}")
    st.divider()

    pages = ["📊 Dashboard", "📦 Inventory Control", "📋 PO Tracker"]
    if "page" not in st.session_state:
        st.session_state.page = "📊 Dashboard"

    for p in pages:
        if st.button(p, use_container_width=True,
                     type="primary" if st.session_state.page == p else "secondary"):
            st.session_state.page = p
            st.rerun()

    st.divider()
    if st.button("Sign Out", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

page = st.session_state.page

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    all_u     = sum(v["Central"] + v["Store1"] + v["Store2"] for v in INVENTORY.values())
    central_u = sum(v["Central"] for v in INVENTORY.values())
    store1_u  = sum(v["Store1"]  for v in INVENTORY.values())
    store2_u  = sum(v["Store2"]  for v in INVENTORY.values())
    low_stock = sum(1 for v in INVENTORY.values() if v["Central"] + v["Store1"] + v["Store2"] < 5)

    st.title("📊 Dashboard")
    st.caption(f"Signed in as **{st.session_state.user_name}** · Last sync: today 10:42 AM · Shopify live")
    st.divider()

    st.markdown("#### Key Inventory Indicators")
    st.caption("Real-time data from Shopify. Updated with every registered movement.")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📦 Total Units",          f"{all_u:,}",  "+142 this week",
              help="Sum of all units across 3 locations. Source: Shopify Inventory API.")
    k2.metric("🔴 Low Stock SKUs",       str(low_stock), "+2 vs last week", delta_color="inverse",
              help="SKUs with fewer than 5 units total. Triggers automatic alert.")
    k3.metric("🚚 POs In Transit",       "4",           "Next ETA: Apr 8",
              help="Confirmed Purchase Orders pending receipt at warehouse.")
    k4.metric("✅ Inventory Accuracy",   "98.2%",       "+0.4% vs baseline",
              help="Match rate between physical count and Shopify records.")

    st.divider()
    st.markdown("#### Stock Distribution by Location")
    st.caption("Shopify manages each location independently. All movements are tracked per location.")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**🏭 Central / Warehouse**")
        st.markdown(f"### {central_u} units")
        st.progress(central_u / all_u, text=f"{central_u/all_u*100:.1f}% of total stock")
        st.caption("Main location. Receives all POs and manages outbound shipments.")
    with c2:
        st.markdown("**🚲 Store 1 · Cycling**")
        st.markdown(f"### {store1_u} units")
        st.progress(store1_u / all_u, text=f"{store1_u/all_u*100:.1f}% of total stock")
        st.caption("Cycling specialty store. Floor inventory only.")
    with c3:
        st.markdown("**🏃 Store 2 · Running**")
        st.markdown(f"### {store2_u} units")
        st.progress(store2_u / all_u, text=f"{store2_u/all_u*100:.1f}% of total stock")
        st.caption("Running specialty store. Floor inventory only.")

    st.divider()
    left, right = st.columns(2)
    with left:
        st.markdown("#### ⚠️ Active Alerts")
        st.caption("Automatically detected situations requiring immediate attention.")
        for sku, data in INVENTORY.items():
            total = data["Central"] + data["Store1"] + data["Store2"]
            if total < 5:
                st.error(f"**{sku}** — {data['desc']}  |  {total} units remaining · Urgent reorder")
        st.info("📦 **Trek Bikes PO-2026-041** — ETA Apr 8 · 24 units incoming to Central")
        st.warning("🔄 **Transfer TRF-021** pending confirmation — Central → Store1 · 6 units")
    with right:
        st.markdown("#### 📋 Recent Movements")
        st.caption("Every inbound, outbound, or transfer is logged with user and reference.")
        st.dataframe(pd.DataFrame(MOVEMENTS), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### 📦 Full Inventory — All Locations")
    st.caption("Consolidated view from Shopify. Each row is an active SKU.")
    rows = []
    for sku, data in INVENTORY.items():
        total = data["Central"] + data["Store1"] + data["Store2"]
        rows.append({
            "SKU": sku, "Description": data["desc"],
            "Central 🏭": data["Central"], "Store1 🚲": data["Store1"], "Store2 🏃": data["Store2"],
            "Total": total,
            "Status": "🔴 Low" if total < 5 else ("🟡 Watch" if total < 10 else "🟢 OK"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: INVENTORY CONTROL
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📦 Inventory Control":
    st.title("📦 Inventory Control")
    st.caption("Inbound · Outbound · Transfers · Adjustments — all movements applied directly in Shopify")
    st.divider()

    with st.expander("📥 Download Excel Template", expanded=False):
        st.caption("Use this template for any type of inventory movement. One format for all locations.")
        tpl = pd.DataFrame([
            ["TRK-FX3-L", "Trek FX3 Disc Large",  2, "inbound",  "Central / Warehouse",  "PO-2026-041"],
            ["SHM-XT-M8", "Shimano XT M8100",      4, "transfer", "Central / Warehouse",  "TRF-021"],
            ["ASS-GEL-P", "Gel Saddle Pro",         3, "outbound", "Store 2 · Running",    ""],
        ], columns=["SKU", "Description", "Quantity", "Type", "Location", "Reference"])
        st.dataframe(tpl, use_container_width=True, hide_index=True)
        buf = io.BytesIO()
        tpl.to_excel(buf, index=False, engine="openpyxl")
        st.download_button("⬇ Download template.xlsx", data=buf.getvalue(),
                           file_name="enroute_template.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.caption("**Valid types:** `inbound` · `outbound` · `transfer` · `receiving`")

    st.divider()
    st.markdown("#### ↑ Upload Movement Excel")
    st.caption("The app validates each row before sending to Shopify. Errors are flagged in the preview.")

    uploaded = st.file_uploader("Select Excel file", type=["xlsx", "xls"])
    if uploaded:
        try:
            df = pd.read_excel(uploaded, engine="openpyxl")
            statuses = []
            for _, row in df.iterrows():
                issues = []
                if str(row.get("SKU", "")) not in VALID_SKUS:
                    issues.append("SKU not found in Shopify")
                if str(row.get("Type", "")).lower() not in VALID_TYPES:
                    issues.append("Invalid type")
                if str(row.get("Location", "")) not in VALID_LOCS:
                    issues.append("Invalid location")
                try:
                    if int(row.get("Quantity", 0)) <= 0:
                        issues.append("Quantity must be > 0")
                except Exception:
                    issues.append("Non-numeric quantity")
                statuses.append("❌ " + " · ".join(issues) if issues else "✅ Valid")
            df["Status"] = statuses
            valid  = sum(1 for s in statuses if s.startswith("✅"))
            errors = sum(1 for s in statuses if s.startswith("❌"))
            c1, c2, c3 = st.columns(3)
            c1.metric("✅ Valid rows", valid)
            c2.metric("❌ Errors", errors, delta_color="inverse")
            c3.metric("📤 Ready for Shopify", valid)
            st.markdown("**Preview — review before applying**")
            st.dataframe(df, use_container_width=True, hide_index=True)
            if valid > 0:
                if st.button(f"🚀 Apply {valid} movements → Shopify", type="primary"):
                    st.success(f"✅ {valid} movements applied in Shopify. (Demo mode)")
                    st.info("In production: each row calls `POST /inventory_levels/adjust.json` on Shopify API.")
        except Exception as e:
            st.error(f"Error reading file: {e}")
    else:
        st.info("💡 Upload an Excel file using the template to see automatic validation and preview.")

    st.divider()
    st.markdown("#### 📊 Current Stock by Location")
    st.caption("Data pulled directly from Shopify Inventory API. Refreshed on every page load.")
    col_s, col_f = st.columns([2, 1])
    with col_s:
        search = st.text_input("🔍 Filter by SKU or description", placeholder="e.g. Trek · Shimano · RUN")
    with col_f:
        status_f = st.selectbox("Status", ["All", "🔴 Low", "🟡 Watch", "🟢 OK"])

    rows = []
    for sku, data in INVENTORY.items():
        total  = data["Central"] + data["Store1"] + data["Store2"]
        status = "🔴 Low" if total < 5 else ("🟡 Watch" if total < 10 else "🟢 OK")
        if search and search.upper() not in sku.upper() and search.lower() not in data["desc"].lower():
            continue
        if status_f != "All" and status != status_f:
            continue
        rows.append({"SKU": sku, "Description": data["desc"],
                     "Central 🏭": data["Central"], "Store1 🚲": data["Store1"], "Store2 🏃": data["Store2"],
                     "Total": total, "Status": status})
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"Showing {len(rows)} of {len(INVENTORY)} active SKUs")
    else:
        st.info("No SKUs found with that filter.")

    st.divider()
    st.markdown("#### 📋 Movement History")
    st.caption("Full traceability: every movement logged with reference, type, user, and timestamp.")
    st.dataframe(pd.DataFrame(MOVEMENTS), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: PO TRACKER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 PO Tracker":
    st.title("📋 PO Tracker")
    st.caption("Purchase Orders · Warehouse Reception · Packing Slip Validation · Automatic Shopify Update")
    st.divider()

    transit  = sum(1 for p in DEMO_POS if p["status"] == "In Transit")
    partial  = sum(1 for p in DEMO_POS if p["status"] == "Partially Received")
    received = sum(1 for p in DEMO_POS if p["status"] == "Received")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔵 In Transit",            transit,  help="Confirmed POs awaiting warehouse receipt.")
    k2.metric("🟡 Partially Received",    partial,  help="POs with incomplete reception. Pending items remain open.")
    k3.metric("🟢 Fully Received",        received, help="POs fully received and applied in Shopify.")
    k4.metric("📦 Total PO Units",        sum(p["units"] for p in DEMO_POS))

    st.divider()
    tab_list, tab_new = st.tabs(["📋 Active POs", "➕ New PO"])

    with tab_list:
        search   = st.text_input("🔍 Search by brand, supplier or PO #",
                                 placeholder="e.g. Trek · Shimano · PO-2026-041")
        status_f = st.selectbox("Filter by status",
                                ["All", "In Transit", "Partially Received", "Received"])
        filtered = [
            p for p in DEMO_POS
            if (not search or search.lower() in p["brand"].lower()
                           or search.lower() in p["id"].lower()
                           or search.lower() in p["supplier"].lower())
            and (status_f == "All" or p["status"] == status_f)
        ]

        STAGES    = ["PO Created", "Confirmed", "In Transit", "Reception", "Shopify ✓"]
        STAGE_IDX = {"In Transit": 2, "Partially Received": 3, "Received": 4}

        for po in filtered:
            icon = STATUS_ICON.get(po["status"], "⚪")
            with st.expander(
                f"{icon} **{po['id']}** — {po['brand']}  ·  {po['supplier']}  |  ETA: {po['eta']}  |  {po['status']}",
                expanded=(po["status"] != "Received"),
            ):
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Supplier",     po["supplier"])
                m2.metric("ETA",          po["eta"])
                m3.metric("Total Units",  po["units"])
                m4.metric("Status",       po["status"])

                st.markdown("**PO Progress**")
                current = STAGE_IDX.get(po["status"], 2)
                cols_tl = st.columns(len(STAGES))
                for i, (col, stage) in enumerate(zip(cols_tl, STAGES)):
                    with col:
                        marker = "🟢" if i < current else ("🟡" if i == current else "⚪")
                        weight = "**" if i <= current else ""
                        st.markdown(f"{marker} {weight}{stage}{weight}")

                st.divider()
                if po["skus"]:
                    df_sku = pd.DataFrame(po["skus"])
                    df_sku["Difference"] = df_sku["Received"] - df_sku["Ordered"]
                    df_sku["Status"] = df_sku["Difference"].apply(
                        lambda d: "✅ Complete" if d == 0 else ("⏳ Pending" if d < 0 else "⚠️ Excess"))
                    st.markdown("**PO Line Items**")
                    st.dataframe(df_sku, use_container_width=True, hide_index=True)
                    buf = io.BytesIO()
                    df_sku.to_excel(buf, index=False, engine="openpyxl")
                    st.download_button(f"⬇ Download {po['id']}.xlsx", data=buf.getvalue(),
                                       file_name=f"{po['id']}.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       key=f"dl_{po['id']}")

                if st.session_state.user_role in ["warehouse", "admin"]:
                    if po["status"] in ["In Transit", "Partially Received"]:
                        st.divider()
                        st.markdown("**📥 Register Reception**")
                        st.caption("Validate received goods against packing slip. Shopify updates automatically on confirmation.")
                        method = st.radio("Validation method",
                                          ["✅ Manual checklist", "📄 Upload receiving Excel"],
                                          horizontal=True, key=f"method_{po['id']}")
                        if method.startswith("✅"):
                            recv_items = {}
                            for item in po["skus"]:
                                pending = item["Ordered"] - item["Received"]
                                if pending > 0:
                                    if st.checkbox(
                                        f"**{item['SKU']}** — {item['Description']} (Ordered: {item['Ordered']} · Pending: {pending})",
                                        key=f"chk_{po['id']}_{item['SKU']}"
                                    ):
                                        recv_items[item["SKU"]] = pending
                            if recv_items:
                                total_recv = sum(recv_items.values())
                                if st.button(f"🚀 Confirm reception of {len(recv_items)} SKUs ({total_recv} units) → Shopify",
                                             key=f"confirm_{po['id']}", type="primary"):
                                    st.success(f"✅ Reception confirmed. {total_recv} units updated in Shopify. (Demo mode)")
                        else:
                            recv_file = st.file_uploader("Upload receiving Excel (universal template)",
                                                          type=["xlsx", "xls"], key=f"recv_{po['id']}")
                            if recv_file:
                                df_r = pd.read_excel(recv_file, engine="openpyxl")
                                st.dataframe(df_r, use_container_width=True, hide_index=True)
                                if st.button("🚀 Confirm reception → Shopify",
                                             key=f"confirm_xl_{po['id']}", type="primary"):
                                    st.success("✅ Reception confirmed. Shopify updated. (Demo mode)")

    with tab_new:
        if st.session_state.user_role not in ["purchasing", "admin"]:
            st.warning("⚠️ Only the purchasing team can create new POs.")
        else:
            st.markdown("#### Create New Purchase Order")
            st.caption("The PO will be visible to the warehouse team with the assigned ETA.")
            c1, c2 = st.columns(2)
            with c1:
                brand    = st.text_input("Brand / Vendor *",   placeholder="e.g. Trek Bikes")
                supplier = st.text_input("Distributor",         placeholder="e.g. QBP Distributor")
                location = st.selectbox("Destination Location *",
                                        ["Central / Warehouse", "Store 1 · Cycling", "Store 2 · Running"])
            with c2:
                eta   = st.date_input("Expected ETA *")
                notes = st.text_area("Notes for warehouse", height=100,
                                     placeholder="Special instructions, delivery conditions, etc.")
            st.markdown("**PO File**")
            st.caption("Attach the vendor PDF or Excel. Warehouse will download it to validate against the packing slip.")
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
                    - Initial status: **In Transit**
                    - Warehouse team has been notified automatically.
                    """)
