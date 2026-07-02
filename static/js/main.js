// Main application JavaScript
// Additional interactive features

// Close modals when clicking outside
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        e.target.classList.remove('show');
    }
});

// Close modals with Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal.show').forEach(m => m.classList.remove('show'));
    }
});

// Auto-dismiss alerts
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.alert').forEach(el => {
        setTimeout(() => { el.style.opacity = '0'; }, 5000);
        setTimeout(() => { el.remove(); }, 6000);
    });
});
