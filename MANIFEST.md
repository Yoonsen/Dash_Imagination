# ImagiNation App Development Manifest

## Current State
The app is a Google Maps-inspired interface with floating, interactive elements designed to work on both desktop and mobile. The main components are:
- Map as the central element
- Floating popup menus activated by clicking
- Information displayed in floating windows that can be closed
- Current layout includes:
  - Sidebar toggle (top left)
  - Category selection (top left)
  - Places button (top left)
  - View toggle (Map/Heatmap) and clustering options (top right)
  - Info button (bottom left)

## Data Structure and Information Flow

### Database Structure
- SQLite database with three main tables:
  - Books table (22,000 entries)
  - Places table (90,000 entries)
  - Books-Places relationship table

### Conceptual Model
- Treat the dataset as a document-term matrix (DTM) where **books are columns** and **places are rows**.
- The primary flow is *books → places*: users assemble a corpus of books, and every downstream view derives from the set of places tied to that corpus.
- Corpus membership is session-scoped and stored in `current-dhlabids-store` (a per-session `dcc.Store`) so each browser session works with its own book selection.
- Places have multiple “projections”:
  1. Places tied to the current corpus (baseline view).
  2. Places surfaced via collocation queries (places near selected keywords).
  3. Places prepared for visualization (frequency-weighted, sampled, or highlighted subsets).
- Dialog logic needs to respect these projections so that place lists, highlights, and map overlays stay synchronized without leaking state across users.

### Core Functionality
1. Corpus Building and Visualization
   - Users can build corpus using metadata filters (author, title, year, category) and optional content queries (wordforms, min counts).
   - Corpus operations support add/union, intersect, and subtract so uploaded corpora or builder results can be combined freely.
   - Places from selected corpus are plotted on map
   - External corpus can be loaded into the app
   - Corpus data lives in `dcc.Store`, ensuring session isolation and predictable Undo/Redo behavior.

2. Interactive Features
   - Click on place to see related books
   - Click on book to access National Library online
   - View all places within selected corpus, sampled subsets, or collocation results
   - Highlight workflow lets collocation hits light up relevant places on the map (current implementation triggers highlight overlay; future revisions will unify this with the place dialog presets).

3. Advanced Analysis (Future)
   - Concordance functionality for place-disease relationships
   - Corpus building based on specific themes (e.g., diseases like cholera, typhus)
   - Collocation and vicinity searches (current collocation pipeline already identifies places near keywords; future work consolidates its UI with the main places dialog presets)

### System Integration
The app connects three main components:
1. Main Application
   - Handles corpus management
   - Displays map and place information
   - Manages user interactions

2. National Library Online
   - Provides book viewing functionality
   - Uses URNs for direct linking

3. DHLab Integration
   - Provides advanced text analysis tools
   - Concordance functionality
   - Collocation analysis
   - Vicinity searches

All components are connected through consistent identifiers (URNs) that work across servers.

## Mobile Optimization Plans

### 1. Responsive Button Sizing
- [ ] Increase button sizes for better touch targets on mobile
- [ ] Adjust spacing between buttons for mobile screens
- [ ] Implement responsive padding and margins

### 2. Modal Improvements
- [ ] Make modals full-screen on mobile
- [ ] Add swipe-to-dismiss functionality
- [ ] Ensure modal content is scrollable
- [ ] Optimize modal content layout for mobile

### 3. Floating Elements
- [ ] Adjust positioning for different screen sizes
- [ ] Consider bottom sheet for mobile instead of side panels
- [ ] Prevent element overlap on small screens
- [ ] Implement responsive positioning

### 4. Map Controls
- [ ] Make map controls more touch-friendly
- [ ] Ensure zoom controls are easily accessible on mobile
- [ ] Optimize touch interactions for map markers

## Current Focus
- [ ] Ensure popups work correctly on all devices
- [ ] Align top layer elements properly on mobile
- [ ] Test and fix any mobile-specific issues

## Planned Global Search Surface
- Reserve the global search field (future top-bar component) for **single-entity lookups** spanning three object types: places, people, and books.
- Search behaves like a Google Maps omnibox: always global, returning discrete hits rather than corpus-sized lists.
- Example flows:
  - Typing a place returns matching place entities plus the books where that place is mentioned; selecting it zooms the map and highlights the relevant corpus slice.
  - Typing an author (e.g., “Amalie Skram”) returns her books, optional NB.no imagery from the relevant era, and an affordance to drop selected books into the active corpus.
  - Typing a book title returns its metadata, associated places, and previews of illustrations pulled from the Qdrant-based similarity index.
- Image traversal: leverage the existing Qdrant collection of illustrations/photos so users can start from a single image (e.g., an encyclopedia plate) and discover visually similar images across other books, optionally adding those source books into the corpus as they go.
- Staging strategy:
  1. Implement minimum viable global search returning entity cards with “Add to corpus” / “Show on map” actions.
  2. Enrich responses with NB.no imagery and timeline context.
  3. Integrate the image-similarity workflow so book discovery can start from visuals, not just text metadata.

## Future Considerations
- Performance optimization for mobile devices
- Offline functionality
- Progressive Web App (PWA) features
- Accessibility improvements
- User feedback and analytics

## Notes
- The app evolved from a Streamlit application
- Inspired by Google Maps interface
- Uses Dash and Bootstrap for UI components
- Database-driven with SQLite backend 