// app.js - JavaScript pour l'interface web DomusIA

document.addEventListener('DOMContentLoaded', function () {
    // Animation d'entrée pour les éléments
    const animatedElements = document.querySelectorAll('.animate-fade-in');
    animatedElements.forEach((el, index) => {
        el.style.animationDelay = `${index * 0.1}s`;
    });
});

// Fonction pour créer une session Stripe
async function createCheckoutSession(plan) {
    const button = event.target;
    const originalText = button.textContent;

    try {
        button.disabled = true;
        button.textContent = 'Chargement...';

        const formData = new FormData();
        formData.append('plan', plan);

        const response = await fetch('/payment/create-session', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.error) {
            alert('Erreur: ' + data.error);
            button.disabled = false;
            button.textContent = originalText;
            return;
        }

        // Rediriger vers Stripe Checkout
        if (data.checkout_url) {
            window.location.href = data.checkout_url;
        }

    } catch (error) {
        console.error('Erreur:', error);
        alert('Une erreur est survenue. Veuillez réessayer.');
        button.disabled = false;
        button.textContent = originalText;
    }
}

// Validation du formulaire d'inscription
function validateRegistrationForm() {
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirm_password');

    if (confirmPassword && password !== confirmPassword.value) {
        alert('Les mots de passe ne correspondent pas.');
        return false;
    }

    if (password.length < 8) {
        alert('Le mot de passe doit contenir au moins 8 caractères.');
        return false;
    }

    return true;
}

// Validation du numéro de téléphone
function validatePhoneNumber() {
    const phone = document.getElementById('phone_number').value;
    const cleaned = phone.replace(/\s/g, '');

    // Format attendu: +212XXXXXXXXX ou 0XXXXXXXXX
    const moroccanPattern = /^(\+212|0)[567]\d{8}$/;

    if (!moroccanPattern.test(cleaned)) {
        alert('Veuillez entrer un numéro de téléphone marocain valide (ex: +212612345678)');
        return false;
    }

    return true;
}

// Afficher/Masquer le mot de passe
function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    if (input.type === 'password') {
        input.type = 'text';
    } else {
        input.type = 'password';
    }
}

// Compte à rebours pour l'expiration du code
function startOtpCountdown(seconds) {
    const display = document.getElementById('otp-countdown');
    if (!display) return;

    let remaining = seconds;

    const interval = setInterval(() => {
        const minutes = Math.floor(remaining / 60);
        const secs = remaining % 60;
        display.textContent = `${minutes}:${secs.toString().padStart(2, '0')}`;

        if (remaining <= 0) {
            clearInterval(interval);
            display.textContent = 'Code expiré';
            display.classList.add('text-error');
        }

        remaining--;
    }, 1000);
}

// Formatage automatique du numéro de téléphone
function formatPhoneInput(input) {
    let value = input.value.replace(/\D/g, '');

    if (value.startsWith('212')) {
        value = '+' + value;
    } else if (value.startsWith('0')) {
        value = '+212' + value.substring(1);
    } else if (!value.startsWith('+')) {
        value = '+212' + value;
    }

    input.value = value;
}
