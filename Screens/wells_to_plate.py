#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
 omero/util_scripts/Wells_To_Plate.py

-----------------------------------------------------------------------------
  Copyright (C) 2006-2016 University of Dundee. All rights reserved.


  This program is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 2 of the License, or
  (at your option) any later version.
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License along
  with this program; if not, write to the Free Software Foundation, Inc.,
  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

------------------------------------------------------------------------------

This script generates a Plate from a Well of Images, i.e. it creates a grid
layout of the multiple Fields. Multiple Well selection is supported.

@author Damir Sudar
<a href="mailto:dsudar@qimagingsys.com">dsudar@qimagingsys.com</a>
@version 4.3
<small>
(<b>Internal version:</b> $Revision: $Date: $)
</small>
@since 3.0-Beta4.3
"""

import omero.scripts as scripts
from omero.gateway import BlitzGateway
import omero.util.script_utils as script_utils
import omero

from omero.rtypes import rint, rlong, rstring, robject, unwrap

ls_abc = ["A","B","C","D","E","F","G","H","I","J","K","L","M",
          "N","O","P","Q","R","S","T","U","V","W","X","Y","Z",
          "AA","AB","AC","AD","AE","AF","AG","AH","AI","AJ","AK","AL","AM",
          "AN","AO","AP","AQ","AR","AS","AT","AU","AV","AW","AX","AY","AZ",
          "BA","BB","BC","BD","BE","BF","BG","BH","BI","BJ","BK","BL","BM",
          "BN","BO","BP","BQ","BR","BS","BT","BU","BV","BW","BX","BY","BZ"]



def addImageToPlate(conn, image, plateId, column, row):
    """
    Add the Image to a Plate, creating a new well at the
    specified column and row
    NB - This will fail if there is already a well at that point
    """
    updateService = conn.getUpdateService()

    well = omero.model.WellI()
    well.plate = omero.model.PlateI(plateId, False)
    well.column = rint(column)
    well.row = rint(row)
    well = updateService.saveAndReturnObject(well)

    try:
        ws = omero.model.WellSampleI()
        ws.image = omero.model.ImageI(image.id, False)
        ws.well = well
        well.addWellSample(ws)
        updateService.saveObject(ws)
    except:
        print "Failed to add image to well sample"
        return False

    return True


def well_fields_to_plate(conn, scriptParams, wellId, screen):

    well = conn.getObject("Well", wellId)
    if well is None:
        print "No well found for ID %s" % wellId
        return

    updateService = conn.getUpdateService()

    # make plate name from well coordinate
    plname = "%s%02d" % (ls_abc[well.row], well.column + 1)

    # create Plate
    plate = omero.model.PlateI()
    plate.name = rstring(plname)
    plate.columnNamingConvention = rstring(str(scriptParams["Column_Names"]))
    # 'letter' or 'number'
    plate.rowNamingConvention = rstring(str(scriptParams["Row_Names"]))
    plate = updateService.saveAndReturnObject(plate)

    if screen is not None and screen.canLink():
        link = omero.model.ScreenPlateLinkI()
        link.parent = omero.model.ScreenI(screen.id, False)
        link.child = omero.model.PlateI(plate.id.val, False)
        updateService.saveObject(link)
    else:
        link = None

    print "Linking images from Well: %d to Plate: %s: %d" \
        % (well.id, plname, plate.id.val)

    row = 0
    col = 0

    firstAxisIsRow = scriptParams["First_Axis"] == 'row'
    axisCount = scriptParams["First_Axis_Count"]

    # loop over images in well
    index = well.countWellSample()
    for index in xrange(0, index):
        image = well.getImage(index)
        print "    linking image: %d to row: %d, column: %d" \
            % (image.id, row, col)
        addedCount = addImageToPlate(conn, image, plate.id.val, col, row)
        # update row and column index
        if firstAxisIsRow:
            row += 1
            if row >= axisCount:
                row = 0
                col += 1
        else:
            col += 1
            if col >= axisCount:
                col = 0
                row += 1

    return plate, link


def mwell_fields_to_plates(conn, scriptParams):

    updateService = conn.getUpdateService()

    message = ""

    # Get the well IDs
    wells, logMessage = script_utils.getObjects(conn, scriptParams)
    message += logMessage

    # Filter dataset IDs by permissions
    IDs = [ws.getId() for ws in wells if ws.canLink()]
    if len(IDs) != len(wells):
        permIDs = [str(ws.getId()) for ws in wells if not ws.canLink()]
        message += "You do not have the permissions to add the images from"\
            " the well(s): %s." % ",".join(permIDs)
    if not IDs:
        return None, message

    # find or create Screen if specified
    screen = None
    newscreen = None
    if "Screen" in scriptParams and len(scriptParams["Screen"]) > 0:
        s = scriptParams["Screen"]
        # see if this is ID of existing screen
        try:
            screenId = long(s)
            screen = conn.getObject("Screen", screenId)
        except ValueError:
            pass
        # if not, create one
        if screen is None:
            newscreen = omero.model.ScreenI()
            newscreen.name = rstring(s)
            newscreen = updateService.saveAndReturnObject(newscreen)
            screen = conn.getObject("Screen", newscreen.id.val)

    plates = []
    links = []
    for wellId in IDs:
        plate, link = well_fields_to_plate(conn, scriptParams,
                                                     wellId, screen)
        if plate is not None:
            plates.append(plate)
        if link is not None:
            links.append(link)

    if newscreen:
        message += "New screen created: %s." % newscreen.getName().val
        robj = newscreen
    elif plates:
        robj = plates[0]
    else:
        robj = None

    if plates:
        if len(plates) == 1:
            message += " New plate created: %s" % plates[0].name.val
        else:
            message += " %s plates created" % len(plates)
        if len(plates) == len(links):
            message += "."
        else:
            message += " but was not attached."
    else:
        message += "No plate created."
    return robj, message


def runAsScript():
    """
    The main entry point of the script, as called by the client via the
    scripting service, passing the required parameters.
    """

    dataTypes = [rstring('Well')]
    firstAxis = [rstring('column'), rstring('row')]
    rowColNaming = [rstring('letter'), rstring('number')]

    client = scripts.client(
        'Wells_To_Plate.py',
        """Take all Fields in a Well and put them in a new Plate, \
