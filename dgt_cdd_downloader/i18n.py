"""
Portuguese interface text. QGIS in Portuguese shows these strings, any other
language shows the English source text. Technical terms and the Log tab stay in English.
"""

from qgis.core import QgsApplication


HELP_TEMPLATE = """
Download geospatial {data} data from portuguese <a href='https://cdd.dgterritorio.gov.pt'>DGT (Direção-Geral do Território) - CDD Portal</a>.

This tool allows you to:
- {login}
- Select an area of interest using either:
  * A bounding box extent (from map canvas or manual entry)
  * A polygon layer (first feature or selected feature will be used). When set, it replaces the extent.
- Download {data} datasets from DGT CDD Portal ({collections}). {selection}
- Automatically organize files by collection
- Create VRT (Virtual Raster) files for raster collections
- Load VRT files automatically into QGIS
- Create boundary layers showing download areas

VRT, boundary layer, request delay, simultaneous downloads and SSL options are under Advanced Parameters. Two simultaneous downloads roughly double the number of requests sent to the portal.

Requirements:
- Valid credentials for the <a href='https://cdd.dgterritorio.gov.pt'>DGT - CDD Portal</a>
- Internet connection

The tool will automatically handle the authentication process using session cookies and divide large areas into smaller chunks to avoid server overload.

{warning}
"""

HELP_TEMPLATE_PT = """
Serviço de descarregamento de dados geográficos ({data}) do <a href='https://cdd.dgterritorio.gov.pt'>Centro de Dados da DGT (Direção-Geral do Território)</a>.

Esta ferramenta permite:
- {login}
- Selecionar uma área de interesse utilizando:
  * Uma extensão retangular (obtida a partir do mapa ou introduzindo as coordenadas manualmente)
  * Uma camada de polígonos (será usado o primeiro polígono da camada ou o polígono selecionado). Quando definida, substitui a extensão.
- Descarregar as coleções de dados {data} disponíveis no Centro de Dados da DGT ({collections}). {selection}
- Organizar os ficheiros descarregados por coleção
- Criar ficheiros VRT (Virtual Raster) para as coleções de rasters
- Carregar automaticamente os VRT no QGIS
- Criar uma layer com a extensão das áreas de download

As opções de VRT, layer de extensão, tempo de espera, downloads em simultâneo e SSL estão nos Parâmetros Avançados. Dois downloads em simultâneo praticamente duplicam o número de pedidos enviados ao portal.

Requisitos:
- Credenciais válidas do <a href='https://cdd.dgterritorio.gov.pt'>Centro de Dados da DGT</a>
- Ligação à Internet

Esta ferramenta vai gerir automaticamente o processo de autenticação usando cookies de sessão e dividir áreas grandes em partes mais pequenas, respeitando os limites impostos pelo servidor.

{warning}
"""

PORTUGUESE = {
    HELP_TEMPLATE: HELP_TEMPLATE_PT,

    # Toolbox names
    'DGT CDD {} Downloader (password)': 'Download {} do CDD da DGT (password)',
    'DGT CDD {} Downloader (QGIS auth manager)': 'Download {} do CDD da DGT (gestor de autenticação do QGIS)',

    # Parameters
    'Area of Interest (Extent)': 'Área de interesse (extensão)',
    'Area of Interest (Polygon Layer, replaces the extent)':
        'Área de interesse (layer de polígonos, substitui a extensão)',
    'Authentication configuration': 'Configuração de autenticação',
    'Collections to download': 'Coleções a descarregar',
    'Output Folder': 'Pasta de output',
    'Delay between requests (seconds)': 'Tempo de espera entre pedidos (segundos)',
    'Maximum area per request (km²)': 'Área máxima por pedido (km²)',
    'Simultaneous downloads': 'Downloads em simultâneo',
    'Create VRT files for raster collections': 'Criar ficheiros VRT para as coleções de rasters',
    'Build overviews (pyramids) for VRT files': 'Criar pirâmides (overviews) para os ficheiros VRT',
    'Load VRT files into QGIS': 'Carregar os ficheiros VRT no QGIS',
    'Create boundary layer showing download areas': 'Criar layer com a extensão das áreas de download',
    'Disable SSL certificate verification (only for networks with SSL inspection)':
        'Desativar a verificação de certificados SSL (apenas em redes com inspeção SSL)',
    'Boundary Layer': 'Layer de extensão',
    'Azores': 'Açores',

    # Help text fragments
    'orthophotos': 'ortofotos',
    'Choose at least one collection.': 'Escolha pelo menos uma coleção.',
    'If no collection is selected, all of them are downloaded.':
        'Se nenhuma coleção for selecionada, serão descarregadas todas.',
    'Login with DGT credentials stored in the QGIS Authentication System, '
    'using a "Basic Authentication" configuration (username and password)':
        'Fazer login com as credenciais da DGT guardadas no sistema de autenticação '
        'do QGIS, numa configuração "Basic Authentication" (username e password)',
    'Login with your DGT credentials (username and password)':
        'Fazer login no Centro de Dados da DGT com as suas credenciais (username e password)',
    'Warning: the password is visible while typing and may be kept in the Processing '
    'log and history. On shared computers use the "QGIS auth manager" version of this tool.':
        'Atenção: a password fica visível ao escrever e pode ficar guardada no registo e '
        'histórico do Processing. Em computadores partilhados use a versão com o '
        'gestor de autenticação do QGIS desta ferramenta.',

    # Errors the user has to act on
    'Please set an extent or a polygon layer as the area of interest':
        'Defina uma extensão ou uma layer de polígonos como área de interesse',
    'An authentication configuration is required': 'É necessária uma configuração de autenticação',
    'Could not load authentication configuration {}': 'Não foi possível carregar a configuração de autenticação {}',
    'The authentication configuration must use the "Basic Authentication" method, not {}':
        'A configuração de autenticação tem de usar o método "Basic Authentication", e não {}',
    'Username and password are required': 'O username e a password são obrigatórios',
    'Authentication failed - check credentials': 'A autenticação falhou - verifique as credenciais',
    "Could not verify the server's SSL certificate: {}\n"
    "If your network uses SSL inspection, enable 'Disable SSL certificate "
    "verification' under Advanced Parameters.":
        'Não foi possível verificar o certificado SSL do servidor: {}\n'
        'Se a sua rede usa inspeção SSL, ative a opção de desativar a verificação de '
        'certificados SSL nos Parâmetros Avançados.',
    '{}: only {} of {} items returned. Try a smaller maximum area.':
        '{}: só foram devolvidos {} de {} itens. Experimente uma área máxima por pedido mais pequena.',
    '{}: the portal could not search area {}, so tiles there may be missing.':
        '{}: o portal não conseguiu pesquisar a área {}, por isso podem faltar quadrículas nessa zona.',
}


def translate(text: str) -> str:
    """Return the Portuguese text when QGIS is in Portuguese, otherwise the English source"""
    if QgsApplication.locale().startswith('pt'):
        return PORTUGUESE.get(text, text)
    return text
