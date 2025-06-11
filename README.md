# Welcome to Dash Imagination!

---

**A message for future maintainers, collaborators, and especially my kids:**

Welcome! This project is built with care, curiosity, and a love for making data and stories come alive. Whether you're a seasoned coder, a new explorer, or a family member picking up where I left off, I hope you find this codebase clear, helpful, and inspiring.

- **Commit messages and code comments** are written for you—so you can understand not just what was done, but why.
- **Don't be afraid to experiment!** Every great project grows with new ideas and fresh eyes.
- **If you're reading this, you're part of the story.** Keep building, keep learning, and don't hesitate to ask for help (from humans or helpful AIs!).

May your bugs be few, your features delightful, and your curiosity endless.

— Lars (and the AI assistant)

---

# Dash_Imagination

## Note on Image Export (Kaleido)

To enable image export (e.g., for Plotly figures), you must install the `kaleido` package directly with pip after running `pdm install`. Do not add `kaleido` to your `pyproject.toml`, as PDM may not be able to resolve it due to its binary-only nature.

After setting up your environment with PDM, run:

```
.venv/bin/pip install kaleido
```

This ensures `kaleido` is available in your virtual environment for image export functionality.
