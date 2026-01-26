// static/js/modal_handler.js

function setupEditConfirmation() {
    const editForm = document.getElementById('edit-user-form');
    const modal = document.getElementById('confirmation-modal');
    const confirmBtn = document.getElementById('confirm-save');
    const cancelBtn = document.getElementById('cancel-save');

    // Si no existen los elementos en esta página, no hacemos nada
    if (!editForm || !modal) return;

    editForm.addEventListener('submit', function(event) {
        // 1. Prevenimos el envío inmediato
        event.preventDefault();
        // 2. Mostramos el modal (quitando la clase hidden si usas Tailwind, o display flex)
        // Nota: Como tu CSS usa 'hidden' de Tailwind, lo manejaremos con clases:
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    });

    confirmBtn.addEventListener('click', function() {
        // 3. Si confirma, enviamos el formulario real
        editForm.submit();
    });

    cancelBtn.addEventListener('click', function() {
        // 4. Si cancela, ocultamos el modal
        modal.classList.remove('flex');
        modal.classList.add('hidden');
    });
}

document.addEventListener('DOMContentLoaded', setupEditConfirmation);