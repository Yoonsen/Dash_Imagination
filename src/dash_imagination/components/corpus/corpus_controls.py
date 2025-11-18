from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from dash import callback, no_update
import dash
from dash import ALL
from ..common.size_controls import size_control_buttons, CARD_DEFAULT_PRESET, DEFAULT_CARD_SIZES

def create_corpus_controls(categories_list=None, titles_list=None, default_filters=None):
    """Create the corpus controls as a popup dialogue, with modern upload/download and info layout."""
    if categories_list is None:
        categories_list = []
    if titles_list is None:
        titles_list = []
    if default_filters is None:
        default_filters = {'categories': [], 'titles': []}

    return dbc.Card([
        dbc.CardHeader(
            html.Div([
                html.Div([
                    html.I(className="fa fa-book me-2"),
                    html.H5("Corpus Controls", className="mb-0", style={"fontSize": "14px", "fontWeight": 500}),
                    html.Button(
                        "×",
                        id='close-corpus',
                        className="btn-close dialog-close-btn",
                        title="Close"
                    )
                ], className="d-flex justify-content-between align-items-center flex-grow-1 me-2"),
                size_control_buttons('corpus-controls')
            ], className="d-flex justify-content-between align-items-center gap-2"),
            className="bg-primary-subtle text-dark",
            id='corpus-header'
        ),
        dbc.CardBody([
            # Upload/Download/Add Books/Reset row
            html.Div([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            dcc.Upload(
                                id='popup-upload-corpus',
                                children=html.Div([
                                    html.I(className="fas fa-upload", style={"color": "#4B6CB7", "fontSize": "1rem"}),
                                ]),
                                style={
                                    'display': 'inline-block',
                                    'cursor': 'pointer',
                                    'border': 'none',
                                    'background': 'none',
                                    'padding': '0',
                                    'width': '40px'
                                },
                                multiple=False
                            ),
                        ], className="text-center")
                    ], width="auto"),
                    dbc.Col([
                        html.Div([
                            dbc.Button([
                                html.I(className="fas fa-download", style={"color": "#4B6CB7", "fontSize": "1rem"})
                            ], id='corpus-download-btn-unique', n_clicks=0, color="link", className="p-0", style={'width': '40px'}),
                            dcc.Download(id='corpus-download-unique')
                        ], className="text-center")
                    ], width="auto"),
                    dbc.Col([
                        html.Div([
                            html.Button([
                                html.I(className="fas fa-plus", style={"color": "#4B6CB7", "fontSize": "1rem"}),
                            ], id='open-corpus-builder', n_clicks=0, className="btn btn-link p-0", style={'width': '40px', 'textDecoration': 'none', 'boxShadow': 'none', 'border': 'none'})
                        ], className="text-center")
                    ], width="auto"),
                    dbc.Col([
                        html.Div([
                            html.Button(
                                html.I(className="far fa-trash-alt", style={"color": "#dc2626", "fontSize": "1rem"}),
                                id='reset-corpus-btn-main',
                                n_clicks=0,
                                className="btn btn-link p-0",
                                style={'width': '40px'},
                                title="Reset Corpus"
                            ),
                            # Remove timer and store, add modal
                            dbc.Modal([
                                dbc.ModalHeader("Confirm Reset Corpus"),
                                dbc.ModalBody("Are you sure you want to reset the corpus? This will clear your current selection."),
                                dbc.ModalFooter([
                                    dbc.Button("Cancel", id="reset-corpus-cancel", color="secondary", className="me-2"),
                                    dbc.Button("Confirm Reset", id="reset-corpus-confirm-modal", color="danger")
                                ])
                            ], id="reset-corpus-modal", is_open=False, centered=True)
                        ], className="text-center")
                    ], width="auto"),
                ], className="g-3 justify-content-center"),
                html.Div(id='popup-upload-status', className="mb-2 text-center")
            ], style={'marginBottom': '12px'}),
            dbc.Row([
                dbc.Col([
                    dbc.Button("+", id='corpus-op-union-controls', n_clicks=0, color='secondary',
                               outline=True, size="sm", title="Add uploaded corpus to current selection")
                ], width="auto"),
                dbc.Col([
                    dbc.Button("&", id='corpus-op-intersection-controls', n_clicks=0, color='secondary',
                               outline=True, size="sm", title="Keep only overlap with current selection")
                ], width="auto"),
                dbc.Col([
                    dbc.Button("-", id='corpus-op-diff-controls', n_clicks=0, color='secondary',
                               outline=True, size="sm", title="Remove uploaded corpus from current selection")
                ], width="auto"),
            ], className="g-2 justify-content-center mb-3"),
            # Corpus info stats row (4 columns)
            html.Div([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.Div([
                                html.I(className="fas fa-book", style={"color": "#4B6CB7", "fontSize": "0.95rem", 'marginRight': '6px'}),
                                html.Span(id='corpus-info-books', style={'fontSize': '0.7rem', 'fontWeight': '400', 'verticalAlign': 'middle'})
                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'})
                        ], className="text-center")
                    ], width=3),
                    dbc.Col([
                        html.Div([
                            html.Div([
                                html.I(className="fas fa-user", style={"color": "#4B6CB7", "fontSize": "0.95rem", 'marginRight': '6px'}),
                                html.Span(id='corpus-info-authors', style={'fontSize': '0.7rem', 'fontWeight': '400', 'verticalAlign': 'middle'})
                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'})
                        ], className="text-center")
                    ], width=3),
                    dbc.Col([
                        html.Div([
                            html.Div([
                                html.I(className="fas fa-map-marker-alt", style={"color": "#4B6CB7", "fontSize": "0.95rem", 'marginRight': '6px'}),
                                html.Span(id='corpus-info-places', style={'fontSize': '0.7rem', 'fontWeight': '400', 'verticalAlign': 'middle'})
                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'})
                        ], className="text-center")
                    ], width=3),
                    dbc.Col([
                        html.Div([
                            html.Div([
                                html.I(className="fas fa-calendar", style={"color": "#4B6CB7", "fontSize": "0.95rem", 'marginRight': '6px'}),
                                html.Span(id='corpus-info-years', style={'fontSize': '0.7rem', 'fontWeight': '400', 'verticalAlign': 'middle'})
                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'})
                        ], className="text-center")
                    ], width=3),
                ], className="g-2 mb-2 justify-content-center"),
            ]),
            html.Hr(style={'margin': '12px 0'}),
            # Browse Table Section (always visible)
            html.Div([
                filter_bar,
                html.Div(id='corpus-browse-table', style={'flex': '1 1 auto', 'minHeight': 0, 'overflowY': 'auto', 'fontSize': '0.8rem'}),
                dcc.Store(id='corpus-table-filter', data={'column': None, 'value': None, 'direction': None})
            ], style={'flex': '1 1 auto', 'display': 'flex', 'flexDirection': 'column', 'minHeight': 0})
        ], style={'flex': '1 1 auto', 'minHeight': 0, 'display': 'flex', 'flexDirection': 'column', 'gap': '0.75rem'}),
        # Hidden resample-container div to suppress callback errors
        html.Div(id='resample-container', style={'display': 'none'})
    ], id='corpus-controls-container', className="position-absolute m-3 dialog-card d-flex flex-column", style={
        'width': f"{DEFAULT_CARD_SIZES['corpus-controls']['width']}px",
        'height': f"{DEFAULT_CARD_SIZES['corpus-controls']['height']}px",
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
        dbc.CardHeader(
            html.Div([
                html.Div([
                    html.I(className="fa fa-chart-bar me-2"),
                    html.H5("Visualization Controls", className="mb-0", style={"fontSize": "14px", "fontWeight": 500}),
                    html.Button(
                        "×",
                        id='close-visualization',
                        className="btn-close dialog-close-btn",
                        title="Close"
                    )
                ], className="d-flex justify-content-between align-items-center flex-grow-1 me-2"),
                size_control_buttons('visualization-controls')
            ], className="d-flex justify-content-between align-items-center gap-2"),
            className="bg-info-subtle text-dark",
            id='visualization-header'
        ),
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
        ], style={'flex': '1 1 auto', 'minHeight': 0, 'overflowY': 'auto'})
    ], id='visualization-controls-container', className="position-absolute dialog-card d-flex flex-column", style={
        'width': f"{DEFAULT_CARD_SIZES['visualization-controls']['width']}px",
        'height': f"{DEFAULT_CARD_SIZES['visualization-controls']['height']}px",
        'zIndex': 800,
        'display': 'none',
        'top': '100px',
        'left': '20px',
        'cursor': 'move'
    }) 

