import streamlit as st

st.set_page_config(
    page_title="Enroute IMS",
    page_icon="🚲",
    layout="wide",
    initial_sidebar_state="expanded",
)

USERS = {
    "admin":      {"password": "enroute2026", "role": "Admin",      "name": "Admin"},
    "warehouse":  {"password": "wh2026",      "role": "Warehouse",  "name": "Warehouse"},
    "purchasing": {"password": "po2026",      "role": "Purchasing", "name": "Purchasing"},
    "shipping":   {"password": "ship2026",    "role": "Shipping",   "name": "Shipping"},
}

LOCATIONS = ["Central / Warehouse", "Store 1 · Cycling", "Store 2 · Running"]

# ── Session state init ───────────────────────────────────────────────────────
defaults = {
    "pos": [],            # list of PO dicts
    "inventory": {},      # {sku: {desc, Central, Store1, Store2}}
    "transfers": [],      # list of transfer log dicts
    "shopify_orders": [], # mock unfulfilled orders
    "receiving_po": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Login ────────────────────────────────────────────────────────────────────
if not st.session_state.get("user_role"):
    _, col, _ = st.columns([1, 1.2, 1])
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
                st.error("Credenciales incorrectas.")
    st.stop()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🚲 Enroute IMS")
    st.caption(f"**{st.session_state.user_name}** · {st.session_state.user_role}")
    st.divider()
    st.caption("Modo: **🧪 Pruebas** — Shopify en preview")
    st.divider()
    if st.button("Sign Out", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── Welcome ──────────────────────────────────────────────────────────────────
st.title("🚲 Enroute IMS")
st.success(f"Bienvenido, **{st.session_state.user_name}**. Selecciona un módulo en el menú lateral.")
st.divider()

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.info("**📊 Dashboard**\nKPIs de inventario, alertas y distribución por location.")
with c2:
    st.info("**📋 PO Tracker**\nCrea POs, sigue órdenes en tránsito y recibe mercancía.")
with c3:
    st.info("**📦 Inventory Control**\nExistencias por location y traspasos entre ubicaciones.")
with c4:
    st.info("**🚚 Shipping**\nÓrdenes pendientes de Shopify. Captura tracking y confirma envío.")

st.divider()
st.caption("🧪 **Modo prueba activo** — Los botones de Shopify muestran el payload que se enviaría al API en producción. Ningún dato real es modificado.")
