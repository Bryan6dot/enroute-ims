import streamlit as st

st.set_page_config(
    page_title="Enroute IMS",
    page_icon="🚲",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state defaults ──────────────────────────────────────────────────
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "user_name" not in st.session_state:
    st.session_state.user_name = None

# ── Auth gate ───────────────────────────────────────────────────────────────
USERS = {
    "admin":     {"password": "enroute2026", "role": "admin",     "name": "Admin"},
    "warehouse": {"password": "wh2026",      "role": "warehouse", "name": "Warehouse"},
    "purchasing": {"password": "po2026",     "role": "purchasing","name": "Purchasing"},
    "store1":    {"password": "s1cycling",   "role": "store",     "name": "Store 1 · Cycling"},
    "store2":    {"password": "s2running",   "role": "store",     "name": "Store 2 · Running"},
}

if not st.session_state.user_role:
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("## 🚲 Enroute IMS")
        st.markdown("##### Inventory Management System")
        st.divider()
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.button("Ingresar", use_container_width=True, type="primary"):
            u = USERS.get(username)
            if u and u["password"] == password:
                st.session_state.user_role = u["role"]
                st.session_state.user_name = u["name"]
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()

# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### 🚲 Enroute IMS")
    st.caption(f"Sesión: **{st.session_state.user_name}**")
    st.divider()
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.user_role = None
        st.session_state.user_name = None
        st.rerun()

# ── Welcome screen after login ──────────────────────────────────────────────
st.title("🚲 Enroute IMS")
st.success(f"Bienvenido, **{st.session_state.user_name}**")
st.markdown("Selecciona un módulo en el menú de la izquierda para comenzar.")

col1, col2, col3 = st.columns(3)
with col1:
    st.info("**📊 Dashboard**\nVista general de existencias, KPIs y alertas.")
with col2:
    st.info("**📦 Inventory Control**\nSube Excel para ajustar inventario en Shopify.")
with col3:
    st.info("**📋 PO Tracker**\nGestiona Purchase Orders y recepciones.")
