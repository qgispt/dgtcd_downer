from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon
import os

# Import the algorithm
from .processing_algorithm import DgtCddDownloaderAlgorithm


class DgtCddDownloaderProvider(QgsProcessingProvider):
    """
    This class registers the DGT CDD Downloader algorithm with the Processing framework.
    """

    def __init__(self):
        super().__init__()

    def loadAlgorithms(self, *args, **kwargs):
        """
        Loads all algorithms belonging to this provider.
        """
        # Instantiate the algorithm and add it directly.
        # The parent class handles storing it.
        alg = DgtCddDownloaderAlgorithm()
        self.addAlgorithm(alg)

    def id(self, *args, **kwargs):
        """
        Returns the unique provider id.
        """
        return 'dgt_cdd_downloader_provider'

    def name(self, *args, **kwargs):
        """
        Returns the provider name, used for the group in the Processing toolbox.
        """
        return self.tr("DGT CDD Portal")

    def longName(self, *args, **kwargs):
        """
        Returns a longer version of the provider name.
        """
        return self.name()

    def icon(self):
        """
        Returns the provider's icon.
        """
        icon_path = os.path.join(
            os.path.dirname(__file__),
            'icon.png'
        )
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon()
