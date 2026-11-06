"""
DGT CDD Downloader: download data from the DGT CDD Portal (https://cdd.dgterritorio.gov.pt).

Command line:

    python3 dgtcd_downer.py --bbox "-9.2 38.7 -9.1 38.8" --username me@mail.pt -c LAZ,MDT-50cm
    python3 dgtcd_downer.py -i

Python or Jupyter notebook:

    from dgtcd_downer import download

    result = download(
        bbox=[-9.2, 38.7, -9.1, 38.8],
        username="me@mail.pt",
        collections=["LAZ", "MDT-50cm"],
    )
"""

import math
import requests
import os
import time
import sys
import argparse
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from getpass import getpass
from html.parser import HTMLParser

BANNER = r"""
     .---.
     |   |         ____   ____ _____    ____ ____  ____
  ___|   |___     |  _ \ / ___|_   _|  / ___|  _ \|  _ \
  \         /     | | | | |  _  | |   | |   | | | | | | |
   \       /      | |_| | |_| | | |   | |___| |_| | |_| |
|   \     /   |   |____/ \____| |_|    \____|____/|____/
|    \___/    |
|_____________|        D  O  W  N  L  O  A  D  E  R
"""
BANNER_COLOR = "\033[38;2;64;165;230m"  # #40A5E6
RESET_COLOR = "\033[0m"

STAC_URL = "https://cdd.dgterritorio.gov.pt/dgt-be/v1/search"
AUTH_BASE_URL = "https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/protocol/openid-connect"
AUTH_SITE = "https://auth.cdd.dgterritorio.gov.pt"
REDIRECT_URI = "https://cdd.dgterritorio.gov.pt/auth/callback"
CLIENT_ID = "aai-oidc-dgt"
MAIN_SITE = "https://cdd.dgterritorio.gov.pt"

LIDAR_COLLECTIONS = ["LAZ", "MDS-2m", "MDS-50cm", "MDT-2m", "MDT-50cm"]
ORTOS_COLLECTIONS = [
    "ORTOS-2025", "ORTOS-2021", "ORTOS-2018", "ORTOS-2015", "ORTOS-2012",
    "ORTOS-2010", "ORTOS-2007", "ORTOS-2004", "ORTOS-1995",
]
AZORES_COLLECTIONS = [
    "ACORES-LAZ", "ACORES-MDE-1", "ACORES-MDE-5", "ACORES-MDE-10",
    "ACORES-MDS-1", "ACORES-MDS-5", "ACORES-MDS-10",
]
COLLECTIONS = LIDAR_COLLECTIONS + ORTOS_COLLECTIONS + AZORES_COLLECTIONS

MAX_WORKERS = 2
DOWNLOAD_BATCH_SIZE = 10  # Files handed to the workers at a time. The session is checked between batches.
MAX_SEARCH_SPLITS = 3  # How many times an area the portal cannot search is cut into quarters

SESSION_TIMEOUT = 25 * 60  # 25 minutes in seconds

# Global state for session management
auth_state = {
    "session": None,
    "username": None,
    "password": None,
    "last_auth_time": 0,
}

# Tells running downloads to stop, for Ctrl+C or a notebook's "Interrupt kernel"
stop_downloads = threading.Event()

class AuthenticationError(Exception):
    """Custom exception for authentication errors."""
    pass

class KeycloakFormParser(HTMLParser):
    """HTML parser to extract form data from Keycloak login page"""
    def __init__(self):
        super().__init__()
        self.form_action = None
        self.form_data = {}
        self.in_form = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'form' and attrs_dict.get('id') == 'kc-form-login':
            self.in_form = True
            self.form_action = attrs_dict.get('action')
        elif tag == 'input' and self.in_form:
            input_name = attrs_dict.get('name')
            input_value = attrs_dict.get('value', '')
            input_type = attrs_dict.get('type', 'text')
            if input_name and input_type == 'hidden':
                self.form_data[input_name] = input_value

    def handle_endtag(self, tag):
        if tag == 'form' and self.in_form:
            self.in_form = False

