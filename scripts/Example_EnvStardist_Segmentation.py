#!/opt/omero/server/stardistenv/bin/python
# Example script for segmentation using StarDist
# from a stardist python environment
# Modified work Copyright 2022 Torec Luik, Amsterdam UMC
# Use is subject to license terms supplied in LICENSE.txt

import subprocess
import omero
import omero.gateway
from omero.gateway import BlitzGateway
from omero import scripts
from omero.rtypes import rstring, rlong, robject, unwrap
from stardist.models import StarDist2D
from stardist import random_label_cmap
from csbdeep.utils import normalize
import matplotlib.pyplot as plt
import os


_DEFAULT_DATA_TYPE = "Image"
_DEFAULT_MODEL = "2D_versatile_fluo"
_VALUES_MODELS = [rstring(_DEFAULT_MODEL)]
_VALUES_DATA_TYPE = [rstring(_DEFAULT_DATA_TYPE)]
_PARAM_DATA_TYPE = "Data_Type"
_PARAM_IDS = "IDs"
_PARAM_MODEL = "Model"
RUN_ON_GPU_NS = "GPU"


def runStarDist(scriptParams, image_np):
    print(scriptParams)
    # creates a pretrained model
    model = StarDist2D.from_pretrained(scriptParams[_PARAM_MODEL])
    labels, polygons = model.predict_instances(normalize(image_np))
    print(labels)
    return labels, image_np


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


def getImageFromOmero(client, ids):
    # we can now create our Blitz Gateway by wrapping the client object
    conn = BlitzGateway(client_obj=client)
    image = conn.getObject("Image", ids[0])
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


def runScript():
    """
    The main entry point of the script
    """
    # prints a list of available models
    # models = [rstring(m) for m in StarDist2D.from_pretrained()]

    client = scripts.client(
        'StarDist.py', 'Run pretrained StarDist model for segmentation',
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

        image_np, image, conn = getImageFromOmero(client, ids)

        result_name = f"SD_{os.path.splitext(image.getName())[0]}.png"
        labels, img = runStarDist(scriptParams, image_np)

        image, file_ann = saveImageToOmero(labels,
                                           img,
                                           image,
                                           result_name,
                                           conn)

        msg = "Script ran with Image ID: %s, Name: %s" % (ids[0],
                                                          image.getName())
        client.setOutput("Message", rstring(str(message) + msg))
        client.setOutput("File_Annotation", robject(file_ann._obj))

    finally:
        client.closeSession()


if __name__ == '__main__':
    runScript()
