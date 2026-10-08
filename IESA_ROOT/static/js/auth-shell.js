/* Auth pages (users/auth_shell.html): password visibility toggle + "one tap = one request". */
function togglePw(btn) {
    var input = btn.previousElementSibling, icon = btn.querySelector('i');
    if (!input) return;
    var show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    if (icon) icon.className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
    btn.setAttribute('aria-pressed', show ? 'true' : 'false');
}

(function () {
    'use strict';
    /* Slow mobile connections invite double taps; forms with data-au-once lock their submit button. */
    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (!form.matches || !form.matches('form[data-au-once]')) return;
        var btn = form.querySelector('button[type="submit"]');
        if (form.dataset.busy) { e.preventDefault(); return; }
        if (e.defaultPrevented) return;
        form.dataset.busy = '1';
        if (btn) setTimeout(function () { btn.disabled = true; }, 0);
    });
    /* Coming back with the browser's Back button must not leave a dead, disabled button. */
    window.addEventListener('pageshow', function (e) {
        if (!e.persisted) return;
        document.querySelectorAll('form[data-au-once]').forEach(function (form) {
            delete form.dataset.busy;
            var btn = form.querySelector('button[type="submit"]');
            if (btn) btn.disabled = false;
        });
    });
})();
