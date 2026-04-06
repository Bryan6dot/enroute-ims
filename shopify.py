import requests
import streamlit as st
import pandas as pd
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────────
def get_shopify_config():
    """Read Shopify credentials from Streamlit secrets."""
    try:
        return {
            "shop":  st.secrets["shopify"]["shop_url"],   # e.g. enroute.myshopify.com
            "token": st.secrets["shopify"]["admin_token"], # Admin API access token
        }
    except Exception:
        return {"shop": "DEMO_MODE", "token": "DEMO_MODE"}


# ── Shopify API ─────────────────────────────────────────────────────────────
class ShopifyClient:
    def __init__(self):
        cfg = get_shopify_config()
        self.base = f"https://{cfg['shop']}/admin/api/2024-01"
        self.headers = {
            "X-Shopify-Access-Token": cfg["token"],
            "Content-Type": "application/json",
        }
        self.demo = cfg["token"] == "DEMO_MODE"

    def _get(self, endpoint):
        if self.demo:
            return None
        r = requests.get(f"{self.base}{endpoint}", headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def _post(self, endpoint, payload):
        if self.demo:
            return {"demo": True}
        r = requests.post(f"{self.base}{endpoint}", headers=self.headers,
                          json=payload, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_locations(self):
        data = self._get("/locations.json")
        if data:
            return data.get("locations", [])
        return DEMO_LOCATIONS

    def get_inventory_levels(self, location_id):
        data = self._get(f"/inventory_levels.json?location_ids={location_id}&limit=250")
        if data:
            return data.get("inventory_levels", [])
        return []

    def adjust_inventory(self, inventory_item_id, location_id, available_adjustment):
        """Apply a delta adjustment (+/-) to a specific SKU at a location."""
        payload = {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available_adjustment": available_adjustment,
        }
        return self._post("/inventory_levels/adjust.json", {"inventory_level": payload})

    def set_inventory(self, inventory_item_id, location_id, available):
        """Set absolute inventory level for a SKU at a location."""
        payload = {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available": available,
        }
        return self._post("/inventory_levels/set.json", {"inventory_level": payload})

    def get_products(self):
        data = self._get("/products.json?limit=250")
        if data:
            return data.get("products", [])
        return DEMO_PRODUCTS

    def get_variant_by_sku(self, sku):
        """Find inventory_item_id for a given SKU."""
        products = self.get_products()
        for product in products:
            for variant in product.get("variants", []):
                if variant.get("sku") == sku:
                    return variant
        return None


# ── Demo data ────────────────────────────────────────────────────────────────
DEMO_LOCATIONS = [
    {"id": 1001, "name": "Central / Warehouse", "active": True},
    {"id": 1002, "name": "Store 1 · Cycling",   "active": True},
    {"id": 1003, "name": "Store 2 · Running",   "active": True},
]

DEMO_PRODUCTS = [
    {"id": 1, "title": "Trek FX3 Disc", "variants": [
        {"sku": "TRK-FX3-L", "inventory_item_id": 101, "title": "Large"},
        {"sku": "TRK-FX3-M", "inventory_item_id": 102, "title": "Medium"},
        {"sku": "TRK-FX3-S", "inventory_item_id": 103, "title": "Small"},
    ]},
    {"id": 2, "title": "Shimano XT M8100", "variants": [
        {"sku": "SHM-XT-M8", "inventory_item_id": 201, "title": "Default"},
    ]},
    {"id": 3, "title": "Gel Sella Pro", "variants": [
        {"sku": "ASS-GEL-P", "inventory_item_id": 301, "title": "Default"},
    ]},
    {"id": 4, "title": "Giro Vantage Helmet", "variants": [
        {"sku": "HELM-GV-M", "inventory_item_id": 401, "title": "Medium"},
        {"sku": "HELM-GV-L", "inventory_item_id": 402, "title": "Large"},
    ]},
]

DEMO_INVENTORY = {
    "TRK-FX3-L": {"Central / Warehouse": 12, "Store 1 · Cycling": 2, "Store 2 · Running": 0},
    "TRK-FX3-M": {"Central / Warehouse": 8,  "Store 1 · Cycling": 3, "Store 2 · Running": 1},
    "TRK-FX3-S": {"Central / Warehouse": 5,  "Store 1 · Cycling": 1, "Store 2 · Running": 0},
    "SHM-XT-M8": {"Central / Warehouse": 2,  "Store 1 · Cycling": 0, "Store 2 · Running": 1},
    "ASS-GEL-P": {"Central / Warehouse": 8,  "Store 1 · Cycling": 3, "Store 2 · Running": 2},
    "HELM-GV-M": {"Central / Warehouse": 0,  "Store 1 · Cycling": 4, "Store 2 · Running": 1},
    "HELM-GV-L": {"Central / Warehouse": 3,  "Store 1 · Cycling": 1, "Store 2 · Running": 0},
}

DEMO_MOVEMENTS = [
    {"fecha": "2026-04-05", "ref": "PO-2026-041", "tipo": "entrada",  "location": "Central", "units": 18, "user": "warehouse"},
    {"fecha": "2026-04-04", "ref": "TRF-021",     "tipo": "traslado", "location": "Central→S1", "units": 6,  "user": "store1"},
    {"fecha": "2026-04-03", "ref": "ADJ-019",     "tipo": "salida",   "location": "Store 2", "units": -3, "user": "store2"},
    {"fecha": "2026-04-02", "ref": "PO-2026-038", "tipo": "entrada",  "location": "Central", "units": 42, "user": "warehouse"},
]

DEMO_POS = [
    {
        "id": "PO-2026-041", "brand": "Trek Bikes", "supplier": "QBP Distributor",
        "items": 8, "units": 24, "eta": "2026-04-08",
        "status": "En tránsito", "location": "Central / Warehouse",
        "created_by": "purchasing", "created_at": "2026-04-01",
        "skus": [
            {"sku": "TRK-FX3-L", "desc": "Trek FX3 Disc Large",  "ordered": 4, "received": 4},
            {"sku": "TRK-FX3-M", "desc": "Trek FX3 Disc Medium", "ordered": 6, "received": 6},
            {"sku": "TRK-FX3-S", "desc": "Trek FX3 Disc Small",  "ordered": 4, "received": 0},
            {"sku": "TRK-ACC-BL","desc": "Trek Accessory Bundle","ordered": 10,"received": 0},
        ],
    },
    {
        "id": "PO-2026-039", "brand": "Shimano", "supplier": "Shimano Direct",
        "items": 12, "units": 60, "eta": "2026-04-12",
        "status": "Parcialmente recibido", "location": "Central / Warehouse",
        "created_by": "purchasing", "created_at": "2026-03-28",
        "skus": [
            {"sku": "SHM-XT-M8", "desc": "Shimano XT M8100", "ordered": 20, "received": 10},
        ],
    },
    {
        "id": "PO-2026-037", "brand": "Garmin", "supplier": "CDN Cycling Supply",
        "items": 5, "units": 15, "eta": "2026-04-18",
        "status": "En tránsito", "location": "Central / Warehouse",
        "created_by": "purchasing", "created_at": "2026-03-25",
        "skus": [],
    },
    {
        "id": "PO-2026-034", "brand": "Giro Helmets", "supplier": "Sport Systems",
        "items": 6, "units": 18, "eta": "2026-04-01",
        "status": "Recibido", "location": "Central / Warehouse",
        "created_by": "purchasing", "created_at": "2026-03-20",
        "skus": [],
    },
]


# ── Excel template columns ───────────────────────────────────────────────────
TEMPLATE_COLUMNS = ["SKU", "Descripcion", "Cantidad", "Tipo", "Location", "Referencia"]
VALID_TYPES      = ["entrada", "salida", "traslado", "recepcion"]
VALID_LOCATIONS  = ["Central / Warehouse", "Store 1 · Cycling", "Store 2 · Running"]


def build_template_df():
    return pd.DataFrame([
        ["TRK-FX3-L", "Trek FX3 Disc Large",  2, "entrada",  "Central / Warehouse",  "PO-2026-041"],
        ["SHM-XT-M8", "Shimano XT M8100",      4, "traslado", "Central / Warehouse",  "TRF-021"],
        ["ASS-GEL-P", "Gel Sella Pro",         3, "salida",   "Store 2 · Running",    ""],
    ], columns=TEMPLATE_COLUMNS)


def validate_excel(df: pd.DataFrame):
    """Returns df with a 'validation' column and a list of error messages."""
    errors = []
    required = set(TEMPLATE_COLUMNS)
    missing  = required - set(df.columns)
    if missing:
        return df, [f"Columnas faltantes: {missing}"]

    known_skus = {
        sku
        for p in DEMO_PRODUCTS
        for v in p["variants"]
        for sku in [v["sku"]]
    }

    statuses = []
    for i, row in df.iterrows():
        issues = []
        if str(row["SKU"]) not in known_skus:
            issues.append("SKU no existe en Shopify")
        if str(row["Tipo"]).lower() not in VALID_TYPES:
            issues.append(f"Tipo inválido: {row['Tipo']}")
        if str(row["Location"]) not in VALID_LOCATIONS:
            issues.append(f"Location inválida: {row['Location']}")
        try:
            if int(row["Cantidad"]) <= 0:
                issues.append("Cantidad debe ser > 0")
        except Exception:
            issues.append("Cantidad no numérica")

        if issues:
            statuses.append("❌ " + " · ".join(issues))
            errors.append(f"Fila {i+2}: {' | '.join(issues)}")
        elif str(row["Tipo"]).lower() == "salida":
            loc  = str(row["Location"])
            sku  = str(row["SKU"])
            curr = DEMO_INVENTORY.get(sku, {}).get(loc, 0)
            if curr < int(row["Cantidad"]):
                statuses.append("⚠️ Stock insuficiente")
            else:
                statuses.append("✅ Válido")
        else:
            statuses.append("✅ Válido")

    df = df.copy()
    df["Estado"] = statuses
    return df, errors


# ── Auth guard helper ────────────────────────────────────────────────────────
def require_auth():
    if not st.session_state.get("user_role"):
        st.warning("Inicia sesión para continuar.")
        st.stop()


def role_allowed(allowed_roles: list):
    role = st.session_state.get("user_role", "")
    if role not in allowed_roles:
        st.error("No tienes permiso para ver esta sección.")
        st.stop()


# ── Status badge helper ──────────────────────────────────────────────────────
STATUS_COLORS = {
    "En tránsito":              "🔵",
    "Parcialmente recibido":    "🟡",
    "Recibido":                 "🟢",
    "Con discrepancia":         "🔴",
}
