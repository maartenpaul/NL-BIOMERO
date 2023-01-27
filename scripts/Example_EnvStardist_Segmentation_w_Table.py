#!/opt/omero/server/stardistenv/bin/python
# -*- coding: utf-8 -*-
#
# Original work Copyright (C) 2014 University of Dundee
#                                   & Open Microscopy Environment.
#                    All Rights Reserved.
# Modified work Copyright 2022 Torec Luik, Amsterdam UMC
# Use is subject to license terms supplied in LICENSE.txt
#
# Example script for segmentation using StarDist
# from a stardist python environment

import subprocess
import omero
import omero.gateway
from omero.gateway import BlitzGateway
from omero import scripts
from omero.rtypes import rstring, rlong, robject, unwrap, rint, wrap
from stardist.models import StarDist2D
from stardist import random_label_cmap
from csbdeep.utils import normalize
# from skimage import util, measure
# import pandas as pd
import matplotlib.pyplot as plt
import os
import time


_DEFAULT_DATA_TYPE = "Image"
_DEFAULT_MODEL = "2D_versatile_fluo"
_VALUES_MODELS = [rstring(_DEFAULT_MODEL)]
_VALUES_DATA_TYPE = [rstring(_DEFAULT_DATA_TYPE)]
_PARAM_DATA_TYPE = "Data_Type"
_PARAM_IDS = "IDs"
_PARAM_MODEL = "Model"
RUN_ON_GPU_NS = "GPU"
SCRIPT_NAME = 'StarDistTable.py'


def runStarDist(scriptParams, image_np):
    print(scriptParams)
    # creates a pretrained model
    model = StarDist2D.from_pretrained(scriptParams[_PARAM_MODEL])
    labels, polygons = model.predict_instances(normalize(image_np))
    print(labels)
    return labels, image_np, polygons


def saveImageToOmero(labels, img, image, name, conn):
    # Save image
    plt.figure(figsize=(8, 8))
    plt.imshow(img if img.ndim == 2 else img[..., 0], clim=(0, 1), cmap='gray')
    plt.imshow(labels, cmap=random_label_cmap(), alpha=0.5)
    plt.axis('off')
    plt.savefig(name)

    # attach the png to the image
    file_ann = conn.createFileAnnfromLocalFile(
        name, mimetype="image/png")
    print("Attaching %s to image" % name)
    image.linkAnnotation(file_ann)

    print("Attaching FileAnnotation to Image: ", "File ID:",
          file_ann.getId(), ",", file_ann.getFile().getName(), "Size:",
          file_ann.getFile().getSize())
    os.remove(name)

    return image, file_ann


def getImageFromOmero(client, id):
    # we can now create our Blitz Gateway by wrapping the client object
    conn = BlitzGateway(client_obj=client)
    image = conn.getObject("Image", id)
    print(image.getName(), image)
    print(image.getName(), image.getDescription())
    # Retrieve information about an image.
    print(" X:", image.getSizeX())
    print(" Y:", image.getSizeY())
    print(" Z:", image.getSizeZ())
    print(" C:", image.getSizeC())
    print(" T:", image.getSizeT())

    z = image.getSizeZ() / 2
    t = 0
    c = 0
    pixels = image.getPrimaryPixels()
    result_img = pixels.getPlane(z, c, t).astype('uint8')

    return result_img, image, conn


# def saveROIsToGeoJson():
#     # From github/ome/omero-guide-python/blob/master/notebooks/idr0062_prediction.ipynb
#     # Convert into Polygon and add to Geometry Collection
#     from geojson import Feature, FeatureCollection, Polygon
#     import geojson
#     c = 1
#     shapes = []
#     for i in range(len(results_details)):
#         details = results_details[i]
#         for obj_id, region in enumerate(details['coord']):
#             coordinates = []
#             x = region[1]
#             y = region[0]
#             for j in range(len(x)):
#                 coordinates.append((float(x[j]), float(y[j])))
#             # append the first coordinate to close the polygon
#             coordinates.append(coordinates[0])
#             shape = Polygon(coordinates)
#             properties = {
#                 "stroke-width": 1,
#                 "z": i,
#                 "c": c,
#             }
#             shapes.append(Feature(geometry=shape, properties=properties))    

#     gc = FeatureCollection(shapes)
    
#     # Save the shapes as geojson
#     geojson_file = "stardist_shapes_%s.geojson" % image_id
#     geojson_dump = geojson.dumps(gc, sort_keys=True)
#     with open(geojson_file, 'w') as out:
#         out.write(geojson_dump)

