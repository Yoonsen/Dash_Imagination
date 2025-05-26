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

    return html.Div([
        html.Div([
            html.Div([
                html.I(className="fa fa-book", style={'marginRight': '8px'}),
                html.H4("Corpus Controls", style={'marginBottom': '0', 'fontWeight': '400', 'flex': '1'}),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-corpus',
                    style={
                        'background': 'none',
                        'border': 'none',
                        'cursor': 'pointer',
                        'fontSize': '16px'
                    }
                )
            ], style={
                'display': 'flex',
                'justifyContent': 'space-between',
                'alignItems': 'center',
                'marginBottom': '10px',
                'cursor': 'move'
            }, id='corpus-header'),
            
            # Upload section
            dcc.Upload(
                id='popup-upload-corpus',
                children=html.Div([
                    html.I(className="fas fa-upload mr-2"),
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
                html.Label("Number of Books", className="block text-sm font-medium text-gray-700"),
                html.Div([
                    dcc.Input(
                        id='popup-sample-size',
                        type='number',
                        value=0,
                        min=0,
                        max=20000,
                        step=100,
                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                    ),
                    html.Div("0 means no limit - all books will be included", className="text-sm text-gray-500 mt-1")
                ])
            ], className="mb-4"),
            
            # Max Places
            html.Div([
                html.Label("Number of Places", className="block text-sm font-medium text-gray-700"),
                html.Div([
                    dcc.Slider(
                        id='popup-max-places-slider',
                        min=0,
                        max=2000,
                        step=100,
                        value=0,
                        marks={i: str(i) for i in range(0, 2001, 500)},
                        className="mt-1"
                    ),
                    html.Div([
                        html.Span("0 means no limit (up to 2000 places for performance)", className="text-sm text-gray-500"),
                        html.Br(),
                        html.Span("Higher values may affect map performance", className="text-sm text-gray-500")
                    ], className="mt-1")
                ])
            ], className="mb-4"),
            
            # Year Range
            html.Div([
                html.Label("Year Range", className="block text-sm font-medium text-gray-700"),
                dcc.RangeSlider(
                    id='year-range-slider',
                    min=1814,
                    max=1905,
                    step=1,
                    value=[1814, 1905],
                    marks={i: str(i) for i in range(1814, 1906, 10)},
                    className="mt-1"
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
                    html.I(className="fas fa-check mr-2"),
                    "Apply Filters"
                ],
                id='apply-filters',
                color="primary",
                className="w-100 mb-3"
            ),
            
            # Reset button
            dbc.Button(
                [
                    html.I(className="fas fa-undo mr-2"),
                    "Clear Corpus"
                ],
                id='popup-reset-corpus',
                color="secondary",
                className="w-100"
            ),
            
            # Corpus Info Section
            html.Div([
                html.Hr(className="my-3"),
                html.H5("Corpus Information", className="mb-3"),
                html.Div(id='corpus-controls-info', children=[
                    html.P("No corpus loaded", className="text-muted")
                ])
            ], className="mt-4")
        ], style={
            'padding': '15px',
            'backgroundColor': 'white',
            'borderRadius': '8px',
            'boxShadow': '0 4px 15px rgba(0,0,0,0.15)',
            'border': '1px solid rgba(0,0,0,0.05)'
        })
    ], id='corpus-controls-container', style={
        'position': 'absolute',
        'top': '80px',
        'left': '20px',
        'width': '350px',
        'maxHeight': '500px',
        'overflowY': 'auto',
        'zIndex': 800,
        'display': 'none',
        'cursor': 'auto'
    })

def create_visualization_controls(categories_list=None, titles_list=None, default_filters=None):
    """Create the visualization controls as a popup dialogue."""
    if categories_list is None:
        categories_list = []
    if titles_list is None:
        titles_list = []
    if default_filters is None:
        default_filters = {'categories': [], 'titles': []}

    return html.Div([
        html.Div([
            html.Div([
                html.I(className="fa fa-grip-horizontal"),
                html.H4("Visualization Controls", style={'marginBottom': '0', 'fontWeight': '400', 'flex': '1'}),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-visualization',
                    style={
                        'background': 'none',
                        'border': 'none',
                        'cursor': 'pointer',
                        'fontSize': '16px'
                    }
                )
            ], style={
                'display': 'flex',
                'justifyContent': 'space-between',
                'alignItems': 'center',
                'marginBottom': '10px',
                'cursor': 'move'
            }, id='visualization-header'),
            
            # Tabs for Map and Heatmap views
            dbc.Tabs([
                # Map View Tab
                dbc.Tab([
                    # Clustering toggle
                    html.Div([
                        html.Label("Clustering", style={'fontWeight': '500', 'marginBottom': '5px'}),
                        dcc.Checklist(
                            id='top-cluster-toggle',
                            options=[{'label': 'Enable Clustering', 'value': 'cluster'}],
                            value=[],
                            className="mt-1"
                        )
                    ], className="mb-4"),
                    
                    # Marker size slider
                    html.Div([
                        html.Label("Place Marker Size", style={'fontWeight': '500', 'marginBottom': '5px'}),
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
                        html.Label("Cluster Marker Size", style={'fontWeight': '500', 'marginBottom': '5px'}),
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
                        html.Label("Cluster Radius (km)", style={'fontWeight': '500', 'marginBottom': '5px'}),
                        dcc.Slider(
                            id='cluster-radius-slider',
                            min=10,
                            max=200,
                            step=10,
                            value=50,
                            marks={i: f"{i}km" for i in range(10, 201, 50)},
                            className="mt-1"
                        )
                    ], className="mb-4"),
                ], label="Map View", tab_id="points"),
                
                # Heatmap View Tab
                dbc.Tab([
                    # Heatmap settings
                    html.Div([
                        html.Label("Color Scheme", style={'fontWeight': '500', 'marginBottom': '5px'}),
                        dcc.Dropdown(
                            id='heatmap-colorscale',
                            options=[
                                {'label': 'Viridis', 'value': 'Viridis'},
                                {'label': 'Plasma', 'value': 'Plasma'},
                                {'label': 'Inferno', 'value': 'Inferno'},
                                {'label': 'Magma', 'value': 'Magma'},
                                {'label': 'Blues', 'value': 'Blues'},
                                {'label': 'Reds', 'value': 'Reds'},
                                {'label': 'Greens', 'value': 'Greens'},
                                {'label': 'Purples', 'value': 'Purples'},
                                {'label': 'Oranges', 'value': 'Oranges'},
                                {'label': 'Greys', 'value': 'Greys'}
                            ],
                            value='Viridis',
                            clearable=False,
                            className="mb-4"
                        )
                    ], className="mb-4"),
                    html.Div([
                        html.Label("Intensity", style={'fontWeight': '500', 'marginBottom': '5px'}),
                        dcc.Slider(
                            id='heatmap-intensity',
                            min=1,
                            max=10,
                            step=1,
                            value=5,
                            marks={i: str(i) for i in range(1, 11, 1)},
                            className="mt-1"
                        )
                    ], className="mb-4"),
                    html.Div([
                        html.Label("Radius", style={'fontWeight': '500', 'marginBottom': '5px'}),
                        dcc.Slider(
                            id='heatmap-radius',
                            min=1,
                            max=10,
                            step=1,
                            value=5,
                            marks={i: str(i) for i in range(1, 11, 1)},
                            className="mt-1"
                        )
                    ], className="mb-4")
                ], label="Heatmap View", tab_id="heatmap")
            ], id="view-tabs", active_tab="points")
        ], style={
            'padding': '15px',
            'backgroundColor': 'white',
            'borderRadius': '8px',
            'boxShadow': '0 4px 15px rgba(0,0,0,0.15)',
            'border': '1px solid rgba(0,0,0,0.05)'
        })
    ], id='visualization-controls-container', style={
        'position': 'absolute',
        'top': '80px',
        'left': '20px',
        'width': '350px',
        'maxHeight': '500px',
        'overflowY': 'auto',
        'zIndex': 800,
        'display': 'none',
        'cursor': 'auto'
    }) 