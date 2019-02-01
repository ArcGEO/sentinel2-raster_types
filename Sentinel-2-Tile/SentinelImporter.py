import arcpy
import datetime
import os
from functools import lru_cache
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

class CloudMask(object):
    ns = {"eop": "http://www.opengis.net/eop/2.0", "gml": "http://www.opengis.net/gml/3.2"}

    @classmethod
    def parseFeatures(cls, maskGmlFile):
        tree = cacheElementTree(maskGmlFile)
        wkid = tree.find('./gml:boundedBy/gml:Envelope', cls.ns).attrib["srsName"].split(":")[-1]
        rids = tree.getroot().attrib["{"+cls.ns["gml"]+"}id"].split("_")
        ts = datetime.datetime.strptime(rids[6], '%Y%m%dT%H%M%S')
        tile = rids[8]
        features = []
        maskFeatures = tree.findall('.//eop:MaskFeature', cls.ns)
        for feature in maskFeatures:
            fid = (feature.attrib["{"+cls.ns["gml"]+"}id"])
            ftype = feature.find("eop:maskType", cls.ns).text
            parray = feature.find("eop:extentOf/gml:Polygon/gml:exterior/gml:LinearRing/gml:posList", cls.ns).text
            coords = [int(coor) for coor in parray.split(" ")]
            points = [[coords[2*i], coords[2*i+1]] for i in range(len(coords)//2)]
            shape = arcpy.Polygon(arcpy.Array([arcpy.Point(*pc) for pc in points]))
            features.append((fid, ftype, tile, ts, shape))
        return features

    @classmethod
    def createFeatureClass(cls, workspace, fcname, spatialReference):
        """ A polygon featureclass with attributes Id[Text(20)], Type[Text(20)], Tile[Text(20)], Timestamp[Date], Shape[Polygon] is expected in outputFC """
        fcl = arcpy.management.CreateFeatureclass(workspace, fcname, "POLYGON", None, "DISABLED", "DISABLED", spatialReference, None, 0, 0, 0, None)
        arcpy.management.AddField(fcl, "Id", "TEXT", field_length=20)
        arcpy.management.AddField(fcl, "Type", "TEXT", field_length=20)
        arcpy.management.AddField(fcl, "Tile", "TEXT", field_length=20)
        arcpy.management.AddField(fcl, "Timestamp", "Date")
  
        return fcl

    @classmethod
    def insertFeatures(cls, features, outputFC):
        """ A polygon featureclass with attributes Id[Text(20)], Type[Text(20)], Tile[Text(20)], Timestamp[Date], Shape[Polygon] is expected in outputFC """
        with arcpy.da.InsertCursor(outputFC, ["Id", "Type","Tile", "Timestamp", "Shape@"]) as icur:
            for feature in features:
                icur.insertRow((feature[0], feature[1], feature[2], feature[3], feature[4]))

    @classmethod
    def appendFeatures(cls, maskGmlFile, outputFeatureClass):
        features = cls.parseFeatures(maskGmlFile)
        cls.insertFeatures(features, outputFeatureClass)

class SentinelImporter(object):

    @classmethod
    def createFileGDB(cls, fullName):
        """ fullName should be something like D:/temp/newDB.gdb """
        arcpy.management.CreateFileGDB(fullName[:-1-len(fullName.split("/")[-1])], fullName.split("/")[-1])
        print("FGDB created.")

    @classmethod
    def createMosaicDataset(cls, workspace, mosaicDsName=None, resolution="10m", spatialReference):
        """ if mosaicDSName is none it generates a new name in the form of THHMMSS. """
        bands = {"10m": "B02 458 522;B03 543 577;B04 650 680;B08 784 899",
                 "20m": "B02 458 522;B03 543 577;B04 650 680;B05 698 712;B06 733 747;B07 773 793;B8A 855 875;B11 1565 1655;B12 2100 2280",
                 "20c": "B00 0 0;B02 458 522;B03 543 577;B04 650 680;B05 698 712;B06 733 747;B07 773 793;B8A 855 875;B11 1565 1655;B12 2100 2280" }

        dt = datetime.datetime.now()
        mosaicDs = "T{0:02}{1:02}{2:02}".format(dt.hour, dt.minute, dt.second) if not mosaicDsName else mosaicDsName
        arcpy.management.CreateMosaicDataset(workspace, mosaicDs, spatialReference,
                 None, None, "CUSTOM", bands[resolution])
        print("Mosaic dataset created.")
        return workspace + "/" + mosaicDs

    @classmethod
    def addTile(cls, mosaicDSName, tileMetadataPath, resolution="10m", cloudMaskFC=None):
        res = "20mCloud" if resolution == "20c" else resolution
        arcpy.management.AddRastersToMosaicDataset(mosaicDSName, "Sentinel-2-L2A-" + res + "Tile", tileMetadataPath)
        if cloudMaskFC:
            CloudMask.appendFeatures(os.path.join(tileMetadataPath[:-12], "qi", "MSK_CLOUDS_B00.gml"), cloudMaskFC)
        print("Tile {0} added.".format(tileMetadataPath))

    @classmethod
    def listTiles(cls, tilesFolder):
        tiles = []
        for (dirpath, dirnames, filenames) in os.walk(tilesFolder):
            for filename in filenames:
                if filename.lower() == "metadata.xml":
                    tiles.append(os.path.join(dirpath, filename))
        return tiles

    @classmethod
    def addTiles(cls, mosaicDSName, tiles, resolution="10m", cloudMaskFC=None):
        processedTiles = []
        failedTiles = []
        for tile in tiles:
            try:
                print("Adding tile {0}...".format(tile))
                cls.addTile(mosaicDSName, tile, resolution, cloudMaskFC)
                processedTiles.append(tile)
            except Exception as e:
                failedTiles.append(tile)
        return (processedTiles, failedTiles)

    @classmethod
    def importTiles(cls, tilesFolder, mosaicDSName, resolution="10m", cloudMaskFC=None):
        tiles = cls.listTiles(tilesFolder)
        return cls.addTiles(mosaicDSName, tiles, resolution, cloudMaskFC)

@lru_cache(maxsize=128)
def cacheElementTree(path):
        try:
            tree = ET.parse(path)
        except ET.ParseError as e:
            print("Exception while parsing {0}\n{1}".format(path,e))
            return None

        return tree

if __name__ == '__main__':
    workspace = arcpy.env.workspace
    # Create Tile Mask FeatureClass
    cloudmask_featureclass = CloudMask.createFeatureClass(workspace, "CloudMask", arcpy.SpatialReference(32634))

    # Create Mosaic Dataset
    mosaic_dataset = SentinelImporter.createMosaicDataset(workspace, "S2-10m", "10m", arcpy.SpatialReference(32634))

    # Load Rasters
    loadedRasters = SentinelImporter.importTiles("E:/Sentinel_tiles_from_amazonS3/", mosaic_dataset, "10m", cloudmask_featureclass)

    print("--------- FAILED TILES ------------")
    print(loadedRasters[1])
    print("Successfully added {0} tiles.".format(len(loadedRasters[0])))

