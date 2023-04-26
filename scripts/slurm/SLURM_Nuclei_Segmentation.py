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
from omero.grid import JobParams
from omero.rtypes import rstring, unwrap, rlong, rbool, rlist
from omero.gateway import BlitzGateway
import omero.scripts as omscripts
import subprocess
import os
from pathlib import Path
from typing import Union, List
import itertools
import re
import datetime
import time as timesleep

SLURM_HOME = "/home/sandbox/ttluik"
IMAGE_PATH = f"{SLURM_HOME}/my-scratch/singularity_images/workflows"
CELLPOSE_IMAGE_PATH = f"{IMAGE_PATH}/cellpose"
STARDIST_IMAGE_PATH = f"{IMAGE_PATH}/stardist"
CELLPROFILER_IMAGE_PATH = f"{IMAGE_PATH}/cellprofiler"
IMAGEJ_IMAGE_PATH = f"{IMAGE_PATH}/imagej"
DEEPCELL_IMAGE_PATH = f"{IMAGE_PATH}/deepcell"
BASE_DATA_PATH = f"{SLURM_HOME}/my-scratch/data"
GIT_DIR_SCRIPT = f"{SLURM_HOME}/slurm-scripts/"
IMAGE_EXPORT_SCRIPT = "_SLURM_Image_transfer.py"
IMAGE_IMPORT_SCRIPT = "SLURM_Get_Results.py"
EXPORT_SCRIPTS = [IMAGE_EXPORT_SCRIPT]
IMPORT_SCRIPTS = [IMAGE_IMPORT_SCRIPT]
SSH_KEY = '~/.ssh/id_rsa'
SLURM_REMOTE = 'luna.amc.nl'
SLURM_USER = 'ttluik'
SSH_HOSTS = '~/.ssh/known_hosts'
_CHECK_JOBSTATE_COMMAND = "sacct -o jobid,state -n -X"
_PYCMD = "Python_Command"
_DEFAULT_CMD = "import numpy as np; arr = np.array([1,2,3,4,5]); print(arr.mean())"
_RUNPY = "Run_Python"
_RUNSLRM = "Check_SLURM_Status"
_SQUEUE = "Check_Queue"
_SINFO = "Check_Cluster"
_SOTHER = "Run_Other_Command"
_SCMD = "Linux_Command"
_DEFAULT_SCMD = "ls -la"
_DATA_SEP = "--data--"
_CELLPOSE_VERSION_CMD = f"ls -h {CELLPOSE_IMAGE_PATH} | grep -oP '(?<=-)v.+(?=.simg)' ; echo '{_DATA_SEP}'"
_DEEPCELL_VERSION_CMD = f"ls -h {DEEPCELL_IMAGE_PATH} | grep -oP '(?<=-)v.+(?=.simg)' ; echo '{_DATA_SEP}'"
_IMAGEJ_VERSION_CMD = f"ls -h {IMAGEJ_IMAGE_PATH} | grep -oP '(?<=-)v.+(?=.simg)' ; echo '{_DATA_SEP}'"
_CELLPROFILER_VERSION_CMD = f"ls -h {CELLPROFILER_IMAGE_PATH} | grep -oP '(?<=-)v.+(?=.simg)' ; echo '{_DATA_SEP}'"
_STARDIST_VERSION_CMD = f"ls -h {STARDIST_IMAGE_PATH} | grep -oP '(?<=-)v.+(?=.simg)' ; echo '{_DATA_SEP}'"
_DATA_CMD = f"ls -h {BASE_DATA_PATH} | grep -oP '.+(?=.zip)'"
_DEFAULT_DATA_TYPE = "Image"
_DEFAULT_MODEL = "nuclei"
_VALUES_MODELS = [rstring(_DEFAULT_MODEL), rstring("cyto")]
_VALUES_DATA_TYPE = [rstring(_DEFAULT_DATA_TYPE)]
_PARAM_DATA_TYPE = "Data_Type"
_PARAM_IDS = "IDs"
_PARAM_MODEL = "Model"
_PARAM_NUCCHANNEL = "Nuclear Channel"
_PARAM_PROBTHRESH = "Cell probability threshold"
_PARAM_DIAMETER = "Cell diameter"
_versions = ["vlatest"]
_DEFAULT_DATA_FOLDER = "SLURM_IMAGES_"
DEFAULT_EMAIL = "t.t.luik@amsterdamumc.nl"
DEFAULT_MAIL = "No"
DEFAULT_TIME = "00:15:00"
DATATYPES = [rstring('Dataset')]


