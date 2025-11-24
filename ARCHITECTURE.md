# ImagiNation – Architecture Overview

This document describes how the ImagiNation app implements the intent expressed in the **ImagiNation App Development Manifest**.  
Where the manifest states *what* the app should be and do, this document describes *how* it is put together.

---

## 1. High-Level Architecture

ImagiNation is a Dash application backed by a SQLite database and external services at the National Library (NB) and DHLab.

Roughly, the system consists of:

- **Frontend (Dash)**
  - Layout and UI components (map, floating panels, buttons, dialogs).
  - Client-side state stored in `dcc.Store` components.
  - Callbacks for user interaction and view updates.
- **Backend / Data Layer**
  - SQLite database with three core tables: `books`, `places`, `book_places`.
  - Query helpers for corpus filtering, place retrieval, and collocation workflows.
- **External Integrations**
  - NB.no for book viewing (via URNs).
  - DHLab services for text analysis (concordances, collocations, vicinity).
  - Qdrant for image similarity and visual discovery (planned integration in the app UI).

The guiding abstraction is: **books as columns, places as rows** (DTM), with views driven by a session-specific corpus.

---

## 2. Frontend Structure (Dash)

> File names here are indicative; adjust to match your repo.

### 2.1 Layout and UI

- `app.py`
  - Initializes the Dash app and server.
  - Registers the main layout and callbacks.

- `layout.py`
  - Defines the top-level layout:
    - **Map container** (central element).
    - **Floating UI elements**:
      - Sidebar toggle (top left).
      - Chip launcher on the left edge with **pill parents** (“Corpus”, “Places”, “Viz”) that fan out into task-specific chips:
        - Corpus: View / Modify
        - Places: Liste / Coll / Sim
        - Visualization: Viz Ctrl (own pill)
        - Pills are **hover- or click-expandable** on desktop, tap-to-toggle on mobile.
      - Map/Heatmap toggle and visualization button (top right).
      - Info button (bottom left).
    - **Floating dialogs** (all draggable/resizable) with mac-style window controls:
      - Corpus view & builder.
      - Places list (tabs for frequency / sampling / collocations) + Place info dialog.
      - Collocation card.
      - Place similarity dialog.
      - Visualization controls.

- `components/`
  - Reusable Dash components for:
    - Map wrapper (e.g. `MapView`).
    - Floating button group.
    - Places dialog.
    - Corpus builder panel.
    - (Future) global search bar.

### 2.2 Client-Side State (`dcc.Store`)

Session-specific state is kept in `dcc.Store` components to avoid leaking context between users:

- `current-dhlabids-store`
  - The active **corpus**: list/set of NB/DHLab IDs (books).
  - All downstream projections (places, collocations) use this as their scope.

- `current-places-store`
  - Places associated with the current corpus, possibly in multiple projections:
    - Baseline corpus places.
    - Collocation/vicinity subsets.
    - Sampled or pre-filtered views for visualization.

- `highlight-store`
  - Acts as a layer of **overlays**:
    - Highlights from collocation queries (places near keywords).
    - Temporary “focus” subsets from user selections.

These stores are read and written by Dash callbacks, ensuring consistent state across panels, dialogs, and map overlays.

### 2.3 Floating Dialog Shell
- Shared header via `card_title_bar` renders macOS-like buttons:
  - **Red ×** closes the card (tied to existing toggle callbacks).
  - **Yellow –** minimizes to title-only, preserving position/size in `dialog-size-store`.
- Each dialog stores state in `*-window-state` so minimize/restore survives size changes.
- Dragging is handled client-side (`assets/drag.js`) with a single interaction pattern across cards.

### 2.4 Core Callbacks

Key callback groups:

1. **Corpus management**
   - Build corpus from metadata filters (author, title, year, category).
   - Add/union, intersect, and subtract operations.
   - Load external corpus (uploaded file / pre-defined corpus).
   - Persist results into `current-dhlabids-store`.

2. **Place projection and visualization**
   - Given `current-dhlabids-store`, query DB for places and write into `current-places-store`.
   - Render markers on the map based on current projection (baseline, collocation, sampled).
   - Toggle map vs. heatmap view and clustering.

3. **Interaction: map ↔ lists ↔ NB**
   - Click on a **place marker** → open dialog listing related books.
   - Click on a **book** in a dialog → open corresponding NB.no page via URN.
   - Use filters in dialogs to switch between:
     - All places in corpus.
     - Collocation/vicinity result subsets.
     - Sampled or high-frequency places.

4. **Collocation / vicinity workflows**
   - Trigger DHLab collocation pipeline for given keywords and corpus.
   - Map collocation results back to places (through `book_places` and `places` tables).
   - Store result in `highlight-store` and/or `current-places-store` presets.
   - Update map and dialogs to reflect highlighted places.

5. **Mobile optimization**
   - Responsive sizing and positioning of floating elements.
   - Full-screen modals on small screens.
   - Prevention of overlapping UI (modals vs. map vs. buttons).

---

## 3. Data Layer (SQLite)

The data layer is backed by a SQLite database.

### 3.1 Core Tables

- `books`
  - ~22,000 entries.
  - Core fields (example): `id`, `dhlabid`, `urn`, `title`, `author`, `year`, `category`, etc.

