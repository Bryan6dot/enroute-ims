import streamlit as st
import pandas as pd
import json, os, uuid, io
from datetime import datetime, date
from pathlib import Path

st.set_page_config(page_title="Enroute IMS", page_icon="🚲", layout="wide", initial_sidebar_state="expanded")

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & DIRECTORIES
# ══════════════════════════════════════════════════════════════════════════════
LOCATIONS = ["Warehouse", "Cycling Store", "Running Store"]
DATA_DIR  = Path("data")
PO_REG    = DATA_DIR / "po_registry.json"
HIST_FILE = DATA_DIR / "file_history.json"
USERS     = {
    "admin":      {"password": "enroute2026", "name": "Admin",      "role": "Admin"},
    "warehouse":  {"password": "wh2026",      "name": "Warehouse",  "role": "Warehouse"},
    "purchasing": {"password": "po2026",      "name": "Purchasing", "role": "Purchasing"},
}

for d in [DATA_DIR / s for s in ["shopify","inhouse","pos","shipping"]]:
    d.mkdir(parents=True, exist_ok=True)

# ── Keyword lists for column detection ────────────────────────────────────────
PRICE_KW  = ["price","cost","total","amount","valor","precio","importe","costo","subtotal","unit price","unit cost"]
QTY_KW    = ["qty","quantity","pcs","pieces","units","cantidad","piezas","cant","count","unidades"]
DESC_KW   = ["description","descripcion","descripción","item","product","nombre","articulo","artículo","detail","part name","concepto"]

# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENCE
# ══════════════════════════════════════════════════════════════════════════════
def load_json(path):
    try: return json.loads(Path(path).read_text()) if Path(path).exists() else []
    except: return []

def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, default=str))

def save_upload(f, category, meta={}):
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = DATA_DIR / category / f"{ts}_{f.name}"
    dst.write_bytes(f.getbuffer()); f.seek(0)
    hist = load_json(HIST_FILE)
    hist.append({"id": str(uuid.uuid4())[:8], "category": category,
                 "filename": dst.name, "original": f.name, "path": str(dst),
                 "uploaded_at": datetime.now().isoformat(), **meta})
    save_json(HIST_FILE, hist)
    return dst

def save_po_registry():
    save_json(PO_REG, st.session_state.po_registry)

# ══════════════════════════════════════════════════════════════════════════════
# FILE READERS
# ══════════════════════════════════════════════════════════════════════════════
def read_excel_or_csv(source):
    if isinstance(source, Path):
        return pd.read_excel(source) if str(source).endswith((".xlsx",".xls")) else pd.read_csv(source)
    n = source.name.lower()
    if n.endswith((".xlsx",".xls")): return pd.read_excel(source)
    return pd.read_csv(source)

