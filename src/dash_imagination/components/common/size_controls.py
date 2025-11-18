from dash import html
import dash_bootstrap_components as dbc

SIZE_PRESETS = {
    'compact': {'width': 320, 'height': 420},
    'standard': {'width': 380, 'height': 500},
    'wide': {'width': 480, 'height': 600},
}

CARD_DEFAULT_PRESET = {
    'place-summary': 'standard',
    'places': 'wide',
    'corpus-controls': 'standard',
    'visualization-controls': 'standard',
    'corpus-builder': 'standard'
}

DEFAULT_CARD_SIZES = {key: SIZE_PRESETS[value].copy() for key, value in CARD_DEFAULT_PRESET.items()}


def size_control_buttons(component_id: str):
    return html.Div([
        html.Div([
            html.Span("W", className="size-label me-1"),
            dbc.ButtonGroup([
                dbc.Button("−", id={'type': 'size-btn', 'card': component_id, 'axis': 'width', 'delta': -80},
                           size="sm", color="light", className="size-btn"),
                dbc.Button("+", id={'type': 'size-btn', 'card': component_id, 'axis': 'width', 'delta': 80},
                           size="sm", color="light", className="size-btn")
            ], size="sm")
        ], className="d-flex align-items-center gap-1"),
        html.Div([
            html.Span("H", className="size-label me-1"),
            dbc.ButtonGroup([
                dbc.Button("−", id={'type': 'size-btn', 'card': component_id, 'axis': 'height', 'delta': -80},
                           size="sm", color="light", className="size-btn"),
                dbc.Button("+", id={'type': 'size-btn', 'card': component_id, 'axis': 'height', 'delta': 80},
                           size="sm", color="light", className="size-btn")
            ], size="sm")
        ], className="d-flex align-items-center gap-1 mt-1")
    ], className="size-control-wrapper")

