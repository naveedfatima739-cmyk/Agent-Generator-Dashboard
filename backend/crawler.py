"""
crawler.py — UniBot-compliant web crawler
FINAL FIXED VERSION
Creates:
datasets/
    site-bundle/
        manifest.json
        sources.json
        records.jsonl
        documents/
"""

import os
import re
import json
import hashlib
import threading
import warnings
from datetime import datetime
from urllib.parse import (
    urlparse,
    urljoin,
    unquote,
)

from collections import deque
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)

import requests
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

THREADS = 15
REQUEST_TIMEOUT = 20
MAX_RETRIES = 1

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Connection": "keep-alive",
}

SKIP_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".ico",
    ".css",
    ".js",
    ".xml",
    ".txt",
    ".csv",
    ".zip",
    ".rar",
    ".mp3",
    ".mp4",
    ".woff",
    ".woff2",
    ".ttf",
)

DOCUMENT_EXTENSIONS = (
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def normalize_url(url: str) -> str:
    url = url.split("#")[0]

    parsed = urlparse(url)

    clean = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query="",
        fragment=""
    ).geturl()

    return clean.rstrip("/")


def content_hash(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:12]


def slugify(url: str) -> str:
    parsed = urlparse(url)

    raw = (
        parsed.netloc +
        parsed.path.replace("/", "-")
    ).lower()

    return re.sub(
        r"[^a-z0-9-]",
        "",
        raw
    ).strip("-")


def sanitise_filename(filename: str) -> str:
    filename = unquote(filename)

    name, ext = os.path.splitext(filename)

    name = re.sub(
        r"[^A-Za-z0-9._-]",
        "-",
        name
    )

    name = re.sub(r"-{2,}", "-", name)

    name = name.strip("-")

    if not name:
        name = "document"

    return f"{name}{ext.lower()}"


def section_id_from_url(
    url: str,
    heading: str = ""
) -> str:

    path = (
        urlparse(url)
        .path
        .strip("/")
        .replace("/", "-")
    )

    if heading:
        heading = re.sub(
            r"[^a-z0-9]+",
            "-",
            heading.lower()
        ).strip("-")

        return f"{path}--{heading}"

    return path or slugify(url)


def is_document_url(url: str) -> bool:
    clean = url.lower().split("?")[0]

    return any(
        clean.endswith(ext)
        for ext in DOCUMENT_EXTENSIONS
    )


def ensure_documents_folder(bundle_dir: str):

    documents_dir = os.path.join(
        bundle_dir,
        "documents"
    )

    os.makedirs(
        documents_dir,
        exist_ok=True
    )

    return documents_dir


# ─────────────────────────────────────────────
# URL CLASSIFICATION
# ─────────────────────────────────────────────

URL_CLASSIFICATION_RULES = [
    (r"merit", "merit_list"),
    (r"admission|apply", "admissions_cycle"),
    (r"fee|tuition", "program_fee_schedule"),
    (r"scholarship", "scholarship"),
    (r"faculty|staff|teacher", "faculty_profile"),
    (r"policy|regulation", "policy_rule"),
    (r"news|event", "news_event"),
    (r"department|office", "org_unit"),
    (r"program|degree", "program"),
]


def classify_url(url: str):

    path = urlparse(url).path.lower()

    for pattern, record_type in URL_CLASSIFICATION_RULES:

        if re.search(pattern, path):
            return record_type

    return "general"


# ─────────────────────────────────────────────
# HTML EXTRACTION
# ─────────────────────────────────────────────

def clean_soup(soup):

    for tag in soup.find_all([
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "noscript",
        "iframe",
        "meta",
        "link",
        "aside",
    ]):
        tag.decompose()

    return soup


def extract_main_text(soup):
    lines = []
    seen = set()

    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'noscript', 'iframe', 'meta', 'link', 'aside']):
        tag.decompose()

    body = soup.find("body")
    if body:
        all_text_elements = body.find_all(['p', 'li', 'td', 'tr', 'th',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'span', 'div', 'article', 'section', 'blockquote'])
        
        for el in all_text_elements:
            text = el.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            
            if len(text) > 20 and text not in seen:
                lines.append(text)
                seen.add(text)

    table_content = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if cells:
                row_text = " | ".join(cell.get_text(strip=True) for cell in cells)
                if len(row_text) > 5:
                    table_content.append(row_text)
    
    if table_content:
        lines.append("\n[TABLE DATA]")
        lines.extend(table_content)
        lines.append("[END TABLE]")

    for dl in soup.find_all("dl"):
        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            term = dt.get_text(strip=True)
            definition = dd.get_text(strip=True)
            if term and definition:
                lines.append(f"{term}: {definition}")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# RECORD BUILDERS
