// static/js/flash_messages.js
document.addEventListener("DOMContentLoaded", () => {
    const flashMessages = document.querySelectorAll(".flash-message");

    flashMessages.forEach((message) => {
        // Espera 5 segundos
        setTimeout(() => {
            // Añade la clase que dispara la animación de salida
            message.classList.add("fade-out");

            // Espera a que termine la animación para eliminar el elemento
            message.addEventListener("animationend", () => {
                message.remove();
            });
        }, 5000); // 5000 milisegundos = 5 segundos
    });
});