# TODO use Fabric library?
class SshClient():
    """ Perform commands and copy files on ssh using subprocess 
        and native ssh client (OpenSSH).
        Based on https://gist.github.com/TorecLuik/aae824e081895707f0a82585d273164f
    """

    def __init__(self,
                 user: str,
                 remote: str,
                 key_path: Union[str, Path],
                 known_hosts: str = "/dev/null") -> None:
        """

        Args:
            user (str): username for the remote
            remote (str): remote host IP/DNS
            key_path (str or pathlib.Path): path to .pem file
            known_hosts (str, optional): path to known_hosts file
        """
        self.user = user
        self.remote = remote
        self.key_path = str(key_path)
        self.known_hosts = known_hosts

    def cmd(self,
            cmds: List[str],
            check=True,
            strict_host_key_checking=True,
            **run_kwargs) -> subprocess.CompletedProcess:
        """runs commands consecutively, ensuring success of each
            after calling the next command.

        Args:
            cmds (list[str]): list of commands to run.
            strict_host_key_checking (bool, optional): Defaults to True.
        """

        # strict_host_key_checking = 'yes' if strict_host_key_checking else 'no'
        strict_host_key_checking = 'no'
        cmd = ' && '.join(cmds)
        print(f"CMD: {cmd} || extra args: {run_kwargs}")
        return subprocess.run(
            [
                'ssh',
                '-i', self.key_path,
                '-o', f'StrictHostKeyChecking={strict_host_key_checking}',
                '-o', f'UserKnownHostsFile={self.known_hosts}',
                # '-o', 'LogLevel=DEBUG',
                f'{self.user}@{self.remote}',
                cmd
            ],
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **run_kwargs
        )

    def scp(self,
            sources: List[Union[str, bytes, os.PathLike]],
            destination: Union[str, bytes, os.PathLike],
            check=True,
            strict_host_key_checking=False,
            recursive=False,
            **run_kwargs) -> subprocess.CompletedProcess:
        """Copies `srouce` file to remote `destination` using the 
            native `scp` command.

        Args:
            source (Union[str, bytes, os.PathLike]): List of source files path.
            destination (Union[str, bytes, os.PathLike]): Destination path on remote.
        """

        strict_host_key_checking = 'yes' if strict_host_key_checking else 'no'

        return subprocess.run(
            list(filter(bool, [
                'scp',
                '-i', self.key_path,
                '-o', f'StrictHostKeyChecking={strict_host_key_checking}',
                '-o', 'UserKnownHostsFile=/dev/null',
                '-o', 'LogLevel=ERROR',
                '-r' if recursive else '',
                *map(str, sources),
                # sources,
                f'{self.user}@{self.remote}:{str(destination)}',
            ])),
            check=check,
            **run_kwargs
        )

    def validate(self):
        return self.cmd([f'echo " "'], check=False).returncode == 0

    def ssh_connect_cmd(self) -> str:
        return f'ssh -i {self.key_path} {self.user}@{self.remote}'


def string_to_list(input_string: str, sep: str = _DATA_SEP) -> list:
    """
    Convert a string into a list of lists using the specified separator.

    :param input_string: A string to convert.
    :param sep: The separator string used to split the input string into a list of strings. Defaults to '--data--'.
    """
    str_list = input_string.split(sep + "\n")
    # split each string into a list, and sort the highest versions first
    result = [sorted(s_list.strip().split('\n'), reverse=True) if s_list.startswith(
        'v') else s_list.strip().split('\n') for s_list in str_list]
    return result


