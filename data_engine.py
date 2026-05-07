"""
data_engine.py — Enroute IMS
Handles all column mapping, normalization, and business logic for:
  - Shopify Inventory Export  (CC and RR stores)
  - Shopify Orders Export     (CC and RR stores)
  - Warehouse Export          (Online location — shared central warehouse)
"""

import io
import re
import pandas as pd
import numpy as np
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════════
# ENCODING HELPER
# ══════════════════════════════════════════════════════════════════════════════
def _detect_encoding(raw_bytes: bytes) -> str:
    """Try common encodings; latin-1 is the final fallback (never raises)."""
    for enc in ["utf-8", "windows-1252", "latin-1"]:
        try:
            raw_bytes.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _read_csv(file) -> pd.DataFrame:
    """Read a CSV from a file path or Streamlit UploadedFile, auto-detecting encoding."""
    raw = file.read() if hasattr(file, "read") else open(file, "rb").read()
    enc = _detect_encoding(raw)
    return pd.read_csv(io.BytesIO(raw), encoding=enc, encoding_errors="replace")


# ══════════════════════════════════════════════════════════════════════════════
# SKU NORMALIZATION
# ══════════════════════════════════════════════════════════════════════════════
def normalize_sku(sku) -> str:
    """
    Strip all non-alphanumeric characters and lowercase.
    Examples:
        '3MF10263318-10.5'  → '3mf10263318105'
        '3MF10263318- 10,5' → '3mf10263318105'
        'X000010253019 '    → 'x000010253019'
        'HELM-GV-M'         → 'helmgvm'
    """
    return re.sub(r"[^a-z0-9]", "", str(sku).lower().strip())


# ══════════════════════════════════════════════════════════════════════════════
# COLUMN MAPS
# ══════════════════════════════════════════════════════════════════════════════
INV_COLS = {
    "Handle":                          "Handle",
    "Title":                           "Title",
    "Option1 Name":                    "Option1_Name",
    "Option1 Value":                   "Option1_Value",
    "Option2 Name":                    "Option2_Name",
    "Option2 Value":                   "Option2_Value",
    "Option3 Name":                    "Option3_Name",
    "Option3 Value":                   "Option3_Value",
    "SKU":                             "SKU",
    "HS Code":                         "HS_Code",
    "COO":                             "COO",
    "Location":                        "Location",
    "Bin name":                        "Bin_Name",
    "Incoming (not editable)":         "Incoming",
    "Unavailable (not editable)":      "Unavailable",
    "Committed (not editable)":        "Committed",
    "Available (not editable)":        "Available",
    "On hand (current)":               "On_Hand",
    "On hand (new)":                   "On_Hand_New",
}

ORD_COLS = {
    "Name":                            "Order_ID",
    "Email":                           "Email",
    "Financial Status":                "Financial_Status",
    "Paid at":                         "Paid_At",
    "Fulfillment Status":              "Fulfillment_Status",
    "Fulfilled at":                    "Fulfilled_At",
    "Accepts Marketing":               "Accepts_Marketing",
    "Currency":                        "Currency",
    "Subtotal":                        "Subtotal",
    "Shipping":                        "Shipping_Cost",
    "Taxes":                           "Taxes",
    "Total":                           "Total",
    "Discount Code":                   "Discount_Code",
    "Discount Amount":                 "Discount_Amount",
    "Shipping Method":                 "Shipping_Method",
    "Created at":                      "Created_At",
    "Lineitem quantity":               "Qty_Ordered",
    "Lineitem name":                   "Item_Name",
    "Lineitem price":                  "Unit_Price",
    "Lineitem compare at price":       "Compare_At_Price",
    "Lineitem sku":                    "SKU",
    "Lineitem requires shipping":      "Requires_Shipping",
    "Lineitem taxable":                "Taxable",
    "Lineitem fulfillment status":     "Line_Fulfillment",
    "Billing Name":                    "Billing_Name",
    "Billing Street":                  "Billing_Street",
    "Billing Address1":                "Billing_Address1",
    "Billing Address2":                "Billing_Address2",
    "Billing Company":                 "Billing_Company",
    "Billing City":                    "Billing_City",
    "Billing Zip":                     "Billing_Zip",
    "Billing Province":                "Billing_Province",
    "Billing Country":                 "Billing_Country",
    "Billing Phone":                   "Billing_Phone",
    "Shipping Name":                   "Shipping_Name",
    "Shipping Address1":               "Shipping_Address1",
    "Shipping Address2":               "Shipping_Address2",
    "Shipping Company":                "Shipping_Company",
    "Shipping City":                   "Shipping_City",
    "Shipping Zip":                    "Shipping_Zip",
    "Shipping Province":               "Shipping_Province",
    "Shipping Country":                "Shipping_Country",
    "Shipping Phone":                  "Shipping_Phone",
    "Notes":                           "Notes",
    "Note Attributes":                 "Note_Attributes",
    "Cancelled at":                    "Cancelled_At",
    "Payment Method":                  "Payment_Method",
    "Payment Reference":               "Payment_Reference",
    "Refunded Amount":                 "Refunded_Amount",
    "Vendor":                          "Vendor",
}

