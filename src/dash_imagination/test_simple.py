import dash
from dash import html, dcc

print("Starting app initialization...")

app = dash.Dash(__name__)

print("Creating layout...")

app.layout = html.Div([
    html.H1("Hello World"),
    html.P("This is a test paragraph"),
    html.Div("Static content - no callbacks")
])

print("Layout created")

if __name__ == '__main__':
    print("Starting server on port 8050...")
    print("Try accessing: http://localhost:8050")
    app.run_server(debug=True, host='0.0.0.0', port=8050) 