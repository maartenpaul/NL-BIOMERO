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
import configparser
from omero.grid import JobParams
from omero.rtypes import rstring
import omero.scripts as omscripts
import subprocess
from pathlib import Path
from typing import List
from fabric import Connection, Result

_PYCMD = "Python_Command"
_DEFAULT_CMD = "import numpy as np; arr = np.array([1,2,3,4,5]); print(arr.mean())"
_RUNPY = "Run_Python"
_RUNSLRM = "Check_SLURM_Status"
_SQUEUE = "Check_Queue"
_SINFO = "Check_Cluster"
_SOTHER = "Run_Other_Command"
_SCMD = "Linux_Command"
_DEFAULT_SCMD = "ls -la"


class SlurmClient(Connection):
    """A client for connecting to and interacting with a Slurm cluster over SSH.

    This class extends the Fabric Connection class, adding methods and attributes specific to working with Slurm.
    SlurmClient accepts the same arguments as Connection.

    Attributes:

    Example:
        # Create a SlurmClient object as contextmanager

        with SlurmClient() as client:

            # Run a command on the remote host

            result = client.run('sbatch myjob.sh')

            # Check whether the command succeeded

            if result.ok:
                print('Job submitted successfully!')

            # Print the output of the command

            print(result.stdout)

        # Create SlurmClient object from config

        with SlurmClient.from_config() as client:

            ...
    """
    DEFAULT_CONFIG_PATH_1 = "/etc/slurm-config.ini"
    DEFAULT_CONFIG_PATH_2 = "~/slurm-config.ini"
    DEFAULT_HOST = "slurm"
    DEFAULT_INLINE_SSH_ENV = True
    DEFAULT_SLURM_DATA_PATH = "$HOME/my-scratch/data/"

    def __init__(self,
                 host=DEFAULT_HOST,
                 user=None,
                 port=None,
                 config=None,
                 gateway=None,
                 forward_agent=None,
                 connect_timeout=None,
                 connect_kwargs=None,
                 inline_ssh_env=DEFAULT_INLINE_SSH_ENV,
                 slurm_data_path: Path = Path(DEFAULT_SLURM_DATA_PATH)):
        super(SlurmClient, self).__init__(host,
                                          user,
                                          port,
                                          config,
                                          gateway,
                                          forward_agent,
                                          connect_timeout,
                                          connect_kwargs,
                                          inline_ssh_env)
        self.slurm_data_path = slurm_data_path

    @classmethod
    def from_config(cls, configfile: str = '') -> 'SlurmClient':
        """Creates a new SlurmClient object using the parameters read from a configuration file (.ini).

        Defaults paths to look for config files are:
            - /etc/slurm-config.ini
            - ~/slurm-config.ini

        Note that this is only for the SLURM specific values that we added.
        Most configuration values are set via configuration mechanisms from Fabric library,
        like SSH settings being loaded from SSH config, /etc/fabric.yml or environment variables.
        See Fabric's documentation for more info on configuration if needed.

        Args:
            configfile (str): The path to your configuration file. Optional.

        Returns:
            SlurmClient: A new SlurmClient object.
        """
        # Load the configuration file
        configs = configparser.ConfigParser(allow_no_value=True)
        # Loads from default locations and given location, missing files are ok
        configs.read([cls.DEFAULT_CONFIG_PATH_1,
                     cls.DEFAULT_CONFIG_PATH_2, configfile])
        # Read the required parameters from the configuration file, fallback to defaults
        host = configs.get("SSH", "host", fallback=cls.DEFAULT_HOST)
        inline_ssh_env = configs.getboolean(
            "SSH", "inline_ssh_env", fallback=cls.DEFAULT_INLINE_SSH_ENV)
        slurm_data_path = Path(configs.get(
            "SLURM", "slurm_data_path", fallback=cls.DEFAULT_SLURM_DATA_PATH))
        # Create the SlurmClient object with the parameters read from the config file
        return cls(host=host, inline_ssh_env=inline_ssh_env, slurm_data_path=slurm_data_path)

    def validate(self):
        """Validate the connection to the Slurm cluster by running a simple command.

        Returns:
            bool: True if the command is executed successfully, False otherwise.
        """
        return self.run('echo " "').ok

    def runCommands(self, cmdlist: List[str]) -> Result:
        """Runs a list of shell commands consecutively, ensuring success of each before calling the next.

        Args:
            cmdlist (List[str]): A list of shell commands to run.

        Returns:
            Result: The result of the last command in the list.
        """
        cmd = ' && '.join(cmdlist)
        print(f"Running commands: {cmd}")
        return self.run(cmd)

    def transfer_data(self, local_path: Path) -> Result:
        """Transfers a file or directory from the local machine to the remote Slurm cluster.

        Args:
            local_path (Path): The local path to the file or directory to transfer.

        Returns:
            Result: The result of the file transfer operation.
        """
        return self.put(local=str(local_path), remote=self.slurm_data_path)


def runScript():
    """
    The main entry point of the script
    """

    with SlurmClient() as slurmClient:

        params = JobParams()
        params.authors = ["Torec Luik"]
        params.version = "0.0.3"
        params.description = f'''Example script to run on slurm cluster

        Runs a script remotely on SLURM.
        
        Connection ready? {slurmClient.validate()}
        '''
        params.name = 'Minimal Slurm Script'
        params.contact = 't.t.luik@amsterdamumc.nl'
        params.institutions = ["Amsterdam UMC"]
        params.authorsInstitutions = [[1]]

        input_list = [
            omscripts.Bool(_RUNPY, grouping="01", default=True),
            omscripts.String(_PYCMD, optional=False, grouping="01.1",
                             description="The Python command to run on slurm",
                             default=_DEFAULT_CMD),
            omscripts.Bool(_RUNSLRM, grouping="02", default=False),
            omscripts.Bool(_SQUEUE, grouping="02.1", default=False),
            omscripts.Bool(_SINFO, grouping="02.2", default=False),
            omscripts.Bool(_SOTHER, grouping="03", default=False),
            omscripts.String(_SCMD, optional=False, grouping="03.1",
                             description="The linux command to run on slurm",
                             default=_DEFAULT_SCMD),
        ]
        inputs = {
            p._name: p for p in input_list
        }
        params.inputs = inputs
        client = omscripts.client(params)

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
                    cmdlist.append("squeue -u $USER")
                if scriptParams[_SINFO]:
                    cmdlist.append("sinfo")
            if scriptParams[_SOTHER]:
                cmdlist.append(scriptParams[_SCMD])
            if scriptParams[_RUNPY]:
                cmdlist.append("module load Anaconda3 && " +
                               f"python -c '{scriptParams[_PYCMD]}'")
            try:
                # run a list of commands
                for cmd in cmdlist:
                    results = slurmClient.run(cmd)
                    print(f"Ran slurm {results}")
            except subprocess.CalledProcessError as e:
                results = f"Error {e.__dict__}"
                print(results)
            finally:
                print_result.append(f"{results.stdout}")
            client.setOutput("Message", rstring("".join(print_result)))
        finally:
            client.closeSession()


if __name__ == '__main__':
    runScript()
