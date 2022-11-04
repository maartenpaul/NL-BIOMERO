#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2014 University of Dundee & Open Microscopy Environment.
#                    All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
#

"""
FOR TRAINING PURPOSES ONLY!
"""
from __future__ import print_function

# This is a 'bare-bones' template to allow easy conversion from a simple
# client-side Python script to a script run by the server, on the OMERO
# scripting service.
# To use the script, simply paste the body of the script (not the connection
# code) into the point indicated below.
# A more complete template, for 'real-world' scripts, is also included in this
# folder
# This script takes an Image ID as a parameter from the scripting service.
import omero
from omero.grid import JobParams
from omero.rtypes import rlong, rstring, unwrap, wrap
from omero.gateway import BlitzGateway
import omero.scripts as scripts
import re

def get_params():
    try:
        client = omero.client()
        client.createSession()
        conn = omero.gateway.BlitzGateway(client_obj=client)
        conn.SERVICE_OPTS.setOmeroGroup(-1)
        
        svc = conn.getScriptService()
        scripts = svc.getScripts()
        objparams = scripts
        # objparams = [rstring(f"Script: {unwrap(s.id)} - {unwrap(s.getName())}")
        #              for s in scripts]
        # if len(scripts) >= 1:
        #     script_id = svc.keys()[-1]
        
        # objparams = [rstring('Dataset:%d %s' % (d.id, d.getName()))
        #              for d in conn.getObjects('Dataset')]
        if not objparams:
            objparams = [rstring('<No objects found>')]
        return objparams
    except Exception as e:
        return ['Exception: %s' % e]
    finally:
        client.closeSession()

        
def runScript():
    """
    The main entry point of the script
    """

    objparams = get_params()

    # Script definition

    # Script name, description and 2 parameters are defined here.
    # These parameters will be recognised by the Insight and web clients and
    # populated with the currently selected Image(s)

    # this script only takes Images (not Datasets etc.)
    # data_types = [rstring('Image')]
    # client = scripts.client(
    #     "SuperScript.py",
    #     ("Example script to run other scripts with the"
    #         " scripting service."),
    #     # first parameter
    #     # scripts.String(
    #     #     "Data_Type", optional=False, values=data_types, default="Image"),
    #     # second parameter
    #     # scripts.List("IDs", optional=False).ofType(rlong(0)),
    #     scripts.String(
    #         'Scripts', optional=False, grouping='1',
    #         description='Select a script', values=objparams),
    #     # namespaces=["GPU"]
    # )
    
    params = JobParams()
    params.authors = ["Torec Luik"]
    params.version = "0.0.1"
    params.description = '''Example script to run other scripts
    
    Select scripts below to run:
    '''
    params.name = 'Super Script'
    params.contact = 't.t.luik@amsterdamumc.nl'
    params.institutions = ["Amsterdam UMC"]
    params.authorsInstitutions = [[1]]
    inputs = {}
    # p = scripts.String(
    #         'Image', optional=False, grouping='1',
    #         description='Select an image', values=dynamic_objparams)
    for s in objparams:
        # rstring(f"Script: {unwrap(s.id)} - {unwrap(s.getName())}")
        boolobj = scripts.Bool(
            str(unwrap(s.id)), default=False, description=unwrap(s.getName()))
        inputs[boolobj._name] = boolobj
    # inputs = {key: for obj in objparams}
    params.inputs = inputs
    # params.namespaces = [omero.constants.namespaces.NSDYNAMIC, 
    #                      omero.constants.namespaces.NSLOGFILE]
    client = scripts.client(params)    
    
    # we can now create our Blitz Gateway by wrapping the client object
    conn = BlitzGateway(client_obj=client)

    # get the 'IDs' parameter (which we have restricted to 'Image' IDs)
    # ids = unwrap(client.getInput("IDs"))
    # image_id = ids[0]        # simply use the first ID for this example


    # ** paste here **
    # Replace the code block below. NB: we have established a connection "conn"
    # and we have an "imageId"
    # image = conn.getObject("Image", image_id)
    # print(image.getName())

    svc = conn.getScriptService()
    # scripts = svc.getScripts()

    scriptParams = {}
    for key in client.getInputKeys():
        if client.getInput(key):
            scriptParams[key] = unwrap(client.getInput(key))

    print(scriptParams)
    
    # if len(scripts) >= 1:
    #     script_id = svc.keys()[-1]
    # else:
    #     script_id = svc.uploadScript('/test/my_script.py', SCRIPT_TEXT)
    
    for k, v in scriptParams:
        if v:
            script_id = int(k)
            # script_id = unwrap(client.getInput("Scripts"))
            # Where's the ID?
            # script_id = int(re.findall(r"\d+", script_id)[0])
            params = svc.getParams(script_id)
            print(f"params: {params}")

            
            # You will need to parse the params to create the proper input
            # inputs = wrap({ 
            #           'Dataset': "Dataset:1 test"
            #         })
            
            inputs = {"Dataset": omero.rtypes.rstring(
                    "Dataset:1 test"), 
                    "Delay": omero.rtypes.rint(10)}

            # The last parameter is how long to wait as an RInt
            proc = svc.runScript(script_id, inputs, None)
            try:
                cb = omero.scripts.ProcessCallbackI(client, proc)
                while not cb.block(1000):  # ms.
                    pass
                cb.close()
                rv = proc.getResults(0)
            finally:
                proc.close(False)

            # Return some value(s).
            results = rv
            print(results.keys())
            if 'Message' in results:
                print(results['Message'].getValue())
            if 'stdout' in results:
                origFile = results['stdout'].getValue()
                print("Script generated StdOut in file:" , origFile.getId().getValue())
            if 'stderr' in results:
                origFile = results['stderr'].getValue()
                print("Script generated StdErr in file:" , origFile.getId().getValue())

    # Here, we return anything useful the script has produced.
    # NB: The Insight and web clients will display the "Message" output.

    # msg = "Script ran with Image ID: %s, Name: %s" % (image_id, image.getName())
    msg2 = f"\nRan other script, params: {params}"
    msg3 = f"\nRan other script, results: {rv}"
    client.setOutput("Message", rstring(msg2+msg3))
    client.close()

    
if __name__ == '__main__':
    runScript()