def saveROIsToOmero(image, image_id, polygons, conn):
    # image = omero.model.ImageI(image_id, True)
    image = image._obj
    rois = []
    z = 0
    # Convert into Polygon
    # From github/ome/omero-guide-python/blob/master/notebooks/idr0062_prediction.ipynb
    print(image, type(image))
    for obj_id, region in enumerate(polygons['coord']):
        roi = omero.model.RoiI()
        roi.setName(rstring("Object %s" % obj_id))
        polygon = omero.model.PolygonI()
        x = region[1]
        y = region[0]
        points = " ".join(
            ["{},{}".format(x[j], y[j]) for j in range(len(x))])
        polygon.setPoints(rstring(points))
        polygon.theZ = rint(z)
        polygon.theC = rint(0)
        roi.addShape(polygon)
        # Link the ROI and the image
        roi.setImage(image)
        rois.append(roi)  
            
    # Question 2: Save the ROI
    rois = conn.getUpdateService().saveAndReturnArray(rois)
    
    # Get ROI measurements
    return saveRegionTableToOmero(image_id, image, conn)


# def createRegionTable(mask, intensity_image):
#     columns = ['label', 'area', 'intensity_mean']
#     props = measure.regionprops_table(mask, intensity_image, 
#                                       properties=columns)
#     df = pd.DataFrame(props).set_index('label')
#     df['area_x_intensity'] = df['area'] * df['intensity_mean']
#     # df.sort_values('area', ascending=False).head()

    
def saveRegionTableToOmero(image_id, image, conn):
    # Create a table
    table = conn.c.sf.sharedResources().newTable(1, "iroi.h5")
    try:
        # Define columns
        rc = omero.grid.RoiColumn('roi_id', 'Roi ID', None)
        si = omero.grid.LongColumn('shape_id', 'Shape ID', None)
        ac = omero.grid.DoubleColumn('area', 'Area of ROI', None)
        ic = omero.grid.LongColumn('intensity', 'Intensity of ROI', None)
        cols = [rc, ac, ic]
        table.initialize(cols)
        
        # Setup data file
        file = table.getOriginalFile()
        measurement = omero.model.FileAnnotationI()
        measurement.ns = rstring(omero.constants.namespaces.NSMEASUREMENT)
        measurement.setFile(omero.model.OriginalFileI(file.id.val, False))
        measurement.setName(wrap("Stats"))
        measurement = conn.getUpdateService().saveAndReturnObject(measurement)
        
        # Setup link with image
        # image.linkAnnotation(measurement)
        # image = conn.getUpdateService().saveAndReturnObject(image)
        link = omero.model.ImageAnnotationLinkI()
        link.setParent(omero.model.ImageI(image_id, False))
        link.setChild(omero.model.FileAnnotationI(
            measurement.getId().getValue(), False))
        conn.getUpdateService().saveAndReturnObject(link)
        
        # Add data
        roi_svc = conn.getRoiService()
        result = roi_svc.findByImage(image_id, None)
        roi_ids = []
        roi_areas = []
        roi_intensities = []
            
        ### Get Pixel Intensities for ROIs
        shape_ids = []
        for roi in result.rois:
            for s in roi.copyShapes():
                shape_ids.append(s.id.val)
            roi_ids.append(roi.id.val)
        nrois = len(roi_ids)
        ch_index = 0
        # Z/T will only be used if a shape doesn't have Z/T set
        the_z = 0
        the_t = 0
        stats = roi_svc.getShapeStatsRestricted(shape_ids, the_z, the_t, [ch_index])
        for s in stats:
            print("Points", s.pointsCount[ch_index])
            print("Min", s.min[ch_index])
            print("Mean", s.mean[ch_index])
            print("Max", s.max[ch_index])
            print("Sum", s.max[ch_index])
            print("StdDev", s.stdDev[ch_index])
            # roi_ids.append(roi._id)
            roi_areas.append(s.pointsCount[ch_index])
            roi_intensities.append(s.mean[ch_index])
                     
        rc.values = roi_ids
        si.values = shape_ids
        ac.values = roi_areas
        ic.values = roi_intensities
        
        # Add data to table
        table.addData(cols)
    finally:
        table.close()
    
    return measurement, nrois


def scriptPostfix(ts):
    return f"{SCRIPT_NAME}_{ts}"


