# DGT CDD Data Downloader


[Português](#intro) / [English](#overview)


## Intro

Facilita o download de ficheiros do Centro de Dados da DGT, para quem não possa esperar pela API que a DGT ainda irá disponibilizar.

Neste momento, só é possível descarregar ficheiros a partir do site do [CDD](https://cdd.dgterritorio.gov.pt/), desenhando áreas de interesse até 200km², clicando em cada quadrícula para adicionar à lista de downloads, e nesta lista ainda clicar no botão de descarregar todos os ficheiros selecionados.

Para quem precisa de áreas maiores que 200km² o processo é muito moroso, e potencialmente indutor de Síndrome do túnel cárpico [^1], isto enquanto não há uma API para o efeito!

Inicialmente foi criado um script permite a descarga "automática" para áreas maiores, que acabou por evoluir para um plugin [QGIS](https://qgis.org/), com o intuito de facilitar o acesso aos dados de todos os utilizadores.


> [!IMPORTANT]  
> Ferramenta desenvolvida pela comunidade e não afiliada com a Direção-Geral do Território.

### Créditos
À [DGT](https://www.dgterritorio.gov.pt/) o nosso agradecimento pela iniciativa de disponibilizar todos os dados do levantamento LIDAR para o território nacional continental, de forma livre e gratuita. Uma iniciativa com um alcance enorme no exercício de cidadania no nosso País.

Versão 0.3.0: obrigado a [Sergio Pinheiro](https://github.com/sergiuspinheiro) pela contribuição nas coleções ORTOS.

## Instalação / Uso

### Plugin QGIS

* Instala via o gestor de módulos (em breve), ou instala via ZIP, com recurso a este [ficheiro.](https://github.com/qgispt/dgtcd_downer/raw/refs/heads/main/dgt_cdd_downloader.zip)
* O plugin fica disponível para uso na Toolbox do Processing do QGIS, com quatro ferramentas:

| Ferramenta | Dados | Autenticação |
|---|---|---|
| Download LiDAR do CDD da DGT (password) | LAZ, MDS, MDT (continente e Açores) | Utilizador e palavra-passe em texto |
| Download LiDAR do CDD da DGT (gestor de autenticação do QGIS) | LAZ, MDS, MDT (continente e Açores) | Gestor de autenticação do QGIS |
| Download ORTOS do CDD da DGT (password) | Ortofotos 1995-2025 (continente) | Utilizador e palavra-passe em texto |
| Download ORTOS do CDD da DGT (gestor de autenticação do QGIS) | Ortofotos 1995-2025 (continente) | Gestor de autenticação do QGIS |

A janela do plugin aparece em português se o QGIS estiver em português, e em inglês nos restantes idiomas. As mensagens do separador _Log_ ficam sempre em inglês.

<img width="900" src="./img/1.png" />

* o uso do plugin é muito simples, contudo é obrigatório conta no [CDD](https://cdd.dgterritorio.gov.pt/)

<img width="900" src="./img/2.png" />

1. Define a área de interesse com uma extensão (por exemplo, a do canvas do QGIS)
2. Em alternativa, escolhe uma layer de polígonos, que substitui a extensão (pode, por exemplo, ser uma freguesia ou um concelho selecionado na layer da CAOP, ou um polígono representando a extensão de uma estrada ou de uma linha elétrica)
3. **Nas ferramentas _password_, coloca o teu utilizador ou e-mail associado à conta do CDD e respetiva palavra-passe. Nas ferramentas _QGIS auth manager_, escolhe a configuração de autenticação**
4. Escolhe qual ou quais a coleções que pretendes fazer download. **No LiDAR, se nenhuma for selecionada, será realizado o download de todas. Nos ORTOS é preciso escolher pelo menos uma (por omissão, a mais recente)**
5. Aconselhamos a definir a pasta de _output_ para os ficheiros não ficarem perdidos na past _temp_ ou _tmp_
6. Não há, mas vai tomar ☕!!

#### Gestor de autenticação do QGIS

Evita escrever a palavra-passe na janela, onde fica visível e pode ficar guardada no registo e histórico do Processing. Na ferramenta, clica no botão ➕ junto a _Authentication configuration_, escolhe o método **Basic Authentication** e coloca o utilizador e a palavra-passe do CDD. Só tens de o fazer uma vez.

#### Parâmetros avançados

Nos parâmetros avançados encontras as restantes opções, que podes normalmente ignorar: tempo de espera entre pedidos, área máxima por pedido, downloads em simultâneo (1 por omissão, 2 no máximo, o que praticamente duplica os pedidos enviados ao portal), criação e carregamento de VRT, pirâmides (só LiDAR, os ortos já as trazem), layer com a extensão dos downloads (guardada na pasta de _output_) e a opção para desativar a verificação de certificados SSL, apenas para redes com inspeção SSL.

#### Açores

As coleções dos Açores estão no fim da lista, identificadas com (Açores). Os ficheiros destas coleções nem sempre têm o mesmo sistema de coordenadas: quando isso acontece é criado um VRT por sistema, por exemplo `ACORES-MDE-1.vrt` e `ACORES-MDE-1_EPSG5014.vrt`. O portal pode falhar em algumas pesquisas de `ACORES-LAZ`; o plugin repete-as em áreas mais pequenas e avisa no _Log_ se ficar alguma zona por pesquisar.

#### Versões dos ficheiros

O plugin e o script acrescentam a versão do tile ao nome do ficheiro, por exemplo `MDS-50cm-163556-07-2025_v02.tif`. Quando a DGT corrige um tile, a execução seguinte descarrega a nova versão e mantém o ficheiro antigo, que podes apagar. Os VRT usam apenas a versão mais recente de cada tile. Os ficheiros descarregados antes desta alteração não têm a versão no nome, por isso são descarregados de novo. As coleções dos Açores não têm versões, por isso os nomes não mudam.


### Linha de comandos

Se quiseres algo mais _raw_ e "simples", podes apenas correr o [script no teu PC](https://raw.githubusercontent.com/qgispt/dgtcd_downer/refs/heads/main/dgtcd_downer.py)

**Requisitos:**
  * O python instalado no sistema
  * conta no [CDD](https://cdd.dgterritorio.gov.pt/)

Verifica os agrumentos necessários para este funcionar com:

```bash
   
   python3 dgtcd_downer.py -h
   
```

<img width="900" src="./img/3.png" />



**Exemplo numa só linha.** A coleção é obrigatória, com `-c` ou `--collections`. Se não indicares `--password`, o script pede-a sem a mostrar:

```bash

   python3 dgtcd_downer.py --bbox "-9.2 38.7 -9.1 38.8" --username eu@mail.pt -c LAZ,MDT-50cm

```

Coleções disponíveis:

* Continente: `LAZ`, `MDS-2m`, `MDS-50cm`, `MDT-2m`, `MDT-50cm`
* Ortofotos (continente): `ORTOS-2025`, `ORTOS-2021`, `ORTOS-2018`, `ORTOS-2015`, `ORTOS-2012`, `ORTOS-2010`, `ORTOS-2007`, `ORTOS-2004`, `ORTOS-1995`
* Açores: `ACORES-LAZ`, `ACORES-MDE-1`, `ACORES-MDE-5`, `ACORES-MDE-10`, `ACORES-MDS-1`, `ACORES-MDS-5`, `ACORES-MDS-10`

Com `-w 2` são feitos dois downloads em simultâneo (o padrão é 1), o que praticamente duplica os pedidos enviados ao portal.

**Ou então, corre o script em modo interativo**

1. Na linha de comandos

```bash
   
   python3 dgtcd_downer.py -i
   
```
2. Coloca o teu utilizador ou e-mail associado à conta do CDD

3. Coloca a tua palavra-passe

4. Necessários os valores da bounding box em WGS84, separados por vírgulas, tipo '-8.93493538, 39.40470256, -8.91592816, 39.41428785'
   
   podes usar o plugin [Lat Lon Tools](https://plugins.qgis.org/plugins/latlontools/) do QGIS, para copiar a extensão no canvas. Lembra-te **WGS84**
  
5. Define a pasta para onde queres realizar o download, 
6. Define os segundos de espera entre cada request/download 
7. Define quantos downloads em simultâneo queres, 1 ou 2
8. Seleciona o número das coleções (ex: 1,3). É obrigatório escolher pelo menos uma
9. E vai tomar ☕!!

**Ou usa num notebook Jupyter ou noutro script Python.** Coloca o `dgtcd_downer.py` na pasta do notebook. A palavra-passe é pedida quando for preciso, para não ficar guardada no notebook:

```python
from dgtcd_downer import download

resultado = download(
    bbox=[-9.2, 38.7, -9.1, 38.8],
    username="eu@mail.pt",
    collections=["LAZ", "MDT-50cm"],
    output_dir="dados",
    workers=1,
)
print(resultado)  # {'downloaded': 12, 'skipped': 0, 'failed': 0, 'output_dir': 'dados'}
```

Para usar a extensão de uma layer (shp, gpkg, kml...), calcula a bbox no notebook. São descarregados todos os ficheiros dentro do retângulo, não apenas os que tocam no polígono:

```python
import geopandas as gpd

bbox = gpd.read_file("area.gpkg").to_crs(4326).total_bounds
download(bbox=bbox, username="eu@mail.pt", collections=["LAZ"])
```


> [!WARNING]  
> Em muitas redes de entidades / instituições, por questões de segurança, portas estranhas como a 8081 ou 9000 podem não se encontrar acessíveis e nesses casos o plugin/script pode não funcionar.

## TODO

* Possibilidade de download sem o frontend atual ✅
* Adicionar a feature essencial...barra de progresso ✅
* Autenticação no script ✅
* Possibilidade de download de uma coleção apenas, várias ou todas ✅
* Definir pastas separadas para cada coleção ✅
* Usar params de entrada para permitir scriptar em batch ✅
* Criar vrt de cada coleção descarregada ✅ (no script do QGIS)
* Criar um tile index das coleções descarregadas ❌
* Criar Curvas de Nível como opção do script ❌
* Fazer um micro how-to para utilização ✅ (mais ou menos feito)
* Fazer um UI 💀💀💀... hmmmm nahhh! Ou melhor no QGIS! ✅

> [!WARNING]  
> Com a eventual disponibilização da API, o script poderá ficar obsoleto.





---
---

## Overview

It simplifies the download of files from the DGT Data Center, for those who can't wait for the API that the DGT is yet to make available.

At the moment, you can only download files from the [CDD website](https://cdd.dgterritorio.gov.pt/) by drawing areas of interest up to 200km², clicking on each square to add it to the download list, and then clicking on the download button for all the selected files.

For those who need areas larger than 200km², the process is very time-consuming, and potentially induces carpal tunnel syndrome [^1], as long as there is no API for the purpose, yet!

Initially, a script was created to allow "automatic" downloading for larger areas, which eventually evolved into a [QGIS](https://qgis.org/) plugin, in order to facilitate access to the data for all users.

> [!IMPORTANT] 
> Tool developed by the community and not affiliated with the Direção-Geral do Território.

## Credits
We would like to thank the DGT for the initiative to make all the LIDAR survey data for the national mainland available, free of charge. This initiative has a huge impact on the exercise of citizenship in our country.

Version 0.3.0: thanks to [Sergio Pinheiro](https://github.com/sergiuspinheiro) for the contribution on the ORTOS collections.


## Install / Usage

### Plugin QGIS

* Install via the plugin manager (coming soon), or install via ZIP, using this [file](https://github.com/qgispt/dgtcd_downer/raw/refs/heads/main/dgt_cdd_downloader.zip)
* The plugin is available for use in the QGIS Processing Toolbox, with four tools:

| Tool | Data | Authentication |
|---|---|---|
| DGT CDD LiDAR Downloader (password) | LAZ, MDS, MDT (mainland and Azores) | Plain text username and password |
| DGT CDD LiDAR Downloader (QGIS auth manager) | LAZ, MDS, MDT (mainland and Azores) | QGIS authentication manager |
| DGT CDD ORTOS Downloader (password) | Orthophotos 1995-2025 (mainland) | Plain text username and password |
| DGT CDD ORTOS Downloader (QGIS auth manager) | Orthophotos 1995-2025 (mainland) | QGIS authentication manager |

The plugin window is shown in Portuguese when QGIS is in Portuguese, and in English in any other language. Messages in the _Log_ tab are always in English.

<img width="900" src="./img/1.png" />

* Use of the plugin is very simple, but a [CDD](https://cdd.dgterritorio.gov.pt/) account is required.

<img width="900" src="./img/2.png" />

1. Set the area of interest with an extent (for instance, the QGIS canvas extent)
2. Alternatively, choose a polygon layer, which replaces the extent (it can be, for instance, a polygon representing an administrative boundary selected from CAOP, or a polygon representing a road or a powerline)
3. **In the _password_ tools, enter your username or e-mail address associated with your CDD account and password. In the _QGIS auth manager_ tools, choose the authentication configuration.**
4. Choose which collection(s) you want to download. **For LiDAR, if none are selected, all will be downloaded. For ORTOS at least one is required (the most recent by default).**
5. We advise you to set the _output_ folder so that the files don't get lost in the _temp_ or _tmp_ folder.
6. There isn't one, but you should go take some ☕!!!

#### QGIS authentication manager

It avoids typing the password in the dialog, where it is visible and may be kept in the Processing log and history. In the tool, click the ➕ button next to _Authentication configuration_, choose the **Basic Authentication** method and enter your CDD username and password. You only need to do this once.

#### Advanced parameters

_Advanced Parameters_ holds the remaining options, which you can usually ignore: delay between requests, maximum area per request, simultaneous downloads (1 by default, 2 at most, which roughly doubles the requests sent to the portal), VRT creation and loading, overviews (LiDAR only, orthophotos already include them), a layer with the download boundaries (saved in the _output_ folder) and the option to disable SSL certificate verification, only for networks with SSL inspection.

#### Azores

The Azores collections are at the end of the list, marked (Azores). Files in these collections do not always share a coordinate system: when that happens, one VRT is created per system, for instance `ACORES-MDE-1.vrt` and `ACORES-MDE-1_EPSG5014.vrt`. The portal can fail on some `ACORES-LAZ` searches; the plugin retries them over smaller areas and warns in the _Log_ if any area is left unsearched.

#### File versions

The plugin and the script add the tile version to the file name, for instance `MDS-50cm-163556-07-2025_v02.tif`. When DGT corrects a tile, the next run downloads the new version and keeps the old file, which you can delete. VRTs use only the latest version of each tile. Files downloaded before this change have no version in their name, so they are downloaded again. The Azores collections have no versions, so their names do not change.


### Command line

If you want something more _raw_ and “simple”, you can just run the [script on your PC](https://raw.githubusercontent.com/qgispt/dgtcd_downer/refs/heads/main/dgtcd_downer.py)

**Requirements**
  * python installed on the system
  * [CDD account](https://cdd.dgterritorio.gov.pt/)

Check the agruments needed for this to work with:

```bash
   
   python3 dgtcd_downer.py -h
   
```

<img width="900" src="./img/3.png" />



**One-line example.** The collection is required, with `-c` or `--collections`. If you leave out `--password`, the script asks for it without showing it:

```bash

   python3 dgtcd_downer.py --bbox "-9.2 38.7 -9.1 38.8" --username me@mail.pt -c LAZ,MDT-50cm

```

Available collections:

* Mainland: `LAZ`, `MDS-2m`, `MDS-50cm`, `MDT-2m`, `MDT-50cm`
* Orthophotos (mainland): `ORTOS-2025`, `ORTOS-2021`, `ORTOS-2018`, `ORTOS-2015`, `ORTOS-2012`, `ORTOS-2010`, `ORTOS-2007`, `ORTOS-2004`, `ORTOS-1995`
* Azores: `ACORES-LAZ`, `ACORES-MDE-1`, `ACORES-MDE-5`, `ACORES-MDE-10`, `ACORES-MDS-1`, `ACORES-MDS-5`, `ACORES-MDS-10`

With `-w 2` two files are downloaded at the same time (the default is 1), which roughly doubles the requests sent to the portal.

**Or else, run the script in interactive mode**

1. On the command line

```bash
   
   python3 dgtcd_downer.py -i
   
```
2. Enter your username or e-mail address associated with the CDD account

3. Enter your password

4. You need the bounding box values in WGS84, separated by commas, like ‘-8.93493538, 39.40470256, -8.91592816, 39.41428785’.
   
   you can use the QGIS plugin [Lat Lon Tools](https://plugins.qgis.org/plugins/latlontools/) to copy the extension into the canvas. Remember **WGS84**
  
5. Define the folder you want to download to,
6. Set the number of seconds to wait between each request/download
7. Set how many simultaneous downloads you want, 1 or 2
8. Select the collection numbers (e.g. 1,3). At least one is required
9. And you should go take some ☕ !!!

**Or use it in a Jupyter notebook or another Python script.** Put `dgtcd_downer.py` in the notebook's folder. The password is asked for when needed, so it stays out of the notebook:

```python
from dgtcd_downer import download

result = download(
    bbox=[-9.2, 38.7, -9.1, 38.8],
    username="me@mail.pt",
    collections=["LAZ", "MDT-50cm"],
    output_dir="data",
    workers=1,
)
print(result)  # {'downloaded': 12, 'skipped': 0, 'failed': 0, 'output_dir': 'data'}
```

To use the extent of a layer (shp, gpkg, kml...), compute the bbox in the notebook. Every file inside the rectangle is downloaded, not only those touching the polygon:

```python
import geopandas as gpd

bbox = gpd.read_file("area.gpkg").to_crs(4326).total_bounds
download(bbox=bbox, username="me@mail.pt", collections=["LAZ"])
```

> [!WARNING] 
> In many networks of organizations / institutions, for security reasons, strange ports such as 8081 or 9000 may not be accessible and in these cases the plugin/script may not work.

## TODO

* Possibility of downloading without the current frontend ✅
* Add essential feature...progress bar ✅
* Authentication in the script ✅
* Possibility of downloading just one collection, several or all ✅
* Define separate folders for each collection ✅
* Use input params to allow batch scripting ✅
* Create vrt of each downloaded collection ✅ (in QGIS script)
* Create a tile index of the downloaded collections ❌
* Create contour lines as a script option ❌
* Make a micro how-to for use ✅ (more or less done)
* Make a UI 💀💀💀... hmmmm nahhh! Or better in QGIS! ✅


> [!WARNING] 
> With the eventual availability of the API, the script may become obsolete.




[^1]: https://duckduckgo.com/?t=ftsa&q=carpal+tunnel+syndrome&ia=web
