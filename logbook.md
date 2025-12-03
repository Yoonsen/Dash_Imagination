# ImagiNation Development Logbook

## June 12, 2024: Design Decision – Orthogonal Book/Place Operations
- Discussed and agreed to treat book and place set operations (add, filter, subtract) as orthogonal, allowing users to manipulate books and places independently.
- The app will not force synchronization between books and places after every operation. Users can perform operations in any order, with the understanding that some places may not be represented in the current corpus if the related books are removed, and vice versa.
- If a user wants to ensure consistency, they can perform additional operations (e.g., filter places after changing books, or vice versa).
- In the future, advanced options may be added to allow pairwise operations on (books, places) together (e.g., "remove all books and places related to Hamsun").
- UI/UX will include tooltips or help text to explain this behavior and guide users.

> **Note (June 2024): Refactor in progress**
> We are currently refactoring the place sampling logic to ensure that all places for a selected corpus are extracted before any sampling or display limits are applied. This will improve accuracy and consistency when refining or displaying places. The reintroduction of a 'resample places' button is also under consideration.

> **Note (June 2024):** Currently, the heatmap visualization uses the sampled set of places (as shown on the map/list). In the future, an option will be added to the visualization tool to allow users to compute the heatmap using either the sampled set or the full set of places in the corpus. This will provide more flexibility for exploring density and distribution.

> **Planned (June 2024):** The place summary/info card will be redesigned to match the corpus card. It will include upload, download, and add (+) buttons, so users can define, upload, and manage places using different NLP techniques or manual curation. This will make place management as flexible and user-friendly as corpus management.

## Overview
This logbook tracks the development progress, decisions, and challenges of the ImagiNation project. It serves as a living document to maintain continuity between development sessions and track the evolution of the project.

## Current Sprint
**Period**: May 15-20, 2024
**Focus**: Place Search, Highlight Feature, and Place Intersectionality

## Active Tasks
- [x] Place Search implementation
- [x] Map centering functionality
- [x] Corpus management improvements
- [ ] Place intersectionality implementation
  - Intersect corpus and places on both place and book levels
  - Improve corpus building with place-based filtering
  - Add bidirectional filtering between places and books

## Recent Decisions
- Implemented global `current_dhlabids` list as single source of truth for corpus management
- Simplified corpus handling by removing redundant filtering logic
- Improved consistency between map data and place details
- Changed author handling: author lists are now split on '/' and deduplicated for dropdowns and stats. Filtering in the corpus builder uses substring matching (case-insensitive) so multi-author books are included. If performance becomes an issue, consider DB-side optimizations or new tables, but with ~20k books this is not expected to be a problem.

## Technical Challenges
- Resolved inconsistency between book counts and displayed books in place details
- Fixed corpus sampling issues by implementing global corpus management
- Improved SQLite query handling for large corpora

## Development Log

### November 26, 2025
- Marked `Corpus Modify` card as “ready”: layout tightened (Year → Metadata → Content), chip wiring verified, and builder visibility confirmed. Safe checkpoint before deployment tweaks.

### November 24, 2025 (Session 2: Authors & Images)
**Progress**:
- Introdusert en **Authors**-modul:
  - Ny pille "Authors" i venstre meny med "List"-valg.
  - Flytende kort med liste over alle forfattere i gjeldende korpus, filtrerbart søkefelt.
  - Detaljkort for valgt forfatter med bildegalleri (fra NB.no) og liste over bøker i korpuset.
- Forfattere identifiseres nå via en syntetisk `author_key` (LOWER(TRIM(author))) slik at klikk i listen alltid finner korrekt person selv om navnet er skrevet forskjellig i databasen.
- Implementert **Historiske Bilder** (IIIF):
  - Integrasjon mot NB.no sitt API for å hente bilder basert på søketermer (stedsnavn, forfatternavn).
  - Filterer på `mediaType=bilder` og sorterer etter dato (eldste først) for å finne relevante historiske foto.
  - Viser resultatene i en horisontal galleri-stripe i både "Place Info" og "Author Info".
  - Bilder er klikkbare og leder direkte til NB.no sin visning.
