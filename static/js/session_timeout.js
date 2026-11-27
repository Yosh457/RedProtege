/*
 * session_timeout.js
 * Control visual del cierre automático de sesión por inactividad.
 *
 * Funcionamiento:
 * - Flask determina la vigencia y el vencimiento de la sesión.
 * - Detecta actividad del usuario para solicitar su renovación.
 * - Muestra un modal de advertencia con un contador regresivo.
 * - Permite renovar la sesión mediante POST con protección CSRF.
 * - Solicita el cierre de sesión al alcanzar el tiempo máximo.
 *
 * IMPORTANTE:
 * - El tiempo máximo de inactividad se configura en app.py.
 * - El tiempo de advertencia se configura en templates/base.html.
 * - JavaScript no determina por sí solo la validez de la sesión.
 */

(() => {
    'use strict';

    document.addEventListener('DOMContentLoaded', () => {

        // --- ELEMENTOS DEL DOM ---

        const config = document.getElementById('config-sesion');
        const modal = document.getElementById('modal-inactividad');
        const mantener = document.getElementById('btn-mantener-sesion');
        const contador = document.getElementById('contador-expiracion');
        const logoutForm = document.getElementById('form-logout-inactividad');

        // Si no existen los elementos requeridos (ej. en login), no hacemos nada.
        if (!config || !modal || !mantener || !contador || !logoutForm) return;

        // --- CONFIGURACIÓN ---

        // Tiempo restante para mostrar la advertencia de inactividad.
        const advertenciaMs = Number(config.dataset.advertenciaSegundos || 120) * 1000;

        // Intervalo mínimo entre solicitudes automáticas de renovación.
        const tiempoEntreRenovacionesMs = 45 * 1000;

        // --- VARIABLES INTERNAS ---

        let expiraEn = null;
        let ultimoEnvio = Date.now();
        let renovando = false;
        let finalizando = false;
        let actividadReciente = false;

        // --- CIERRE DE SESIÓN ---

        function irAlLogin() {
            if (finalizando) return;

            finalizando = true;
            window.location.assign(config.dataset.loginUrl);
        }

        function finalizarSesion() {
            if (finalizando) return;

            finalizando = true;

            // Un POST con CSRF solicita el cierre; si Flask ya expiró,
            // before_request redirigirá igualmente al login.
            logoutForm.submit();
        }

        // --- CONTROL DEL VENCIMIENTO ---

        function actualizarVencimiento(segundos) {
            // Calcular el vencimiento según el tiempo informado por Flask.
            expiraEn = Date.now() + Math.max(0, segundos) * 1000;
            ultimoEnvio = Date.now();
            actividadReciente = false;

            modal.classList.add('hidden');
            mantener.disabled = false;
            mantener.textContent = 'Permanecer Conectado';
        }

        // --- COMUNICACIÓN CON EL SERVIDOR ---

        async function solicitud(url, metodo = 'GET') {
            const opciones = {
                method: metodo,
                credentials: 'same-origin',
                cache: 'no-store',
                headers: { 'Accept': 'application/json' }
            };

            // Incorporar el token CSRF en las solicitudes POST.
            if (metodo === 'POST') {
                opciones.headers['X-CSRFToken'] = config.dataset.csrf;
            }

            const respuesta = await fetch(url, opciones);

            // Validar el estado HTTP y el formato de la respuesta.
            if (
                !respuesta.ok
                || !respuesta.headers.get('Content-Type')?.includes('application/json')
            ) {
                if (respuesta.status === 401 || respuesta.redirected) irAlLogin();

                throw new Error(`No se pudo comprobar la sesión (${respuesta.status})`);
            }

            const datos = await respuesta.json();

            // Redirigir al login si Flask informa que la sesión no es válida.
            if (!datos.autenticado) {
                irAlLogin();
                throw new Error('Sesión no válida');
            }

            return datos;
        }

        // --- RENOVACIÓN DE SESIÓN ---

        async function renovar(explicita = false) {
            // Evitar renovaciones simultáneas o durante el cierre de sesión.
            if (renovando || finalizando) return;

            // La renovación automática requiere actividad reciente y el modal oculto.
            if (!explicita && (!modal.classList.contains('hidden') || !actividadReciente)) return;

            renovando = true;

            // Deshabilitar temporalmente el botón durante la renovación manual.
            if (explicita) {
                mantener.disabled = true;
                mantener.textContent = 'Comprobando...';
            }

            try {
                const datos = await solicitud(config.dataset.renovarUrl, 'POST');
                actualizarVencimiento(datos.restante_segundos);

            } catch (error) {
                console.warn(error);

                if (explicita && !finalizando) {
                    mantener.disabled = false;
                    mantener.textContent = 'Reintentar';
                }

                // Ante fallos de red no se presupone que la sesión fue renovada.

            } finally {
                renovando = false;
            }
        }

        // --- DETECCIÓN DE ACTIVIDAD DEL USUARIO ---

        function registrarActividad() {
            if (finalizando || !modal.classList.contains('hidden')) return;

            actividadReciente = true;

            // Solo actividad real del usuario puede iniciar un POST de renovación.
            // Los eventos frecuentes no generan una petición por movimiento.
            if (Date.now() - ultimoEnvio >= tiempoEntreRenovacionesMs) {
                renovar();
            }
        }

        // Event listeners para detectar actividad del usuario.
        ['pointerdown', 'keydown', 'scroll', 'touchstart'].forEach(evento => {
            document.addEventListener(evento, registrarActividad, { passive: true });
        });

        // Para una escritura continua, no depende de clics de ratón.
        document.addEventListener('input', registrarActividad, { passive: true });

        // Botón del modal para mantener la sesión.
        mantener.addEventListener('click', () => renovar(true));

        // --- MODAL Y CONTADOR REGRESIVO ---

        function actualizarPantalla() {
            if (finalizando || expiraEn === null) return;

            // Calcular el tiempo restante según el vencimiento de la sesión.
            const restantes = Math.max(0, Math.ceil((expiraEn - Date.now()) / 1000));

            // Solicitar el cierre de sesión al alcanzar el tiempo máximo.
            if (restantes <= 0) {
                finalizarSesion();
                return;
            }

            // Mostrar el modal únicamente al alcanzar el tiempo de advertencia.
            if (restantes * 1000 <= advertenciaMs) {
                modal.classList.remove('hidden');

                const minutos = String(Math.floor(restantes / 60)).padStart(2, '0');
                const segundos = String(restantes % 60).padStart(2, '0');

                contador.textContent = `${minutos}:${segundos}`;

            } else {
                modal.classList.add('hidden');
            }
        }

        // --- CONSULTA DEL ESTADO DE SESIÓN ---

        async function consultarEstado() {
            if (finalizando) return;

            try {
                const datos = await solicitud(config.dataset.estadoUrl);

                actualizarVencimiento(datos.restante_segundos);
                actualizarPantalla();

            } catch (error) {
                console.warn(error);
            }
        }

        // --- SINCRONIZACIÓN Y ARRANQUE ---

        // Nunca renovamos por cargar la página, cambiar de pestaña o mediante sondeos.
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) consultarEstado();
        });

        // Consultar el estado al restaurar una página desde la caché del navegador.
        window.addEventListener('pageshow', (evento) => {
            if (evento.persisted) consultarEstado();
        });

        // Actualizar el contador visual cada segundo.
        setInterval(actualizarPantalla, 1000);

        // Consultar el estado inicial de la sesión al cargar la página.
        consultarEstado();
    });
})();