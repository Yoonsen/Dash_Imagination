# Dash_Imagination

## Note on Image Export (Kaleido)

To enable image export (e.g., for Plotly figures), you must install the `kaleido` package directly with pip after running `pdm install`. Do not add `kaleido` to your `pyproject.toml`, as PDM may not be able to resolve it due to its binary-only nature.

After setting up your environment with PDM, run:

```
.venv/bin/pip install kaleido
```

This ensures `kaleido` is available in your virtual environment for image export functionality.
