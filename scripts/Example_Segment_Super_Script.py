#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Original work Copyright (C) 2014 University of Dundee
#                                   & Open Microscopy Environment.
#                    All Rights Reserved.
# Modified work Copyright 2022 Torec Luik, Amsterdam UMC
# Use is subject to license terms supplied in LICENSE.txt
#

from __future__ import print_function
import omero
from omero.rtypes import rlong, rstring, unwrap, rlist, robject
from omero.gateway import BlitzGateway
import omero.scripts as omscripts

_DEFAULT_DATA_TYPE = "Image"
_PARAM_DATA_TYPE = "Data_Type"
_PARAM_IDS = "IDs"
_VALUES_DATA_TYPE = [rstring(_DEFAULT_DATA_TYPE)]
SCRIPTNAMES = ["Example_EnvCellpose_Segmentation.py",
               "Example_EnvStardist_Segmentation.py"]


def runScript():
    """
    The main entry point of the script
    """

    client = omscripts.client(
        'Segmentation Super Script',
        '''Example script to run other scripts

        Runs both cellpose and stardist, for comparison
        ''',
        omscripts.String(_PARAM_DATA_TYPE, optional=False, grouping="01",
                         values=_VALUES_DATA_TYPE, default=_DEFAULT_DATA_TYPE),
        omscripts.List(_PARAM_IDS,
                       optional=False, grouping="02").ofType(rlong(0)),
        namespaces=[omero.constants.namespaces.NSDYNAMIC],
        authors=["Torec Luik"],
        version="0.0.1",
        contact='t.t.luik@amsterdamumc.nl',
        institutions=["Amsterdam UMC"],
        authorsInstitutions=[[1]]
    )

    try:
        scriptParams = client.getInputs(unwrap=True)
        # we can now create our Blitz Gateway by wrapping the client object
        conn = BlitzGateway(client_obj=client)

        svc = conn.getScriptService()
        scripts = svc.getScripts()

        script_ids = [unwrap(s.id) for s in scripts
                      if unwrap(s.getName()) in SCRIPTNAMES]

        print_result = {
            'Message': [],
            'File_Annotation': []
        }
        for k in script_ids:
            script_id = int(k)

            params = svc.getParams(script_id)
            print(f"params: {params}")
            inputs = {_PARAM_IDS: rlist(rlong(scriptParams[_PARAM_IDS][0]))}

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
                print_result['Message'].append(results['Message'].getValue())

            if 'File_Annotation' in results:
                print_result['File_Annotation'].append(
                    results['File_Annotation'].getValue())

        client.setOutput("Message",
                         rstring("\n".join(print_result['Message'])))
        for i, ann in enumerate(print_result['File_Annotation']):
            client.setOutput(f"File_Annotation_{i}", robject(ann))
    finally:
        client.closeSession()


if __name__ == '__main__':
    runScript()