# Warehouse export column map — flexible to handle slight header variations
WH_COLS = {
    "SKU#":        "SKU",
    "SKU":         "SKU",          # fallback if header is just "SKU"
    "Description": "Description",
    "Stock Qty":   "Stock_Qty",
    "Qty":         "Stock_Qty",    # fallback
    "Brand":       "Brand",
    "Type":        "Type",
    "Gender":      "Gender",
    "Color":       "Color",
    "Size":        "Size",
    "Location":    "Location",
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _rename_exact(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """Rename only columns present in the file using exact matching."""
    present = {raw: internal for raw, internal in col_map.items() if raw in df.columns}
    df = df.rename(columns=present)
    return df[list(present.values())]


# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY PARSER  (Shopify export — CC or RR)
# ══════════════════════════════════════════════════════════════════════════════
def parse_inventory(file) -> pd.DataFrame:
    raw = _read_csv(file)
    df  = _rename_exact(raw, INV_COLS)

    numeric_cols = ["Incoming", "Unavailable", "Committed", "Available", "On_Hand"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = _to_num(df[col])
        else:
            df[col] = 0

    df = df[df["SKU"].astype(str).str.strip().ne("")].reset_index(drop=True)

    def variant_label(row):
        parts = [row.get("Option1_Value",""), row.get("Option2_Value",""), row.get("Option3_Value","")]
        return " / ".join(p for p in parts if str(p).strip() not in ["", "nan"])
    df["Variant"] = df.apply(variant_label, axis=1)

    # ── Normalize SKU for cross-source matching ───────────────────────────
    df["SKU_norm"] = df["SKU"].apply(normalize_sku)

    return df


# ══════════════════════════════════════════════════════════════════════════════
# WAREHOUSE PARSER  (Online location — shared central warehouse)
# ══════════════════════════════════════════════════════════════════════════════
def parse_warehouse(file) -> pd.DataFrame:
    """
    Parse the central warehouse export.
    Expected columns: Location, Brand, Type, Description, Gender, Color, Size, SKU#, Stock Qty
    Returns a clean DataFrame with SKU_norm for joining to Shopify exports.
    """
    raw = _read_csv(file)

    # Rename whatever columns are present
    df = raw.rename(columns={k: v for k, v in WH_COLS.items() if k in raw.columns})

    # Ensure SKU column exists
    if "SKU" not in df.columns:
        raise ValueError("Warehouse file must have a 'SKU#' or 'SKU' column.")

    if "Stock_Qty" not in df.columns:
        df["Stock_Qty"] = 0
    df["Stock_Qty"] = _to_num(df["Stock_Qty"]).astype(int)

    # Keep only rows with a SKU
    df = df[df["SKU"].astype(str).str.strip().ne("")].reset_index(drop=True)

    # ── Normalize SKU ─────────────────────────────────────────────────────
    df["SKU_norm"] = df["SKU"].apply(normalize_sku)

    return df


# ══════════════════════════════════════════════════════════════════════════════
# WAREHOUSE ↔ SHOPIFY MERGE  (normalized SKU join)
# ══════════════════════════════════════════════════════════════════════════════
def merge_warehouse_shopify(
    wh_df: pd.DataFrame,
    sh_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join warehouse stock to Shopify inventory using normalized SKU.
    Preserves original SKU columns for display; SKU_norm is only for matching.

    Result columns added to sh_df:
        WH_SKU        — original warehouse SKU string
        WH_Stock      — warehouse Stock_Qty
        WH_Brand      — brand from warehouse
        WH_Desc       — description from warehouse
        SKU_matched   — True if a warehouse row was found
        SKU_exact     — True if original SKUs match exactly (case-insensitive)
        Stock_Delta   — Shopify On_Hand minus Warehouse Stock_Qty
    """
    wh = wh_df[
        ["SKU", "SKU_norm", "Stock_Qty"]
        + [c for c in ["Brand", "Description"] if c in wh_df.columns]
    ].copy().rename(columns={
        "SKU":         "WH_SKU",
        "Stock_Qty":   "WH_Stock",
        "Brand":       "WH_Brand",
        "Description": "WH_Desc",
    })

    merged = sh_df.merge(wh, on="SKU_norm", how="left")

    merged["SKU_matched"] = merged["WH_Stock"].notna()
    merged["SKU_exact"]   = (
        merged["SKU"].astype(str).str.lower() ==
        merged["WH_SKU"].astype(str).str.lower()
    )
    merged["WH_Stock"]    = merged["WH_Stock"].fillna(0).astype(int)
    merged["Stock_Delta"] = merged["On_Hand"] - merged["WH_Stock"]

    return merged


# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY BY SKU
# ══════════════════════════════════════════════════════════════════════════════
def inventory_by_sku(inv_df: pd.DataFrame) -> pd.DataFrame:
    totals = inv_df.groupby("SKU").agg(
        Title           = ("Title",     "first"),
        Variant         = ("Variant",   "first"),
        Total_OnHand    = ("On_Hand",   "sum"),
        Total_Available = ("Available", "sum"),
        Total_Committed = ("Committed", "sum"),
        Total_Incoming  = ("Incoming",  "sum"),
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
    df  = _rename_exact(raw, ORD_COLS)

    for ts_col in ["Created_At", "Fulfilled_At", "Paid_At", "Cancelled_At"]:
        if ts_col in df.columns:
            df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")

    for num_col in ["Qty_Ordered", "Unit_Price", "Subtotal", "Total"]:
        if num_col in df.columns:
            df[num_col] = _to_num(df[num_col])

    for s_col in ["Financial_Status", "Fulfillment_Status", "Line_Fulfillment"]:
        if s_col in df.columns:
            df[s_col] = df[s_col].fillna("").str.lower().str.strip()

    if "SKU" in df.columns:
        df["SKU"] = df["SKU"].astype(str).str.strip()

    # ── Normalize SKU ─────────────────────────────────────────────────────
    df["SKU_norm"] = df["SKU"].apply(normalize_sku)

    return df


# ══════════════════════════════════════════════════════════════════════════════
# ORDERS SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
def orders_summary(ord_df: pd.DataFrame) -> dict:
    orders = ord_df.drop_duplicates("Order_ID").copy()
    total  = len(orders)

    ful   = (orders["Fulfillment_Status"] == "fulfilled").sum()
    unful = (orders["Fulfillment_Status"] == "unfulfilled").sum()
    part  = (orders["Fulfillment_Status"] == "partial").sum()
    pend  = (orders["Financial_Status"] == "pending").sum()
    refnd = orders["Financial_Status"].isin(["refunded", "partially_refunded"]).sum()
    canc  = orders["Cancelled_At"].notna().sum() if "Cancelled_At" in orders.columns else 0

    done = orders[
        (orders["Fulfillment_Status"] == "fulfilled") &
        orders["Fulfilled_At"].notna() &
        orders["Created_At"].notna()
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
# FULFILLABILITY CHECK
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
        Available_Stock = ("Available", "sum"),
        Incoming_Stock  = ("Incoming",  "sum"),
    ).reset_index()

    merged = open_lines.merge(stock, on="SKU", how="left")
    merged["Available_Stock"] = merged["Available_Stock"].fillna(0).astype(int)
    merged["Incoming_Stock"]  = merged["Incoming_Stock"].fillna(0).astype(int)
    merged["Effective_Stock"] = merged["Available_Stock"] + merged["Incoming_Stock"]
    merged["Can_Fulfill"]     = merged["Effective_Stock"] >= merged["Qty_Ordered"]
    merged["Gap"]             = (merged["Qty_Ordered"] - merged["Effective_Stock"]).clip(lower=0).astype(int)

    return merged.sort_values("Can_Fulfill").reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY MATCH — Shopify vs Warehouse
# ══════════════════════════════════════════════════════════════════════════════
def inventory_match(inv_df: pd.DataFrame, warehouse_location: str = "In Store") -> dict:
    loc_df = inv_df[inv_df["Location"] == warehouse_location].copy()

    if loc_df.empty:
        return {
            "match_pct": 0, "total_skus": 0,
            "matched_skus": 0, "discrepancy_skus": 0,
            "detail_df": pd.DataFrame()
        }

    loc_df = loc_df[loc_df["SKU"].str.strip().ne("")]
    grp = loc_df.groupby("SKU").agg(
        Title     = ("Title",     "first"),
        Variant   = ("Variant",   "first"),
        On_Hand   = ("On_Hand",   "sum"),
        Available = ("Available", "sum"),
        Committed = ("Committed", "sum"),
    ).reset_index()

    grp["Difference"] = grp["On_Hand"] - grp["Available"]
    grp["Status"] = grp["Difference"].apply(
        lambda d: "✅ Match" if d == 0 else "🔴 Discrepancy"
    )
    grp.loc[(grp["On_Hand"] == 0) & (grp["Available"] == 0), "Status"] = "⚪ No Stock"

    total       = len(grp)
    matched     = (grp["Status"] == "✅ Match").sum()
    discrepancy = (grp["Status"] == "🔴 Discrepancy").sum()
    no_stock    = (grp["Status"] == "⚪ No Stock").sum()
    active      = total - no_stock
    match_pct   = round(matched / active * 100, 1) if active > 0 else 0

    return {
        "match_pct":        match_pct,
        "total_skus":       total,
        "active_skus":      int(active),
        "matched_skus":     int(matched),
        "discrepancy_skus": int(discrepancy),
        "no_stock_skus":    int(no_stock),
        "detail_df":        grp.sort_values("Difference", key=abs, ascending=False),
    }


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════════════
def validate_inventory_file(df: pd.DataFrame) -> list[str]:
    warnings = []
    for col in ["SKU", "Location", "Available", "On_Hand"]:
        if col not in df.columns:
            warnings.append(f"❌ Missing required column: '{col}'")
    if "SKU" in df.columns and df["SKU"].str.strip().eq("").all():
        warnings.append("❌ All SKU values are empty")
    if "Available" in df.columns and df["Available"].sum() == 0:
        warnings.append("⚠️ Available stock is 0 for all rows — check file format")
    return warnings


def validate_orders_file(df: pd.DataFrame) -> list[str]:
    warnings = []
    for col in ["Order_ID", "Fulfillment_Status", "Created_At", "SKU", "Qty_Ordered"]:
        if col not in df.columns:
            warnings.append(f"❌ Missing required column: '{col}'")
    return warnings


def validate_warehouse_file(df: pd.DataFrame) -> list[str]:
    warnings = []
    if "SKU" not in df.columns:
        warnings.append("❌ Missing required column: 'SKU#' or 'SKU'")
    if "Stock_Qty" not in df.columns:
        warnings.append("❌ Missing required column: 'Stock Qty' or 'Qty'")
    if "SKU" in df.columns and df["SKU"].str.strip().eq("").all():
        warnings.append("❌ All SKU values are empty")
    return warnings
