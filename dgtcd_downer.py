import math
import requests
import os
import json
import time
import sys
import argparse
import urllib.parse
from html.parser import HTMLParser

# Global state for session management
auth_state = {
    "session": None,
    "username": None,
    "password": None,
    "last_auth_time": 0,
    "download_counter": 0,
}
SESSION_TIMEOUT = 25 * 60  # 25 minutes in seconds

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

def is_session_valid(stac_url):
    """Check if the current session is still valid by making a test API call."""
    try:
        test_payload = {"bbox": [-9.0, 38.0, -8.0, 39.0], "limit": 1}
        response = auth_state["session"].post(stac_url, json=test_payload, timeout=15)
        return response.status_code == 200
    except Exception as e:
        print(f"\n[Session validation check failed: {e}]")
        return False

# --- Authenticate() to update global state ---
def authenticate(username, password):
    """
    Authenticates with DGT using username and password and updates the global state.
    """
    # Constants for authentication
    auth_base_url = "https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/protocol/openid-connect"
    redirect_uri = "https://cdd.dgterritorio.gov.pt/auth/callback"
    client_id = "aai-oidc-dgt"
    main_site = "https://cdd.dgterritorio.gov.pt"
    stac_url = "https://cdd.dgterritorio.gov.pt/dgt-be/v1/search"
    
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
        response = session.get(main_site, timeout=30)
        response.raise_for_status()
        auth_params = {'client_id': client_id, 'response_type': 'code', 'redirect_uri': redirect_uri, 'scope': 'openid profile email'}
        full_auth_url = f"{auth_base_url}/auth?" + urllib.parse.urlencode(auth_params)
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
        login_url = parser.form_action if not parser.form_action.startswith('/') else f"https://auth.cdd.dgterritorio.gov.pt{parser.form_action}"
        login_headers = headers.copy()
        login_headers.update({'Content-Type': 'application/x-www-form-urlencoded', 'Origin': 'https://auth.cdd.dgterritorio.gov.pt', 'Referer': response.url})
        response = session.post(login_url, data=login_data, headers=login_headers, allow_redirects=True, timeout=30)
        response.raise_for_status()
        
        # 5: Check if login was successful by testing the STAC API
        if response.url.startswith(main_site):
            print("Successfully redirected to main site. Verifying session...")
            test_response = session.post(stac_url, json={"bbox": [-9.0, 38.0, -8.0, 39.0], "limit": 1}, timeout=30)
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
        "image/tiff; application=geotiff": ".tif",
        "image/tiff": ".tif",
        "application/vnd.laszip": ".laz",
    }
    return mime_to_extension.get(mime_type, ".bin")

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