# ─────────────────────────────────────────────

def envelope(
    record_id,
    record_type,
    url,
    title,
    payload
):

    return {
        "record_id": record_id,
        "record_type": record_type,
        "source_url": url,
        "source_section_id": section_id_from_url(url),
        "source_section_label": title,
        "source_locator": "body",
        "source_authority_tier": 2,
        "conflict_scope_id": record_id,
        "dedupe_key": f"{record_type}:{content_hash(url)}",
        "cycle_label": None,
        "year_confidence": "unknown",
        "record_payload": payload,
    }


def build_general(
    url,
    title,
    content
):

    record_type = classify_url(url)

    return [
        envelope(
            f"{record_type}:{content_hash(url)}",
            record_type,
            url,
            title,
            {
                "title": title,
                "content": content
            }
        )
    ]


def build_document_asset(
    url: str,
    parent_url: str = None
):

    normalized_url = normalize_url(url)

    parsed = urlparse(normalized_url)

    raw_filename = os.path.basename(
        parsed.path
    )

    if not raw_filename:
        raw_filename = (
            f"document-"
            f"{content_hash(url)}.pdf"
        )

    filename = sanitise_filename(
        raw_filename
    )

    ext = os.path.splitext(
        filename
    )[1].lower()

    kind_map = {
        ".pdf": "pdf",
        ".docx": "word_document",
        ".xlsx": "spreadsheet",
        ".pptx": "presentation",
    }

    mime_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }

    doc_hash = content_hash(
        normalized_url
    )

    payload = {
        "document_url": normalized_url,
        "parent_page_url": parent_url,
        "filename": filename,
        "local_path": f"documents/{filename}",
        "page_count": 0,
        "media_type": mime_map.get(
            ext,
            "application/octet-stream"
        ),
        "document_kind": kind_map.get(
            ext,
            "unknown"
        ),
        "parser_backend": "not_parsed",
        "parser_metadata": {},
    }

    return [{
        "record_id": f"document_asset:{doc_hash}",
        "record_type": "document_asset",
        "source_url": normalized_url,
        "source_section_id": section_id_from_url(
            normalized_url
        ),
        "source_section_label": filename,
        "source_locator": f"document://{filename}",
        "source_authority_tier": 2,
        "conflict_scope_id": f"document_asset:{doc_hash}",
        "dedupe_key": f"document_asset:{doc_hash}",
        "cycle_label": None,
        "year_confidence": "unknown",
        "record_payload": payload,
    }]


# ─────────────────────────────────────────────
# FETCH
# ─────────────────────────────────────────────

def fetch_page(url):

    # DOCUMENT
    if is_document_url(url):

        try:
            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers=HEADERS,
                verify=False,
                stream=True,
                allow_redirects=True
            )

            if response.status_code < 400:
                return url, None, True

        except Exception:
            pass

        return url, None, False

    # HTML
    for _ in range(MAX_RETRIES + 1):

        try:
            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers=HEADERS,
                verify=False,
                allow_redirects=True
            )

            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type",
                ""
            ).lower()

            if "text/html" not in content_type:
                return url, None, False

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            return url, soup, False

        except Exception:
            pass

    return url, None, False


# ─────────────────────────────────────────────
# LINKS
# ─────────────────────────────────────────────

def get_links(
    soup,
    base_url,
    base_domain
):

    links = {}

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a["href"].strip()

        if (
            href.startswith("#")
            or href.startswith("mailto:")
            or href.startswith("javascript:")
        ):
            continue

        full_url = normalize_url(
            urljoin(base_url, href)
        )

        parsed = urlparse(full_url)

        if parsed.netloc != base_domain:
            continue

        if any(
            full_url.lower().endswith(ext)
            for ext in SKIP_EXTENSIONS
        ):
            continue

        links[full_url] = (
            a.get_text(strip=True)
            or None
        )

    return list(links.items())


