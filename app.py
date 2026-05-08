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
        parse_warehouse, validate_warehouse_file,
        cross_reference, _loc_stats,
    )
    ENGINE_OK = True
except ImportError as _ie:
    ENGINE_OK = False
    _import_error = str(_ie)

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
    "inv_df":       None,
    "ord_df":       None,
    "inv_store":    {},
    "ord_store":    {},
    "po_published": None,
    "wh_df":        None,
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
        st.caption(
            f"**{store_label}** ({store_code})  \n"
            f"{'✅' if inv_loaded else '⚪'} Inventory · "
            f"{'✅' if ord_loaded else '⚪'} Orders"
        )
    wh_loaded = st.session_state.wh_df is not None
    st.caption(f"**🏭 Warehouse**  \n{'✅' if wh_loaded else '⚪'} Master file")

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


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    st.title("📊 Dashboard")

    if not ENGINE_OK:
        st.error("❌ `data_engine.py` not found. Place it in the same folder as `app.py`.")
        st.stop()

    # ── Shopify file upload ───────────────────────────────────────────────
    no_data = not st.session_state.inv_store and not st.session_state.ord_store
    with st.expander("📂 Upload Shopify Export Files", expanded=no_data):

        def _rebuild_combined():
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
                             help=f"Clear {store_code} data", disabled=not has_data):
                    st.session_state.inv_store.pop(store_code, None)
                    st.session_state.ord_store.pop(store_code, None)
                    _rebuild_combined()
                    st.rerun()
            st.divider()

    # ── Warehouse file upload ─────────────────────────────────────────────
    with st.expander("🏭 Upload Warehouse Master File",
                     expanded=(st.session_state.wh_df is None)):
        st.caption("Format: Brand · Type · Description · Gender · Color · Size · SKU# · UPC/EAN# · Location · Stock Qty")
        wh_file = st.file_uploader(
            "wh", type=["xlsx", "xls", "csv"],
            key="wh_upload", label_visibility="collapsed"
        )
        if wh_file:
            try:
                wh_parsed = parse_warehouse(wh_file)
                warns = validate_warehouse_file(wh_parsed)
                for w in warns: st.warning(w)
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
            st.success(f"✅ Loaded — {wh['SKU'].nunique():,} SKUs · {int(wh['Stock_Qty'].sum()):,} total units")
        if st.session_state.wh_df is not None:
            if st.button("🗑 Clear warehouse file", key="clear_wh"):
                st.session_state.wh_df = None
                st.rerun()

    inv_df = st.session_state.inv_df
    if inv_df is None:
        st.info("Upload at least one Shopify inventory file above to see the dashboard.")
        st.stop()

    # Store filter
    loaded_stores = list(st.session_state.inv_store.keys())
    STORE_LABELS  = {"CC": "🚴 Cycling (CC)", "RR": "🏃 Running (RR)"}
    if len(loaded_stores) > 1:
        sel_store_label = st.selectbox(
            "📍 View store",
            ["All Stores"] + [STORE_LABELS.get(s, s) for s in loaded_stores],
            key="dash_store_filter"
        )
        store_code_map = {STORE_LABELS.get(s, s): s for s in loaded_stores}
        sel_store = store_code_map.get(sel_store_label)
    else:
        sel_store = loaded_stores[0] if loaded_stores else None

    def _filter_store(df, store_code):
        if df is None or store_code is None: return df
        return df[df["Store"] == store_code].copy() if "Store" in df.columns else df

    inv_view = _filter_store(inv_df, sel_store) if sel_store else inv_df

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 1 — INVENTORY STORE COMPARISON  (HTML card widget)
    # ══════════════════════════════════════════════════════════════════════
    inv_cc = st.session_state.inv_store.get("CC")
    inv_rr = st.session_state.inv_store.get("RR")

    def _inv_stats(df):
        if df is None or len(df) == 0:
            return {"skus": 0, "on_hand": 0, "stockouts": 0,
                    "available": 0, "committed": 0}
        sku_total = df.groupby("SKU")["On_Hand"].sum()
        active    = sku_total[sku_total > 0]
        return {
            "skus":      int(len(active)),
            "on_hand":   int(df["On_Hand"].sum()),
            "available": int(df["Available"].sum()),
            "committed": int(df["Committed"].sum()),
            "stockouts": int((sku_total == 0).sum()),
        }

    cc_s = _inv_stats(inv_cc)
    rr_s = _inv_stats(inv_rr)

    def _loc_rows_html(inv_cc, inv_rr, inv_view):
        if inv_view is None: return ""
        loc_df, _ = _loc_stats(inv_view)
        if loc_df.empty: return ""
        def su(df, loc):
            if df is None: return 0
            return int(df[df["Location"] == loc]["On_Hand"].sum())
        html = ""
        for _, row in loc_df.iterrows():
            loc   = row["Location"]
            cc_u  = su(inv_cc, loc); rr_u = su(inv_rr, loc)
            tot_u = cc_u + rr_u
            cp = round(cc_u / tot_u * 100) if tot_u else 0
            html += (
                f'<div class="loc-card">'
                f'<div class="loc-name">{loc}</div>'
                f'<div class="loc-pct">{row["pct_total"]:.1f}%</div>'
                f'<div class="loc-split-bar">'
                f'<div class="lsb-cc" style="width:{cp}%;"></div>'
                f'<div class="lsb-rr" style="width:{100-cp}%;"></div>'
                f'</div>'
                f'<div class="loc-meta"><span>CC {cc_u:,}</span><span>RR {rr_u:,}</span></div>'
                f'<div class="loc-detail">Avail {row["pct_available"]:.1f}% · Commit {row["pct_committed"]:.1f}%</div>'
                f'</div>'
            )
        return html

    loc_html = _loc_rows_html(inv_cc, inv_rr, inv_view)

    css_store = """
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:transparent;color:#111;}
.wrap{padding:4px 0 8px;}
.split{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px;}
.card{background:#fff;border:1px solid #e5e5e5;border-radius:12px;padding:16px;}
@media(prefers-color-scheme:dark){
  body{color:#f0f0f0;}
  .card{background:#1a1a1a;border-color:#2e2e2e;}
  .kpi-box{background:#242424!important;}
  .loc-card{background:#1a1a1a;border-color:#2e2e2e;}
}
.store-hdr{display:flex;align-items:center;gap:8px;margin-bottom:12px;}
.badge{font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;}
.badge-cc{background:#111;color:#fff;}
.badge-rr{background:#E24B4A;color:#fff;}
.store-name{font-size:13px;font-weight:500;}
.kpi-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;}
.kpi-box{background:#f5f5f5;border-radius:8px;padding:10px 12px;}
.kpi-lbl{font-size:10px;color:#888;margin-bottom:3px;}
.kpi-val{font-size:18px;font-weight:500;}
.sec-lbl{font-size:10px;letter-spacing:.08em;color:#aaa;text-transform:uppercase;margin-bottom:10px;}
.combined-hdr{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:12px;}
.combined-title{font-size:13px;font-weight:500;}
.combined-sub{font-size:11px;color:#888;}
.loc-legend{display:flex;gap:12px;font-size:11px;color:#888;}
.ll-dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:3px;}
.loc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;}
.loc-card{border:1px solid #e5e5e5;border-radius:8px;padding:10px 12px;}
.loc-name{font-size:10px;color:#888;margin-bottom:4px;}
.loc-pct{font-size:19px;font-weight:500;}
.loc-split-bar{display:flex;height:3px;border-radius:2px;overflow:hidden;margin:6px 0 5px;}
.lsb-cc{height:100%;background:#111;}
.lsb-rr{height:100%;background:#E24B4A;}
.loc-meta{display:flex;justify-content:space-between;font-size:10px;color:#888;}
.loc-detail{font-size:10px;color:#aaa;margin-top:4px;}
"""

    html_store = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{css_store}</style></head><body><div class="wrap">
