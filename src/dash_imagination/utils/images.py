import logging
from xml.etree import ElementTree as ET

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NB_API_BASE = "https://api.nb.no/catalog/v1/search"
GALLICA_SRU_URL = "https://gallica.bnf.fr/SRU"


def fetch_historical_images(
    search_term: str, limit: int = 5, include_gallica: bool = True
) -> list[dict]:
    """
    Fetch historical images for a place/author.

    The `limit` argument represents how many images we request **per source** so the
    gallery can blend local NB.no material with international Gallica items.
    """
    if not search_term or limit <= 0:
        return []

    images: list[dict] = []

    per_source_limit = max(1, limit)

    try:
        images.extend(_fetch_nb_images(search_term, per_source_limit))
    except Exception as exc:
        logger.error("NB fetch failed: %s", exc)

    if include_gallica:
        try:
            images.extend(fetch_gallica_images(search_term, per_source_limit))
        except Exception as exc:
            logger.error("Gallica fetch failed: %s", exc)

    return images


def _fetch_nb_images(search_term: str, limit: int) -> list[dict]:
    params = {
        "q": search_term,
        "mediaTypeOrder": "bilder",
        "mediaTypeSize": 1,
        "filter": "mediatype:bilder",
        "searchType": "FULL_TEXT_SEARCH",
        "sort": "date",
        "sortOrder": "asc",
        "size": limit,
        "profile": "wwwnbno",
    }

    response = requests.get(NB_API_BASE, params=params, timeout=5)
    response.raise_for_status()
    data = response.json()

    media_results = data.get("_embedded", {}).get("mediaTypeResults", [])
    if not media_results:
        return []

    result_items = (
        media_results[0]
        .get("result", {})
        .get("_embedded", {})
        .get("items", [])
    )

    images = []
    for item in result_items:
        try:
            metadata = item.get("metadata", {})
            links = item.get("_links", {})

            title = metadata.get("title", "")
            date = metadata.get("dateCreated", "")
            thumb_url = links.get("thumbnail_medium", {}).get("href")
            iiif_manifest = links.get("presentation", {}).get("href")
            urn = metadata.get("identifiers", {}).get("urn")

            view_url = f"https://www.nb.no/items/{urn}" if urn else "#"

            if thumb_url:
                images.append(
                    {
                        "title": title,
                        "date": date,
                        "thumbnail": thumb_url,
                        "manifest": iiif_manifest,
                        "view_url": view_url,
                        "urn": urn,
                        "source": "NB.no",
                    }
                )
        except Exception as exc:
            logger.warning("Error parsing NB item: %s", exc)
            continue

    return images


def fetch_gallica_images(search_term: str, limit: int = 5) -> list[dict]:
    """
    Query Gallica's SRU endpoint for image material and turn it into a unified
    image payload compatible with the rest of the UI.
    """
    if not search_term or limit <= 0:
        return []

    safe_term = search_term.replace('"', " ")
    cql_query = f'dc.type all "image" and gallica all "{safe_term}"'
    params = {
        "operation": "searchRetrieve",
        "version": "1.2",
        "query": cql_query,
        "startRecord": 1,
        "maximumRecords": max(10, limit * 2),
        "lang": "en",
    }

    response = requests.get(GALLICA_SRU_URL, params=params, timeout=6)
    response.raise_for_status()

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        logger.error("Unable to parse Gallica response: %s", exc)
        return []

    ns = {
        "srw": "http://www.loc.gov/zing/srw/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    images: list[dict] = []
    for record in root.findall(".//srw:records/srw:record", ns):
        metadata = record.find(".//oai_dc:dc", ns)
        if metadata is None:
            continue

        title = _first_text(metadata, "dc:title", ns)
        date = _first_text(metadata, "dc:date", ns)
        identifiers = [
            elem.text for elem in metadata.findall("dc:identifier", ns) if elem.text
        ]
        ark_url = next((ident for ident in identifiers if "ark:/" in ident), None)
        if not ark_url:
            continue

        manifest_url = _build_gallica_manifest_url(ark_url)
        thumbnail = _first_text(metadata, "thumbnail", ns) or _build_gallica_thumbnail(
            ark_url
        )

        images.append(
            {
                "title": title or "Gallica image",
                "date": date,
                "thumbnail": thumbnail,
                "manifest": manifest_url,
                "view_url": ark_url,
                "source": "Gallica",
            }
        )

        if len(images) >= limit:
            break

    return images


def _first_text(parent, tag: str, ns: dict) -> str | None:
    """
    Retrieve the text for the first matching child element.
    Supports bare tags such as <thumbnail> that are not namespaced.
    """
    if ":" in tag:
        elem = parent.find(tag, ns)
    else:
        # try bare tag first, fall back to wildcard search for namespace variants
        elem = parent.find(tag)
        if elem is None:
            elem = parent.find(f".//{{*}}{tag}")
    return elem.text.strip() if elem is not None and elem.text else None


def _build_gallica_manifest_url(ark_url: str) -> str | None:
    if not ark_url:
        return None
    if "ark:/" not in ark_url:
        return None
    ark_part = ark_url.split("ark:/", 1)[-1]
    return f"https://gallica.bnf.fr/iiif/ark:/{ark_part}/manifest.json"


def _build_gallica_thumbnail(ark_url: str) -> str | None:
    if not ark_url:
        return None
    if ark_url.endswith(".thumbnail"):
        return ark_url
    return f"{ark_url}.thumbnail"

