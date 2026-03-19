from qgis.core import QgsApplication, QgsMessageLog, Qgis

# Import the provider
from .dgt_cdd_downloader_provider import DgtCddDownloaderProvider

# Check for dependencies
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

class DgtCddDownloaderPlugin:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """
        Constructor.
        :param iface: An interface instance that will be passed to this class
            which provides access to the QGIS application settings and main
            interface objects.
        """
        self.iface = iface
        self.provider = None

    def initGui(self):
        """
        Called when the plugin is loaded in QGIS.
        """
        if not REQUESTS_AVAILABLE:
            self.iface.messageBar().pushMessage(
                "Warning",
                "DGT CDD Downloader plugin requires the 'requests' library. Please install it.",
                level=Qgis.MessageLevel.Critical,
                duration=15
            )
            QgsMessageLog.logMessage(
                "DGT CDD Downloader: Could not import 'requests'. The plugin will be disabled. "
                "Please install it in your QGIS Python environment (e.g., 'py3-pip install requests' in OSGeo4W Shell).",
                'DGT CDD Downloader',
                level=Qgis.MessageLevel.Critical
            )
            return

        self.provider = DgtCddDownloaderProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        """
        Called when the plugin is unloaded.
        """
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
