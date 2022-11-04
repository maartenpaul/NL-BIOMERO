#!/opt/omero/server/cellposeenv/bin/python
# Example OMERO.script using Cellpose segmentation
# from a cellpose python environment

import subprocess
import omero
import omero.gateway
from omero import scripts
from omero.gateway import BlitzGateway
from omero.rtypes import rstring, rlong, robject, unwrap
from cellpose import models, io
import os
import numpy as np


RUN_ON_GPU_NS = "GPU"
CELLPOSE_MODELS = [rstring("nuclei")]
CELLPOSE_DEFAULT = "nuclei"


def random_label_cmap(n=2**16, h=(0, 1), lp=(.4, 1), s=(.2, .8)):
    '''
    Borrowed from StarDist for now:
    https://github.com/stardist/stardist/blob/389f46c4bfcc1ccfaad8c7819e6bd35cf3800290/stardist/plot/plot.py#L8
    '''
    import matplotlib
    import colorsys
    # cols = np.random.rand(n,3)
    # cols = np.random.uniform(0.1,1.0,(n,3))
    h, lp, s = np.random.uniform(*h, n), np.random.uniform(*lp, n), np.random.uniform(*s, n)
    cols = np.stack(
        [colorsys.hls_to_rgb(_h, _l, _s) for _h, _l, _s in zip(h, lp, s)],
        axis=0)
    cols[0] = 0
    return matplotlib.colors.ListedColormap(cols)


def saveCPImageToOmero(img, masks, flows, image, name, conn):
    # ## Save image

    # save results as png
    io.save_to_png(img, masks, flows, name)

    # name = name+'_cp_output.png'

    files = [f for f in os.listdir('.') if os.path.isfile(f) and f.endswith('_cp_output.png')]
    print(files)

    for name in files:
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


def runCellpose(scriptParams, image_np):
    # DEFINE CELLPOSE MODEL
    # model_type='cyto' or model_type='nuclei'
    model = models.Cellpose(gpu=False, model_type='nuclei')
    # define CHANNELS to run segementation on
    # grayscale=0, R=1, G=2, B=3
    # channels = [cytoplasm, nucleus]
    # if NUCLEUS channel does not exist, set the second channel to 0
    # channels = [0,0]
    # IF ALL YOUR IMAGES ARE THE SAME TYPE, you can give a list with 2 elements
    # channels = [0,0] # IF YOU HAVE GRAYSCALE
    # channels = [2,3] # IF YOU HAVE G=cytoplasm and B=nucleus
    # channels = [2,1] # IF YOU HAVE G=cytoplasm and R=nucleu
    chan = [0, 0]
    masks, flows, styles, diams = model.eval(image_np, diameter=None,
                                             channels=chan)
    return masks, flows, styles, diams


def runScript():
    """
    The main entry point of the script
    """
    dataTypes = [rstring('Image')]

    client = scripts.client(
        'CellPose.py', 'Run pretrained CellPose model',
        scripts.String("Data_Type", optional=False, grouping="01",
                       values=dataTypes, default="Image"),
        scripts.List("IDs", optional=False, grouping="02").ofType(rlong(0)),
        scripts.String("Model", optional=False, grouping="03",
                       values=CELLPOSE_MODELS,
                       default=CELLPOSE_DEFAULT),
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

        result_name = f"CP_{os.path.splitext(image.getName())[0]}.png"
        masks, flows, _, _ = runCellpose(scriptParams, image_np)

        image, file_ann = saveCPImageToOmero(image_np, masks, flows,
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