def getImageVersionsAndDataFiles(slurmClient):
    """Retrieve parameter options from SLURM server

    Args:
        slurmClient (_type_): SSH client to SLURM server

    Returns:
        Lists: _cellpose_versions, _deepcell_versions, _stardist_versions, _imagej_versions, _cellprofiler_versions, _data_versions
    """
    if slurmClient.validate():
        cmdlist = [_CELLPOSE_VERSION_CMD,
                   _DEEPCELL_VERSION_CMD,
                   _STARDIST_VERSION_CMD,
                   _IMAGEJ_VERSION_CMD,
                   _CELLPROFILER_VERSION_CMD,
                   _DATA_CMD]
        slurm_response = call_slurm(slurmClient, cmdlist)
        # responselist = slurm_response[0].strip().split('\n')
        # split_responses = [list(y) for x, y in itertools.groupby(
        #     responselist, lambda z: z == _DATA_SEP) if not x]
        # print(split_responses, len(split_responses))
        # # _cellpose_versions, _deepcell_versions, _stardist_versions, _imagej_versions, _cellprofiler_versions,
        # return split_responses[0], split_responses[1], split_responses[2], split_responses[3], split_responses[4], split_responses[5],
        return string_to_list(slurm_response[0])
    else:
        return _versions, [_DEFAULT_DATA_FOLDER]


