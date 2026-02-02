# LLM Build Spec (Frontend/Backend rewrite)

Målet er å kunne regenerere appen (frontend + backend) fra dette dokumentet uten å lese eksisterende kode. ID-er og dataformer bevares der det gir kompatibilitet, men implementasjon er valgfri (foreslått: React + FastAPI).

## 1. Domene og data
- Identifikatorer:
  - `dhlabid` (bok-ID, int)
  - `token` (steds-ID, tekst)
  - `urn` (NB-URN for bok)
- Kjerneobjekter:
  - **Book**: {dhlabid, title, author, year, urn}
  - **Place**: {token, name (modern), latitude, longitude, frequency, book_count}
  - **Concordance row**: {left, keyword, right, urn, concordance?, metadata}
  - **Collocation row**: {word, count}
- Standardbegrensninger:
  - Concordance: limit 500 rader; vis forhåndsvisning 50.
  - Collocations: default før/etter = 10 (tidl. 50).

## 2. API-kontrakter (forslag)
- `POST /corpus/op` {dhlabids: [int], op: union|intersection|difference} -> {dhlabids: [int]}
- `GET /corpus` -> {dhlabids: [int], size: int}
- `GET /places` params: {dhlabids, year_range?, category?, author?, title?, max_places?} -> orient='split' JSON (token, name, lat, lon, frequency, book_count)
- `POST /concordance` {urns|dhlabids|token, query, before?, after?, limit?} -> {size, frame: [rows]}
- `POST /collocations` {urns|dhlabids|tokens, before?, after?, samplesize?} -> {frame: [rows]}
- `GET /images/place|author` -> IIIF payload (valgfritt)
- Auth: ikke spesifisert (kan legges til senere).

## 3. Global state (frontend)
- `current-dhlabids` (liste av int) – aktivt korpus.
- `current-filters` (kategori/forfatter/tittel/år/max_places/selected_tokens/corpus_source/last_operation).
- Places:
  - `places-frequency-data` (orient='split')
  - `places-collocation-data` (orient='split')
  - `all-places-store` (fullt dataset for global skalering)
- Collocations:
  - `collocation-place-tokens` (liste token)
  - `collocation-place-counts` (map token -> count)
- Concordance:
  - `concordance-data` (full DF for nedlasting)
- Images:
  - `place-images-store`, `author-images-store`, `image-gallery-store`
- UI state:
  - window pos/size (per kort)
  - minimize/close flags
  - map view type (map/heat)
  - global loading overlay (vises ved korpus-oppdatering; skjules når kartet er klart)

## 4. Vinduer / UI-kontrakter
Bruk `Window(id, title, draggable, resizable, portal?)` i React med `react-rnd` eller tilsvarende. Modal bruker portal.

- **Place Summary** (`place-summary-container`)
  - Vises ved kartklikk/omnibox-valg.
  - Innhold: navn/token, badges (mentions, books), bokliste (tittel, forfatter, år, urn-link), bilder.
  - Knapper: `open-concordance` (åpner modal), close/minimize.
  - Data: `get_place_details(token, current_dhlabids)`.

- **Concordance Modal** (`concordance-modal`, portal)
  - Inputs: `concordance-query` (text), `concordance-window` (number, default 25).
  - Buttons: `run-concordance`, `download-concordance`.
  - State: `concordance-data-store` (full DF).
  - Visning: spinner ved fetch; tabel-lignende liste med link til bok (`urn`), konkordans-tekst; vis “Viser topp 50 av {size}”.
  - Nedlasting: CSV med metadata-kolonne (title/year/author/mentions).

- **Place-specific Concordance** (`place-concordance` knapper)
  - Ligner modal-visningen; bruker token som query; before/after 25/25; samme metadata og nedlasting.

- **Places-list** (`place-names-container`)
  - Modes: frequency, sampling, collocations, similarity.
  - Kontroller: søk, max_places slider, tabs; download; highlight toggle.
  - Data: `filtered-data` / `places-frequency-data` / `places-collocation-data`.

- **Corpus Builder** (`corpus-builder-card`)
  - Inputs: kategori/forfatter/tittel, år-range, max_places, content wordforms + minfreq.
  - Operasjoner: union/intersection/diff; build/oppdater-knapp.
  - Statusmelding ved bygging; spinner.
  - Oppdaterer `current-dhlabids` + `current-filters`.

- **Corpus Controls** (`corpus-controls-container`)
  - Viser korpusstørrelse, nedlasting, tøm/reset.

- **Collocation Card** (`collocation-card`)
  - Inputs: keywords, before/after (default 10), run.
  - Viser matching places (token=AND-match på place token), counts; highlight toggle; apply til places view.

- **Place Similarity Dialog** (`place-similarity-dialog`)
  - Viser liknende steder, kan legge til steder/bøker i korpus (via tokens -> dhlabids).

- **Omnibox (global search)** (`global-place-search`)
  - Søker i steder/bøker/forfattere.
  - Resultater: lister med “legg til i korpus” (bok/forfatter), “vis sted”.
  - Klikk på “legg til” oppdaterer korpus og viser global overlay; overlay skjules når kartet oppdateres.

- **Map/Heatmap controls** (top-right)
  - Toggle map/heat.
  - View state lagres (zoom etc.).

- **Global Loading Overlay** (`loading-overlay`)
  - Tekst: “Oppdaterer korpus og steder …”
  - Vises ved: build-corpus-knapp, omnibox add (bok/forfatter) → corpus change.
  - Skjules når kart (`main-map`) oppdateres.
  - Vis ikke ved init når korpus er tomt.

- **Image Gallery Modal** (`image-gallery-modal`)
  - Klikk på thumbnails åpner galleri; data fra `place-images-store` / `author-images-store`.

## 5. Interaksjonsflyt (hovedscenarier)
- Kartklikk/omnibox → fetch place details → åpne place summary → (valgfritt) åpne konkordans-modal → run/download.
- Omnibox “legg til bok/forfatter” → corpus oppdateres → overlay on → map/places oppdateres → overlay off.
- Corpus builder “Update” → corpus oppdateres → overlay on → map/places oppdateres → overlay off.
- Collocation run → collocation tokens/counts → places-collocation-data → places list i coll-modus (og highlight toggle).
- Download-knapper henter CSV fra relevant dataset (places, concordance).

## 6. Stil / tokens (anbefaling)
- Portaler for modaler; z-index høyt uten manuell stacking.
- Bruk design tokens for spacing/radius/farger; card shadow ~ “0 2px 8px rgba(0,0,0,0.1)”.
- Spinner: standard “default” stil.

## 7. Tekst / UX
- Overlay-tekst: “Oppdaterer korpus og steder …”
- Concordance-summary: “Viser topp {shown} av {total} treff”.
- Collocation default vindu: 10/10.
- Content filter minfreq: input med default 1.

## 8. Migrasjonsnotater
- Behold ID-navn i API og frontend der det er enkelt (token/urn/dhlabid, orient='split' for tabeller).
- Sett opp Docker for backend (FastAPI + SQLite seed). Frontend kan bygges separat (Next/React).
 - Autentisering kan legges på senere; starten kan være åpen.

Dette dokumentet skal være nok til at en LLM (eller utvikler) kan gjenskape funksjonaliteten uten å lese eksisterende kode.