arranging them into rows or columns as specified.
Optionally add the Plate to a new or existing Screen.
See http://help.openmicroscopy.org/scripts.html""",

        scripts.String(
            "Data_Type", optional=False, grouping="1",
            description="Choose source of images (only Well supported)",
            values=dataTypes, default="Well"),

        scripts.List(
            "IDs", optional=False, grouping="2",
            description="List of Well IDs to convert to new"
            " Plates.").ofType(rlong(0)),

        scripts.String(
            "First_Axis", grouping="3", optional=False, default='column',
            values=firstAxis,
            description="""Arrange images accross 'column' first or down"
            " 'row'"""),

        scripts.Int(
            "First_Axis_Count", grouping="3.1", optional=False, default=12,
            description="Number of Rows or Columns in the 'First Axis'",
            min=1),

        scripts.String(
            "Column_Names", grouping="4", optional=False, default='number',
            values=rowColNaming,
            description="""Name plate columns with 'number' or 'letter'"""),

        scripts.String(
            "Row_Names", grouping="5", optional=False, default='letter',
            values=rowColNaming,
            description="""Name plate rows with 'number' or 'letter'"""),

        scripts.String(
            "Screen", grouping="6",
            description="Option: put output Plate(s) in a Screen. Enter"
            " Name of new screen or ID of existing screen"""),

        version="0.0.1",
        authors=["Damir Sudar"],
        institutions=["Quantitative Imaging Systems LLC"],
        contact="dsudar@qimagingsys.com",
    )

    try:
        scriptParams = client.getInputs(unwrap=True)
        print scriptParams

        # wrap client to use the Blitz Gateway
        conn = BlitzGateway(client_obj=client)

        # convert Well(s) to Plate(s). Returns new plates and/or screen
        newObj, message = mwell_fields_to_plates(conn, scriptParams)

        client.setOutput("Message", rstring(message))
        if newObj:
            client.setOutput("New_Object", robject(newObj))

    finally:
        client.closeSession()

if __name__ == "__main__":
    runAsScript()