# Session validation helper functions
def is_session_expired():
    """Check if session has likely expired based on time."""
    return (time.time() - auth_state["last_auth_time"]) > SESSION_TIMEOUT

def is_session_valid():
    """Check if the current session is still valid by making a test API call."""
    try:
        test_payload = {"bbox": [-9.0, 38.0, -8.0, 39.0], "limit": 1}
        response = auth_state["session"].post(STAC_URL, json=test_payload, timeout=15)
        return response.status_code == 200
    except Exception as e:
        print(f"\n[Session validation check failed: {e}]")
        return False

def refresh_session():
    """Log in again if the session has expired. Never call this while files are downloading."""
    if is_session_expired() or not is_session_valid():
        print("\n[Session expired or invalid, re-authenticating...]")
        if not authenticate(auth_state["username"], auth_state["password"]):
            raise AuthenticationError("Re-authentication failed. Aborting.")

# --- Authenticate() to update global state ---
def authenticate(username, password):
    """
    Authenticates with DGT using username and password and updates the global state.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8", "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8", "Connection": "keep-alive"
    }

    try:
        print("Starting authentication process...")
        session = requests.Session()
        session.headers.update(headers)

        # 1: Visit main site to get initial session
        print("Visiting main site...")
        response = session.get(MAIN_SITE, timeout=30)
        response.raise_for_status()
        auth_params = {'client_id': CLIENT_ID, 'response_type': 'code', 'redirect_uri': REDIRECT_URI, 'scope': 'openid profile email'}
        full_auth_url = f"{AUTH_BASE_URL}/auth?" + urllib.parse.urlencode(auth_params)
        print("Getting authentication page...")
        response = session.get(full_auth_url, timeout=30)
        response.raise_for_status()

        # 3: Parse the login form
        parser = KeycloakFormParser()
        parser.feed(response.text)
        if not parser.form_action: raise AuthenticationError("Could not find login form on the authentication page.")
        print("Found login form, submitting credentials...")

        # 4: Submit login form
        login_data = parser.form_data.copy()
        login_data.update({'username': username, 'password': password})
        login_url = parser.form_action if not parser.form_action.startswith('/') else f"{AUTH_SITE}{parser.form_action}"
        login_headers = headers.copy()
        login_headers.update({'Content-Type': 'application/x-www-form-urlencoded', 'Origin': AUTH_SITE, 'Referer': response.url})
        response = session.post(login_url, data=login_data, headers=login_headers, allow_redirects=True, timeout=30)
        response.raise_for_status()
        
        # 5: Check if login was successful by testing the STAC API
        if response.url.startswith(MAIN_SITE):
            print("Successfully redirected to main site. Verifying session...")
            test_response = session.post(STAC_URL, json={"bbox": [-9.0, 38.0, -8.0, 39.0], "limit": 1}, timeout=30)
            if test_response.status_code == 200:
                print("Authentication successful! Session is valid.")
                auth_state.update({"session": session, "username": username, "password": password, "last_auth_time": time.time()})
                return True
            else:
                raise AuthenticationError(f"Authentication test failed. STAC API returned status {test_response.status_code}. Please check credentials.")
        else:
            raise AuthenticationError("Authentication failed. Unexpected redirection URL.")

    except requests.RequestException as e:
        print(f"Network error during authentication: {e}")
        return False
    except AuthenticationError as e:
        print(f"Authentication error: {e}")
        return False

def get_file_extension(mime_type):
    mime_to_extension = {
        "image/tiff": ".tif",
        "application/vnd.laszip": ".laz",
    }
    # Ignore parameters such as "application=geotiff" or "profile=cloud-optimized"
    media_type = (mime_type or "").split(";", 1)[0].strip().lower()
    return mime_to_extension.get(media_type, ".bin")

def divide_bbox(bbox, max_area_km2=200):
    min_lon, min_lat, max_lon, max_lat = bbox
    deg_to_km = 111
    width_km = (max_lon - min_lon) * deg_to_km * math.cos(math.radians((min_lat + max_lat) / 2))
    height_km = (max_lat - min_lat) * deg_to_km
    if width_km * height_km <= max_area_km2: return [bbox]
    splits_x = math.ceil(width_km / math.sqrt(max_area_km2))
    splits_y = math.ceil(height_km / math.sqrt(max_area_km2))

    delta_lon = (max_lon - min_lon) / splits_x
    delta_lat = (max_lat - min_lat) / splits_y

    small_bboxes = []
    for i in range(splits_x):
        for j in range(splits_y):
            small_min_lon = min_lon + i * delta_lon
            small_max_lon = min(small_min_lon + delta_lon, max_lon)
            small_min_lat = min_lat + j * delta_lat
            small_max_lat = min(small_min_lat + delta_lat, max_lat)
            small_bboxes.append([small_min_lon, small_min_lat, small_max_lon, small_max_lat])
    
    return small_bboxes

def split_bbox(bbox):
    """Cut a bounding box into quarters."""
    min_lon, min_lat, max_lon, max_lat = bbox
    mid_lon, mid_lat = (min_lon + max_lon) / 2, (min_lat + max_lat) / 2
    return [
        [min_lon, min_lat, mid_lon, mid_lat], [mid_lon, min_lat, max_lon, mid_lat],
        [min_lon, mid_lat, mid_lon, max_lat], [mid_lon, mid_lat, max_lon, max_lat],
    ]

def post_search(payload):
    """Run one STAC API search, reporting failures as an empty result."""
    try:
        # Use session from global state
        response = auth_state["session"].post(STAC_URL, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Erro na query da API STAC para a bbox {payload.get('bbox')}: {e}")
        return {"features": []}

def search_stac_api(bbox, collections, delay=0.2, splits_left=MAX_SEARCH_SPLITS):
    """
    Search the STAC API for items in a bounding box.

    Two kinds of result need more searches:
    - Responses are capped at `limit` items, so a search can be cut short.
    - Some ACORES-LAZ items make the portal answer with an error object, with HTTP 200.
      That fails the whole search, even for the other collections and the rest of the area.

    Both are handled by searching each collection on its own. A collection that still
    fails is then searched in smaller parts, to keep everything around the bad items.
    """
    print(f"A esperar {delay}s antes de procurar...")
    time.sleep(delay)
    result = post_search({"bbox": bbox, "limit": 1000, "collections": collections})

    failed = "code" in result
    context = result.get("context", {})
    matched = context.get("matched", 0)
    returned = context.get("returned", matched)
    if not failed and matched <= returned:
        return result

    if len(collections) > 1:
        parts = [(bbox, [collection], splits_left) for collection in collections]
    elif not failed:
        print(f"AVISO: {collections[0]}: só foram devolvidos {returned} de {matched} itens.")
        return result
    elif splits_left > 0:
        parts = [(part, collections, splits_left - 1) for part in split_bbox(bbox)]
    else:
        print(f"AVISO: {collections[0]}: o portal não conseguiu pesquisar a área {bbox}, por isso podem faltar ficheiros nessa zona.")
        return {"features": []}

    features = []
    for part_bbox, part_collections, part_splits in parts:
        features.extend(search_stac_api(part_bbox, part_collections, delay, part_splits).get("features", []))
    return {"features": features}

def add_version(item_id, item):
    """Add the item version to its name, as in MDS-50cm-163556-07-2025_v02. Azores items have no version."""
    version = item.get("properties", {}).get("version")
    return f"{item_id}_v{str(version).zfill(2)}" if version else item_id

def collect_urls_per_collection(stac_response, seen_urls):
    """Collect download URLs by collection. `seen_urls` is shared across searches, because
    tiles on the edge of a search area are found twice and two workers must not write the same file."""
    urls_per_collection = {}

    for item in stac_response.get("features", []):
        collection = item.get("collection", "unknown")
        item_id = next((link.get("href").split("/")[-1] for link in item.get("links", []) if link.get("rel") == "self"), item.get("id", "unknown"))
        item_id = add_version(item_id, item)
        for asset in item.get("assets", {}).values():
            url = asset.get("href")

            if url and url not in seen_urls:
                urls_per_collection.setdefault(collection, []).append((url, item_id, get_file_extension(asset.get("type"))))
                seen_urls.add(url)
    
    return urls_per_collection

def download_file(url, item_id, extension, output_dir, delay=5.0, show_progress=True):
    """Download one file. Returns "downloaded", "skipped" or "failed"."""
    if stop_downloads.is_set():
        return "failed"

    filename = f"{item_id}{extension}" if item_id else f"{url.split('/')[-1]}{extension}"
    file_path = os.path.join(output_dir, filename)
    # Only complete files get the final name, so a later run can trust "file exists"
    part_path = f"{file_path}.part"

    if os.path.exists(file_path):
        print(f"Ignorar {filename}: ficheiro já existe")
        return "skipped"

    print(f"A esperar {delay}s antes do download do {filename}...")
    time.sleep(delay)

    max_retries, retry_delay = 3, 5
    retry_count = 0
    while retry_count < max_retries:
        try:
            response = auth_state["session"].get(url, stream=True, timeout=60)
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type.startswith("text/html"):
                raise AuthenticationError(f"Authentication error for {url} (received HTML).")
            response.raise_for_status()

            total = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 8192
            bar_length = 30

            os.makedirs(output_dir, exist_ok=True)
            with open(part_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if stop_downloads.is_set():
                        break
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if show_progress and total > 0:
                            done = int(bar_length * downloaded / total)
                            percent = int(100 * downloaded / total)
                            bar = f"[{'#' * done}{'-' * (bar_length - done)}] {percent}%"
                            sys.stdout.write(f"\rDownloading {filename} {bar}")
                            sys.stdout.flush()

            if show_progress and total > 0:
                sys.stdout.write("\n")

            if stop_downloads.is_set():
                os.remove(part_path)
                return "failed"

            os.replace(part_path, file_path)
            if not show_progress or total == 0:
                print(f"Download do {filename} realizado!")

            return "downloaded"
        
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.exceptions.Timeout) as e:
            if show_progress:
                sys.stdout.write("\n") # Clean up line from progress bar
            retry_count += 1
            if retry_count < max_retries:
                print(f"Erro de rede no download {filename} (tentativa {retry_count}/{max_retries}): {e}")
                print(f"A esperar {retry_delay}s antes de tentar novamente...")
                time.sleep(retry_delay)
                continue
            else:
                print(f"Falha no download {filename} após {max_retries} tentativas: {e}")
                return "failed"
        except Exception as e:
            if show_progress:
                sys.stdout.write("\n") # Clean up line from progress bar
            print(f"Erro no download {url}: {e}")
            return "failed"
    return "failed"

def download_files(files, output_dir, delay, workers, results):
    """Download a list of (url, item_id, extension) with `workers` threads, adding outcomes to `results`."""
    # Progress bars of two files at once would overwrite each other
    show_progress = workers == 1

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for start in range(0, len(files), DOWNLOAD_BATCH_SIZE):
            refresh_session()
            futures = [
                executor.submit(download_file, url, item_id, extension, output_dir, delay, show_progress)
                for url, item_id, extension in files[start:start + DOWNLOAD_BATCH_SIZE]
            ]
            try:
                for future in as_completed(futures):
                    results[future.result()] += 1
                    if not show_progress:
                        print(f"[{start + sum(f.done() for f in futures)}/{len(files)}]")
            except BaseException:
                # Leaving the executor waits for its threads, so tell them to stop first
                stop_downloads.set()
                raise

def run_downloads(bbox, output_dir, delay, collections, workers):
    small_bboxes = divide_bbox(bbox)
    print(f"Bbox dividida em {len(small_bboxes)} pequenas bboxes")

    all_urls_per_collection = {}
    seen_urls = set()
    for i, small_bbox in enumerate(small_bboxes, 1):
        print(f"A processar bbox {i}/{len(small_bboxes)}: {small_bbox}")
        stac_response = search_stac_api(small_bbox, collections, delay)
        urls_per_collection = collect_urls_per_collection(stac_response, seen_urls)
        
        for collection, url_id_ext_pairs in urls_per_collection.items():
            all_urls_per_collection.setdefault(collection, []).extend(url_id_ext_pairs)
        print(f"Encontrados {sum(len(urls) for urls in urls_per_collection.values())} items na bbox {i}")

    total_urls = sum(len(urls) for urls in all_urls_per_collection.values())
    print(f"Total de URLs únicos para download: {total_urls}")
    results = {"downloaded": 0, "skipped": 0, "failed": 0}
    stop_downloads.clear()
    for collection, url_id_ext_pairs in all_urls_per_collection.items():
        print(f"\nDownloading da coleção: {collection}")
        download_files(url_id_ext_pairs, os.path.join(output_dir, collection), delay, workers, results)
    print(f"\nResumo: Download de {results['downloaded']} ficheiros, ignorados {results['skipped']} ficheiros, falhados {results['failed']} ficheiros")
    return results

def parse_bbox(text):
    """Read 'min_lon min_lat max_lon max_lat', separated by spaces or commas."""
    bbox = [float(value) for value in text.replace(",", " ").split()]
    if len(bbox) != 4:
        raise ValueError("Bounding box must have 4 values: min_lon min_lat max_lon max_lat")
    return bbox

def download(bbox, username, collections, password=None, output_dir="./downloaded_files", delay=5.0, workers=1):
    """
    Download the given collections in a bounding box. This is the entry point for
    Python scripts and Jupyter notebooks.

    bbox: [min_lon, min_lat, max_lon, max_lat] in WGS84, as a list or an array such as
          geopandas total_bounds
    username: e-mail or username of the CDD account
    collections: list of collection names, see COLLECTIONS. Required.
    password: asked for when needed if left out, which keeps it out of the notebook
    output_dir: each collection goes to its own folder inside this one
    delay: seconds to wait between requests/downloads, for each worker
    workers: 1 or 2 simultaneous downloads. 2 roughly doubles the requests sent to the portal.

    Returns {"downloaded": n, "skipped": n, "failed": n, "output_dir": path}.
    Raises ValueError for invalid arguments and AuthenticationError if the login fails.
    """
    if isinstance(collections, str):
        collections = collections.split(",")
    collections = [collection.strip() for collection in collections or [] if collection.strip()]
    if not collections:
        raise ValueError(f"Choose at least one collection: {', '.join(COLLECTIONS)}")

    bbox = [float(value) for value in bbox]
    if len(bbox) != 4:
        raise ValueError("Bounding box must have 4 values: min_lon min_lat max_lon max_lat")

    if workers not in range(1, MAX_WORKERS + 1):
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}")

    unknown = [collection for collection in collections if collection not in COLLECTIONS]
    if unknown:
        print(f"AVISO: coleções fora da lista conhecida, a usar na mesma: {', '.join(unknown)}")

    # Reuse a valid session, so a notebook can call this repeatedly without logging in again
    if auth_state["session"] is None or auth_state["username"] != username or is_session_expired():
        if password is None:
            password = getpass("DGT Password: ")
        if not authenticate(username, password):
            raise AuthenticationError("Could not log in to the DGT CDD Portal")

    results = run_downloads(bbox, output_dir, delay, collections, workers)
    return {**results, "output_dir": output_dir}

def print_banner():
    """Print the banner, in colour only on a real terminal, so logs stay free of escape codes."""
    if sys.stdout.isatty() and "NO_COLOR" not in os.environ:
        if os.name == "nt":
            os.system("")  # Turns on ANSI colours in Windows consoles
        print(f"{BANNER_COLOR}{BANNER}{RESET_COLOR}")
    else:
        print(BANNER)

def collection_label(collection):
    region = "Azores" if collection in AZORES_COLLECTIONS else "PT"
    return f"{collection} ({region})"

def choose_collections():
    """Ask for collections until a valid selection is given."""
    print("\nColeções disponíveis:")
    for i, name in enumerate(COLLECTIONS, 1):
        print(f"  {i}. {collection_label(name)}")

    while True:
        selected_input = input("Seleciona o número das coleções (ex: 1,3):\n> ").strip()
        try:
            indices = [int(i) - 1 for i in selected_input.split(",")]
            if indices and all(0 <= i < len(COLLECTIONS) for i in indices):
                return [COLLECTIONS[i] for i in indices]
        except ValueError:
            pass
        print("Input inválido. Escolhe pelo menos uma coleção da lista.")

def interactive_mode():
    print("\n--- DGT CDD Downloader (Interactive Mode) ---")
    try:
        username = input("DGT Username (Email):\n> ").strip()
        password = getpass("DGT Password:\n> ").strip()

        if not authenticate(username, password):
            sys.exit(1)

        input_bbox = parse_bbox(input("Define a bounding box (WGS84) separada por virgulas, como (min_lon,min_lat,max_lon,max_lat):\n> "))
        output_dir = input("Diretoria de output (default: ./downloaded_files):\n> ").strip() or "./downloaded_files"
        download_delay = float(input("Tempo de espera em segundos entre cada request/download (default: 5.0):\n> ").strip() or 5.0)
        workers = int(input(f"Downloads em simultâneo, 1 a {MAX_WORKERS} (default: 1):\n> ").strip() or 1)
        selected_collections = choose_collections()

        print("\nInício do processo de download...\n")

        return input_bbox, username, output_dir, download_delay, selected_collections, workers
    except (ValueError, EOFError) as e:
        print(f"Erro no modo interativo: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print_banner()
    parser = argparse.ArgumentParser(description="DGT CDD Downloader with automated authentication.")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("--bbox", type=str, help="Bounding box as 'min_lon min_lat max_lon max_lat' (e.g., '-9.2 38.7 -9.1 38.8')")
    parser.add_argument("--username", type=str, help="Your DGT CDD username (email)")
    parser.add_argument("--password", type=str, help="Your DGT CDD password (asked for if left out)")
    parser.add_argument("-c", "--collections", type=str, help=f"Required. Comma-separated collection names: {', '.join(COLLECTIONS)}")
    parser.add_argument("--output-dir", type=str, default="./downloaded_files", help="Output directory (default: ./downloaded_files)")
    parser.add_argument("--delay", type=float, default=5.0, help="Delay between requests/downloads in seconds, for each worker (default: 5.0)")
    parser.add_argument("-w", "--workers", type=int, choices=range(1, MAX_WORKERS + 1), default=1, help="Simultaneous downloads (default: 1). 2 roughly doubles the requests sent to the portal")

    args = parser.parse_args()

    try:
        if args.interactive:
            input_bbox, username, output_dir, download_delay, selected_collections, workers = interactive_mode()
            download(input_bbox, username, selected_collections, output_dir=output_dir, delay=download_delay, workers=workers)
        else:
            # Command-line mode
            if not all([args.bbox, args.username, args.collections]):
                parser.error("In non-interactive mode, --bbox, --username and --collections (-c) are required.")

            try:
                input_bbox = parse_bbox(args.bbox)
            except ValueError as e:
                parser.error(f"Invalid bbox format: {e}")

            print("\n--- DGT CDD Downloader (Command-Line Mode) ---")
            print(f"Bounding box: {input_bbox}")
            print(f"Output directory: {args.output_dir}")
            print(f"Delay: {args.delay}s")
            print(f"Workers: {args.workers}")
            print(f"Collections: {args.collections}")
            print("\nInício do processo de download...\n")
            download(input_bbox, args.username, args.collections, password=args.password, output_dir=args.output_dir, delay=args.delay, workers=args.workers)
    except KeyboardInterrupt:
        print("\nInterrompido.")
        sys.exit(130)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        sys.exit(1)
