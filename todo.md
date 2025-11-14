## TODO

- [ ] Investigate React warning about `componentWillReceiveProps` and update offending component (likely third-party Dash component) to supported lifecycle methods.
- [ ] Audit `current-filters` defaults and ensure UI controls (slider, stores) never reset `max_places` to zero.
- [ ] Create helper script/alias to launch app via `pdm run env PYTHONPATH=src python -m dash_imagination.app` to avoid environment mismatch.
- [x] Replace module-level `CorpusState` with per-session `dcc.Store`-backed state to prevent corpus/place data leaking across users in Cloud Run.
- [x] Prototype resizable pane layout as an alternative to draggable cards.
- [ ] Offer alternate resampling modes so users can override the current sampling strategy.
- [ ] Make the default place list sort by highest frequency and only sample entries below the current cap.
- [ ] Add a global search field that covers places, people and books.
- [ ] Extend the place card with frequency/sample toggle buttons, download/upload hooks and tooling for filtering spurious places (mirroring corpus +/− logic).
- [ ] Provide CSV download of the place list with columns: historical name, modern name, frequency, latitude, longitude.
- [ ] Surface representative images from books (NB.no) alongside place data.
- [ ] Highlight top-most frequent places directly in the UI.
- [ ] Add min/max controls for limiting the place list or frequency range.
- [x] Ensure the heatmap uses the full corpus data rather than the sampled subset.
- [ ] Integrate collocation results into the place card experience.
- [ ] Refresh the various dialog layouts for consistency and clarity.
- [ ] Review place names against their geolocations and clean up mismatches.
- [ ] Extract candidate place names from the corpus (token analysis) for manual review.
- [ ] Investigate CLS / needs-theory presentation for toponyms and geomorphemes on the map.

