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
from omero.rtypes import rstring, unwrap, rlong, rbool, rlist
from omero.gateway import BlitzGateway
import omero.scripts as omscripts
import datetime
from omero_slurm_client import SlurmClient
import logging
import time as timesleep
from paramiko import SSHException

logger = logging.getLogger(__name__)

IMAGE_EXPORT_SCRIPT = "_SLURM_Image_Transfer.py"
IMAGE_IMPORT_SCRIPT = "SLURM_Get_Results.py"
EXPORT_SCRIPTS = [IMAGE_EXPORT_SCRIPT]
IMPORT_SCRIPTS = [IMAGE_IMPORT_SCRIPT]
DATATYPES = [rstring('Dataset'), rstring('Image')]


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
        params.version = "0.0.8"
        params.description = f'''Script to run nuclei segmentation on slurm
        cluster.

        This runs a script remotely on your Slurm cluster.
        Connection ready? {slurmClient.validate()}
        '''
        params.name = 'Slurm Nuclei Segmentation'
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
                default="Dataset"),
            omscripts.List(
                "IDs", optional=False, grouping="01.2",
                description="List of Dataset IDs or Image IDs").ofType(
                    rlong(0)),
            omscripts.Bool("E-mail", grouping="01.3",
                           description=email_descr,
                           default=True),
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
            email = getOmeroEmail(client, conn)  # retrieve an email for Slurm

            # --------------------------------------------
            # :: 1. Push selected data to Slurm ::
            # --------------------------------------------
            # Generate a filename for the input data
            zipfile = createFileName(client, conn)
            # Send data to Slurm, zipped, over SSH
            # Uses _SLURM_Image_Transfer script from Omero
            rv = exportImageToSLURM(client, conn, zipfile)
            print(f"Ran data export: {rv.keys()}, {rv}")
            if 'Message' in rv:
                log_string += f"Exported data. {rv['Message'].getValue()}"

            # --------------------------------------------
            # :: 2. Unpack data on Slurm ::
            # --------------------------------------------
            unpack_result = slurmClient.unpack_data(zipfile)
            print(unpack_result.stdout)
            if not unpack_result.ok:
                print("Error unpacking data:", unpack_result.stderr)
            else:
                slurm_job_ids = {}
                # Quick git pull on Slurm for latest version of job scripts
                update_result = slurmClient.update_slurm_scripts()
                print(update_result.__dict__)
                
                # --------------------------------------------
                # :: 3. Create Slurm jobs for all workflows ::
                # --------------------------------------------
                for wf_name in workflows:
                    if unwrap(client.getInput(wf_name)):
                        log_string, slurm_job_id = run_workflow(
                            slurmClient,
                            _workflow_params[wf_name],
                            client,
                            log_string,
                            zipfile,
                            email,
                            wf_name)
                        slurm_job_ids[wf_name] = slurm_job_id

                # 4. Poll SLURM results
                slurm_job_id_list = [
                    x for x in slurm_job_ids.values() if x >= 0]
                print(slurm_job_id_list)
                while slurm_job_id_list:
                    # Query all jobids we care about
                    try:
                        job_status_dict, _ = slurmClient.check_job_status(
                            slurm_job_id_list)
                    except Exception as e:
                        log_string += f" ERROR WITH JOB: {e}"

                    for slurm_job_id, job_state in job_status_dict.items():
                        print(f"Job {slurm_job_id} is {job_state}.")

                        lm = f"-- Status of batch job\
                            {slurm_job_id}: {job_state}"
                        logging.debug(lm)
                        print(lm)
                        if job_state == "TIMEOUT":
                            log_msg = f"Job {slurm_job_id} is TIMEOUT."
                            log_string += log_msg
                            # TODO resubmit? add an option?
                            # new_job_id = slurmClient.resubmit_job(
                            #     slurm_job_id)
                            # log_msg = f"Job {slurm_job_id} has been
                            # resubmitted ({new_job_id})."
                            print(log_msg)
                            logging.warning(log_msg)
                            # log_string += log_msg
                            slurm_job_id_list.remove(slurm_job_id)
                            # slurm_job_id_list.append(new_job_id)
                        elif job_state == "COMPLETED":
                            # 5. Retrieve SLURM images
                            # 6. Store results in OMERO
                            rv_imp = importImagesToOmero(
                                client, conn, slurm_job_id)
                            if rv:
                                log_msg = f"{rv_imp['Message'].getValue()}"
                            else:
                                log_msg = "Attempted to import images to\
                                    Omero."
                            print(log_msg)
                            logging.info(log_msg)
                            log_string += log_msg
                            slurm_job_id_list.remove(slurm_job_id)
                        elif (job_state.startswith("CANCELLED")
                                or job_state == "FAILED"):
                            # Remove from future checks
                            log_msg = f"Job {slurm_job_id} is {job_state}."
                            print(log_msg)
                            logging.warning(log_msg)
                            log_string += log_msg
                            slurm_job_id_list.remove(slurm_job_id)
                        elif (job_state == "PENDING"
                                or job_state == "RUNNING"):
                            # expected
                            log_msg = f"Job {slurm_job_id} is busy..."
                            print(log_msg)
                            logging.debug(log_msg)
                            continue
                        else:
                            log_msg = f"Oops! State of job {slurm_job_id}\
                                is unknown: {job_state}. Stop tracking."
                            print(log_msg)
                            logging.warning(log_msg)
                            log_string += log_msg
                            slurm_job_id_list.remove(slurm_job_id)

                    # wait for 10 seconds before checking again
                    conn.keepAlive()  # keep the connection alive
                    timesleep.sleep(10)

            # 7. Script output
            client.setOutput("Message", rstring(log_string))
        finally:
            client.closeSession()