- `places`
  - ~90,000 entries.
  - Core fields: `id`, `place_id`, `name`, `latitude`, `longitude`, optional `type` / administrative info.

- `book_places`
  - Relationship table between books and places.
  - Core fields: `book_id`, `place_id`, `count` (frequency / mentions), optional additional metadata (page ranges, contexts).

Conceptually, this realizes:

- Rows: **places**
- Columns: **books**
- Cell values: frequency (or presence) → a sparse document-term matrix (DTM).

### 3.2 Query Layer

A thin Python layer encapsulates DB access, with functions like:

- `get_books(filters)`  
  Filters by metadata (author, year, category) and optional search constraints (wordforms, min counts).

- `get_places_for_books(book_ids)`  
  Returns places and aggregated frequencies for a given corpus.

- `get_books_for_place(place_id, corpus_ids=None)`  
  Returns books mentioning a given place, optionally restricted to current corpus.

- `sample_places(place_set, strategy)`  
  For controlling visualization density (e.g., top-N by frequency, random sample, etc.).

Collocation-specific queries are typically delegated to DHLab endpoints, but DB tables provide the bridge back to coordinates.

---

## 4. External Integrations

### 4.1 NB.no Book Viewer

- Each book has a **URN** that allows deep linking into NB’s online viewer.
- The frontend constructs these URLs and opens them in a new tab/window when a user clicks a book.

### 4.2 DHLab Services

DHLab provides the heavy lifting for text analysis:

- **Concordances**
  - Given a corpus and search term(s), return concordance lines for further inspection.

- **Collocation**
  - Given a keyword and corpus, compute collocates.
  - ImagiNation uses these results to:
    - identify books where keyword and place co-occur.
    - derive place projections for highlight overlays.

- **Vicinity searches**
  - Identify terms appearing in the textual vicinity of places or diseases.
  - Used for building place–disease views (e.g., cholera, typhus, etc.).

All services are connected via stable identifiers (e.g., URNs or DHLab internal IDs) so results can be re-joined with local DB tables.

### 4.3 Qdrant (Image Similarity, Planned UI Integration)

- A Qdrant collection stores vector embeddings for illustrations/photos.
- Each vector is linked to:
  - an image identifier (IIIF or internal ID),
  - a URN/book identifier.
- Planned flows:
  - Start from a single image → retrieve visually similar images across the collection.
  - From retrieved images → add their source books into the active corpus.
  - Expose this as part of the **global search and discovery** layer.

---

## 5. Global Search Surface

Omniboxen som står i topplinjen i dag leverer den “Google Maps”-opplevelsen vi planla:

### 5.1 Entities and Behavior

Søk skjer i tre parallelle “univers” – vi splitter inputten i ord og matcher ordene uansett rekkefølge/tegnsett:

- **Steder**  
  Resultatkort: token + moderne navn + antall bøker/forekomster.  
  Handling: “Vis på kartet” zoomer og åpner Place Info med samme logikk som marker-klikk.

- **Bøker**  
  Resultatkort: tittel, år, forfatter, med NB.no-lenke.  
  Handling: “Åpne NB” + “Legg til korpus” (egnede dhlabids går rett i `current-dhlabids-store`, kartet tegnes på nytt).

- **Forfattere**  
  Resultatkort: navn + antall bøker.  
  Handling: “Legg bøker til korpus” (bulk-add). Perfekt for å starte et nytt korpus før man hopper til Corpus Modify.

### 5.2 UI og state

- Pillefilter over resultatene lar brukeren togg­le kategorier uten å skrive søket om igjen (vi lagrer valget i `global-search-filter-store`).  
- Kortene vises i et responsivt grid (scrollbart) med samme card/pill-estetikk som resten av appen.  
- Alle søkehandlinger respekterer eksisterende stores (`current-dhlabids-store`, `place-summary`, `selected-place`), så søk → korpus → kart er en én-klikk-flyt.

### 5.3 Videre arbeid

1. **Enrichment**  
   - Legg til NB.no-bilder/tidslinjer i kortene, vis representative steder direkte i kortet.

2. **Image-driven discovery**  
   - Når Qdrant-integrasjonen lander, lar vi brukeren starte søket fra ett bilde (visuelt lignende bøker → Legg til korpus).

---

## 6. Mobile and PWA Considerations

### 6.1 Mobile Layout

- Larger buttons and increased spacing for touch.
- Full-screen modals on small screens; scrollable content.
- Reconsider side panels as bottom sheets where appropriate.
- Ensure map controls (zoom, layer toggles) remain accessible.

### 6.2 Performance and PWA

- Reduce payload sizes for mobile (sampling, lazy loading).
- Use client-side caching where possible.
- Longer-term: PWA support
  - Service worker for basic offline capabilities.
  - Cached tiles, basic corpus snapshot, and last-viewed state.

---

## 7. Evolution Notes

- The app originated as a **Streamlit** prototype and was later rewritten in Dash to gain:
  - finer control over layout and state,
  - better integration with complex callbacks and client-side stores.
- The current architecture is designed to:
  - keep the **corpus** as the primary “knob”,
  - treat all views as different **projections** of places and books,
  - integrate analysis (DHLab) and discovery (Qdrant/NB.no) through stable identifiers (URNs).

The manifest captures where the app is going; this architecture describes the current implementation and the path for incremental enhancements.