- Utvidet bildehentingen med Gallica (BnF): SRU-søk → IIIF-manifest → thumbnails, slik at vi alltid får noen treff selv når NB ikke har materiale.
- Galleriene viser nå inntil 5 bilder per kilde (NB + Gallica) med små kildebadges så brukeren ser hvor motivet kommer fra.
- UX-forbedringer:
  - Fikset omnibox-oppførsel: søkeskuffen lukkes ved klikk utenfor, men holdes åpen ved interaksjon (klient-side `preventDefault` på `mousedown`).
  - Fikset minimering av "Place Details" (hindret blankt innhold/resize-glitch).
  - Refaktorert nye Author-kort til å bruke `dbc.Card` for konsistent styling (farger, padding, skygger).
  - Oppdatert `drag.js` for å støtte de nye kortene.
  - Fjernet midlertidig minimeringsknappen på Place Details siden kortet åpnes raskt via kart/omnibox; notert for fremtidig reimplementasjon.
  - Erstattet W±/H±-knappene i tittelbaren med en egenutviklet sirkulær resize-kontroll: én knapp viser fire hotspots (blå plusser for å øke bredde/høyde, røde minus for å redusere) ved hover/fokus, med samme backend-logikk for `size-btn`. Gir et ryddigere, mer “mac”-aktig uttrykk.

**Notes**:
- Bildeoppslag er basert på tekstsøk, så presisjonen avhenger av metadata hos NB. For kjente steder og forfattere fungerer det utmerket.
- Appen har nå tre klare innganger til materialet: Bøker (Corpus), Steder (Places) og Mennesker (Authors).

### November 24, 2025 (Session 1: Omnibox)
**Progress**:
- Levered første versjon av omniboxen: parallelle treff for steder/bøker/forfattere, actions som “Vis på kartet”, “Åpne NB”, “Legg (alle) i korpus”.
- Multi-token søk (ordrekkefølge og komma spiller ingen rolle) med aggregering direkte fra SQLite, og handlingene skriver tilbake til de samme `dcc.Store`-ene som kortene bruker, så kartet oppdateres automatisk.
- La inn pillefilter + kolonne-layout i resultatskuffen, og gjorde feltet scrollbart slik at mange treff fortsatt er lesbare.
- Sørget for at korpuset (og Places/kart) rehydreres når man legger til bøker via søk, slik at man kan bygge et helt nytt korpus fra “intelligent søk” før man eventuelt bruker Corpus Modify til finpuss.

### November 21, 2025
**Progress**:
- Polished the top toolbar: Map vs. Heatmap is now a calm two-button group (no extra label), and the visualization chip lives inside the launcher stack for symmetry.
- Grouped the launcher chips in vertical pairs (Corpus View/Modify, Places List/Coll, Place Books/Similarity) so orientation and navigation are instantly clear.
- Brought the closers in every card over to the left and renamed the “Add books” actions to “Update”, matching the new similarity workflow where users repeatedly refresh corpora.
- Made similarity results write back to the corpus plus `selected_tokens`, enabling instant inspection of only the suggested places, with a plan to add overlap/highlight toggles next.
- Rebuilt the chip launcher into pill parents with hover/tap flyouts, and added mac-style window controls (close/minimize) to every floating dialog with per-card window state.
- Prevented size callbacks from reviving closed cards, and ensured minimizing doesn’t break drag handles by hiding body content without removing the header.
- Added utility CSS so window controls remain legible on colored headers (e.g., Place Info’s red title bar).

### November 19, 2025
**Progress**:
- Finished debugging the new W±/H± sizing workflow so every dialog honors its private entry in `dialog-size-store`.
- Let the Places card keep its table inside the frame by making the tabs flex vertically with `overflow` containment on the card body.
- Stopped the Corpus Builder from forcing 350×500 when opened via Corpus Controls; it now reuses the previously stored size.
- Restored the classic “hidden on load” behavior so floating cards stay out of sight until their buttons are clicked.
- Tuned default presets (one W+ for Corpus Controls, two H+ for Corpus Builder and Places) so common laptop sizes look right on first open.

