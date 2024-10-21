#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.shortcuts import render
from omeroweb.webclient.decorators import login_required, render_response
from omero.rtypes import unwrap
import logging
from django.http import JsonResponse
from omero.gateway import BlitzGateway
from omero.api import IScriptPrx
from omero.sys import Parameters
from omero.model import OriginalFileI

logger = logging.getLogger(__name__)

@login_required()
@render_response()
def webclient_templates_import_datase(request, base_template, **kwargs):
    """ Simply return the named template. Similar functionality to
    django.views.generic.simple.direct_to_template """
    template_name = 'importsdatabase/webgateway/%s.html' % base_template
    return {'template': template_name}

@login_required()
def get_imports_database(request, conn=None, **kwargs):
    pass