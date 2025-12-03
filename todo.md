## TODO

- [ ] Investigate React warning about `componentWillReceiveProps` and update offending component (likely third-party Dash component) to supported lifecycle methods.
- [ ] Audit `current-filters` defaults and ensure UI controls (slider, stores) never reset `max_places` to zero.
- [ ] Create helper script/alias to launch app via `pdm run env PYTHONPATH=src python -m dash_imagination.app` to avoid environment mismatch.
- [x] Replace module-level `CorpusState` with per-session `dcc.Store`-backed state to prevent corpus/place data leaking across users in Cloud Run.

- [ ] Document dialog rebuild plan with fixed-size presets (no live resize) and assign each dialog to the right preset.
- [ ] Implement shared dialog shell (header/body/footer) applying those presets, with scrollable table/content regions.
- [ ] Update dialog tables to rely on CSS overflow within fixed heights instead of ResizeObserver logic to avoid call-stack loops.
- [ ] Add “Download places CSV” action inside the Places dialog (include historical name, modern name, frequency, latitude, longitude so results can be used in external GIS tools).
- [ ] Add checkbox in Places to let the heatmap follow the current subset (freq/sampling/collocations) instead of whole corpus.
- [ ] Fix Places dialog background/overflow so the lower half keeps a solid backdrop when scrolling.
- [ ] Revisit Corpus Controls overlay vs. compact corpus summary div; add affordances to inspect/sample current corpus directly from the summary.
- [ ] Vurdere egen SQL-kolonne/tabell for stabile forfatter-IDer synkronisert med autoritetsregister slik at UI alltid finner samme person selv ved navnevarianter.
- [ ] Undersøk hvorfor Author Info iblant ikke viser bøker/bilder selv om forfatteren finnes i korpuset; reproduser og stabiliser kallene.
- [ ] Utforske bok-bilder: eksponere illustrasjoner/sider per bok (gjerne via Corpus View) og bruk Qdrant-lenker for å hoppe mellom lignende bilder.