def runScript():
    """
    The main entry point of the script
    """

    # Script definition

    # Script name, description and 2 parameters are defined here.
    # These parameters will be recognised by the Insight and web clients and
    # populated with the currently selected Image(s)
    slurmClient = SshClient(user=SLURM_USER,
                            remote=SLURM_REMOTE,
                            key_path=SSH_KEY,
                            known_hosts=SSH_HOSTS)

    params = JobParams()
    params.authors = ["Torec Luik"]
    params.version = "0.0.2"
    params.description = f'''Script to run nuclei segmentation on slurm cluster.
    First run the {IMAGE_EXPORT_SCRIPT} script to export your data to the cluster.

    This runs a script remotely on: {SLURM_REMOTE}
    Connection ready? {slurmClient.validate()}
    '''
    params.name = 'Slurm Nuclei Segmentation'
    params.contact = 't.t.luik@amsterdamumc.nl'
    params.institutions = ["Amsterdam UMC"]
    params.authorsInstitutions = [[1]]

    _cellpose_versions, _deepcell_versions, _stardist_versions, _imagej_versions, _cellprofiler_versions, _datafiles = getImageVersionsAndDataFiles(
        slurmClient)
    input_list = [
        omscripts.String(
            "Data_Type", optional=False, grouping="01.1",
            description="Input dataset(s) only", values=DATATYPES,
            default="Dataset"),
        omscripts.List(
            "IDs", optional=False, grouping="01.2",
            description="List of Dataset IDs").ofType(rlong(0)),
        omscripts.Bool("E-mail", grouping="01.3",
                       description="Do you want an email if your job is done or cancelled?",
                       default=True),
        omscripts.Bool("CellPose", grouping="04", default=False),
        omscripts.String("CellPose_Version", grouping="04.1",
                         description="Version of the Singularity Image of Cellpose",
                         values=_cellpose_versions),
        omscripts.String(_PARAM_MODEL, optional=False, grouping="04.3",
                         values=_VALUES_MODELS, default=_DEFAULT_MODEL),
        omscripts.Int(_PARAM_NUCCHANNEL, optional=True, grouping="04.4",
                      description="Channel with the nuclei (to segment)",
                      default=0),
        omscripts.Float(_PARAM_PROBTHRESH, optional=True, grouping="04.5",
                        description="threshold when to segment (0 = everything, 1 = nothing)",
                        default=0.5),
        omscripts.Float(_PARAM_DIAMETER, optional=True, grouping="04.6",
                        description="Diameter of a cell. Leave at 0 to let the computer guess.",
                        default=0),
        omscripts.Bool("DeepCell", grouping="03", default=False),
        omscripts.String("DeepCell_Version", grouping="03.0",
                         description="Version of the Singularity Image of DeepCell",
                         values=_deepcell_versions),
        omscripts.Float("nuclei_min_size", optional=True, grouping="03.1",
                        description="Minimum estimated size of a nucleus",
                        default=25),
        omscripts.Float("boundary_weight", optional=True, grouping="03.2",
                        description="Boundary class weight (larger value results in better object separation but smaller objects)",
                        default=1.0),
        omscripts.Bool("StarDist", grouping="05", default=False),
        omscripts.String("StarDist_Version", grouping="05.0",
                         description="Version of the Singularity Image of StarDist",
                         values=_stardist_versions),
        omscripts.Float("stardist_prob_t", optional=True, grouping="05.1",
                        description="Probability Threshold in range [0.0, 1.0] - higher values lead to fewer segmented objects, but will likely avoid false positives",
                        default=0.5),
        omscripts.Float("stardist_nms_t", optional=True, grouping="05.2",
                        description="Overlap Threshold in range [0.0, 1.0] - higher values allow segmented objects to overlap substantially.",
                        default=0.5),
        omscripts.Float("stardist_norm_perc_low", optional=True, grouping="05.3",
                        description="Percentile low in range [0.0 100.0]",
                        default=1),
        omscripts.Float("stardist_norm_perc_high", optional=True, grouping="05.4",
                        description="Percentile high in range [0.0 100.0]",
                        default=99.8),
        omscripts.Bool("ImageJ", grouping="06", default=False),
        omscripts.String("ImageJ_Version", grouping="06.0",
                         description="Version of the Singularity Image of ImageJ",
                         values=_imagej_versions),
        omscripts.Float("ij_radius", optional=True, grouping="06.1",
                        description="Size of smoothing filter",
                        default=5),
        omscripts.Float("ij_threshold", optional=True, grouping="06.2",
                        description="Size of smoothing filter",
                        default=-0.5),
        omscripts.Bool("CellProfiler", grouping="07", default=False),
        omscripts.String("CellProfiler_Version", grouping="07.0",
                         description="Version of the Singularity Image of Cellprofiler",
                         values=_cellprofiler_versions),
        omscripts.String("nuclei_diameter_range", optional=True, grouping="07.1",
                         description="Typical diameter of objects, in pixel units (Min,Max)",
                         default="15,4000"),
        omscripts.Float("size_smoothing_filter", optional=True, grouping="07.2",
                        description="Size of smoothing filter",
                        default=5),
    ]
    inputs = {
        p._name: p for p in input_list
    }
    params.inputs = inputs
    params.namespaces = [omero.constants.namespaces.NSDYNAMIC]
    client = omscripts.client(params)

    try:
        cmdlist = []
        print_result = ""
        conn = BlitzGateway(client_obj=client)
        conn.SERVICE_OPTS.setOmeroGroup(-1)
        zipfile = createFileName(client, conn)
        # 1. Get image(s) from OMERO
        # 2. Send image(s) to SLURM
        # Use _SLURM_Image_Transfer script from Omero
        # we can now create our Blitz Gateway by wrapping the client object
        rv = exportImageToSLURM(client, conn, zipfile)
        print(f"Ran data export: {rv.keys()}, {rv}")
        if 'Message' in rv:
            print_result += f"Exported data. {rv['Message'].getValue()}"

        # 3. Call SLURM (segmentation)
        use_email = getEmailForSLURM(client, conn)

        time = DEFAULT_TIME
        unzip_cmd = f"mkdir {BASE_DATA_PATH}/{zipfile} \
            {BASE_DATA_PATH}/{zipfile}/data \
            {BASE_DATA_PATH}/{zipfile}/data/in \
            {BASE_DATA_PATH}/{zipfile}/data/out \
            {BASE_DATA_PATH}/{zipfile}/data/gt; \
            7z e -y -o{BASE_DATA_PATH}/{zipfile}/data/in \
            {BASE_DATA_PATH}/{zipfile}.zip *.tiff *.tif"
        cmdlist.append(unzip_cmd)
        update_cmd = f"git -C {GIT_DIR_SCRIPT} pull"
        cmdlist.append(update_cmd)

        # SELECT SEGMENTER
        # Perhaps nicer to separate these all into singular scripts and call those scripts?
        if unwrap(client.getInput("CellPose")):
            print("Running Cellpose")
            cellpose_version = unwrap(client.getInput("CellPose_Version"))
            cmdlist = runCellPose(client, cellpose_version,
                                  cmdlist, zipfile, use_email, time)

        if unwrap(client.getInput("StarDist")):
            print("Running Stardist")
            stardist_version = unwrap(client.getInput("StarDist_Version"))
            cmdlist = runStarDist(client, stardist_version,
                                  cmdlist, zipfile, use_email, time)

        if unwrap(client.getInput("DeepCell")):
            print("Running DeepCell")
            deepcell_version = unwrap(client.getInput("DeepCell_Version"))
            cmdlist = runDeepCell(client, deepcell_version,
                                  cmdlist, zipfile, use_email, time)

        if unwrap(client.getInput("ImageJ")):
            print("Running ImageJ")
            imagej_version = unwrap(client.getInput("ImageJ_Version"))
            cmdlist = runImageJ(client, imagej_version,
                                cmdlist, zipfile, use_email, time)

        if unwrap(client.getInput("CellProfiler")):
            print("Running CellProfiler")
            cellprofiler_version = unwrap(
                client.getInput("CellProfiler_Version"))
            cmdlist = runCellProfiler(
                client, cellprofiler_version, cmdlist, zipfile, use_email, time)

        # scriptParams = client.getInputs(unwrap=True) # just unwrapped a bunch already...
        # ... Submitted batch job 73547
        slurm_result = call_slurm(slurmClient, cmdlist)
        slurm_result = "".join(slurm_result)
        print(slurm_result)
        slurm_job_id_list = list((int(s.strip()) for s in slurm_result.split(
            "Submitted batch job") if s.strip().isdigit()), -1)

        slurm_job_id_list = [x for x in slurm_job_id_list if x >= 0]
        # 4. Poll SLURM results
        while slurm_job_id_list:
            # Query all jobids we care about
            try:
                cmdlist = []
                slurm_job_id_params = " ".join(
                    [f"-j {jobid}" for jobid in slurm_job_id_list])
                cmdlist.append(
                    f"{_CHECK_JOBSTATE_COMMAND} {slurm_job_id_params}")
                print_job = call_slurm(slurmClient, cmdlist)
                print(print_job[0])
                job_status_dict = {line.split()[0]: line.split(
                )[1] for line in print_job.split("\n") if line}
                # = print_job[0].strip()
                print_result += f"\n{job_state}"
            except Exception as e:
                print_result += f" ERROR WITH JOB: {e}"

            for slurm_job_id, job_state in job_status_dict:
                print(f"Job {slurm_job_id} is {job_state}.")

                print_result += f"Submitted to SLURM as batch job {slurm_job_id}."
                if job_state == "TIMEOUT":
                    print_result += f"Job {slurm_job_id} is TIMEOUT."
                    new_job_id = resubmitJob(client, conn, slurm_job_id, time)
                    print_result += f"Job {slurm_job_id} has been resubmitted."
                    slurm_job_id_list.remove(slurm_job_id)
                    slurm_job_id_list.append(new_job_id)
                elif job_state == "COMPLETED":
                    # 5. Retrieve SLURM images
                    # 6. Store results in OMERO
                    rv_imp = importImagesFromSLURM(client, conn, slurm_job_id)
                    print_result += f"{rv_imp['Message'].getValue()}"
                    slurm_job_id_list.remove(slurm_job_id)
                elif job_state.startswith("CANCELLED"):
                    # Remove from future checks
                    print_result += f"Job {slurm_job_id} is CANCELLED."
                    slurm_job_id_list.remove(slurm_job_id)
                elif job_state == "PENDING" or job_state == "RUNNING":
                    # expected
                    continue
                else:
                    print_result += f"Oops! State of job {slurm_job_id}: {job_state}"
                    slurm_job_id_list.remove(slurm_job_id)

            timesleep.sleep(5)  # wait for 5 seconds before checking again

        # 7. Script output
        client.setOutput("Message", rstring(print_result))
    finally:
        client.closeSession()