<div class="sec-lbl">Inventory — store comparison</div>
<div class="split">
<div class="card">
  <div class="store-hdr"><span class="badge badge-cc">CC</span><span class="store-name">Cycling Store</span></div>
  <div class="kpi-row">
    <div class="kpi-box"><div class="kpi-lbl">SKUs w/ stock</div><div class="kpi-val">{cc_s["skus"]:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">On Hand</div><div class="kpi-val">{cc_s["on_hand"]:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Stockouts</div><div class="kpi-val" style="color:#E24B4A;">{cc_s["stockouts"]:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Available</div><div class="kpi-val" style="color:#1D9E75;">{cc_s["available"]:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Committed</div><div class="kpi-val">{cc_s["committed"]:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Avail %</div><div class="kpi-val">{round(cc_s["available"]/cc_s["on_hand"]*100) if cc_s["on_hand"] else 0}%</div></div>
  </div>
</div>
<div class="card">
  <div class="store-hdr"><span class="badge badge-rr">RR</span><span class="store-name">Running Store</span></div>
  <div class="kpi-row">
    <div class="kpi-box"><div class="kpi-lbl">SKUs w/ stock</div><div class="kpi-val">{rr_s["skus"]:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">On Hand</div><div class="kpi-val">{rr_s["on_hand"]:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Stockouts</div><div class="kpi-val" style="color:#E24B4A;">{rr_s["stockouts"]:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Available</div><div class="kpi-val" style="color:#1D9E75;">{rr_s["available"]:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Committed</div><div class="kpi-val">{rr_s["committed"]:,}</div></div>
    <div class="kpi-box"><div class="kpi-lbl">Avail %</div><div class="kpi-val">{round(rr_s["available"]/rr_s["on_hand"]*100) if rr_s["on_hand"] else 0}%</div></div>
  </div>
</div>
</div>
<div class="card">
  <div class="combined-hdr">
    <div><div class="combined-title">Inventory by location</div><div class="combined-sub">CC vs RR split per location</div></div>
    <div class="loc-legend">
      <span><span class="ll-dot" style="background:#111;"></span>CC</span>
      <span><span class="ll-dot" style="background:#E24B4A;"></span>RR</span>
    </div>
  </div>
  <div class="loc-grid">{loc_html}</div>
</div>
</div></body></html>"""

    components.html(html_store, height=420, scrolling=False)

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 2 — INVENTORY ACCURACY  (requires WH file)
    # ══════════════════════════════════════════════════════════════════════
    if st.session_state.wh_df is None:
        st.info("🏭 Upload the Warehouse Master File above to see the Inventory Accuracy section.")
        st.stop()

    wh_df = st.session_state.wh_df

    # ── Compute accuracy metrics ──────────────────────────────────────────
    # Shopify "Online" location = shared warehouse in Shopify
    def _online_stock(df):
        if df is None: return pd.DataFrame(columns=["SKU_norm","Shopify_Online"])
        online = df[df["Location"] == "Online"].copy()
        return (
            online.groupby("SKU_norm")["On_Hand"]
            .sum().reset_index()
            .rename(columns={"On_Hand": "Shopify_Online"})
        )

    cc_online = _online_stock(inv_cc)
    rr_online = _online_stock(inv_rr)

    # Merge CC+RR online stock
    shopify_online = cc_online.merge(rr_online, on="SKU_norm", how="outer", suffixes=("_cc","_rr")).fillna(0)
    shopify_online["Shopify_Online"] = shopify_online.get("Shopify_Online_cc", shopify_online.get("Shopify_Online",0)) + \
                                       shopify_online.get("Shopify_Online_rr", 0)
    # Handle column naming depending on merge
    for col in ["Shopify_Online_cc", "Shopify_Online_rr"]:
        if col in shopify_online.columns:
            pass
    # Recompute cleanly
    cc_on = cc_online.rename(columns={"Shopify_Online":"CC_Online"})
    rr_on = rr_online.rename(columns={"Shopify_Online":"RR_Online"})
    shopify_online = cc_on.merge(rr_on, on="SKU_norm", how="outer").fillna(0)
    shopify_online["Shopify_Online"] = shopify_online["CC_Online"] + shopify_online["RR_Online"]
    shopify_online_valued = shopify_online[shopify_online["Shopify_Online"] > 0]

    # Warehouse aggregated
    wh_agg = (
        wh_df.groupby("SKU_norm")
        .agg(
            WH_SKU  =("SKU",         "first"),
            WH_Desc =("Description", "first"),
            WH_Brand=("Brand",       "first"),
            WH_Stock=("Stock_Qty",   "sum"),
        )
        .reset_index()
    )
    wh_with_stock = wh_agg[wh_agg["WH_Stock"] > 0]

    # Three-way join: Shopify Online vs WH
    merged = shopify_online_valued.merge(
        wh_with_stock[["SKU_norm","WH_SKU","WH_Desc","WH_Brand","WH_Stock"]],
        on="SKU_norm", how="outer", indicator=True
    )

    in_both      = merged[merged["_merge"] == "both"].copy()
    shopify_only = merged[merged["_merge"] == "left_only"].copy()   # Shopify Online, not in WH
    wh_only      = merged[merged["_merge"] == "right_only"].copy()  # WH stock, not in Shopify Online

    # Add SKU / Title to shopify_only from inv_df
    if inv_df is not None:
        sku_meta = inv_df.groupby("SKU_norm").agg(
            SKU=("SKU","first"), Title=("Title","first")
        ).reset_index()
        shopify_only = shopify_only.merge(sku_meta, on="SKU_norm", how="left")

    # Discrepancy in matched
    in_both["WH_Stock"]      = in_both["WH_Stock"].fillna(0).astype(int)
    in_both["Shopify_Online"] = in_both["Shopify_Online"].fillna(0).astype(int)
    in_both["Delta"]         = in_both["WH_Stock"] - in_both["Shopify_Online"]

    exact_match   = int((in_both["Delta"] == 0).sum())
    wh_higher     = int((in_both["Delta"] >  0).sum())
    wh_lower      = int((in_both["Delta"] <  0).sum())
    total_matched = len(in_both)
    total_sh_on   = int(shopify_online_valued["Shopify_Online"].sum())
    total_wh      = int(wh_with_stock["WH_Stock"].sum())
    match_pct     = round(exact_match / total_matched * 100, 1) if total_matched else 0

    # ── Pre-compute misassignment SKUs so KPIs can split pure vs misassigned ──
    _non_online_skus = set()
    if inv_df is not None:
        _all_loc_pre = inv_df.groupby(["SKU_norm","Location"])["On_Hand"].sum().reset_index()
        _non_online_pre = _all_loc_pre[
            (_all_loc_pre["Location"] != "Online") & (_all_loc_pre["On_Hand"] > 0)
        ]
        _non_online_skus = set(_non_online_pre["SKU_norm"])

    # Split matched discrepancies into pure vs misassignment
    disc_mask   = in_both["Delta"] != 0
    missass_mask = in_both["SKU_norm"].isin(_non_online_skus)
    pure_wh_higher  = int(((in_both["Delta"] > 0) & ~missass_mask).sum())
    pure_wh_lower   = int(((in_both["Delta"] < 0) & ~missass_mask).sum())
    missass_matched = int((disc_mask & missass_mask).sum())

    # WH-only: split pure vs misassignment
    wh_only_missass = int(wh_only["SKU_norm"].isin(_non_online_skus).sum())
    wh_only_pure    = len(wh_only) - wh_only_missass

    total_pure_disc   = pure_wh_higher + pure_wh_lower + wh_only_pure
    total_misassigned = missass_matched + wh_only_missass

    # ── Accuracy KPI HTML cards ───────────────────────────────────────────
    css_acc = """
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:transparent;color:#111;}
.wrap{padding:4px 0 8px;}
.sec-lbl{font-size:10px;letter-spacing:.08em;color:#aaa;text-transform:uppercase;margin-bottom:10px;}
.row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px;}
.row3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;}
.card{background:#fff;border:1px solid #e5e5e5;border-radius:12px;padding:14px 16px;}
.card-green{background:#f0faf5;border:1px solid #b2dfc9;}
.card-red{background:#fff5f5;border:1px solid #f5c0c0;}
.card-amber{background:#fffbf0;border:1px solid #f5dfa0;}
@media(prefers-color-scheme:dark){
  body{color:#f0f0f0;}
  .card{background:#1a1a1a;border-color:#2e2e2e;}
  .card-green{background:#0d2b1e;border-color:#1a5c3a;}
  .card-red{background:#2b0d0d;border-color:#5c1a1a;}
  .card-amber{background:#2b2200;border-color:#5c4400;}
}
.lbl{font-size:10px;color:#888;margin-bottom:4px;letter-spacing:.03em;}
.val{font-size:22px;font-weight:500;}
.sub{font-size:11px;margin-top:3px;color:#aaa;}
.val-green{color:#1D9E75;}
.val-red{color:#E24B4A;}
.val-amber{color:#BA7517;}
.big-pct{font-size:38px;font-weight:600;}
"""

    html_acc = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{css_acc}</style></head><body><div class="wrap">
<div class="sec-lbl">Inventory accuracy — Warehouse vs Shopify Online</div>

<div class="row">
  <div class="card">
    <div class="lbl">Shopify Online SKUs (valued)</div>
    <div class="val">{len(shopify_online_valued):,}</div>
    <div class="sub">{total_sh_on:,} total units</div>
  </div>
  <div class="card">
    <div class="lbl">Warehouse SKUs (stock &gt; 0)</div>
    <div class="val">{len(wh_with_stock):,}</div>
    <div class="sub">{total_wh:,} total units</div>
  </div>
  <div class="card">
    <div class="lbl">Matched SKUs (in both)</div>
    <div class="val">{total_matched:,}</div>
    <div class="sub">cross-referenced</div>
  </div>
  <div class="card {'card-green' if match_pct >= 80 else 'card-amber' if match_pct >= 50 else 'card-red'}">
    <div class="lbl">Accuracy rate</div>
    <div class="val big-pct {'val-green' if match_pct >= 80 else 'val-amber' if match_pct >= 50 else 'val-red'}">{match_pct}%</div>
    <div class="sub">exact qty match / matched SKUs</div>
  </div>
</div>

<div class="row">
  <div class="card card-green">
    <div class="lbl">✅ Exact match</div>
    <div class="val val-green">{exact_match:,}</div>
    <div class="sub">WH qty = Shopify Online qty</div>
  </div>
  <div class="card card-amber">
    <div class="lbl">⚖️ Pure discrepancy</div>
    <div class="val val-amber">{total_pure_disc:,}</div>
    <div class="sub">True qty mismatch — needs Shopify adjustment</div>
  </div>
  <div class="card" style="background:#f0f4ff;border-color:#b0c4f5;">
    <div class="lbl">📍 Possible misassignment</div>
    <div class="val" style="color:#2255CC;">{total_misassigned:,}</div>
    <div class="sub">Has stock in other locations — may not be a real error</div>
  </div>
  <div class="card card-amber">
    <div class="lbl">🛍 Shopify only — not in WH</div>
    <div class="val val-red">{len(shopify_only):,}</div>
    <div class="sub">Shopify Online has stock, WH file doesn't</div>
  </div>
</div>

<div class="row">
  <div class="card card-amber">
    <div class="lbl">⬆ WH &gt; Shopify (pure)</div>
    <div class="val val-amber">{pure_wh_higher:,}</div>
    <div class="sub">Add units to Shopify Online</div>
  </div>
  <div class="card card-red">
    <div class="lbl">⬇ WH &lt; Shopify (pure)</div>
    <div class="val val-red">{pure_wh_lower:,}</div>
    <div class="sub">Remove units from Shopify Online</div>
  </div>
  <div class="card card-red">
    <div class="lbl">🏭 WH only — pure (not in Shopify)</div>
    <div class="val val-amber">{wh_only_pure:,}</div>
    <div class="sub">No other location stock — add to Shopify Online</div>
  </div>
  <div class="card" style="background:#f0f4ff;border-color:#b0c4f5;">
    <div class="lbl">🏭 WH only — possible misassignment</div>
    <div class="val" style="color:#2255CC;">{wh_only_missass:,}</div>
    <div class="sub">WH stock exists + other Shopify locations have stock</div>
  </div>
</div>

</div></body></html>"""

    components.html(html_acc, height=390, scrolling=False)

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 3 — INVENTORY REPORT  (discrepancy detail)
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("### 📋 Inventory Report")
    st.caption("Discrepancies between Warehouse master file and Shopify Online location. Use this to adjust stock in Shopify.")

    # ── Pre-compute: possible misassignment ─────────────────────────────────
    # SKUs where WH has stock (or discrepancy) AND Shopify has units in OTHER
    # locations (not Online) — suggesting the stock may be wrongly assigned.
    misassign_df = pd.DataFrame()
    if inv_df is not None:
        all_loc = inv_df.groupby(["SKU_norm","Location"])["On_Hand"].sum().reset_index()
        non_online = all_loc[all_loc["Location"] != "Online"].copy()
        non_online_agg = (non_online.groupby("SKU_norm")["On_Hand"]
                          .sum().reset_index()
                          .rename(columns={"On_Hand":"Shopify_Other_Locs"}))

        # Candidates: WH-only rows + discrepancy rows
        disc_base = in_both[in_both["Delta"] != 0][
            ["SKU_norm","WH_SKU","WH_Desc","WH_Brand","WH_Stock","Shopify_Online"]].copy()
        wh_base = wh_only[["SKU_norm","WH_SKU","WH_Desc","WH_Brand","WH_Stock"]].copy()
        wh_base["Shopify_Online"] = 0
        candidates = pd.concat([disc_base, wh_base], ignore_index=True)

        # Keep only those with stock in non-Online locations
        candidates = candidates.merge(non_online_agg, on="SKU_norm", how="inner")
        candidates = candidates[candidates["Shopify_Other_Locs"] > 0].copy()

        if not candidates.empty:
            # Add Shopify SKU + Title
            sku_meta3 = inv_df.groupby("SKU_norm").agg(
                Shopify_SKU=("SKU","first"), Title=("Title","first")
            ).reset_index()
            candidates = candidates.merge(sku_meta3, on="SKU_norm", how="left")

            # Add Store (CC / RR / CC+RR)
            cc_skus = set(inv_cc["SKU_norm"]) if inv_cc is not None else set()
            rr_skus = set(inv_rr["SKU_norm"]) if inv_rr is not None else set()
            def _store(n):
                in_cc = n in cc_skus
                in_rr = n in rr_skus
                if in_cc and in_rr: return "CC + RR"
                if in_cc:           return "CC 🚴"
                if in_rr:           return "RR 🏃"
                return "—"
            candidates["Store"] = candidates["SKU_norm"].apply(_store)

            # Pivot non-Online locations as individual columns
            pivot_skus = non_online[non_online["SKU_norm"].isin(candidates["SKU_norm"])].copy()
            loc_pivot = pivot_skus.pivot_table(
                index="SKU_norm", columns="Location",
                values="On_Hand", aggfunc="sum", fill_value=0
            ).reset_index()
            loc_pivot.columns.name = None
            candidates = candidates.merge(loc_pivot, on="SKU_norm", how="left")

            # Total Shopify across ALL locations
            all_agg = (all_loc.groupby("SKU_norm")["On_Hand"]
                       .sum().reset_index()
                       .rename(columns={"On_Hand":"Shopify_All_Locs"}))
            candidates = candidates.merge(all_agg, on="SKU_norm", how="left")
            candidates["Shopify_All_Locs"] = candidates["Shopify_All_Locs"].fillna(0).astype(int)

            candidates["Status"] = candidates.apply(
                lambda r: "✅ Total matches WH" if r["WH_Stock"] == r["Shopify_All_Locs"]
                else (f"⬆ WH has {r['WH_Stock']-r['Shopify_All_Locs']:+,} more"
                      if r["WH_Stock"] > r["Shopify_All_Locs"]
                      else f"⬇ Shopify has {r['Shopify_All_Locs']-r['WH_Stock']:+,} more"),
                axis=1
            )
            misassign_df = candidates.copy()

    # SKU_norms that belong in Misassignment — exclude from Qty Discrepancy
    misassign_skus = set(misassign_df["SKU_norm"]) if not misassign_df.empty else set()
    n_misassign = len(misassign_df)

    # Pure discrepancy = matched with delta != 0 AND no non-Online stock
    pure_disc_df = in_both[
        (in_both["Delta"] != 0) & (~in_both["SKU_norm"].isin(misassign_skus))
    ].copy()
    n_pure_disc = len(pure_disc_df)

    tab_disc, tab_wh_only, tab_sh_only, tab_wrong_loc = st.tabs([
        f"⚖️ Qty Discrepancy ({n_pure_disc:,})",
        f"🏭 WH only — add to Shopify ({len(wh_only):,})",
        f"🛍 Shopify only — review ({len(shopify_only):,})",
        f"📍 Possible Misassignment ({n_misassign:,})",
    ])

    # ── Tab 1: Qty discrepancy ────────────────────────────────────────────
    # Only SKUs where WH ≠ Shopify Online AND the SKU has NO stock in any
    # other Shopify location (those cases live in Possible Misassignment).
    with tab_disc:
        st.caption(
            "SKUs where WH stock ≠ Shopify Online **and** the item has no stock "
            "in any other Shopify location. Adjust the Shopify Online qty to match the physical count."
        )

        disc_df = pure_disc_df.copy()
        if disc_df.empty:
            st.success("✅ No pure quantity discrepancies — all mismatches involve stock in other locations (see Possible Misassignment tab).")
        else:
            if inv_df is not None:
                sku_meta2 = inv_df.groupby("SKU_norm").agg(
                    Shopify_SKU=("SKU","first"), Title=("Title","first")
                ).reset_index()
                disc_df = disc_df.merge(sku_meta2, on="SKU_norm", how="left")

            disc_df["Action"] = disc_df["Delta"].apply(
                lambda d: f"▲ Add {d:+,} in Shopify Online" if d > 0
                          else f"▼ Remove {abs(d):,} from Shopify Online"
            )

            show_cols = {}
            if "Shopify_SKU" in disc_df.columns: show_cols["Shopify_SKU"] = "Shopify SKU"
            if "WH_SKU"      in disc_df.columns: show_cols["WH_SKU"]      = "WH SKU"
            if "Title"       in disc_df.columns: show_cols["Title"]        = "Product Title"
            if "WH_Brand"    in disc_df.columns: show_cols["WH_Brand"]     = "Brand"
            if "WH_Desc"     in disc_df.columns: show_cols["WH_Desc"]      = "WH Description"
            show_cols.update({
                "WH_Stock":       "WH Stock",
                "Shopify_Online": "Shopify Online",
                "Delta":          "Delta",
                "Action":         "Action",
            })

            display = disc_df[list(show_cols.keys())].rename(columns=show_cols)
            display = display.sort_values("Delta", key=abs, ascending=False).reset_index(drop=True)

            st.dataframe(
                display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Delta":          st.column_config.NumberColumn("Delta", format="%+d"),
                    "WH Stock":       st.column_config.NumberColumn("WH Stock"),
                    "Shopify Online": st.column_config.NumberColumn("Shopify Online"),
                }
            )
            n_higher = int((disc_df["Delta"] > 0).sum())
            n_lower  = int((disc_df["Delta"] < 0).sum())
            st.caption(f"{len(display):,} pure discrepancies · WH higher: {n_higher:,} · WH lower: {n_lower:,}")

    # ── Tab 2: WH only — not in Shopify Online ───────────────────────────
    with tab_wh_only:
        st.caption("These SKUs have physical stock in the warehouse but **zero units in Shopify Online location**. Add them to Shopify to reflect actual stock.")

        if wh_only.empty:
            st.success("✅ All warehouse SKUs are reflected in Shopify Online.")
        else:
            wh_show = wh_only[["WH_SKU","WH_Brand","WH_Desc","WH_Stock"]].copy()
            wh_show.columns = ["WH SKU","Brand","Description","WH Stock"]
            wh_show["Action"] = "▲ Add to Shopify Online"
            wh_show = wh_show.sort_values("WH Stock", ascending=False).reset_index(drop=True)
            st.dataframe(
                wh_show,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "WH Stock": st.column_config.NumberColumn("WH Stock"),
                }
            )
            st.caption(f"{len(wh_show):,} SKUs · {int(wh_only['WH_Stock'].sum()):,} total units not reflected in Shopify")

    # ── Tab 3: Shopify Online only — not in WH ───────────────────────────
    with tab_sh_only:
        st.caption("These SKUs show stock in **Shopify Online** but are absent from the Warehouse master file. Verify physical count or remove from Shopify if stock doesn't exist.")

        if shopify_only.empty:
            st.success("✅ All Shopify Online SKUs are present in the warehouse file.")
        else:
            sh_cols = ["SKU_norm"]
            rename_sh = {"SKU_norm": "SKU norm"}
            if "SKU" in shopify_only.columns:
                sh_cols.insert(0, "SKU"); rename_sh["SKU"] = "Shopify SKU"
            if "Title" in shopify_only.columns:
                sh_cols.append("Title"); rename_sh["Title"] = "Product Title"
            sh_cols.append("Shopify_Online")
            rename_sh["Shopify_Online"] = "Shopify Online Units"

            sh_show = shopify_only[[c for c in sh_cols if c in shopify_only.columns]].copy()
            sh_show = sh_show.rename(columns=rename_sh)
            sh_show["Action"] = "🔍 Verify / Remove from Shopify"
            sh_show = sh_show.sort_values("Shopify Online Units", ascending=False).reset_index(drop=True)
            st.dataframe(
                sh_show,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Shopify Online Units": st.column_config.NumberColumn("Shopify Online Units"),
                }
            )
            st.caption(f"{len(sh_show):,} SKUs · {int(shopify_only['Shopify_Online'].sum()):,} total units in Shopify with no WH record")

    # ── Tab 4: Possible misassignment ─────────────────────────────────────
    with tab_wrong_loc:
        st.caption(
            "SKUs where the **Shopify Online location shows 0** (or a discrepancy vs WH), "
            "but the SKU **has stock in other Shopify locations**. "
            "The physical units may simply be assigned to the wrong location in Shopify. "
            "Review and move stock to the Online location if it physically sits in the warehouse."
        )

        if misassign_df.empty:
            st.success("✅ No potential misassignments detected.")
        else:
            # Build display columns dynamically
            # Fixed columns first
            fixed = {}
            if "Shopify_SKU" in misassign_df.columns: fixed["Shopify_SKU"] = "Shopify SKU"
            if "WH_SKU"      in misassign_df.columns: fixed["WH_SKU"]      = "WH SKU"
            if "Title"       in misassign_df.columns: fixed["Title"]        = "Product"
            if "WH_Brand"    in misassign_df.columns: fixed["WH_Brand"]     = "Brand"
            if "Store"       in misassign_df.columns: fixed["Store"]        = "Store"
            fixed["WH_Stock"]       = "WH Stock"
            fixed["Shopify_Online"] = "Shopify Online"

            # Dynamic location columns (all non-standard columns = Shopify locations)
            reserved = {"SKU_norm","Shopify_SKU","WH_SKU","Title","WH_Desc","WH_Brand",
                        "WH_Stock","Shopify_Online","Shopify_Other_Locs",
                        "Shopify_All_Locs","Status","_merge","CC_Online","RR_Online"}
            loc_cols = [c for c in misassign_df.columns if c not in reserved]

            fixed["Shopify_All_Locs"] = "Shopify Total (all locs)"
            fixed["Status"]           = "WH vs Shopify Total"

            all_cols = list(fixed.keys()) + loc_cols
            # Deduplicate columns before rename (pivot may produce collisions)
            seen_cols = {}
            dedup_cols = []
            for c in misassign_df.columns:
                if c in seen_cols:
                    seen_cols[c] += 1
                    dedup_cols.append(f"{c}_{seen_cols[c]}")
                else:
                    seen_cols[c] = 0
                    dedup_cols.append(c)
            misassign_df.columns = dedup_cols

            # Re-derive loc_cols after dedup
            reserved = {"SKU_norm","Shopify_SKU","WH_SKU","Title","WH_Desc","WH_Brand",
                        "Store","WH_Stock","Shopify_Online","Shopify_Other_Locs",
                        "Shopify_All_Locs","Status","_merge","CC_Online","RR_Online"}
            loc_cols = [c for c in misassign_df.columns if c not in reserved
                        and not c.startswith("SKU_norm")]

            all_cols = list(fixed.keys()) + loc_cols
            display_ma = misassign_df[[c for c in all_cols if c in misassign_df.columns]].copy()
            display_ma = display_ma.rename(columns=fixed)

            # Highlight "Total matches WH" rows
            total_match  = (misassign_df["Status"].str.startswith("✅")).sum()
            total_higher = (misassign_df["Status"].str.startswith("⬆")).sum()
            total_lower  = (misassign_df["Status"].str.startswith("⬇")).sum()

            m1, m2, m3 = st.columns(3)
            m1.metric("✅ Total matches WH (wrong loc only)", total_match,
                      help="WH stock = total Shopify stock — just in wrong location")
            m2.metric("⬆ WH still has more",  total_higher,
                      help="Even counting all locations, WH has more")
            m3.metric("⬇ Shopify still has more", total_lower,
                      help="Even counting all locations, Shopify total exceeds WH")

            st.dataframe(
                display_ma.sort_values("WH Stock", ascending=False).reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "WH Stock":               st.column_config.NumberColumn("WH Stock"),
                    "Shopify Online":         st.column_config.NumberColumn("Shopify Online"),
                    "Shopify Total (all locs)":st.column_config.NumberColumn("Shopify Total (all locs)"),
                    **{c: st.column_config.NumberColumn(c) for c in loc_cols if c in display_ma.columns}
                }
            )
            st.caption(
                f"{len(display_ma):,} SKUs flagged · "
                f"{total_match:,} are likely just wrong location · "
                f"Action: move stock to **Online** location in Shopify"
            )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: INVENTORY CONTROL
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📦 Inventory Control":
    st.title("📦 Inventory Control")
    tab1, tab2 = st.tabs(["📊 Inventory by Location", "📥 Receive PO"])

    with tab1:
        inv_df = st.session_state.inv_df
        if inv_df is None:
            st.info("No inventory file loaded. Upload it from the Dashboard.")
        else:
            st.markdown("#### Shopify Inventory — Detail by Location, grouped by Product")
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
                      if _ic_store and "Store" in inv_df.columns else inv_df.copy())

            loc_df, grand_total = _loc_stats(ic_inv)
            active_locs  = loc_df["Location"].tolist()
            selected_loc = st.selectbox("Location", ["All Locations"] + active_locs)

            filtered = (ic_inv.copy() if selected_loc == "All Locations"
                        else ic_inv[ic_inv["Location"] == selected_loc].copy())

            by_title = filtered.groupby("Title").agg(
                Variants  =("SKU",       "nunique"),
                On_Hand   =("On_Hand",   "sum"),
                Available =("Available", "sum"),
                Committed =("Committed", "sum"),
                Incoming  =("Incoming",  "sum"),
            ).reset_index().sort_values("On_Hand", ascending=False)

            loc_total = by_title["On_Hand"].sum()
            by_title["% of Loc"] = (by_title["On_Hand"] / loc_total * 100).round(1).astype(str) + "%" if loc_total else "0%"
            by_title["% Avail"]  = (by_title["Available"] / by_title["On_Hand"].replace(0,1) * 100).round(1).astype(str) + "%"
            by_title["% Commit"] = (by_title["Committed"] / by_title["On_Hand"].replace(0,1) * 100).round(1).astype(str) + "%"

            c1, c2, c3, c4 = st.columns(4)
            kpi(c1, "Products",        f"{len(by_title):,}")
            kpi(c2, "Total On Hand",   f"{int(loc_total):,} units")
            kpi(c3, "Total Available", f"{int(by_title['Available'].sum()):,} units")
            kpi(c4, "Total Committed", f"{int(by_title['Committed'].sum()):,} units")

            has_stock = by_title[by_title["On_Hand"] > 0]
            no_stock  = by_title[by_title["On_Hand"] == 0]
            st.caption(f"**{len(has_stock)}** products with stock · **{len(no_stock)}** with no stock")

            search = st.text_input("🔍 Filter by product name", placeholder="e.g. Jersey, Bib, Sock...")
            if search:
                has_stock = has_stock[has_stock["Title"].str.contains(search, case=False, na=False)]

            st.dataframe(
                has_stock[["Title","Variants","On_Hand","% of Loc","Available","% Avail","Committed","% Commit","Incoming"]]
                .rename(columns={"On_Hand":"On Hand"}),
                use_container_width=True, hide_index=True,
            )

            st.divider()
            st.markdown("#### Variant detail")
            title_list = has_stock["Title"].tolist()
            if title_list:
                sel_title = st.selectbox("Select product", title_list)
                variant_df = ic_inv[ic_inv["Title"] == sel_title] if selected_loc == "All Locations" \
                    else ic_inv[(ic_inv["Title"] == sel_title) & (ic_inv["Location"] == selected_loc)]
                show_cols  = ["SKU","Option1_Name","Option1_Value","Option2_Name","Option2_Value",
                              "Option3_Name","Option3_Value","Location","On_Hand","Available","Committed","Incoming"]
                opt_cols   = [c for c in show_cols if c.startswith("Option")]
                non_empty  = [c for c in opt_cols if variant_df[c].astype(str).str.strip().replace("nan","").any()]
                final_cols = ["SKU"] + non_empty + ["Location","On_Hand","Available","Committed","Incoming"]
                st.dataframe(
                    variant_df[final_cols].rename(columns={"On_Hand":"On Hand"}),
                    use_container_width=True, hide_index=True,
                )

    with tab2:
        st.markdown("#### Inbound Purchase Orders")
        st.caption("Sorted by ETA · Check Arrived when shipment lands · Check Completed once entered in Shopify")
        pos_all = st.session_state.pos
        if not pos_all:
            st.info("No POs registered yet. Create one in **PO Tracker → Create PO**.")
        else:
            for po in pos_all:
                try:
                    eta_date = datetime.strptime(po["eta"], "%Y-%m-%d").date()
                    if eta_date <= date.today() and po.get("status") == "In Transit":
                        po["status"] = "Arrived"
                        if not po.get("arrived_at"):
                            po["arrived_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass

            ord_df2     = st.session_state.ord_df
            sku_to_open = {}
            if ord_df2 is not None:
                open_lines = ord_df2[
                    ord_df2["Fulfillment_Status"].isin(["unfulfilled","partial",""])
                ][["Order_ID","SKU","Qty_Ordered","Item_Name"]].copy()
                open_lines["SKU"] = open_lines["SKU"].astype(str).str.strip()
                open_lines = open_lines[
                    open_lines["SKU"].ne("") & open_lines["SKU"].ne("nan") & open_lines["SKU"].ne("None")
                ]
                for _, row in open_lines.iterrows():
                    sku_to_open.setdefault(str(row["SKU"]).upper(), []).append({
                        "order": row["Order_ID"], "item": str(row["Item_Name"])[:50],
                        "qty":   int(row["Qty_Ordered"]),
                    })

            def _eta_sort(po):
                try: return datetime.strptime(po["eta"], "%Y-%m-%d")
                except: return datetime.max

            status_filter = st.selectbox("Filter by status",
                ["All","In Transit","Arrived","Completed","Cancelled"], key="recv_filter")
            filtered_pos  = sorted(
                [p for p in pos_all if status_filter == "All" or p["status"] == status_filter],
                key=_eta_sort
            )

            if not filtered_pos:
                st.info(f"No POs with status '{status_filter}'.")
            else:
                for po in filtered_pos:
                    status_icon = {"In Transit":"🚚","Arrived":"📦","Completed":"✅","Cancelled":"❌"}.get(po.get("status",""),"📋")
                    try:
                        delta = (datetime.strptime(po["eta"],"%Y-%m-%d").date() - date.today()).days
                        days_label = f" · **{delta}d away**" if delta > 0 else \
                                     " · **Arriving today**" if delta == 0 else \
                                     f" · **{abs(delta)}d overdue**"
                    except:
                        days_label = ""

                    po_skus = {s["sku"].strip().upper() for s in po.get("skus", [])}
                    matched = [{**entry, "sku": sku}
                               for sku in po_skus for entry in sku_to_open.get(sku, [])]

                    with st.container(border=True):
                        c1, c2, c3 = st.columns([3, 3, 2])
                        c1.markdown(f"{status_icon} **{po['id']}** · {po['brand']}"
                            + (f"\n\nPO#: `{po['po_number']}`" if po.get("po_number","—") != "—" else ""))
                        c2.markdown(f"📅 ETA: **{po['eta']}**{days_label}  \n📍 {po.get('location','—')}  \n"
                            + (f"🚛 {po['ship_via']}" if po.get("ship_via","—") != "—" else ""))
                        c3.markdown(f"Status: **{po.get('status','')}**  \nLines: **{len(po.get('skus',[]))}**  \nCreated: {po['created']}")

                        st.divider()
                        cb1, cb2, info_col = st.columns([2, 2, 4])
                        is_arrived   = po.get("status") in ("Arrived","Completed")
                        is_completed = po.get("status") == "Completed"
                        arrived_check   = cb1.checkbox("📦 Arrived", value=is_arrived, key=f"arr_{po['id']}")
                        completed_check = cb2.checkbox("✅ Completed", value=is_completed, key=f"cmp_{po['id']}",
                                                        disabled=(not is_arrived and not arrived_check))

                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M"); changed = False
                        if   completed_check and not is_completed:
                            po["status"] = "Completed"; po["completed_at"] = now_str
                            if not po.get("arrived_at"): po["arrived_at"] = now_str
                            changed = True
                        elif not completed_check and is_completed:
                            po["status"] = "Arrived"; po.pop("completed_at", None); changed = True
                        elif arrived_check and not is_arrived:
                            po["status"] = "Arrived"; po["arrived_at"] = now_str; changed = True
                        elif not arrived_check and is_arrived and not is_completed:
                            po["status"] = "In Transit"; po.pop("arrived_at", None); changed = True
                        if changed: st.rerun()

                        ts_parts = []
                        if po.get("arrived_at"):   ts_parts.append(f"Arrived: `{po['arrived_at']}`")
                        if po.get("completed_at"): ts_parts.append(f"Completed: `{po['completed_at']}`")
                        if ts_parts: info_col.caption("  ·  ".join(ts_parts))

                        if matched:
                            st.warning(f"🔔 **{len(matched)} open order line(s) need items from this PO**")
                        if po.get("skus"):
                            with st.expander(f"📋 {len(po['skus'])} line items"):
                                sku_df = pd.DataFrame(po["skus"]).rename(
                                    columns={"sku":"SKU","desc":"Description","qty":"Qty Ordered"})
                                sku_df["Open Orders"] = sku_df["SKU"].apply(
                                    lambda s: f"🔔 {len(sku_to_open.get(s.strip().upper(),[]))} waiting"
                                    if sku_to_open.get(s.strip().upper()) else "—")
                                st.dataframe(sku_df, use_container_width=True, hide_index=True)
                        if matched:
                            with st.expander(f"🔔 Open orders waiting ({len(matched)} lines)"):
                                mo_df = pd.DataFrame(matched)[["order","sku","item","qty"]]
                                mo_df.columns = ["Order ID","SKU","Item","Qty Needed"]
                                st.dataframe(mo_df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: PO TRACKER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 PO Tracker":
    st.title("📋 PO Tracker")
    tab1, tab2 = st.tabs(["➕ Create PO", "📄 All POs"])

    SKU_KW  = ["sku","article","ref","item#","item code","code","código","referencia","part","artículo"]
    DESC_KW = ["description","descripcion","descripción","name","nombre","product","detail","concepto","titulo","title"]
    QTY_KW  = ["qty","quantity","cantidad","units","piezas","pcs","ordered","order qty","cant"]
    JUNK    = {"nan","none","null","","#","no.","#ref!"}

    def _find_col(headers_lower, kw_list):
        for kw in kw_list:
            for j, h in enumerate(headers_lower):
                if kw in h: return j
        return None

    def _clean_qty(val):
        try: return max(1, int(float(str(val).replace(",","").strip())))
        except: return 1

    def _parse_table(table):
        if not table or len(table) < 2: return []
        headers = [str(h).lower().strip() if h else "" for h in table[0]]
        si = _find_col(headers, SKU_KW); di = _find_col(headers, DESC_KW); qi = _find_col(headers, QTY_KW)
        items = []
        for row in table[1:]:
            sku  = str(row[si]).strip() if si is not None and si < len(row) else ""
            desc = str(row[di]).strip() if di is not None and di < len(row) else ""
            qty  = _clean_qty(row[qi]) if qi is not None and qi < len(row) else 1
            if sku.lower() not in JUNK:
                items.append({"SKU": sku, "Description": desc, "Qty": qty})
        return items

    def extract_from_pdf(file_bytes):
        import pdfplumber, io, re
        ARTICLE_START  = re.compile(r'^([A-Z0-9][A-Z0-9\.\-_]{5,30})\s+', re.I)
        HAS_DOT        = re.compile(r'\.')
        QTY_UNIT       = re.compile(r'\b(\d+)\s+(?:Pcs|EA|Units?|Each)\b', re.I)
        FOOTER_RE      = re.compile(r'^(Net Total|Discount|Shipping|GST|PST|Total\b|Whs Policy|Thank you)', re.I)
        ITEM_HEADER_RE = re.compile(r'(Article|SKU|Item|Ref)\s+(Colour|Color|Description|Desc)', re.I)
        BRAND_RE       = re.compile(r'Banking Info:\s*(.+)', re.I)
        INV_RE         = re.compile(r'\b(INV/[A-Z]+/\d+)\b', re.I)
        CUST_PO_RE     = re.compile(r'Customer PO No[.\s:]+([A-Za-z0-9_\-]+)', re.I)
        CARRIERS       = ["UPS","DHL","FedEx","Fedex","Canada Post","Purolator","USPS","TNT","Canpar"]
        full_text = ""; items_text = []; items_table = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                full_text += txt + "\n"; lines = txt.splitlines()
                for table in page.extract_tables(): items_table.extend(_parse_table(table))
                in_items = False
                for line in lines:
                    if ITEM_HEADER_RE.search(line): in_items = True; continue
                    if not in_items: continue
                    if FOOTER_RE.match(line): in_items = False; continue
                    m_start = ARTICLE_START.match(line)
                    if m_start:
                        code = m_start.group(1)
                        if not HAS_DOT.search(code): continue
                        rest = line[m_start.end():]; m_qty = QTY_UNIT.search(rest)
                        items_text.append({"SKU": code,
                                           "Description": rest[:m_qty.start()].strip() if m_qty else rest.strip(),
                                           "Qty": int(m_qty.group(1)) if m_qty else 1})
        raw_items = items_table if items_table else items_text
        seen, items = set(), []
        for it in raw_items:
            key = it["SKU"].strip().lower()
            if key and key not in seen:
                seen.add(key)
                items.append({"SKU": it["SKU"], "Description": it["Description"], "Qty": it["Qty"]})
        brand = ""; po_number = ""; ship_via = ""
        m = BRAND_RE.search(full_text)
        if m: brand = __import__("re").split(r'\bGmbH\b', m.group(1).strip())[0].strip().rstrip(",").strip()
        m = INV_RE.search(full_text)
        if m: po_number = m.group(1)
        m2 = CUST_PO_RE.search(full_text)
        if m2 and not po_number: po_number = m2.group(1).strip()
        all_lines = full_text.splitlines()
        ship_idx = next((i for i,l in enumerate(all_lines) if __import__("re").search(r'Ship Via',l,re.I)), None)
        if ship_idx is not None:
            for l in all_lines[ship_idx:ship_idx+6]:
                for carrier in CARRIERS:
                    m = __import__("re").search(rf'({__import__("re").escape(carrier)}[\w\s]{{0,12}})', l, re.I)
                    if m:
                        ship_via = __import__("re").split(r'\s{{3,}}|\bPO\b|\bBox\b|\bRemit\b', m.group(1), flags=re.I)[0].strip()
                        break
                if ship_via: break
        return {"brand": brand, "po_number": po_number, "ship_via": ship_via, "items": items}

    def extract_from_excel(file_bytes, filename):
        import io
        df = pd.read_csv(io.BytesIO(file_bytes)) if filename.endswith(".csv") \
             else pd.read_excel(io.BytesIO(file_bytes))
        def find_col(kw_list):
            for c in df.columns:
                if any(k in c.lower() for k in kw_list): return c
            return None
        sku_col = find_col(SKU_KW); desc_col = find_col(DESC_KW); qty_col = find_col(QTY_KW)
        items = []
        for _, row in df.iterrows():
            sku  = str(row[sku_col]).strip()  if sku_col  else ""
            desc = str(row[desc_col]).strip() if desc_col else ""
            qty  = _clean_qty(row[qty_col])   if qty_col  else 1
            if sku.lower() not in JUNK:
                items.append({"SKU": sku, "Description": desc, "Qty": qty})
        return {"brand":"","po_number":"","ship_via":"","items": items}

    with tab1:
        if st.session_state.get("po_published"):
            pub = st.session_state.po_published
            st.success(f"✅ **PO added** — `{pub['id']}` · {pub['brand']} · {pub['lines']} items · now visible in **Receive PO**.")
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
                st.session_state.po_published = None; st.rerun()
            st.stop()

        st.markdown("#### New Purchase Order")
        st.markdown("**Step 1 — Upload invoice** *(PDF, Excel, or CSV)*")
        invoice_file = st.file_uploader("invoice", type=["pdf","xlsx","xls","csv"],
                                         key="invoice_upload", label_visibility="collapsed")
        if invoice_file and "invoice_extracted" not in st.session_state:
            fname = invoice_file.name.lower(); file_bytes = invoice_file.read()
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

        if "invoice_extracted" in st.session_state:
            result = st.session_state.invoice_extracted
            n = len(result.get("items", []))
            if n: st.success(f"✅ Extracted **{n} line items** from invoice.")
            else:  st.warning("⚠️ No line items detected. Fill them in manually.")
            if st.button("🗑 Clear invoice / start over"):
                st.session_state.pop("invoice_extracted", None)
                st.session_state.po_items = [{"SKU":"","Description":"","Qty":1}]; st.rerun()

        st.divider()
        st.markdown("**Step 2 — Order details**")
        extracted = st.session_state.get("invoice_extracted", {})
        c1, c2 = st.columns(2)
        brand    = c1.text_input("Brand / Vendor *", value=extracted.get("brand",""), placeholder="e.g. Specialized, MAAP")
        supplier = c2.text_input("Distributor", placeholder="optional")
        c1, c2   = st.columns(2)
        eta      = c1.date_input("Expected Arrival *", value=date.today())
        location = c2.selectbox("Destination *", SHOPIFY_LOCATIONS)
        with st.expander("Optional — PO Number, Ship Via, Tracking"):
            c1, c2, c3 = st.columns(3)
            po_number = c1.text_input("PO Number", value=extracted.get("po_number",""), placeholder="e.g. PO-2026-001")
            ship_via  = c2.text_input("Ship Via",  value=extracted.get("ship_via",""),  placeholder="e.g. DHL, FedEx")
            tracking  = c3.text_input("Tracking Number", placeholder="optional")

        st.divider()
        st.markdown("**Step 3 — Review line items**")
        items = st.session_state.po_items
        h = st.columns([2, 5, 1, 0.5])
        h[0].caption("SKU / Article"); h[1].caption("Description"); h[2].caption("Qty")
        for i, item in enumerate(items):
            c1, c2, c3, c4 = st.columns([2, 5, 1, 0.5])
            items[i]["SKU"]         = c1.text_input("SKU",  value=item["SKU"],         key=f"po_sku_{i}",  placeholder="SKU",         label_visibility="collapsed")
            items[i]["Description"] = c2.text_input("Desc", value=item["Description"], key=f"po_desc_{i}", placeholder="Description", label_visibility="collapsed")
            items[i]["Qty"]         = c3.number_input("Qty", value=item["Qty"],        key=f"po_qty_{i}",  min_value=1,               label_visibility="collapsed")
            if c4.button("🗑", key=f"del_{i}") and len(items) > 1:
                st.session_state.po_items.pop(i); st.rerun()

        if st.button("+ Add line"):
            st.session_state.po_items.append({"SKU":"","Description":"","Qty":1}); st.rerun()

        st.divider()
        valid_lines = [i for i in items if i["SKU"].strip()]
        if valid_lines:
            st.markdown(f"**Preview — {len(valid_lines)} line items ready to publish:**")
            st.dataframe(pd.DataFrame(valid_lines), use_container_width=True, hide_index=True)

        if st.button("🚀 Publish PO", type="primary", disabled=(not brand or not valid_lines)):
            if not brand: st.error("Brand / Vendor is required.")
            elif not valid_lines: st.error("Add at least one line item with a SKU.")
            else:
                new_id = f"PO-{datetime.now().strftime('%Y%m%d')}-{len(st.session_state.pos)+1:03d}"
                st.session_state.pos.append({
                    "id": new_id, "brand": brand, "supplier": supplier or "—",
                    "eta": str(eta), "location": location, "status": "In Transit",
                    "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "po_number": po_number or "—", "ship_via": ship_via or "—", "tracking": tracking or "—",
                    "skus": [{"sku": i["SKU"], "desc": i["Description"], "qty": i["Qty"]} for i in valid_lines],
                })
                st.session_state.po_published = {
                    "id": new_id, "brand": brand, "lines": len(valid_lines),
                    "eta": str(eta), "location": location, "ship_via": ship_via or "—",
                }
                st.session_state.po_items = [{"SKU":"","Description":"","Qty":1}]
                st.session_state.pop("invoice_extracted", None)
                st.rerun()

    with tab2:
        st.markdown("#### Purchase Orders")
        if not st.session_state.pos:
            st.info("No POs yet. Create one in the tab above.")
        else:
            status_filter = st.selectbox("Filter", ["All","In Transit","Arrived","Completed","Cancelled"])
            filtered = (st.session_state.pos if status_filter == "All"
                        else [p for p in st.session_state.pos if p["status"] == status_filter])
            for po in filtered:
                icon = {"In Transit":"🚚","Arrived":"📦","Completed":"✅","Cancelled":"❌"}.get(po["status"],"📋")
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2,2,2,1])
                    c1.markdown(f"**{po['id']}**  \n{po['brand']} · {po['supplier']}  \n"
                        + (f"PO#: `{po['po_number']}`" if po.get('po_number','—') != '—' else ""))
                    c2.markdown(f"**ETA:** {po['eta']}  \n**Dest:** {po['location']}  \n"
                        + (f"Ship Via: {po['ship_via']}" if po.get('ship_via','—') != '—' else ""))
                    c3.markdown(f"**Status:** {icon} {po['status']}  \n**Created:** {po['created']}  \n"
                        + (f"Tracking: `{po['tracking']}`" if po.get('tracking','—') != '—' else ""))
                    c4.markdown(f"**Lines:** {len(po.get('skus',[]))}")
                    if po.get("skus"):
                        with st.expander("View items"):
                            st.dataframe(
                                pd.DataFrame(po["skus"]).rename(
                                    columns={"sku":"SKU","desc":"Description","qty":"Qty"}),
                                use_container_width=True, hide_index=True,
                            )
