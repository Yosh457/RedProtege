// static/validation.js

document.addEventListener('DOMContentLoaded', () => {
    // Referencias a los elementos del DOM
    const passwordInput = document.getElementById('nueva_password');
    const confirmPasswordInput = document.getElementById('confirmar_password');
    const submitBtn = document.getElementById('submit-btn');
    const togglePassword = document.getElementById('toggle-password');
    const eyeIcon = document.getElementById('eye-icon');
    const eyeSlashIcon = document.getElementById('eye-slash-icon');

    // Referencias a los criterios de validación
    const lengthCheck = document.getElementById('length-check');
    const upperCheck = document.getElementById('upper-check');
    const numberCheck = document.getElementById('number-check');
    const matchCheck = document.getElementById('match-check');

    // Función para actualizar el estado visual de un criterio
    function updateCriterion(element, isValid) {
        if (isValid) {
            element.classList.remove('text-red-500');
            element.classList.add('text-green-500');
        } else {
            element.classList.remove('text-green-500');
            element.classList.add('text-red-500');
        }
    }

    // Función principal que se ejecuta cada vez que se escribe en el campo de contraseña
    function validatePassword() {
        const password = passwordInput.value;
        const confirmPassword = confirmPasswordInput.value;

        // 1. Validar longitud (mínimo 8 caracteres)
        const hasLength = password.length >= 8;
        updateCriterion(lengthCheck, hasLength);

        // 2. Validar si tiene al menos una mayúscula
        const hasUpperCase = /[A-Z]/.test(password);
        updateCriterion(upperCheck, hasUpperCase);

        // 3. Validar si tiene al menos un número
        const hasNumber = /[0-9]/.test(password);
        updateCriterion(numberCheck, hasNumber);

        // 4. Validar si la confirmación coincide
        const passwordsMatch = password === confirmPassword && password !== '';
        updateCriterion(matchCheck, passwordsMatch);

        // 5. Habilitar o deshabilitar el botón de envío
        // El botón solo se activa si TODOS los criterios son verdaderos
        if (hasLength && hasUpperCase && hasNumber && passwordsMatch) {
            submitBtn.disabled = false;
        } else {
            submitBtn.disabled = true;
        }
    }

    // --- EVENT LISTENERS ---

    // Escuchamos los eventos 'keyup' en ambos campos de contraseña
    passwordInput.addEventListener('keyup', validatePassword);
    confirmPasswordInput.addEventListener('keyup', validatePassword);

    // Lógica para el botón de mostrar/ocultar contraseña
    togglePassword.addEventListener('click', () => {
        // Cambiamos el tipo de input de 'password' a 'text' y viceversa
        const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
        passwordInput.setAttribute('type', type);
        confirmPasswordInput.setAttribute('type', type); // También afecta al campo de confirmación
        
        // Cambiamos el icono del ojo
        eyeIcon.classList.toggle('hidden');
        eyeSlashIcon.classList.toggle('hidden');
    });
});