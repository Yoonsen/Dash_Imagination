$(document).ready(function() {
    function setupDraggable() {
        if ($('#place-summary-container').length) {
            $('#place-summary-container').draggable({
                handle: '.card-header',
                containment: 'window',
                scroll: false
            });
        } else {
            setTimeout(setupDraggable, 500);
        }
    }
    setupDraggable();
});