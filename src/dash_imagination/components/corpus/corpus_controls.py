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
                dcc.Input(
                    id='popup-sample-size',
                    type='number',
                    value=1000,
                    min=100,
                    max=10000,
                    step=100,
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                )
            ], className="mb-4"),
            
            # Max Places
            html.Div([
                html.Label("Number of Places", className="block text-sm font-medium text-gray-700"),
                dcc.Slider(
                    id='popup-max-places-slider',
                    min=100,
                    max=1600,
                    step=100,
                    value=1500,
                    marks={i: str(i) for i in range(100, 1601, 300)},
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
            
            # View type selection
            html.Div([
                html.Label("View Type", style={'fontWeight': '500', 'marginBottom': '5px'}),
                dcc.RadioItems(
                    id='view-toggle',
                    options=[
                        {'label': 'Points', 'value': 'points'},
                        {'label': 'Heatmap', 'value': 'heatmap'}
                    ],
                    value='points',
                    labelStyle={'display': 'inline-block', 'marginRight': '10px'}
                )
            ], className="mb-4"),
            
            # Marker size control
            html.Div([
                html.Label("Marker Size", style={'fontWeight': '500', 'marginBottom': '5px'}),
                dcc.Slider(
                    id='marker-size-slider',
                    min=1,
                    max=20,
                    step=1,
                    value=8,  # Reduced default size
                    marks={i: str(i) for i in range(1, 21, 2)},
                    tooltip={"placement": "bottom", "always_visible": True}
                ),
                html.Div(style={'height': '10px'}),  # Add some spacing
                
                # Cluster marker size control
                html.Label("Cluster Size", style={'fontWeight': '500', 'marginBottom': '5px'}),
                dcc.Slider(
                    id='cluster-size-slider',
                    min=1,
                    max=10,
                    step=1,
                    value=3,  # Smaller default size for clusters
                    marks={i: str(i) for i in range(1, 11)},
                    tooltip={"placement": "bottom", "always_visible": True}
                ),
                html.Div(style={'height': '10px'}),  # Add some spacing
                
                # Heatmap controls
                html.Div([
                    html.Label("Heatmap Intensity", style={'fontWeight': '500', 'marginBottom': '5px'}),
                    dcc.Slider(
                        id='heatmap-intensity',
                        min=1,
                        max=10,
                        step=1,
                        value=5,
                        marks={i: str(i) for i in range(1, 11)},
                        tooltip={"placement": "bottom", "always_visible": True}
                    ),
                    html.Div(style={'height': '10px'}),
                    
                    html.Label("Heatmap Radius", style={'fontWeight': '500', 'marginBottom': '5px'}),
                    dcc.Slider(
                        id='heatmap-radius',
                        min=1,
                        max=10,
                        step=1,
                        value=5,
                        marks={i: str(i) for i in range(1, 11)},
                        tooltip={"placement": "bottom", "always_visible": True}
                    )
                ], id='heatmap-settings', style={'display': 'none'})
            ])
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
        'zIndex': 800,
        'display': 'none'
    }) 