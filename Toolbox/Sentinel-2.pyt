# -*- coding: utf-8 -*-

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
            shape = arcpy.Polygon(arcpy.Array([arcpy.Point(*pc) for pc in points]), arcpy.SpatialReference(int(wkid)))
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
        outSR = arcpy.Describe(outputFC).spatialReference

        with arcpy.da.InsertCursor(outputFC, ["Id", "Type","Tile", "Timestamp", "Shape@"]) as icur:
            for feature in features:
                geom = feature[4]
                if outSR.factoryCode != geom.spatialReference.factoryCode:
                    geom.projectAs(outSR)
                icur.insertRow((feature[0], feature[1], feature[2], feature[3], geom))

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
    def createMosaicDataset(cls, workspace, mosaicDsName=None, resolution="10m", spatialReference=None):
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
    def addTiles(cls, mosaicDSName, tiles, resolution="10m", cloudMaskFC=None, messages=None):
        processedTiles = []
        failedTiles = []
        for tile in tiles:
            try:
                arcpy.SetProgressorLabel("Adding {0}...".format(tile))
                cls.addTile(mosaicDSName, tile, resolution, cloudMaskFC)
                processedTiles.append(tile)
            except Exception as e:
                failedTiles.append(tile)
                if messages:
                    messages.addWarningMessage("Unable to add tile {0}".format(tile))
                else:
                    arcpy.AddWarning("Unable to add tile {0}".format(tile))
            finally:
                arcpy.SetProgressorPosition()
        arcpy.SetProgressorPosition()
        return (processedTiles, failedTiles)

    @classmethod
    def importTiles(cls, tilesFolder, mosaicDSName, resolution="10m", cloudMaskFC=None, messages=None):
        tiles = cls.listTiles(tilesFolder)
        arcpy.SetProgressor("step", "Adding tiles to mosaic dataset...",
                    0, len(tiles), 1)
        return cls.addTiles(mosaicDSName, tiles, resolution, cloudMaskFC, messages)

@lru_cache(maxsize=128)
def cacheElementTree(path):
        try:
            tree = ET.parse(path)
        except ET.ParseError as e:
            print("Exception while parsing {0}\n{1}".format(path,e))
            return None

        return tree

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Toolbox"
        self.alias = ""

        # List of tool classes associated with this toolbox
        self.tools = [CreateCloudMask, CreateMosaicDataset, AddTiles]

pt_map = {"Sentinel-2 10m, 4 Bands": "10m", "Sentinel-2 20m, 9 Bands": "20m", "Sentinel-2 20m, 10 Bands": "20c"}

class CreateCloudMask(object):
    def __init__(self):
        self.label = "Create Cloud Mask Feature Class"
        self.description = "Creates new featureclass to store vector cloud mask."
        self.canRunInBackground = True

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Input Workspace",
            name="in_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        param0.defaultEnvironmentName = "workspace"

        param1 = arcpy.Parameter(
                displayName="Feature Class Name",
                name="fc_name",
                datatype="GPString",
                parameterType="Required",
                direction="Input")
        
        param2 = arcpy.Parameter(
                displayName="Spatial Reference",
                name="spatial_reference",
                datatype="GPCoordinateSystem",
                parameterType="Optional",
                direction="Input")
        
        param3 = arcpy.Parameter(
            displayName="Output Feature Class",
            name="out_featuresClass",
            datatype="DEFeatureClass",
            parameterType="Derived",
            direction="Output")

        return [param0, param1, param2, param3]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        cloudmask_featureclass = CloudMask.createFeatureClass(
                parameters[0].valueAsText, parameters[1].valueAsText, parameters[2].valueAsText)

        parameters[3] = cloudmask_featureclass
        return cloudmask_featureclass

class CreateMosaicDataset(object):
    def __init__(self):
        self.label = "Create Mosaic Dataset"
        self.description = "Creates new Mosaic Dataset with Sentinel-2 band defintions."
        self.canRunInBackground = True

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Input Workspace",
            name="in_workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        param0.defaultEnvironmentName = "workspace"

        param1 = arcpy.Parameter(
                displayName="Mosaic Dataset Name",
                name="mds_name",
                datatype="GPString",
                parameterType="Required",
                direction="Input")
        
        param2 = arcpy.Parameter(
                displayName="Raster Product Type",
                name="raster_product_type",
                datatype="GPString",
                parameterType="Required",
                direction="Input")

        param2.filter.type = "ValueList"
        param2.filter.list = list(pt_map.keys())

        param3 = arcpy.Parameter(
                displayName="Spatial Reference",
                name="spatial_reference",
                datatype="GPCoordinateSystem",
                parameterType="Optional",
                direction="Input")

        param4 = arcpy.Parameter(
            displayName="Output Mosaic Dataset",
            name="out_mosaicDataset",
            datatype="DEMosaicDataset",
            parameterType="Derived",
            direction="Output")
        return [param0, param1, param2, param3, param4]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        mosaic_dataset = SentinelImporter.createMosaicDataset(
                parameters[0].valueAsText,
                parameters[1].valueAsText,
                pt_map[parameters[2].valueAsText],
                parameters[3].valueAsText
        )
        parameters[4] = mosaic_dataset
        return mosaic_dataset

class AddTiles(object):
    def __init__(self):
        self.label = "Add Tiles to Mosaic Dataset"
        self.description = "Adds all raster tiles from a directory (recursively) to mosaic dataset."
        self.canRunInBackground = True

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Input Folder",
            name="in_folder",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
                displayName="Mosaic Dataset",
                name="mds_name",
                datatype="DEMosaicDataset",
                parameterType="Required",
                direction="Input")
        
        param2 = arcpy.Parameter(
                displayName="Raster Product Type",
                name="raster_product_type",
                datatype="GPString",
                parameterType="Required",
                direction="Input")

        param2.filter.type = "ValueList"
        param2.filter.list = list(pt_map.keys())

        param3 = arcpy.Parameter(
                displayName="Cloud Mask FeatureClass",
                name="cloud_mask",
                datatype="DEFeatureClass",
                parameterType="Optional",
                direction="Input")

        return [param0, param1, param2, param3]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        loadedRasters = SentinelImporter.importTiles(
                parameters[0].valueAsText, 
                parameters[1].valueAsText, 
                pt_map[parameters[2].valueAsText], 
                parameters[3].valueAsText if len(parameters)>3 else None,
                messages
            )
        
        messages.addMessage("Successfully added {0} tiles.".format(len(loadedRasters[0])))
        if len(loadedRasters[1]) > 0:
            messages.addWarningMessage("Failed to load {0} tiles.".format(len(loadedRasters[1])))

        return

