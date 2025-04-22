// static/js/script.js
document.addEventListener('DOMContentLoaded', function() {
    // Inicializar iconos Lucide (aunque también se hace en base.html)
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // Mensaje de confirmación para acciones importantes
    const confirmForms = document.querySelectorAll('.confirm-action');
    confirmForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const message = this.dataset.confirmMessage || '¿Estás seguro de realizar esta acción?';
            if (!confirm(message)) {
                e.preventDefault();
                return false;
            }
        });
    });

    // Copiar al portapapeles
    const copyButtons = document.querySelectorAll('.copy-to-clipboard');
    copyButtons.forEach(button => {
        button.addEventListener('click', function() {
            const textToCopy = this.dataset.copyText;
            navigator.clipboard.writeText(textToCopy).then(() => {
                // Cambiar temporalmente el texto del botón
                const originalText = this.innerHTML;
                const checkIcon = document.createElement('i');
                checkIcon.setAttribute('data-lucide', 'check');
                
                this.innerHTML = '';
                this.appendChild(checkIcon);
                this.appendChild(document.createTextNode(' Copiado'));
                
                // Volver a crear los iconos
                lucide.createIcons();
                
                setTimeout(() => {
                    this.innerHTML = originalText;
                    // Volver a crear los iconos si es necesario
                    if (originalText.includes('data-lucide')) {
                        lucide.createIcons();
                    }
                }, 2000);
            }).catch(err => {
                console.error('Error al copiar: ', err);
            });
        });
    });
    
    // Tooltips personalizados
    const tooltipTriggers = document.querySelectorAll('[data-tooltip]');
    tooltipTriggers.forEach(element => {
        element.addEventListener('mouseenter', function() {
            const tooltipText = this.dataset.tooltip;
            const tooltip = document.createElement('div');
            
            tooltip.className = 'bg-gray-900 text-white text-xs px-2 py-1 rounded absolute z-50 shadow-lg';
            tooltip.textContent = tooltipText;
            tooltip.style.top = (this.offsetTop - 30) + 'px';
            tooltip.style.left = (this.offsetLeft + this.offsetWidth / 2) + 'px';
            tooltip.style.transform = 'translateX(-50%)';
            
            document.body.appendChild(tooltip);
            
            this.addEventListener('mouseleave', function() {
                tooltip.remove();
            }, { once: true });
        });
    });
    
    // Animaciones de entrada
    const fadeElements = document.querySelectorAll('.fade-in');
    if (fadeElements.length > 0) {
        fadeElements.forEach((element, index) => {
            setTimeout(() => {
                element.classList.add('opacity-100');
                element.classList.remove('opacity-0');
            }, index * 100);
        });
    }
});