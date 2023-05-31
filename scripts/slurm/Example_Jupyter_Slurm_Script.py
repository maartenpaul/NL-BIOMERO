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
from omero.rtypes import rstring, unwrap
from omero.gateway import BlitzGateway
import omero.scripts as omscripts
import subprocess
import os
from pathlib import Path
from typing import Union, List
from fabric import Connection

SSH_KEY = '~/.ssh/id_rsa'
SLURM_REMOTE = 'luna.amc.nl'
SLURM_USER = 'ttluik'
SSH_HOSTS = '~/.ssh/known_hosts'
_PYCMD = "Python_Command"
_DEFAULT_CMD = "import numpy as np; arr = np.array([1,2,3,4,5]); print(arr.mean())"
_RUNPY = "Run_Python"
_RUNSLRM = "Check_SLURM_Status"
_SQUEUE = "Check_Queue"
_SINFO = "Check_Cluster"
_SOTHER = "Run_Other_Command"
_SCMD = "Linux_Command"
_DEFAULT_SCMD = "ls -la"
_JUPYTER_PORT = 9000

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
    params.version = "0.0.1"
    params.description = f'''Example script to run on slurm cluster

    Runs a script remotely on: {SLURM_REMOTE}
    
    Connection ready? {slurmClient.validate()}
    '''
    params.name = 'Minimal Slurm Script'
    params.contact = 't.t.luik@amsterdamumc.nl'
    params.institutions = ["Amsterdam UMC"]
    params.authorsInstitutions = [[1]]
    
    input_list = [
    ]
    inputs = {
        p._name: p for p in input_list
    }
    params.inputs = inputs
    client = omscripts.client(params)

    # we can now create our Blitz Gateway by wrapping the client object
    conn = BlitzGateway(client_obj=client)
    try:
        scriptParams = client.getInputs(unwrap=True)
        print(f"Params: {scriptParams}")
        print(f"Validating slurm connection:\
              {slurmClient.validate()} for {slurmClient.__dict__}")
        
        print(f"Running py cmd: {scriptParams[_PYCMD]}")
        print_result = []
        cmdlist = []
        if scriptParams[_RUNSLRM]:
            if scriptParams[_SQUEUE]: 
                cmdlist.append(f"squeue -u {SLURM_USER}")
            if scriptParams[_SINFO]: 
                cmdlist.append("sinfo")
        if scriptParams[_SOTHER]: 
            cmdlist.append(scriptParams[_SCMD])      
        if scriptParams[_RUNPY]:
            cmdlist.append("module load Anaconda3")
            cmdlist.append(f"python -c '{scriptParams[_PYCMD]}'")
        try:
            c = Connection(host=SLURM_REMOTE, user=SLURM_USER)
            with c.forward_local(_JUPYTER_PORT):
                c.run('command')
                c.put('file')
            # # run a list of commands
            # results = slurmClient.cmd(
            #     cmdlist,
            #     check=True,
            #     strict_host_key_checking=False)
            print(f"Ran slurm {results.__dict__}")
        except subprocess.CalledProcessError as e:
            results = f"Error {e.__dict__}"
            print(results)
        finally:
            print_result.append(f"{results.stdout.decode('utf-8')}")
        # Scripts that generate a URL link should return the omero.rtypes.rmap, 
        # with the following keys: “type”: “URL”, 
        # “href”: “URL address to open”, 
        # “title”: “Help message”. 
        # The client will give users the option of opening the URL in a new browser window/tab. 
        # To use this feature the URL omero.types.rmap should use the key: ‘URL’ in the output map.
        # url = omero.rtypes.wrap({
        #     "type": "URL",
        #     "href": "https://<server>:<jupyterport>",
        #     "title": "Open URL link to your jupyter notebook",
        # })
        # client.setOutput("URL", url)
        client.setOutput("Message", rstring("".join(print_result)))
    finally:
        client.closeSession()


if __name__ == '__main__':
    runScript()