def resubmitJob(client, conn, slurm_job_id, time):
    """Holder for a function to resubmit a timed out job

    Args:
        client (_type_): _description_
        conn (_type_): _description_
        slurm_job_id (_type_): _description_
        time (_type_): _description_
    """
    # TODO requeue with more time
    return slurm_job_id


def getEmailForSLURM(client, conn):
    if unwrap(client.getInput("E-mail")):
        try:
            # Retrieve information about the authenticated user
            user = conn.getUser()
            use_email = user.getEmail()
            if use_email == "None":
                print("No email given for this user")
                use_email = DEFAULT_EMAIL
        except omero.gateway.OMEROError as e:
            print(f"Error retrieving email {e}")
            use_email = DEFAULT_EMAIL
    else:
        use_email = DEFAULT_EMAIL
    print(f"Using email {use_email}")
    return use_email


def exportImageToSLURM(client, conn, zipfile):
    svc = conn.getScriptService()
    scripts = svc.getScripts()
    script_ids = [unwrap(s.id)
                  for s in scripts if unwrap(s.getName()) in EXPORT_SCRIPTS]
    # TODO: export nucleus channel only? that is individual channels, but filtered...
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

    rv = runOMEROScript(client, svc, script_ids, inputs)
    return rv


def runOMEROScript(client, svc, script_ids, inputs):
    for k in script_ids:
        script_id = int(k)
        params = svc.getParams(script_id)
        print(f"params: {params}")

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


