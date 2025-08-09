"""
DGT CDD Downloader - QGIS Processing Tool with Cookie-based Authentication
Ferramenta para download de dados geoespaciais da DGT através do QGIS com autenticação por cookies
"""

import math
import requests
import os
import json
import time
import urllib.parse
import glob
import ssl
from typing import Dict, List, Tuple, Any, Optional
from html.parser import HTMLParser

from requests.adapters import HTTPAdapter
from urllib3 import PoolManager

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingAlgorithm,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterString,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean,
    QgsMessageLog,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsFields,
    QgsField,
    QgsProcessingParameterVectorDestination,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsVectorFileWriter,
    QgsRasterLayer
)
from qgis.PyQt.QtWidgets import QMessageBox
import processing


class SSLNoVerifyAdapter(HTTPAdapter):
    """
    A custom Transport Adapter for requests that disables SSL certificate verification.
    This is used as a last resort for environments with intrusive SSL inspection
    where standard `verify=False` is not sufficient.
    """
    def init_poolmanager(self, connections, maxsize, block=False):
        """
        Initializes a urllib3 PoolManager with a custom SSL context that
        does not perform certificate verification. This method is compatible
        with older Python versions.
        """
        # Create a custom SSL context
        context = ssl.create_default_context()
        # Disable hostname checking
        context.check_hostname = False
        # Disable certificate verification
        context.verify_mode = ssl.CERT_NONE
        
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=context
        )


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


class DgtCddDownloaderAlgorithm(QgsProcessingAlgorithm):
    """
    QGIS Processing Algorithm for downloading DGT CDD data with cookie-based authentication
    """
    
    # Constants
    INPUT_EXTENT = 'INPUT_EXTENT'
    INPUT_POLYGON = 'INPUT_POLYGON'
    INPUT_METHOD = 'INPUT_METHOD'
    USERNAME = 'USERNAME'
    PASSWORD = 'PASSWORD'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'
    DELAY = 'DELAY'
    COLLECTIONS = 'COLLECTIONS'
    MAX_AREA = 'MAX_AREA'
    CREATE_BOUNDARY_LAYER = 'CREATE_BOUNDARY_LAYER'
    BOUNDARY_OUTPUT = 'BOUNDARY_OUTPUT'
    CREATE_VRT = 'CREATE_VRT'
    BUILD_OVERVIEWS = 'BUILD_OVERVIEWS'
    LOAD_VRT = 'LOAD_VRT'
    
    def __init__(self):
        super().__init__()
        self.stac_url = "https://cdd.dgterritorio.gov.pt/dgt-be/v1/search"
        self.auth_base_url = "https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/protocol/openid-connect"
        self.redirect_uri = "https://cdd.dgterritorio.gov.pt/auth/callback"
        self.client_id = "aai-oidc-dgt"
        self.main_site = "https://cdd.dgterritorio.gov.pt"
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin"
        }
        
        self.available_collections = []
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Collections that are rasters (not LiDAR point clouds)
        self.raster_collections = ['MDS-2m', 'MDS-50cm', 'MDT-2m', 'MDT-50cm']
        
        # Session management
        self.session_timeout = 25 * 60  # 25 minutes in seconds
        self.last_auth_time = 0
        self._username = None
        self._password = None
        self._download_counter = 0
    
    def tr(self, string):
        return QCoreApplication.translate('Processing', string)
    
    def createInstance(self):
        return DgtCddDownloaderAlgorithm()
    
    def name(self):
        return 'dgt_cdd_lidar_data_downloader'
    
    def displayName(self):
        return self.tr('DGT CDD Data Downloader')
    

# Removed to avoid a subgroup creation
#    def group(self):
#        return self.tr('DGT CDD Portal')
    
