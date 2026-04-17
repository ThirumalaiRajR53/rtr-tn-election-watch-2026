/* TN Election Watch – shared client-side utilities */

document.addEventListener('DOMContentLoaded', () => {
    // Highlight active nav link
    const path = window.location.pathname;
    document.querySelectorAll('.navbar-nav .nav-link').forEach(link => {
        const href = link.getAttribute('href');
        if (href === path || (href !== '/' && path.startsWith(href))) {
            link.classList.add('active');
        }
    });
});

function formatINR(value) {
    if (value === null || value === undefined) return '—';
    const v = parseFloat(value);
    if (v >= 1e7) return '₹' + (v / 1e7).toFixed(2) + ' Cr';
    if (v >= 1e5) return '₹' + (v / 1e5).toFixed(2) + ' L';
    if (v >= 1e3) return '₹' + (v / 1e3).toFixed(1) + ' K';
    return '₹' + v.toLocaleString('en-IN');
}
