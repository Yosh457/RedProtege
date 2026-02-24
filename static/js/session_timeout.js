/*
 * session_timeout.js
 * -------------------------------------------------------
 * Maneja el cierre automático de sesión por inactividad.
 *
 * Funcionamiento:
 * - Detecta actividad del usuario (mouse, teclado, scroll, etc.)
 * - A los X minutos muestra un modal de advertencia
 * - Muestra un contador regresivo automático
 * - Al cumplirse el tiempo máximo, cierra la sesión
 *
 * IMPORTANTE:
 * - Solo se cambian TIEMPO_ADVERTENCIA y TIEMPO_MAXIMO
 * - El contador se calcula SOLO automáticamente
 * - Los tiempos se calcular en milisegundos (1 minuto = 60 * 1000 ms)
 */

(function() {

    /* =====================================================
     * CONFIGURACIÓN (ÚNICO LUGAR DONDE TOCAR TIEMPOS)
     * ===================================================== */

    // Tiempo sin actividad para mostrar advertencia
    const TIEMPO_ADVERTENCIA = 8 * 60 * 1000; // 8 minutos

    // Tiempo total antes de cerrar sesión
    const TIEMPO_MAXIMO = 10 * 60 * 1000;     // 10 minutos

    // Tiempo del contador (derivado automáticamente)
    const TIEMPO_CONTADOR = (TIEMPO_MAXIMO - TIEMPO_ADVERTENCIA) / 1000;
    
    /* =====================================================
     * VARIABLES INTERNAS
     * ===================================================== */

    let warningTimer;
    let logoutTimer;
    let countdownInterval;
    let tiempoRestante = TIEMPO_CONTADOR;

    // Elementos del DOM (se obtienen al cargar)
    let modal;
    let btnMantener;
    let contador;

    /* =====================================================
     * INICIALIZACIÓN
     * ===================================================== */

    function init() {
        modal = document.getElementById('modal-inactividad');
        btnMantener = document.getElementById('btn-mantener-sesion');
        contador = document.getElementById('contador-expiracion');

         // Si no existe el modal (ej: en login), no hacemos nada
        if (!modal || !btnMantener) return;

        // Event listeners para actividad del usuario
        ['click', 'mousemove', 'keypress', 'scroll', 'touchstart'].forEach(evt => {
            document.addEventListener(evt, () => {
                // Solo reinicia si el modal NO está visible
                if (modal.classList.contains('hidden')) {
                    resetTimers();
                }
            }, true);
        });

        // Botón del modal para mantener la sesión
        btnMantener.addEventListener('click', () => {
            clearInterval(countdownInterval);
            ocultarModal();
            resetTimers();
        });

        // Iniciar temporizadores
        startTimers();
    }

    /* =====================================================
     * CONTROL DE TIMERS
     * ===================================================== */

    function startTimers() {
        // Timer 1: Mostrar Advertencia
        warningTimer = setTimeout(mostrarModal, TIEMPO_ADVERTENCIA);
        
        // Timer 2: Cierre de Sesión Automatico (backup por si falla la lógica del modal)
        logoutTimer = setTimeout(cerrarSesion, TIEMPO_MAXIMO);
    }

    function resetTimers() {
        clearTimeout(warningTimer);
        clearTimeout(logoutTimer);
        clearInterval(countdownInterval);
        startTimers();
    }

    /* =====================================================
     * MODAL + CONTADOR
     * ===================================================== */

    function mostrarModal() {
        if (!modal) return;

        modal.classList.remove('hidden');
        // Opcional: Sonido de alerta
        // new Audio('/static/sounds/alert.mp3').play().catch(()=>{}); 

        // Inicializar contador
        tiempoRestante = TIEMPO_CONTADOR;
        actualizarContador();

        countdownInterval = setInterval(() => {
            tiempoRestante--;
            actualizarContador();

            if (tiempoRestante <= 0) {
                clearInterval(countdownInterval);
            }
        }, 1000);
    }

    function ocultarModal() {
        if (modal) {
            modal.classList.add('hidden');
        }
    }

    function actualizarContador() {
        if (!contador) return;

        const minutos = String(Math.floor(tiempoRestante / 60)).padStart(2, '0');
        const segundos = String(tiempoRestante % 60).padStart(2, '0');

        contador.textContent = `${minutos}:${segundos}`;
    }

    /* =====================================================
     * CIERRE DE SESIÓN
     * ===================================================== */

    function cerrarSesion() {
        window.location.href = "/logout?reason=timeout";
    }

    /* =====================================================
     * ARRANQUE
     * ===================================================== */

    // Inicializar cuando cargue el DOM
    document.addEventListener('DOMContentLoaded', init);

})();