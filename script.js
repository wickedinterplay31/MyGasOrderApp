// Animation and Interaction Script for Gas Ordering App

function initializeApp() {
    initializeAnimations();
    initializeScrollAnimations();
    initializeFormValidations();
    initializeMenuInteractions();
    initializeStatsToggle();
    initializeToastNotifications();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}

// Initialize general animations
function initializeAnimations() {
    // Add stagger classes to cards for sequential animation
    const cards = document.querySelectorAll('.gas-card, .product-card, .role-btn');
    cards.forEach((card, index) => {
        card.classList.add(`stagger-${(index % 5) + 1}`);
        card.classList.add('float-up');
    });

    // Add breathing animation to important buttons
    const importantButtons = document.querySelectorAll('.btn-primary, .role-btn');
    importantButtons.forEach(btn => {
        btn.classList.add('breathe');
    });

    // Add pulse animation to notification elements
    const notifications = document.querySelectorAll('.toast');
    notifications.forEach(toast => {
        toast.classList.add('pulse');
    });
}

// Initialize scroll-triggered animations
function initializeScrollAnimations() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, observerOptions);

    // Observe elements that should fade in on scroll
    const fadeElements = document.querySelectorAll('.gas-card, .product-card, .report-table, .dashboard-section');
    fadeElements.forEach(el => {
        el.classList.add('fade-in');
        observer.observe(el);
    });
}

// Initialize form validation animations
function initializeFormValidations() {
    const forms = document.querySelectorAll('form');

    forms.forEach(form => {
        const inputs = form.querySelectorAll('input, textarea, select');

        inputs.forEach(input => {
            input.addEventListener('blur', function() {
                if (this.checkValidity() === false) {
                    this.classList.add('invalid');
                    // Shake animation will be triggered by CSS
                    setTimeout(() => {
                        this.classList.remove('invalid');
                    }, 300);
                }
            });

            input.addEventListener('input', function() {
                if (this.classList.contains('invalid') && this.checkValidity()) {
                    this.classList.remove('invalid');
                }
            });
        });

        // Add loading state to form submission
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.classList.add('loading');
                submitBtn.disabled = true;
            }
        });
    });
}

// Initialize menu interactions
function initializeMenuInteractions() {
    const toggles = document.querySelectorAll('.menu-toggle-btn, #menu-toggle');
    const menu = document.querySelector('.dashboard-menu');
    const layout = document.querySelector('.dashboard-layout');

    if (!menu || toggles.length === 0) {
        return;
    }

    let closeTimeout;

    function openMenu(toggle) {
        menu.classList.add('menu-open');
        menu.style.width = '220px';
        menu.style.padding = '18px';
        menu.style.opacity = '1';
        menu.style.visibility = 'visible';
        if (layout) {
            layout.classList.add('menu-open');
        }
        if (toggle) {
            toggle.classList.add('menu-open');

            const spans = toggle.querySelectorAll('span');
            if (spans.length === 3) {
                spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
                spans[1].style.opacity = '0';
                spans[2].style.transform = 'rotate(-45deg) translate(7px, -6px)';
            }
        }
    }

    function closeMenu() {
        menu.classList.remove('menu-open');
        menu.style.width = '0';
        menu.style.padding = '18px 0';
        menu.style.opacity = '0';
        menu.style.visibility = 'hidden';
        if (layout) {
            layout.classList.remove('menu-open');
        }
        toggles.forEach(toggle => {
            toggle.classList.remove('menu-open');
            const spans = toggle.querySelectorAll('span');
            if (spans.length === 3) {
                spans[0].style.transform = 'none';
                spans[1].style.opacity = '1';
                spans[2].style.transform = 'none';
            }
        });
    }

    function scheduleClose() {
        clearTimeout(closeTimeout);
        closeTimeout = setTimeout(() => {
            if (!Array.from(toggles).some(toggle => toggle.matches(':hover')) && !menu.matches(':hover')) {
                closeMenu();
            }
        }, 120);
    }

    toggles.forEach(toggle => {
        toggle.addEventListener('mouseenter', function() {
            openMenu(toggle);
        });

        toggle.addEventListener('mouseleave', scheduleClose);
    });

    menu.addEventListener('mouseenter', function() {
        clearTimeout(closeTimeout);
    });

    menu.addEventListener('mouseleave', scheduleClose);

    document.addEventListener('click', function(event) {
        if (!menu.contains(event.target) && !Array.from(toggles).some(toggle => toggle.contains(event.target))) {
            closeMenu();
        }
    });

    // Add hover effects to menu items
    const menuItems = document.querySelectorAll('.menu-item');
    menuItems.forEach(item => {
        item.addEventListener('mouseenter', function() {
            this.style.transform = 'translateX(10px)';
        });

        item.addEventListener('mouseleave', function() {
            this.style.transform = 'translateX(0)';
        });
    });
}

