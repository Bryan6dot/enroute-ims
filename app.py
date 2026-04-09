import streamlit as st
import pandas as pd
import uuid
from datetime import date, datetime

st.set_page_config(page_title="Enroute IMS", page_icon="🚲", layout="wide", initial_sidebar_state="expanded")

USERS     = {"admin":{"password":"enroute2026","role":"Admin","name":"Admin"},"warehouse":{"password":"wh2026","role":"Warehouse","name":"Warehouse"},"purchasing":{"password":"po2026","role":"Purchasing","name":"Purchasing"},"shipping":{"password":"ship2026","role":"Shipping","name":"Shipping"}}
LOCATIONS = ["Central / Warehouse","Store 1 · Cycling","Store 2 · Running"]
LOC_KEY   = {"Central / Warehouse":"Central","Store 1 · Cycling":"Store1","Store 2 · Running":"Store2"}
CARRIERS  = ["DHL","FedEx","UPS","Estafeta","Redpack","Otro"]

for k,v in {"pos":[],"inventory":{},"transfers":[],"shopify_orders":[],"page":"📊 Dashboard","po_items":[{"SKU":"","Descripción":"","Qty Ordenada":1}]}.items():
    if k not in st.session_state: st.session_state[k]=v

def shopify_preview(endpoint,method,payload,description=""):
    with st.container(border=True):
        st.markdown("#### 📡 Shopify API — Vista previa del envío")
        if description: st.caption(description)
        c1,c2=st.columns([1,2])
        with c1:
            st.markdown(f"**Método:** `{method}`")
            st.markdown("**Endpoint:**")
            st.code(endpoint,language="text")
            st.markdown(f"**Timestamp:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
        with c2:
            st.markdown("**Payload:**")
            st.json(payload)
        st.warning("⚠️ **Modo prueba** — Este payload NO fue enviado a Shopify.")

# ── LOGIN ─────────────────────────────────────────────────────────────────────
if not st.session_state.get("user_role"):
    _,col,_=st.columns([1,1.2,1])
    with col:
        st.markdown("## 🚲 Enroute IMS")
        st.markdown("##### Inventory Management System")
        st.divider()
        username=st.text_input("Username")
        password=st.text_input("Password",type="password")
        if st.button("Sign In",use_container_width=True,type="primary"):
            u=USERS.get(username)
            if u and u["password"]==password:
                st.session_state.user_role=u["role"]
                st.session_state.user_name=u["name"]
                st.rerun()
            else: st.error("Credenciales incorrectas.")
    st.stop()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🚲 Enroute IMS")
    st.caption(f"**{st.session_state.user_name}** · {st.session_state.user_role}")
    st.divider()
    for p in ["📊 Dashboard","📋 PO Tracker","📦 Inventory Control","🚚 Shipping"]:
        if st.button(p,use_container_width=True,type="primary" if st.session_state.page==p else "secondary"):
            st.session_state.page=p
            st.rerun()
    st.divider()
    st.caption("🧪 Modo prueba — Shopify en preview")
    st.divider()
    if st.button("Sign Out",use_container_width=True):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()

page=st.session_state.page

# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page=="📊 Dashboard":
    st.title("📊 Dashboard")
    st.caption("Vista general de inventario · KPIs en tiempo real")
    st.divider()
    inv=st.session_state.inventory; pos=st.session_state.pos; trfs=st.session_state.transfers
    total_skus=len(inv); total_units=sum(v.get("Central",0)+v.get("Store1",0)+v.get("Store2",0) for v in inv.values())
    low_stock=sum(1 for v in inv.values() if 0<v.get("Central",0)+v.get("Store1",0)+v.get("Store2",0)<5)
    stockouts=sum(1 for v in inv.values() if v.get("Central",0)+v.get("Store1",0)+v.get("Store2",0)==0)
    pos_transit=sum(1 for p in pos if p.get("status")=="En tránsito")
    pos_partial=sum(1 for p in pos if p.get("status")=="Parcial")
    k1,k2,k3,k4,k5,k6=st.columns(6)
    k1.metric("📦 SKUs",total_skus or "—"); k2.metric("🔢 Unidades",total_units or "—")
    k3.metric("🚚 POs en tránsito",pos_transit or "—"); k4.metric("⚠️ Rec. parcial",pos_partial or "—")
    k5.metric("🔴 Low stock",low_stock or "—",delta_color="inverse"); k6.metric("🚫 Stockouts",stockouts or "—",delta_color="inverse")
    st.divider()
    st.markdown("#### Distribución por Location")
    if not inv:
        c1,c2,c3=st.columns(3)
        for col,loc in zip([c1,c2,c3],LOCATIONS):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{loc}**"); st.markdown("### — unidades"); st.caption("Sin datos. Recibe un PO.")
    else:
        cu=sum(v.get("Central",0) for v in inv.values()); s1=sum(v.get("Store1",0) for v in inv.values()); s2=sum(v.get("Store2",0) for v in inv.values()); au=max(cu+s1+s2,1)
        c1,c2,c3=st.columns(3)
        for col,label,val in zip([c1,c2,c3],["🏭 Central / Warehouse","🚲 Store 1 · Cycling","🏃 Store 2 · Running"],[cu,s1,s2]):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{label}**"); st.markdown(f"### {val} unidades"); st.progress(val/au); st.caption(f"{val/au*100:.1f}% del total")
    st.divider()
    left,right=st.columns(2)
    with left:
        st.markdown("#### ⚠️ Alertas activas")
        if not inv: st.info("Los alertas aparecerán aquí una vez se registren existencias.")
        else:
            alerted=False
            for sku,data in inv.items():
                total=data.get("Central",0)+data.get("Store1",0)+data.get("Store2",0)
                if total==0: st.error(f"**{sku}** — {data.get('desc','—')} · STOCKOUT"); alerted=True
                elif total<5: st.warning(f"**{sku}** — {data.get('desc','—')} · Low stock ({total} uds.)"); alerted=True
            if not alerted: st.success("Sin alertas activas.")
        st.markdown("#### 🚚 POs activos")
        if not pos: st.info("No hay POs. Crea uno en PO Tracker.")
        else:
            for p in pos:
                if p["status"]=="En tránsito": st.info(f"**{p['id']}** — {p['supplier']} · ETA: {p['eta']}")
                elif p["status"]=="Parcial": st.warning(f"**{p['id']}** — {p['supplier']} · Recepción parcial")
    with right:
        st.markdown("#### 📋 Inventario completo")
        if not inv: st.info("Sin datos de inventario aún.")
        else:
            rows=[]
            for sku,data in inv.items():
                total=data.get("Central",0)+data.get("Store1",0)+data.get("Store2",0)
                rows.append({"SKU":sku,"Descripción":data.get("desc","—"),"Central 🏭":data.get("Central",0),"Store 1 🚲":data.get("Store1",0),"Store 2 🏃":data.get("Store2",0),"Total":total,"Estado":"🚫 Stockout" if total==0 else("🔴 Low" if total<5 else("🟡 Watch" if total<10 else"🟢 OK"))})
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        st.markdown("#### 🔄 Últimos traspasos")
        if not trfs: st.info("No se han registrado traspasos.")
        else: st.dataframe(pd.DataFrame(trfs[-10:]),use_container_width=True,hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# PO TRACKER
# ══════════════════════════════════════════════════════════════════════════════
elif page=="📋 PO Tracker":
    st.title("📋 PO Tracker")
    st.caption("Gestión de órdenes de compra — Crear · Seguimiento · Recepción")
    st.divider()
    tab_create,tab_transit,tab_receive=st.tabs(["➕ Crear PO","🔵 En tránsito","📥 Recibir mercancía"])

    with tab_create:
        st.markdown("#### Nueva Orden de Compra")
        ca,cb=st.columns(2)
        with ca: supplier=st.text_input("Proveedor *",placeholder="Ej. Trek Bikes México"); reference=st.text_input("# Referencia proveedor",placeholder="Ej. INV-2025-8841")
        with cb: eta=st.date_input("ETA *",min_value=date.today()); dest_loc=st.selectbox("Location de destino *",LOCATIONS)
        st.markdown("#### Artículos del pedido")
        edited=st.data_editor(pd.DataFrame(st.session_state.po_items),num_rows="dynamic",use_container_width=True,
            column_config={"SKU":st.column_config.TextColumn("SKU *"),"Descripción":st.column_config.TextColumn("Descripción *"),"Qty Ordenada":st.column_config.NumberColumn("Qty Ordenada *",min_value=1,step=1)},hide_index=True)
        st.session_state.po_items=edited.to_dict("records")
        st.divider()
        if st.button("✅ Registrar PO",type="primary"):
            valid=[r for r in st.session_state.po_items if r.get("SKU") and r.get("Descripción")]
            if not supplier: st.error("El campo Proveedor es obligatorio.")
            elif not valid: st.error("Agrega al menos un artículo con SKU y Descripción.")
            else:
                po_id=f"PO-{date.today().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
                st.session_state.pos.append({"id":po_id,"supplier":supplier,"reference":reference,"eta":str(eta),"destination":dest_loc,"status":"En tránsito","created_at":datetime.now().strftime("%Y-%m-%d %H:%M"),"total_units":sum(r.get("Qty Ordenada",0) for r in valid),"skus":[{"SKU":r["SKU"].strip().upper(),"Descripción":r["Descripción"],"Qty Ordenada":r.get("Qty Ordenada",0),"Qty Recibida":0} for r in valid]})
                st.session_state.po_items=[{"SKU":"","Descripción":"","Qty Ordenada":1}]
                st.success(f"✅ **{po_id}** registrado. Visible en 'En tránsito'.")
                st.rerun()

    with tab_transit:
        st.markdown("#### Órdenes en tránsito")
        if not st.session_state.pos: st.info("No hay POs. Crea uno en la pestaña 'Crear PO'.")
        else:
            ICONS={"En tránsito":"🔵","Parcial":"🟡","Recibido":"🟢","Discrepancia":"🔴"}
            for po in st.session_state.pos:
                with st.expander(f"{ICONS.get(po['status'],'⚪')} **{po['id']}** — {po['supplier']} · ETA: {po['eta']} · {po['status']}"):
                    c1,c2,c3,c4=st.columns(4); c1.metric("Proveedor",po["supplier"]); c2.metric("ETA",po["eta"]); c3.metric("Destino",po["destination"]); c4.metric("Estado",po["status"])
                    st.dataframe(pd.DataFrame(po["skus"]),use_container_width=True,hide_index=True)

    with tab_receive:
        st.markdown("#### Recepción de mercancía")
        pos_open=[p for p in st.session_state.pos if p["status"] in("En tránsito","Parcial")]
        if not pos_open: st.info("No hay POs pendientes de recepción.")
        else:
            sel_id=st.selectbox("Selecciona el PO a recibir",[p["id"] for p in pos_open])
            po=next(p for p in pos_open if p["id"]==sel_id)
            st.markdown(f"**Proveedor:** {po['supplier']}  |  **ETA:** {po['eta']}  |  **Destino:** {po['destination']}")
            st.divider()
            has_slip=st.radio("¿El paquete llegó con packing slip?",["✅ Sí, tengo packing slip","❌ No, sin packing slip"],horizontal=True)
            if "❌" in has_slip:
                st.warning("Sin packing slip. Exporta la lista para revisar el paquete.")
                csv=pd.DataFrame([{"SKU":s["SKU"],"Descripción":s["Descripción"],"Qty Esperada":s["Qty Ordenada"],"Qty Recibida":""} for s in po["skus"]]).to_csv(index=False).encode("utf-8")
                st.download_button("📥 Exportar CSV para revisión",data=csv,file_name=f"{po['id']}_revision.csv",mime="text/csv")
                st.info("Después de revisar, selecciona '✅ Sí' para continuar.")
            else:
                st.markdown("#### Captura las cantidades recibidas")
                received={}
                for s in po["skus"]:
                    sku=s["SKU"]; ca,cb,cc=st.columns([3,1,1])
                    with ca: st.text(f"{sku} — {s['Descripción']}")
                    with cb: st.caption(f"Ordenado: {s['Qty Ordenada']}")
                    with cc: received[sku]=st.number_input("Recibido",min_value=0,max_value=int(s["Qty Ordenada"])*2,value=int(s.get("Qty Recibida",0)),key=f"recv_{po['id']}_{sku}")
                st.text_area("Notas de recepción (opcional)",key="recv_notes")
                st.divider()
                if st.button("📡 Confirmar recepción → Shopify",type="primary"):
                    adjustments=[]; new_status="Recibido"; loc_key=LOC_KEY.get(po["destination"],"Central")
                    for s in po["skus"]:
                        sku=s["SKU"]; qty_ord=int(s["Qty Ordenada"]); qty_rec=int(received.get(sku,0))
                        if sku not in st.session_state.inventory: st.session_state.inventory[sku]={"desc":s["Descripción"],"Central":0,"Store1":0,"Store2":0}
                        st.session_state.inventory[sku][loc_key]+=qty_rec; st.session_state.inventory[sku]["desc"]=s["Descripción"]
                        adjustments.append({"sku":sku,"qty":qty_rec})
                        if qty_rec<qty_ord:
                            if new_status=="Recibido": new_status="Parcial"
                        elif qty_rec>qty_ord: new_status="Discrepancia"
                    for p in st.session_state.pos:
                        if p["id"]==po["id"]:
                            p["status"]=new_status
                            for s in p["skus"]: s["Qty Recibida"]=received.get(s["SKU"],0)
                    st.success(f"✅ Recepción registrada. Estado PO: **{new_status}**")
                    st.markdown("---")
                    st.markdown(f"### 📡 Llamadas al API de Shopify ({len(adjustments)} total)")
                    for adj in adjustments:
                        shopify_preview("/admin/api/2026-01/inventory_levels/adjust.json","POST",{"inventory_level":{"inventory_item_id":f"← GET /variants.json?sku={adj['sku']}","location_id":f"← GET /locations.json → {po['destination']}","available_adjustment":adj["qty"],"reason":"received"}},f"Suma **+{adj['qty']} uds.** de `{adj['sku']}` en {po['destination']}")

# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY CONTROL
# ══════════════════════════════════════════════════════════════════════════════
elif page=="📦 Inventory Control":
    st.title("📦 Inventory Control")
    st.caption("Existencias por location · Traspasos entre ubicaciones")
    st.divider()
    tab_stock,tab_transfer=st.tabs(["📊 Existencias actuales","🔄 Traspaso entre locations"])

    with tab_stock:
        inv=st.session_state.inventory
        if not inv: st.info("Sin datos de inventario. Las existencias se crean al recibir un PO en **PO Tracker**.")
        else:
            cf1,cf2=st.columns([1,2])
            with cf1: loc_filter=st.selectbox("Filtrar por location",["Todas"]+LOCATIONS)
            with cf2: search=st.text_input("Buscar SKU o descripción")
            rows=[]
            for sku,data in inv.items():
                if search and search.upper() not in sku and search.lower() not in data.get("desc","").lower(): continue
                total=data.get("Central",0)+data.get("Store1",0)+data.get("Store2",0)
                if loc_filter!="Todas" and data.get(LOC_KEY[loc_filter],0)==0: continue
                rows.append({"SKU":sku,"Descripción":data.get("desc","—"),"Central 🏭":data.get("Central",0),"Store 1 🚲":data.get("Store1",0),"Store 2 🏃":data.get("Store2",0),"Total":total,"Estado":"🚫 Stockout" if total==0 else("🔴 Low" if total<5 else("🟡 Watch" if total<10 else"🟢 OK"))})
            if not rows: st.warning("No hay artículos que coincidan con el filtro.")
            else: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True); st.caption(f"{len(rows)} SKU(s) · {sum(r['Total'] for r in rows)} unidades totales")

    with tab_transfer:
        st.markdown("#### Traspaso entre locations")
        st.caption("Shopify recibe **dos ajustes**: resta en origen y suma en destino.")
        inv=st.session_state.inventory
        if not inv: st.info("Sin datos de inventario. Recibe al menos un PO para habilitar traspasos.")
        else:
            c1,c2=st.columns(2)
            with c1: origin=st.selectbox("📍 Location origen",LOCATIONS,key="trf_origin")
            with c2: destination=st.selectbox("📍 Location destino",[l for l in LOCATIONS if l!=origin],key="trf_dest")
            origin_key=LOC_KEY[origin]; available={sku:d for sku,d in inv.items() if d.get(origin_key,0)>0}
            st.markdown("#### Artículos a traspasar")
            if not available: st.warning(f"No hay existencias en **{origin}**.")
            else:
                trf_items=[]
                for sku,data in available.items():
                    avail=data.get(origin_key,0); ca,cb,cc,cd=st.columns([2,2,1,1])
                    with ca: st.text(sku)
                    with cb: st.text(data.get("desc","—"))
                    with cc: st.caption(f"Disp: {avail}")
                    with cd: qty=st.number_input("Qty",min_value=0,max_value=avail,value=0,key=f"trf_{sku}")
                    if qty>0: trf_items.append({"sku":sku,"desc":data.get("desc","—"),"qty":qty})
                st.divider()
                if st.button("📡 Ejecutar traspaso → Shopify",type="primary"):
                    if not trf_items: st.error("Selecciona al menos un artículo con cantidad mayor a 0.")
                    else:
                        dest_key=LOC_KEY[destination]
                        for item in trf_items:
                            st.session_state.inventory[item["sku"]][origin_key]-=item["qty"]
                            st.session_state.inventory[item["sku"]][dest_key]+=item["qty"]
                            st.session_state.transfers.append({"Fecha":datetime.now().strftime("%Y-%m-%d %H:%M"),"SKU":item["sku"],"Descripción":item["desc"],"Qty":item["qty"],"Origen":origin,"Destino":destination})
                        st.success(f"✅ Traspaso registrado — {len(trf_items)} SKU(s) de {origin} → {destination}")
                        st.markdown("---")
                        st.markdown(f"### 📡 Llamadas al API de Shopify ({len(trf_items)*2} total)")
                        for item in trf_items:
                            shopify_preview("/admin/api/2026-01/inventory_levels/adjust.json","POST",{"inventory_level":{"inventory_item_id":f"← GET /variants.json?sku={item['sku']}","location_id":f"← GET /locations.json → {origin}","available_adjustment":-item["qty"],"reason":"movement_created"}},f"**RESTA {item['qty']} uds.** de `{item['sku']}` en {origin}")
                            shopify_preview("/admin/api/2026-01/inventory_levels/adjust.json","POST",{"inventory_level":{"inventory_item_id":f"← GET /variants.json?sku={item['sku']}","location_id":f"← GET /locations.json → {destination}","available_adjustment":+item["qty"],"reason":"movement_received"}},f"**SUMA {item['qty']} uds.** de `{item['sku']}` en {destination}")

# ══════════════════════════════════════════════════════════════════════════════
# SHIPPING
# ══════════════════════════════════════════════════════════════════════════════
elif page=="🚚 Shipping":
    st.title("🚚 Shipping")
    st.caption("Órdenes pendientes · Shopify descuenta inventario al crearse la orden — Streamlit solo confirma el envío")
    st.divider()
    st.info("**¿Por qué Streamlit no descuenta inventario aquí?**  \nCuando el cliente hace una orden en Shopify, Shopify descuenta el stock automáticamente.  \nStreamlit solo **confirma el despacho** con el número de rastreo. Shopify cambia la orden a `fulfilled` y notifica al cliente.")
    st.divider()
    col_sync,col_manual=st.columns([2,1])
    with col_sync:
        st.markdown("#### Órdenes pendientes de envío")
        if st.button("🔄 Sincronizar desde Shopify",type="secondary"):
            shopify_preview("/admin/api/2026-01/orders.json?fulfillment_status=unfulfilled&status=open&limit=50","GET",{"fulfillment_status":"unfulfilled","status":"open","fields":"id,order_number,created_at,customer,line_items,location_id,financial_status","limit":50},"Shopify devuelve todas las órdenes activas sin fulfillment.")
    with col_manual:
        st.markdown("#### Agregar orden de prueba")
        with st.expander("➕ Nueva orden manual"):
            m_order=st.text_input("# Orden",placeholder="SHP-10041",key="m_order"); m_client=st.text_input("Cliente",placeholder="María González",key="m_client")
            m_sku=st.text_input("SKU",placeholder="ERC-BIKE-29-BLK",key="m_sku"); m_desc=st.text_input("Descripción",placeholder="Trek Marlin BLK",key="m_desc")
            m_qty=st.number_input("Qty",min_value=1,value=1,key="m_qty"); m_loc=st.selectbox("Location",LOCATIONS,key="m_loc")
            if st.button("Agregar orden",key="btn_add"):
                if m_order and m_client and m_sku:
                    st.session_state.shopify_orders.append({"order_id":str(uuid.uuid4())[:8].upper(),"order_number":m_order,"cliente":m_client,"sku":m_sku.upper(),"descripcion":m_desc,"qty":m_qty,"location":m_loc,"status":"unfulfilled","created_at":datetime.now().strftime("%Y-%m-%d")})
                    st.success("Orden agregada."); st.rerun()
                else: st.error("# Orden, Cliente y SKU son obligatorios.")
    st.divider()
    orders=[o for o in st.session_state.shopify_orders if o.get("status")=="unfulfilled"]
    if not orders: st.info("No hay órdenes pendientes. Sincroniza con Shopify o agrega una orden de prueba.")
    else:
        st.markdown(f"**{len(orders)} orden(es) pendiente(s)**")
        for order in orders:
            with st.expander(f"📦 **{order['order_number']}** — {order['cliente']} · {order['sku']} · {order['qty']} uds. · {order['location']}"):
                c1,c2,c3,c4=st.columns(4); c1.metric("# Orden",order["order_number"]); c2.metric("Cliente",order["cliente"]); c3.metric("Location",order["location"]); c4.metric("Fecha",order["created_at"])
                st.markdown(f"**SKU:** `{order['sku']}` — {order.get('descripcion','—')}  |  **Qty:** {order['qty']}")
                st.caption(f"Shopify Order ID: `{order['order_id']}`")
                st.divider()
                st.markdown("##### Confirmar envío")
                ct1,ct2=st.columns(2)
                with ct1: tracking=st.text_input("Número de rastreo / Label ID *",placeholder="Ej. 1Z999AA10123456784",key=f"trk_{order['order_id']}")
                with ct2: carrier=st.selectbox("Carrier *",CARRIERS,key=f"car_{order['order_id']}")
                notify=st.checkbox("Notificar al cliente (Shopify envía email automáticamente)",value=True,key=f"ntf_{order['order_id']}")
                if st.button(f"📡 Marcar como enviado — {order['order_number']}",type="primary",key=f"ship_{order['order_id']}"):
                    if not tracking: st.error("El número de rastreo es obligatorio.")
                    else:
                        for o in st.session_state.shopify_orders:
                            if o["order_id"]==order["order_id"]: o["status"]="fulfilled"; o["tracking"]=tracking; o["carrier"]=carrier; o["shipped_at"]=datetime.now().strftime("%Y-%m-%d %H:%M")
                        st.success(f"✅ Orden **{order['order_number']}** marcada como enviada.")
                        st.markdown("---"); st.markdown("### 📡 Llamada al API de Shopify")
                        shopify_preview(f"/admin/api/2026-01/orders/{order['order_id']}/fulfillments.json","POST",{"fulfillment":{"location_id":f"← GET /locations.json → {order['location']}","tracking_number":tracking,"tracking_company":carrier,"notify_customer":notify,"line_items":[{"id":f"← line_item_id de orden {order['order_id']}","quantity":order["qty"]}]}},f"Marca **{order['order_number']}** como enviada con tracking `{tracking}` via {carrier}.\n**El inventario ya fue descontado por Shopify — Streamlit no hace adjust.**")
                        st.rerun()
    fulfilled=[o for o in st.session_state.shopify_orders if o.get("status")=="fulfilled"]
    if fulfilled:
        st.divider(); st.markdown(f"#### ✅ Órdenes enviadas esta sesión ({len(fulfilled)})")
        st.dataframe(pd.DataFrame([{"# Orden":o["order_number"],"Cliente":o["cliente"],"SKU":o["sku"],"Qty":o["qty"],"Carrier":o.get("carrier","—"),"Tracking":o.get("tracking","—"),"Enviado":o.get("shipped_at","—"),"Location":o["location"]} for o in fulfilled]),use_container_width=True,hide_index=True)
