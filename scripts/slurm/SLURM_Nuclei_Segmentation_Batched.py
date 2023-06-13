#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Original work Copyright (C) 2014 University of Dundee
#                                   & Open Microscopy Environment.
#                    All Rights Reserved.
# Modified work Copyright 2022 Torec Luik, Amsterdam UMC
# Use is subject to license terms supplied in LICENSE.txt
#
# Example OMERO.script to run multiple segmentation images on Slurm.

from __future__ import print_function
import omero
from omero.grid import JobParams
from omero.rtypes import rstring, wrap, unwrap, rlong
from omero.gateway import BlitzGateway
import omero.scripts as omscripts
from omero_slurm_client import SlurmClient
import logging
from itertools import islice
import time as timesleep

logger = logging.getLogger(__name__)

IMAGE_EXPORT_SCRIPT = "SLURM_Nuclei_Segmentation.py"
PROC_SCRIPTS = [IMAGE_EXPORT_SCRIPT]
DATATYPES = [rstring('Image')]


def runScript():
    """
    The main entry point of the script
    """
    # --------------------------------------------
    # :: Slurm Client ::
    # --------------------------------------------
    # Start by setting up the Slurm Client from configuration files.
    # We will use the client to connect via SSH to Slurm to send data and
    # commands.
    with SlurmClient.from_config() as slurmClient:
        # --------------------------------------------
        # :: Script definition ::
        # --------------------------------------------
        # Script name, description and parameters are defined here.
        # These parameters will be recognised by the Insight and web clients
        # and populated with the currently selected Image(s)/Dataset(s)
        params = JobParams()
        params.authors = ["Torec Luik"]
        params.version = "0.0.1"
        params.description = f'''Script to run nuclei segmentation on slurm
        cluster, automatically batched.

        This runs a script remotely on your Slurm cluster.
        Connection ready? {slurmClient.validate()}
        '''
        params.name = 'Slurm Nuclei Segmentation (Batched)'
        params.contact = 't.t.luik@amsterdamumc.nl'
        params.institutions = ["Amsterdam UMC"]
        params.authorsInstitutions = [[1]]
        # Default script parameters that we want to know for all workflows:
        # input and output.
        email_descr = "Do you want an email if your job is done or cancelled?"
        input_list = [
            omscripts.String(
                "Data_Type", optional=False, grouping="01.1",
                description="The data you want to work with.",
                values=DATATYPES,
                default="Image"),
            omscripts.List(
                "IDs", optional=False, grouping="01.2",
                description="List of Dataset IDs or Image IDs").ofType(
                    rlong(0)),
            omscripts.Bool("E-mail", grouping="01.3",
                           description=email_descr,
                           default=True),
            omscripts.Int("Batch_Size", optional=False, grouping="01.4",
                          description="Number of images to send to 1 slurm job",
                          default=32)
        ]
        # Generate script parameters for all our workflows
        (wf_versions, _) = slurmClient.get_all_image_versions_and_data_files()
        na = ["Not Available!"]
        _workflow_params = {}
        _workflow_available_versions = {}
        # All currently configured workflows
        workflows = wf_versions.keys()
        for group_incr, wf in enumerate(workflows):
            # increment per wf, determines UI order
            parameter_group = f"0{group_incr+2}"
            _workflow_available_versions[wf] = wf_versions.get(
                wf, na)
            # Get the workflow parameters (dynamically) from their repository
            _workflow_params[wf] = slurmClient.get_workflow_parameters(
                wf)
            # Main parameter to select this workflow for execution
            wf_ = omscripts.Bool(wf, grouping=parameter_group, default=False)
            input_list.append(wf_)
            # Select an available container image version to execute on Slurm
            version_descr = f"Version of the container of {wf}"
            wf_v = omscripts.String(f"{wf}_Version",
                                    grouping=f"{parameter_group}.0",
                                    description=version_descr,
                                    values=_workflow_available_versions[wf])
            input_list.append(wf_v)
            # Create a script parameter for all workflow parameters
            for param_incr, (k, param) in enumerate(_workflow_params[
                    wf].items()):
                print(param_incr, k, param)
                logging.info(param)
                # Convert the parameter from cy(tomine)type to om(ero)type
                omtype_param = slurmClient.convert_cytype_to_omtype(
                    param["cytype"],
                    param["default"],
                    param["name"],
                    description=param["description"],
                    default=param["default"],
                    grouping=f"{parameter_group}.{param_incr+1}",
                    optional=param['optional']
                )
                input_list.append(omtype_param)
        # Finish setting up the Omero script UI
        inputs = {
            p._name: p for p in input_list
        }
        params.inputs = inputs
        # Reload instead of caching
        params.namespaces = [omero.constants.namespaces.NSDYNAMIC]
        client = omscripts.client(params)

        # --------------------------------------------
        # :: Workflow execution ::
        # --------------------------------------------
        # Here we actually run the chosen workflows on the chosen data
        # on Slurm.
        # Steps:
        # 1. Push selected data to Slurm
        # 2. Unpack data on Slurm
        # 3. Create Slurm jobs for all workflows
        # 4. Check Slurm job statuses
        # 5. When completed, pull and upload data to Omero
        try:
            # log_string will be output in the Omero Web UI
            log_string = ""
            # Check if user actually selected (a version of) a workflow to run
            selected_workflows = {wf_name: unwrap(
                client.getInput(wf_name)) for wf_name in workflows}
            if not any(selected_workflows.values()):
                raise ValueError("ERROR: Please select at least 1 workflow!")
            version_errors = ""
            for wf, selected in selected_workflows.items():
                selected_version = unwrap(client.getInput(f"{wf}_Version"))
                print(wf, selected, selected_version)
                if selected and not selected_version:
                    version_errors += f"ERROR: No version for '{wf}'! \n"
            if version_errors:
                raise ValueError(version_errors)

            # Connect to Omero
            conn = BlitzGateway(client_obj=client)
            conn.SERVICE_OPTS.setOmeroGroup(-1)
            svc = conn.getScriptService()
            # Find script
            scripts = svc.getScripts()
            script_ids = [unwrap(s.id)
                          for s in scripts if unwrap(s.getName()) in PROC_SCRIPTS]
            if not script_ids:
                raise ValueError(
                    f"Cannot export images to Slurm: scripts ({PROC_SCRIPTS})\
                        not found in ({[unwrap(s.getName()) for s in scripts]}) ")
            # --------------------------------------------
            # :: 1. Split data into batches ::
            # --------------------------------------------
            batch_size = unwrap(client.getInput("Batch_Size"))
            data_ids = unwrap(client.getInput("IDs"))
            batch_ids = chunk(data_ids, batch_size)
            print(list(batch_ids))

            # --------------------------------------------
            # :: 2. Setup the main script for each batch ::
            # --------------------------------------------
            # Prepare script inputs
            inputs = client.getInputs()
            processes = {}
            callbacks = {}
            remaining_batches = {i: b for i, b in enumerate(batch_ids)}
            print(remaining_batches)
            for i, batch in remaining_batches.items():
                inputs["IDs"] = wrap(batch)  # override ids
                del inputs["Batch_Size"]
                for k in script_ids:
                    script_id = int(k)
                    # The last parameter is how long to wait as an RInt
                    proc = svc.runScript(script_id, inputs, None)
                    processes[i] = proc
                    cb = omero.scripts.ProcessCallbackI(client, proc)
                    callbacks[i] = cb
            print(processes, callbacks)
            # --------------------------------------------
            # :: 3. Track all the batch jobs ::
            # --------------------------------------------
            try:
                # 4. Poll results
                logger.debug(remaining_batches, processes)
                while remaining_batches:
                    # loop the remaining processes
                    for i, proc in processes.items():
                        cb = callbacks[i]
                        if cb.block(1):  # Check if finished, or wait x ms
                            cb.close()
                            rv = proc.getResults(0)  # "Message"?
                            log_string += rv
                            logger.info(
                                f"Batch {i} - [{remaining_batches[i]}] done: {rv}")
                            del remaining_batches[i]
                        else:
                            pass

                    # wait for 10 seconds before checking again
                    timesleep.sleep(10)

            finally:
                for proc in processes:
                    proc.close(False)  # stop the scripts

            # 7. Script output
            client.setOutput("Message", rstring(log_string))
        finally:
            client.closeSession()


def chunk(lst, n):
    """Yield successive n-sized chunks from lst."""
    it = iter(lst)
    return iter(lambda: tuple(islice(it, n)), ())


if __name__ == '__main__':
    runScript()
