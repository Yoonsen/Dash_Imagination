from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State

def create_corpus_controls(categories_list=None, titles_list=None, default_filters=None):
    if categories_list is None:
        categories_list = []
    if titles_list is None:
        titles_list = []
    if default_filters is None:
        default_filters = {'categories': [], 'titles': []}

    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Corpus Controls")),
        dbc.ModalBody([
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
            
            # Reset button
            dbc.Button(
                [
                    html.I(className="fas fa-undo mr-2"),
                    "Reset to Default"
                ],
                id='popup-reset-corpus',
                color="secondary",
                className="w-100"
            ),
            
            html.Hr(),
            
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
            ])
        ]),
        dbc.ModalFooter(
            dbc.Button("Close", id="close-corpus-modal", className="ml-auto")
        )
    ], id='corpus-controls-modal', size="lg") 