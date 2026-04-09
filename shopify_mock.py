import streamlit as st
from datetime import datetime

def shopify_preview(endpoint: str, method: str, payload: dict, description: str = ""):
    with st.container(border=True):
        st.markdown("#### 📡 Shopify API — Vista previa del envío")
        if description:
            st.caption(description)
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"**Método:** `{method}`")
            st.markdown("**Endpoint:**")
            st.code(endpoint, language="text")
            st.markdown(f"**Timestamp:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
        with col2:
            st.markdown("**Payload:**")
            st.json(payload)
        st.warning("⚠️ **Modo prueba** — Este payload NO fue enviado a Shopify. En producción se ejecutaría esta llamada al API.")