# ─────────────────────────────────────────────
# SOURCE ENTRY
# ─────────────────────────────────────────────

def build_source_entry(
    url,
    record_type
):

    return {
        "source_url": url,
        "canonical_url": normalize_url(url),
        "source_class": record_type,
        "crawl_method": "html_static",
        "legal_status": "allowed",
        "crawl_status": "verified_live",
        "default_authority_tier": 2,
        "refresh_policy": "weekly",
        "parser_target": (
            "document"
            if is_document_url(url)
            else "html"
        ),
        "parent_source_url": None,
        "link_text": None,
        "is_active": True,
        "last_crawled_at": None,
        "last_successful_crawl_at": None,
    }


# ─────────────────────────────────────────────
# CRAWLER
# ─────────────────────────────────────────────

def crawl_entire_website(start_url):

    parsed = urlparse(start_url)

    base_domain = parsed.netloc

    start_url = normalize_url(start_url)

    queue = deque([start_url])

    visited = set()

    queued = {start_url}

    all_records = []

    all_sources = {}

    doc_parents = {}

    lock = threading.Lock()

    page_count = 0

    print(f"\n[START] {start_url}\n")

    while queue:

        batch = []

        while queue and len(batch) < THREADS:

            url = queue.popleft()

            if url not in visited:
                visited.add(url)
                batch.append(url)

        print(f"[BATCH] {len(batch)}")

        with ThreadPoolExecutor(
            max_workers=THREADS
        ) as executor:

            futures = {
                executor.submit(
                    fetch_page,
                    url
                ): url
                for url in batch
            }

            for future in as_completed(futures):

                url, soup, is_doc = future.result()

                # DOCUMENT
                if is_doc:

                    parent = doc_parents.get(url)

                    records = build_document_asset(
                        url,
                        parent
                    )

                    with lock:

                        all_records.extend(
                            records
                        )

                        all_sources[url] = (
                            build_source_entry(
                                url,
                                "document_asset"
                            )
                        )

                        print(
                            f"📄 DOCUMENT FOUND: {url}"
                        )

                    continue

                if soup is None:
                    continue

                clean_soup(soup)

                title = (
                    soup.title.string.strip()
                    if soup.title
                    else url
                )

                content = extract_main_text(
                    soup
                )

                records = build_general(
                    url,
                    title,
                    content
                )

                with lock:

                    all_records.extend(
                        records
                    )

                    record_type = classify_url(
                        url
                    )

                    all_sources[url] = (
                        build_source_entry(
                            url,
                            record_type
                        )
                    )

                    page_count += 1

                    print(
                        f"✓ {page_count} "
                        f"{title[:60]}"
                    )

                links = get_links(
                    soup,
                    url,
                    base_domain
                )

                with lock:

                    for (
                        link_url,
                        link_text
                    ) in links:

                        if is_document_url(
                            link_url
                        ):
                            doc_parents[
                                link_url
                            ] = url

                        if (
                            link_url not in visited
                            and link_url not in queued
                        ):

                            queue.append(
                                link_url
                            )

                            queued.add(
                                link_url
                            )

    print(
        f"\n[DONE] "
        f"{page_count} pages crawled\n"
    )

    return {
        "total_pages": page_count,
        "records": all_records,
        "sources": list(
            all_sources.values()
        ),
    }


# ─────────────────────────────────────────────
# DOCUMENT DOWNLOADER
# ─────────────────────────────────────────────

def _download_document(
    doc_url,
    dest_path
):

    try:

        response = requests.get(
            doc_url,
            timeout=60,
            headers=HEADERS,
            verify=False,
            stream=True,
            allow_redirects=True
        )

        response.raise_for_status()

        with open(dest_path, "wb") as f:

            for chunk in response.iter_content(
                65536
            ):
                if chunk:
                    f.write(chunk)

        # empty/corrupt file
        if os.path.getsize(dest_path) < 500:

            os.remove(dest_path)

            return False

        return True

    except Exception as e:

        print(
            f"✗ download failed "
            f"{doc_url}"
        )

        print(e)

        return False


