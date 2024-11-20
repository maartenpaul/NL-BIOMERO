#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 University of Dundee.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Aleksandra Tarkowska <A(dot)Tarkowska(at)dundee(dot)ac(dot)uk>,
#
# Version: 1.0

import os
from setuptools import setup, find_packages


# Utility function to read the README file.
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name="omero-database-pages",
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    packages=find_packages(exclude=['ez_setup']),
    description="A Python plugin for OMERO.web to display database pages",
    long_description=read('README.rst'),
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
    author='Cellular Imaging Amsterdam UMC',
    author_email='rrosas@amsterdamumc.nl',
    license='AGPL-3.0',
    url="https://github.com/Cellular-Imaging-Amsterdam-UMC/omero-database-pages",
    download_url='https://github.com/Cellular-Imaging-Amsterdam-UMC/omero-database-pages/archive/refs/heads/main.zip',
    keywords=['OMERO.web', 'plugin', 'database pages', 'imports database','workflows database'],
    install_requires=['omero-web>=5.6.0', 'pyjwt'],
    python_requires='>=3',
    include_package_data=True,
    zip_safe=False,
    package_data={
        'database_pages': [
            'templates/databasepages/webclient_plugins/imports_database_page.html',
            'templates/databasepages/webclient_plugins/workflows_database_page.html',
            'templates/databasepages/webclient_plugins/server_side_browser_page.html',
            'static/databasepages/css/database_pages.css',
            'static/databasepages/css/server_side_browser.css',
            'static/databasepages/js/server_side_browser.js',
            '03-database_pages.omero',
        ],
    },
    entry_points={
        'console_scripts': [
            'omero-database-pages-setup=database_pages.setup_integration:main',
        ],
    },
)
