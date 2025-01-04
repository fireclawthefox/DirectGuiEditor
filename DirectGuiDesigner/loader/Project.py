"""Module for loading a project from a '.gui' file."""

#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "Fireclaw the Fox"
__license__ = """
Simplified BSD (BSD 2-Clause) License.
See License.txt or http://opensource.org/licenses/BSD-2-Clause for more info
"""

import os
import json
import logging
import tempfile

from direct.showbase.DirectObject import DirectObject
from DirectGuiDesigner.core.PropertyHelper import PropertyHelper
from DirectGuiDesigner.core.ElementInfo import ElementInfo

from DirectFolderBrowser.DirectFolderBrowser import DirectFolderBrowser

# We need these to be able to load the objects from the json file
from panda3d.core import TextNode
from panda3d.core import NodePath
from panda3d.core import LVecBase2f, LVecBase3f, LVecBase4f, LPoint2f, LPoint3f, LPoint4f
from panda3d.core import LVecBase2, LVecBase3, LVecBase4, LPoint2, LPoint3, LPoint4, ConfigVariableString

import importlib.util


class ProjectLoader(DirectObject):
    """Class for loading project files (.gui)."""

    funcMap = {"initialText":"set"}
    # This prioList will be walked through if all other options not in
    # this list have already been set
    prioList = ["frameSize"]
    setAsOption = ["frameSize", "canvasSize", "indicatorValue", "frameColor", "barColor", "barRelief", "range", "value", "relief", "borderWidth", "clipSize", "scrollBarWidth", "state"]
    ignoreMap = []#"state"]
    ignoreComponentSplit = ["text", "image"]

    def __init__(self, fileName, visualEditorInfo, elementHandler, customWidgetHandler, getEditorPlacer, allWidgetDefinitions, exceptionLoading=False, tooltip=None, newProjectCall=None, directLoading=False):
        self.newProjectCall = newProjectCall
        self.extraOptions = ["borderWidth", "frameColor", "initialText", "clipSize"]
        self.parentMap = {}
        self.radiobuttonOthersDict = {}
        self.elementDict = {}
        self.elementHandler = elementHandler
        self.customWidgetHandler = customWidgetHandler
        self.visualEditorInfo = visualEditorInfo
        self.visualEditor = visualEditorInfo.element
        self.getEditorPlacer = getEditorPlacer
        self.hasErrors = False
        self.allWidgetDefinitions = allWidgetDefinitions
        if directLoading:
            self.__executeLoad(fileName)
        elif exceptionLoading:
            self.excLoad()
        else:
            self.browser = DirectFolderBrowser(
                self.Load,
                True,
                defaultPath=os.path.dirname(fileName),
                defaultFilename=os.path.split(fileName)[1],
                tooltip=tooltip,
                askForOverwrite=False,
                title="Load GUI Project")

    def excLoad(self):
        """Load an exception save."""
        tmpPath = os.path.join(tempfile.gettempdir(), "DGDExceptionSave.gui")
        self.__executeLoad(tmpPath)

    def get(self):
        """Get the loaded project."""
        return self.elementDict

    def Load(self, doLoad):
        """Used when user loads a project manually (using the file browser)."""
        if doLoad:
            path = self.browser.get()
            path = os.path.expanduser(path)
            path = os.path.expandvars(path)

            if not os.path.exists(path):
                base.messenger.send("showWarning", ["File \"{}\" does not exist.".format(path)])
                return

            if self.newProjectCall():
                self.__executeLoad(path)
            else:
                self.accept("clearDirtyFlag", self.__executeLoad, [path])
        self.browser.destroy()
        del self.browser

    def __executeLoad(self, path):
        """Do the actual loading from file 'path'."""
        fileContent = None
        with open(path, 'r') as infile:
            try:
                fileContent = json.load(infile)
            except Exception as e:
                logging.error("Couldn't load project file {}".format(infile))
                logging.exception(e)
                base.messenger.send("showWarning", ["Error while loading Project!\nPlease check output logs for more information."])
                return
        if fileContent is None:
            logging.error("Problems reading Project file: {}".format(infile))
            return

        self.canvasParents = [
            "a2dTopCenter","a2dBottomCenter","a2dLeftCenter","a2dRightCenter",
            "a2dTopLeft","a2dTopRight","a2dBottomLeft","a2dBottomRight"]
        self.createdParents = ["root"] + self.canvasParents
        self.postponedElements = {}
        if fileContent["ProjectVersion"] != "0.2a":
            logging.warning("Unsupported Project Version")
            base.messenger.send("showWarning", ["Unsupported Project Version"])
            return
        base.messenger.send("setVisualEditorParent", [fileContent["EditorConfig"]["usePixel2D"]])
        base.messenger.send("setVisualEditorCanvasSize", [eval(fileContent["EditorConfig"]["canvasSize"])])
        for name, elementInfo in fileContent["ComponentList"].items():
            self.__createElement(name, elementInfo)

        for elementInfo, option in self.radiobuttonOthersDict.items():
            elementList = []
            for elementId, info in self.elementDict.items():
                if info.name in option:
                    elementList.append(info.element)
            elementInfo.element["others"] = elementList

        if self.hasErrors:
            base.messenger.send("showWarning", ["Errors occured while loading the project!\nProject may not be fully loaded\nSee output log for more information."])
            return

        base.messenger.send("setLastPath", [path])
        base.messenger.send("updateElementDict-afterLoad", [self.elementDict])

    def __createElement(self, name, info):
        """Control the creation of gui elements so that they are created in the correct order."""
        if info["parent"] not in self.createdParents:
            self.postponedElements[name] = info
            return

        # create the element
        self.__createControl(name, info)
        self.createdParents.append(name)

        if name in self.postponedElements.keys():
            del self.postponedElements[name]

        # check if we can create postponed elements
        for elementName, elementInfo in self.postponedElements.copy().items():
            if elementName in self.createdParents:
                continue
            if elementInfo["parent"] in self.createdParents:
                self.__createElement(elementName, elementInfo)

    def __createControl(self, jsonElementName, jsonElementInfo):
        """Create a specific gui element."""
        funcName = f"create{jsonElementInfo['type']}"
        if not hasattr(self.elementHandler, funcName):
            logging.error("Couldn not create element, unknown function {}".format(funcName))
            return

        parentName = jsonElementInfo["parent"]
        parent = None
        if parentName in self.parentMap.keys():
            parent = self.elementDict[self.parentMap[parentName]]
        elif parentName in self.canvasParents:
            parent = self.getEditorPlacer(parentName)

        elementInfo = self.__createElementInfo(jsonElementInfo, funcName, parent)
        if elementInfo is None:
            return

        # load the extra definitions of the element info
        elementInfo.command = jsonElementInfo["command"]
        elementInfo.extraArgs = jsonElementInfo["extraArgs"]
        elementInfo.extraOptions = jsonElementInfo["extraOptions"]
        elementInfo.addItemExtraArgs = jsonElementInfo["addItemExtraArgs"]
        elementInfo.addItemNode = jsonElementInfo["addItemNode"]
        elementInfo.name = jsonElementName
        if "transparency" in jsonElementInfo:
            elementInfo.element.setTransparency(eval(jsonElementInfo["transparency"]))

        if type(elementInfo) is tuple:
            self.__updateElementInfoTuple(elementInfo, parent, jsonElementInfo)
        elif type(parent) == type(NodePath()):
            self.__updateElementInfoNodePath(elementInfo, parent, jsonElementInfo)
        else:
            self.__updateElementInfoOtherType(elementInfo, parent, jsonElementInfo)
        base.messenger.send("refreshStructureTree")

    def __updateElementInfoTuple(self, elementInfo, parent, jsonElementInfo):
        if parent is not None and "DirectScrolledList" == parent.type:
            parent.element.addItem(elementInfo[0].element)
        elif parent is not None and "DirectEntryScroll" == parent.type:
            parent.element.setEntry(elementInfo[0].element)
            parent.extraOptions["entry"] = "self." + elementInfo[0].name
        parentWidget = self.customWidgetHandler.getWidget(parent.type if parent is not None else "")
        if parentWidget is not None \
        and parentWidget.addItemFunction is not None:
            # call custom widget add function
            getattr(parent.element, parentWidget.addItemFunction)(elementInfo[0].element)

        for entry in elementInfo:
            entry.parent = parent
            self.__setProperties(entry, jsonElementInfo)
            self.elementDict[entry.element.guiId] = entry
            self.parentMap[jsonElementName] = entry.element.guiId

    def __updateElementInfoNodePath(self, elementInfo, parent, jsonElementInfo):
        elementInfo.parent = parent
        self.__setProperties(elementInfo, jsonElementInfo)
        if elementInfo.type == "DirectScrolledFrame":
            elementInfo.element.setScrollBarWidth()
        self.elementDict[elementInfo.element.guiId] = elementInfo
        self.parentMap[jsonElementName] = elementInfo.element.guiId

    def __updateElementInfoOtherType(self, elementInfo, parent, jsonElementInfo):
        elementInfo.parent = parent
        if parent is not None and "DirectScrolledList" == parent.type:
            parent.element.addItem(elementInfo.element)
        elif parent is not None and "DirectEntryScroll" == parent.type:
            parent.element.setEntry(elementInfo.element)
            parent.extraOptions["entry"] = "self." + elementInfo.name
        elif parent is not None and "DirectScrolledFrame" == parent.type:
            elementInfo.element.reparentTo(parent.element.canvas)
        parentWidget = self.customWidgetHandler.getWidget(parent.type if parent is not None else "")
        if parentWidget is not None:
            self.__handleWidgetAddItemFunc(elementInfo, parent, parentWidget)

        self.__setProperties(elementInfo, jsonElementInfo)
        if elementInfo.type == "DirectScrolledFrame":
            elementInfo.element.setScrollBarWidth()
        self.elementDict[elementInfo.element.guiId] = elementInfo
        self.parentMap[jsonElementName] = elementInfo.element.guiId

    def __createElementInfo(self, jsonElementInfo, funcName, parent):
        widget = self.customWidgetHandler.getWidget(jsonElementInfo["type"])
        if funcName == "createDirectEntryScroll":
            elementInfo = getattr(self.elementHandler, funcName)(parent.element if parent is not None else None, False)
        elif widget is not None:
            # Custom widget add
            elementInfo = getattr(self.elementHandler, funcName)(widget, parent.element if parent is not None else None)
        else:
            elementInfo = getattr(self.elementHandler, funcName)(parent.element if parent is not None else None)

    def __handleWidgetAddItemFunc(self, elementInfo, parent, parentWidget):
        if isinstance(parentWidget.addItemExtraArgs, dict):  # get the extra args from the .gui file
            for index, (value, parentArg) in enumerate(zip(elementInfo.addItemExtraArgs, parentWidget.addItemExtraArgs.values())):
                valueType = parentArg["type"]
                if valueType != "element":
                    continue
                # replace the element name for the element itself
                for elInfo in self.elementDict.values():
                    if elInfo.name != value:
                        continue
                    elementInfo.addItemExtraArgs[index] = elInfo.element
                    break
                else:
                    # if the element was not found
                    self.doMethodLater(0.2, self.__handleWidgetAddItemFunc, "__handleWidgetAddItem", [elementInfo, parent, parentWidget])
                    return
        # call custom widget add function
        parentWidget.callAddItemFunc(parent, elementInfo)

    def __setProperties(self, elementInfo, jsonElementInfo):
        """Set properties of element in 'elementInfo' to values specified in 'jsonElementInfo'."""
        tempOptionDict = {}
        for name, value in jsonElementInfo["element"].items():
            if name == "others":
                self.radiobuttonOthersDict[elementInfo] = value
                continue
            if name in self.prioList:
                tempOptionDict[name] = value
            else:
                self.__setProperty(elementInfo, name, value)

        for name, value in tempOptionDict.items():
            self.__setProperty(elementInfo, name, value)

        if "frameSize" not in tempOptionDict.keys():
            elementInfo.element.resetFrameSize()

    def __setProperty(self, elementInfo, name, value):
        """Set a specific property of the element in 'elementInfo'."""
        if elementInfo.type not in self.allWidgetDefinitions:
            logging.error("Couldn't load property {}. No Definition available.".format(name))
            return

        element = elementInfo.element
        subElementInfo = None
        optionName = name
        if "_" in name:
            parts = name.split("_")
            componentName = "_".join(parts[:-1])
            optionName = parts[-1]

            if elementInfo.element.hascomponent(componentName):
                element = elementInfo.element.component(componentName)

                subElementInfo = ElementInfo(
                    element,
                    type(element).__name__,
                    elementInfo.name,
                    elementInfo.parent,
                    elementInfo.extraOptions,
                    elementInfo.createAfter,
                    elementInfo.customImportPath,
                    elementInfo.addItemExtraArgs,
                    elementInfo.addItemNode
                )

        ei = subElementInfo if subElementInfo is not None else elementInfo
        wdList = self.allWidgetDefinitions[ei.type]

        try:
            widgetDef = next(filter(
                lambda wd: wd.internalName == optionName,
                wdList))
        except:
            logging.exception("Widget definition for {} not found! Unable to set value.".format(wd.internalName))
            return

        if isinstance(value, str):
            PropertyHelper.setValue(widgetDef, ei, eval(value), value)
        else:
            PropertyHelper.setValue(widgetDef, ei, eval(value))

        if subElementInfo is None \
        or len(subElementInfo.valueHasChanged.keys()) <= 0:
            # no sub elements to update
            return

        # update the changed dictionary
        key = next(iter(subElementInfo.valueHasChanged))
        changed = subElementInfo.valueHasChanged[key]
        elementInfo.valueHasChanged[name] = changed
