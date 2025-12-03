$(document).ready(function() {
    console.log("Document ready, setting up drag functionality");

    // Track highest z-index so active card floats on top
    let highestZ = 1000;

    function bringToFront($element) {
        if (!$element || $element.length === 0) {
            return;
        }
        if ($element.data('raising')) {
            return;
        }
        $element.data('raising', true);
        highestZ += 1;
        $element.css('z-index', highestZ);
        requestAnimationFrame(() => {
            $element.removeData('raising');
        });
    }

    function monitorVisibilityElement($element) {
        if (!$element || $element.length === 0) {
            return;
        }
        if ($element.data('visibilityObserver')) {
            return;
        }

        // If already visible when initialized, bring to front
        let lastVisible = $element.is(':visible');
        if (lastVisible) {
            bringToFront($element);
        }

        const element = $element.get(0);
        const observer = new MutationObserver(function(mutations) {
            let visibilityChanged = false;
            mutations.forEach(function(mutation) {
                if (mutation.attributeName === 'style' || mutation.attributeName === 'class') {
                    visibilityChanged = true;
                }
            });
            if (!visibilityChanged) {
                return;
            }
            const isVisible = $element.is(':visible');
            if (isVisible && !lastVisible) {
                bringToFront($element);
            }
            lastVisible = isVisible;
        });
        observer.observe(element, { attributes: true, attributeFilter: ['style', 'class'] });
        $element.data('visibilityObserver', observer);
    }

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

                const $summary = $('#place-summary-container');
                $summary.draggable({
                    handle: '#summary-header',
                    containment: 'window',
                    start: function(event, ui) {
                        bringToFront($(this));
                        $(this).addClass("dragging");
                        console.log("Started dragging summary");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging summary at:", ui.position);
                    }
                }).on('mousedown', function() {
                    bringToFront($(this));
                });
                monitorVisibilityElement($summary);
            }

            // Initialize place-names-container if it exists
            if ($('#place-names-container').length > 0) {
                console.log("Found place-names-container, making it draggable");

                const $places = $('#place-names-container');
                $places.draggable({
                    handle: '#place-names-header',
                    containment: 'window',
                    start: function(event, ui) {
                        bringToFront($(this));
                        $(this).addClass("dragging");
                        console.log("Started dragging places");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging places at:", ui.position);
                    }
                }).on('mousedown', function() {
                    bringToFront($(this));
                });
                monitorVisibilityElement($places);
            }

            // Initialize place-similarity-dialog if it exists
            if ($('#place-similarity-dialog').length > 0) {
                console.log("Found place-similarity-dialog, making it draggable");

                const $similarity = $('#place-similarity-dialog');
                $similarity.draggable({
                    handle: '#similarity-header',
                    containment: 'window',
                    start: function(event, ui) {
                        bringToFront($(this));
                        $(this).addClass("dragging");
                        console.log("Started dragging similarity dialog");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging similarity dialog at:", ui.position);
                    }
                }).on('mousedown', function() {
                    bringToFront($(this));
                });
                monitorVisibilityElement($similarity);
            }

            // Initialize corpus-controls-container if it exists
            if ($('#corpus-controls-container').length > 0) {
                console.log("Found corpus-controls-container, making it draggable");

                const $corpusControls = $('#corpus-controls-container');
                $corpusControls.draggable({
                    handle: '#corpus-header',
                    containment: 'window',
                    start: function(event, ui) {
                        bringToFront($(this));
                        $(this).addClass("dragging");
                        console.log("Started dragging corpus controls");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging corpus controls at:", ui.position);
                    }
                }).on('mousedown', function() {
                    bringToFront($(this));
                });
                monitorVisibilityElement($corpusControls);
            }

            // Initialize visuals containers (map + heatmap) if they exist
            const visualConfigs = [
                { selector: '#map-visuals-container', handle: '#map-visuals-header', label: 'map visuals' },
                { selector: '#heatmap-visuals-container', handle: '#heatmap-visuals-header', label: 'heatmap visuals' }
            ];

            visualConfigs.forEach(({ selector, handle, label }) => {
                if ($(selector).length > 0) {
                    console.log(`Found ${selector}, making it draggable`);
                    const $visualCard = $(selector);
                    $visualCard.draggable({
                        handle,
                        containment: 'window',
                        start: function(event, ui) {
                            bringToFront($(this));
                            $(this).addClass("dragging");
                            console.log(`Started dragging ${label}`);
                        },
                        stop: function(event, ui) {
                            $(this).removeClass("dragging");
                            console.log(`Stopped dragging ${label} at:`, ui.position);
                        }
                    }).on('mousedown', function() {
                        bringToFront($(this));
                    });
                    monitorVisibilityElement($visualCard);
                }
            });

            // Initialize corpus-builder-card if it exists
            if ($('#corpus-builder-card').length > 0) {
                console.log("Found corpus-builder-card, making it draggable");
                const $builder = $('#corpus-builder-card');
                $builder.draggable({
                    handle: '#corpus-builder-header',
                    containment: 'window',
                    start: function(event, ui) {
                        bringToFront($(this));
                        $(this).addClass("dragging");
                        console.log("Started dragging corpus builder card");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging corpus builder card at:", ui.position);
                    }
                }).on('mousedown', function() {
                    bringToFront($(this));
                });
                monitorVisibilityElement($builder);
            }

            // Initialize collocation-card if it exists
            if ($('#collocation-card').length > 0) {
                console.log("Found collocation-card, making it draggable");
                const $collocation = $('#collocation-card');
                $collocation.draggable({
                    handle: '#collocation-card-header',
                    containment: 'window',
                    start: function(event, ui) {
                        bringToFront($(this));
                        $(this).addClass("dragging");
                        console.log("Started dragging collocation card");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging collocation card at:", ui.position);
                    }
                }).on('mousedown', function() {
                    bringToFront($(this));
                });
                monitorVisibilityElement($collocation);
            }

            // Initialize author-list-container if it exists
            if ($('#author-list-container').length > 0) {
                console.log("Found author-list-container, making it draggable");
                const $authorList = $('#author-list-container');
                $authorList.draggable({
                    handle: '.card-title-bar', // Use standard class
                    containment: 'window',
                    start: function(event, ui) {
                        bringToFront($(this));
                        $(this).addClass("dragging");
                        console.log("Started dragging author list");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging author list at:", ui.position);
                    }
                }).on('mousedown', function() {
                    bringToFront($(this));
                });
                monitorVisibilityElement($authorList);
            }

            // Initialize author-info-container if it exists
            if ($('#author-info-container').length > 0) {
                console.log("Found author-info-container, making it draggable");
                const $authorInfo = $('#author-info-container');
                $authorInfo.draggable({
                    handle: '.card-title-bar', // Use standard class
                    containment: 'window',
                    start: function(event, ui) {
                        bringToFront($(this));
                        $(this).addClass("dragging");
                        console.log("Started dragging author info");
                    },
                    stop: function(event, ui) {
                        $(this).removeClass("dragging");
                        console.log("Stopped dragging author info at:", ui.position);
                    }
                }).on('mousedown', function() {
                    bringToFront($(this));
                });
                monitorVisibilityElement($authorInfo);
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

        // Check place similarity dialog
        if ($('#place-similarity-dialog').is(':visible') && 
            !$('#place-similarity-dialog').hasClass('ui-draggable')) {
            console.log("Similarity dialog is visible but not draggable yet, initializing");
            initializeDraggable();
        }

        // Check corpus controls container
        if ($('#corpus-controls-container').is(':visible') && 
            !$('#corpus-controls-container').hasClass('ui-draggable')) {
            console.log("Corpus controls container is visible but not draggable yet, initializing");
            initializeDraggable();
        }

        ['#map-visuals-container', '#heatmap-visuals-container'].forEach(function(selector) {
            if ($(selector).is(':visible') && !$(selector).hasClass('ui-draggable')) {
                console.log(selector + " is visible but not draggable yet, initializing");
                initializeDraggable();
            }
        });

        // Check collocation card
        if ($('#collocation-card').is(':visible') && 
            !$('#collocation-card').hasClass('ui-draggable')) {
            console.log("Collocation card is visible but not draggable yet, initializing");
            initializeDraggable();
        }

        // Check author list container
        if ($('#author-list-container').is(':visible') && 
            !$('#author-list-container').hasClass('ui-draggable')) {
            console.log("Author list container is visible but not draggable yet, initializing");
            initializeDraggable();
        }

        // Check author info container
        if ($('#author-info-container').is(':visible') && 
            !$('#author-info-container').hasClass('ui-draggable')) {
            console.log("Author info container is visible but not draggable yet, initializing");
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

        // Check place similarity dialog
        if ($('#place-similarity-dialog').is(':visible') && 
            !$('#place-similarity-dialog').hasClass('ui-draggable')) {
            console.log("Similarity dialog is visible in interval check but not draggable, initializing");
            initializeDraggable();
        }

        // Check corpus controls container
        if ($('#corpus-controls-container').is(':visible') && 
            !$('#corpus-controls-container').hasClass('ui-draggable')) {
            console.log("Corpus controls container is visible in interval check but not draggable, initializing");
            initializeDraggable();
        }

        ['#map-visuals-container', '#heatmap-visuals-container'].forEach(function(selector) {
            if ($(selector).is(':visible') && !$(selector).hasClass('ui-draggable')) {
                console.log(selector + " is visible in interval check but not draggable, initializing");
                initializeDraggable();
            }
        });

        // Check collocation card
        if ($('#collocation-card').is(':visible') && 
            !$('#collocation-card').hasClass('ui-draggable')) {
            console.log("Collocation card is visible in interval check but not draggable, initializing");
            initializeDraggable();
        }

        // Check author list container
        if ($('#author-list-container').is(':visible') && 
            !$('#author-list-container').hasClass('ui-draggable')) {
            console.log("Author list container is visible in interval check but not draggable, initializing");
            initializeDraggable();
        }

        // Check author info container
        if ($('#author-info-container').is(':visible') && 
            !$('#author-info-container').hasClass('ui-draggable')) {
            console.log("Author info container is visible in interval check but not draggable, initializing");
            initializeDraggable();
        }
    }, 2000);

    // Set cursor styles
    $("#summary-header, #place-names-header, #corpus-header, #map-visuals-header, #heatmap-visuals-header, #corpus-builder-header, #collocation-card-header, #similarity-header, #author-list-header, #author-info-header, .card-title-bar").css("cursor", "grab");

    // Add touch support for draggable elements
    function addTouchSupport() {
        $('#place-summary-container, #place-names-container, #corpus-controls-container, #map-visuals-container, #heatmap-visuals-container, #collocation-card, #place-similarity-dialog, #author-list-container, #author-info-container').on('touchstart', function(event) {
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

        $('#place-summary-container, #place-names-container, #corpus-controls-container, #map-visuals-container, #heatmap-visuals-container, #collocation-card, #place-similarity-dialog, #author-list-container, #author-info-container').on('touchmove', function(event) {
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

        $('#place-summary-container, #place-names-container, #corpus-controls-container, #map-visuals-container, #heatmap-visuals-container, #collocation-card, #place-similarity-dialog, #author-list-container, #author-info-container').on('touchend', function(event) {
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

    // Add this function to center the corpus builder card in pixels
    function centerCorpusBuilderCard() {
        var card = document.getElementById('corpus-builder-card');
        if (card && card.style.display === 'block') {
            // Remove transform if present
            card.style.transform = '';
            // Set left in px to center
            var windowWidth = window.innerWidth;
            var cardWidth = card.offsetWidth || 350;
            var leftPx = Math.max(0, Math.round((windowWidth - cardWidth) / 2));
            card.style.left = leftPx + 'px';
        }
    }

    // Observe style changes to the corpus builder card to trigger centering
    var corpusBuilderCard = document.getElementById('corpus-builder-card');
    if (corpusBuilderCard) {
        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                    if (corpusBuilderCard.style.display === 'block') {
                        centerCorpusBuilderCard();
                    }
                }
            });
        });
        observer.observe(corpusBuilderCard, { attributes: true });
    }

    // Optionally, recenter on window resize if the card is visible and hasn't been dragged
    window.addEventListener('resize', function() {
        var card = document.getElementById('corpus-builder-card');
        if (card && card.style.display === 'block' && !card.classList.contains('ui-draggable-dragging')) {
            centerCorpusBuilderCard();
        }
    });
});