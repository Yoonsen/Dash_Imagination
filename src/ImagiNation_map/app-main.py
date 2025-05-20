"""
ImagiNation - Main application entry point
"""
import dash

from components.layouts import create_layout
from components.callbacks import register_callbacks
from components.timeline_callbacks import register_timeline_callbacks
from components.map_callbacks import register_map_callbacks
from components.heatmap_callbacks import register_heatmap_callbacks
from data.data_layer import DataLayer
from config.settings import DEBUG_MODE, HOST

def create_app():
    """Initialize and configure the Dash application"""
    app = dash.Dash(__name__, suppress_callback_exceptions=True)
    dl = DataLayer()
    
    # Set up application layout
    app.layout = create_layout(dl)
    
    # Register all callbacks
    register_callbacks(app, dl)
    register_timeline_callbacks(app, dl)
    register_map_callbacks(app, dl)
    register_heatmap_callbacks(app, dl)
    
    return app

def main():
    """Main application entry point"""
    app = create_app()
    app.run_server(debug=DEBUG_MODE, host=HOST)

if __name__ == '__main__':
    main()
