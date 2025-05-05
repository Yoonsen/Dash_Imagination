import dash
from dash import dcc, html
import dash_bootstrap_components as dbc

def create_map_controls():
    """Create the map controls component including style, marker size, view toggle, and heatmap settings."""
    return html.Div([
        # Upload Corpus Component
        html.Div([
            dcc.Upload(
                id='upload-corpus',
                children=html.Div([
                    html.I(className="fas fa-upload", style={'marginRight': '5px'}),
                    'Upload Corpus'
                ]),
                style={
                    'width': '100%',
                    'height': '60px',
                    'lineHeight': '60px',
                    'borderWidth': '1px',
                    'borderStyle': 'dashed',
                    'borderRadius': '5px',
                    'textAlign': 'center',
                    'marginBottom': '10px',
                    'cursor': 'pointer'
                },
                multiple=False
            ),
            html.Div(id='upload-status')
        ], className="control-item"),

        # Sample Size Slider
        html.Div([
            html.Label("Sample Size", className="control-label"),
            html.Div([
                dcc.Slider(
                    id='sample-size',
                    min=10,
                    max=100,
                    step=10,
                    value=50,
                    marks={i: str(i) for i in range(10, 101, 20)},
                    className="slider"
                )
            ], className="slider-container")
        ], className="control-item"),

        # Max Places Slider
        html.Div([
            html.Label("Max Places", className="control-label"),
            html.Div([
                dcc.Slider(
                    id='max-places-slider',
                    min=100,
                    max=2000,
                    step=100,
                    value=1500,
                    marks={i: str(i) for i in range(100, 2001, 500)},
                    className="slider"
                )
            ], className="slider-container")
        ], className="control-item"),

        # Reset Corpus Button
        html.Div([
            html.Button(
                html.I(className="fas fa-undo", style={'marginRight': '5px'}),
                id='reset-corpus',
                className="btn btn-outline-secondary btn-sm",
                style={'marginBottom': '10px', 'width': '100%'}
            )
        ], className="control-item"),

        # Map Style Dropdown
        html.Div([
            html.Label("Map Style", className="control-label"),
            dcc.Dropdown(
                id='map-style',
                options=[
                    {'label': 'Light', 'value': 'light'},
                    {'label': 'Dark', 'value': 'dark'},
                    {'label': 'Satellite', 'value': 'satellite'}
                ],
                value='light',
                clearable=False,
                className="dropdown"
            )
        ], className="control-item"),

        # Marker Size Slider
        html.Div([
            html.Label("Marker Size", className="control-label"),
            html.Div([
                dcc.Slider(
                    id='marker-size-slider',
                    min=2,
                    max=6,
                    step=1,
                    value=3,
                    marks={i: str(i) for i in range(2, 7)},
                    className="slider"
                )
            ], className="slider-container")
        ], className="control-item"),

        # View Toggle
        html.Div([
            html.Label("View Type", className="control-label"),
            dcc.RadioItems(
                id='view-toggle',
                options=[
                    {'label': 'Points', 'value': 'points'},
                    {'label': 'Heatmap', 'value': 'heatmap'}
                ],
                value='points',
                labelStyle={'display': 'inline-block', 'margin-right': '10px'},
                className="radio-group"
            )
        ], className="control-item"),

        # Heatmap Settings (initially hidden)
        html.Div([
            html.Label("Heatmap Settings", className="control-label"),
            html.Div([
                html.Label("Intensity", className="sub-label"),
                dcc.Slider(
                    id='heatmap-intensity',
                    min=1,
                    max=10,
                    step=1,
                    value=5,
                    marks={i: str(i) for i in range(1, 11)},
                    className="slider"
                ),
                html.Label("Radius", className="sub-label"),
                dcc.Slider(
                    id='heatmap-radius',
                    min=5,
                    max=50,
                    step=5,
                    value=20,
                    marks={i: str(i) for i in range(5, 51, 5)},
                    className="slider"
                )
            ], className="heatmap-settings")
        ], id='heatmap-settings', className="control-item", style={'display': 'none'}),

        # Cluster Toggle
        html.Div([
            html.Label("Clustering", className="control-label"),
            dcc.RadioItems(
                id='cluster-toggle',
                options=[
                    {'label': 'On', 'value': 'on'},
                    {'label': 'Off', 'value': 'off'}
                ],
                value='on',
                labelStyle={'display': 'inline-block', 'margin-right': '10px'},
                className="radio-group"
            )
        ], className="control-item")
    ], className="map-controls") 