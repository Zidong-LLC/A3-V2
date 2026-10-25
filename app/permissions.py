"""Perfiles del personal de A3 y qué puede hacer cada uno en la plataforma interna.

Fuente: «Perfiles Plataforma.docx» (A3, octubre de 2026). Por módulo, cada perfil tiene
uno de tres niveles: sin acceso, consulta (ver) o gestión (ver y modificar). Lógica pura:
quien la hace cumplir en cada pedido es `app/access.py`, en el servidor. Ocultar un
botón no alcanza.
"""
NINGUNO, CONSULTA, GESTION = 0, 1, 2

PERFILES = {
    "administrador": "Administrador",
    "recepcion": "Recepción",
    "digitacion": "Digitación",
    "auxiliar_administrativa": "Auxiliar administrativa",
    "procesamiento": "Procesamiento",
}

# Orden del menú lateral; también decide a qué sección entra cada perfil al iniciar sesión.
MODULOS = ("dashboard", "operacion", "clientes", "solicitudes", "pedidos", "facturacion",
           "motorizados", "agenda", "muestras", "resultados", "cargas", "precios", "usuarios")

_N, _C, _G = NINGUNO, CONSULTA, GESTION
# Matriz del docx. «Registrar», «Consultar/actualizar» y «Gestionar» permiten modificar;
# «Consultar» y «Solo consultar», solo ver. Precios y usuarios no están en el docx: los
# precios mueven plata y los usuarios dan acceso, así que quedan para el Administrador.
_MATRIZ = {
    #                           pan op  cli sol ped fac mot age mue res car pre usu
    "recepcion":               (_G, _G, _G, _G, _G, _N, _G, _G, _G, _C, _N, _N, _N),
    "digitacion":              (_G, _G, _C, _G, _G, _N, _N, _N, _G, _G, _G, _N, _N),
    "auxiliar_administrativa": (_G, _N, _G, _N, _C, _G, _N, _N, _N, _N, _N, _N, _N),
    "procesamiento":           (_G, _G, _N, _C, _C, _N, _N, _N, _G, _G, _G, _N, _N),
}

# Ruta (endpoint de Flask) -> módulos que la habilitan; alcanza con uno. «bp.*» cubre
# todo un blueprint. Un test exige que cada ruta del personal esté acá o en LIBRES.
_ENDPOINTS = {
    "dashboard.dashboard_home": ("dashboard",),
    "dashboard.dashboard_overview": ("dashboard",),
    "dashboard.operation_page": ("operacion",),
    "dashboard.clients_page": ("clientes",),
    "dashboard.new_client_page": ("clientes",),
    "dashboard.approval_decision": ("clientes",),
    "dashboard.update_client_profile": ("clientes",),
    "dashboard.update_client_assignment": ("clientes",),
    "dashboard.delete_client": ("clientes",),
    "dashboard.suggest_couriers": ("clientes",),
    "dashboard.confirm_suggested_assignments": ("clientes",),
    "dashboard_client.ficha_cliente": ("clientes",),
    "dashboard_client.buscar_clientes": ("clientes", "solicitudes", "facturacion"),
    "dashboard.courier_suggestion": ("clientes", "solicitudes"),
    "dashboard.neighborhood_search": ("clientes", "solicitudes"),
    "dashboard.requests_page": ("solicitudes",),
    "dashboard.new_request_page": ("solicitudes",),
    "dashboard.update_request_status": ("solicitudes", "operacion"),
    "dashboard.update_request_operation": ("solicitudes", "operacion", "agenda"),
    "dashboard.service_order_print_page": ("solicitudes", "pedidos", "operacion"),
    "dashboard.pedidos_page": ("pedidos",),
    "dashboard.close_pedido_manually": ("pedidos", "facturacion"),  # facturar exige facturación
    "dashboard.billing_page": ("facturacion",),
    "dashboard.api_list_invoices": ("facturacion",),
    "dashboard.api_invoice_detail": ("facturacion",),
    "dashboard.api_export_invoices": ("facturacion",),
    "dashboard.api_sync_invoices": ("facturacion",),
    "dashboard.motorizados_page": ("motorizados",),
    "dashboard.create_courier_endpoint": ("motorizados",),
    "dashboard.update_courier_endpoint": ("motorizados",),
    "dashboard.update_courier_locality_assignment": ("motorizados",),
    "dashboard.probar_aviso": ("motorizados",),
    "dashboard_agenda.*": ("agenda",),
    "dashboard.samples_page": ("muestras",),
    "dashboard.update_sample_status": ("muestras",),
    "dashboard.assign_profile_to_samples": ("muestras",),
    "dashboard.list_custom_profiles": ("muestras",),
    "dashboard.save_custom_profile": ("muestras",),
    "dashboard.rename_custom_profile": ("muestras",),
    "dashboard.delete_custom_profile": ("muestras",),
    "dashboard.update_catalog_item": ("precios",),
    "dashboard.update_discount_tiers": ("precios",),
    "dashboard.api_anarvet_clients": ("resultados",),
    "dashboard.api_anarvet_assign": ("resultados",),
    "dashboard.api_anarvet_automatch": ("resultados",),
    "dashboard.api_anarvet_sync": ("resultados",),
    "dashboard_results.*": ("resultados",),
    "dashboard_anarvet.*": ("resultados",),
    "dashboard_import.*": ("cargas",),
    "dashboard_users.*": ("usuarios",),
    "dashboard_maestros.client_ficha": ("clientes",),
    "dashboard_maestros.courier_delete": ("motorizados",),
    "dashboard_maestros.courier_transfer": ("motorizados", "agenda"),
    "dashboard_maestros.historial": ("clientes", "motorizados", "muestras"),
    "dashboard_maestros.municipio": ("motorizados",),
}

# Rutas para cualquier persona con sesión (o sin ella, el login).
LIBRES = frozenset({"dashboard.login", "dashboard.logout", "dashboard.root",
                    "dashboard.get_column_prefs", "dashboard.save_column_prefs"})

# Qué módulo hace falta gestionar para cada tipo de carga masiva: Cargas es la puerta,
# pero cargar precios exige poder cambiar precios, y cargar clientes, gestionar clientes.
MODULO_DE_CARGA = {"precios": "precios", "portafolio": "precios", "clientes": "clientes",
                   "motorizados": "motorizados"}


def nivel(perfil: str | None, modulo: str) -> int:
    if perfil == "administrador":
        return GESTION
    fila = _MATRIZ.get(perfil or "")
    if not fila or modulo not in MODULOS:
        return NINGUNO
    return fila[MODULOS.index(modulo)]


def puede(perfil: str | None, modulo: str, requerido: int = CONSULTA) -> bool:
    return nivel(perfil, modulo) >= requerido


def modulos_de(endpoint: str) -> tuple[str, ...] | None:
    """Módulos que habilitan una ruta, o None si la ruta no está mapeada."""
    if endpoint in _ENDPOINTS:
        return _ENDPOINTS[endpoint]
    return _ENDPOINTS.get(endpoint.split(".")[0] + ".*")


def permite(perfil: str | None, endpoint: str, requerido: int) -> bool:
    """¿El perfil puede usar esta ruta con este nivel? Ruta sin mapear = cerrada."""
    if endpoint in LIBRES:
        return True
    modulos = modulos_de(endpoint)
    return bool(modulos) and any(puede(perfil, m, requerido) for m in modulos)

