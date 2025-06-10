from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from dash import callback, no_update
import dash

def create_corpus_controls(categories_list=None, titles_list=None, default_filters=None):
    """Create the corpus controls as a popup dialogue, with modern upload/download and info layout."""
    if categories_list is None:
        categories_list = []
    if titles_list is None:
        titles_list = []
    if default_filters is None:
        default_filters = {'categories': [], 'titles': []}

    return dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.I(className="fa fa-book me-2"),
                html.H5("Corpus Controls", className="mb-0", style={"fontSize": "14px", "fontWeight": 500}),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-corpus',
                    className="btn-close"
                )
            ], className="d-flex justify-content-between align-items-center")
        ], className="bg-primary-subtle text-dark", id='corpus-header'),
        dbc.CardBody([
            # Upload/Download/Add Books/Reset row
            html.Div([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            dcc.Upload(
                                id='popup-upload-corpus',
                                children=html.Div([
                                    html.I(className="fas fa-upload fa-lg d-block text-center", style={"color": "#2563eb"}),
                                ]),
                                style={
                                    'display': 'inline-block',
                                    'cursor': 'pointer',
                                    'border': 'none',
                                    'background': 'none',
                                    'padding': '0',
                                    'width': '60px'
                                },
                                multiple=False
                            ),
                            html.Small("Upload", className="d-block text-center mt-1")
                        ], className="text-center")
                    ], width="auto"),
                    dbc.Col([
                        html.Div([
                            dbc.Button([
                                html.I(className="fas fa-download fa-lg d-block text-center", style={"color": "#059669"})
                            ], id='corpus-download-btn-unique', n_clicks=0, color="link", className="p-0", style={'width': '60px'}),
                            html.Small("Download", className="d-block text-center mt-1"),
                            dcc.Download(id='corpus-download-unique')
                        ], className="text-center")
                    ], width="auto"),
                    dbc.Col([
                        html.Div([
                            html.Button([
                                html.I(className="fas fa-plus fa-lg d-block text-center", style={"color": "#d97706"}),
                            ], id='open-corpus-builder', n_clicks=0, className="btn btn-link p-0", style={'width': '60px', 'textDecoration': 'none', 'boxShadow': 'none', 'border': 'none'}),
                            html.Small("Add Books", className="d-block text-center mt-1")
                        ], className="text-center")
                    ], width="auto"),
                    dbc.Col([
                        html.Div([
                            html.Button(
                                html.I(className="far fa-trash-alt fa-lg d-block text-center", style={"color": "#dc2626"}),
                                id='reset-corpus-btn-main',
                                n_clicks=0,
                                className="btn btn-link p-0",
                                style={'width': '60px'},
                                title="Reset Corpus (double-click to confirm)"
                            ),
                            html.Small("Reset", className="d-block text-center mt-1"),
                            dcc.Interval(id='reset-corpus-timer', interval=5000, n_intervals=0, disabled=True, max_intervals=1),
                            dcc.Store(id='reset-corpus-confirm', data=False)
                        ], className="text-center")
                    ], width="auto"),
                ], className="g-3 justify-content-center"),
                html.Div(id='popup-upload-status', className="mb-2 text-center")
            ], className="mb-3"),
            # Corpus info stats row (4 columns)
            html.Div([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-book fa-lg", style={"color": "#2563eb", "fontSize": "1.1rem"}),
                            html.Div(id='corpus-info-books', className="fw-bold mt-1", style={'fontSize': '0.95rem'}),
                            html.Small("Books", className="text-muted", style={"fontSize": "0.8rem"})
                        ], className="text-center")
                    ], width=3),
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-user fa-lg", style={"color": "#059669", "fontSize": "1.1rem"}),
                            html.Div(id='corpus-info-authors', className="fw-bold mt-1", style={'fontSize': '0.95rem'}),
                            html.Small("Authors", className="text-muted", style={"fontSize": "0.8rem"})
                        ], className="text-center")
                    ], width=3),
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-map-marker-alt fa-lg", style={"color": "#f59e42", "fontSize": "1.1rem"}),
                            html.Div(id='corpus-info-places', className="fw-bold mt-1", style={'fontSize': '0.95rem'}),
                            html.Small("Places", className="text-muted", style={"fontSize": "0.8rem"})
                        ], className="text-center")
                    ], width=3),
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-calendar fa-lg", style={"color": "#d97706", "fontSize": "1.1rem"}),
                            html.Div(id='corpus-info-years', className="fw-bold mt-1", style={'fontSize': '0.95rem'}),
                            html.Small("Years", className="text-muted", style={"fontSize": "0.8rem"})
                        ], className="text-center")
                    ], width=3),
                ], className="g-2 mb-3 justify-content-center")
            ]),
            html.Hr(style={'margin': '12px 0'}),
            # Browse Table Section (always visible)
            html.Div([
                html.Div(id='corpus-browse-table', style={'flex': '1 1 auto', 'minHeight': 0, 'overflowY': 'auto', 'fontSize': '0.8rem'})
            ], style={'height': '100%', 'display': 'flex', 'flexDirection': 'column'})
        ], style={'height': '444px', 'overflowY': 'auto'}),
        # Hidden resample-places button to suppress callback errors and allow future restoration
        html.Button("Resample Places", id="resample-places", style={"display": "none"}),
        # Hidden resample-container div to suppress callback errors
        html.Div(id='resample-container', style={'display': 'none'})
    ], id='corpus-controls-container', className="position-absolute m-3", style={
        'width': '450px',
        'height': '500px',
        'zIndex': 800,
        'display': 'none',
        'top': '60px',
        'left': '10px'
    })

