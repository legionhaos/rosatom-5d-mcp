# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import os

_PLUGIN_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin.json")


def getMetaData():
    try:
        with open(_PLUGIN_JSON, "r") as handle:
            return json.load(handle)
    except (OSError, IOError, ValueError):
        return {}


def register(app):
    from plugin.slicer_bridge.extension import STEAIExtension
    return {"extension": STEAIExtension()}