#    def groupId(self):
#        return 'dgt_cdd_portal'
    
    def shortHelpString(self):
        return self.tr("""
        Download geospatial LiDAR data from portuguese <a href='https://cdd.dgterritorio.gov.pt'>DGT (Direção-Geral do Território) - CDD Portal</a>.

        This tool allows you to:
        - Login with your DGT credentials (username and password)
        - Select an area of interest using either:
          * A bounding box extent (from map canvas or manual entry)
          * A polygon layer (first feature or selected feature will be used)
        - Download various geospatial LiDAR datasets from DGT CDD Portal
        (LAZ, MDS-50cm, MDS-2m, MDT-50cm, MDT-2m)
        - Automatically organize files by collection
        - Create VRT (Virtual Raster) files for raster collections
        - Load VRT files automatically into QGIS
        - Create boundary layers showing download areas
        
        Requirements:
        - Valid credentials for the <a href='https://cdd.dgterritorio.gov.pt'>DGT - CDD Portal</a>
        - Internet connection
        
        The tool will automatically handle the authentication process using session cookies and divide large areas into smaller chunks to avoid server overload.
        
        -------------------------------------------------
        
        Serviço de descarregamento de dados geográficos LiDAR da DGT (Direção-Geral do Território) - Centro de Dados.
        (https://cdd.dgterritorio.gov.pt)
        
        Esta ferramenta permite:
        - Fazer login no Centro de dados da DGT com as suas credenciais (username e password)
        - Selecionar uma área de interesse utilizando:
          * Uma extensão retangular (obtida a partir do mapa ou introduzindo as coordenadas manualmente)
          * Uma camada de polígonos (será usado o primeiro polígono da camada ou o polígono selecionado)
        - Descarregar as várias coleções de dados LiDAR disponíveis no Centro de Dados da DGT
        (LAZ, MDS-50cm, MDS-2m, MDT-50cm, MDT-2m)
        - Organizar os ficheiros descarregados por coleção
        - Criar ficheiros VRT (Virtual Raster) para as coleções de rasters
        - Carregar automaticamente os VRT no QGIS
        - Criar uma layer com a extensão das áreas de download
        
        Requisitos:
        - Credenciais válidas do <a href='https://cdd.dgterritorio.gov.pt'>Centro de Dados da DGT</a>
        - Ligação à Internet
        
        Esta ferramenta vai gerir automaticamente o processo de autenticação usando cookies de sessão e dividir áreas grandes em partes mais pequenas, respeitando os limites impostos pelo servidor.
        
        """)
    
    def initAlgorithm(self, config=None):
        # Input method selection
        self.addParameter(
            QgsProcessingParameterEnum(
                self.INPUT_METHOD,
                self.tr('Input Method'),
                options=[self.tr('Extent (Bounding Box)'), self.tr('Polygon Layer')],
                defaultValue=0,
                optional=False
            )
        )
        
        # Input extent (shown when extent method is selected)
        self.addParameter(
            QgsProcessingParameterExtent(
                self.INPUT_EXTENT,
                self.tr('Area of Interest (Extent)'),
                defaultValue=None,
                optional=True
            )
        )
        
        # Input polygon layer (shown when polygon method is selected)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_POLYGON,
                self.tr('Area of Interest (Polygon Layer)'),
                types=[QgsProcessing.TypeVectorPolygon],
                optional=True
            )
        )
        
        # Authentication parameters
        self.addParameter(
            QgsProcessingParameterString(
                self.USERNAME,
                self.tr('Username'),
                multiLine=False,
                defaultValue='',
                optional=False
            )
        )
        
        # Password parameter (Note: QGIS Processing doesn't support native password fields)
        # The password will be visible while typing - use with caution in shared environments
        self.addParameter(
            QgsProcessingParameterString(
                self.PASSWORD,
                self.tr('Password'),
                multiLine=False,
                defaultValue='',
                optional=False
            )
        )
        
        # Output folder
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr('Output Folder')
            )
        )
        
        # Optional parameters
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DELAY,
                self.tr('Delay between requests (seconds)'),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=5.0,
                minValue=1.0,
                maxValue=60.0
            )
        )
        
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_AREA,
                self.tr('Maximum area per request (km²)'),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=200.0,
                minValue=50.0,
                maxValue=200.0
            )
        )
        
        # Collections (predefined options)
        self.addParameter(
            QgsProcessingParameterEnum(
                self.COLLECTIONS,
                self.tr('Collections to download'),
                options=['LAZ', 'MDS-2m', 'MDS-50cm', 'MDT-2m', 'MDT-50cm'],
                allowMultiple=True,
                optional=True
            )
        )
        
        # VRT options
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CREATE_VRT,
                self.tr('Create VRT files for raster collections'),
                defaultValue=True,
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.BUILD_OVERVIEWS,
                self.tr('Build overviews (pyramids) for VRT files'),
                defaultValue=True,
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_VRT,
                self.tr('Load VRT files into QGIS'),
                defaultValue=True,
                optional=True
            )
        )

        # Create boundary layer
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CREATE_BOUNDARY_LAYER,
                self.tr('Create boundary layer showing download areas'),
                defaultValue=True,
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterVectorDestination(
                self.BOUNDARY_OUTPUT,
                self.tr('Boundary Layer'),
                type=QgsProcessing.TypeVectorPolygon,
                optional=True,
                createByDefault=True
            )
        )
        # Individual product checkboxes (default True)
        self.addParameter(
            QgsProcessingParameterBoolean(
            'DOWNLOAD_LAZ',
            self.tr('Download LAZ (point cloud)'),
            defaultValue=True,
            optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
            'DOWNLOAD_MDS_2M',
            self.tr('Download MDS-2m (raster)'),
            defaultValue=True,
            optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
            'DOWNLOAD_MDS_50CM',
            self.tr('Download MDS-50cm (raster)'),
            defaultValue=True,
            optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
            'DOWNLOAD_MDT_2M',
            self.tr('Download MDT-2m (raster)'),
            defaultValue=True,
            optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
            'DOWNLOAD_MDT_50CM',
            self.tr('Download MDT-50cm (raster)'),
            defaultValue=True,
            optional=True
            )
        )
    
    def is_session_valid(self, feedback: QgsProcessingFeedback) -> bool:
        """Check if the current session is still valid"""
        try:
            test_bbox = [-9.0, 38.0, -8.0, 39.0]  # Small test area
            test_payload = {"bbox": test_bbox, "limit": 1}
            
            response = self.session.post(
                self.stac_url,
                json=test_payload,
                timeout=30
            )
            
            return response.status_code == 200
        except Exception as e:
            feedback.pushInfo(f"Session validation error: {e}")
            return False
    
    def is_session_expired(self):
        """Check if session has likely expired based on time"""
        return (time.time() - self.last_auth_time) > self.session_timeout
    
    def authenticate(self, username: str, password: str, feedback: QgsProcessingFeedback) -> bool:
        """Authenticate with DGT using username and password, extracting session cookies"""
        try:
            feedback.pushInfo("Starting authentication process...")
            
            # Create a fresh session
            self.session = requests.Session()

            # Mount the custom adapter to forcefully disable SSL verification for all requests.
            # This is a robust workaround for environments with SSL inspection proxies
            # that interfere with standard certificate validation.
            feedback.pushWarning("Mounting custom adapter to disable SSL verification for the entire session.")
            self.session.mount('https://', SSLNoVerifyAdapter())
            self.session.mount('http://', SSLNoVerifyAdapter())
            
            self.session.headers.update(self.headers)
            
            # Step 1: Visit main site to get initial session
            feedback.pushInfo("Visiting main site...")
            response = self.session.get(self.main_site, timeout=30)
            response.raise_for_status()
            
            # Step 2: Look for login link or go directly to auth
            auth_url = f"{self.auth_base_url}/auth"
            auth_params = {
                'client_id': self.client_id,
                'response_type': 'code',
                'redirect_uri': self.redirect_uri,
                'scope': 'openid profile email'
            }
            
            full_auth_url = f"{auth_url}?" + urllib.parse.urlencode(auth_params)
            feedback.pushInfo("Getting authentication page...")
            
            # Step 3: Get the login form
            response = self.session.get(full_auth_url, timeout=30)
            response.raise_for_status()
            
            feedback.pushInfo(f"Got login page (status: {response.status_code})")
            
            # Step 4: Parse the login form
            parser = KeycloakFormParser()
            parser.feed(response.text)
            
            if not parser.form_action:
                raise AuthenticationError("Could not find login form")
            
            feedback.pushInfo("Found login form, submitting credentials...")
            
            # Step 5: Submit login form
            login_data = parser.form_data.copy()
            login_data.update({
                'username': username,
                'password': password
            })
            
            # Build absolute URL for form action
            if parser.form_action.startswith('/'):
                login_url = f"https://auth.cdd.dgterritorio.gov.pt{parser.form_action}"
            else:
                login_url = parser.form_action
            
            login_headers = self.headers.copy()
            login_headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://auth.cdd.dgterritorio.gov.pt',
                'Referer': response.url
            })
            
            response = self.session.post(
                login_url,
                data=login_data,
                headers=login_headers,
                allow_redirects=True,  # Allow redirects
                timeout=30
            )
            
            feedback.pushInfo(f"Login response: {response.status_code}")
            
            # Step 6: Check if we're back at the main site (successful auth)
            if response.url.startswith(self.main_site):
                feedback.pushInfo("Successfully redirected to main site")
                self.last_auth_time = time.time()
                
                # Extract important cookies
                cookies = self.session.cookies
                important_cookies = []
                
                for cookie in cookies:
                    if cookie.name in ['auth_session', 'connect.sid', 'JSESSIONID', 'KC_RESTART']:
                        important_cookies.append(f"{cookie.name}={cookie.value}")
                
                if important_cookies:
                    feedback.pushInfo(f"Found authentication cookies: {', '.join([c.split('=')[0] for c in important_cookies])}")
                else:
                    feedback.pushInfo("No specific authentication cookies found, but session should be valid")
                
                # Test the session by making a request to the STAC API
                feedback.pushInfo("Testing authentication with STAC API...")
                if self.is_session_valid(feedback):
                    feedback.pushInfo("Authentication successful! Session is valid.")
                    return True
                else:
                    feedback.reportError("Authentication test failed")
                    return False
            
            # Step 7: Check for authentication errors
            if "error" in response.url.lower() or response.status_code >= 400:
                feedback.reportError("Authentication failed - check credentials")
                return False
            
            # If we get here, something unexpected happened
            feedback.reportError(f"Unexpected response: {response.status_code}, URL: {response.url}")
            return False
            
        except requests.RequestException as e:
            feedback.reportError(f"Network error during authentication: {e}")
            return False
        except Exception as e:
            feedback.reportError(f"Authentication error: {e}")
            return False
    
    def get_file_extension(self, mime_type: str) -> str:
        """Get file extension based on MIME type"""
        mime_to_extension = {
            "image/tiff; application=geotiff": ".tif",
            "image/tiff": ".tif",
            "application/vnd.laszip": ".laz",
            "application/octet-stream": ".bin",
            "application/json": ".json",
            "text/xml": ".xml"
        }
        return mime_to_extension.get(mime_type, ".bin")
    
    def divide_bbox(self, bbox: List[float], max_area_km2: float) -> List[List[float]]:
        """Divide large bounding box into smaller chunks"""
        min_lon, min_lat, max_lon, max_lat = bbox
        deg_to_km = 111
        
        # Calculate dimensions
        width_km = (max_lon - min_lon) * deg_to_km * math.cos(math.radians((min_lat + max_lat) / 2))
        height_km = (max_lat - min_lat) * deg_to_km
        total_area_km2 = width_km * height_km
        
        if total_area_km2 <= max_area_km2:
            return [bbox]
        
        # Calculate splits
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
    
    def divide_polygon(self, polygon: QgsGeometry, max_area_km2: float) -> List[QgsGeometry]:
        """Divide large polygon into smaller chunks"""
        # Convert polygon to bounding box first (simple implementation)
        bbox = polygon.boundingBox()
        min_lon, min_lat = bbox.xMinimum(), bbox.yMinimum()
        max_lon, max_lat = bbox.xMaximum(), bbox.yMaximum()
        
        deg_to_km = 111
        
        # Calculate dimensions
        width_km = (max_lon - min_lon) * deg_to_km * math.cos(math.radians((min_lat + max_lat) / 2))
        height_km = (max_lat - min_lat) * deg_to_km
        total_area_km2 = width_km * height_km
        
        if total_area_km2 <= max_area_km2:
            return [polygon]
        
        # Calculate splits
        splits_x = math.ceil(width_km / math.sqrt(max_area_km2))
        splits_y = math.ceil(height_km / math.sqrt(max_area_km2))
        
        delta_lon = (max_lon - min_lon) / splits_x
        delta_lat = (max_lat - min_lat) / splits_y
        
        small_polygons = []
        for i in range(splits_x):
            for j in range(splits_y):
                small_min_lon = min_lon + i * delta_lon
                small_max_lon = min(small_min_lon + delta_lon, max_lon)
                small_min_lat = min_lat + j * delta_lat
                small_max_lat = min(small_min_lat + delta_lat, max_lat)
                
                # Create rectangle polygon
                rect = QgsGeometry.fromRect(QgsRectangle(small_min_lon, small_min_lat, small_max_lon, small_max_lat))
                
                # Clip with original polygon
                clipped = rect.intersection(polygon)
                if not clipped.isEmpty() and clipped.area() > 0:
                    small_polygons.append(clipped)
        
        return small_polygons
    
    def search_stac_api_bbox(self, bbox: List[float], collections: List[str] = None, 
                           delay: float = 0.2) -> Dict:
        """Search STAC API for items in bounding box"""
        payload = {
            "bbox": bbox,
            "limit": 1000
        }
        if collections:
            payload["collections"] = collections
        
        time.sleep(delay)
        
        try:
            response = self.session.post(
                self.stac_url, 
                json=payload, 
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            QgsMessageLog.logMessage(
                f"STAC API error for bbox {bbox}: {e}",
                "DGT Downloader",
                Qgis.Warning
            )
            return {"features": []}
    
    def search_stac_api_geometry(self, geometry: QgsGeometry, collections: List[str] = None, 
                               delay: float = 0.2) -> Dict:
        """Search STAC API for items intersecting with geometry"""
        # Convert QgsGeometry to GeoJSON format
        geom_json = json.loads(geometry.asJson())
        
        payload = {
            "filter": {
                "op": "intersects",
                "args": [
                    {"property": "geometry"},
                    geom_json
                ]
            },
            "limit": 1000
        }
        
        if collections:
            payload["collections"] = collections
        
        time.sleep(delay)
        
        try:
            response = self.session.post(
                self.stac_url, 
                json=payload, 
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            QgsMessageLog.logMessage(
                f"STAC API error for geometry {geom_json}: {e}",
                "DGT Downloader",
                Qgis.Warning
            )
            return {"features": []}
    
    def collect_urls_per_collection(self, stac_response: Dict) -> Dict[str, List[Tuple[str, str, str]]]:
        """Collect download URLs organized by collection"""
        urls_per_collection = {}
        seen_urls = set()
        
        for item in stac_response.get("features", []):
            collection = item.get("collection", "unknown")
            
            # Get item ID
            item_id = None
            for link in item.get("links", []):
                if link.get("rel") == "self":
                    item_id = link.get("href", "").split("/")[-1]
                    break
            
            if not item_id:
                item_id = item.get("id", "unknown")
            
            # Process assets
            assets = item.get("assets", {})
            for asset_key, asset in assets.items():
                url = asset.get("href")
                mime_type = asset.get("type", "")
                extension = self.get_file_extension(mime_type)
                
                if url and url not in seen_urls:
                    if collection not in urls_per_collection:
                        urls_per_collection[collection] = []
                    urls_per_collection[collection].append((url, item_id, extension))
                    seen_urls.add(url)
        
        return urls_per_collection
    
    def download_file(self, url: str, item_id: str, extension: str, 
                     output_dir: str, delay: float,
                     feedback: QgsProcessingFeedback) -> bool:
        """Download a single file with session validation and retry logic"""
        # Check session validity periodically
        self._download_counter += 1
        if self._download_counter % 10 == 0:  # Check every 10 files
            if self.is_session_expired() or not self.is_session_valid(feedback):
                feedback.pushInfo("Session expired or invalid, re-authenticating...")
                if not self.authenticate(self._username, self._password, feedback):
                    raise AuthenticationError("Re-authentication failed")
        
        filename = f"{item_id}{extension}"
        file_path = os.path.join(output_dir, filename)
        
        # Skip if file exists
        if os.path.exists(file_path):
            feedback.pushInfo(f"Skipping {filename}: file already exists")
            return False
        
        feedback.pushInfo(f"Downloading {filename}...")
        time.sleep(delay)
        
        max_retries = 3
        retry_delay = 5  # seconds between retries
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                response = self.session.get(
                    url, 
                    stream=True,
                    timeout=60
                )
                
                # Check for authentication errors
                content_type = response.headers.get("Content-Type", "").lower()
                if content_type.startswith("text/html"):
                    # Might be an auth error page
                    if "login" in response.text.lower() or "auth" in response.text.lower():
                        raise AuthenticationError(f"Authentication error for {url}")
                
                response.raise_for_status()
                
                # Create output directory
                os.makedirs(output_dir, exist_ok=True)
                
                # Download with progress
                total_size = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if feedback.isCanceled():
                            return False
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total_size > 0:
                                progress = int(100 * downloaded / total_size)
                                feedback.setProgress(progress)
                
                feedback.pushInfo(f"Downloaded {filename} successfully")
                return True
                
            except requests.exceptions.RequestException as e:
                # This broad exception catches ConnectionError, Timeout, SSLError, etc.
                retry_count += 1
                if retry_count < max_retries:
                    feedback.pushInfo(f"Connection error downloading {filename} (attempt {retry_count}/{max_retries}): {str(e)}")
                    feedback.pushInfo(f"Waiting {retry_delay} seconds before retry...")
                    time.sleep(retry_delay)
                    continue
                else:
                    feedback.reportError(f"Failed to download {filename} after {max_retries} attempts: {str(e)}")
                    return False
                    
            except Exception as e:
                feedback.reportError(f"Error downloading {url}: {e}")
                return False
        
        return False
    
    def create_vrt_for_collection(self, collection: str, output_dir: str, 
                                 feedback: QgsProcessingFeedback) -> Optional[str]:
        """Create a VRT file for a raster collection"""
        try:
            # Only create VRT for raster collections
            if collection not in self.raster_collections:
                feedback.pushInfo(f"Skipping VRT creation for {collection} (not a raster collection)")
                return None
            
            collection_dir = os.path.join(output_dir, collection)
            if not os.path.exists(collection_dir):
                feedback.pushInfo(f"Collection directory {collection_dir} does not exist")
                return None
            
            # Find all raster files in the collection directory
            raster_patterns = ['*.tif', '*.tiff', '*.TIF', '*.TIFF']
            raster_files = []
            
            for pattern in raster_patterns:
                raster_files.extend(glob.glob(os.path.join(collection_dir, pattern)))
            
            if not raster_files:
                feedback.pushInfo(f"No raster files found in {collection_dir}")
                return None
            
            feedback.pushInfo(f"Found {len(raster_files)} raster files for {collection}")
            
            # Create VRT file path
            vrt_filename = f"{collection}.vrt"
            vrt_path = os.path.join(output_dir, vrt_filename)
            
            # Use GDAL's buildvrt through processing
            vrt_params = {
                'INPUT': raster_files,
                'OUTPUT': vrt_path,
                'RESOLUTION': 0,  # Use average resolution
                'SEPARATE': False,  # Merge into single band
                'PROJ_DIFFERENCE': False,  # Don't allow projection differences
                'ADD_ALPHA': False,
                'ASSIGN_CRS': None,
                'RESAMPLING': 0,  # Nearest neighbor
                'SRC_NODATA': '',
                'EXTRA': ''
            }
            
            feedback.pushInfo(f"Creating VRT file for {collection}...")
            
            # Run the buildvrt algorithm
            result = processing.run(
                "gdal:buildvirtualraster",
                vrt_params,
                feedback=feedback
            )
            
            if result and os.path.exists(vrt_path):
                feedback.pushInfo(f"VRT file created successfully: {vrt_path}")
                return vrt_path
            else:
                feedback.reportError(f"Failed to create VRT file for {collection}")
                return None
                
        except Exception as e:
            feedback.reportError(f"Error creating VRT for {collection}: {str(e)}")
            return None
    
    def build_vrt_overviews(self, vrt_path: str, feedback: QgsProcessingFeedback) -> bool:
        """Build overviews (pyramids) for a VRT file"""
        try:
            if not os.path.exists(vrt_path):
                feedback.reportError(f"VRT file does not exist: {vrt_path}")
                return False
            
            feedback.pushInfo(f"Building overviews for {os.path.basename(vrt_path)}...")
            
            # Use GDAL's overview builder through processing
            overview_params = {
                'INPUT': vrt_path,
                'LEVELS': '2 4 8 16 32',  # Standard pyramid levels
                'RESAMPLING': 0,  # Nearest neighbor
                'FORMAT': 0,  # External (GTiff.ovr)
                'EXTRA': ''
            }
            
            result = processing.run(
                "gdal:overviews",
                overview_params,
                feedback=feedback
            )
            
            if result:
                feedback.pushInfo(f"Successfully built overviews for {os.path.basename(vrt_path)}")
                return True
            else:
                feedback.reportError(f"Failed to build overviews for {os.path.basename(vrt_path)}")
                return False
                
        except Exception as e:
            feedback.reportError(f"Error building overviews for {os.path.basename(vrt_path)}: {str(e)}")
            return False
    
    def load_vrt_to_qgis(self, vrt_path: str, collection: str, 
                        feedback: QgsProcessingFeedback) -> bool:
        """Load VRT file into QGIS"""
        try:
            if not os.path.exists(vrt_path):
                feedback.reportError(f"VRT file does not exist: {vrt_path}")
                return False
            
            # Create raster layer
            layer_name = f"DGT_{collection}"
            raster_layer = QgsRasterLayer(vrt_path, layer_name)
            
            if not raster_layer.isValid():
                feedback.reportError(f"Failed to create raster layer from {vrt_path}")
                return False
            
            # Add layer to project
            QgsProject.instance().addMapLayer(raster_layer)
            feedback.pushInfo(f"Added {layer_name} to QGIS project")
            
            return True
            
        except Exception as e:
            feedback.reportError(f"Error loading VRT to QGIS: {str(e)}")
            return False
    
    def create_boundary_layer_bbox(self, bboxes: List[List[float]], output_path: str, 
                                context: QgsProcessingContext, feedback: QgsProcessingFeedback) -> str:
        """Create a vector layer showing download boundaries from bboxes"""
        try:
            # Create memory layer first
            crs = QgsCoordinateReferenceSystem('EPSG:4326')
            layer = QgsVectorLayer(
                f"Polygon?crs=EPSG:4326",
                "DGT Download Boundaries",
                "memory"
            )
            
            # Create fields with proper constructor
            fields = QgsFields()
            fields.append(QgsField("id", QVariant.Int, "Integer"))
            fields.append(QgsField("min_lon", QVariant.Double, "Real"))
            fields.append(QgsField("min_lat", QVariant.Double, "Real"))
            fields.append(QgsField("max_lon", QVariant.Double, "Real"))
            fields.append(QgsField("max_lat", QVariant.Double, "Real"))
            fields.append(QgsField("area_km2", QVariant.Double, "Real"))
            
            # Add fields to layer
            layer.dataProvider().addAttributes(fields)
            layer.updateFields()
            
            # Create features
            features = []
            for i, bbox in enumerate(bboxes):
                min_lon, min_lat, max_lon, max_lat = bbox
                
                # Create polygon geometry
                points = [
                    QgsPointXY(min_lon, min_lat),
                    QgsPointXY(max_lon, min_lat),
                    QgsPointXY(max_lon, max_lat),
                    QgsPointXY(min_lon, max_lat),
                    QgsPointXY(min_lon, min_lat)
                ]
                
                geometry = QgsGeometry.fromPolygonXY([points])
                
                # Calculate area
                deg_to_km = 111
                width_km = (max_lon - min_lon) * deg_to_km * math.cos(math.radians((min_lat + max_lat) / 2))
                height_km = (max_lat - min_lat) * deg_to_km
                area_km2 = width_km * height_km
                
                # Create feature
                feature = QgsFeature()
                feature.setGeometry(geometry)
                feature.setAttributes([i + 1, min_lon, min_lat, max_lon, max_lat, area_km2])
                features.append(feature)
            
            # Add features to layer
            layer.dataProvider().addFeatures(features)
            layer.updateExtents()
            
            # Write layer to file
            transform_context = context.transformContext()
            save_options = QgsVectorFileWriter.SaveVectorOptions()
            save_options.driverName = "GPKG"
            save_options.fileEncoding = "UTF-8"
            
            error = QgsVectorFileWriter.writeAsVectorFormatV2(
                layer,
                output_path,
                transform_context,
                save_options
            )
            
            if error[0] == QgsVectorFileWriter.NoError:
                feedback.pushInfo(f"Boundary layer created successfully: {output_path}")
                return output_path
            else:
                feedback.reportError(f"Error creating boundary layer: {error[1]}")
                return None
                
        except Exception as e:
            feedback.reportError(f"Error creating boundary layer: {str(e)}")
            return None
    
    def create_boundary_layer_polygon(self, polygons: List[QgsGeometry], output_path: str, 
                                    context: QgsProcessingContext, feedback: QgsProcessingFeedback) -> str:
        """Create a vector layer showing download boundaries from polygons"""
        try:
            # Create memory layer first
            crs = QgsCoordinateReferenceSystem('EPSG:4326')
            layer = QgsVectorLayer(
                f"Polygon?crs=EPSG:4326",
                "DGT Download Boundaries",
                "memory"
            )
            
            # Create fields with proper constructor
            fields = QgsFields()
            fields.append(QgsField("id", QVariant.Int, "Integer"))
            fields.append(QgsField("min_lon", QVariant.Double, "Real"))
            fields.append(QgsField("min_lat", QVariant.Double, "Real"))
            fields.append(QgsField("max_lon", QVariant.Double, "Real"))
            fields.append(QgsField("max_lat", QVariant.Double, "Real"))
            fields.append(QgsField("area_km2", QVariant.Double, "Real"))
            
            # Add fields to layer
            layer.dataProvider().addAttributes(fields)
            layer.updateFields()
            
            # Create features
            features = []
            for i, polygon in enumerate(polygons):
                bbox = polygon.boundingBox()
                min_lon, min_lat = bbox.xMinimum(), bbox.yMinimum()
                max_lon, max_lat = bbox.xMaximum(), bbox.yMaximum()
                
                # Create feature with actual polygon geometry
                feature = QgsFeature()
                feature.setGeometry(polygon)
                
                # Calculate area in km²
                deg_to_km = 111
                width_km = (max_lon - min_lon) * deg_to_km * math.cos(math.radians((min_lat + max_lat) / 2))
                height_km = (max_lat - min_lat) * deg_to_km
                area_km2 = width_km * height_km
                
                feature.setAttributes([i + 1, min_lon, min_lat, max_lon, max_lat, area_km2])
                features.append(feature)
            
            # Add features to layer
            layer.dataProvider().addFeatures(features)
            layer.updateExtents()
            
            # Write layer to file
            transform_context = context.transformContext()
            save_options = QgsVectorFileWriter.SaveVectorOptions()
            save_options.driverName = "GPKG"
            save_options.fileEncoding = "UTF-8"
            
            error = QgsVectorFileWriter.writeAsVectorFormatV2(
                layer,
                output_path,
                transform_context,
                save_options
            )
            
            if error[0] == QgsVectorFileWriter.NoError:
                feedback.pushInfo(f"Boundary layer created successfully: {output_path}")
                return output_path
            else:
                feedback.reportError(f"Error creating boundary layer: {error[1]}")
                return None
                
        except Exception as e:
            feedback.reportError(f"Error creating boundary layer: {str(e)}")
            return None
    
    def processAlgorithm(self, parameters, context, feedback):
        """Main processing algorithm"""
        try:
            # Get parameters
            input_method = self.parameterAsEnum(parameters, self.INPUT_METHOD, context)
            extent = self.parameterAsExtent(parameters, self.INPUT_EXTENT, context) if input_method == 0 else None
            polygon_source = self.parameterAsSource(parameters, self.INPUT_POLYGON, context) if input_method == 1 else None
            self._username = self.parameterAsString(parameters, self.USERNAME, context)
            self._password = self.parameterAsString(parameters, self.PASSWORD, context)
            output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
            delay = self.parameterAsDouble(parameters, self.DELAY, context)
            max_area = self.parameterAsDouble(parameters, self.MAX_AREA, context)
            collection_indices = self.parameterAsEnums(parameters, self.COLLECTIONS, context)
            create_vrt = self.parameterAsBool(parameters, self.CREATE_VRT, context)
            build_overviews = False
            if create_vrt:
                build_overviews = self.parameterAsBool(parameters, self.BUILD_OVERVIEWS, context)
            load_vrt = self.parameterAsBool(parameters, self.LOAD_VRT, context)
            create_boundary = self.parameterAsBool(parameters, self.CREATE_BOUNDARY_LAYER, context)
            boundary_output = self.parameterAsOutputLayer(parameters, self.BOUNDARY_OUTPUT, context)
            
            # Initialize download counter
            self._download_counter = 0
            
            # Validate inputs
            if not self._username or not self._password:
                raise QgsProcessingException("Username and password are required")
            
            # Handle input based on method
            if input_method == 0:  # Extent method
                if extent.isNull():
                    raise QgsProcessingException("Please specify an area of interest extent")
                
                # Convert extent to WGS84 if needed
                extent_crs = self.parameterAsExtentCrs(parameters, self.INPUT_EXTENT, context)
                if extent_crs != QgsCoordinateReferenceSystem('EPSG:4326'):
                    transform = QgsCoordinateTransform(
                        extent_crs,
                        QgsCoordinateReferenceSystem('EPSG:4326'),
                        context.project()
                    )
                    extent = transform.transformBoundingBox(extent)
                
                # Convert to bbox list
                bbox = [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]
                
                feedback.pushInfo(f"Processing extent: {bbox}")
                
                # Divide large areas into smaller chunks
                feedback.pushInfo("Dividing area into smaller chunks...")
                small_bboxes = self.divide_bbox(bbox, max_area)
                feedback.pushInfo(f"Created {len(small_bboxes)} download chunks")
                
            else:  # Polygon method
                polygon_source = self.parameterAsSource(parameters, self.INPUT_POLYGON, context)
                if polygon_source is None:
                    raise QgsProcessingException("Please specify a polygon layer for area of interest")

                # Get first feature (from selection if any)
                features = polygon_source.getFeatures()
                try:
                    first_feature = next(features)
                except StopIteration:
                    raise QgsProcessingException("Polygon layer has no features")

                polygon = first_feature.geometry()
                
                # Transform to WGS84 if needed
                if polygon_source.sourceCrs() != QgsCoordinateReferenceSystem('EPSG:4326'):
                    transform = QgsCoordinateTransform(
                        polygon_source.sourceCrs(),
                        QgsCoordinateReferenceSystem('EPSG:4326'),
                        context.project()
                    )
                    polygon.transform(transform)
                
                feedback.pushInfo(f"Processing polygon with {polygon.asWkt()[:50]}...")
                
                # Divide large areas into smaller chunks
                feedback.pushInfo("Dividing area into smaller chunks...")
                small_polygons = self.divide_polygon(polygon, max_area)
                feedback.pushInfo(f"Created {len(small_polygons)} download chunks")
            
            # Authenticate
            feedback.pushInfo("Authenticating with DGT...")
            if not self.authenticate(self._username, self._password, feedback):
                raise QgsProcessingException("Authentication failed")
            
            # Get collections to download
            available_collections = ['LAZ', 'MDS-2m', 'MDS-50cm', 'MDT-2m', 'MDT-50cm']
            # Remove any collections that were not checked in the individual product checkboxes
            checkbox_map = {
                'LAZ': 'DOWNLOAD_LAZ',
                'MDS-2m': 'DOWNLOAD_MDS_2M',
                'MDS-50cm': 'DOWNLOAD_MDS_50CM',
                'MDT-2m': 'DOWNLOAD_MDT_2M',
                'MDT-50cm': 'DOWNLOAD_MDT_50CM'
            }
            available_collections = [
                c for c in available_collections
                if self.parameterAsBool(parameters, checkbox_map[c], context)
            ]

            if collection_indices:
                collections = [available_collections[i] for i in collection_indices]
            else:
                collections = available_collections
            
            feedback.pushInfo(f"Collections to download: {collections}")
            
            # Collect all download URLs
            all_urls_per_collection = {}
            
            if input_method == 0:  # Extent method
                total_chunks = len(small_bboxes)
                
                for i, small_bbox in enumerate(small_bboxes):
                    if feedback.isCanceled():
                        return {}
                    
                    feedback.pushInfo(f"Processing chunk {i+1}/{total_chunks}: {small_bbox}")
                    feedback.setProgress(int(100 * i / total_chunks))
                    
                    # Check session before each chunk
                    if self.is_session_expired() or not self.is_session_valid(feedback):
                        feedback.pushInfo("Session expired or invalid, re-authenticating...")
                        if not self.authenticate(self._username, self._password, feedback):
                            raise AuthenticationError("Re-authentication failed")
                    
                    # Search STAC API
                    stac_response = self.search_stac_api_bbox(small_bbox, collections, delay)
                    
                    if not stac_response.get("features"):
                        feedback.pushInfo(f"No features found for chunk {i+1}")
                        continue
                    
                    # Collect URLs
                    urls_per_collection = self.collect_urls_per_collection(stac_response)
                    
                    # Merge with all URLs
                    for collection, urls in urls_per_collection.items():
                        if collection not in all_urls_per_collection:
                            all_urls_per_collection[collection] = []
                        all_urls_per_collection[collection].extend(urls)
            else:  # Polygon method
                total_chunks = len(small_polygons)
                
                for i, small_polygon in enumerate(small_polygons):
                    if feedback.isCanceled():
                        return {}
                    
                    feedback.pushInfo(f"Processing chunk {i+1}/{total_chunks}")
                    feedback.setProgress(int(100 * i / total_chunks))
                    
                    # Check session before each chunk
                    if self.is_session_expired() or not self.is_session_valid(feedback):
                        feedback.pushInfo("Session expired or invalid, re-authenticating...")
                        if not self.authenticate(self._username, self._password, feedback):
                            raise AuthenticationError("Re-authentication failed")
                    
                    # Search STAC API with polygon geometry
                    stac_response = self.search_stac_api_geometry(small_polygon, collections, delay)
                    
                    if not stac_response.get("features"):
                        feedback.pushInfo(f"No features found for chunk {i+1}")
                        continue
                    
                    # Collect URLs
                    urls_per_collection = self.collect_urls_per_collection(stac_response)
                    
                    # Merge with all URLs
                    for collection, urls in urls_per_collection.items():
                        if collection not in all_urls_per_collection:
                            all_urls_per_collection[collection] = []
                        all_urls_per_collection[collection].extend(urls)
            
            # Remove duplicates
            for collection in all_urls_per_collection:
                seen = set()
                unique_urls = []
                for url, item_id, extension in all_urls_per_collection[collection]:
                    if url not in seen:
                        unique_urls.append((url, item_id, extension))
                        seen.add(url)
                all_urls_per_collection[collection] = unique_urls
            
            # Download files
            total_files = sum(len(urls) for urls in all_urls_per_collection.values())
            downloaded_files = 0
            vrt_files = []
            
            feedback.pushInfo(f"Found {total_files} files to download")
            
            for collection, urls in all_urls_per_collection.items():
                if feedback.isCanceled():
                    return {}
                
                if not urls:
                    continue
                
                feedback.pushInfo(f"Downloading {len(urls)} files from {collection} collection...")
                
                # Create collection directory
                collection_dir = os.path.join(output_folder, collection)
                os.makedirs(collection_dir, exist_ok=True)
                
                # Download files
                for url, item_id, extension in urls:
                    if feedback.isCanceled():
                        return {}
                    
                    success = self.download_file(
                        url, item_id, extension, collection_dir, delay, feedback
                    )
                    
                    downloaded_files += 1
                    feedback.setProgress(int(100 * downloaded_files / total_files))
                    
                    if not success:
                        continue
                
                # Create VRT for raster collections
                if create_vrt and collection in self.raster_collections:
                    feedback.pushInfo(f"Creating VRT for {collection}...")
                    vrt_path = self.create_vrt_for_collection(collection, output_folder, feedback)
                    
                    if vrt_path:
                        vrt_files.append((vrt_path, collection))
                        
                        # Build overviews if requested
                        if build_overviews:
                            self.build_vrt_overviews(vrt_path, feedback)
                        
                        # Load VRT to QGIS if requested
                        if load_vrt:
                            self.load_vrt_to_qgis(vrt_path, collection, feedback)

            # Create boundary layer if requested
            boundary_layer_path = None
            if create_boundary and boundary_output:
                feedback.pushInfo("Creating boundary layer...")
                
                if input_method == 0:  # Extent method
                    boundary_layer_path = self.create_boundary_layer_bbox(
                        small_bboxes, boundary_output, context, feedback
                    )
                else:  # Polygon method
                    boundary_layer_path = self.create_boundary_layer_polygon(
                        small_polygons, boundary_output, context, feedback
                    )
                
                if boundary_layer_path:
                    # Load boundary layer to QGIS
                    boundary_layer = QgsVectorLayer(boundary_layer_path, "DGT Download Boundaries", "ogr")
                    if boundary_layer.isValid():
                        QgsProject.instance().addMapLayer(boundary_layer)
                        feedback.pushInfo("Boundary layer added to QGIS")
            
            # Summary
            feedback.pushInfo("Download process completed!")
            feedback.pushInfo(f"Total files downloaded: {downloaded_files}")
            feedback.pushInfo(f"Collections processed: {len(all_urls_per_collection)}")
            
            if vrt_files:
                feedback.pushInfo(f"VRT files created: {len(vrt_files)}")
                for vrt_path, collection in vrt_files:
                    feedback.pushInfo(f"  - {collection}: {vrt_path}")
            
            # Return results
            results = {
                'OUTPUT_FOLDER': output_folder,
                'DOWNLOADED_FILES': downloaded_files,
                'COLLECTIONS': list(all_urls_per_collection.keys())
            }
            
            if boundary_layer_path:
                results['BOUNDARY_OUTPUT'] = boundary_layer_path
            
            if vrt_files:
                results['VRT_FILES'] = [vrt_path for vrt_path, _ in vrt_files]
            
            return results
            
        except AuthenticationError as e:
            raise QgsProcessingException(f"Authentication failed: {str(e)}")
        except Exception as e:
            feedback.reportError(f"Error in processing: {str(e)}")
            raise QgsProcessingException(f"Processing failed: {str(e)}")


def classFactory(iface):
    """
    Required function for QGIS plugin loading
    """
    return DgtCddDownloaderAlgorithm()