def importImagesFromSLURM(client, conn, SLURM_JOB_ID):
    svc = conn.getScriptService()
    scripts = svc.getScripts()
    script_ids = [unwrap(s.id)
                  for s in scripts if unwrap(s.getName()) in IMPORT_SCRIPTS]
    projects = ['%d_%s' % (d.id, d.getName())
                for d in conn.getObjects('Dataset', unwrap(client.getInput("IDs")))]
    objparams = [rstring('%d: %s' % (d.id, d.getName()))
                 for d in conn.getObjects('Project', opts={})]
    inputs = {"Completed Job": rbool(True),
              "SLURM Job Id": rlong(SLURM_JOB_ID),
              "Project": rlist([]),
              }

    rv = runOMEROScript(client, svc, script_ids, inputs)
    return rv


def createFileName(client, conn):
    objparams = ['%d_%s' % (d.id, d.getName())
                 for d in conn.getObjects('Dataset', unwrap(client.getInput("IDs")))]
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    filename = "_".join(objparams)
    zipfile = f"{filename}_{timestamp}"
    print(zipfile)
    return zipfile


def runCellPose(client, cellpose_version, cmdlist, zipfile, use_email, time):
    cp_model = unwrap(client.getInput(_PARAM_MODEL))
    nuc_channel = unwrap(client.getInput(_PARAM_NUCCHANNEL))
    prob_threshold = unwrap(client.getInput(_PARAM_PROBTHRESH))
    cell_diameter = unwrap(client.getInput(_PARAM_DIAMETER))

    sbatch_cmd = f"export DATA_PATH={BASE_DATA_PATH}/{zipfile} ; \
            export IMAGE_PATH={CELLPOSE_IMAGE_PATH} ; \
            export IMAGE_VERSION={cellpose_version} ; \
            export DIAMETER={cell_diameter} ; \
            export PROB_THRESHOLD={prob_threshold} ; \
            export NUC_CHANNEL={nuc_channel} ; \
            export CP_MODEL={cp_model} ; \
            export USE_GPU=true ; \
            sbatch --mail-user={use_email} --time={time} {GIT_DIR_SCRIPT}/jobs/cellpose.sh"
    cmdlist.append(sbatch_cmd)
    return cmdlist


