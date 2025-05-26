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
            }

            // Initialize corpus-controls-container if it exists
            if ($('#corpus-controls-container').length > 0) {
                console.log("Found corpus-controls-container, making it draggable");

                $('#corpus-controls-container').draggable({
                    handle: '#corpus-header',
                    containment: 'window',
                    start: function(event, ui) {
                        $(this).addClass("dragging");
                        console.log("Started dragging corpus controls");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging corpus controls at:", ui.position);
                    }
                });
            }

            // Initialize visualization-controls-container if it exists
            if ($('#visualization-controls-container').length > 0) {
                console.log("Found visualization-controls-container, making it draggable");

                $('#visualization-controls-container').draggable({
                    handle: '#visualization-header',
                    containment: 'window',
                    start: function(event, ui) {
                        $(this).addClass("dragging");
                        console.log("Started dragging visualization controls");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging visualization controls at:", ui.position);
                    }
                });
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

        // Check corpus controls container
        if ($('#corpus-controls-container').is(':visible') && 
            !$('#corpus-controls-container').hasClass('ui-draggable')) {
            console.log("Corpus controls container is visible but not draggable yet, initializing");
            initializeDraggable();
        }

        // Check visualization controls container
        if ($('#visualization-controls-container').is(':visible') && 
            !$('#visualization-controls-container').hasClass('ui-draggable')) {
            console.log("Visualization controls container is visible but not draggable yet, initializing");
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

        // Check corpus controls container
        if ($('#corpus-controls-container').is(':visible') && 
            !$('#corpus-controls-container').hasClass('ui-draggable')) {
            console.log("Corpus controls container is visible in interval check but not draggable, initializing");
            initializeDraggable();
        }

        // Check visualization controls container
        if ($('#visualization-controls-container').is(':visible') && 
            !$('#visualization-controls-container').hasClass('ui-draggable')) {
            console.log("Visualization controls container is visible in interval check but not draggable, initializing");
            initializeDraggable();
        }
    }, 2000);

    // Set cursor styles
    $("#summary-header, #places-header, #corpus-header, #visualization-header").css("cursor", "grab");

    // Add touch support for draggable elements
    function addTouchSupport() {
        $('#place-summary-container, #place-names-container, #corpus-controls-container, #visualization-controls-container').on('touchstart', function(event) {
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

        $('#place-summary-container, #place-names-container, #corpus-controls-container, #visualization-controls-container').on('touchmove', function(event) {
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

        $('#place-summary-container, #place-names-container, #corpus-controls-container, #visualization-controls-container').on('touchend', function(event) {
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