def runScript():
    """
    The main entry point of the script
    """
    # prints a list of available models
    # models = [rstring(m) for m in StarDist2D.from_pretrained()]

    client = scripts.client(
        SCRIPT_NAME, 
        'Run pretrained StarDist model for segmentation, output a table',
        scripts.String(_PARAM_DATA_TYPE, optional=False, grouping="01",
                       values=_VALUES_DATA_TYPE, default=_DEFAULT_DATA_TYPE),
        scripts.List(_PARAM_IDS,
                     optional=False, grouping="02").ofType(rlong(0)),
        scripts.String(_PARAM_MODEL, optional=False, grouping="03",
                       values=_VALUES_MODELS,
                       default=_DEFAULT_MODEL),
        namespaces=[omero.constants.namespaces.NSDYNAMIC, RUN_ON_GPU_NS],
    )

    try:
        ts = time.time()
        scriptParams = client.getInputs(unwrap=True)

        bashCommandName = "echo $HOSTNAME"
        hostname = subprocess.check_output(['bash', '-c', bashCommandName])
        bashCommandWorker = "echo $OMERO_WORKER_NAME"
        worker = subprocess.check_output(['bash', '-c', bashCommandWorker])

        message = (
            f"This script ran on {worker}:{hostname}\n"
            f"Params: {scriptParams}\n"
            )
        print(message)

        # get the 'IDs' parameter (which we have restricted to 'Image' IDs)
        ids = unwrap(client.getInput("IDs"))
        names = {}
        nroi_arr = {}
        for id in ids:
            # TODO: get images in 1 go (less traffic)
            # TODO: run analysis in parallel (less waiting time)
            # TODO: stream images to the algorithm (less memory)
            # TODO: catch errors, e.g. continue after 1 fails
            image_np, image, conn = getImageFromOmero(client, id)

            result_name = f"SD_{os.path.splitext(image.getName())[0]}_{scriptPostfix(ts)}.png"
            labels, img, polygons = runStarDist(scriptParams, image_np)

            image, file_ann = saveImageToOmero(labels,
                                               img,
                                               image,
                                               result_name,
                                               conn)
            
            names[id] = image.getName()
            table, nrois = saveROIsToOmero(image, id, polygons, conn)
            nroi_arr[id] = nrois
        
        query_service = conn.getQueryService()
        params = omero.sys.ParametersI()
        print(ids)
        params.addIds(ids)
        query = "select l.parent.id from DatasetImageLink as l where l.child.id in (:ids)"
        result = query_service.projection(query, params, conn.SERVICE_OPTS)
        # for r in result:
        #     print("Dataset ID:", r[0].val)
        datasets = {r[0].val for r in result}
        print(f"Datasets {datasets}")
        
        # add nrois to dataset
        # first create our table...
        # columns we want are: imageId, roiId, shapeId, theZ, theT,
        # lineLength, shapetext.
        columns = [
            omero.grid.LongColumn('imageId', '', []),
            omero.grid.LongColumn('nRois', 'Number of ROIs', []),
            omero.grid.StringColumn('imageName', 'Name of Image', 64, []),
            ]
        # create and initialize the table
        table = conn.c.sf.sharedResources().newTable(
            1, f"SDROIs_{scriptPostfix(ts)}")
        table.initialize(columns)
        # Prepare data for adding to OMERO table.
        # print(*nroi_arr, *nroi_arr.values(), type(*nroi_arr), type(*nroi_arr.values()))
        data = [
            omero.grid.LongColumn('imageId', '', list(nroi_arr.keys())),
            omero.grid.LongColumn('nRois', 'Number of ROIs', list(nroi_arr.values())),
            omero.grid.StringColumn('imageName', 'Name of Image', 64, list(names.values())),
            ]
        table.addData(data)
        # get the table as an original file & attach this data to Dataset
        orig_file = table.getOriginalFile()
        fileAnn = omero.model.FileAnnotationI()
        fileAnn.setFile(orig_file)
        for ds in datasets:
            link = omero.model.DatasetAnnotationLinkI()
            link.setParent(omero.model.DatasetI(ds, False))
            link.setChild(fileAnn)
            conn.getUpdateService().saveAndReturnObject(link)
            
        msg = "Script ran with Images: %s" % (names)
        client.setOutput("Message", rstring(str(message) + msg))
        client.setOutput("File_Annotation", robject(file_ann._obj))
        client.setOutput("Table", robject(table._obj))

    finally:
        client.closeSession()


if __name__ == '__main__':
    runScript()