def search_stac_api(stac_url, bbox, collections=None, delay=0.2):
    payload = {
        "bbox": bbox,
        "limit": 1000
    }
    if collections:
        payload["collections"] = collections

    print(f"A esperar {delay}s antes de procurar...")
    time.sleep(delay)
    
    try:
        # Use session from global state
        response = auth_state["session"].post(stac_url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Erro na query da API STAC para a bbox {bbox}: {e}")
        return {"features": []}

def collect_urls_per_collection(stac_response):
    urls_per_collection = {}
    seen_urls = set()

    for item in stac_response.get("features", []):
        collection = item.get("collection", "unknown")
        item_id = next((link.get("href").split("/")[-1] for link in item.get("links", []) if link.get("rel") == "self"), item.get("id", "unknown"))
        for asset in item.get("assets", {}).values():
            url = asset.get("href")

            if url and url not in seen_urls:
                urls_per_collection.setdefault(collection, []).append((url, item_id, get_file_extension(asset.get("type"))))
                seen_urls.add(url)
    
    return urls_per_collection

# Check global session validity periodically
def download_file(stac_url, url, item_id, extension, output_dir, delay=5.0):

    auth_state["download_counter"] += 1
    if auth_state["download_counter"] % 10 == 0:
        if is_session_expired() or not is_session_valid(stac_url):
            print("\n[Session expired or invalid, re-authenticating...]")
            if not authenticate(auth_state["username"], auth_state["password"]):
                raise AuthenticationError("Re-authentication failed. Aborting.")

    filename = f"{item_id}{extension}" if item_id else f"{url.split('/')[-1]}{extension}"
    file_path = os.path.join(output_dir, filename)

    if os.path.exists(file_path):
        print(f"Ignorar {filename}: ficheiro já existe")
        return True

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
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            done = int(bar_length * downloaded / total)
                            percent = int(100 * downloaded / total)
                            bar = f"[{'#' * done}{'-' * (bar_length - done)}] {percent}%"
                            sys.stdout.write(f"\rDownloading {filename} {bar}")
                            sys.stdout.flush()
            
            if total > 0:
                sys.stdout.write("\n")
            else:
                print(f"Download do {filename} realizado! (tamanho desconhecido)")
            
            return True # Success
        
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.exceptions.Timeout) as e:
            sys.stdout.write("\n") # Clean up line from progress bar
            retry_count += 1
            if retry_count < max_retries:
                print(f"Erro de rede no download {filename} (tentativa {retry_count}/{max_retries}): {e}")
                print(f"A esperar {retry_delay}s antes de tentar novamente...")
                time.sleep(retry_delay)
                continue
            else:
                print(f"Falha no download {filename} após {max_retries} tentativas: {e}")
                return False
        except Exception as e:
            sys.stdout.write("\n") # Clean up line from progress bar
            print(f"Erro no download {url}: {e}")
            return False
    return False

