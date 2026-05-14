"""
data_engine.py — Enroute IMS
Parsers and cross-reference logic for:
  - Shopify Inventory Export  (CC store)
  - Shopify Inventory Export  (RR store)
  - Warehouse Master File     (shared physical stock)
"""

import io
import re
import pandas as pd
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════════
# ENCODING
# ══════════════════════════════════════════════════════════════════════════════
def _detect_encoding(raw_bytes: bytes) -> str:
    for enc in ["utf-8", "windows-1252", "latin-1"]:
        try:
            raw_bytes.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _read_csv(file) -> pd.DataFrame:
    raw = file.read() if hasattr(file, "read") else open(file, "rb").read()
    enc = _detect_encoding(raw)
    return pd.read_csv(io.BytesIO(raw), encoding=enc,
                       encoding_errors="replace", low_memory=False)


# ══════════════════════════════════════════════════════════════════════════════
# SKU NORMALIZATION
# ══════════════════════════════════════════════════════════════════════════════
def normalize_sku(sku) -> str:
    """Strip all non-alphanumeric chars and lowercase.
    '3MF10263318-10.5'   -> '3mf10263318105'
    'MAP-WAV080_BGRN_XS' -> 'mapwav080bgrnxs'
    """
    return re.sub(r"[^a-z0-9]", "", str(sku).lower().strip())


# ══════════════════════════════════════════════════════════════════════════════
# COLUMN SPECS
# ══════════════════════════════════════════════════════════════════════════════
SHOPIFY_INV_COLS = [
    "Handle", "Title",
    "Option1 Name", "Option1 Value",
    "Option2 Name", "Option2 Value",
    "Option3 Name", "Option3 Value",
    "SKU", "HS Code", "COO", "Location", "Bin name",
    "Incoming (not editable)", "Unavailable (not editable)",
    "Committed (not editable)", "Available (not editable)",
    "On hand (current)", "On hand (new)",
]

INV_RENAME = {
    "Option1 Name":               "Option1_Name",
    "Option1 Value":              "Option1_Value",
    "Option2 Name":               "Option2_Name",
    "Option2 Value":              "Option2_Value",
    "Option3 Name":               "Option3_Name",
    "Option3 Value":              "Option3_Value",
    "HS Code":                    "HS_Code",
    "Bin name":                   "Bin_Name",
    "Incoming (not editable)":    "Incoming",
    "Unavailable (not editable)": "Unavailable",
    "Committed (not editable)":   "Committed",
    "Available (not editable)":   "Available",
    "On hand (current)":          "On_Hand",
    "On hand (new)":              "On_Hand_New",
}

WH_COLS = ["Brand", "Type", "Description", "Gender",
           "Color", "Size", "SKU#", "UPC/EAN#", "Location", "Stock Qty"]

