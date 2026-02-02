## Notater: overgang til JS/React

### Vinduer/modaler (drag/resize/z-index)
- Bruk ferdige komponenter i React:
  - `react-rnd` for drag + resize i ett (bounds, min/max size, snap).
  - Alternativ: `react-draggable` + `react-resizable`.
  - Modaler/drawers via UI-bibliotek (MUI/Chakra) med portal → z-index-problemer forsvinner.
- Lag en liten `WindowShell`-komponent som:
  - Tar props for `id`, `initialPosition/size`, `bounds`, `minSize`.
  - Lagrer posisjon/størrelse i global store (Zustand/Recoil) eller localStorage.
  - Eksporterer `onFocus` for å håndtere z-index stacking uten manuell CSS.

### State og asynkron flyt
- Bruk React Query/SWR for kall til API (korpus/places/konkordans/kollokasjon):
  - Gir `isLoading/isFetching/error/data` automatisk → enhetlig spinner/feilmelding.
  - “Global overlay” kan kobles til “any inflight” queries eller spesifikke nøkler.
- Del state: global store for korpus (liste av dhlabid), filter, window-states; Query-cache for serverdata.

### API-kontrakter (for FastAPI/backend)
- Hold JSON-shape nær dagens Dash (orient='split' der det hjelper) for enkel migrering:
  - `GET /corpus` (liste dhlabid + metadata)
  - `POST /corpus/op` {dhlabids, op: union|intersection|difference}
  - `GET /places` med filtrering (år/kategori/søk/max_places)
  - `POST /concordance` {urns|dhlabids|token, query, before, after, limit}
  - `POST /collocations` {urns|dhlabids|tokens, before, after, samplesize}
- Vurder auth/ACL tidlig hvis data flyttes til ny backend.

### Migreringsstrategi
- Start med API-laget (FastAPI) bak Docker; seed SQLite ved build, differensier dev/prod.
- Bygg ny React-klient som konsumerer endepunkter parallelt med eksisterende Dash; bytt surface for surface.
- Behold identifikatorer (token/urn/dhlabid) konsekvent mellom lagene for enkel porting av søk/koll/konk.
