#!/opt/omero/server/cellposeenv/bin/python
# PROCESSOR-2 
# Example OMERO.script using dynamic arguments
# Included in omero/developers/scripts/user-guide.txt
# A list of datasets will be dynamically generated and used to populate the
# script parameters every time the script is called

from re import I
import subprocess
import time
import omero
import omero.gateway
from omero import scripts
from omero.rtypes import rstring


RUN_ON_GPU_NS = "GPU"

def busy_wait(dt):   
    current_time = time.time()
    i = 0
    while (time.time() < current_time+dt):
        i += 1
    print(i)

def runScript():
    """
    The main entry point of the script
    """

    client = scripts.client(
        'Minimal Cellpose', 'Minimal script importing cellpose',
        namespaces=[RUN_ON_GPU_NS],
    )

    try:
        scriptParams = client.getInputs(unwrap=True)
        bashCommandName = "echo $HOSTNAME"
        hostname = subprocess.check_output(['bash', '-c', bashCommandName])
        bashCommandWorker = "echo $OMERO_WORKER_NAME"
        worker = subprocess.check_output(['bash', '-c', bashCommandWorker])
        
        import cellpose
        bashCommandCP = "/opt/omero/server/cellposeenv/bin/python -m pip show cellpose"
        cp = subprocess.check_output(['bash', '-c', bashCommandCP])
        # from cellpose import models
        # # model_type='cyto' or 'nuclei' or 'cyto2'
        # model = models.Cellpose(gpu=True)
        
        message = (
            f"This script ran on {worker.decode('utf-8')}:{hostname.decode('utf-8')}\n"
            f"Params: {scriptParams}\n"
            f"Library: {cp.decode('utf-8') }"
            )
        
        print(message)
        
        client.setOutput('Message', rstring(str(message)))    

    finally:
        client.closeSession()


if __name__ == '__main__':
    runScript()
