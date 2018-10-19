# Sentinel2-raster_types
Defines python raster types to enable read and load Sentinel-2 L2A product tiles with ArcGIS Pro.

Sentinel-2 senses visible and infrared spectrum 12 band rasters that are processed by the pipeline. The processing results are L1C - top of the atmosphere and L2A - bottom of the atmosphere raster products available for free on Amazon S3.
https://registry.opendata.aws/sentinel-2/

The products called granules are also cut to 100x100km tiles according to the military grid
https://sentinel.esa.int/documents/247904/1955685/S2A_OPER_GIP_TILPAR_MPC__20151209T095117_V20150622T000000_21000101T000000_B00.kml


"For Level-1C and Level-2A, the granules, also called tiles, are 100x100 km2 ortho-images in UTM/WGS84 projection. Download the Sentinel-2 tiling grid kml.
The UTM (Universal Transverse Mercator) system divides the Earth's surface into 60 zones. Each UTM zone has a vertical width of 6° of longitude and horizontal width of 8° of latitude." - https://sentinel.esa.int/web/sentinel/missions/sentinel-2/data-products

The raster storage on Amazon S3 is organized to a file structure, with metadata and images for every band in separate files and folders. This Sentinel-2 raster type uppon installation defines new raster types within ArcGIS Pro
Sentinel-2-L2A-10mTile which is a 4-band raster (red, green, blue and near infrared) with 10m/px resolution
Sentinel-2-L2A-20mTile which is a 9-band raster with 20m/px resolution
Sentinel-2-L2A-60mTile which is a 11-band raster with 60m/px resolution
build from the respective folders R10m, R20m and R60m imaginery.

To install create a new directory under 
C:\Program Files\ArcGIS\Pro\Resources\Raster\Types\System\
named Sentinel-2-Tile
and copy the python file and raster function templates defined in *.rft.xml files to the directory.
After restarting the ArcGIS Pro new raster types will be available in the Add Rasters to Mosaic Dataset geoprocessing tool.
