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
from omero.rtypes import rstring, unwrap, rlong
from omero.gateway import BlitzGateway
import omero.scripts as omscripts
import subprocess
import os
from pathlib import Path
from typing import Union, List
import itertools
import re

SLURM_HOME = "/home/sandbox/ttluik"
IMAGE_PATH = f"{SLURM_HOME}/my-scratch/singularity_images/workflows/cellpose"
BASE_DATA_PATH = f"{SLURM_HOME}/my-scratch/data"
GIT_DIR_SCRIPT = f"{SLURM_HOME}/slurm-scripts/"
IMAGE_EXPORT_SCRIPT = "_SLURM_Image_transfer.py"
SCRIPTNAMES = [IMAGE_EXPORT_SCRIPT]
SSH_KEY = '~/.ssh/id_rsa'
SLURM_REMOTE = 'luna.amc.nl'
SLURM_USER = 'ttluik'
SSH_HOSTS = '~/.ssh/known_hosts'
_VERSION_CMD = f"ls -h {IMAGE_PATH} | grep -oP '(?<=-)v.+(?=.simg)'"
_DATA_SEP = "--data--"
_DATA_CMD = f"echo '{_DATA_SEP}' && ls -h {BASE_DATA_PATH} | grep -oP '.+(?=.zip)'"
_DEFAULT_DATA_TYPE = "Image"
_DEFAULT_MODEL = "nuclei"
_VALUES_MODELS = [rstring(_DEFAULT_MODEL), rstring("cyto")]
_PARAM_MODEL = "Model"
_PARAM_NUCCHANNEL = "Nuclear Channel"
_PARAM_PROBTHRESH = "Cell probability threshold"
_PARAM_DIAMETER = "Cell diameter"
_versions = ["vlatest"]
_DEFAULT_DATA_FOLDER = "SLURM_IMAGES_"
DEFAULT_MAIL = "No"
DEFAULT_TIME = "00:15:00"


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


def getImageVersionsAndDataFiles(slurmClient):
    if slurmClient.validate():
        cmdlist = [_VERSION_CMD, _DATA_CMD]
        slurm_response = call_slurm(slurmClient, cmdlist)
        responselist = slurm_response[0].strip().split('\n')
        split_responses = [list(y) for x, y in itertools.groupby(responselist, lambda z: z == _DATA_SEP) if not x]
        return split_responses[0], split_responses[1]
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
    params.description = f'''Script to run CellPose on slurm cluster.
    First run the {IMAGE_EXPORT_SCRIPT} script to export your data to the cluster.
    
    Specifically will run: 
    https://hub.docker.com/r/torecluik/t_nucleisegmentation-cellpose

    This runs a script remotely on: {SLURM_REMOTE}
    Connection ready? {slurmClient.validate()}
    '''
    params.name = 'Slurm Cellpose Segmentation'
    params.contact = 't.t.luik@amsterdamumc.nl'
    params.institutions = ["Amsterdam UMC"]
    params.authorsInstitutions = [[1]]
    
    _versions, _datafiles = getImageVersionsAndDataFiles(slurmClient)
    input_list = [
        omscripts.Bool("CellPose", grouping="04", default=True),
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
        omscripts.String("Folder_Name", grouping="05",
                         description=f"Name of folder where images are stored, as provided with {IMAGE_EXPORT_SCRIPT}",
                         values=_datafiles),
        omscripts.Bool("SLURM Job Parameters", grouping="06", default=True),
        omscripts.String("Version", grouping="06.1",
                         description="Version of the Singularity Image of Cellpose",
                         values=_versions),
        omscripts.String("Duration", grouping="06.2",
                         description="Maximum time the script should run for. Max is 8 hours. Notation is hh:mm:ss",
                         default=DEFAULT_TIME),
        omscripts.String("E-mail", grouping="06.3",
                         description="Provide an e-mail if you want a mail when your job is done or cancelled.",
                         default=DEFAULT_MAIL)
    ]
    inputs = {
        p._name: p for p in input_list
    }
    params.inputs = inputs
    params.namespaces = [omero.constants.namespaces.NSDYNAMIC] 
    client = omscripts.client(params)

    # we can now create our Blitz Gateway by wrapping the client object
    # conn = BlitzGateway(client_obj=client)
    
    # get the 'IDs' parameter (which we have restricted to 'Image' IDs)
    # ids = unwrap(client.getInput("IDs"))
    cellpose_version = unwrap(client.getInput("Version"))
    try:
        ## 1. Get image(s) from OMERO
        ## 2. Send image(s) to SLURM
        # Use _SLURM_Image_Transfer script from Omero
        
        ## 3. Call SLURM (segmentation)
        zipfile = unwrap(client.getInput("Folder_Name"))
        cp_model = unwrap(client.getInput(_PARAM_MODEL))
        nuc_channel = unwrap(client.getInput(_PARAM_NUCCHANNEL))
        prob_threshold = unwrap(client.getInput(_PARAM_PROBTHRESH))
        cell_diameter = unwrap(client.getInput(_PARAM_DIAMETER))
        email = unwrap(client.getInput("E-mail"))
        if email == DEFAULT_MAIL:
            use_email = "t.t.luik@amsterdamumc.nl"
        else:
            use_email = email
        time = unwrap(client.getInput("Duration"))
        cmdlist = []
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
        sbatch_cmd = f"export DATA_PATH={BASE_DATA_PATH}/{zipfile} ; \
        export IMAGE_PATH={IMAGE_PATH} ; \
        export IMAGE_VERSION={cellpose_version} ; \
        export DIAMETER={cell_diameter} ; \
        export PROB_THRESHOLD={prob_threshold} ; \
        export NUC_CHANNEL={nuc_channel} ; \
        export CP_MODEL={cp_model} ; \
        export USE_GPU=true ; \
        sbatch --mail-user={use_email} --time={time} {GIT_DIR_SCRIPT}/jobs/cellpose.sh"
        cmdlist.append(sbatch_cmd)
        scriptParams = client.getInputs(unwrap=True) # just unwrapped a bunch already...
        print_result = call_slurm(slurmClient, cmdlist) # ... Submitted batch job 73547
        print_result = "".join(print_result)
        print(print_result)
        SLURM_JOB_ID = next((int(s.strip()) for s in print_result.split("Submitted batch job") if s.strip().isdigit()), -1)
        print_result = f"Submitted to SLURM as batch job {SLURM_JOB_ID}."
        ## 4. Poll SLURM results   
        try:
            cmdlist = []
            cmdlist.append(f"scontrol show job {SLURM_JOB_ID}")
            print_job = call_slurm(slurmClient, cmdlist)
            print(print_job[0])
            job_state = re.search('JobState=(\w+) Reason=(\w+)', print_job[0]).group()
            print_result += f"\n{job_state}"
        except Exception as e:
            print_result += f" ERROR WITH JOB: {e}"

        ## 5. Retrieve SLURM images
        
        ## 6. Store results in OMERO
        
        ## 7. Script output
        client.setOutput("Message", rstring(print_result))
    finally:
        client.closeSession()


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
