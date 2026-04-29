"""
ui/empleados.py — Alta y gestión de empleados.
Solo accesible para rol admin.
"""
import datetime
import hashlib
import streamlit as st
from config import HONORIFICOS, PERMISOS_DISPONIBLES
from firebase import cargar_empleados, guardar_empleado, eliminar_empleado

_ROLES = ["operador", "admin"]


def _hash_pwd(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


def _key_para_empleado(uid_clean: str, nombre_clean: str) -> str:
    """Genera la clave Firebase: UID si hay, si no timestamp+nombre."""
    if uid_clean:
        return uid_clean.replace(":", "_").upper()
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_nom = nombre_clean[:12].replace(" ", "_").upper()
    return f"EMP_{ts}_{safe_nom}"


def render():
    st.markdown(
        "<h3 style='color:#EAE0CF;margin-bottom:4px;'>Gestión de Empleados</h3>",
        unsafe_allow_html=True,
    )

    empleados = cargar_empleados()

    # ── Alta de empleado ──────────────────────────────────────
    with st.expander("+ Registrar nuevo empleado", expanded=not bool(empleados)):
        with st.form("form_alta_empleado", clear_on_submit=True):
            c1, c2, c3_name = st.columns([1, 2, 2])
            with c1:
                honorifico = st.selectbox("Honorífico", HONORIFICOS, key="emp_hon")
            with c2:
                nombre = st.text_input("Nombre(s)", placeholder="Ej: Juan Carlos", key="emp_nombre")
            with c3_name:
                apellido = st.text_input("Apellido(s)", placeholder="Ej: García López", key="emp_apellido")

            c3, c4 = st.columns(2)
            with c3:
                puesto = st.text_input("Puesto", placeholder="Ej: Jefe de Almacén", key="emp_puesto")
            with c4:
                rol = st.selectbox("Rol en el sistema", _ROLES, key="emp_rol")

            uid_rfid = st.text_input(
                "UID de tarjeta RFID (opcional)",
                placeholder="Ej: A1:B2:C3:D4",
                help="Déjalo vacío si el empleado no tiene tarjeta RFID.",
                key="emp_uid",
            )

            st.markdown(
                "<div style='color:#94B4C1;font-size:12px;margin:8px 0 4px;'>"
                "Contraseña de acceso alternativa (opcional)</div>",
                unsafe_allow_html=True,
            )
            cp1, cp2 = st.columns(2)
            with cp1:
                pwd1 = st.text_input("Contraseña", type="password",
                                     placeholder="Mín. 6 caracteres", key="emp_pwd1")
            with cp2:
                pwd2 = st.text_input("Confirmar contraseña", type="password",
                                     placeholder="Repite la contraseña", key="emp_pwd2")

            permisos = st.multiselect(
                "Permisos",
                PERMISOS_DISPONIBLES,
                default=["consulta_inventario"],
                key="emp_permisos",
            )

            submitted = st.form_submit_button("Registrar empleado", use_container_width=True)
            if submitted:
                uid_clean      = uid_rfid.strip().upper()
                nombre_clean   = nombre.strip()
                apellido_clean = apellido.strip()
                puesto_clean   = puesto.strip()
                pwd1_clean     = pwd1.strip()
                pwd2_clean     = pwd2.strip()

                # Validaciones
                if not nombre_clean:
                    st.error("El nombre es obligatorio.")
                elif not apellido_clean:
                    st.error("El apellido es obligatorio.")
                elif not uid_clean and not pwd1_clean:
                    st.error("Debes proporcionar al menos un UID RFID o una contraseña.")
                elif pwd1_clean and pwd1_clean != pwd2_clean:
                    st.error("Las contraseñas no coinciden.")
                elif pwd1_clean and len(pwd1_clean) < 6:
                    st.error("La contraseña debe tener al menos 6 caracteres.")
                else:
                    key = _key_para_empleado(uid_clean, apellido_clean)
                    datos = {
                        "nombre":     nombre_clean,
                        "apellido":   apellido_clean,
                        "honorifico": honorifico if honorifico != "(ninguno)" else "",
                        "puesto":     puesto_clean,
                        "rol":        rol,
                        "permisos":   permisos,
                        "uid_rfid":   uid_clean,
                        "activo":     True,
                        "fecha_alta": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }
                    if pwd1_clean:
                        datos["password_hash"] = _hash_pwd(pwd1_clean)

                    # Guardar con key explícita (no depende de uid_rfid)
                    from firebase import EMPLEADOS_URL
                    import requests
                    url = EMPLEADOS_URL.replace("empleados.json", f"empleados/{key}.json")
                    try:
                        res = requests.put(url, json=datos, timeout=5)
                        ok = res.status_code in (200, 204)
                    except Exception:
                        ok = False

                    if ok:
                        st.success(f"Empleado '{nombre_clean}' registrado correctamente.")
                        st.rerun()
                    else:
                        st.error("Error al guardar en Firebase. Verifica la conexión.")

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
        hon   = emp.get("honorifico", "")
        nom   = emp.get("nombre", "")
        ape   = emp.get("apellido", "")
        pues  = emp.get("puesto", "—")
        rol   = emp.get("rol", "operador")
        uid   = emp.get("uid_rfid", "") or "—"
        perms = emp.get("permisos", [])
        fecha = emp.get("fecha_alta", "—")
        tiene_pwd = bool(emp.get("password_hash"))

        nombre_completo = f"{nom} {ape}".strip() or "—"
        nombre_display = f"{hon} {nombre_completo}".strip() if hon else nombre_completo
        rol_color = "#94B4C1" if rol == "admin" else "#547792"

        acceso_tags = ""
        if uid != "—":
            acceso_tags += "<span style='background:rgba(84,119,146,0.25);color:#94B4C1;font-size:11px;padding:2px 8px;border-radius:4px;'>RFID</span> "
        if tiene_pwd:
            acceso_tags += "<span style='background:rgba(84,119,146,0.25);color:#94B4C1;font-size:11px;padding:2px 8px;border-radius:4px;'>Contraseña</span>"

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
                f"<div style='margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;'>{acceso_tags}</div>"
                f"<div style='margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;'>"
                + "".join(
                    f"<span style='background:rgba(84,119,146,0.2);color:#94B4C1;"
                    f"font-size:11px;padding:2px 8px;border-radius:4px;'>{p}</span>"
                    for p in perms
                )
                + f"</div></div>",
                unsafe_allow_html=True,
            )

            _, col_del = st.columns([5, 1])
            with col_del:
                if st.button("Eliminar", key=f"del_{key}", type="secondary", use_container_width=True):
                    st.session_state[f"_confirm_del_{key}"] = True

            if st.session_state.get(f"_confirm_del_{key}"):
                st.warning(f"¿Eliminar a {nombre_display}? Esta acción no se puede deshacer.")
                ca, cb = st.columns(2)
                with ca:
                    if st.button("Sí, eliminar", key=f"del_ok_{key}", type="primary", use_container_width=True):
                        uid_val = emp.get("uid_rfid", "")
                        if uid_val:
                            eliminar_empleado(uid_val)
                        else:
                            # Eliminar por key directamente
                            from firebase import EMPLEADOS_URL
                            import requests
                            url = EMPLEADOS_URL.replace("empleados.json", f"empleados/{key}.json")
                            try:
                                requests.delete(url, timeout=5)
                            except Exception:
                                pass
                        st.session_state.pop(f"_confirm_del_{key}", None)
                        st.rerun()
                with cb:
                    if st.button("Cancelar", key=f"del_no_{key}", use_container_width=True):
                        st.session_state.pop(f"_confirm_del_{key}", None)
                        st.rerun()