def create_visualization_controls(categories_list=None, titles_list=None, default_filters=None):
    """Create the visualization controls as a popup dialogue."""
    if categories_list is None:
        categories_list = []
    if titles_list is None:
        titles_list = []
    if default_filters is None:
        default_filters = {'categories': [], 'titles': []}

    return dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.I(className="fa fa-chart-bar me-2"),
                html.H5("Visualization Controls", className="mb-0", style={"fontSize": "14px", "fontWeight": 500}),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-visualization',
                    className="btn-close"
                )
            ], className="d-flex justify-content-between align-items-center")
        ], className="bg-info-subtle text-dark", id='visualization-header'),
        dbc.CardBody([
            # Tabs for Map and Heatmap views
            dbc.Tabs([
                # Map View Tab
                dbc.Tab([
                    # Clustering toggle
                    html.Div([
                        html.Label("Clustering", className="form-label"),
                        dcc.Checklist(
                            id='top-cluster-toggle',
                            options=[{'label': 'Enable Clustering', 'value': 'cluster'}],
                            value=[],
                            className="mt-1"
                        )
                    ], className="mb-4"),
                    
                    # Marker size slider
                    html.Div([
                        html.Label("Place Marker Size", className="form-label"),
                        dcc.Slider(
                            id='marker-size-slider',
                            min=1,
                            max=20,
                            step=1,
                            value=8,
                            marks={i: str(i) for i in range(1, 21, 2)},
                            className="mt-1"
                        )
                    ], className="mb-4"),
                    
                    # Cluster size slider
                    html.Div([
                        html.Label("Cluster Marker Size", className="form-label"),
                        dcc.Slider(
                            id='cluster-size-slider',
                            min=1,
                            max=10,
                            step=1,
                            value=3,
                            marks={i: str(i) for i in range(1, 11, 1)},
                            className="mt-1"
                        )
                    ], className="mb-4"),
                    
                    # Cluster radius slider
                    html.Div([
                        html.Label("Cluster Radius", className="form-label"),
                        dcc.Slider(
                            id='cluster-radius-slider',
                            min=10,
                            max=100,
                            step=10,
                            value=50,
                            marks={i: str(i) for i in range(10, 101, 20)},
                            className="mt-1"
                        )
                    ], className="mb-4")
                ], label="Map View"),
                
                # Heatmap View Tab
                dbc.Tab([
                    # Heatmap intensity slider
                    html.Div([
                        html.Label("Heatmap Intensity", className="form-label"),
                        dcc.Slider(
                            id='heatmap-intensity',
                            min=1,
                            max=10,
                            step=1,
                            value=5,
                            marks={i: str(i) for i in range(1, 11)},
                            className="mt-1"
                        )
                    ], className="mb-4"),
                    
                    # Heatmap radius slider
                    html.Div([
                        html.Label("Heatmap Radius", className="form-label"),
                        dcc.Slider(
                            id='heatmap-radius',
                            min=5,
                            max=50,
                            step=5,
                            value=20,
                            marks={i: str(i) for i in range(5, 51, 5)},
                            className="mt-1"
                        )
                    ], className="mb-4"),
                    
                    # Heatmap colorscale dropdown
                    html.Div([
                        html.Label("Heatmap Colorscale", className="form-label"),
                        dcc.Dropdown(
                            id='heatmap-colorscale',
                            options=[
                                {'label': 'Viridis', 'value': 'Viridis'},
                                {'label': 'Plasma', 'value': 'Plasma'},
                                {'label': 'Inferno', 'value': 'Inferno'},
                                {'label': 'Magma', 'value': 'Magma'},
                                {'label': 'Blues', 'value': 'Blues'},
                                {'label': 'Reds', 'value': 'Reds'},
                                {'label': 'Greens', 'value': 'Greens'}
                            ],
                            value='Viridis',
                            clearable=False
                        )
                    ], className="mb-4")
                ], label="Heatmap View")
            ], className="mt-4"),
            
            # Download format dropdown
            html.Div([
                html.Label("Download Format", className="form-label"),
                dcc.Dropdown(
                    id='download-format',
                    options=[
                        {'label': 'PNG (image)', 'value': 'png'},
                        {'label': 'PDF (vector)', 'value': 'pdf'},
                        {'label': 'SVG (vector)', 'value': 'svg'}
                    ],
                    value='png',
                    clearable=False,
                    className="mb-2"
                )
            ], className="mb-3"),
            # Download resolution dropdown
            html.Div([
                html.Label("Resolution", className="form-label"),
                dcc.Dropdown(
                    id='download-resolution',
                    options=[
                        {'label': 'Standard (1920x1080)', 'value': 'standard'},
                        {'label': 'High (3840x2160)', 'value': 'high'},
                        {'label': 'Publication (6000x4000)', 'value': 'publication'}
                    ],
                    value='standard',
                    clearable=False,
                    className="mb-2"
                )
            ], className="mb-3"),
            # Download button
            dbc.Button(
                [
                    html.I(className="fas fa-download me-2"),
                    "Download Map"
                ],
                id='download-map',
                color="primary",
                className="w-100"
            ),
            # Download component for Dash downloads
            dcc.Download(id="download-map-file"),
            # Status message
            html.Div(id='download-status', className="mt-2")
        ], style={'overflowY': 'auto', 'maxHeight': 'calc(500px - 56px)'})  # 56px is header height
    ], id='visualization-controls-container', className="position-absolute", style={
        'width': '350px',
        'height': '500px',
        'zIndex': 800,
        'display': 'none',
        'top': '100px',
        'left': '20px',
        'cursor': 'move'
    }) 

