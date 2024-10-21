#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.urls import re_path
from . import views

urlpatterns = [
    re_path(r'^webclient_templates/(?P<base_template>[a-z0-9_]+)/',
            views.webclient_templates, name='webclient_templates'),
    re_path(r'^get_imports_database/$', views.get_imports_database, name='get_imports_database'),
]