function initializeStatsToggle() {
    const toggles = document.querySelectorAll('.stats-toggle');
    toggles.forEach(toggle => {
        const card = toggle.closest('.menu-stats-card');
        const detail = card ? card.querySelector('.stats-detail') : null;
        if (!detail) {
            return;
        }

        toggle.addEventListener('click', function() {
            const isOpen = detail.classList.toggle('open');
            detail.hidden = !isOpen;
            toggle.textContent = isOpen ? 'Hide details' : 'Show details';
        });
    });
}

// Initialize toast notifications
function initializeToastNotifications() {
    const toasts = document.querySelectorAll('.toast');

    toasts.forEach(toast => {
        // Auto-hide toasts after 5 seconds
        setTimeout(() => {
            toast.style.animation = 'slideOutRight 0.5s ease-out forwards';
            setTimeout(() => {
                toast.remove();
            }, 500);
        }, 5000);

        // Add close functionality
        const closeBtn = toast.querySelector('.close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                toast.style.animation = 'slideOutRight 0.3s ease-out forwards';
                setTimeout(() => {
                    toast.remove();
                }, 300);
            });
        }
    });
}

// Utility function to create toast notifications
function showToast(message, type = 'info') {
    const toastContainer = document.querySelector('.toast-container') || createToastContainer();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button class="close-btn">&times;</button>
    `;

    toastContainer.appendChild(toast);

    // Initialize the new toast
    initializeToastNotifications();
}

function createToastContainer() {
    const container = document.createElement('div');
    container.className = 'toast-container';
    container.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 1000;
        max-width: 400px;
    `;
    document.body.appendChild(container);
    return container;
}

// Add click animations to buttons
document.addEventListener('click', function(e) {
    if (e.target.matches('button, .button, .gas-card, .product-card')) {
        e.target.style.transform = 'scale(0.95)';
        setTimeout(() => {
            e.target.style.transform = '';
        }, 150);
    }
});

// Add keyboard navigation enhancements
document.addEventListener('keydown', function(e) {
    // Close modals with Escape key
    if (e.key === 'Escape') {
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            modal.style.display = 'none';
        });
    }

    // Enhance tab navigation with focus animations
    if (e.key === 'Tab') {
        setTimeout(() => {
            const focused = document.activeElement;
            if (focused && (focused.tagName === 'INPUT' || focused.tagName === 'TEXTAREA' || focused.tagName === 'SELECT')) {
                focused.style.boxShadow = '0 0 0 3px rgba(52, 152, 219, 0.3)';
            }
        }, 10);
    }
});

// Add page transition effects
window.addEventListener('beforeunload', function() {
    document.body.style.opacity = '0';
    document.body.style.transform = 'scale(0.95)';
});

// Performance optimization: Debounce scroll events
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Add smooth scrolling to anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Add loading states for AJAX requests (if any)
const originalFetch = window.fetch;
window.fetch = function(...args) {
    document.body.classList.add('loading');
    return originalFetch.apply(this, args).finally(() => {
        document.body.classList.remove('loading');
    });
};