def get_available_collections_fallback(stac_url):
    print("A obter as coleções via a API do STAC...")
    payload = {
        #for some reason the first 1000 features for portugal only report 2 collections... changed to smaller bbox with all collections
        #"bbox": [-9.5, 36.5, -6.0, 42.5],  # Portugal mainland
        "bbox":  [-8.694649,39.430359,-8.693619,39.433011],
        "limit": 1000
    }
    try:
        response = auth_state["session"].post(stac_url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return sorted({c for feature in data.get("features", []) if (c := feature.get("collection"))})
    except Exception as e:
        print(f"Erro a obter as coleções: {e}")
        return []

def interactive_mode(stac_url):
    print("\n--- DGT CDD Downloader (Interactive Mode) ---")
    try:
        username = input("DGT Username (Email):\n> ").strip()
        password = input("DGT Password:\n> ").strip()
        

        if not authenticate(username, password):
            sys.exit(1)

        bbox_input = input("Define a bounding box (WGS84) separada por virgulas, como (min_lon,min_lat,max_lon,max_lat):\n> ")
        input_bbox = [float(x.strip()) for x in bbox_input.split(",")]
        output_dir = input("Diretoria de output (default: ./downloaded_files):\n> ").strip() or "./downloaded_files"
        download_delay = float(input("Tempo de espera em segundos entre cada request/download (default: 5.0):\n> ").strip() or 5.0)
        available = get_available_collections_fallback(stac_url)
        if not available:
            print("AVISO: Não foi possível obter as coleções. A processar sem esse filtro.")
            selected_collections = None
        else:
            print("\nColeções disponíveis:")
            for i, name in enumerate(available, 1):
                print(f"  {i}. {name}")
            selected_input = input("Seleciona o número da coleção (ex: 1,3 ou Enter para todas na BBox):\n> ").strip()
            selected_collections = None
            if selected_input:
                try:
                    indices = [int(i) - 1 for i in selected_input.split(",")]
                    selected_collections = [available[i] for i in indices if 0 <= i < len(available)]
                except Exception:
                    print("Input inválido. A processar sem esse filtro.")
                    
        print("\nInício do processo de download...\n")

        return input_bbox, output_dir, download_delay, selected_collections
    except Exception as e:
        print(f"Erro no modo interativo: {e}")
        sys.exit(1)

def main(bbox, stac_url, output_dir, delay, collections=None):
    small_bboxes = divide_bbox(bbox)
    print(f"Bbox dividida em {len(small_bboxes)} pequenas bboxes")

    all_urls_per_collection = {}
    for i, small_bbox in enumerate(small_bboxes, 1):
        print(f"A processar bbox {i}/{len(small_bboxes)}: {small_bbox}")
        stac_response = search_stac_api(stac_url, small_bbox, collections=collections)
        urls_per_collection = collect_urls_per_collection(stac_response)
        
        for collection, url_id_ext_pairs in urls_per_collection.items():
            all_urls_per_collection.setdefault(collection, []).extend(url_id_ext_pairs)
        print(f"Encontrados {sum(len(urls) for urls in urls_per_collection.values())} items na bbox {i}")

    total_urls = sum(len(urls) for urls in all_urls_per_collection.values())
    print(f"Total de URLs únicos para download: {total_urls}")
    downloaded, skipped = 0, 0
    auth_state["download_counter"] = 0
    for collection, url_id_ext_pairs in all_urls_per_collection.items():
        print(f"\nDownloading da coleção: {collection}")
        collection_output_dir = os.path.join(output_dir, collection)
        for j, (url, item_id, extension) in enumerate(url_id_ext_pairs, 1):
            print(f"A processar o URL {j}/{len(url_id_ext_pairs)} : {url}")
            if download_file(stac_url, url, item_id, extension, collection_output_dir, delay):
                if not os.path.exists(os.path.join(collection_output_dir, f"{item_id}{extension}")):
                    downloaded += 1
                else:
                    skipped += 1
            else:
                pass 
    print(f"\nResumo: Download de {downloaded} ficheiros, ignorados {skipped} ficheiros")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DGT CDD Downloader with automated authentication.")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("--bbox", type=str, help="Bounding box as 'min_lon min_lat max_lon max_lat' (e.g., '-9.2 38.7 -9.1 38.8')")
    parser.add_argument("--username", type=str, help="Your DGT CDD username (email)")
    parser.add_argument("--password", type=str, help="Your DGT CDD password")
    parser.add_argument("--output-dir", type=str, default="./downloaded_files", help="Output directory (default: ./downloaded_files)")
    parser.add_argument("--delay", type=float, default=5.0, help="Delay between requests/downloads in seconds (default: 5.0)")
    parser.add_argument("--collections", type=str, help="Comma-separated collection names (e.g., LAZ,MDT-50cm)")

    args = parser.parse_args()

    # Static config
    STAC_SEARCH_URL = "https://cdd.dgterritorio.gov.pt/dgt-be/v1/search"

    try:
        session = None
        if args.interactive:
            input_bbox, output_dir, download_delay, selected_collections = interactive_mode(STAC_SEARCH_URL)
            main(input_bbox, STAC_SEARCH_URL, output_dir, download_delay, collections=selected_collections)
        else:
            # Command-line mode
            if not all([args.bbox, args.username, args.password]):
                parser.error("In non-interactive mode, --bbox, --username, and --password are required.")
            
            if not authenticate(args.username, args.password):
                sys.exit(1)
            
            try:
                input_bbox = [float(x.strip()) for x in args.bbox.split()]
                if len(input_bbox) != 4:
                    raise ValueError("Bounding box must have 4 values: min_lon min_lat max_lon max_lat")
            except ValueError as e:
                parser.error(f"Invalid bbox format: {e}")
            selected_collections = [c.strip() for c in args.collections.split(",")] if args.collections else None
            print("\n--- DGT CDD Downloader (Command-Line Mode) ---")
            print(f"Bounding box: {input_bbox}")
            print(f"Output directory: {args.output_dir}")
            print(f"Delay: {args.delay}s")
            print(f"Collections: {selected_collections or 'All available in BBox'}")
            print("\nInício do processo de download...\n")
            main(input_bbox, STAC_SEARCH_URL, args.output_dir, args.delay, collections=selected_collections)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        sys.exit(1)

