const DEFAULT_DURATION = 4000;
const MAX_TOASTS = 3;

function getContainer() {
    return document.getElementById('toast-container');
}

export function showToast(message, type = 'info', duration = DEFAULT_DURATION) {
    const container = getContainer();
    if (!container) {
        console.warn('Toast container missing; falling back to alert:', message);
        return;
    }

    // Skip if an identical message is already on screen (prevents spam from rapid clicks).
    const visible = container.querySelectorAll('.toast');
    if ([...visible].some((t) => t.dataset.message === message)) {
        return;
    }
    // Cap concurrent toasts so they never pile up — drop the oldest.
    if (visible.length >= MAX_TOASTS) {
        visible[0].remove();
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.dataset.message = message;
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toast.textContent = message;
    container.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('toast-visible'));

    const remove = () => {
        toast.classList.remove('toast-visible');
        toast.addEventListener('transitionend', () => toast.remove(), { once: true });
        setTimeout(() => toast.remove(), 400);
    };

    const timer = setTimeout(remove, duration);
    toast.addEventListener('click', () => {
        clearTimeout(timer);
        remove();
    });
}
