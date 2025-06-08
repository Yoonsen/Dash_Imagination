# ImagiNation Development Logbook

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