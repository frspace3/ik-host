(function() {
    // 1. Inject CSS for user-select protection
    const style = document.createElement('style');
    style.innerHTML = `
        /* Disable text selection globally */
        body, html {
            -webkit-user-select: none !important;
            -moz-user-select: none !important;
            -ms-user-select: none !important;
            user-select: none !important;
        }
        /* Allow selection in input fields, textareas, contenteditable elements, and CodeMirror editor */
        input, textarea, [contenteditable], [contenteditable] *, .CodeMirror, .CodeMirror * {
            -webkit-user-select: text !important;
            -moz-user-select: text !important;
            -ms-user-select: text !important;
            user-select: text !important;
        }
    `;
    if (document.head) {
        document.head.appendChild(style);
    } else {
        document.addEventListener('DOMContentLoaded', function() {
            document.head.appendChild(style);
        });
    }

    // Helper to check if event target is inside an exempt editor/input element
    function isExempt(target) {
        if (!target) return false;
        return !!(
            target.closest('input') || 
            target.closest('textarea') || 
            target.closest('[contenteditable]') || 
            target.closest('.CodeMirror')
        );
    }

    // 2. Intercept context menu (right-click)
    document.addEventListener('contextmenu', function(e) {
        if (!isExempt(e.target)) {
            e.preventDefault();
            return false;
        }
    });

    // 3. Intercept copy event
    document.addEventListener('copy', function(e) {
        if (!isExempt(e.target)) {
            e.preventDefault();
            return false;
        }
    });

    // 4. Intercept keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // F12
        if (e.key === 'F12' || e.keyCode === 123) {
            e.preventDefault();
            return false;
        }

        const ctrlOrMeta = e.ctrlKey || e.metaKey;
        const shiftOrAlt = e.shiftKey || e.altKey;

        // Ctrl+Shift+I / J / C (DevTools) or Cmd+Opt+I / J / C (Mac DevTools)
        if (ctrlOrMeta && shiftOrAlt && (
            e.key === 'I' || e.key === 'i' || e.keyCode === 73 ||
            e.key === 'J' || e.key === 'j' || e.keyCode === 74 ||
            e.key === 'C' || e.key === 'c' || e.keyCode === 67
        )) {
            e.preventDefault();
            return false;
        }

        // Ctrl+U / Cmd+U (View Source)
        // Ctrl+S / Cmd+S (Save Page)
        // Ctrl+P / Cmd+P (Print Page)
        if (ctrlOrMeta && !e.shiftKey && (
            e.key === 'U' || e.key === 'u' || e.keyCode === 85 ||
            e.key === 'S' || e.key === 's' || e.keyCode === 83 ||
            e.key === 'P' || e.key === 'p' || e.keyCode === 80
        )) {
            e.preventDefault();
            return false;
        }

        // Ctrl+A / Cmd+A (Select All) - restricted unless target is exempt
        if (ctrlOrMeta && (e.key === 'A' || e.key === 'a' || e.keyCode === 65)) {
            if (!isExempt(e.target)) {
                e.preventDefault();
                return false;
            }
        }
    });

    // 5. Extra security check: disable drag-and-drop of images and links
    // But allow drag operations on deploy zones, file managers, and draggable cards
    document.addEventListener('dragstart', function(e) {
        const tag = e.target.tagName;
        // Allow drag on elements with draggable="true" attribute (e.g. srv-card reorder)
        if (e.target.getAttribute && e.target.getAttribute('draggable') === 'true') {
            return;
        }
        // Allow drag on elements inside deploy zones or file manager areas
        if (e.target.closest && (e.target.closest('#deployZone') || e.target.closest('#fileListWrap') || e.target.closest('.deploy-zone'))) {
            return;
        }
        if (tag === 'IMG' || tag === 'A') {
            e.preventDefault();
            return false;
        }
    });
})();
