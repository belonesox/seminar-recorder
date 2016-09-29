#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
 Setup for the package
"""

from setuptools import setup
setup(
    entry_points={
        'console_scripts': [
            'seminar_record=seminar_recorder:main',
        ],
    },
    name='seminar_recorder',
    version='1.01',
    packages=['seminar_recorder'],
    author_email = "stanislav.fomin@gmail.com",

)

