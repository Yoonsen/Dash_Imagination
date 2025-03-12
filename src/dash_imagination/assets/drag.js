// assets/drag.js
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
            
            // Check if the place summary container exists
            if ($('#place-summary-container').length === 0) {
                console.log("Place summary container not found yet, waiting...");
                setTimeout(initializeDraggable, 500);
                return;
            }
            
            console.log("Found place-summary-container, making it draggable");
            
            // Initialize draggable
            $('#place-summary-container').draggable({
                handle: '#summary-header',
                containment: 'window',
                start: function(event, ui) {
                    console.log("Started dragging");
                },
                stop: function(event, ui) {
                    console.log("Stopped dragging at:", ui.position);
                }
            });
            
            console.log("Draggable initialized successfully");
        } catch (error) {
            console.error("Error initializing draggable:", error);
        }
    }
    
    // Try to initialize when document is ready
    initializeDraggable();
    
    // Also try when the map is clicked (the container might appear later)
    $(document).on('click', function() {
        if ($('#place-summary-container').is(':visible') && 
            !$('#place-summary-container').hasClass('ui-draggable')) {
            console.log("Container is visible but not draggable yet, initializing");
            initializeDraggable();
        }
    });
    
    // Also check periodically
    setInterval(function() {
        if ($('#place-summary-container').is(':visible') && 
            !$('#place-summary-container').hasClass('ui-draggable')) {
            console.log("Container is visible in interval check but not draggable, initializing");
            initializeDraggable();
        }
    }, 2000);
});