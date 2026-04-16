"""
Enroute IMS — app.py
Single-file Streamlit app. Requires data_engine.py in the same folder.
"""

import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
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

    # ── ANIMATED HTML DASHBOARD ────────────────────────────────────────────

    def _build_dashboard_html(inv_cc, inv_rr, ord_cc, ord_rr, inv_view, ord_view):
        def inv_stats(df, ord_df=None):
            if df is None or len(df) == 0:
                return {"skus":0,"on_hand":0,"stockouts":0,"available":0,"committed":0,
                        "pct_with_mov":0,"pct_no_mov":0,"n_with_mov":0,"n_no_mov":0}
            sku_total = df.groupby("SKU")["On_Hand"].sum()
            active = sku_total[sku_total > 0].index.tolist()
            n_active = len(active)
            # Movement: SKUs that appear in orders
            if ord_df is not None and n_active:
                ord_skus = set(ord_df["SKU"].astype(str).str.strip().dropna())
                ord_skus.discard(""); ord_skus.discard("nan")
                n_with = len([s for s in active if s in ord_skus])
                n_no   = n_active - n_with
            else:
                n_with = n_no = 0
            return {
                "skus":        int(n_active),
                "on_hand":     int(df["On_Hand"].sum()),
                "available":   int(df["Available"].sum()),
                "committed":   int(df["Committed"].sum()),
                "stockouts":   int((sku_total == 0).sum()),
                "n_with_mov":  n_with,
                "n_no_mov":    n_no,
                "pct_with_mov": round(n_with/n_active*100,1) if n_active else 0,
                "pct_no_mov":   round(n_no/n_active*100,1) if n_active else 0,
            }

        def fulf_stats(ord_df, inv_df):
            if ord_df is None or inv_df is None:
                return {"total":0,"can":0,"cannot":0,"pct":0,"gap":0}
            f = check_fulfillability(ord_df, inv_df)
            can = int(f["Can_Fulfill"].sum())
            tot = len(f)
            return {"total":tot,"can":can,"cannot":tot-can,
                    "pct":round(can/tot*100,1) if tot else 0,"gap":int(f["Gap"].sum())}

        def rev(ord_df):
            if ord_df is None: return 0
            paid = ord_df[ord_df["Financial_Status"]=="paid"].drop_duplicates("Order_ID")
            return int(paid["Total"].sum())

        cc  = inv_stats(inv_cc, ord_cc); rr  = inv_stats(inv_rr, ord_rr)
        fc_cc = fulf_stats(ord_cc, inv_cc); fc_rr = fulf_stats(ord_rr, inv_rr)
        oc    = orders_summary(ord_cc) if ord_cc is not None else {}
        orr_s = orders_summary(ord_rr) if ord_rr is not None else {}
        oc_wait = (lambda d: round((pd.Timestamp.now(tz='UTC') - d[d['Fulfillment_Status'].isin(['unfulfilled','partial'])].drop_duplicates('Order_ID')['Created_At']).dt.total_seconds().div(3600).div(24).mean(), 1) if d is not None and not d[d['Fulfillment_Status'].isin(['unfulfilled','partial'])].empty else 0.0)(ord_cc)
        orr_wait = (lambda d: round((pd.Timestamp.now(tz='UTC') - d[d['Fulfillment_Status'].isin(['unfulfilled','partial'])].drop_duplicates('Order_ID')['Created_At']).dt.total_seconds().div(3600).div(24).mean(), 1) if d is not None and not d[d['Fulfillment_Status'].isin(['unfulfilled','partial'])].empty else 0.0)(ord_rr)
        oc_total  = oc.get("total_orders",0)
        orr_total = orr_s.get("total_orders",0)

        def loc_rows_html():
            if inv_view is None: return ""
            loc_df, grand = _loc_stats(inv_view)
            if len(loc_df) == 0: return ""
            def su(df, loc):
                if df is None: return 0
                return int(df[df["Location"]==loc]["On_Hand"].sum())
            html = ""
            for _, row in loc_df.iterrows():
                loc = row["Location"]
                cc_u = su(inv_cc, loc); rr_u = su(inv_rr, loc)
                tot_u = cc_u + rr_u
                cp = round(cc_u/tot_u*100) if tot_u else 0
                rp = 100 - cp
                html += (
                    f'<div class="loc-card">'
                    f'<div class="loc-name">{loc}</div>'
                    f'<div class="loc-pct">{row["pct_total"]:.1f}%</div>'
                    f'<div class="loc-split-bar">'
                    f'<div class="lsb-cc" style="width:{cp}%;"></div>'
                    f'<div class="lsb-rr" style="width:{rp}%;"></div>'
                    f'</div>'
                    f'<div class="loc-meta"><span>CC {cc_u:,}</span><span>RR {rr_u:,}</span></div>'
                    f'<div class="loc-detail">Avail {row["pct_available"]:.1f}% &middot; Commit {row["pct_committed"]:.1f}%</div>'
                    f'</div>'
                )
            return html

        pos_transit = [p for p in st.session_state.pos if p.get("status")=="In Transit"]
        transit_qty = {}
        for p in pos_transit:
            for s in p.get("skus",[]):
                k = s["sku"].strip().upper()
                transit_qty[k] = transit_qty.get(k,0) + int(s.get("qty",0))

        n_transit_full = 0; n_transit_partial = 0; transit_units_coming = 0
        total_lines_combined = 0; can_combined = 0; gap_combined = 0
        if inv_view is not None and ord_view is not None:
            fulf_all = check_fulfillability(ord_view, inv_view)
            total_lines_combined = len(fulf_all)
            can_combined = int(fulf_all["Can_Fulfill"].sum())
            gap_combined = int(fulf_all["Gap"].sum())
            if transit_qty:
                cant_all = fulf_all[~fulf_all["Can_Fulfill"]].copy()
                cant_all["_up"] = cant_all["SKU"].astype(str).str.strip().str.upper()
                cant_all["_t"]   = cant_all["_up"].map(lambda k: transit_qty.get(k,0))
                n_transit_full    = int((cant_all["_t"] >= cant_all["Gap"]).sum())
                n_transit_partial = int(((cant_all["_t"] > 0) & (cant_all["_t"] < cant_all["Gap"])).sum())
                transit_units_coming = int(cant_all[cant_all["_t"] > 0]["_t"].sum())
        n_transit_cover = n_transit_full   # keep for backward compat label
        cannot_combined = total_lines_combined - can_combined
        pct_can = round(can_combined/total_lines_combined*100,1) if total_lines_combined else 0
        loc_html = loc_rows_html()

        css = """*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:transparent;color:#111;}
.dash{padding:4px 0 12px;}
.split{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px;}
.store-card,.combined,.order-card,.fulfill-section{background:#fff;border:1px solid #e5e5e5;border-radius:12px;padding:16px;}
.combined,.fulfill-section{margin-bottom:14px;}
.order-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px;}
@media(prefers-color-scheme:dark){
  body{color:#f0f0f0;}
  .store-card,.combined,.order-card,.fulfill-section{background:#1a1a1a;border-color:#2e2e2e;}
  .kpi-box,.fc-box{background:#242424;}
  .loc-card{border-color:#2e2e2e;background:#1a1a1a;}
  .proc-row{border-color:#2e2e2e;}
  .divider{background:#2e2e2e;}
  .leg-val{color:#f0f0f0;}
  .rev span{color:#f0f0f0;}
}
.store-hdr{display:flex;align-items:center;gap:8px;margin-bottom:12px;}
.badge{font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;letter-spacing:.04em;}
.badge-cc{background:#111;color:#fff;}
.badge-rr{background:#E24B4A;color:#fff;}
.store-name{font-size:13px;font-weight:500;}
.kpi-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;}
.kpi-box{background:#f5f5f5;border-radius:8px;padding:10px 12px;}
.kpi-lbl{font-size:10px;color:#888;margin-bottom:3px;letter-spacing:.03em;}
.kpi-val{font-size:18px;font-weight:500;}
.kpi-sub{font-size:10px;margin-top:1px;}
.kpi-sub.up{color:#1D9E75;}
.pie-lbl-txt{font-size:11px;color:#888;margin-bottom:6px;}
.pie-section{display:flex;align-items:center;gap:10px;}
.donut-wrap{position:relative;width:72px;height:72px;flex-shrink:0;}
.donut-center{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:500;}
.legend{display:flex;flex-direction:column;gap:5px;}
.leg-item{display:flex;align-items:center;gap:6px;font-size:11px;color:#888;}
.leg-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;}
.leg-val{margin-left:auto;font-weight:500;font-size:11px;color:#111;}
.sec-lbl{font-size:10px;letter-spacing:.08em;color:#aaa;text-transform:uppercase;margin-bottom:10px;}
.combined-hdr{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:12px;}
.combined-title{font-size:13px;font-weight:500;}
.combined-sub{font-size:11px;color:#888;}
.loc-legend{display:flex;gap:12px;font-size:11px;color:#888;}
.ll-dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:3px;}
.loc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;}
.loc-card{border:1px solid #e5e5e5;border-radius:8px;padding:10px 12px;}
.loc-name{font-size:10px;color:#888;margin-bottom:4px;}
.loc-pct{font-size:19px;font-weight:500;}
.loc-split-bar{display:flex;height:3px;border-radius:2px;overflow:hidden;margin:6px 0 5px;}
.lsb-cc{height:100%;background:#111;}
.lsb-rr{height:100%;background:#E24B4A;}
.loc-meta{display:flex;justify-content:space-between;font-size:10px;color:#888;}
.loc-detail{font-size:10px;color:#aaa;margin-top:4px;}
.proc-row{display:flex;gap:14px;border-top:1px solid #f0f0f0;padding-top:10px;margin-top:10px;}
.p-lbl{font-size:10px;color:#aaa;}
.p-val{font-size:15px;font-weight:500;}
.rev{font-size:11px;color:#888;margin-top:8px;}
.rev span{font-weight:500;color:#111;}
.fc-row{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px;}
.fc-box{background:#f5f5f5;border-radius:8px;padding:10px 12px;}
.fc-lbl{font-size:10px;color:#888;margin-bottom:3px;}
.fc-val{font-size:18px;font-weight:500;}
.fc-sub{font-size:10px;margin-top:1px;}
.divider{height:1px;background:#f0f0f0;margin:12px 0;}
.bar-item{display:flex;flex-direction:column;align-items:center;}
.bar-seg-wrap{display:flex;gap:4px;align-items:flex-end;}
.bar-seg{width:28px;border-radius:3px 3px 0 0;transition:height .8s cubic-bezier(.4,0,.2,1);}
.bar-lbl{font-size:10px;color:#888;margin-top:4px;}
.bar-legend{display:flex;gap:12px;font-size:10px;color:#888;margin-top:6px;justify-content:center;}
.bl-dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:3px;}"""

        cc_can   = fc_cc["can"]; cc_can_not = fc_cc["cannot"]
        rr_can   = fc_rr["can"]; rr_can_not = fc_rr["cannot"]
        cc_pct_v = fc_cc["pct"]; rr_pct_v   = fc_rr["pct"]
        cc_gap   = fc_cc["gap"]; rr_gap     = fc_rr["gap"]
        cc_so    = cc["stockouts"]; rr_so    = rr["stockouts"]
        cc_oh    = cc["on_hand"];   rr_oh    = rr["on_hand"]
        cc_sk    = cc["skus"];      rr_sk    = rr["skus"]
        oc_ful   = oc.get("fulfilled",0); orr_ful  = orr_s.get("fulfilled",0)
        oc_unf   = oc.get("unfulfilled",0); orr_unf = orr_s.get("unfulfilled",0)
        oc_avg   = oc.get("avg_processing_hrs",0)
        oc_min   = oc.get("min_processing_hrs",0)
        oc_max   = oc.get("max_processing_hrs",0)
        orr_avg  = orr_s.get("avg_processing_hrs",0)
        orr_min  = orr_s.get("min_processing_hrs",0)
        orr_max  = orr_s.get("max_processing_hrs",0)
        oc_fp    = round(oc_ful/oc_total*100,1) if oc_total else 0
        orr_fp   = round(orr_ful/orr_total*100,1) if orr_total else 0
        p100     = round(100-pct_can,1)
        # Stock sufficient — unit-level + location source breakdown
        if inv_view is not None and ord_view is not None and can_combined > 0:
            _fulf_can = check_fulfillability(ord_view, inv_view)
            _can_rows = _fulf_can[_fulf_can["Can_Fulfill"]].copy()
            _stock_src = inv_view.groupby("SKU").agg(
                _av =("Available",   "sum"),
                _inc=("Incoming",    "sum"),
                _oh =("On_Hand",     "sum"),
                _com=("Committed",   "sum"),
            ).reset_index()
            _can_rows = _can_rows.merge(_stock_src, on="SKU", how="left").fillna(0)
            total_units_needed     = int(_can_rows["Qty_Ordered"].sum())
            _can_rows["_used_av"]  = _can_rows[["Qty_Ordered","_av"]].min(axis=1).astype(int)
            _can_rows["_used_inc"] = (_can_rows["Qty_Ordered"] - _can_rows["_used_av"]).clip(lower=0).astype(int)
            units_from_available   = int(_can_rows["_used_av"].sum())
            units_from_incoming    = int(_can_rows["_used_inc"].sum())
            total_onhand_in_can    = int(_can_rows["_oh"].sum())
            total_committed_in_can = int(_can_rows["_com"].sum())
            total_av_in_can        = int(_can_rows["_av"].sum())
            pct_units_available    = round(units_from_available / total_units_needed * 100, 1) if total_units_needed else 0
            _sbl = inv_view.groupby(["SKU","Location"])["Available"].sum().reset_index()
            _sbl = _sbl[_sbl["Available"] > 0]
            def _find_src(sku, qty):
                locs = _sbl[_sbl["SKU"]==sku].sort_values("Available", ascending=False)
                for _, r in locs.iterrows():
                    if r["Available"] >= qty: return r["Location"]
                return "Mix: " + " + ".join(locs["Location"].tolist()) if not locs.empty else "Unknown"
            _can_rows["_qty"] = _can_rows["Qty_Ordered"].astype(float)
            _can_rows["Source_Loc"] = _can_rows.apply(lambda r: _find_src(r["SKU"], r["_qty"]), axis=1)
            _loc_counts = _can_rows["Source_Loc"].value_counts().to_dict()
            _badge_colors = {"Online":"#111","In Store":"#1D9E75","Mix":"#BA7517",
                             "Reserve Warehouse":"#185FA5","Enroute Richmond":"#533AB7","Reserve Instore":"#993556"}
            def _bc(loc):
                for k,v in _badge_colors.items():
                    if k in loc: return v
                return "#888"
            loc_badges_html = "".join(
                f'<span style="display:inline-flex;align-items:center;gap:4px;background:{_bc(loc)};'
                f'color:#fff;font-size:11px;font-weight:500;padding:4px 10px;border-radius:20px;">'
                f'{loc}&nbsp;<strong>{cnt}</strong></span>'
                for loc, cnt in sorted(_loc_counts.items(), key=lambda x: -x[1])
            )
            _now2 = pd.Timestamp.now(tz="UTC")
            _open2 = ord_view[ord_view["Fulfillment_Status"].isin(["unfulfilled","partial",""])].drop_duplicates("Order_ID").copy()
            oldest_open_days = round((_now2 - _open2["Created_At"]).dt.total_seconds().div(86400).max(), 1) if not _open2.empty else 0
        else:
            total_units_needed = units_from_available = units_from_incoming = 0
            total_onhand_in_can = total_committed_in_can = 0
            pct_units_available = 0
            total_av_in_can = 0
            loc_badges_html = ""
            oldest_open_days = 0
        oc_wt    = oc_wait
        orr_wt   = orr_wait
        cc_pct_with_mov = cc["pct_with_mov"]; cc_pct_no_mov = cc["pct_no_mov"]
        cc_n_with_mov   = cc["n_with_mov"];   cc_n_no_mov   = cc["n_no_mov"]
        rr_pct_with_mov = rr["pct_with_mov"]; rr_pct_no_mov = rr["pct_no_mov"]
        rr_n_with_mov   = rr["n_with_mov"];   rr_n_no_mov   = rr["n_no_mov"]
        def pct_sub24(ord_df):
            if ord_df is None: return 0.0
            done = ord_df[(ord_df["Fulfillment_Status"]=="fulfilled") & ord_df["Fulfilled_At"].notna() & ord_df["Created_At"].notna()].copy()
            done["hrs"] = (done["Fulfilled_At"] - done["Created_At"]).dt.total_seconds() / 3600
            done = done[done["hrs"] >= 0]
            return round((done["hrs"] < 24).sum() / len(done) * 100, 1) if len(done) else 0.0
        oc_sub24  = pct_sub24(ord_cc)
        orr_sub24 = pct_sub24(ord_rr)

        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<div class="dash">
