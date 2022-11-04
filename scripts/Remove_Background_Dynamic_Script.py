#!/usr/bin/env python
# Example OMERO.script using dynamic arguments
# Included in omero/developers/scripts/user-guide.txt
# A list of datasets will be dynamically generated and used to populate the
# script parameters every time the script is called

import os
import omero
import omero.gateway
from omero.gateway import BlitzGateway
from omero import scripts
from omero.rtypes import rstring, robject, unwrap
from omero.util.script_utils import numpy_save_as_image, numpy_to_image
from skimage.filters import rank
from skimage.morphology import disk
import numpy as np
from scipy import ndimage as ndi
import re


def get_params():
    try:
        client = omero.client()
        client.createSession()
        conn = omero.gateway.BlitzGateway(client_obj=client)
        conn.SERVICE_OPTS.setOmeroGroup(-1)
        # get images
        objparams = [rstring('Images:%d %s' % (d.id, d.getName()))
                     for d in conn.getObjects('Image')]
        if not objparams:
            objparams = [rstring('<No objects found>')]
        return objparams
    except Exception as e:
        return ['Exception: %s' % e]
    finally:
        client.closeSession()
        

def process_image(img):  # ImageI object
    print(img.getName(), img.getDescription())
    # Retrieve information about an image.
    print(" X:", img.getSizeX())
    print(" Y:", img.getSizeY())
    print(" Z:", img.getSizeZ())
    print(" C:", img.getSizeC())
    print(" T:", img.getSizeT())
    
    z = img.getSizeZ() / 2
    t = 0
    c = 0
    pixels = img.getPrimaryPixels()
    result_img = pixels.getPlane(z, c, t)      # get a numpy array.
    
    # Create a circular structuring element (SE) whose size depends on i
    # i = 75
    # SE = (np.mgrid[:i,:i][0] - np.floor(i/2))**2 + (np.mgrid[:i,:i][1] - np.floor(i/2))**2 <= np.floor(i/2)**2
    SE = disk(37)
    
    # Create the background by running a mean filter over the image using the disc SE and assign the output to a new variable
    # Use the function 'skimage.filters.rank.mean'
    img8 = (((result_img - result_img.min()) / (result_img.max() - result_img.min())) * 255).astype('uint8')
    
    # The documentation tells us that the gaussian_filter function expects a smoothing factor sigma, 
    # so we will arbitrarily define one (this can be changed later)
    sigma = 4
    img_smooth8 = ndi.filters.gaussian_filter(img8, sigma)
    # bg8 = rank.mean(img_smooth8, footprint=SE)
    bg8 = rank.mean(img_smooth8, selem=SE)
    
    # Threshold the Gaussian-smoothed original image against the background image using a relational expression
    result_img = img_smooth8 > bg8
    
    return result_img


def runScript():
    """
    The main entry point of the script
    """

    objparams = get_params()

    client = scripts.client(
        'Remove Background Script', 'Example script using dynamic parameters',

        scripts.String(
            'Image', optional=False, grouping='1',
            description='Select an image', values=objparams),

        namespaces=[omero.constants.namespaces.NSDYNAMIC],
    )

    try:
        scriptParams = client.getInputs(unwrap=True)
        message = 'Params: %s\n' % scriptParams
        print(message)
        # client.setOutput('Hello World! Message', rstring(str(message)))
        
        # we can now create our Blitz Gateway by wrapping the client object
        conn = BlitzGateway(client_obj=client)
        
        # get the 'IDs' parameter (which we have restricted to 'Image' IDs)
        # ids = unwrap(client.getInput("IDs"))
        image_name = scriptParams['Image']        # simply use the first ID for this example
        
        # Where's the ID?
        image_id = re.findall(r"\d+", image_name)[0]

        # ** paste here **
        # Replace the code block below. NB: we have established a connection "conn"
        # and we have an "imageId"
        image = conn.getObject("Image", image_id)
        print(image.getName())
        
        ## Process image
        new_img = process_image(image).astype(int) # Numpy array
        name = "Background_Removed.png"
        
        # ## Save image
        # # Return some value(s).
        min_max = (new_img.min(), new_img.max())
        # numpy_save_as_image(new_img, min_max, np.int32, name)
        new_img = numpy_to_image(new_img, min_max, np.int32)
        try:
            new_img.save(name)
        except (IOError, KeyError, ValueError) as e:
            msg = "Cannot save the array as an image: %s: %s" % (
                name, e)

        # # attach the png to the image
        # attach the png to the image
        file_ann = conn.createFileAnnfromLocalFile(
            name, mimetype="image/png")
        print("Attaching %s to image" % name)
        image.linkAnnotation(file_ann)
        
        print("Attaching FileAnnotation to Image: ", "File ID:", 
              file_ann.getId(),",", file_ann.getFile().getName(), "Size:", 
              file_ann.getFile().getSize())
        os.remove(name) 


        # Here, we return anything useful the script has produced.
        # NB: The Insight and web clients will display the "Message" output.

        msg = "Script ran with Image ID: %s, Name: %s" % (image_id, image.getName())
        client.setOutput("Message", rstring(msg))
        client.setOutput("File_Annotation", robject(omero.model.FileAnnotationI(file_ann.getId(), False)))

    finally:
        client.closeSession()


if __name__ == '__main__':
    runScript()
