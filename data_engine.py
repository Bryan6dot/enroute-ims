"""
data_engine.py — Enroute IMS
Handles all column mapping, normalization, and business logic for:
  - Shopify Inventory Export  (inventoryexport.csv)
  - Shopify Orders Export     (OdersExport.csv / OrdersExport.csv)
"""

import pandas as pd
import numpy as np
from datetime import datetime
import re as _re

# ══════════════════════════════════════════════════════════════════════════════
# EXACT COLUMN NAMES — Shopify Inventory Export
# Full set as confirmed by Enroute team.
# Exact matching avoids the "available" ⊂ "unavailable" substring collision bug.
# "On hand (new)" kept for completeness but not used in calculations.
# ══════════════════════════════════════════════════════════════════════════════
INV_COLS = {
    # Raw Shopify column            →  Internal name
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
    "Available (not editable)":        "Available",   # ← exact match, NOT substring
    "On hand (current)":               "On_Hand",     # ← source of truth for stock
    "On hand (new)":                   "On_Hand_New", # ← edit field, not used in calcs
}

# ══════════════════════════════════════════════════════════════════════════════
# EXACT COLUMN NAMES — Shopify Orders Export
# Full set as confirmed by Enroute team.
# ══════════════════════════════════════════════════════════════════════════════
ORD_COLS = {
    # Raw Shopify column            →  Internal name
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

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _to_num(series: pd.Series) -> pd.Series:
    """Convert column to numeric; 'not stocked' and blanks → 0."""
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _rename_exact(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """
    Rename only columns that exist in the file using exact matching.
    Columns not in the map are dropped (keeps the df clean).
    """
    present = {raw: internal
               for raw, internal in col_map.items()
               if raw in df.columns}
    df = df.rename(columns=present)
    return df[list(present.values())]


# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY PARSER
# ══════════════════════════════════════════════════════════════════════════════
def parse_inventory(file) -> pd.DataFrame:
    """
    Parse the Shopify Inventory Export.
    Returns a clean DataFrame with one row per SKU+Location combination.
    Numeric columns are safe (no 'not stocked' strings).

    Key columns in result:
        SKU, Title, Option1_Value, Option2_Value, Option3_Value,
        Location, Incoming, Unavailable, Committed, Available, On_Hand
    """
    raw = pd.read_csv(file) if isinstance(file, str) else pd.read_csv(file)
    df  = _rename_exact(raw, INV_COLS)

    # Ensure all expected columns exist (guard against partial exports)
    numeric_cols = ["Incoming", "Unavailable", "Committed", "Available", "On_Hand"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = _to_num(df[col])
        else:
            df[col] = 0

    # Drop rows with no SKU (image/blank rows in Shopify exports)
    df = df[df["SKU"].astype(str).str.strip().ne("")].reset_index(drop=True)

    # Build a human-readable variant label
    def variant_label(row):
        parts = [row.get("Option1_Value",""), row.get("Option2_Value",""), row.get("Option3_Value","")]
        return " / ".join(p for p in parts if str(p).strip() not in ["", "nan"])
    df["Variant"] = df.apply(variant_label, axis=1)

    return df


def inventory_by_sku(inv_df: pd.DataFrame) -> pd.DataFrame:
    """
    Consolidate inventory across all locations per SKU.
    Returns one row per SKU with total and per-location breakdown.
    """
    totals = inv_df.groupby("SKU").agg(
        Title       = ("Title",     "first"),
        Variant     = ("Variant",   "first"),
        Total_OnHand  = ("On_Hand",    "sum"),
        Total_Available = ("Available",  "sum"),
        Total_Committed = ("Committed",  "sum"),
        Total_Incoming  = ("Incoming",   "sum"),
    ).reset_index()

    # Per-location pivot for "where are the units"
    loc_pivot = inv_df.pivot_table(
        index="SKU",
        columns="Location",
        values="On_Hand",
        aggfunc="sum",
        fill_value=0
    ).reset_index()
    loc_pivot.columns.name = None

    result = totals.merge(loc_pivot, on="SKU", how="left")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# ORDERS PARSER
# ══════════════════════════════════════════════════════════════════════════════
def parse_orders(file) -> pd.DataFrame:
    """
    Parse the Shopify Orders Export.
    Returns a clean DataFrame with one row per ORDER LINE ITEM.

    Key columns in result:
        Order_ID, Financial_Status, Fulfillment_Status,
        Created_At, Fulfilled_At, SKU, Item_Name,
        Qty_Ordered, Unit_Price, Line_Fulfillment,
        Shipping_Method, Store_Location, Vendor, Total
    """
    raw = pd.read_csv(file) if isinstance(file, str) else pd.read_csv(file)
    df  = _rename_exact(raw, ORD_COLS)

    # Parse timestamps
    for ts_col in ["Created_At", "Fulfilled_At", "Paid_At", "Cancelled_At"]:
        if ts_col in df.columns:
            df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")

    # Numeric
    for num_col in ["Qty_Ordered", "Unit_Price", "Subtotal", "Total"]:
        if num_col in df.columns:
            df[num_col] = _to_num(df[num_col])

    # Normalize status to lowercase for consistent filtering
    for s_col in ["Financial_Status", "Fulfillment_Status", "Line_Fulfillment"]:
        if s_col in df.columns:
            df[s_col] = df[s_col].fillna("").str.lower().str.strip()

    # Clean SKU
    if "SKU" in df.columns:
        df["SKU"] = df["SKU"].astype(str).str.strip()

    return df


def orders_summary(ord_df: pd.DataFrame) -> dict:
    """
    Compute order-level KPIs from the orders DataFrame.

    Returns a dict with:
        total_orders       — unique order count
        fulfilled          — count shipped
        unfulfilled        — paid but not yet started
        partial            — partially shipped
        pending_payment    — not paid yet
        refunded           — refunded orders
        cancelled          — cancelled orders
        avg_processing_hrs — avg hours from creation to fulfillment (fulfilled orders)
        min_processing_hrs
        max_processing_hrs
    """
    # Deduplicate to order level for status counts
    orders = ord_df.drop_duplicates("Order_ID").copy()
    total  = len(orders)

    ful   = (orders["Fulfillment_Status"] == "fulfilled").sum()
    unful = (orders["Fulfillment_Status"] == "unfulfilled").sum()
    part  = (orders["Fulfillment_Status"] == "partial").sum()
    pend  = (orders["Financial_Status"] == "pending").sum()
    refnd = orders["Financial_Status"].isin(["refunded", "partially_refunded"]).sum()
    canc  = orders["Cancelled_At"].notna().sum() if "Cancelled_At" in orders.columns else 0

    # Processing time: Created_At → Fulfilled_At (fulfilled orders only)
    done = orders[
        (orders["Fulfillment_Status"] == "fulfilled") &
        orders["Fulfilled_At"].notna() &
        orders["Created_At"].notna()
    ].copy()
    done["proc_hrs"] = (done["Fulfilled_At"] - done["Created_At"]).dt.total_seconds() / 3600
    done = done[done["proc_hrs"] > 0]

    avg_hrs = round(done["proc_hrs"].mean(), 1) if len(done) else 0
    min_hrs = round(done["proc_hrs"].min(),  1) if len(done) else 0
    max_hrs = round(done["proc_hrs"].max(),  1) if len(done) else 0

    return {
        "total_orders":       total,
        "fulfilled":          int(ful),
        "unfulfilled":        int(unful),
        "partial":            int(part),
        "pending_payment":    int(pend),
        "refunded":           int(refnd),
        "cancelled":          int(canc),
        "avg_processing_hrs": avg_hrs,
        "min_processing_hrs": min_hrs,
        "max_processing_hrs": max_hrs,
    }


# ══════════════════════════════════════════════════════════════════════════════
# FULFILLABILITY CHECK — Can inventory cover open orders?
# ══════════════════════════════════════════════════════════════════════════════
def check_fulfillability(ord_df: pd.DataFrame, inv_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each OPEN (unfulfilled / partial) order line item, check whether
    the available inventory is sufficient to fulfill it.
    Includes Incoming stock (Shopify internal transfers) in the available count.

    Returns a DataFrame with columns:
        Order_ID, SKU, Item_Name, Qty_Ordered,
        Available_Stock, Incoming_Stock, Can_Fulfill, Gap
    """
    open_lines = ord_df[
        ord_df["Fulfillment_Status"].isin(["unfulfilled", "partial", ""])
    ][["Order_ID","SKU","Item_Name","Qty_Ordered","Financial_Status"]].copy()

    open_lines["SKU"] = open_lines["SKU"].astype(str).str.strip()
    open_lines = open_lines[open_lines["SKU"].ne("") & open_lines["SKU"].ne("nan") & open_lines["SKU"].notna()]

    # Consolidated available + incoming per SKU
    stock = inv_df.groupby("SKU").agg(
        Available_Stock=("Available","sum"),
        Incoming_Stock =("Incoming", "sum"),
    ).reset_index()

    merged = open_lines.merge(stock, on="SKU", how="left")
    merged["Available_Stock"] = merged["Available_Stock"].fillna(0).astype(int)
    merged["Incoming_Stock"]  = merged["Incoming_Stock"].fillna(0).astype(int)
    merged["Effective_Stock"] = merged["Available_Stock"] + merged["Incoming_Stock"]
    merged["Can_Fulfill"]     = merged["Effective_Stock"] >= merged["Qty_Ordered"]
    merged["Gap"]             = (merged["Qty_Ordered"] - merged["Effective_Stock"]).clip(lower=0).astype(int)

    return merged.sort_values("Can_Fulfill").reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY MATCH — Shopify vs Warehouse (In Store / physical location)
# ══════════════════════════════════════════════════════════════════════════════
def inventory_match(inv_df: pd.DataFrame,
                    warehouse_location: str = "In Store") -> dict:
    """
    Compare Shopify 'On_Hand' stock vs a specific physical location.
    In Enroute's case, 'In Store' is the physical warehouse location.

    Returns:
        match_pct         — % of SKUs where On_Hand == Available (exact match)
        total_skus        — total SKUs evaluated
        matched_skus      — SKUs that match exactly
        discrepancy_skus  — SKUs with a difference
        detail_df         — DataFrame with per-SKU comparison
    """
    loc_df = inv_df[inv_df["Location"] == warehouse_location].copy()

    if loc_df.empty:
        return {
            "match_pct": 0, "total_skus": 0,
            "matched_skus": 0, "discrepancy_skus": 0,
            "detail_df": pd.DataFrame()
        }

    loc_df = loc_df[loc_df["SKU"].str.strip().ne("")]

    # Group by SKU (in case of duplicates within same location)
    grp = loc_df.groupby("SKU").agg(
        Title     = ("Title",     "first"),
        Variant   = ("Variant",   "first"),
        On_Hand   = ("On_Hand",   "sum"),
        Available = ("Available", "sum"),
        Committed = ("Committed", "sum"),
    ).reset_index()

    grp["Difference"] = grp["On_Hand"] - grp["Available"]
    grp["Status"] = grp["Difference"].apply(
        lambda d: "✅ Match" if d == 0 else ("🔴 Discrepancy" if d != 0 else "⚪ No Stock")
    )

    # Override: both zero = no stock, not a real match for reporting
    grp.loc[(grp["On_Hand"] == 0) & (grp["Available"] == 0), "Status"] = "⚪ No Stock"

    total       = len(grp)
    matched     = (grp["Status"] == "✅ Match").sum()
    discrepancy = (grp["Status"] == "🔴 Discrepancy").sum()
    no_stock    = (grp["Status"] == "⚪ No Stock").sum()
    active      = total - no_stock  # SKUs that actually have some stock to compare

    match_pct = round((matched / active * 100), 1) if active > 0 else 0

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
# QUICK VALIDATION — call this to verify files loaded correctly
# ══════════════════════════════════════════════════════════════════════════════
def validate_inventory_file(df: pd.DataFrame) -> list[str]:
    """Return list of warnings if required columns are missing or data looks wrong."""
    warnings = []
    required = ["SKU", "Location", "Available", "On_Hand"]
    for col in required:
        if col not in df.columns:
            warnings.append(f"❌ Missing required column: '{col}'")
    if "SKU" in df.columns and df["SKU"].str.strip().eq("").all():
        warnings.append("❌ All SKU values are empty")
    if "Available" in df.columns and df["Available"].sum() == 0:
        warnings.append("⚠️ Available stock is 0 for all rows — check file format")
    return warnings


def validate_orders_file(df: pd.DataFrame) -> list[str]:
    """Return list of warnings for orders file."""
    warnings = []
    required = ["Order_ID", "Fulfillment_Status", "Created_At", "SKU", "Qty_Ordered"]
    for col in required:
        if col not in df.columns:
            warnings.append(f"❌ Missing required column: '{col}'")
    return warnings

# ══════════════════════════════════════════════════════════════════════════════
# WAREHOUSE RECONCILIATION
# ══════════════════════════════════════════════════════════════════════════════
WH_COLS = {
    "Location": "WH_Location", "Brand": "Brand", "Type": "Type",
    "Description": "WH_Description", "Gender": "Gender", "Color": "Color",
    "Size": "Size", "SKU#": "SKU", "Stock Qty": "WH_Qty",
}

def parse_warehouse(file) -> pd.DataFrame:
    fname = getattr(file, "name", "")
    raw = pd.read_csv(file) if fname.lower().endswith(".csv") else pd.read_excel(file)
    col_map = {}
    for wh_col, internal in WH_COLS.items():
        for c in raw.columns:
            if wh_col.lower() == c.lower().strip():
                col_map[c] = internal; break
        if internal not in col_map.values():
            for c in raw.columns:
                if wh_col.lower() in c.lower():
                    col_map[c] = internal; break
    df = raw.rename(columns=col_map)
    keep = [v for v in WH_COLS.values() if v in df.columns]
    df = df[keep].copy()
    df["SKU"] = df["SKU"].astype(str).str.strip()
    df = df[df["SKU"].ne("") & df["SKU"].ne("nan")].reset_index(drop=True)
    if "WH_Qty" in df.columns:
        df["WH_Qty"] = _to_num(df["WH_Qty"]).astype(int)
    return df


# ── SKU normalization helpers ─────────────────────────────────────────────────
_GENDER_MAP = {
    "m": "M", "men": "M", "mens": "M", "male": "M", "hombre": "M", "man": "M",
    "w": "W", "women": "W", "womens": "W", "female": "W", "mujer": "W", "wmn": "W",
}

def _normalize_size_zeros(sku: str) -> str:
    """3MF10270753-08.5 → 3MF10270753-8.5  (and vice versa stored as candidate)"""
    return _re.sub(r'(?<=-)(0+)(\d)', r'\2', sku)

def _add_zero_size(sku: str) -> str:
    """3MF10270753-8.5 → 3MF10270753-08.5"""
    return _re.sub(r'(?<=-)(\d)(\.\d)', r'0\1\2', sku)

def _gender_prefix(gender_val: str) -> str:
    return _GENDER_MAP.get(str(gender_val).strip().lower(), "")

def _sku_candidates(wh_sku: str, gender_val: str) -> list[str]:
    """Return ordered list of Shopify SKU candidates to try for a given WH SKU."""
    base = wh_sku.strip()
    norm = _normalize_size_zeros(base)   # remove leading zero
    zero = _add_zero_size(base)          # add leading zero

    candidates = [base, norm, zero]

    gp = _gender_prefix(gender_val)
    if gp:
        # Insert gender prefix before last dash-segment: BASE-SIZE → BASE-[M/W]SIZE
        for src in [base, norm, zero]:
            m = _re.match(r'^(.*-)([^-]+)$', src)
            if m:
                candidates.append(m.group(1) + gp + m.group(2))

    # Deduplicate preserving order
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def reconcile_warehouse(wh_df: pd.DataFrame, inv_df: pd.DataFrame,
                         shopify_location: str = "Online") -> pd.DataFrame:
    """
    Match warehouse SKUs against Shopify Online location.
    WH-driven: only WH SKUs are evaluated.
    Applies SKU normalization: gender prefix (M/W) + leading-zero size variants.
    """
    shop = inv_df[inv_df["Location"].str.strip().str.lower() == shopify_location.lower()]
    shop_agg = shop.groupby("SKU").agg(
        Title=("Title", "first"),
        Shopify_OnHand=("On_Hand", "sum"),
        Shopify_Available=("Available", "sum"),
    ).reset_index()
    shop_dict = shop_agg.set_index("SKU").to_dict("index")

    agg_dict: dict = {"WH_Qty": ("WH_Qty", "sum")}
    if "WH_Description" in wh_df.columns: agg_dict["WH_Desc"] = ("WH_Description", "first")
    if "Gender"         in wh_df.columns: agg_dict["Gender"]  = ("Gender",          "first")
    wh_agg = wh_df.groupby("SKU").agg(**agg_dict).reset_index()

    rows = []
    for _, row in wh_agg.iterrows():
        wh_sku  = row["SKU"]
        gender  = row.get("Gender", "") if "Gender" in wh_agg.columns else ""
        cands   = _sku_candidates(wh_sku, str(gender))

        matched_sku = next((c for c in cands if c in shop_dict), None)
        exact       = matched_sku == wh_sku if matched_sku else False
        s           = shop_dict[matched_sku] if matched_sku else {}

        rows.append({
            "WH_SKU":           wh_sku,
            "Shopify_SKU":      matched_sku or "—",
            "Match_Type":       "Exact" if exact else ("Normalized" if matched_sku else "Not Found"),
            "WH_Desc":          row.get("WH_Desc", ""),
            "Title":            s.get("Title", ""),
            "WH_Qty":           int(row["WH_Qty"]),
            "Shopify_OnHand":   int(s.get("Shopify_OnHand", 0)),
            "Shopify_Available":int(s.get("Shopify_Available", 0)),
        })

    df = pd.DataFrame(rows)
    df["Delta"] = df["Shopify_OnHand"] - df["WH_Qty"]
    df["Status"] = df.apply(lambda r:
        "⚠️ No encontrado" if r["Match_Type"] == "Not Found" else
        ("✅ Match"        if r["Delta"] == 0  else
        ("🔴 Shopify+"    if r["Delta"] >  0  else "🔵 WH+")), axis=1)

    return df.sort_values("Delta", key=abs, ascending=False).reset_index(drop=True)
