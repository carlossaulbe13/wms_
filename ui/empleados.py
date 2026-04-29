"""
ui/empleados.py — Alta y gestión de empleados.
Solo accesible para rol admin.
"""
import datetime
import streamlit as st
from config import HONORIFICOS, PERMISOS_DISPONIBLES
from firebase import cargar_empleados, guardar_empleado, eliminar_empleado

_ROLES = ["operador", "admin"]

_PUESTOS_SUGERIDOS = [
    "Jefe de Almacén", "Auxiliar de Almacén", "Operador Logístico",
    "Supervisor", "Coordinador", "Gerente", "Analista", "Técnico",
]


def render():
    st.markdown(
        "<h3 style='color:#EAE0CF;margin-bottom:4px;'>Gestión de Empleados</h3>",
        unsafe_allow_html=True,
    )

    empleados = cargar_empleados()

    # ── Alta de empleado ──────────────────────────────────────
    with st.expander("+ Registrar nuevo empleado", expanded=not bool(empleados)):
        with st.form("form_alta_empleado", clear_on_submit=True):
            c1, c2 = st.columns([1, 3])
            with c1:
                honorifico = st.selectbox("Honorífico", HONORIFICOS, key="emp_hon")
            with c2:
                nombre = st.text_input("Nombre completo", placeholder="Ej: Juan García López", key="emp_nombre")

            c3, c4 = st.columns(2)
            with c3:
                puesto = st.text_input(
                    "Puesto", placeholder="Ej: Jefe de Almacén", key="emp_puesto"
                )
            with c4:
                rol = st.selectbox("Rol en el sistema", _ROLES, key="emp_rol")

            uid_rfid = st.text_input(
                "UID de tarjeta RFID",
                placeholder="Ej: A1:B2:C3:D4",
                help="Escribe el UID tal como aparece en el lector (separado por ':')",
                key="emp_uid",
            )

            permisos = st.multiselect(
                "Permisos",
                PERMISOS_DISPONIBLES,
                default=["consulta_inventario"],
                key="emp_permisos",
            )

            submitted = st.form_submit_button("Registrar empleado", use_container_width=True)
            if submitted:
                uid_clean = uid_rfid.strip().upper()
                nombre_clean = nombre.strip()
                puesto_clean = puesto.strip()
                if not nombre_clean:
                    st.error("El nombre es obligatorio.")
                elif not uid_clean:
                    st.error("El UID RFID es obligatorio.")
                else:
                    datos = {
                        "nombre":     nombre_clean,
                        "honorifico": honorifico if honorifico != "(ninguno)" else "",
                        "puesto":     puesto_clean,
                        "rol":        rol,
                        "permisos":   permisos,
                        "uid_rfid":   uid_clean,
                        "activo":     True,
                        "fecha_alta": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }
                    ok = guardar_empleado(uid_clean, datos)
                    if ok:
                        st.success(f"Empleado '{nombre_clean}' registrado correctamente.")
                        st.rerun()
                    else:
                        st.error("Error al guardar en Firebase. Intenta de nuevo.")

    if not empleados:
        st.info("No hay empleados registrados aún.")
        return

    st.markdown("---")
    st.markdown(
        f"<div style='color:#94B4C1;font-size:13px;margin-bottom:12px;'>"
        f"{len(empleados)} empleado(s) registrado(s)</div>",
        unsafe_allow_html=True,
    )

    # ── Lista de empleados ────────────────────────────────────
    for key, emp in empleados.items():
        hon  = emp.get("honorifico", "")
        nom  = emp.get("nombre", "—")
        pues = emp.get("puesto", "—")
        rol  = emp.get("rol", "operador")
        uid  = emp.get("uid_rfid", "—")
        perms = emp.get("permisos", [])
        fecha = emp.get("fecha_alta", "—")

        nombre_display = f"{hon} {nom}".strip() if hon else nom
        rol_color = "#94B4C1" if rol == "admin" else "#547792"

        with st.container():
            st.markdown(
                f"<div style='background:#213448;border:1px solid rgba(84,119,146,0.4);"
                f"border-radius:10px;padding:14px 18px;margin-bottom:8px;'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<div>"
                f"  <span style='color:#EAE0CF;font-size:15px;font-weight:700;'>{nombre_display}</span>"
                f"  <span style='color:#94B4C1;font-size:12px;margin-left:10px;'>{pues}</span>"
                f"</div>"
                f"<span style='color:{rol_color};font-size:11px;font-weight:700;"
                f"background:rgba(84,119,146,0.15);padding:3px 10px;border-radius:6px;'>"
                f"{rol.upper()}</span>"
                f"</div>"
                f"<div style='color:#547792;font-size:12px;margin-top:6px;'>"
                f"UID: <code style='color:#94B4C1;'>{uid}</code> &nbsp;·&nbsp; Alta: {fecha}"
                f"</div>"
                f"<div style='margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;'>"
                + "".join(
                    f"<span style='background:rgba(84,119,146,0.2);color:#94B4C1;"
                    f"font-size:11px;padding:2px 8px;border-radius:4px;'>{p}</span>"
                    for p in perms
                )
                + f"</div></div>",
                unsafe_allow_html=True,
            )

            col_edit, col_del = st.columns([5, 1])
            with col_del:
                if st.button("Eliminar", key=f"del_{key}", type="secondary", use_container_width=True):
                    st.session_state[f"_confirm_del_{key}"] = True

            if st.session_state.get(f"_confirm_del_{key}"):
                st.warning(f"¿Eliminar a {nombre_display}? Esta acción no se puede deshacer.")
                ca, cb = st.columns(2)
                with ca:
                    if st.button("Sí, eliminar", key=f"del_ok_{key}", type="primary", use_container_width=True):
                        eliminar_empleado(uid)
                        st.session_state.pop(f"_confirm_del_{key}", None)
                        st.rerun()
                with cb:
                    if st.button("Cancelar", key=f"del_no_{key}", use_container_width=True):
                        st.session_state.pop(f"_confirm_del_{key}", None)
                        st.rerun()