**Notes**:
- Once a few sessions settle we can revisit the default presets per card; the store already supports swapping them without code changes.
- Keep an eye out for other callbacks that might run on first render without `prevent_initial_call` and flip visibility unexpectedly.
- Established the pattern for similarity-driven corpus building, so follow-up sessions can layer on highlighting and overlap views without rewriting state handling.

### November 13, 2025
**Progress**:
- Replaced the remaining reference to the global `CorpusState` with session-local data from `current-dhlabids-store`, preventing corpus changes from bleeding across users on Cloud Run.
- Verified the Dash app runs via `pdm run env PYTHONPATH=src python src/dash_imagination/app.py`, ensuring Plotly 6 trace classes (`go.Scattermap`, `go.Densitymap`) are available in local debugging sessions.
- Let the heatmap render from the full corpus stored in `all-places-store` while keeping scatter markers sampled, so users get dense overviews without overwhelming mobile devices.
- Moved component imports (corpus/map/place dialogs) below the Dash app instantiation to guarantee callback registration on Cloud Run and other WSGI hosts.
- Introduced Places-pane tabs (Frekvens, Sampling, Kollokasjoner) so users can inspect og nedlaste underlister før de aktiverer kartvisningen. Hver fane respekterer `max_places` og har egen “Vis steder”-knapp og CSV-eksport.
- Collokasjonshighlight er erstattet av en kollokasjonsfane i Places og et register over valgte tokens (`selected_tokens`), så heatmap/kart forholder seg til samme domino som andre faner.
- Nedlastingsknapper ble lagt til for alle tre Places-lister (token, moderne navn, frekvens, bokfrekvens, lat/lon).
- Erstattet preset-dropdownene i alle flytende kort med egne bredde/høyde-knapper (W±, H±). Størrelsene lagres per kort i `dialog-size-store`, og layoutene er gjort om til `flex` med én scrollbar per kort slik at knappene aldri havner utenfor flaten.

### November 12, 2025
**Progress**:
- Restored local environment alignment by running the Dash app through the PDM-managed virtualenv (`pdm run env PYTHONPATH=src python -m dash_imagination.app`) so Plotly 6 is available and `go.Scattermap` renders correctly.
- Fixed corpus resampling default by setting `default_filters['max_places']` to 500, preventing the resample callback from returning empty datasets after filter resets or uploads.
- Added `todo.md` to track follow-up tasks (React lifecycle warning, safeguard filter defaults, helper launch script).
- Added union/intersection/difference controls for corpus uploads and builder output; state updates now respect the selected set operation and automatically recompute place tokens to match.
- Introduced collocation explorer in the corpus builder (via `dh.Collocations`), mapping dhlabids to URNs and intersecting collocates with place names to surface relevant locations for keywords like “krig”.
- Added highlight workflow to paint collocation-matched places on the map (button-triggered overlay).

**Notes**:
- Heatmap and map views now stay in sync after uploads and resampling; baseline limit of 500 keeps the UI responsive while allowing manual adjustment.
- Consider enhancing the heatmap to optionally use all places from `all-places-store` to better visualize large corpora without overwhelming the scatter view.
 - Future: introduce stop-place list upload to filter spurious tokens.

### June 10, 2024
**Progress**:
- Collaborative, iterative refinement of UI/UX and backend for the ImagiNation app, focusing on corpus builder, marker popups, clustering, and state management.
- Improved drag behavior and visual polish for the corpus builder card.
- Optimized marker popup generation for map responsiveness.
- Added spinners and feedback for book/content addition actions.
- Made corpus content search more intuitive for empty corpora.
- Refactored SQLite access for thread safety and robustness.
- Enhanced error handling and callback safety.
- Refined reset/clear filter button logic for user safety.
- Iteratively improved alignment, compactness, and visual consistency of UI controls and tables.
- Reverted resizable card experiments after user feedback.
- Managed branches and commits to keep main branch stable and up to date.

