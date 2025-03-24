$(document).ready(function() {
    console.log("Document ready, setting up drag functionality");

    // Function to initialize draggable behavior
    function initializeDraggable() {
        console.log("Initializing draggable elements");

        try {
            // Check if jQuery UI is loaded
            if (typeof $.ui === 'undefined') {
                console.error("jQuery UI is not loaded!");
                return;
            }

            // Initialize place-summary-container if it exists
            if ($('#place-summary-container').length > 0) {
                console.log("Found place-summary-container, making it draggable");

                $('#place-summary-container').draggable({
                    handle: '#summary-header',
                    containment: 'window',
                    start: function(event, ui) {
                        $(this).addClass("dragging");
                        console.log("Started dragging summary");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging summary at:", ui.position);
                    }
                });
            } else {
                console.log("Place summary container not found yet, will try again later");
            }

            // Initialize place-names-container if it exists
            if ($('#place-names-container').length > 0) {
                console.log("Found place-names-container, making it draggable");

                $('#place-names-container').draggable({
                    handle: '#places-header',
                    containment: 'window',
                    start: function(event, ui) {
                        $(this).addClass("dragging");
                        console.log("Started dragging places");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging places at:", ui.position);
                    }
                });
            } else {
                console.log("Place names container not found yet, will try again later");
            }

            console.log("Draggable initialization attempt completed");
        } catch (error) {
            console.error("Error initializing draggable:", error);
        }
    }

    // Try to initialize when document is ready
    initializeDraggable();

    // Also try when elements are clicked (they might appear later)
    $(document).on('click', function() {
        // Check place summary container
        if ($('#place-summary-container').is(':visible') && 
            !$('#place-summary-container').hasClass('ui-draggable')) {
            console.log("Summary container is visible but not draggable yet, initializing");
            initializeDraggable();
        }

        // Check place names container
        if ($('#place-names-container').is(':visible') && 
            !$('#place-names-container').hasClass('ui-draggable')) {
            console.log("Places container is visible but not draggable yet, initializing");
            initializeDraggable();
        }
    });

    // Also check periodically
    setInterval(function() {
        // Check place summary container
        if ($('#place-summary-container').is(':visible') && 
            !$('#place-summary-container').hasClass('ui-draggable')) {
            console.log("Summary container is visible in interval check but not draggable, initializing");
            initializeDraggable();
        }

        // Check place names container
        if ($('#place-names-container').is(':visible') && 
            !$('#place-names-container').hasClass('ui-draggable')) {
            console.log("Places container is visible in interval check but not draggable, initializing");
            initializeDraggable();
        }
    }, 2000);

    // Set cursor styles
    $("#summary-header, #places-header").css("cursor", "grab");

    // Add touch support for draggable elements
    function addTouchSupport() {
        $('#place-summary-container, #place-names-container').on('touchstart', function(event) {
            var touch = event.originalEvent.touches[0];
            var simulatedEvent = new MouseEvent('mousedown', {
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: touch.clientX,
                clientY: touch.clientY
            });
            touch.target.dispatchEvent(simulatedEvent);
            event.preventDefault();
        });

        $('#place-summary-container, #place-names-container').on('touchmove', function(event) {
            var touch = event.originalEvent.touches[0];
            var simulatedEvent = new MouseEvent('mousemove', {
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: touch.clientX,
                clientY: touch.clientY
            });
            touch.target.dispatchEvent(simulatedEvent);
            event.preventDefault();
        });

        $('#place-summary-container, #place-names-container').on('touchend', function(event) {
            var simulatedEvent = new MouseEvent('mouseup', {
                bubbles: true,
                cancelable: true,
                view: window
            });
            event.target.dispatchEvent(simulatedEvent);
            event.preventDefault();
        });
    }

    // Add touch support when document is ready
    addTouchSupport();
});