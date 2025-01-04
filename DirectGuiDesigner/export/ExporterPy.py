"""Module for exporting a project to a python (.py) file."""

#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "Fireclaw the Fox"
__license__ = """
Simplified BSD (BSD 2-Clause) License.
See License.txt or http://opensource.org/licenses/BSD-2-Clause for more info
"""

import os
import logging
from panda3d.core import ConfigVariableBool
from DirectFolderBrowser.DirectFolderBrowser import DirectFolderBrowser

from DirectGuiDesigner.tools.JSONTools import JSONTools
from DirectGuiDesigner.core.PropertyHelper import PropertyHelper


class ExporterPy:
    functionMapping = {
        "base":{"initialText":"get"},
        "text":{"align":"align", "scale":"scale", "pos":"pos", "fg":"fg", "bg":"bg"}}

    # list of control names starting with the following will be ignored
    ignoreControls = ["item", "cancelframe", "popupMarker", "popupMenu"]
    # list of control names staritng with the following will always be included
    explIncludeControls = ["itemFrame"]

    tabWidth = 4

    def __init__(
            self,
            fileName,
            guiElementsDict,
            customWidgetHandler,
            getEditorFrame,
            getEditorRootCanvas,
            getAllEditorPlacers,
            allWidgetDefinitions,
            tooltip,
            usePixel2D):
        self.guiElementsDict = guiElementsDict
        self.customWidgetHandler = customWidgetHandler

        jsonTools = JSONTools()
        self.jsonFileContent = jsonTools.getProjectJSON(
            self.guiElementsDict,
            getEditorFrame,
            getEditorRootCanvas,
            getAllEditorPlacers,
            allWidgetDefinitions,
            usePixel2D)
        self.jsonElements = self.jsonFileContent["ComponentList"]

        self.createdParents = ["root"]
        self.postponedElements = {}
        self.postSetupCalling = []
        self.radiobuttonDict = {}
        self.customWidgetAddDict = {}

        importStatements = {
            "DirectButton":"from direct.gui.DirectButton import DirectButton",
            "DirectEntry":"from direct.gui.DirectEntry import DirectEntry",
            "DirectEntryScroll":"from direct.gui.DirectEntryScroll import DirectEntryScroll",
            "DirectCheckBox":"from direct.gui.DirectCheckBox import DirectCheckBox",
            "DirectCheckButton":"from direct.gui.DirectCheckButton import DirectCheckButton",
            "DirectOptionMenu":"from direct.gui.DirectOptionMenu import DirectOptionMenu",
            "DirectRadioButton":"from direct.gui.DirectRadioButton import DirectRadioButton",
            "DirectSlider":"from direct.gui.DirectSlider import DirectSlider",
            "DirectScrollBar":"from direct.gui.DirectScrollBar import DirectScrollBar",
            "DirectScrolledList":"from direct.gui.DirectScrolledList import DirectScrolledList",
            "DirectScrolledListItem":"from direct.gui.DirectScrolledList import DirectScrolledListItem",
            "DirectLabel":"from direct.gui.DirectLabel import DirectLabel",
            "DirectWaitBar":"from direct.gui.DirectWaitBar import DirectWaitBar",
            "OkDialog":"from direct.gui.DirectDialog import OkDialog",
            "OkCancelDialog":"from direct.gui.DirectDialog import OkCancelDialog",
            "YesNoDialog":"from direct.gui.DirectDialog import YesNoDialog",
            "YesNoCancelDialog":"from direct.gui.DirectDialog import YesNoCancelDialog",
            "RetryCancelDialog":"from direct.gui.DirectDialog import RetryCancelDialog",
            "DirectFrame":"from direct.gui.DirectFrame import DirectFrame",
            "DirectScrolledFrame":"from direct.gui.DirectScrolledFrame import DirectScrolledFrame",
        }

        self.content = """#!/usr/bin/python
# -*- coding: utf-8 -*-

# This file was created using the DirectGUI Designer

from direct.gui import DirectGuiGlobals as DGG
"""
        usedImports = []
        for name, elementInfo in self.guiElementsDict.items():
            if elementInfo.type not in usedImports:
                if elementInfo.type in importStatements:
                    self.content = "{}\n{}".format(self.content, importStatements[elementInfo.type])
                else:
                    self.content = "{}\n{}".format(self.content, elementInfo.customImportPath)
                usedImports.append(elementInfo.type)
        self.content += """
from panda3d.core import (
    LPoint3f,
    LVecBase3f,
    LVecBase4f,
    TextNode
)

class GUI:
    def __init__(self, rootParent=None):
        """

        for name, elementInfo in self.jsonElements.items():
            self.content += self.__createElement(name, elementInfo)

        self.content += "\n"
        for line in self.postSetupCalling:
            self.content += line + "\n"

        for radioButton, others in self.radiobuttonDict.items():
            self.content += " " * tabWidth * 2 + f"{radioButton}.setOthers(["
            for other in others:
                self.content += other + ","
            self.content += "])\n"

        topLevelItems = []
        for name, elementInfo in self.jsonElements.items():
            widget = self.customWidgetHandler.getWidget(elementInfo["type"])
            if widget is not None:
                if name not in self.customWidgetAddDict: continue
                for element in self.customWidgetAddDict[name]:
                    if widget.addItemFunction is not None:
                        extraArgs = ""
                        childInfo = self.jsonElements[element.removeprefix("self.")]  # elementInfo for elements to add
                        if args := childInfo["addItemExtraArgs"]:  # add extra args to add item function
                            if isinstance(widget.addItemExtraArgs, dict):
                                for arg, definition in zip(args, widget.addItemExtraArgs.values()):
                                    valueType = definition["type"]
                                    if valueType == "str":
                                        extraArgs += f", '{arg}'"
                                    elif valueType == "element":
                                        extraArgs += f", self.{arg}"
                                    else:
                                        extraArgs += f", {arg}"
                            else:
                                for arg in args:
                                    if isinstance(arg, str):
                                        extraArgs += f", '{arg}'"
                                    else:
                                        extraArgs += f", {arg}"

                        self.content += " " * tabWidth * 2 + f"self.{name}.{widget.addItemFunction}({element}{extraArgs})\n"

            if elementInfo["parent"] == "root" or elementInfo["parent"].startswith("a2d"):
                topLevelItems.append(name)

        # Create helper functions for toplevel elements
        if len(topLevelItems) > 0:
            self.content += "\n"
            self.content += " " * tabWidth + "def show(self):\n"
            for name in topLevelItems:
                self.content += " " * tabWidth * 2 + f"self.{name}.show()\n"

            self.content += "\n"
            self.content += " " * tabWidth + "def hide(self):\n"
            for name in topLevelItems:
                self.content += " " * tabWidth * 2 + f"self.{name}.hide()\n"

            self.content += "\n"
            self.content += " " * tabWidth + "def destroy(self):\n"
            for name in topLevelItems:
                self.content += " " * tabWidth * 2 + f"self.{name}.destroy()\n"

        # Make script executable if desired
        if ConfigVariableBool("create-executable-scripts", False).getValue():
            self.content += """
# We need a showbase instance to make this script directly runnable
from direct.showbase.ShowBase import ShowBase
app = ShowBase()\n"""
            if usePixel2D:
                self.content += "GUI(app.pixel2d)\n"
            else:
                self.content += "GUI()\n"
            self.content += "app.run()\n"

        self.browser = DirectFolderBrowser(
            self.save,
            True,
            defaultPath=os.path.dirname(fileName),
            defaultFilename=os.path.split(fileName)[1],
            tooltip=tooltip,
            askForOverwrite=True,
            title="Export as Python script")

    def save(self, doSave):
        """Used when exporting manually (through the file browser)."""
        if doSave:
            path = self.browser.get()
            path = os.path.expanduser(path)
            path = os.path.expandvars(path)
            self.__executeSave(path)
            base.messenger.send("setLastPath", [path])
        self.browser.destroy()
        del self.browser

    def __executeSave(self, path):
        """Actually export project to file."""
        with open(path, 'w') as outfile:
            outfile.write(self.content)

    def __createElement(self, name, elementInfo):
        extraOptions = ""
        for optionName, optionValue in elementInfo["extraOptions"].items():
            v = optionValue
            if "others" in optionName:
                continue
            writeAsIsList = ["command"]
            if type(v) is list:
                v = f"[{','.join(map(str, v))}]"
            elif type(v) is str and optionName not in writeAsIsList:
                v = f"'{v}'"

            definition = PropertyHelper.getDefinition(elementInfo, optionName)
            # we don't want to pass None values to loader functions, just store None itself
            # if this is not intended for some loaders, we need to enhance the definition
            # to make sure we know when to use the loader func and when to store None.
            if definition.loaderFunc is not None and v is not None:
                if isinstance(definition.loaderFunc, str):
                    v = definition.loaderFunc.replace("value", f"{v}")

            extraOptions += " " * tabWidth * 3 + f"{optionName}={v},\n"
        elementCode = """
        self.{} = {}(
{}{}        )\n""".format(
            name,
            elementInfo["type"],
            self.__writeElementOptions(name, elementInfo),
            extraOptions,
            )
        if elementInfo["element"]["transparency"] != "M_none":
            elementCode += " " * tabWidth * 2 + f"self.{name}.setTransparency({elementInfo['element']['transparency']})\n"

        if elementInfo["type"] == "DirectScrolledListItem":
            self.postSetupCalling.append(" " * tabWidth * 2 + f"self.{elementInfo['parent']}.addItem(self.{name})")

        return elementCode

    def __writeElementOptions(self, name, elementInfo):
        elementOptions = ""
        indent = " " * tabWidth * 3

        for optionKey, optionValue in elementInfo["element"].items():
            if optionKey.endswith("transparency"):
                continue

            if optionKey in elementInfo["extraOptions"].keys():
                continue

            elementOptions += f"{indent}{optionKey} = {optionValue},\n"

        for optionKey, optionValue in elementInfo["extraOptions"].items():
            if optionKey == "others":
                others = []
                for other in optionValue:
                    others.append("self.{}".format(other))
                self.radiobuttonDict["self.{}".format(name)] = others

        if elementInfo["parent"] != "root":
            self.canvasParents = [
                "a2dTopCenter","a2dBottomCenter","a2dLeftCenter","a2dRightCenter",
                "a2dTopLeft","a2dTopRight","a2dBottomLeft","a2dBottomRight"]

            if elementInfo["parent"] in self.jsonElements and self.jsonElements[elementInfo["parent"]]["type"] == "DirectScrollFrame":
                # use the canvas as parent
                elementOptions += indent + "parent=self." + elementInfo["parent"] + ".getCanvas(),\n"
            elif elementInfo["parent"] in self.jsonElements and elementInfo["addItemNode"] is not None:
                elementOptions += indent + "parent=self." + elementInfo["parent"] + "." + elementInfo["addItemNode"] + ",\n"
            elif elementInfo["parent"] in self.jsonElements and self.customWidgetHandler.getWidget(self.jsonElements[elementInfo["parent"]]["type"]) is not None:
                widget = self.customWidgetHandler.getWidget(self.jsonElements[elementInfo["parent"]]["type"])
                if widget.addItemFunction is not None:
                    if elementInfo["parent"] in self.customWidgetAddDict:
                        self.customWidgetAddDict[elementInfo["parent"]].append("self.{}".format(name))
                    else:
                        self.customWidgetAddDict[elementInfo["parent"]] = ["self.{}".format(name)]
            elif elementInfo["parent"] in self.canvasParents:
                elementOptions += indent + "parent=base." + elementInfo["parent"] + ",\n"
            else:
                elementOptions += indent + "parent=self." + elementInfo["parent"] + ",\n"
        else:
            # use the parent passed to the class
            elementOptions += indent + "parent=rootParent,\n"

        return elementOptions
