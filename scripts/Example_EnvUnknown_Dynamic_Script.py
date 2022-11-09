#!/opt/omero/server/unknownenv/bin/python
# -*- coding: utf-8 -*-
#
# Original work Copyright (C) 2014 University of Dundee
#                                   & Open Microscopy Environment.
#                    All Rights Reserved.
# Modified work Copyright 2022 Torec Luik, Amsterdam UMC
# Use is subject to license terms supplied in LICENSE.txt
#

import subprocess
import time
import omero
import omero.gateway
from omero import scripts
from omero.rtypes import rstring


RUN_ON_GPU_NS = "GPU"

def get_params():
    try:
        client = omero.client()
        client.createSession()
        conn = omero.gateway.BlitzGateway(client_obj=client)
        conn.SERVICE_OPTS.setOmeroGroup(-1)
        objparams = [rstring('Dataset:%d %s' % (d.id, d.getName()))
                     for d in conn.getObjects('Dataset')]
        if not objparams:
            objparams = [rstring('<No objects found>')]
        return objparams
    except Exception as e:
        return ['Exception: %s' % e]
    finally:
        client.closeSession()

def busy_wait(dt):   
    current_time = time.time()
    while (time.time() < current_time+dt):
        pass

def runScript():
    """
    The main entry point of the script
    """

    objparams = get_params()

    client = scripts.client(
        'LONG Dynamic Test', 'Long script using dynamic parameters',

        scripts.String(
            'Dataset', optional=False, grouping='1',
            description='Select a dataset', values=objparams),
                
        scripts.Int(
            'Delay', optional=False, grouping='2',
            description='Select a duration',
            values=[0, 10, 20, 30, 40, 50, 60], default=40),

        namespaces=[omero.constants.namespaces.NSDYNAMIC, RUN_ON_GPU_NS],
    )

    try:
        scriptParams = client.getInputs(unwrap=True)
        bashCommandName = "echo $HOSTNAME"
        hostname = subprocess.check_output(['bash', '-c', bashCommandName])
        bashCommandWorker = "echo $OMERO_WORKER_NAME"
        worker = subprocess.check_output(['bash', '-c', bashCommandWorker])
        
        message = (
            f"That took {scriptParams['Delay']}s !\n"
            f"This script ran on {worker}:{hostname}\n"
            f"Params: {scriptParams}\n"
            )
        
        import os
        for k,v in os.environ.items():
            print(k,v)
    
        print(F"sleeping for {scriptParams['Delay']}s first")
        
        # time.sleep(scriptParams['Delay'])
        busy_wait(scriptParams['Delay'])
        
        print(message)
        
        client.setOutput('Message', rstring(str(message)))
        
        import stardist
        import cellpose

    finally:
        client.closeSession()


if __name__ == '__main__':
    runScript()
