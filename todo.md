## TODO

- [ ] Investigate React warning about `componentWillReceiveProps` and update offending component (likely third-party Dash component) to supported lifecycle methods.
- [ ] Audit `current-filters` defaults and ensure UI controls (slider, stores) never reset `max_places` to zero.
- [ ] Create helper script/alias to launch app via `pdm run env PYTHONPATH=src python -m dash_imagination.app` to avoid environment mismatch.
- [x] Replace module-level `CorpusState` with per-session `dcc.Store`-backed state to prevent corpus/place data leaking across users in Cloud Run.

- [ ] Document dialog rebuild plan with fixed-size presets (no live resize) and assign each dialog to the right preset.
- [ ] Implement shared dialog shell (header/body/footer) applying those presets, with scrollable table/content regions.
- [ ] Update dialog tables to rely on CSS overflow within fixed heights instead of ResizeObserver logic to avoid call-stack loops.