def runStarDist(client, image_version, cmdlist, zipfile, use_email, time):
    stardist_prob_t = unwrap(client.getInput("stardist_prob_t"))
    stardist_nms_t = unwrap(client.getInput("stardist_nms_t"))
    stardist_norm_perc_low = unwrap(client.getInput("stardist_norm_perc_low"))
    stardist_norm_perc_high = unwrap(
        client.getInput("stardist_norm_perc_high"))

    sbatch_cmd = f"export DATA_PATH={BASE_DATA_PATH}/{zipfile} ; \
            export IMAGE_PATH={STARDIST_IMAGE_PATH} ; \
            export IMAGE_VERSION={image_version} ; \
            export STARDIST_PROB_T={stardist_prob_t} ; \
            export STARDIST_NMS_T={stardist_nms_t} ; \
            export STARDIST_NORM_PERC_LOW={stardist_norm_perc_low} ; \
            export STARDIST_NORM_PERC_HIGH={stardist_norm_perc_high} ; \
            sbatch --mail-user={use_email} --time={time} {GIT_DIR_SCRIPT}/jobs/stardist.sh"
    cmdlist.append(sbatch_cmd)
    return cmdlist


def runImageJ(client, image_version, cmdlist, zipfile, use_email, time):
    ij_radius = unwrap(client.getInput("ij_radius"))
    ij_threshold = unwrap(client.getInput("ij_threshold"))

    sbatch_cmd = f"export DATA_PATH={BASE_DATA_PATH}/{zipfile} ; \
            export IMAGE_PATH={IMAGEJ_IMAGE_PATH} ; \
            export IMAGE_VERSION={image_version} ; \
            export IJ_RADIUS={ij_radius} ; \
            export IJ_THRESHOLD={ij_threshold} ; \
            sbatch --mail-user={use_email} --time={time} {GIT_DIR_SCRIPT}/jobs/imagej.sh"
    cmdlist.append(sbatch_cmd)
    return cmdlist


def runDeepCell(client, image_version, cmdlist, zipfile, use_email, time):
    nuclei_min_size = unwrap(client.getInput("nuclei_min_size"))
    boundary_weight = unwrap(client.getInput("boundary_weight"))

    sbatch_cmd = f"export DATA_PATH={BASE_DATA_PATH}/{zipfile} ; \
            export IMAGE_PATH={DEEPCELL_IMAGE_PATH} ; \
            export IMAGE_VERSION={image_version} ; \
            export NUCLEI_MIN_SIZE={nuclei_min_size} ; \
            export BOUNDARY_WEIGHT={boundary_weight} ; \
            sbatch --mail-user={use_email} --time={time} {GIT_DIR_SCRIPT}/jobs/deepcell.sh"
    cmdlist.append(sbatch_cmd)
    return cmdlist


def runCellProfiler(client, image_version, cmdlist, zipfile, use_email, time):
    nuclei_diameter_range = unwrap(client.getInput("nuclei_diameter_range"))
    size_smoothing_filter = unwrap(client.getInput("size_smoothing_filter"))

    sbatch_cmd = f"export DATA_PATH={BASE_DATA_PATH}/{zipfile} ; \
            export IMAGE_PATH={CELLPROFILER_IMAGE_PATH} ; \
            export IMAGE_VERSION={image_version} ; \
            export NUCLEI_DIAMETER_RANGE={nuclei_diameter_range} ; \
            export SIZE_SMOOTHING_FILTER={size_smoothing_filter} ; \
            sbatch --mail-user={use_email} --time={time} {GIT_DIR_SCRIPT}/jobs/cellprofiler.sh"
    cmdlist.append(sbatch_cmd)
    return cmdlist


def call_slurm(slurmClient, cmdlist):
    """Easier function to provide list of commandline orders to SLURM server.

    Args:
        slurmClient (SshClient): SLURM SshClient
        cmdlist (List): List of commands to execute on SLURM

    Returns:
        String: Message describing results
    """
    print_result = []
    try:
        # run a list of commands
        results = slurmClient.cmd(
            cmdlist,
            check=True,
            strict_host_key_checking=False)
        print(f"Ran slurm {results.__dict__}")
        try:
            print_result.append(f"{results.stdout.decode('utf-8')}")
        except Exception:
            print_result.append(f"{results.stderr.decode('utf-8')}")
    except subprocess.CalledProcessError as e:
        results = f"Error {e.__dict__}"
        print(results)
    return print_result


if __name__ == '__main__':
    runScript()
