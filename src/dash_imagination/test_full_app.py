import dash
from dash import html, dcc, Output, Input
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
import os

# Initialize the app with our standard setup
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
    ],
    suppress_callback_exceptions=True
)

# Create a simple layout with our key components
app.layout = html.Div([
    html.H1("Test App", className="text-center my-4"),
    
    # Test Bootstrap components
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Test Card"),
                dbc.CardBody("This is a test card using Bootstrap")
            ])
        ], width=6)
    ], className="mb-4"),
    
    # Test Mapbox
    dcc.Graph(
        id='test-map',
        style={'height': '50vh'},
        figure=go.Figure(
            data=[
                go.Scattermap(
                    lat=[60.5],
                    lon=[9.0],
                    mode='markers',
                    marker=dict(size=10, color='red'),
                    text=['Test Point']
                )
            ],
            layout=dict(
                mapbox=dict(
                    style='open-street-map',
                    center=dict(lat=60.5, lon=9.0),
                    zoom=4
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                showlegend=False
            )
        )
    ),
    
    # Test Store components
    dcc.Store(id='test-store', data={'test': 'data'}),
    
    # Test Loading component
    dcc.Loading(
        id="loading-1",
        type="default",
        children=html.Div(id="loading-output")
    )
])

# Add a simple callback
@app.callback(
    Output("loading-output", "children"),
    Input("test-store", "data")
)
def update_output(data):
    return f"Store data: {data}"

if __name__ == '__main__':
    print("Starting test app...")
    app.run_server(debug=True, host='0.0.0.0', port=8065) 