**Key Changes**:
1. Refactored card centering and drag logic for smoother UX.
2. Marker popups are now generated on demand, improving map load times.
3. Spinners and feedback messages added for all major corpus actions.
4. Content tab now defaults to searching all books if corpus is empty.
5. All database access now uses context managers to avoid threading errors.
6. Reset button is now icon-only, top-aligned, and requires double-click confirmation.
7. UI controls and tables are more compact, visually aligned, and free of unnecessary outlines.
8. All major quirks and usability issues addressed through incremental improvements.

**State Management Note**:
- With the current design, frequent corpus resets and uploads may lead to confusing or inconsistent state, especially after deployment. This is a known area for future improvement. Next session will focus on reviewing and improving state management to ensure robust, predictable behavior for users.

**Next Steps**:
- Monitor user feedback after deployment, especially around corpus resets and uploads.
- Review and improve state management logic to prevent confusion and ensure consistency.
- Continue refining UI/UX based on real-world usage.

### May 20, 2024
**Progress**:
- Implemented custom download functionality for map visualization
- Added support for multiple formats and resolutions
- Created server-side download endpoint

**Key Changes**:
1. Added new download UI components:
   - Format selection (PNG, PDF, SVG)
   - Resolution options (Standard, High, Publication)
   - Download button with status feedback
2. Implemented server-side download endpoint:
   - Added `/download-map` route for handling downloads
   - Support for multiple image formats
   - Configurable resolution settings
3. Created client-side download trigger:
   - JavaScript-based download initiation
   - Status feedback for users
   - Error handling for failed downloads

**Technical Challenges**:
- Download trigger not working as expected
- Need to debug client-side JavaScript execution
- Server-side image generation needs testing

**Next Steps**:
- Debug and fix download trigger functionality
- Test image generation with different formats
- Add proper error handling and user feedback
- Consider alternative download approaches if needed

### May 20, 2024 (2)
**Progress**:
- Implemented robust Excel download for current corpus (with URL column for NB.no)
- Fixed callback registration order bug (all callbacks now registered before app.run)
- Added XlsxWriter to requirements for Excel export
- Confirmed full download/upload/reset round-trip workflow for user testing

**Key Changes**:
1. Download button now exports corpus as Excel (.xlsx) with columns: dhlabid, title, author, year, category, url
2. Upload and reset work seamlessly, allowing users to save, restore, and iterate on corpora
3. All callback registration issues resolved (no more silent failures)
4. Ready for real user testing and feedback

**Next Steps**:
- Deploy to production
- Gather user feedback on corpus management workflow
- Adjust download/upload features as needed based on real usage

### May 17, 2024 (2)
**Progress**:
- Fixed syntax error in map update function
- Improved error handling in map visualization

**Key Changes**:
1. Restructured try-except block in `update_map` function for better error handling
2. Fixed indentation issues in the map update logic
3. Ensured proper error catching and reporting for map visualization

**Next Steps**:
- Monitor error handling in production
- Consider adding more detailed error logging
- Plan for additional error recovery mechanisms

### May 17, 2024
**Progress**:
- Fixed initial map data load and grid view issues
- Improved app initialization behavior

**Key Changes**:
1. Modified `default_filters` initialization:
   - Set empty initial values for all filter parameters
   - Ensured consistent empty state across components
2. Added `prevent_initial_call=True` to all relevant callbacks:
   - Map update callback
   - Filtered data callback
   - Corpus controls callbacks
   - Visualization controls callbacks
3. Improved app startup behavior:
   - Map now starts completely empty
   - No data is loaded until explicit user interaction
   - Grid view is bypassed on startup

**Next Steps**:
- Monitor performance with the new initialization approach
- Consider adding loading states for better UX
- Plan for additional user interaction improvements

### May 15, 2024
**Progress**:
- Implemented global corpus management system
- Fixed inconsistencies in place details display
- Improved corpus sampling logic

**Key Changes**:
1. Added global `current_dhlabids` list for corpus management
2. Modified `get_places_for_map` and `get_place_details` to use global corpus
3. Updated corpus upload and reset functionality
4. Improved logging for better debugging

