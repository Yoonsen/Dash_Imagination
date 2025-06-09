# ImagiNation App Development Manifest

## Current State
The app is a Google Maps-inspired interface with floating, interactive elements designed to work on both desktop and mobile. The main components are:
- Map as the central element
- Floating popup menus activated by clicking
- Information displayed in floating windows that can be closed
- Current layout includes:
  - Sidebar toggle (top left)
  - Category selection (top left)
  - Places button (top left)
  - View toggle (Map/Heatmap) and clustering options (top right)
  - Info button (bottom left)

## Data Structure and Information Flow

### Database Structure
- SQLite database with three main tables:
  - Books table (22,000 entries)
  - Places table (90,000 entries)
  - Books-Places relationship table

### Core Functionality
1. Corpus Building and Visualization
   - Users can build corpus using book metadata
   - Places from selected corpus are plotted on map
   - External corpus can be loaded into the app

2. Interactive Features
   - Click on place to see related books
   - Click on book to access National Library online
   - View all places within selected corpus
   - Place highlighting functionality (to be implemented)

3. Advanced Analysis (Future)
   - Concordance functionality for place-disease relationships
   - Corpus building based on specific themes (e.g., diseases like cholera, typhus)
   - Collocation and vicinity searches

### System Integration
The app connects three main components:
1. Main Application
   - Handles corpus management
   - Displays map and place information
   - Manages user interactions

2. National Library Online
   - Provides book viewing functionality
   - Uses URNs for direct linking

3. DHLab Integration
   - Provides advanced text analysis tools
   - Concordance functionality
   - Collocation analysis
   - Vicinity searches

All components are connected through consistent identifiers (URNs) that work across servers.

## Mobile Optimization Plans

### 1. Responsive Button Sizing
- [ ] Increase button sizes for better touch targets on mobile
- [ ] Adjust spacing between buttons for mobile screens
- [ ] Implement responsive padding and margins

### 2. Modal Improvements
- [ ] Make modals full-screen on mobile
- [ ] Add swipe-to-dismiss functionality
- [ ] Ensure modal content is scrollable
- [ ] Optimize modal content layout for mobile

### 3. Floating Elements
- [ ] Adjust positioning for different screen sizes
- [ ] Consider bottom sheet for mobile instead of side panels
- [ ] Prevent element overlap on small screens
- [ ] Implement responsive positioning

### 4. Map Controls
- [ ] Make map controls more touch-friendly
- [ ] Ensure zoom controls are easily accessible on mobile
- [ ] Optimize touch interactions for map markers

## Current Focus
- [ ] Ensure popups work correctly on all devices
- [ ] Align top layer elements properly on mobile
- [ ] Test and fix any mobile-specific issues

## Future Considerations
- Performance optimization for mobile devices
- Offline functionality
- Progressive Web App (PWA) features
- Accessibility improvements
- User feedback and analytics

## Notes
- The app evolved from a Streamlit application
- Inspired by Google Maps interface
- Uses Dash and Bootstrap for UI components
- Database-driven with SQLite backend 