def run_workflow(slurmClient: SlurmClient,
                 workflow_params,
                 client,
                 log_string: str,
                 zipfile,
                 email,
                 name):
    print(f"Running {name}")
    workflow_version = unwrap(
        client.getInput(f"{name}_Version"))
    kwargs = {}
    for k in workflow_params:
        kwargs[k] = unwrap(client.getInput(k))  # kwarg dict
    print(f"Run workflow with: {kwargs}")
    try:
        cp_result, slurm_job_id = slurmClient.run_workflow(
            workflow_name=name,
            workflow_version=workflow_version,
            input_data=zipfile,
            email=email,
            time=None,
            **kwargs)
        print(cp_result.stdout)
        if not cp_result.ok:
            print(f"Error running {name} job:",
                  cp_result.stderr)
        else:
            log_string += f"Submitted {name} to Slurm\
                as batch job {slurm_job_id}."

            job_status_dict, poll_result = slurmClient.check_job_status(
                [slurm_job_id])
            print(
                job_status_dict[slurm_job_id], poll_result.stdout)
            if not poll_result.ok:
                print("Error checking job status:",
                      poll_result.stderr)
            else:
                log_string += f"\n{job_status_dict[slurm_job_id]}"
    except Exception as e:
        log_string += f" ERROR WITH JOB: {e}"
        print(log_string)
        raise SSHException(log_string)
    return log_string, slurm_job_id


def getOmeroEmail(client, conn):
    if unwrap(client.getInput("E-mail")):
        try:
            # Retrieve information about the authenticated user
            user = conn.getUser()
            use_email = user.getEmail()
            if use_email == "None":
                print("No email given for this user")
                use_email = None
        except omero.gateway.OMEROError as e:
            print(f"Error retrieving email {e}")
            use_email = None
    else:
        use_email = None
    print(f"Using email {use_email}")
    return use_email


def exportImageToSLURM(client: omscripts.client,
                       conn: BlitzGateway,
                       zipfile: str):
    svc = conn.getScriptService()
    scripts = svc.getScripts()
    script_ids = [unwrap(s.id)
                  for s in scripts if unwrap(s.getName()) in EXPORT_SCRIPTS]
    if not script_ids:
        raise ValueError(
            f"Cannot export images to Slurm: scripts ({EXPORT_SCRIPTS})\
                not found in ({[unwrap(s.getName()) for s in scripts]}) ")
    # TODO: export nucleus channel only? that is individual channels,
    # but filtered...
    inputs = {"Data_Type": client.getInput("Data_Type"),
              "IDs": client.getInput("IDs"),
              "Image settings (Optional)": rbool(True),
              "Export_Individual_Channels": rbool(False),
              "Export_Merged_Image": rbool(True),
              "Choose_Z_Section": rstring('Max projection'),
              "Choose_T_Section": rstring('Default-T (last-viewed)'),
              "Format": rstring('TIFF'),
              "Folder_Name": rstring(zipfile)
              }
    print(inputs, script_ids)
    rv = runOMEROScript(client, svc, script_ids, inputs)
    return rv


def runOMEROScript(client: omscripts.client, svc, script_ids, inputs):
    rv = None
    for k in script_ids:
        script_id = int(k)
        # params = svc.getParams(script_id) # we can dynamically get them

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
    return rv


def importImagesToOmero(client: omscripts.client,
                        conn: BlitzGateway,
                        slurm_job_id: int) -> str:
    if conn.keepAlive():
        svc = conn.getScriptService()
        scripts = svc.getScripts()
    else:
        msg = f"Lost connection with OMERO. Slurm done @ {slurm_job_id}"
        logger.error(msg)
        raise ConnectionError(msg)
       
    script_ids = [unwrap(s.id)
                  for s in scripts if unwrap(s.getName()) in IMPORT_SCRIPTS]
    first_id = unwrap(client.getInput("IDs"))[0]
    print(script_ids, first_id, unwrap(client.getInput("Data_Type")))
    opts = {}
    # get parent dataset and project
    if unwrap(client.getInput("Data_Type")) == 'Image':
        opts['dataset'] = [d.id for d in conn.getObjects(
            'Dataset', opts={'image': first_id})][0]
    elif unwrap(client.getInput("Data_Type")) == 'Dataset':
        opts['dataset'] = first_id
    print(opts)
    projects = [rstring('%d: %s' % (d.id, d.getName()))
                for d in conn.getObjects('Project', opts=opts)]
    print(projects)
    inputs = {"Completed Job": rbool(True),
              "SLURM Job Id": rstring(str(slurm_job_id)),
              "Project": rlist(projects),
              }
    print(f"Running script {script_ids} with inputs: {inputs}")
    rv = runOMEROScript(client, svc, script_ids, inputs)
    return rv


def createFileName(client: omscripts.client, conn: BlitzGateway) -> str:
    opts = {}
    if unwrap(client.getInput("Data_Type")) == 'Image':
        # get parent dataset
        opts['image'] = unwrap(client.getInput("IDs"))[0]
        objparams = ['%d_%s' % (d.id, d.getName())
                     for d in conn.getObjects('Dataset', opts=opts)]
    elif unwrap(client.getInput("Data_Type")) == 'Dataset':
        objparams = ['%d_%s' % (d.id, d.getName())
                     for d in conn.getObjects('Dataset',
                                              unwrap(client.getInput("IDs")))]

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    filename = "_".join(objparams)
    full_filename = f"{filename}_{timestamp}"
    print("Filename: " + full_filename)
    return full_filename


if __name__ == '__main__':
    runScript()
