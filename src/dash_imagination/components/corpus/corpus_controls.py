from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State

def create_corpus_controls(categories_list=None, titles_list=None, default_filters=None):
    """Create the corpus controls as a popup dialogue."""
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
                html.H4("Corpus Controls", className="mb-0"),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-corpus',
                    className="btn-close"
                )
            ], className="d-flex justify-content-between align-items-center")
        ], className="bg-primary text-white", id='corpus-header'),
        dbc.CardBody([
            # Upload section
            dcc.Upload(
                id='popup-upload-corpus',
                children=html.Div([
                    html.I(className="fas fa-upload me-2"),
                    'Drag and Drop or ',
                    html.A('Select a Corpus File')
                ]),
                style={
                    'width': '100%',
                    'height': '60px',
                    'lineHeight': '60px',
                    'borderWidth': '1px',
                    'borderStyle': 'dashed',
                    'borderRadius': '5px',
                    'textAlign': 'center',
                    'margin': '10px 0',
                    'cursor': 'pointer'
                },
                multiple=False
            ),
            html.Div(id='popup-upload-status', className="mb-4"),
            
            # Sample Size
            html.Div([
                html.Label("Number of Books", className="form-label"),
                html.Div([
                    dcc.Input(
                        id='popup-sample-size',
                        type='number',
                        value=0,
                        min=0,
                        max=20000,
                        step=100,
                        className="form-control"
                    ),
                    html.Div("0 means no limit - all books will be included", className="form-text")
                ])
            ], className="mb-4"),
            
            # Max Places Slider
            html.Div([
                html.Label("Maximum Places", className="form-label"),
                dcc.Slider(
                    id='popup-max-places-slider',
                    min=100,
                    max=2000,
                    step=100,
                    value=1500,
                    marks={i: str(i) for i in range(100, 2001, 500)},
                    className="mb-3"
                )
            ], className="mb-4"),
            
            # Year Range Slider
            html.Div([
                html.Label("Year Range", className="form-label"),
                dcc.RangeSlider(
                    id='year-range-slider',
                    min=1814,
                    max=1905,
                    step=1,
                    value=[1814, 1905],
                    marks={i: str(i) for i in range(1814, 1906, 10)},
                    className="mb-3"
                )
            ], className="mb-4"),
            
            # Category selection
            html.Div([
                html.H5("Select Categories", className="mb-3"),
                dcc.Dropdown(
                    id='category-dropdown',
                    options=[{'label': cat, 'value': cat} for cat in categories_list],
                    value=default_filters['categories'],
                    multi=True,
                    placeholder="Select categories..."
                )
            ], className="mb-4"),
            
            # Title selection
            html.Div([
                html.H5("Select Titles", className="mb-3"),
                dcc.Dropdown(
                    id='title-dropdown',
                    options=[{'label': title, 'value': title} for title in titles_list],
                    value=default_filters['titles'],
                    multi=True,
                    placeholder="Select titles..."
                )
            ], className="mb-4"),
            
            # Apply Filters button
            dbc.Button(
                [
                    html.I(className="fas fa-check me-2"),
                    "Apply Filters"
                ],
                id='apply-filters',
                color="primary",
                className="w-100 mb-3"
            ),
            
            # Reset button
            dbc.Button(
                [
                    html.I(className="fas fa-undo me-2"),
                    "Clear Corpus"
                ],
                id='popup-reset-corpus',
                color="secondary",
                className="w-100"
            ),
            
            # Resampling section
            html.Div([
                html.Hr(),
                html.H5("Resampling", className="mb-3"),
                html.Div(id='corpus-controls-info', className="mb-2"),
                html.Div(id='author-count', className="mb-2"),
                html.Div(id='book-count', className="mb-2"),
                html.Div(id='total-places', className="mb-2"),
                html.Div(id='sample-places', className="mb-2"),
                html.Div(id='max-sample-size', className="mb-3"),
                dbc.Button(
                    [
                        html.I(className="fas fa-random me-2"),
                        "Resample Places"
                    ],
                    id='resample-places',
                    color="info",
                    className="w-100"
                )
            ], id='resample-container', style={'display': 'none'})
        ], style={'overflowY': 'auto', 'maxHeight': 'calc(500px - 56px)'})  # 56px is header height
    ], id='corpus-controls-container', className="position-absolute m-3", style={
        'width': '350px',
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
                html.I(className="fa fa-grip-horizontal me-2"),
                html.H4("Visualization Controls", className="mb-0"),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-visualization',
                    className="btn-close"
                )
            ], className="d-flex justify-content-between align-items-center")
        ], className="bg-info text-white", id='visualization-header'),
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