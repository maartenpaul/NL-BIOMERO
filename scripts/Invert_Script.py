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
from omero.grid import JobParams
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
    result_img = pixels.getPlane(z, c, t).astype('uint8')     # get a numpy array.
    
    # 256 - 0 = 256; 256 - 256 = 0!
    result_img = result_img.max() - result_img
    
    return result_img

def runScript():
    """
    The main entry point of the script
    """

    dynamic_objparams = get_params()
    
    params = JobParams()
    params.authors = ["Torec Luik"]
    params.version = "0.0.1"
    params.description = '''Example script to invert image
    
    Will accept 1 image as input, process it and 
    attach the processed image as annotation on the original.
    '''
    params.name = 'Invert Image Script'
    params.contact = 't.t.luik@amsterdamumc.nl'
    params.institutions = ["Amsterdam UMC"]
    params.authorsInstitutions = [[1]]
    inputs = {}
    p = scripts.String(
            'Image', optional=False, grouping='1',
            description='Select an image', values=dynamic_objparams)
    inputs[p._name] = p
    params.inputs = inputs
    params.namespaces = [omero.constants.namespaces.NSDYNAMIC, 
                         omero.constants.namespaces.NSLOGFILE]
    client = scripts.client(params)    

    # client = scripts.client(
    #     'Invert Image Script', 'Example script to invert image',

    #     scripts.String(
    #         'Image', optional=False, grouping='1',
    #         description='Select an image', values=objparams),

    #     namespaces=[omero.constants.namespaces.NSDYNAMIC],
    # )

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
        name = f"Inverted_{image.getName()}.png"
        
        # ## Save image
        # # Return some value(s).
        min_max = (new_img.min(), new_img.max())
        # numpy_save_as_image(new_img, min_max, np.int32, name)
        final_img = numpy_to_image(new_img, min_max, np.int32)
        try:
            final_img.save(name)
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
        
        # size_z, size_c, size_t = 1, 1, 1
        # i = conn.createImageFromNumpySeq(
        #     plane_gen(new_img), f"Inverted_{image.getName()}", size_z, size_c, size_t,
        #     dataset=None, sourceImageId=image_id)
        # print('Created new Image:%s Name:"%s"' % (i.getId(), i.getName()))


        # Here, we return anything useful the script has produced.
        # NB: The Insight and web clients will display the "Message" output.

        msg = "Script ran with Image ID: %s, Name: %s" % (image_id, image.getName())
        client.setOutput("Message", rstring(msg))
        # client.setOutput("Image", robject(i))
        client.setOutput("File_Annotation", robject(file_ann._obj))

    finally:
        client.closeSession()


def plane_gen(img):
    yield img


if __name__ == '__main__':
    runScript()