def _populate_documents_folder(
    records,
    documents_dir
):

    os.makedirs(
        documents_dir,
        exist_ok=True
    )

    written = 0

    used_names = set()

    print(
        "\n[DOWNLOADING DOCUMENTS]\n"
    )

    for record in records:

        if (
            record.get("record_type")
            != "document_asset"
        ):
            continue

        payload = record.get(
            "record_payload",
            {}
        )

        doc_url = payload.get(
            "document_url"
        )

        filename = payload.get(
            "filename"
        )

        if not doc_url or not filename:
            continue

        filename = sanitise_filename(
            filename
        )

        base, ext = os.path.splitext(
            filename
        )

        unique = filename

        counter = 1

        while unique in used_names:

            unique = (
                f"{base}-{counter}{ext}"
            )

            counter += 1

        used_names.add(unique)

        payload["filename"] = unique

        payload["local_path"] = (
            f"documents/{unique}"
        )

        destination = os.path.join(
            documents_dir,
            unique
        )

        print(
            f"↓ downloading {unique}"
        )

        success = _download_document(
            doc_url,
            destination
        )

        if success:

            written += 1

            print(
                f"✓ saved {unique}"
            )

        else:

            print(
                f"✗ failed {unique}"
            )

    print(
        f"\n[DOCUMENTS SAVED] {written}\n"
    )

    return written


# ─────────────────────────────────────────────
# SAVE DATASET
# ─────────────────────────────────────────────

def _domain_slug(url):

    netloc = (
        urlparse(url)
        .netloc
        .lower()
    )

    netloc = re.sub(
        r"^www\.",
        "",
        netloc
    )

    return re.sub(
        r"[^a-z0-9]+",
        "-",
        netloc
    ).strip("-")


def save_dataset(
    agent_id,
    url,
    prompt,
    description=""
):

    # ABSOLUTE PATH FIX
    base_dir = os.path.abspath(
        os.path.dirname(__file__)
    )

    datasets_dir = os.path.abspath(
        os.path.join(
            base_dir,
            "datasets"
        )
    )

    os.makedirs(
        datasets_dir,
        exist_ok=True
    )

    print(
        f"\nDATASETS DIR:\n"
        f"{datasets_dir}\n"
    )

    crawled = crawl_entire_website(
        url
    )

    site_slug = _domain_slug(url)

    bundle_dir = os.path.abspath(
        os.path.join(
            datasets_dir,
            f"{site_slug}-bundle"
        )
    )

    os.makedirs(
        bundle_dir,
        exist_ok=True
    )

    print(
        f"\nBUNDLE DIR:\n"
        f"{bundle_dir}\n"
    )

    # CREATE DOCUMENTS FOLDER
    documents_dir = ensure_documents_folder(
        bundle_dir
    )

    print(
        f"DOCUMENTS DIR:\n"
        f"{documents_dir}\n"
    )

    # DOWNLOAD DOCUMENTS
    doc_count = _populate_documents_folder(
        crawled["records"],
        documents_dir
    )

    dataset = {
        "agent_id": agent_id,
        "site_slug": site_slug,
        "description": description,
        "sources": crawled["sources"],
        "records": crawled["records"],
        "total_pages_crawled": crawled["total_pages"],
        "created_at": datetime.now().isoformat(),
    }

    json_path = os.path.join(
        bundle_dir,
        f"{agent_id}.json"
    )

    with open(
        json_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            dataset,
            f,
            indent=2,
            ensure_ascii=False
        )

    with open(
        os.path.join(
            bundle_dir,
            "sources.json"
        ),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            crawled["sources"],
            f,
            indent=2,
            ensure_ascii=False
        )

    with open(
        os.path.join(
            bundle_dir,
            "records.jsonl"
        ),
        "w",
        encoding="utf-8"
    ) as f:

        for record in crawled["records"]:

            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False
                ) + "\n"
            )

    manifest = {
        "partner_id": site_slug,
        "partner_display_name": (
            description
            or site_slug
        ),
        "submission_cycle_label": (
            f"cycle-"
            f"{datetime.now().strftime('%Y-%m')}"
        ),
        "schema_version": "1.0",
        "generated_at": (
            datetime.now().isoformat() + "Z"
        ),
        "counts": {
            "sources": len(
                crawled["sources"]
            ),
            "records": len(
                crawled["records"]
            ),
            "documents": doc_count,
        }
    }

    with open(
        os.path.join(
            bundle_dir,
            "manifest.json"
        ),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            manifest,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\n[SAVED SUCCESSFULLY]\n")

    print(bundle_dir)

    return json_path