<div class="sec-lbl">Inventory — store comparison</div>
<div class="split">
<div class="store-card">
  <div class="store-hdr"><span class="badge badge-cc">CC</span><span class="store-name">Cycling Store</span></div>
  <div class="kpi-row">
    <div class="kpi-box"><div class="kpi-lbl">SKUs w/ stock</div><div class="kpi-val">{cc_sk:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">On Hand</div><div class="kpi-val">{cc_oh:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Stockouts</div><div class="kpi-val" style="color:#E24B4A;">{cc_so:,}</div></div>
  </div>
  <div style="display:flex;gap:6px;margin-bottom:10px;">
    <div style="flex:1;background:#f5f5f5;border-radius:6px;padding:7px 10px;">
      <div style="font-size:10px;color:#888;margin-bottom:2px;">With movement</div>
      <div style="font-size:16px;font-weight:500;color:#1D9E75;">{cc_pct_with_mov}%</div>
      <div style="font-size:10px;color:#888;">{cc_n_with_mov:,} SKUs</div>
    </div>
    <div style="flex:1;background:#f5f5f5;border-radius:6px;padding:7px 10px;">
      <div style="font-size:10px;color:#888;margin-bottom:2px;">No movement</div>
      <div style="font-size:16px;font-weight:500;color:#E24B4A;">{cc_pct_no_mov}%</div>
      <div style="font-size:10px;color:#888;">{cc_n_no_mov:,} SKUs</div>
    </div>
  </div>
  <div class="pie-lbl-txt">Fulfillability — open orders</div>
  <div class="pie-section">
    <div class="donut-wrap"><canvas id="pieCC" width="72" height="72"></canvas><div class="donut-center">{cc_pct_v:.0f}%</div></div>
    <div class="legend">
      <div class="leg-item"><div class="leg-dot" style="background:#111;"></div><span>Can fulfill</span><span class="leg-val">{cc_can:,}</span></div>
      <div class="leg-item"><div class="leg-dot" style="background:#E24B4A;"></div><span>Short</span><span class="leg-val">{cc_can_not:,}</span></div>
      <div class="leg-item"><div class="leg-dot" style="background:#ccc;"></div><span>Gap (units)</span><span class="leg-val">{cc_gap:,}</span></div>
    </div>
  </div>
</div>
<div class="store-card">
  <div class="store-hdr"><span class="badge badge-rr">RR</span><span class="store-name">Running Store</span></div>
  <div class="kpi-row">
    <div class="kpi-box"><div class="kpi-lbl">SKUs w/ stock</div><div class="kpi-val">{rr_sk:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">On Hand</div><div class="kpi-val">{rr_oh:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Stockouts</div><div class="kpi-val" style="color:#E24B4A;">{rr_so:,}</div></div>
  </div>
  <div style="display:flex;gap:6px;margin-bottom:10px;">
    <div style="flex:1;background:#f5f5f5;border-radius:6px;padding:7px 10px;">
      <div style="font-size:10px;color:#888;margin-bottom:2px;">With movement</div>
      <div style="font-size:16px;font-weight:500;color:#1D9E75;">{rr_pct_with_mov}%</div>
      <div style="font-size:10px;color:#888;">{rr_n_with_mov:,} SKUs</div>
    </div>
    <div style="flex:1;background:#f5f5f5;border-radius:6px;padding:7px 10px;">
      <div style="font-size:10px;color:#888;margin-bottom:2px;">No movement</div>
      <div style="font-size:16px;font-weight:500;color:#E24B4A;">{rr_pct_no_mov}%</div>
      <div style="font-size:10px;color:#888;">{rr_n_no_mov:,} SKUs</div>
    </div>
  </div>
  <div class="pie-lbl-txt">Fulfillability — open orders</div>
  <div class="pie-section">
    <div class="donut-wrap"><canvas id="pieRR" width="72" height="72"></canvas><div class="donut-center">{rr_pct_v:.0f}%</div></div>
    <div class="legend">
      <div class="leg-item"><div class="leg-dot" style="background:#E24B4A;"></div><span>Can fulfill</span><span class="leg-val">{rr_can:,}</span></div>
      <div class="leg-item"><div class="leg-dot" style="background:#f5a5a5;"></div><span>Short</span><span class="leg-val">{rr_can_not:,}</span></div>
      <div class="leg-item"><div class="leg-dot" style="background:#ccc;"></div><span>Gap (units)</span><span class="leg-val">{rr_gap:,}</span></div>
    </div>
  </div>
</div>
</div>
<div class="combined">
  <div class="combined-hdr">
    <div><div class="combined-title">Inventory by location</div><div class="combined-sub">CC vs RR split per location</div></div>
    <div class="loc-legend"><span><span class="ll-dot" style="background:#111;"></span>CC</span><span><span class="ll-dot" style="background:#E24B4A;"></span>RR</span></div>
  </div>
  <div class="loc-grid">{loc_html}</div>
</div>
<div class="sec-lbl">Orders — store comparison</div>
<div class="order-row">
<div class="order-card">
  <div class="store-hdr"><span class="badge badge-cc">CC</span><span class="store-name">Cycling orders</span></div>
  <div class="kpi-row">
    <div class="kpi-box"><div class="kpi-lbl">Total</div><div class="kpi-val">{oc_total:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Fulfilled</div><div class="kpi-val">{oc_ful:,}</div><div class="kpi-sub up">{oc_fp}%</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Unfulfilled</div><div class="kpi-val" style="color:#E24B4A;">{oc_unf:,}</div></div>
  </div>
  <div class="proc-row">
    <div><div class="p-lbl">Avg fulfillment</div><div class="p-val">{oc_avg} hrs</div></div>
    <div><div class="p-lbl">Filled &lt;24 hrs</div><div class="p-val" style="color:#1D9E75;">{oc_sub24}%</div></div>
    <div><div class="p-lbl">Avg wait (open)</div><div class="p-val" style="color:#E24B4A;">{oc_wt} days</div></div>
  </div>
</div>
<div class="order-card">
  <div class="store-hdr"><span class="badge badge-rr">RR</span><span class="store-name">Running orders</span></div>
  <div class="kpi-row">
    <div class="kpi-box"><div class="kpi-lbl">Total</div><div class="kpi-val">{orr_total:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Fulfilled</div><div class="kpi-val">{orr_ful:,}</div><div class="kpi-sub up">{orr_fp}%</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Unfulfilled</div><div class="kpi-val" style="color:#E24B4A;">{orr_unf:,}</div></div>
  </div>
  <div class="proc-row">
    <div><div class="p-lbl">Avg fulfillment</div><div class="p-val">{orr_avg} hrs</div></div>
    <div><div class="p-lbl">Filled &lt;24 hrs</div><div class="p-val" style="color:#1D9E75;">{orr_sub24}%</div></div>
    <div><div class="p-lbl">Avg wait (open)</div><div class="p-val" style="color:#E24B4A;">{orr_wt} days</div></div>
  </div>
</div>
</div>
<div class="fulfill-section">
  <div class="sec-lbl" style="margin-bottom:10px;">Fulfillability — combined</div>
  <div class="fc-row">
    <div class="fc-box"><div class="fc-lbl">Open lines</div><div class="fc-val">{total_lines_combined:,}</div></div>
    <div class="fc-box"><div class="fc-lbl">Stock sufficient</div><div class="fc-val" style="color:#1D9E75;">{can_combined:,}</div><div class="fc-sub" style="color:#1D9E75;">{pct_can}%</div></div>
    <div class="fc-box"><div class="fc-lbl">Stock short</div><div class="fc-val" style="color:#E24B4A;">{cannot_combined:,}</div><div class="fc-sub" style="color:#E24B4A;">{p100}%</div></div>
    <div class="fc-box"><div class="fc-lbl">In transit cover</div><div class="fc-val">{n_transit_full:,} full · {n_transit_partial:,} partial</div><div class="fc-sub" style="color:#888;">{transit_units_coming:,} units coming · of {cannot_combined} short</div></div>
  </div>
  <div style="border-top:1px solid #f0f0f0;padding-top:10px;margin-top:2px;">
    <div style="font-size:10px;color:#888;margin-bottom:8px;letter-spacing:.05em;text-transform:uppercase;">Stock sufficient — {can_combined:,} lines · {total_units_needed:,} units · oldest open: {oldest_open_days} days</div>
    <div style="margin-bottom:8px;">
      <div style="font-size:11px;color:#555;margin-bottom:5px;font-weight:500;">Pick location — where inventory is available</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;">{loc_badges_html}</div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">
      <div style="padding:8px 10px;border-radius:6px;background:#f5f5f5;">
        <div style="font-size:10px;color:#888;margin-bottom:3px;">On Hand — these SKUs</div>
        <div style="font-size:17px;font-weight:500;">{total_onhand_in_can:,}</div>
        <div style="font-size:10px;color:#aaa;margin-top:1px;">total physical units</div>
      </div>
      <div style="padding:8px 10px;border-radius:6px;background:#f5f5f5;">
        <div style="font-size:10px;color:#888;margin-bottom:3px;">Available — these SKUs</div>
        <div style="font-size:17px;font-weight:500;">{total_av_in_can:,}</div>
        <div style="font-size:10px;color:#aaa;margin-top:1px;">free for new orders</div>
      </div>
      <div style="padding:8px 10px;border-radius:6px;background:#f5f5f5;">
        <div style="font-size:10px;color:#888;margin-bottom:3px;">Committed — these SKUs</div>
        <div style="font-size:17px;font-weight:500;">{total_committed_in_can:,}</div>
        <div style="font-size:10px;color:#aaa;margin-top:1px;">assigned to other orders</div>
      </div>
      <div style="padding:8px 10px;border-radius:6px;background:#f0faf5;">
        <div style="font-size:10px;color:#0F6E56;margin-bottom:3px;">Demand from 520 lines</div>
        <div style="font-size:17px;font-weight:500;color:#0F6E56;">{total_units_needed:,}</div>
        <div style="font-size:10px;color:#1D9E75;margin-top:1px;">{pct_units_available}% filled from Available</div>
      </div>
    </div>
  </div>
</div>
</div>
<script>
var isDark=window.matchMedia('(prefers-color-scheme:dark)').matches;
var bg=isDark?'rgba(255,255,255,.1)':'#e5e5e5';
function drawDonut(id,pct,fill,bg,sz){{
  var c=document.getElementById(id);if(!c)return;
  sz=sz||72;var half=sz/2;
  var ctx=c.getContext('2d'),cx=half,cy=half,r=half*0.77,lw=sz*0.097,start=-Math.PI/2,target=pct/100,t0=null;
  function frame(now){{if(!t0)t0=now;var el=Math.min((now-t0)/900,1);
    var prog=target*(el<.5?2*el*el:-1+(4-2*el)*el);
    ctx.clearRect(0,0,sz,sz);
    ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.strokeStyle=bg;ctx.lineWidth=lw;ctx.stroke();
    ctx.beginPath();ctx.arc(cx,cy,r,start,start+Math.PI*2*prog);ctx.strokeStyle=fill;ctx.lineWidth=lw;ctx.lineCap='round';ctx.stroke();
    if(el<1)requestAnimationFrame(frame);}}
  requestAnimationFrame(frame);
}}
drawDonut('pieCC',{cc_pct_v},isDark?'#ddd':'#111',bg);
drawDonut('pieRR',{rr_pct_v},'#E24B4A',bg);
</script></body></html>"""

    # ── Render HTML dashboard ─────────────────────────────────────────
    inv_cc_d = st.session_state.inv_store.get("CC")
    inv_rr_d = st.session_state.inv_store.get("RR")
    ord_cc_d = st.session_state.ord_store.get("CC")
    ord_rr_d = st.session_state.ord_store.get("RR")

    if inv_view is not None or ord_view is not None:
        html_dash = _build_dashboard_html(
            inv_cc_d, inv_rr_d, ord_cc_d, ord_rr_d, inv_view, ord_view
        )
        components.html(html_dash, height=1060, scrolling=False)

    # ── Transit info banner ───────────────────────────────────────────
    _pos_transit = [p for p in st.session_state.pos if p.get("status")=="In Transit"]
    _transit_qty = {}
    for _p in _pos_transit:
        for _s in _p.get("skus",[]):
            _k = _s["sku"].strip().upper()
            _transit_qty[_k] = _transit_qty.get(_k,0) + int(_s.get("qty",0))
    if _transit_qty and inv_view is not None and ord_view is not None:
        _fp = check_fulfillability(ord_view, inv_view)
        _cant = _fp[~_fp["Can_Fulfill"]].copy()
        _cant["_up"] = _cant["SKU"].astype(str).str.strip().str.upper()
        _n_full = int(_cant.apply(lambda r: _transit_qty.get(r["_up"],0)>=r["Gap"],axis=1).sum())
        _n_part = int(_cant.apply(lambda r: 0 < _transit_qty.get(r["_up"],0) < r["Gap"],axis=1).sum())
        _n = _n_full + _n_part
        if _n:
            st.info(f"🚚 **{_n} open order line(s)** have items in an **In Transit PO** — {_n_full} fully covered, {_n_part} partially covered.")

    # ── Detail expanders — ordered per spec ──────────────────────────

    # Build fulfillability detail once (used in two expanders below)
    _fulf_detail = None
    _can_df = _cant_df = pd.DataFrame()
    if ord_view is not None and inv_view is not None:
        _fulf_detail = check_fulfillability(ord_view, inv_view)
        _now_ts = pd.Timestamp.now(tz="UTC")
        _open_ord = ord_view[
            ord_view["Fulfillment_Status"].isin(["unfulfilled","partial",""])
        ].drop_duplicates("Order_ID")[["Order_ID","Created_At","Financial_Status"]].copy()
        _open_ord["Days Open"] = (
            (_now_ts - _open_ord["Created_At"]).dt.total_seconds() / 86400
        ).round(1)
        _fulf_t = _fulf_detail.merge(_open_ord[["Order_ID","Days Open"]], on="Order_ID", how="left")

        _pos_t = [p for p in st.session_state.pos if p.get("status")=="In Transit"]
        _tqty = {}
        for _p in _pos_t:
            for _s in _p.get("skus",[]):
                _tqty[_s["sku"].strip().upper()] = _tqty.get(_s["sku"].strip().upper(),0)+int(_s.get("qty",0))
        def _ts(row):
            in_t = _tqty.get(row["_sku_up"],0)
            if in_t==0: return "—",False
            elif in_t>=row["Gap"]: return f"🚚 Yes ({in_t})",True
            else: return f"⚠️ Partial ({in_t}/{row['Gap']})",False
        _cant_df = _fulf_t[~_fulf_t["Can_Fulfill"]].copy()
        _cant_df["_sku_up"] = _cant_df["SKU"].astype(str).str.strip().str.upper()
        _cant_df[["Transit_Status","_covered"]] = _cant_df.apply(lambda r: pd.Series(_ts(r)), axis=1)
        _can_df  = _fulf_t[_fulf_t["Can_Fulfill"]].sort_values("Days Open", ascending=False)

    # 1. Inventory detail by location
    if inv_view is not None:
        loc_df_exp, _ = _loc_stats(inv_view)
        display = loc_df_exp.copy()
        display["% of Total"]  = display["pct_total"].round(1).astype(str) + "%"
        display["% Available"] = display["pct_available"].round(1).astype(str) + "%"
        display["% Committed"] = display["pct_committed"].round(1).astype(str) + "%"
        with st.expander("📦 Inventory detail by location"):
            st.dataframe(
                display[["Location","On_Hand","% of Total","Available","% Available","Committed","% Committed","Incoming"]]
                .rename(columns={"On_Hand":"On Hand"}),
                use_container_width=True, hide_index=True,
            )

    # 2. All orders
    if ord_view is not None:
        with st.expander("📋 All orders"):
            order_level = ord_view.drop_duplicates("Order_ID")[["Order_ID","Financial_Status","Fulfillment_Status","Created_At","Fulfilled_At","Subtotal","Total","Shipping_Method","Vendor"]].copy()
            order_level["Created_At"]   = order_level["Created_At"].dt.strftime("%Y-%m-%d %H:%M")
            order_level["Fulfilled_At"] = order_level["Fulfilled_At"].dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(order_level, use_container_width=True, hide_index=True)

    # 3. Lines ready to ship + lines stock short (side by side)
    if not _can_df.empty or not _cant_df.empty:
        c1, c2 = st.columns(2)
        with c1:
            avg_can = round(_can_df["Days Open"].mean(), 1) if not _can_df.empty else 0
            with st.expander(f"✅ {len(_can_df)} lines ready to ship — avg {avg_can} days open"):
                # Add location source column
                if not _can_df.empty:
                    try:
                        _sbl2 = inv_view.groupby(["SKU","Location"])["Available"].sum().reset_index()
                        _sbl2 = _sbl2[_sbl2["Available"] > 0]
                        def _fs2(sku, qty):
                            locs = _sbl2[_sbl2["SKU"]==sku].sort_values("Available", ascending=False)
                            for _, r in locs.iterrows():
                                if r["Available"] >= qty: return r["Location"]
                            return "Mix: " + " + ".join(locs["Location"].tolist()) if not locs.empty else "—"
                        _can_show = _can_df.copy()
                        _can_show["Pick From"] = _can_show.apply(
                            lambda r: _fs2(r["SKU"], float(r["Qty_Ordered"])), axis=1
                        )
                    except Exception:
                        _can_show = _can_df.copy()
                        _can_show["Pick From"] = "—"
                    st.dataframe(
                        _can_show[["Order_ID","SKU","Item_Name","Qty_Ordered","Pick From",
                                   "Available_Stock","Financial_Status","Days Open"]]
                        .rename(columns={"Order_ID":"Order","Item_Name":"Item",
                                         "Qty_Ordered":"Qty","Available_Stock":"In Stock",
                                         "Financial_Status":"Status"}),
                        use_container_width=True, hide_index=True,
                    )
        with c2:
            avg_cant = round(_cant_df["Days Open"].mean(), 1) if not _cant_df.empty else 0
            with st.expander(f"❌ {len(_cant_df)} lines stock short — avg {avg_cant} days open"):
                show = _cant_df[["Order_ID","SKU","Item_Name","Qty_Ordered",
                                  "Available_Stock","Gap","Financial_Status",
                                  "Transit_Status","Days Open"]].copy()
                show.columns = ["Order","SKU","Item","Qty","In Stock","Gap",
                                 "Status","In Transit PO","Days Open"]
                st.dataframe(show, use_container_width=True, hide_index=True)

    # 4. Inventory movement detail
    if inv_view is not None and ord_view is not None:
        st.caption("Inventory movement analysis — based on orders in current export period")
        ord_skus_set = set(ord_view["SKU"].astype(str).str.strip().dropna())
        ord_skus_set.discard(""); ord_skus_set.discard("nan")
        inv_active = inv_view.copy()
        sku_oh = inv_active.groupby("SKU")["On_Hand"].sum()
        active_skus = sku_oh[sku_oh > 0].index
        inv_active = inv_active[inv_active["SKU"].isin(active_skus)]
        inv_summary = inv_active.groupby(["SKU","Title"]).agg(
            On_Hand   =("On_Hand",   "sum"),
            Available =("Available", "sum"),
            Committed =("Committed", "sum"),
            Incoming  =("Incoming",  "sum"),
        ).reset_index()
        inv_summary["Movement"] = inv_summary["SKU"].apply(
            lambda s: "With movement" if s in ord_skus_set else "No movement"
        )
        with_mov = inv_summary[inv_summary["Movement"] == "With movement"].sort_values("On_Hand", ascending=False)
        no_mov   = inv_summary[inv_summary["Movement"] == "No movement"].sort_values("On_Hand", ascending=False)
        c1, c2 = st.columns(2)
        with c1:
            with st.expander(f"✅ {len(with_mov):,} SKUs with movement — {int(with_mov['On_Hand'].sum()):,} units on hand"):
                st.caption("SKUs that appear in at least one order in the current export")
                st.dataframe(
                    with_mov[["SKU","Title","On_Hand","Available","Committed","Incoming"]]
                    .rename(columns={"On_Hand":"On Hand"}),
                    use_container_width=True, hide_index=True,
                )
        with c2:
            with st.expander(f"⚠️ {len(no_mov):,} SKUs with no movement — {int(no_mov['On_Hand'].sum()):,} units on hand"):
                st.caption("Active stock with no sales in current export period")
                st.dataframe(
                    no_mov[["SKU","Title","On_Hand","Available","Committed","Incoming"]]
                    .rename(columns={"On_Hand":"On Hand"}),
                    use_container_width=True, hide_index=True,
                )


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

            # Store filter for Inventory Control
            _ic_store_opts = {"All Stores": None}
            _ic_store_opts.update({
                {"CC": "🚴 Cycling (CC)", "RR": "🏃 Running (RR)"}.get(s, s): s
                for s in st.session_state.inv_store.keys()
            })
            if len(st.session_state.inv_store) > 1:
                _ic_sel_label = st.selectbox("Store", list(_ic_store_opts.keys()), key="ic_store")
                _ic_store = _ic_store_opts[_ic_sel_label]
            else:
                _ic_store = next(iter(st.session_state.inv_store), None)

            ic_inv = (inv_df[inv_df["Store"] == _ic_store].copy()
                      if _ic_store and "Store" in inv_df.columns
                      else inv_df.copy())

            loc_df, grand_total = _loc_stats(ic_inv)
            active_locs = loc_df["Location"].tolist()
            selected_loc = st.selectbox("Location", ["All Locations"] + active_locs)

            filtered = (
                ic_inv.copy() if selected_loc == "All Locations"
                else ic_inv[ic_inv["Location"] == selected_loc].copy()
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
                variant_df = ic_inv[ic_inv["Title"] == sel_title] if selected_loc == "All Locations" \
                    else ic_inv[(ic_inv["Title"] == sel_title) & (ic_inv["Location"] == selected_loc)]

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
