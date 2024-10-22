#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.shortcuts import render
from omeroweb.webclient.decorators import login_required, render_response
import logging

logger = logging.getLogger(__name__)

@login_required()
@render_response()
def imports_database_page(request, conn=None, **kwargs):
    return {'template': 'importsdatabase/webclient_plugins/imports_database_page.html'}

@login_required()
@render_response()
def imports_webclient_templates(request, base_template, **kwargs):
    """ Simply return the named template for imports database. """
    template_name = f'importsdatabase/webgateway/{base_template}.html'
    return {'template': template_name}
