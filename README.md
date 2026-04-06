# 🚲 Enroute IMS — Inventory Management System

Sistema de gestión de inventario multi-location conectado con Shopify.

## Stack
- **Frontend:** Streamlit (Python)
- **API:** Shopify Admin API 2024-01
- **Hosting:** Streamlit Community Cloud / Azure App Service

## Estructura
```
enroute-ims/
├── app.py                  # Entry point + auth
├── pages/
│   ├── 1_Dashboard.py      # Vista general + KPIs
│   ├── 2_Inventory_Control.py  # Upload Excel + ajustes
│   └── 3_PO_Tracker.py    # Purchase Orders
├── utils/
│   └── shopify.py          # API client + demo data
├── .streamlit/
│   ├── config.toml         # Tema visual
│   └── secrets.toml        # Credenciales (NO en git)
└── requirements.txt
```

## Instalación local
```bash
git clone https://github.com/TU_USUARIO/enroute-ims.git
cd enroute-ims
pip install -r requirements.txt
streamlit run app.py
```

## Configurar Shopify
Edita `.streamlit/secrets.toml`:
```toml
[shopify]
shop_url    = "tu-tienda.myshopify.com"
admin_token = "shpat_xxxxxxxxxxxxxxxxxxxx"
```

Para obtener el token:
1. Shopify Admin → Settings → Apps → Develop apps
2. Create app → Configure Admin API scopes:
   - `read_inventory`, `write_inventory`
   - `read_products`
   - `read_locations`
3. Install app → copia el **Admin API access token**

## Deploy en Streamlit Community Cloud (gratis)
1. Sube el repo a GitHub (público)
2. Ve a [share.streamlit.io](https://share.streamlit.io)
3. New app → selecciona repo → `app.py`
4. Advanced → Secrets → pega el contenido de `secrets.toml`

## Usuarios demo
| Usuario    | Contraseña  | Rol        |
|------------|-------------|------------|
| admin      | enroute2026 | Admin      |
| warehouse  | wh2026      | Warehouse  |
| purchasing | po2026      | Purchasing |
| store1     | s1cycling   | Store 1    |
| store2     | s2running   | Store 2    |

## Modo demo
Sin credenciales de Shopify, la app corre en modo demo con datos de ejemplo.
Toda la lógica de validación y UI funciona igual.