ORD_COLS = {
    "Name":                       "Order_ID",
    "Email":                      "Email",
    "Financial Status":           "Financial_Status",
    "Paid at":                    "Paid_At",
    "Fulfillment Status":         "Fulfillment_Status",
    "Fulfilled at":               "Fulfilled_At",
    "Accepts Marketing":          "Accepts_Marketing",
    "Currency":                   "Currency",
    "Subtotal":                   "Subtotal",
    "Shipping":                   "Shipping_Cost",
    "Taxes":                      "Taxes",
    "Total":                      "Total",
    "Discount Code":              "Discount_Code",
    "Discount Amount":            "Discount_Amount",
    "Shipping Method":            "Shipping_Method",
    "Created at":                 "Created_At",
    "Lineitem quantity":          "Qty_Ordered",
    "Lineitem name":              "Item_Name",
    "Lineitem price":             "Unit_Price",
    "Lineitem compare at price":  "Compare_At_Price",
    "Lineitem sku":               "SKU",
    "Lineitem requires shipping": "Requires_Shipping",
    "Lineitem taxable":           "Taxable",
    "Lineitem fulfillment status":"Line_Fulfillment",
    "Billing Name":               "Billing_Name",
    "Billing City":               "Billing_City",
    "Billing Province":           "Billing_Province",
    "Billing Country":            "Billing_Country",
    "Shipping Name":              "Shipping_Name",
    "Shipping City":              "Shipping_City",
    "Shipping Province":          "Shipping_Province",
    "Shipping Country":           "Shipping_Country",
    "Notes":                      "Notes",
    "Cancelled at":               "Cancelled_At",
    "Payment Method":             "Payment_Method",
    "Refunded Amount":            "Refunded_Amount",
    "Vendor":                     "Vendor",
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


# ══════════════════════════════════════════════════════════════════════════════
# SHOPIFY INVENTORY PARSER  (CC or RR)
# ══════════════════════════════════════════════════════════════════════════════
def parse_inventory(file) -> pd.DataFrame:
    raw  = _read_csv(file)
    keep = [c for c in SHOPIFY_INV_COLS if c in raw.columns]
    df   = raw[keep].copy().rename(columns=INV_RENAME)

    for col in ["Incoming", "Unavailable", "Committed", "Available", "On_Hand"]:
        df[col] = _to_num(df[col]) if col in df.columns else 0

    df = df[df["SKU"].astype(str).str.strip().ne("")].reset_index(drop=True)

    def _variant(row):
        parts = [str(row.get(f"Option{i}_Value", "")) for i in range(1, 4)]
        return " / ".join(p for p in parts if p.strip() not in ["", "nan"])

    df["Variant"]  = df.apply(_variant, axis=1)
    df["SKU_norm"] = df["SKU"].apply(normalize_sku)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# WAREHOUSE PARSER
# Columns: Brand | Type | Description | Gender | Color | Size |
#          SKU#  | UPC/EAN# | Location | Stock Qty
# NOTE: 'Location' in the WH file is a physical bin (e.g. A7-03), NOT a
#       Shopify location. Renamed to WH_Bin to avoid collision with Shopify's
#       'Location' column.
# ══════════════════════════════════════════════════════════════════════════════
def parse_warehouse(file) -> pd.DataFrame:
    """
    Parse the central warehouse master file (Excel or CSV).
    Uses fuzzy column matching (strip + lowercase) to handle minor
    header variations from different Excel exports.
    """
    fname = getattr(file, "name", "") or ""
    if hasattr(file, "seek"):
        file.seek(0)
    raw_bytes = file.read() if hasattr(file, "read") else open(file, "rb").read()

    def _try_excel(b):
        df = pd.read_excel(io.BytesIO(b), engine="openpyxl")
        if all(str(c).startswith("Unnamed") for c in df.columns):
            df_raw = pd.read_excel(io.BytesIO(b), header=None, engine="openpyxl")
            for i, row in df_raw.iterrows():
                vals = [str(v).strip() for v in row.values if str(v).strip() not in ("", "nan")]
                if len(vals) >= 3:
                    df = pd.read_excel(io.BytesIO(b), header=i, engine="openpyxl")
                    break
        return df

    if fname.lower().endswith((".xlsx", ".xls")):
        raw = _try_excel(raw_bytes)
    else:
        try:
            raw = _try_excel(raw_bytes)
        except Exception:
            enc = _detect_encoding(raw_bytes)
            raw = pd.read_csv(io.BytesIO(raw_bytes), encoding=enc,
                              encoding_errors="replace", low_memory=False)

    # Fuzzy column matching: normalized header → actual header
    col_norm_map = {c.strip().lower(): c for c in raw.columns}

    TARGETS = {
        "SKU":         ["sku#", "sku", "item code", "article", "ref"],
        "UPC":         ["upc/ean#", "upc", "ean", "barcode"],
        "WH_Bin":      ["location", "bin", "bin name", "loc"],
        "Stock_Qty":   ["stock qty", "stock_qty", "qty", "quantity",
                        "stock", "on hand", "on_hand"],
        "Brand":       ["brand"],
        "Type":        ["type"],
        "Description": ["description", "desc", "name"],
        "Gender":      ["gender"],
        "Color":       ["color", "colour"],
        "Size":        ["size"],
    }

    rename_map = {}
    for internal, candidates in TARGETS.items():
        for cand in candidates:
            if cand in col_norm_map:
                actual = col_norm_map[cand]
                if actual not in rename_map:
                    rename_map[actual] = internal
                break

    df = raw[list(rename_map.keys())].copy().rename(columns=rename_map)

    if "SKU" not in df.columns:
        raise ValueError(f"Could not find SKU column. Headers found: {list(raw.columns)}")
    if "Stock_Qty" not in df.columns:
        raise ValueError(f"Could not find Stock Qty column. Headers found: {list(raw.columns)}")

    df["Stock_Qty"] = _to_num(df["Stock_Qty"]).astype(int)

    for col in ["Brand", "Description", "WH_Bin", "Type", "Gender", "Color", "Size"]:
        if col not in df.columns:
            df[col] = ""

    df = df[df["SKU"].astype(str).str.strip().ne("") & df["SKU"].notna()].reset_index(drop=True)
    df["SKU_norm"] = df["SKU"].astype(str).apply(normalize_sku)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# WAREHOUSE <-> SHOPIFY CROSS-REFERENCE
# ══════════════════════════════════════════════════════════════════════════════
def cross_reference(
    wh_df: pd.DataFrame,
    cc_df,   # pd.DataFrame | None
    rr_df,   # pd.DataFrame | None
) -> dict:
    """
    Cross-reference warehouse stock vs Shopify inventory (CC + RR).

    Returns dict with keys:
      summary, matched, shopify_only, wh_only
    """

    def _agg_shopify(df, total_col, online_col):
        if df is None:
            return pd.DataFrame(columns=["SKU_norm", "SKU", "Title", total_col, online_col])
        total = (
            df.groupby("SKU_norm")
            .agg(SKU=("SKU", "first"), Title=("Title", "first"),
                 _total=("On_Hand", "sum"))
            .reset_index()
            .rename(columns={"_total": total_col})
        )
        online = (
            df[df["Location"] == "Online"]
            .groupby("SKU_norm")["On_Hand"]
            .sum().reset_index()
            .rename(columns={"On_Hand": online_col})
        )
        return total.merge(online, on="SKU_norm", how="left").fillna({online_col: 0})

    cc = _agg_shopify(cc_df, "CC_Total", "CC_Online")
    rr = _agg_shopify(rr_df, "RR_Total", "RR_Online")

    shopify = cc.merge(
        rr[["SKU_norm", "RR_Total", "RR_Online"]],
        on="SKU_norm", how="outer"
    ).fillna({"CC_Total": 0, "RR_Total": 0, "CC_Online": 0, "RR_Online": 0})

    if "SKU"   not in shopify.columns: shopify["SKU"]   = ""
    if "Title" not in shopify.columns: shopify["Title"] = ""
    rr_meta = rr[["SKU_norm", "SKU", "Title"]].rename(
        columns={"SKU": "SKU_rr", "Title": "Title_rr"})
    shopify = shopify.merge(rr_meta, on="SKU_norm", how="left")
    shopify["SKU"]   = shopify["SKU"].fillna(shopify.get("SKU_rr",   ""))
    shopify["Title"] = shopify["Title"].fillna(shopify.get("Title_rr", ""))
    shopify = shopify.drop(columns=["SKU_rr", "Title_rr"], errors="ignore")

    shopify["Shopify_Total"]  = shopify["CC_Total"]  + shopify["RR_Total"]
    shopify["Shopify_Online"] = shopify["CC_Online"] + shopify["RR_Online"]
    shopify_valued = shopify[shopify["Shopify_Total"] > 0].copy()

    wh_agg = (
        wh_df.groupby("SKU_norm")
        .agg(WH_SKU=("SKU", "first"), WH_Desc=("Description", "first"),
             WH_Brand=("Brand", "first"), WH_Stock=("Stock_Qty", "sum"))
        .reset_index()
    )

    full         = shopify_valued.merge(wh_agg, on="SKU_norm", how="outer", indicator=True)
    matched      = full[full["_merge"] == "both"].copy()
    shopify_only = full[full["_merge"] == "left_only"].copy()
    wh_only      = full[(full["_merge"] == "right_only") & (full["WH_Stock"] > 0)].copy()

    matched["WH_Stock"]       = matched["WH_Stock"].fillna(0).astype(int)
    matched["Shopify_Online"] = matched["Shopify_Online"].fillna(0).astype(int)
    matched["Delta"]          = matched["WH_Stock"] - matched["Shopify_Online"]
    matched["Delta_Status"]   = matched["Delta"].apply(
        lambda d: "✅ Match" if d == 0 else ("⬆ WH > Shopify" if d > 0 else "⬇ WH < Shopify")
    )

    summary = {
        "shopify_cc_skus_valued": int((shopify["CC_Total"] > 0).sum()),
        "shopify_rr_skus_valued": int((shopify["RR_Total"] > 0).sum()),
        "shopify_total_valued":   int(len(shopify_valued)),
        "shopify_total_units":    int(shopify_valued["Shopify_Total"].sum()),
        "shopify_online_units":   int(shopify_valued["Shopify_Online"].sum()),
        "wh_total_skus":          int(wh_df["SKU_norm"].nunique()),
        "wh_skus_with_stock":     int((wh_agg["WH_Stock"] > 0).sum()),
        "wh_total_units":         int(wh_df["Stock_Qty"].sum()),
        "matched_skus":           int(len(matched)),
        "shopify_only_skus":      int(len(shopify_only)),
        "wh_only_skus":           int(len(wh_only)),
        "delta_exact":            int((matched["Delta"] == 0).sum()),
        "delta_wh_higher":        int((matched["Delta"] > 0).sum()),
        "delta_wh_lower":         int((matched["Delta"] < 0).sum()),
    }

    matched_display = matched[[
        "SKU", "Title", "WH_SKU", "WH_Brand", "WH_Desc",
        "CC_Total", "RR_Total", "Shopify_Total",
        "CC_Online", "RR_Online", "Shopify_Online",
        "WH_Stock", "Delta", "Delta_Status",
    ]].rename(columns={
        "SKU": "Shopify_SKU", "Title": "Shopify_Title",
        "Shopify_Total": "Shopify_On_Hand",
    }).sort_values("Delta", key=abs, ascending=False).reset_index(drop=True)

    shopify_only_display = shopify_only[[
        "SKU", "Title", "CC_Total", "RR_Total", "Shopify_Total",
    ]].rename(columns={
        "SKU": "Shopify_SKU", "Title": "Shopify_Title",
        "Shopify_Total": "Shopify_On_Hand",
    }).sort_values("Shopify_On_Hand", ascending=False).reset_index(drop=True)

    wh_only_display = wh_only[[
        "WH_SKU", "WH_Brand", "WH_Desc", "WH_Stock",
    ]].sort_values("WH_Stock", ascending=False).reset_index(drop=True)

    return {
        "summary":      summary,
        "matched":      matched_display,
        "shopify_only": shopify_only_display,
        "wh_only":      wh_only_display,
    }


# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY BY SKU
# ══════════════════════════════════════════════════════════════════════════════
def inventory_by_sku(inv_df: pd.DataFrame) -> pd.DataFrame:
    totals = inv_df.groupby("SKU").agg(
        Title           = ("Title",    "first"),
        Variant         = ("Variant",  "first"),
        Total_OnHand    = ("On_Hand",  "sum"),
        Total_Available = ("Available","sum"),
        Total_Committed = ("Committed","sum"),
        Total_Incoming  = ("Incoming", "sum"),
    ).reset_index()
    loc_pivot = inv_df.pivot_table(
        index="SKU", columns="Location", values="On_Hand",
        aggfunc="sum", fill_value=0,
    ).reset_index()
    loc_pivot.columns.name = None
    return totals.merge(loc_pivot, on="SKU", how="left")


# ══════════════════════════════════════════════════════════════════════════════
# ORDERS PARSER
# ══════════════════════════════════════════════════════════════════════════════
def parse_orders(file) -> pd.DataFrame:
    raw     = _read_csv(file)
    present = {k: v for k, v in ORD_COLS.items() if k in raw.columns}
    df      = raw.rename(columns=present)[list(present.values())].copy()

    for ts in ["Created_At", "Fulfilled_At", "Paid_At", "Cancelled_At"]:
        if ts in df.columns:
            df[ts] = pd.to_datetime(df[ts], utc=True, errors="coerce")
    for num in ["Qty_Ordered", "Unit_Price", "Subtotal", "Total"]:
        if num in df.columns:
            df[num] = _to_num(df[num])
    for s in ["Financial_Status", "Fulfillment_Status", "Line_Fulfillment"]:
        if s in df.columns:
            df[s] = df[s].fillna("").str.lower().str.strip()
    if "SKU" in df.columns:
        df["SKU"] = df["SKU"].astype(str).str.strip()
    df["SKU_norm"] = df["SKU"].apply(normalize_sku)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# ORDERS SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
def orders_summary(ord_df: pd.DataFrame) -> dict:
    orders = ord_df.drop_duplicates("Order_ID").copy()
    total  = len(orders)
    ful    = (orders["Fulfillment_Status"] == "fulfilled").sum()
    unful  = (orders["Fulfillment_Status"] == "unfulfilled").sum()
    part   = (orders["Fulfillment_Status"] == "partial").sum()
    pend   = (orders["Financial_Status"]   == "pending").sum()
    refnd  = orders["Financial_Status"].isin(["refunded","partially_refunded"]).sum()
    canc   = orders["Cancelled_At"].notna().sum() if "Cancelled_At" in orders.columns else 0

    done = orders[
        (orders["Fulfillment_Status"] == "fulfilled") &
        orders["Fulfilled_At"].notna() & orders["Created_At"].notna()
    ].copy()
    done["proc_hrs"] = (done["Fulfilled_At"] - done["Created_At"]).dt.total_seconds() / 3600
    done = done[done["proc_hrs"] > 0]

    return {
        "total_orders":       total,
        "fulfilled":          int(ful),
        "unfulfilled":        int(unful),
        "partial":            int(part),
        "pending_payment":    int(pend),
        "refunded":           int(refnd),
        "cancelled":          int(canc),
        "avg_processing_hrs": round(done["proc_hrs"].mean(), 1) if len(done) else 0,
        "min_processing_hrs": round(done["proc_hrs"].min(),  1) if len(done) else 0,
        "max_processing_hrs": round(done["proc_hrs"].max(),  1) if len(done) else 0,
    }


# ══════════════════════════════════════════════════════════════════════════════
# FULFILLABILITY
# ══════════════════════════════════════════════════════════════════════════════
def check_fulfillability(ord_df: pd.DataFrame, inv_df: pd.DataFrame) -> pd.DataFrame:
    open_lines = ord_df[
        ord_df["Fulfillment_Status"].isin(["unfulfilled", "partial", ""])
    ][["Order_ID","SKU","Item_Name","Qty_Ordered","Financial_Status"]].copy()
    open_lines["SKU"] = open_lines["SKU"].astype(str).str.strip()
    open_lines = open_lines[
        open_lines["SKU"].ne("") & open_lines["SKU"].ne("nan") & open_lines["SKU"].notna()
    ]
    stock = inv_df.groupby("SKU").agg(
        Available_Stock=("Available","sum"),
        Incoming_Stock =("Incoming", "sum"),
    ).reset_index()
    merged                    = open_lines.merge(stock, on="SKU", how="left")
    merged["Available_Stock"] = merged["Available_Stock"].fillna(0).astype(int)
    merged["Incoming_Stock"]  = merged["Incoming_Stock"].fillna(0).astype(int)
    merged["Effective_Stock"] = merged["Available_Stock"] + merged["Incoming_Stock"]
    merged["Can_Fulfill"]     = merged["Effective_Stock"] >= merged["Qty_Ordered"]
    merged["Gap"]             = (merged["Qty_Ordered"] - merged["Effective_Stock"]).clip(lower=0).astype(int)
    return merged.sort_values("Can_Fulfill").reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
# PER-LOCATION STATS  (used by Dashboard HTML)
# ══════════════════════════════════════════════════════════════════════════════
def _loc_stats(inv_df: pd.DataFrame):
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
    return grp[grp["On_Hand"] > 0].reset_index(drop=True), grand


# ══════════════════════════════════════════════════════════════════════════════
# POSSIBLE SKU ERRORS — fuzzy match between WH-only and Shopify-only SKUs
#
# Called from app.py as:
#   find_sku_errors(_wh_e, _sh_e, inv_df=inv_df)
#
# Input columns
# -------------
# wh_only_df    : SKU_norm, WH_SKU, WH_Desc, WH_Stock, [WH_Location]
# shopify_only_df: SKU_norm, SKU, Title
# inv_df        : full combined Shopify inventory — used for per-location pivot
#
# Output columns (exact spec)
# ---------------------------
# WH_SKU | Shopify_SKU | Shopify_Title | WH_Description | WH Location |
# Online | In Store | Reserve Instore | Reserve Warehouse | SLG | SLG Hong Kong |
# WH_Stock | Shopify_OnHand | Qty_Delta | Match_Type
#
# Match types detected
# --------------------
#   Gender prefix  — WH SKU_norm starts/lacks M/W/U/K vs Shopify
#   Leading zero   — one side has an extra leading 0
#   Substring      — one SKU_norm contains the other (min 5 chars)
# ══════════════════════════════════════════════════════════════════════════════

# Shopify locations shown as individual columns in the SKU errors table
SHOPIFY_STOCK_LOCS = [
    "Online", "In Store", "Reserve Instore",
    "Reserve Warehouse", "SLG", "SLG Hong Kong",
]

def find_sku_errors(
    wh_only_df: pd.DataFrame,
    shopify_only_df: pd.DataFrame,
    inv_df: pd.DataFrame = None,
) -> pd.DataFrame:
    GENDER = ['m', 'w', 'u', 'k']
    EMPTY_COLS = [
        'WH_SKU', 'Shopify_SKU', 'Shopify_Title', 'WH_Description',
        'WH Location',
        *SHOPIFY_STOCK_LOCS,
        'WH_Stock', 'Shopify_OnHand', 'Qty_Delta', 'Match_Type',
    ]

    if (wh_only_df is None or shopify_only_df is None
            or wh_only_df.empty or shopify_only_df.empty):
        return pd.DataFrame(columns=EMPTY_COLS)

    # ── Per-location stock pivot from full inv_df (CC + RR summed) ───────────
    # loc_pivot: SKU_norm → {location_name: on_hand_total}
    loc_pivot = {}  # type: dict
    if inv_df is not None and not inv_df.empty:
        grp = (
            inv_df.groupby(["SKU_norm", "Location"])["On_Hand"]
            .sum().reset_index()
        )
        for _, row in grp.iterrows():
            loc_pivot.setdefault(str(row["SKU_norm"]), {})[row["Location"]] = int(row["On_Hand"])

    # ── Shopify-only lookup: SKU_norm → row ──────────────────────────────────
    sh_map = {str(row["SKU_norm"]): row for _, row in shopify_only_df.iterrows()}

    rows = []
    for _, wh in wh_only_df.iterrows():
        nw         = str(wh["SKU_norm"])
        match_type = None
        sh_row     = None

        # 1. Gender prefix — strip from WH SKU_norm
        for p in GENDER:
            if nw.startswith(p) and nw[1:] in sh_map:
                sh_row, match_type = sh_map[nw[1:]], f"Gender prefix ({p.upper()} stripped)"
                break

        # 2. Gender prefix — add to WH SKU_norm
        if not match_type:
            for p in GENDER:
                if (p + nw) in sh_map:
                    sh_row, match_type = sh_map[p + nw], f"Gender prefix ({p.upper()} added)"
                    break

        # 3. Leading zeros — WH has the extra zero
        if not match_type:
            stripped = nw.lstrip("0")
            if stripped and stripped != nw and stripped in sh_map:
                sh_row, match_type = sh_map[stripped], "Leading zero (WH extra)"

        # 4. Leading zeros — Shopify has the extra zero
        if not match_type:
            if ("0" + nw) in sh_map:
                sh_row, match_type = sh_map["0" + nw], "Leading zero (Shopify extra)"

        # 5. Substring (min 5 chars to reduce noise)
        if not match_type and len(nw) >= 5:
            for sh_n, sh_r in sh_map.items():
                if sh_n != nw and (nw in sh_n or sh_n in nw):
                    sh_row, match_type = sh_r, "Substring"
                    break

        if not match_type:
            continue

        sh_norm     = str(sh_row["SKU_norm"])
        sh_locs     = loc_pivot.get(sh_norm, {})
        sh_on_hand  = sum(sh_locs.values())
        wh_stock    = int(wh.get("WH_Stock", 0))

        row: dict = {
            "WH_SKU":         wh.get("WH_SKU",      "—"),
            "Shopify_SKU":    sh_row.get("SKU",      sh_row.get("SKU_norm", "—")),
            "Shopify_Title":  sh_row.get("Title",    "—"),
            "WH_Description": wh.get("WH_Desc",     "—"),
            "WH Location":    wh.get("WH_Location",  "—"),
        }
        for loc in SHOPIFY_STOCK_LOCS:
            row[loc] = sh_locs.get(loc, 0)

        row["WH_Stock"]       = wh_stock
        row["Shopify_OnHand"] = sh_on_hand
        row["Qty_Delta"]      = wh_stock - sh_on_hand
        row["Match_Type"]     = match_type
        rows.append(row)

    return (
        pd.DataFrame(rows).sort_values("WH_Stock", ascending=False).reset_index(drop=True)
        if rows else pd.DataFrame(columns=EMPTY_COLS)
    )


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════════════
def validate_inventory_file(df: pd.DataFrame) -> list:
    warns = []
    for col in ["SKU", "Location", "Available", "On_Hand"]:
        if col not in df.columns:
            warns.append(f"❌ Missing column: '{col}'")
    if "SKU" in df.columns and df["SKU"].str.strip().eq("").all():
        warns.append("❌ All SKU values are empty")
    if "On_Hand" in df.columns and df["On_Hand"].sum() == 0:
        warns.append("⚠️ On_Hand is 0 for all rows — check file")
    return warns


def validate_orders_file(df: pd.DataFrame) -> list:
    warns = []
    for col in ["Order_ID", "Fulfillment_Status", "Created_At", "SKU", "Qty_Ordered"]:
        if col not in df.columns:
            warns.append(f"❌ Missing column: '{col}'")
    return warns


def validate_warehouse_file(df: pd.DataFrame) -> list:
    warns = []
    if "SKU" not in df.columns:
        warns.append("❌ Missing column: 'SKU#'")
    if "Stock_Qty" not in df.columns:
        warns.append("❌ Missing column: 'Stock Qty'")
    if "SKU" in df.columns and df["SKU"].astype(str).str.strip().eq("").all():
        warns.append("❌ All SKU values are empty")
    return warns
