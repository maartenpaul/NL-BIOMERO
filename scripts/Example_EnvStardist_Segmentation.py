#!/opt/omero/server/stardistenv/bin/python
# Example script for segmentation using StarDist
# from a stardist python environment

import subprocess
import omero
import omero.gateway
from omero.gateway import BlitzGateway
from omero import scripts
from omero.rtypes import rstring, rlong, robject, unwrap
from stardist.models import StarDist2D
from stardist.data import test_image_nuclei_2d
from stardist import random_label_cmap
from csbdeep.utils import normalize
import matplotlib.pyplot as plt
import os
# try:
# from PIL import Image  # see ticket:2597
# except:  # pragma: nocover
#     try:
#         import Image  # see ticket:2597
#     except:
#         print('No Pillow installed')


RUN_ON_GPU_NS = "GPU"
        

def runStarDist(scriptParams, image_np):
    # creates a pretrained model
    model = StarDist2D.from_pretrained('2D_versatile_fluo')
    img = test_image_nuclei_2d()
    print(img, image_np)
    labels, polygons = model.predict_instances(normalize(image_np))
    print(labels)
    # sd_img = render_label(labels, img=img)
    # print(sd_img)
    return labels, image_np


def saveImageToOmero(labels, img, image, name, conn):
    # ## Save image    
    plt.figure(figsize=(8,8))
    plt.imshow(img if img.ndim==2 else img[...,0], clim=(0,1), cmap='gray')
    plt.imshow(labels, cmap=random_label_cmap(), alpha=0.5)
    plt.axis('off')
    plt.savefig(name)

    # attach the png to the image
    file_ann = conn.createFileAnnfromLocalFile(
        name, mimetype="image/png")
    print("Attaching %s to image" % name)
    image.linkAnnotation(file_ann)
    
    print("Attaching FileAnnotation to Image: ", "File ID:", 
            file_ann.getId(),",", file_ann.getFile().getName(), "Size:", 
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
    dataTypes = [rstring('Image')]
    # prints a list of available models
    # models = [rstring(m) for m in StarDist2D.from_pretrained()]

    client = scripts.client(
        'StarDist.py', 'Run pretrained StarDist model',
        scripts.String("Data_Type", optional=False, grouping="01", values=dataTypes, default="Image"),
        scripts.List("IDs", optional=False, grouping="02").ofType(rlong(0)),
        scripts.String("Model", optional=False, grouping="03", values=[rstring("2D_versatile_fluo")], default="2D_versatile_fluo"),
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
        
        result_name = f"SD_{image.getName()}.png"
        labels, img = runStarDist(scriptParams, image_np)
        
        image, file_ann = saveImageToOmero(labels, 
                                           img, 
                                           image, 
                                           result_name, 
                                           conn)
        
        msg = "Script ran with Image ID: %s, Name: %s" % (ids[0], image.getName())
        client.setOutput("Message", rstring(str(message) + msg))
        client.setOutput("File_Annotation", robject(file_ann._obj))
    
    finally:
        client.closeSession()


if __name__ == '__main__':
    runScript()