@callback(
    Output('reset-corpus-modal', 'is_open'),
    [Input('reset-corpus-btn-main', 'n_clicks'),
     Input('reset-corpus-cancel', 'n_clicks'),
     Input('reset-corpus-confirm-modal', 'n_clicks')],
    [State('reset-corpus-modal', 'is_open')],
    prevent_initial_call=True
)
def toggle_reset_modal(reset_btn, cancel_btn, confirm_btn, is_open):
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_open
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger == 'reset-corpus-btn-main':
        return True
    elif trigger in ['reset-corpus-cancel', 'reset-corpus-confirm-modal']:
        return False
    return is_open

# Remove old filter bars and input
# Add new filter bar and modal
filter_bar = html.Div(
    [
        html.Div(
            html.Span("\u2699", style={"fontSize": "1.3rem"}),
            id="corpus-filter-bar",
            title="Filter corpus…",
            style={
                "width": "400px",
                "height": "18px",
                "margin": "0 auto 10px auto",
                "background": "#e0e7ef",
                "borderRadius": "6px",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "fontSize": "0.9rem",
                "fontWeight": 500,
                "color": "#4B6CB7",
                "cursor": "pointer",
                "boxShadow": "0 1px 2px rgba(0,0,0,0.04)",
                "transition": "background 0.2s"
            }
        ),
        dbc.Modal(
            [
                dbc.ModalHeader("Filter Corpus (coming soon)"),
                dbc.ModalBody("Filter options will appear here."),
                dbc.ModalFooter(
                    dbc.Button("Confirm", id="corpus-filter-modal-confirm", color="primary", n_clicks=0)
                )
            ],
            id="corpus-filter-modal",
            is_open=False,
            centered=True,
            backdrop=True,
        )
    ]
) 

@callback(
    Output('corpus-filter-modal', 'is_open'),
    [Input('corpus-filter-bar', 'n_clicks'), Input('corpus-filter-modal-confirm', 'n_clicks')],
    [State('corpus-filter-modal', 'is_open')],
    prevent_initial_call=True
)
def toggle_filter_modal(bar_click, confirm_click, is_open):
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_open
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger == 'corpus-filter-bar' and bar_click:
        return True
    elif trigger == 'corpus-filter-modal-confirm' and confirm_click:
        return False
    return is_open 