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
# Extra columns (Fisical, Warehouse_location, Validated, etc.) are ignored.
# ══════════════════════════════════════════════════════════════════════════════
def parse_inventory(file) -> pd.DataFrame:
    raw = _read_csv(file)
    keep = [c for c in SHOPIFY_INV_COLS if c in raw.columns]
    df = raw[keep].copy().rename(columns=INV_RENAME)

    for col in ["Incoming", "Unavailable", "Committed", "Available", "On_Hand"]:
        df[col] = _to_num(df[col]) if col in df.columns else 0

    df = df[df["SKU"].astype(str).str.strip().ne("")].reset_index(drop=True)

    def _variant(row):
        parts = [str(row.get(f"Option{i}_Value", "")) for i in range(1, 4)]
        return " / ".join(p for p in parts if p.strip() not in ["", "nan"])
    df["Variant"] = df.apply(_variant, axis=1)
    df["SKU_norm"] = df["SKU"].apply(normalize_sku)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# WAREHOUSE PARSER
# Columns: Brand | Type | Description | Gender | Color | Size |
#          SKU#  | UPC/EAN# | Location | Stock Qty
# NOTE: 'Location' here is a physical bin (e.g. A7-03), NOT a Shopify location.
#       Renamed to WH_Bin to avoid confusion.
# ══════════════════════════════════════════════════════════════════════════════
def parse_warehouse(file) -> pd.DataFrame:
    """
    Parse the central warehouse master file (Excel or CSV).
    Uses fuzzy column matching (strip + lowercase) to handle minor
    header variations from different Excel exports.
    """
    # ── Detect file type robustly ─────────────────────────────────────────
    fname = getattr(file, "name", "") or ""
    raw_bytes = file.read() if hasattr(file, "read") else open(file, "rb").read()

    if fname.lower().endswith((".xlsx", ".xls")):
        raw = pd.read_excel(io.BytesIO(raw_bytes))
    else:
        # Try Excel first (some files are xlsx without extension), then CSV
        try:
            raw = pd.read_excel(io.BytesIO(raw_bytes))
        except Exception:
            enc = _detect_encoding(raw_bytes)
            raw = pd.read_csv(io.BytesIO(raw_bytes), encoding=enc,
                              encoding_errors="replace", low_memory=False)

    # ── Fuzzy column matching ─────────────────────────────────────────────
    # Build a map from normalized header → actual header in file
    col_norm_map = {c.strip().lower(): c for c in raw.columns}

    # Canonical target → list of possible normalized names to try
    TARGETS = {
        "SKU":       ["sku#", "sku", "item code", "article", "ref"],
        "UPC":       ["upc/ean#", "upc", "ean", "barcode"],
        "WH_Bin":    ["location", "bin", "bin name", "loc"],
        "Stock_Qty": ["stock qty", "stock_qty", "qty", "quantity",
                      "stock", "on hand", "on_hand"],
        "Brand":     ["brand"],
        "Type":      ["type"],
        "Description":["description", "desc", "name"],
        "Gender":    ["gender"],
        "Color":     ["color", "colour"],
        "Size":      ["size"],
    }

    rename_map = {}   # actual_col → internal_name
    for internal, candidates in TARGETS.items():
        for cand in candidates:
            if cand in col_norm_map:
                actual = col_norm_map[cand]
                if actual not in rename_map:  # first match wins
                    rename_map[actual] = internal
                break

    df = raw[list(rename_map.keys())].copy().rename(columns=rename_map)

    # ── Ensure critical columns exist ─────────────────────────────────────
    if "SKU" not in df.columns:
        raise ValueError(
            f"Could not find SKU column. Headers found: {list(raw.columns)}"
        )
    if "Stock_Qty" not in df.columns:
        raise ValueError(
            f"Could not find Stock Qty column. Headers found: {list(raw.columns)}"
        )

    df["Stock_Qty"] = _to_num(df["Stock_Qty"]).astype(int)

    # Optional columns — fill with empty string if missing
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

    Definitions:
      - 'Shopify valued' = SKU with On_Hand > 0 in ANY location in CC or RR
      - 'Shopify Online' = On_Hand where Location == 'Online' (shared warehouse in Shopify)
      - 'WH Stock'       = sum of Stock_Qty per SKU in master file

    Returns dict with keys:
      summary       - KPI dict (counts and units)
      matched       - SKUs present in both Shopify (valued) and WH
      shopify_only  - SKUs with Shopify value but absent from WH
      wh_only       - WH SKUs with Stock_Qty > 0 but absent from Shopify (valued)
    """

    def _agg_shopify(df, total_col, online_col):
        if df is None:
            empty = pd.DataFrame(columns=["SKU_norm", "SKU", "Title", total_col, online_col])
            return empty
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
            .sum()
            .reset_index()
            .rename(columns={"On_Hand": online_col})
        )
        return total.merge(online, on="SKU_norm", how="left").fillna({online_col: 0})

    cc = _agg_shopify(cc_df, "CC_Total", "CC_Online")
    rr = _agg_shopify(rr_df, "RR_Total", "RR_Online")

    # Merge CC + RR into one Shopify view
    shopify = cc.merge(
        rr[["SKU_norm", "RR_Total", "RR_Online"]],
        on="SKU_norm", how="outer"
    ).fillna({"CC_Total": 0, "RR_Total": 0, "CC_Online": 0, "RR_Online": 0})

    # Fill SKU/Title from RR where CC is missing
    if "SKU" not in shopify.columns:
        shopify["SKU"] = ""
    if "Title" not in shopify.columns:
        shopify["Title"] = ""
    rr_meta = rr[["SKU_norm", "SKU", "Title"]].rename(
        columns={"SKU": "SKU_rr", "Title": "Title_rr"})
    shopify = shopify.merge(rr_meta, on="SKU_norm", how="left")
    shopify["SKU"]   = shopify["SKU"].fillna(shopify.get("SKU_rr", ""))
    shopify["Title"] = shopify["Title"].fillna(shopify.get("Title_rr", ""))
    shopify = shopify.drop(columns=["SKU_rr", "Title_rr"], errors="ignore")

    shopify["Shopify_Total"]  = shopify["CC_Total"]  + shopify["RR_Total"]
    shopify["Shopify_Online"] = shopify["CC_Online"] + shopify["RR_Online"]

    shopify_valued = shopify[shopify["Shopify_Total"] > 0].copy()

    # Warehouse aggregate
    wh_agg = (
        wh_df.groupby("SKU_norm")
        .agg(WH_SKU=("SKU", "first"), WH_Desc=("Description", "first"),
             WH_Brand=("Brand", "first"), WH_Stock=("Stock_Qty", "sum"))
        .reset_index()
    )

    # Three-way split
    full = shopify_valued.merge(wh_agg, on="SKU_norm", how="outer", indicator=True)
    matched      = full[full["_merge"] == "both"].copy()
    shopify_only = full[full["_merge"] == "left_only"].copy()
    wh_only_raw  = full[full["_merge"] == "right_only"].copy()
    wh_only      = wh_only_raw[wh_only_raw["WH_Stock"] > 0].copy()

    # Delta: WH Stock vs Shopify Online
    matched["WH_Stock"]      = matched["WH_Stock"].fillna(0).astype(int)
    matched["Shopify_Online"] = matched["Shopify_Online"].fillna(0).astype(int)
    matched["Delta"]         = matched["WH_Stock"] - matched["Shopify_Online"]
    matched["Delta_Status"]  = matched["Delta"].apply(
        lambda d: "✅ Match" if d == 0 else ("⬆ WH > Shopify" if d > 0 else "⬇ WH < Shopify")
    )

    # Summary KPIs
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

    # Display DataFrames
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
    raw = _read_csv(file)
    present = {k: v for k, v in ORD_COLS.items() if k in raw.columns}
    df = raw.rename(columns=present)[list(present.values())].copy()

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
    merged = open_lines.merge(stock, on="SKU", how="left")
    merged["Available_Stock"]  = merged["Available_Stock"].fillna(0).astype(int)
    merged["Incoming_Stock"]   = merged["Incoming_Stock"].fillna(0).astype(int)
    merged["Effective_Stock"]  = merged["Available_Stock"] + merged["Incoming_Stock"]
    merged["Can_Fulfill"]      = merged["Effective_Stock"] >= merged["Qty_Ordered"]
    merged["Gap"]              = (merged["Qty_Ordered"] - merged["Effective_Stock"]).clip(lower=0).astype(int)
    return merged.sort_values("Can_Fulfill").reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════════════
def validate_inventory_file(df: pd.DataFrame) -> list[str]:
    warns = []
    for col in ["SKU", "Location", "Available", "On_Hand"]:
        if col not in df.columns:
            warns.append(f"❌ Missing column: '{col}'")
    if "SKU" in df.columns and df["SKU"].str.strip().eq("").all():
        warns.append("❌ All SKU values are empty")
    if "On_Hand" in df.columns and df["On_Hand"].sum() == 0:
        warns.append("⚠️ On_Hand is 0 for all rows — check file")
    return warns


def validate_orders_file(df: pd.DataFrame) -> list[str]:
    warns = []
    for col in ["Order_ID", "Fulfillment_Status", "Created_At", "SKU", "Qty_Ordered"]:
        if col not in df.columns:
            warns.append(f"❌ Missing column: '{col}'")
    return warns


def validate_warehouse_file(df: pd.DataFrame) -> list[str]:
    warns = []
    if "SKU" not in df.columns:
        warns.append("❌ Missing column: 'SKU#'")
    if "Stock_Qty" not in df.columns:
        warns.append("❌ Missing column: 'Stock Qty'")
    if "SKU" in df.columns and df["SKU"].astype(str).str.strip().eq("").all():
        warns.append("❌ All SKU values are empty")
    return warns


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
