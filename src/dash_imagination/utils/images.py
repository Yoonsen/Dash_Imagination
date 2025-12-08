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


def hydrate_gallery_images(
    images: list[dict] | None,
    *,
    max_items: int = 8,
    max_px: int = 1400
) -> list[dict]:
    """
    Resolve IIIF manifests so the UI can display larger previews.

    Returns a copy of the incoming list with an extra `full` key that points to
    a high-resolution rendition (falls back to the thumbnail when unavailable).
    """
    if not images:
        return []

    hydrated: list[dict] = []
    for image in images[: max(1, max_items)]:
        manifest_url = image.get("manifest")
        full_src = resolve_iiif_image(manifest_url, max_px=max_px) if manifest_url else None
        hydrated.append(
            {
                **image,
                "full": full_src or image.get("thumbnail"),
            }
        )
    return hydrated


def resolve_iiif_image(manifest_url: str | None, *, max_px: int = 1400) -> str | None:
    """
    Best-effort fetch of a single high-resolution image URL from a IIIF manifest.
    Supports both Presentation v2 (`sequences`) and v3 (`items`).
    """
    if not manifest_url:
        return None
    try:
        response = requests.get(manifest_url, timeout=6)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("Unable to load IIIF manifest %s: %s", manifest_url, exc)
        return None

    if not isinstance(data, dict):
        return None

    # IIIF Presentation v3
    items = data.get("items")
    if isinstance(items, list):
        for canvas in items:
            url = _extract_from_canvas_v3(canvas, max_px)
            if url:
                return url

    # IIIF Presentation v2
    sequences = data.get("sequences")
    if isinstance(sequences, list):
        for sequence in sequences:
            canvases = sequence.get("canvases", [])
            for canvas in canvases:
                url = _extract_from_canvas_v2(canvas, max_px)
                if url:
                    return url

    return None


def _extract_from_canvas_v3(canvas: dict, max_px: int) -> str | None:
    if not isinstance(canvas, dict):
        return None
    annotation_pages = canvas.get("items", [])
    for page in annotation_pages:
        items = page.get("items", [])
        for annotation in items:
            body = annotation.get("body")
            if isinstance(body, list):
                for candidate in body:
                    url = _build_fullsize_from_body(candidate, max_px)
                    if url:
                        return url
            else:
                url = _build_fullsize_from_body(body, max_px)
                if url:
                    return url
    return None


def _build_fullsize_from_body(body: dict | None, max_px: int) -> str | None:
    if not isinstance(body, dict):
        return None
    image_id = body.get("id") or body.get("@id")
    service = body.get("service")
    return _compose_iiif_url(image_id, service, max_px)


def _extract_from_canvas_v2(canvas: dict, max_px: int) -> str | None:
    if not isinstance(canvas, dict):
        return None
    images = canvas.get("images", [])
    for image in images:
        resource = image.get("resource")
        url = _build_fullsize_from_resource(resource, max_px)
        if url:
            return url
    return None


def _build_fullsize_from_resource(resource: dict | None, max_px: int) -> str | None:
    if not isinstance(resource, dict):
        return None
    image_id = resource.get("@id") or resource.get("id")
    service = resource.get("service")
    return _compose_iiif_url(image_id, service, max_px)


def _compose_iiif_url(image_id: str | None, service: dict | str | None, max_px: int) -> str | None:
    service_id = None
    if isinstance(service, list) and service:
        service = service[0]
    if isinstance(service, dict):
        service_id = service.get("id") or service.get("@id")
    elif isinstance(service, str):
        service_id = service

    if service_id:
        base = service_id.rstrip("/")
        return f"{base}/full/!{max_px},{max_px}/0/default.jpg"

    return image_id


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