def read_pdf_tables(uploaded_file):
    """Extract all tables from a PDF invoice using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        st.error("Falta librería pdfplumber. Asegúrate de que esté en requirements.txt.")
        return None

    raw = uploaded_file.read(); uploaded_file.seek(0)
    all_frames = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for tbl in tables:
                if not tbl or len(tbl) < 2: continue
                header = [str(c).strip() if c else f"Col{i}" for i, c in enumerate(tbl[0])]
                rows   = [[str(c).strip() if c else "" for c in r] for r in tbl[1:]]
                df = pd.DataFrame(rows, columns=header)
                df = df.loc[:, df.apply(lambda c: c.str.strip().ne("").any())]
                df = df.dropna(how="all")
                if not df.empty: all_frames.append(df)

    if not all_frames:
        st.error("No se encontraron tablas en el PDF. Prueba con el archivo en Excel.")
        return None
    return pd.concat(all_frames, ignore_index=True)

def read_any_file(uploaded_file):
    """Route to correct reader based on file extension."""
    n = uploaded_file.name.lower()
    if n.endswith(".pdf"):     return read_pdf_tables(uploaded_file)
    if n.endswith((".xlsx","xls")): return pd.read_excel(uploaded_file)
    return pd.read_csv(uploaded_file)

# ══════════════════════════════════════════════════════════════════════════════
# SHOPIFY STANDARD EXPORT PROCESSING
# Shopify inventory CSV export columns (exact):
# Handle, Title, Option1 Name, Option1 Value, Option2 Name, Option2 Value,
# SKU, HS Code, COO, Location, Incoming, Unavailable, Committed, Available, On hand
# ══════════════════════════════════════════════════════════════════════════════
SHOPIFY_EXACT = {
    "Handle":        "Handle",
    "Title":         "Title",
    "Option1 Value": "Option1",
    "Option2 Value": "Option2",
    "SKU":           "SKU",
    "Location":      "Location",
    "Incoming":      "Incoming",
    "Unavailable":   "Unavailable",
    "Committed":     "Committed",
    "Available":     "Available",
    "On hand":       "On Hand",
}

def process_shopify(df):
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={k: v for k, v in SHOPIFY_EXACT.items() if k in df.columns})

    # Extract Brand from Handle (first segment before "-") or Title (first word)
    if "Brand" not in df.columns:
        if "Handle" in df.columns:
            df["Brand"] = df["Handle"].astype(str).str.split("-").str[0].str.title()
        elif "Title" in df.columns:
            df["Brand"] = df["Title"].astype(str).str.split().str[0]

    for col in ["SKU","Title","Brand","Location","Available","On Hand","Committed","Incoming","Option1","Option2"]:
        if col not in df.columns: df[col] = ""

    for col in ["Available","On Hand","Committed","Incoming"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Drop rows with no SKU
    df = df[df["SKU"].astype(str).str.strip() != ""]
    return df.reset_index(drop=True)

def process_inhouse(df):
    """Flexible in-house Excel mapper."""
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    # Try to detect columns by keywords
    rename = {}
    for col in df.columns:
        cl = col.lower()
        if "sku" in cl and "SKU" not in rename.values():             rename[col] = "SKU"
        elif any(k in cl for k in ["brand","marca","vendor"]) and "Brand" not in rename.values():    rename[col] = "Brand"
        elif any(k in cl for k in DESC_KW) and "Description" not in rename.values():                rename[col] = "Description"
        elif any(k in cl for k in QTY_KW) and "Qty" not in rename.values():                         rename[col] = "Qty"
        elif any(k in cl for k in ["location","ubicac","store","tienda"]) and "Location" not in rename.values(): rename[col] = "Location"
    df = df.rename(columns=rename)
    for col in ["SKU","Brand","Description","Qty","Location"]:
        if col not in df.columns: df[col] = ""
    df["Qty"] = pd.to_numeric(df["Qty"], errors="coerce").fillna(0).astype(int)
    df = df[df["SKU"].astype(str).str.strip() != ""]
    return df.reset_index(drop=True)

# ══════════════════════════════════════════════════════════════════════════════
# DISCREPANCY ENGINE
# ══════════════════════════════════════════════════════════════════════════════
def compare_inventories(shopify_df, inhouse_df, location):
    sh = shopify_df.copy()
    ih = inhouse_df.copy()

    if "Location" in sh.columns and sh["Location"].astype(str).str.strip().any():
        sh = sh[sh["Location"].astype(str).str.lower().str.contains(location.lower(), na=False)]
    if "Location" in ih.columns and ih["Location"].astype(str).str.strip().any():
        ih = ih[ih["Location"].astype(str).str.lower().str.contains(location.lower(), na=False)]

    sh_g = sh.groupby("SKU", as_index=False)["Available"].sum().rename(columns={"Available":"Shopify_Qty"})
    ih_g = ih.groupby("SKU", as_index=False)["Qty"].sum().rename(columns={"Qty":"InHouse_Qty"})

    merged = sh_g.merge(ih_g, on="SKU", how="outer").fillna(0)
    merged["Shopify_Qty"]  = merged["Shopify_Qty"].astype(int)
    merged["InHouse_Qty"]  = merged["InHouse_Qty"].astype(int)
    merged["Difference"]   = merged["InHouse_Qty"] - merged["Shopify_Qty"]

    def status(r):
        if r["Shopify_Qty"] == 0 and r["InHouse_Qty"] > 0: return "🟡 Solo In-House"
        if r["InHouse_Qty"] == 0 and r["Shopify_Qty"] > 0: return "🟡 Solo Shopify"
        if r["Difference"]  == 0: return "✅ Match"
        return "🔴 Discrepancia"

    merged["Status"] = merged.apply(status, axis=1)
    merged["Diferencia"] = merged["Difference"].apply(lambda x: f"+{x}" if x > 0 else str(x))
    return merged[["SKU","Shopify_Qty","InHouse_Qty","Diferencia","Status"]].sort_values(
        "Difference", key=abs, ascending=False)

def detect_col(df, keywords):
    for c in df.columns:
        if any(k in c.lower() for k in keywords): return c
    return None

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
for k, v in {"page":"📊 Summary","latest_shopify":{},"latest_inhouse":{},
              "latest_shipping":None,"po_registry":load_json(PO_REG)}.items():
    if k not in st.session_state: st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("user_role"):
    _, col, _ = st.columns([1,1.2,1])
    with col:
        st.markdown("## 🚲 Enroute IMS"); st.markdown("##### Inventory Management System"); st.divider()
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Sign In", use_container_width=True, type="primary"):
            u = USERS.get(username)
            if u and u["password"] == password:
                st.session_state.user_role = u["role"]
                st.session_state.user_name = u["name"]
                st.rerun()
            else: st.error("Credenciales incorrectas.")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🚲 Enroute IMS")
    st.caption(f"**{st.session_state.user_name}** · {st.session_state.user_role}")
    st.divider()
    for p in ["📊 Summary","📦 Inventory","📥 Receiving","🚚 Shipping"]:
        if st.button(p, use_container_width=True,
                     type="primary" if st.session_state.page==p else "secondary"):
            st.session_state.page = p; st.rerun()
    st.divider()
    hist = load_json(HIST_FILE)
    st.caption(f"📁 **Modo Reader** · {len(hist)} archivos históricos")
    if hist:
        last = hist[-1]
        st.caption(f"Último: `{last['original']}` · {last['uploaded_at'][:10]}")
    st.divider()
    if st.button("Sign Out", use_container_width=True):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()

page = st.session_state.page

# ══════════════════════════════════════════════════════════════════════════════
# 📊 SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Summary":
    st.title("📊 Summary")
    st.caption("KPIs generales · Distribución por location · Órdenes pendientes")
    st.divider()

    with st.expander("📤 Cargar nuevo set de archivos", expanded=not st.session_state.latest_shopify):
        st.caption("El análisis siempre usa el archivo más reciente. Los anteriores se guardan como historial.")
        c1, c2 = st.columns(2)
        with c1:
            sh_f = st.file_uploader("Export Shopify (CSV estándar)", type=["csv"], key="sum_sh")
            if sh_f:
                df = pd.read_csv(sh_f); sh_f.seek(0)
                save_upload(sh_f, "shopify", {"type":"shopify"})
                st.session_state.latest_shopify["all"] = process_shopify(df)
                st.success(f"✅ Shopify: {len(df):,} filas cargadas.")
        with c2:
            ih_f = st.file_uploader("In-House Inventory (Excel .xlsx)", type=["xlsx","xls"], key="sum_ih")
            if ih_f:
                df = pd.read_excel(ih_f); ih_f.seek(0)
                save_upload(ih_f, "inhouse", {"type":"inhouse"})
                st.session_state.latest_inhouse["all"] = process_inhouse(df)
                st.success(f"✅ In-House: {len(df):,} filas cargadas.")

    sh = st.session_state.latest_shopify.get("all")
    ih = st.session_state.latest_inhouse.get("all")
    po = st.session_state.po_registry

    if sh is None and ih is None:
        st.info("Sube al menos un archivo para activar el Summary.")
        st.stop()

    # ── KPIs ─────────────────────────────────────────────────────────────────
    st.markdown("#### KPIs Generales")
    sh_skus   = sh["SKU"].nunique()         if sh is not None else 0
    sh_units  = int(sh["Available"].sum())  if sh is not None else 0
    ih_skus   = ih["SKU"].nunique()         if ih is not None else 0
    ih_units  = int(ih["Qty"].sum())        if ih is not None else 0
    po_trans  = sum(1 for p in po if p.get("status")=="In Transit")
    po_arr    = sum(1 for p in po if p.get("status")=="Arrived")
    po_part   = sum(1 for p in po if p.get("status")=="Partial Complete")

    k1,k2,k3,k4,k5,k6,k7,k8 = st.columns(8)
    k1.metric("🔷 SKUs Shopify",   sh_skus  or "—")
    k2.metric("📦 Units Shopify",  sh_units or "—")
    k3.metric("🏠 SKUs In-House",  ih_skus  or "—")
    k4.metric("📦 Units In-House", ih_units or "—")
    k5.metric("✈️ In Transit",     po_trans or "—")
    k6.metric("📦 Arrived",        po_arr   or "—")
    k7.metric("⚠️ Partial",        po_part  or "—")
    k8.metric("✅ Completed",      sum(1 for p in po if p.get("status")=="Completed") or "—")

    st.divider()

    # ── Distribution by location ──────────────────────────────────────────────
    st.markdown("#### Distribución de Inventario por Location (Shopify)")
    if sh is not None and "Location" in sh.columns and sh["Location"].astype(str).str.strip().any():
        loc_data = sh.groupby("Location")["Available"].sum().reset_index()
        total    = max(int(loc_data["Available"].sum()), 1)
        cols     = st.columns(max(len(loc_data), 1))
        for i, (_, row) in enumerate(loc_data.iterrows()):
            with cols[i]:
                with st.container(border=True):
                    st.markdown(f"**{row['Location']}**")
                    st.markdown(f"### {int(row['Available']):,} uds.")
                    st.progress(int(row["Available"]) / total)
                    st.caption(f"{row['Available']/total*100:.1f}% del total")
    else:
        st.info("El archivo de Shopify no contiene columna Location con datos.")

    st.divider()

    # ── Brands by location ────────────────────────────────────────────────────
    left, right = st.columns(2)
    with left:
        st.markdown("#### Marcas por Location (Shopify)")
        if sh is not None and "Brand" in sh.columns and "Location" in sh.columns:
            bl = sh[sh["Available"] > 0].groupby(["Location","Brand"])["Available"].sum().reset_index()
            for loc in sorted(bl["Location"].unique()):
                sub = bl[bl["Location"]==loc].sort_values("Available", ascending=False)
                with st.expander(f"📍 {loc} — {sub['Brand'].nunique()} marcas · {int(sub['Available'].sum()):,} uds."):
                    st.dataframe(sub[["Brand","Available"]].rename(columns={"Available":"Units"}),
                                 use_container_width=True, hide_index=True)
        else:
            st.info("Sin datos de marcas.")

    with right:
        st.markdown("#### Estado de POs")
        if not po:
            st.info("No hay POs. Ve a **Receiving** para cargar una factura.")
        else:
            ICONS = {"In Transit":"✈️","Arrived":"📦","Partial Complete":"⚠️","Completed":"✅"}
            for p in reversed(po[-15:]):
                icon = ICONS.get(p.get("status",""),"⚪")
                st.markdown(f"{icon} **{p.get('po_id','—')}** — {p.get('supplier','—')} · ETA: {p.get('eta','—')} · **{p.get('status','—')}**")

# ══════════════════════════════════════════════════════════════════════════════
# 📦 INVENTORY
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📦 Inventory":
    st.title("📦 Inventory")
    st.caption("Comparación Shopify vs In-House por location · Detección de discrepancias por SKU")
    st.divider()

    sh = st.session_state.latest_shopify.get("all")
    ih = st.session_state.latest_inhouse.get("all")

    # Upload inline if missing
    if sh is None or ih is None:
        missing = ([("Export Shopify (CSV)","csv",   "inv_sh")] if sh is None else []) + \
                  ([("In-House (Excel .xlsx)","xlsx","inv_ih")] if ih is None else [])
        st.warning(f"Faltan archivos. Cárgalos aquí o ve a **Summary**.")
        cols = st.columns(len(missing))
        for i,(label,ftype,key) in enumerate(missing):
            with cols[i]:
                f = st.file_uploader(label, type=[ftype,"xls"] if ftype=="xlsx" else [ftype], key=key)
                if f:
                    if ftype == "csv":
                        df = pd.read_csv(f); f.seek(0)
                        save_upload(f,"shopify",{"type":"shopify"})
                        st.session_state.latest_shopify["all"] = process_shopify(df)
                    else:
                        df = pd.read_excel(f); f.seek(0)
                        save_upload(f,"inhouse",{"type":"inhouse"})
                        st.session_state.latest_inhouse["all"] = process_inhouse(df)
                    st.rerun()
        if sh is None or ih is None: st.stop()

    # ── Per-location comparison ───────────────────────────────────────────────
    for location in LOCATIONS:
        st.markdown(f"---")
        st.markdown(f"### 📍 {location}")
        col_sh, col_ih = st.columns(2)

        # Filter data for this location
        def loc_filter(df, key, loc):
            if "Location" not in df.columns or not df["Location"].astype(str).str.strip().any():
                return df
            return df[df["Location"].astype(str).str.lower().str.contains(loc.lower(), na=False)]

        loc_sh = loc_filter(sh, "Location", location)
        loc_ih = loc_filter(ih, "Location", location)

        with col_sh:
            with st.container(border=True):
                st.caption("**Shopify** — Export oficial")
                if loc_sh.empty:
                    st.warning(f"Sin registros de Shopify para '{location}'")
                else:
                    show = [c for c in ["SKU","Brand","Title","Option1","Option2","Available","On Hand","Committed"] if c in loc_sh.columns]
                    st.dataframe(loc_sh[show].reset_index(drop=True), use_container_width=True, hide_index=True)
                    st.caption(f"SKUs: {loc_sh['SKU'].nunique()} · Units: {int(loc_sh['Available'].sum()):,}")

        with col_ih:
            with st.container(border=True):
                st.caption("**In House** — Conteo almacén")
                if loc_ih.empty:
                    st.warning(f"Sin registros In-House para '{location}'")
                else:
                    show = [c for c in ["SKU","Brand","Description","Qty"] if c in loc_ih.columns]
                    st.dataframe(loc_ih[show].reset_index(drop=True), use_container_width=True, hide_index=True)
                    st.caption(f"SKUs: {loc_ih['SKU'].nunique()} · Units: {int(loc_ih['Qty'].sum()):,}")

        # ── Discrepancy table ─────────────────────────────────────────────────
        st.markdown(f"##### 🔍 Discrepancias — {location}")
        disc = compare_inventories(sh, ih, location)

        if disc.empty:
            st.info("Sin datos suficientes para comparar.")
        else:
            matches  = (disc["Status"]=="✅ Match").sum()
            disc_cnt = (disc["Status"]=="🔴 Discrepancia").sum()
            only_sh  = (disc["Status"]=="🟡 Solo Shopify").sum()
            only_ih  = (disc["Status"]=="🟡 Solo In-House").sum()

            m1,m2,m3,m4 = st.columns(4)
            m1.metric("✅ Match",           matches)
            m2.metric("🔴 Discrepancias",   disc_cnt, delta_color="inverse")
            m3.metric("🟡 Solo en Shopify", only_sh)
            m4.metric("🟡 Solo In-House",   only_ih)

            def color_disc(row):
                if "Match"        in row["Status"]: return ["background-color:#E8F5E9"]*len(row)
                if "Solo"         in row["Status"]: return ["background-color:#FFF9C4"]*len(row)
                if "Discrepancia" in row["Status"]: return ["background-color:#FFEBEE"]*len(row)
                return [""]*len(row)

            st.dataframe(disc.style.apply(color_disc, axis=1), use_container_width=True, hide_index=True)

            only_disc = disc[disc["Status"] != "✅ Match"]
            if not only_disc.empty:
                st.download_button(
                    f"📥 Exportar discrepancias — {location}",
                    data=only_disc.to_csv(index=False).encode("utf-8"),
                    file_name=f"disc_{location.replace(' ','_')}_{date.today()}.csv",
                    mime="text/csv", key=f"dl_disc_{location}"
                )

# ══════════════════════════════════════════════════════════════════════════════
# 📥 RECEIVING
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📥 Receiving":
    st.title("📥 Receiving")
    st.caption("Carga facturas (Excel o PDF) · Genera CSV sin precios · Sigue el estatus del embarque")
    st.divider()

    tab_up, tab_track, tab_kpi = st.tabs(["➕ Subir Factura / PO", "📋 Tracker de POs", "📈 KPIs"])

    # ── TAB 1: UPLOAD ─────────────────────────────────────────────────────────
    with tab_up:
        st.markdown("#### Subir Factura")
        st.caption("Acepta **Excel (.xlsx)** y **PDF**. El sistema detecta las columnas de artículos y cantidad, elimina los precios y genera un CSV de seguimiento.")

        po_file = st.file_uploader("Factura / PO", type=["xlsx","xls","pdf"], key="po_up")

        if po_file:
            with st.spinner("Procesando archivo..."):
                df_raw = read_any_file(po_file)

            if df_raw is None: st.stop()

            st.markdown("#### Vista previa del archivo")
            st.dataframe(df_raw.head(30), use_container_width=True, hide_index=True)
            st.divider()

            st.markdown("#### Confirma las columnas")
            all_cols = list(df_raw.columns)
            ca, cb = st.columns(2)
            with ca:
                auto_desc = detect_col(df_raw, DESC_KW)
                col_desc  = st.selectbox("Columna Descripción / Artículo *", all_cols,
                                          index=all_cols.index(auto_desc) if auto_desc in all_cols else 0)
            with cb:
                auto_qty  = detect_col(df_raw, QTY_KW)
                col_qty   = st.selectbox("Columna Cantidad *", all_cols,
                                          index=all_cols.index(auto_qty) if auto_qty in all_cols else 0)

            price_cols  = [c for c in all_cols if any(k in c.lower() for k in PRICE_KW)]
            extra_keep  = st.multiselect("Columnas adicionales a conservar (opcional)",
                                          [c for c in all_cols if c not in [col_desc, col_qty] + price_cols])

            if price_cols:
                st.warning(f"Columnas de precio detectadas y **eliminadas**: `{'` · `'.join(price_cols)}`")

            st.divider()
            p1,p2,p3 = st.columns(3)
            with p1: supplier = st.text_input("Proveedor *", placeholder="Trek Bikes México")
            with p2: eta      = st.date_input("ETA *", min_value=date.today())
            with p3: dest_loc = st.selectbox("Location destino", LOCATIONS)

            if st.button("✅ Procesar y registrar PO", type="primary"):
                if not supplier:
                    st.error("El campo Proveedor es obligatorio.")
                else:
                    keep    = [col_desc, col_qty] + extra_keep
                    df_cl   = df_raw[keep].copy().dropna(subset=[col_desc, col_qty])
                    df_cl   = df_cl.rename(columns={col_desc:"Description", col_qty:"Qty"})
                    df_cl["Qty"] = pd.to_numeric(df_cl["Qty"], errors="coerce").fillna(0)
                    df_cl   = df_cl[df_cl["Qty"] > 0].reset_index(drop=True)
                    df_cl["ETA"]      = str(eta)
                    df_cl["Supplier"] = supplier
                    df_cl["Location"] = dest_loc

                    po_id    = f"PO-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
                    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
                    csv_path = DATA_DIR / "pos" / f"{ts}_{po_id}_clean.csv"
                    df_cl.to_csv(csv_path, index=False)

                    record = {"po_id": po_id, "supplier": supplier, "eta": str(eta),
                              "destination": dest_loc, "status": "In Transit",
                              "created_at": datetime.now().isoformat(),
                              "csv_path": str(csv_path),
                              "total_items": int(df_cl["Qty"].sum()),
                              "total_lines": len(df_cl),
                              "arrived_at": None, "completed_at": None,
                              "history": [{"event":"Created — In Transit","ts":datetime.now().isoformat()}]}
                    st.session_state.po_registry.append(record)
                    save_po_registry()

                    po_file.seek(0)
                    save_upload(po_file, "pos", {"po_id": po_id, "supplier": supplier, "type":"po"})

                    st.success(f"✅ **{po_id}** registrado. Estatus: **In Transit** · ETA: {eta}")
                    st.markdown("#### CSV generado (sin precios)")
                    st.dataframe(df_cl, use_container_width=True, hide_index=True)
                    st.download_button("📥 Descargar CSV limpio", data=df_cl.to_csv(index=False).encode("utf-8"),
                                       file_name=f"{po_id}_items.csv", mime="text/csv")
                    st.rerun()

    # ── TAB 2: TRACKER ────────────────────────────────────────────────────────
    with tab_track:
        st.markdown("#### Tracker de POs")
        pos = st.session_state.po_registry

        if not pos:
            st.info("No hay POs registradas. Sube una factura en la pestaña anterior.")
        else:
            STATUS_ICON  = {"In Transit":"✈️","Arrived":"📦","Partial Complete":"⚠️","Completed":"✅"}
            ALL_STATUS   = ["In Transit","Arrived","Partial Complete","Completed"]
            filt = st.multiselect("Filtrar por estatus", ALL_STATUS, default=ALL_STATUS)

            for po in reversed(pos):
                if po["status"] not in filt: continue
                icon = STATUS_ICON.get(po["status"],"⚪")
                created = datetime.fromisoformat(po["created_at"])
                days    = (datetime.now() - created).days
                with st.expander(
                    f"{icon} **{po['po_id']}** — {po['supplier']} · ETA: {po['eta']} · "
                    f"{po['total_items']:,} uds. · {days}d en sistema · **{po['status']}**"
                ):
                    c1,c2,c3,c4 = st.columns(4)
                    c1.metric("Proveedor",   po["supplier"])
                    c2.metric("ETA",         po["eta"])
                    c3.metric("Destino",     po["destination"])
                    c4.metric("Total items", f"{po['total_items']:,}")

                    for ev in po.get("history",[]):
                        st.caption(f"• {ev['event']} — {ev['ts'][:16]}")

                    # Status update
                    if po["status"] != "Completed":
                        st.markdown("**Actualizar estatus:**")
                        next_s  = [s for s in ALL_STATUS if s != po["status"]]
                        btn_row = st.columns(len(next_s))
                        for i, ns in enumerate(next_s):
                            with btn_row[i]:
                                if st.button(f"{STATUS_ICON.get(ns,'')} → {ns}",
                                             key=f"s_{po['po_id']}_{ns}", use_container_width=True):
                                    for p in st.session_state.po_registry:
                                        if p["po_id"] == po["po_id"]:
                                            p["status"] = ns
                                            p["history"].append({"event": f"→ {ns}",
                                                                  "ts": datetime.now().isoformat()})
                                            if ns == "Arrived":           p["arrived_at"]   = datetime.now().isoformat()
                                            if ns in ("Completed","Partial Complete"): p["completed_at"] = datetime.now().isoformat()
                                    save_po_registry(); st.rerun()

                    if po.get("csv_path") and Path(po["csv_path"]).exists():
                        st.download_button("📥 Descargar CSV del PO",
                                           data=Path(po["csv_path"]).read_bytes(),
                                           file_name=f"{po['po_id']}_items.csv", mime="text/csv",
                                           key=f"dl_{po['po_id']}")

    # ── TAB 3: KPIs ───────────────────────────────────────────────────────────
    with tab_kpi:
        st.markdown("#### KPIs de Recepción")
        pos = st.session_state.po_registry

        if not pos:
            st.info("Sin datos aún.")
        else:
            completed = [p for p in pos if p["status"]=="Completed"]
            partial   = [p for p in pos if p["status"]=="Partial Complete"]
            arrived   = [p for p in pos if p["status"]=="Arrived"]
            transit   = [p for p in pos if p["status"]=="In Transit"]

            k1,k2,k3,k4 = st.columns(4)
            k1.metric("📊 Total POs",         len(pos))
            k2.metric("✅ Completados",        len(completed))
            k3.metric("⚠️ Partial Complete",   len(partial))
            k4.metric("✈️ En tránsito",        len(transit))

            st.divider()

            days_arrive  = [(datetime.fromisoformat(p["arrived_at"])   - datetime.fromisoformat(p["created_at"])).days for p in pos if p.get("arrived_at")]
            days_complete= [(datetime.fromisoformat(p["completed_at"]) - datetime.fromisoformat(p["created_at"])).days for p in pos if p.get("completed_at")]
            days_arr_cmp = [(datetime.fromisoformat(p["completed_at"]) - datetime.fromisoformat(p["arrived_at"])).days  for p in pos if p.get("arrived_at") and p.get("completed_at")]

            st.markdown("#### ⏱️ Tiempos promedio")
            m1,m2,m3 = st.columns(3)
            m1.metric("Días Creado → Arrived",   f"{sum(days_arrive)/len(days_arrive):.1f}"   if days_arrive   else "—", help="Tiempo en tránsito")
            m2.metric("Días Arrived → Completed", f"{sum(days_arr_cmp)/len(days_arr_cmp):.1f}" if days_arr_cmp  else "—", help="Tiempo de entrada al sistema desde recepción física")
            m3.metric("Días Creado → Completed",  f"{sum(days_complete)/len(days_complete):.1f}" if days_complete else "—", help="Tiempo total del proceso")

            st.divider()
            st.markdown("#### Detalle por PO")
            rows = []
            for p in pos:
                cr  = datetime.fromisoformat(p["created_at"])
                d_a = (datetime.fromisoformat(p["arrived_at"])   - cr).days if p.get("arrived_at")   else "—"
                d_c = (datetime.fromisoformat(p["completed_at"]) - cr).days if p.get("completed_at") else "—"
                rows.append({"PO": p["po_id"],"Proveedor": p["supplier"],"ETA": p["eta"],
                              "Status": p["status"],"Creado": p["created_at"][:10],
                              "Días → Arrived": d_a,"Días → Completed": d_c,
                              "Total Uds.": f"{p['total_items']:,}"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# 🚚 SHIPPING
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🚚 Shipping":
    st.title("🚚 Shipping")
    st.caption("Reporte de paquetes enviados por el almacén")
    st.divider()

    tab_up, tab_view = st.tabs(["📤 Subir Reporte","📋 Ver Envíos"])

    with tab_up:
        st.markdown("#### Subir reporte de envíos")
        st.caption("El almacén sube el reporte de paquetes enviados (Excel o CSV). Cada reporte se guarda como historial.")
        sf = st.file_uploader("Reporte de envíos (Excel / CSV)", type=["xlsx","xls","csv"], key="ship_up")
        if sf:
            try:
                df = read_excel_or_csv(sf)
                st.markdown("#### Vista previa")
                st.dataframe(df.head(20), use_container_width=True, hide_index=True)
                if st.button("✅ Guardar reporte", type="primary"):
                    sf.seek(0); save_upload(sf,"shipping",{"type":"shipping"})
                    st.session_state.latest_shipping = df
                    st.success(f"✅ Reporte guardado — {len(df):,} registros.")
                    st.rerun()
            except Exception as e: st.error(f"Error: {e}")

    with tab_view:
        ship = st.session_state.latest_shipping
        if ship is None:
            files = sorted((DATA_DIR/"shipping").glob("*"), reverse=True)
            if files:
                try: ship = read_excel_or_csv(files[0]); st.session_state.latest_shipping = ship
                except: pass

        if ship is None:
            st.info("No hay reportes cargados.")
        else:
            st.markdown(f"**{len(ship):,} registros · Reporte más reciente**")
            k1,k2,k3,k4 = st.columns(4)
            k1.metric("📦 Total envíos", len(ship))
            qc = detect_col(ship, QTY_KW)
            if qc: k2.metric("🔢 Unidades", int(pd.to_numeric(ship[qc],errors="coerce").sum()))
            dc = detect_col(ship, ["date","fecha","ship"])
            if dc: k3.metric("📅 Período", f"{str(ship[dc].min())[:10]} → {str(ship[dc].max())[:10]}")
            cc = detect_col(ship, ["carrier","courier","paqueteria"])
            if cc: k4.metric("🚚 Carriers", ship[cc].nunique())

            st.divider()
            srch = st.text_input("Buscar", placeholder="Orden, tracking, SKU...")
            if srch:
                mask = ship.apply(lambda c: c.astype(str).str.contains(srch,case=False,na=False)).any(axis=1)
                display = ship[mask]
            else: display = ship
            st.dataframe(display, use_container_width=True, hide_index=True)
            st.caption(f"{len(display):,} de {len(ship):,} registros")
            st.download_button("📥 Descargar reporte",
                               data=ship.to_csv(index=False).encode("utf-8"),
                               file_name=f"shipping_{date.today()}.csv", mime="text/csv")

            st.divider()
            st.markdown("#### 📂 Historial de reportes")
            hist_s = [h for h in load_json(HIST_FILE) if h.get("category")=="shipping"]
            if hist_s:
                st.dataframe(pd.DataFrame([{"Fecha":h["uploaded_at"][:16],"Archivo":h["original"]} for h in hist_s]),
                             use_container_width=True, hide_index=True)
