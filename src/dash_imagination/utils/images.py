import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NB_API_BASE = "https://api.nb.no/catalog/v1/search"

def fetch_historical_images(search_term: str, limit: int = 5) -> list[dict]:
    """
    Fetch historical images from NB.no API based on a search term.
    Prioritizes oldest images first.
    """
    if not search_term:
        return []

    params = {
        "q": search_term,
        "mediaTypeOrder": "bilder",
        "mediaTypeSize": 1,
        "filter": "mediatype:bilder",
        "searchType": "FULL_TEXT_SEARCH",
        "sort": "date",
        "sortOrder": "asc",
        "size": limit,
        "profile": "wwwnbno"
    }

    try:
        response = requests.get(NB_API_BASE, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("_embedded", {}).get("mediaTypeResults", [])[0].get("result", {}).get("_embedded", {}).get("items", [])
        
        images = []
        for item in items:
            try:
                metadata = item.get("metadata", {})
                links = item.get("_links", {})
                
                title = metadata.get("title", "")
                date = metadata.get("dateCreated", "")
                thumb_url = links.get("thumbnail_medium", {}).get("href")
                iiif_manifest = links.get("presentation", {}).get("href")
                urn = item.get("metadata", {}).get("identifiers", {}).get("urn")
                
                # Construct a direct view link if URN exists
                view_url = f"https://www.nb.no/items/{urn}" if urn else "#"

                if thumb_url:
                    images.append({
                        "title": title,
                        "date": date,
                        "thumbnail": thumb_url,
                        "manifest": iiif_manifest,
                        "view_url": view_url,
                        "urn": urn
                    })
            except Exception as e:
                logger.warning(f"Error parsing image item: {e}")
                continue
                
        return images

    except Exception as e:
        logger.error(f"Error fetching images from NB API: {e}")
        return []

