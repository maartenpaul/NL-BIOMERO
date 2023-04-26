#!/opt/omero/server/cellposeenv/bin/python
# -*- coding: utf-8 -*-
#
# Original work Copyright (C) 2014 University of Dundee
#                                   & Open Microscopy Environment.
#                    All Rights Reserved.
# Modified work Copyright 2022 Torec Luik, Amsterdam UMC
# Use is subject to license terms supplied in LICENSE.txt
#
# Example OMERO.script using Cellpose segmentation
# from a cellpose python environment

import subprocess
import omero
import omero.gateway
from omero import scripts
import omero.util.script_utils as script_utils
from omero.constants.namespaces import NSCREATED
from omero.gateway import BlitzGateway
from omero.rtypes import rstring, rlong, robject, unwrap, rint, wrap
from cellpose import models, io
import os
import numpy as np
from pathlib import Path
from typing import Union, List
import itertools
import re

SLURM_HOME = "/home/sandbox/ttluik"
SLURM_DATA_PATH = f"{SLURM_HOME}/my-scratch/data/"
_CHANNEL_VALUES = [rint(0), rint(1), rint(2), rint(3)]
_DEFAULT_CHANNEL_CYTOPLASM = 0
_DEFAULT_CHANNEL_NUCLEUS = 0
_DEFAULT_DATA_TYPE = "Image"
_DEFAULT_MODEL = "nuclei"
_MODELS_VALUES = [rstring(_DEFAULT_MODEL)]
_PARAM_CHANNEL_CYTOPLASM = "Channel_(cytoplasm)"
_PARAM_CHANNEL_NUCLEUS = "Channel_(nucleus)"
_PARAM_DATA_TYPE = "Data_Type"
_PARAM_IDS = "IDs"
_PARAM_MODEL = "Model"
_QUEUE_COMMAND = "squeue --nohead --format %F -u ttluik"
_ACCT_COMMAND = "sacct --starttime 2023-01-01 -o JobId -n -X"
SLURM_JOB_ID = "SLURM Job Id"
SLURM_JOB_ID_OLD = "SLURM Job Id (old)"
RUN_ON_GPU_NS = "GPU"
SSH_KEY = '~/.ssh/id_rsa'
SLURM_REMOTE = 'luna.amc.nl'
SLURM_USER = 'ttluik'
SSH_HOSTS = '~/.ssh/known_hosts'
RUNNING_JOB = "Running Job"
COMPLETED_JOB = "Completed Job"


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

    def scpull(self,
               destination: Union[str, bytes, os.PathLike],
               source: Union[str, bytes, os.PathLike],
               check=True,
               strict_host_key_checking=False,
               recursive=False,
               **run_kwargs) -> subprocess.CompletedProcess:
        """Copies remote `destination` file to local `source` using the 
            native `scp` command.
            
            Inverse of scp command.

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
                # *map(str, sources),
                f'{self.user}@{self.remote}:{str(destination)}',
                str(source),
            ])),
            check=check,
            **run_kwargs
        )

    
    def validate(self):
        return self.cmd([f'echo " "'], check=False).returncode == 0

    def ssh_connect_cmd(self) -> str:
        return f'ssh -i {self.key_path} {self.user}@{self.remote}'


def saveCPImageToOmero(img, masks, flows, image, name, conn):
    # ## Save image

    # save results as png
    io.save_to_png(img, masks, flows, name)

    # name = name+'_cp_output.png'

    files = [f for f in os.listdir('.') if os.path.isfile(f)
             and f.endswith('_cp_output.png')]
    print(files)

    for name in files:
        # attach the png to the image
        file_ann = conn.createFileAnnfromLocalFile(
            name, mimetype="image/png")
        print("Attaching %s to image" % name)
        image.linkAnnotation(file_ann)

        print("Attaching FileAnnotation to Image: ", "File ID:",
              file_ann.getId(), ",", file_ann.getFile().getName(), "Size:",
              file_ann.getFile().getSize())

        os.remove(name)

    return image, file_ann


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


def getRunningJobs(slurmClient):
    if slurmClient.validate():
        cmdlist = [_QUEUE_COMMAND]
        slurm_response = call_slurm(slurmClient, cmdlist)
        responselist = slurm_response[0].strip().split('\n')
        return responselist
    else: 
        return ["Error connecting to SLURM"]
    

def getOldJobs(slurmClient):
    if slurmClient.validate():
        cmdlist = [_ACCT_COMMAND]
        slurm_response = call_slurm(slurmClient, cmdlist)
        responselist = slurm_response[0].strip().split('\n')
        responselist.reverse()  # newest on top
        return responselist
    else: 
        return ["Error connecting to SLURM"]


def getUserProjects():
    try:
        client = omero.client()
        client.createSession()
        conn = omero.gateway.BlitzGateway(client_obj=client)
        conn.SERVICE_OPTS.setOmeroGroup(-1)
        objparams = [rstring('%d: %s' % (d.id, d.getName()))
                     for d in conn.getObjects('Project')]
        #  if type(d) == omero.model.ProjectI
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

    slurmClient = SshClient(user=SLURM_USER,
                            remote=SLURM_REMOTE,
                            key_path=SSH_KEY,
                            known_hosts=SSH_HOSTS)
    
    _slurmjobs = getRunningJobs(slurmClient)
    _oldjobs = getOldJobs(slurmClient)
    _projects = getUserProjects()
    dataTypes = [rstring('Project')]
    client = scripts.client(
        'Slurm Get Update',
        '''Retrieve an update about your SLURM job.
        
        Will download the logfile if you select a completed job.
        ''',
        scripts.Bool(RUNNING_JOB, optional=True, grouping="01", default=True),
        scripts.String(SLURM_JOB_ID, optional=True, grouping="01.1",
                       values=_slurmjobs),
        scripts.Bool(COMPLETED_JOB, optional=True, default=False, grouping="02"),
        scripts.String(SLURM_JOB_ID_OLD, optional=True, grouping="02.1",
                       values=_oldjobs),
        # scripts.String("Data_Type", optional=False, grouping="02.3", values=dataTypes, default="Project",
        #                description="Project to attach workflow results to"),
        # scripts.List("IDs", optional=False, grouping="02.4", 
        #              description="Project to attach workflow results to",
        #              values=_projects).ofType(rlong(0)),
        scripts.List("Project", optional=False, grouping="02.5", 
                     description="Project to attach workflow results to",
                     values=_projects),
        namespaces=[omero.constants.namespaces.NSDYNAMIC],
    )

    try:
        scriptParams = client.getInputs(unwrap=True)

        message = ""
        print(f"Request: {scriptParams}\n")
        
        # Job id
        slurm_job_id = unwrap(client.getInput(SLURM_JOB_ID))
        slurm_job_id_old = unwrap(client.getInput(SLURM_JOB_ID_OLD)).strip()
        
        # Job State
        if unwrap(client.getInput(RUNNING_JOB)):
            try:
                cmdlist = []
                cmdlist.append(f"scontrol show job {slurm_job_id}")
                print_job = call_slurm(slurmClient, cmdlist)
                print(print_job[0])
                job_state = re.search('JobState=(\w+) Reason=(\w+)', print_job[0]).group()
                message += f"\n{job_state}"
            except Exception as e:
                message += f" Show job failed: {e}"
        elif unwrap(client.getInput(COMPLETED_JOB)):
            try:
                cmdlist = []
                cmdlist.append(f"sacct -n -o JobId,State,End -X -j {slurm_job_id_old}")
                print_job = call_slurm(slurmClient, cmdlist)
                print(print_job[0])
                message += f"\n{print_job[0]}"
            except Exception as e:
                message += f" Show job failed: {e}"
        
        # Job log  
        if unwrap(client.getInput(RUNNING_JOB)):
            try:
                cmdlist = []
                update_cmd = f"tail -n 10 cellpose-{slurm_job_id}.log"
                cmdlist.append(update_cmd)
                print_result = call_slurm(slurmClient, cmdlist) # ... Submitted batch job 73547
                print_result = "".join(print_result)
                print(print_result.encode('utf-8'))
                progress_percentage = re.findall(b'\d+%', print_result.encode('utf-8'))[-1]
                message += f" Progress: {progress_percentage}\n"
            except Exception as e:
                message += f" Tailing logfile failed: {e}\n"
        elif unwrap(client.getInput(COMPLETED_JOB)):
            try:
                cmdlist = []
                update_cmd = f"tail -n 10 cellpose-{slurm_job_id_old}.log"
                
                # run a list of commands
                local_tmp_storage = "/tmp/"
                logfile = f"cellpose-{slurm_job_id_old}.log"
                results = slurmClient.scpull(
                        destination=f"{SLURM_HOME}/{logfile}",
                        source=local_tmp_storage,
                        check=True,
                        strict_host_key_checking=False)
                print(f"Ran slurm {results.__dict__}")
                
                export_file = local_tmp_storage+logfile
                output_display_name = f"Job logfile '{logfile}'"
                namespace = NSCREATED + "/SLURM/SLURM_GET_UPDATE"
                mimetype = 'text/plain'
                obj = client.upload(export_file, type=mimetype)
                obj_id = obj.id.val
                # webclient = "https://my-server/webclient/"
                url = f"get_original_file/{obj_id}/"
                client.setOutput("URL", wrap({"type": "URL", "href": url}))
                # client.setOutput("Message", wrap("Click the button to download"))
                # print(f"Uploaded object {obj_id}/{type(obj)}:{obj}")
                conn = BlitzGateway(client_obj=client)
                # project_ids = unwrap(client.getInput("IDs"))

                # file_ann = conn.createFileAnnfromLocalFile(
                #         export_file, mimetype=mimetype, ns=namespace, desc=output_display_name)
                # print("Attaching FileAnnotation to Projects: ", "File ID:", file_ann.getId(),
                #         ",", file_ann.getFile().getName(), "Size:", file_ann.getFile().getSize())
                # for projectId in project_ids:
                project_ids = unwrap(client.getInput("Project"))
                print(project_ids)
                project_id = project_ids[0].split(":")[0]
                print(project_id)
                project = conn.getObject("Project", project_id)
                # project.linkAnnotation(file_ann)     # link it to project.
                file_annotation, ann_message = script_utils.create_link_file_annotation(
                    conn, export_file, project, output=output_display_name,
                    namespace=namespace, mimetype=mimetype)
                
                if len(project_ids) > 1:  # link to the other given projects too
                    for project_id in project_ids[1:]:
                        project_id = project_id.split(":")[0]
                        project = conn.getObject("Project", project_id)
                        project.linkAnnotation(file_annotation)  # link it to project.
                
                message += ann_message
                client.setOutput("File_Annotation", robject(file_annotation._obj))
            except Exception as e:
                message += f" Importing logfile failed: {e}\n"

        client.setOutput("Message", rstring(str(message)))

    finally:
        client.closeSession()


if __name__ == '__main__':
    runScript()


