# Changelog

## [2024-05-13] - Development Environment and Import Fixes

### Fixed
- Updated import paths in `app.py` to use full package path for components:
  - Changed `from components.map import create_map_controls` to `from dash_imagination.components.map import create_map_controls`
  - Changed `from components.corpus import create_corpus_controls` to `from dash_imagination.components.corpus import create_corpus_controls`
- Updated deprecated Dash imports in `components/corpus/corpus_controls.py`:
  - Replaced `import dash_core_components as dcc` with `from dash import dcc`
  - Replaced `import dash_html_components as html` with `from dash import html`

### Changed
- Confirmed app runs successfully using `pdm run python -m dash_imagination.app`
- Established working development environment over SSH

### Notes
- App is now working with proper package imports
- Development can continue either through SSH or X11 forwarding
- Next major task remains Place Search feature as per todolist.md 