@callback(
    [Output('reset-corpus-btn-main', 'className'),
     Output('reset-corpus-btn-main', 'title'),
     Output('reset-corpus-timer', 'disabled'),
     Output('reset-corpus-timer', 'n_intervals'),
     Output('reset-corpus-confirm', 'data')],
    [Input('reset-corpus-btn-main', 'n_clicks'),
     Input('reset-corpus-timer', 'n_intervals')],
    [State('reset-corpus-btn-main', 'className'),
     State('reset-corpus-timer', 'disabled'),
     State('reset-corpus-confirm', 'data')],
    prevent_initial_call=True
)
def confirm_reset_corpus(n_clicks, timer_intervals, className, timer_disabled, confirm_state):
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    if triggered_id == 'reset-corpus-btn-main':
        # First click: highlight (add text-danger), enable timer, set confirm True
        if 'text-danger' not in className:
            return 'btn btn-link p-0 text-danger', 'Click again to confirm reset', False, 0, True
        else:
            # Second click: allow the actual reset action (handled elsewhere), reset timer and confirm
            return 'btn btn-link p-0', 'Reset Corpus (double-click to confirm)', True, 0, False
    elif triggered_id == 'reset-corpus-timer':
        # Timer expired: revert to plain
        return 'btn btn-link p-0', 'Reset Corpus (double-click to confirm)', True, 0, False
    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update 