**Next Steps**:
- Monitor performance with large corpora
- Consider adding corpus modification features
- Plan for additional corpus analysis tools

## Testing Notes
- Verified consistency between book counts and displayed books
- Tested with both uploaded and sampled corpora
- Confirmed proper handling of large corpora

## User Feedback
*To be added after user testing*

## Performance Monitoring
*To be added as metrics are collected*

## Notes
- Update this logbook regularly with significant changes
- Include both technical and user-facing changes
- Document any challenges and their solutions

## 2024-03-19: Improved Cluster Visualization
- Added polygon visualization for clusters when clicked
- Implemented convex hull for clusters with 3+ points
- Added oval visualization for 2-point clusters
- Fixed polygon edge handling for clusters spanning map boundaries
- Improved polygon completeness by adding edge points and ensuring closure
- Adjusted cluster visualization to better represent spatial distribution of places

## 2024-05-16: Environment Fixes and Pre-Deployment

- Removed all references to `dash_virtualized` from the codebase and requirements.
- Ensured that the app runs locally by either:
  - Running from the `src/` directory with `

## UI Component Updates (2024-03-21)

### Component Migration to dbc.Card
- Converted dialog components to use `dbc.Card` for consistent styling and better integration with Bootstrap
- Implemented proper card headers with icons and close buttons
- Added scrollable card bodies with proper height calculations

### Color Scheme Implementation
- Added distinct color coding for different card types:
  - Place Details card: `bg-danger-subtle` (red tint)
  - Place Names card: `bg-warning-subtle` (yellow tint)
  - Place Similarity dialog: `bg-info-subtle` (blue tint)
- Colors help users distinguish between different functional areas of the interface

### Resize Functionality Attempt
- Attempted to implement modern resize functionality using native JavaScript
- Added resize handles for all directions (n, s, e, w, ne, nw, se, sw)
- Implemented size constraints (300-800px width, 400-800px height)
- Note: Resize functionality is currently not working as expected and needs further investigation

### Next Steps
- Investigate and fix resize functionality
- Consider alternative approaches for card resizing
- Review Bootstrap's built-in resizing capabilities
- Test cross-browser compatibility

## 2024-03-19: Migrating Corpus Controls

- Created new corpus builder card component to replace old corpus controls
- Migrated key functionality:
  * Max places slider (100-2000 places)
  * Year range slider (1814-1905)
  * Category selection
  * Build corpus button
  * Resampling functionality
- Progress:
  * Most UI controls successfully moved to new card
  * Resampling button and container added
  * Callbacks updated to use new component IDs
  * Some issues with place registration to be resolved
- Next steps:
  * PRIORITY: Debug place plotting functionality
    - Trace data flow from corpus builder to map
    - Check if places are being properly sampled from database
    - Verify current-filters and filtered-data store updates
    - Ensure map callback receives and processes place data
    - Add logging to track place data at each step
  * Debug place registration in resampling
  * Complete full testing of migrated controls
  * Remove old corpus controls once migration is complete
  * Make corpus builder card draggable (reuse existing card dragging code)

### June 8, 2024
**Progress**:
- Made the corpus builder card draggable, matching the behavior of other cards (e.g., corpus controls, visualization controls).
- Used the existing drag-and-drop logic in `assets/drag.js` for consistency.

**Key Changes**:
1. Updated `drag.js` to add drag-and-drop support for `#corpus-builder-card` using its header as the drag handle.
2. Set the cursor style for the builder card header to `grab` for visual feedback.

**Next Steps**:
- Monitor user feedback on the new draggable builder card.
- Consider adding resize functionality in the future if needed.

**Environment Note:**
- The `kaleido` package (required for Plotly image export) cannot be reliably installed via PDM due to its binary-only distribution.
- **Workaround:** Remove `kaleido` from `pyproject.toml` and `pdm.lock`. After running `pdm install`, manually install it in the virtual environment with:
  
  ```
  .venv/bin/pip install kaleido
  ```
- This ensures image export features work as expected.
