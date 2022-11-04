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
import omero
from omero.grid import JobParams
from omero.rtypes import rstring, unwrap
from omero.gateway import BlitzGateway
import omero.scripts as omscripts

SCRIPTNAMES = ["Example_Minimal_EnvCellpose.py",
               "Example_Minimal_EnvStardist.py"]


def runScript():
    """
    The main entry point of the script
    """

    # Script definition

    # Script name, description and 2 parameters are defined here.
    # These parameters will be recognised by the Insight and web clients and
    # populated with the currently selected Image(s)

    params = JobParams()
    params.authors = ["Torec Luik"]
    params.version = "0.0.1"
    params.description = f'''Example script to run other scripts

    Runs a parameterless other scripts:
    {SCRIPTNAMES}
    '''
    params.name = 'Minimal Super Script'
    params.contact = 't.t.luik@amsterdamumc.nl'
    params.institutions = ["Amsterdam UMC"]
    params.authorsInstitutions = [[1]]
    inputs = {}
    params.inputs = inputs
    client = omscripts.client(params)

    # we can now create our Blitz Gateway by wrapping the client object
    conn = BlitzGateway(client_obj=client)

    svc = conn.getScriptService()
    scripts = svc.getScripts()

    script_ids = [unwrap(s.id) for s in scripts
                  if unwrap(s.getName()) in SCRIPTNAMES]

    print_result = []
    for k in script_ids:
        script_id = int(k)

        params = svc.getParams(script_id)
        print(f"params: {params}")
        inputs = {"Delay": omero.rtypes.rint(10)}

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
        print_result.append(results['Message'].getValue())

    client.setOutput("Message", rstring("".join(print_result)))
    client.close()


if __name__ == '__main__':
    runScript()
