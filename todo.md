## TODO

- [ ] Investigate React warning about `componentWillReceiveProps` and update offending component (likely third-party Dash component) to supported lifecycle methods.
- [ ] Audit `current-filters` defaults and ensure UI controls (slider, stores) never reset `max_places` to zero.
- [ ] Create helper script/alias to launch app via `pdm run env PYTHONPATH=src python -m dash_imagination.app` to avoid environment mismatch.
- [ ] Replace module-level `CorpusState` with per-session `dcc.Store`-backed state to prevent corpus/place data leaking across users in Cloud Run.

