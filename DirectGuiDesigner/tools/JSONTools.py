#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "Fireclaw the Fox"
__license__ = """
Simplified BSD (BSD 2-Clause) License.
See License.txt or http://opensource.org/licenses/BSD-2-Clause for more info
"""

import logging

from direct.gui import DirectGuiGlobals as DGG
from panda3d.core import NodePath
from DirectGuiDesigner.core.PropertyHelper import PropertyHelper
from DirectGuiDesigner.core.ElementInfo import ElementInfo
from DirectGuiDesigner.core.WidgetDefinition import PropertyEditTypes

class JSONTools:
    functionMapping = {
        "base":{"initialText":"get"},
        }

    subOptionMapping = {
        "image":{"scale":"scale", "pos":"pos"}}

    specialPropMapping = {
        "align":{
            "0":"TextNode.A_left",
            "1":"TextNode.A_right",
            "2":"TextNode.A_center",
            "3":"TextNode.A_boxed_left",
            "4":"TextNode.A_boxed_right",
            "5":"TextNode.A_boxed_center"
        }
    }

    ignoreMapping = {
        "DirectCheckButton":["indicator_text"],
        "DirectRadioButton":["indicator_text"],
    }
    ignoreFunction = ["state", "width"]
    ignoreOptions = ["guiId", "enableEdit"]
    ignoreOptionsWithSub = ["item_", "item0_"]
    keepExactIgnoreOptionsWithSub = ["item_text"]
    ignoreRepr = ["command"]

    explIncludeOptions = ["forceHeight", "numItemsVisible", "pos", "hpr", "scrollBarWidth", "initialText"]

    def getProjectJSON(
            self,
            guiElementsDict,
            getEditorFrame,
            getEditorRootCanvas,
            getAllEditorPlacers,
            allWidgetDefinitions,
            usePixel2D):
        self.guiElementsDict = guiElementsDict
        self.allWidgetDefinitions = allWidgetDefinitions
        self.getEditorFrame = getEditorFrame
        jsonElements = {}
        jsonElements["ProjectVersion"] = "0.2a"
        jsonElements["EditorConfig"] = {}
        jsonElements["EditorConfig"]["usePixel2D"] = usePixel2D
        jsonElements["EditorConfig"]["canvasSize"] = repr(getEditorFrame()["canvasSize"])
        jsonElements["ComponentList"] = {}

        self.writtenRoots = []

        self.getEditorRootCanvas = getEditorRootCanvas
        self.getAllEditorPlacers = getAllEditorPlacers

        roots = [None] + getAllEditorPlacers()

        for root in roots:
            self.__writeSortedContent(root, jsonElements)
            for name, elementInfo in self.guiElementsDict.items():
                if elementInfo.parent not in self.writtenRoots:
                    self.__writeSortedContent(elementInfo.parent, jsonElements)

        return jsonElements

    def __writeSortedContent(self, root, jsonElements):
        """To have everything in the right order, we're going to go through all
        elements here and add them from top to bottom, first the parents, then
        respectively their children."""
        for name, elementInfo in self.guiElementsDict.items():
            if elementInfo.parent == root:
                if root not in self.writtenRoots: self.writtenRoots.append(root)
                try:
                    jsonElements["ComponentList"][elementInfo.name] = self.__createJSONEntry(elementInfo)
                except Exception as e:
                    logging.exception("error while writing {}:".format(elementInfo.name))
                    base.messenger.send("showWarning", ["error while writing {}:".format(elementInfo.name)])
                self.__writeSortedContent(elementInfo, jsonElements)

    def __createJSONEntry(self, elementInfo):
        from DirectGuiDesigner.DirectGuiDesigner import DirectGuiDesigner
        addItemExtraArgs = []
        for arg in elementInfo.addItemExtraArgs:
            if isinstance(arg, NodePath):
                name = DirectGuiDesigner.elementDict[arg.guiId].name
                addItemExtraArgs.append(name)
            else:
                addItemExtraArgs.append(arg)

        return {
            "element": self.__writeElement(elementInfo),
            "type": elementInfo.type,
            "parent": self.__writeParent(elementInfo.parent),
            "command": elementInfo.command,
            "extraArgs": elementInfo.extraArgs,
            "extraOptions": elementInfo.extraOptions,
            "addItemExtraArgs": addItemExtraArgs,
            "addItemNode": elementInfo.addItemNode
        }

    def __writeParent(self, parent):
        if parent is None or parent == self.getEditorRootCanvas():
            return "root"
        canvasParents = self.getAllEditorPlacers()
        if type(parent) == type(NodePath()):
            if parent in canvasParents:
                return parent.getName().replace("canvas", "a2d")
            else:
                return parent.getName()
        if parent.element.guiId in self.guiElementsDict.keys():
            return self.guiElementsDict[parent.element.guiId].name
        return parent.element.guiId

    def __getAllSubcomponents(self, componentName, component, componentPath):
        if componentPath == "":
            componentPath = componentName
        else:
            componentPath += "_" + componentName

        self.componentsList[component] = componentPath
        if not hasattr(component, "components"): return
        for subcomponentName in component.components():
            self.__getAllSubcomponents(subcomponentName, component.component(subcomponentName), componentPath)

    def __writeElement(self, elementInfo):
        element = elementInfo.element
        elementJson = {}

        self.componentsList = {element:""}
        # Check if the component has any sub-components assigned, e.g.
        # component0_subcomp0_subsubcomp0
        # we want    ^   and  ^
        for subcomponentName in element.components():
            self.__getAllSubcomponents(subcomponentName, element.component(subcomponentName), "")

        self.hasError = False

        for element, name in self.componentsList.items():
            if elementInfo.type in self.ignoreMapping \
            and name in self.ignoreMapping[elementInfo.type]:
                continue
            if name in self.ignoreRepr:
                reprFunc = lambda x: x
            else:
                reprFunc = repr
            if name != "":
                name += "_"

            for functionMapKey in self.functionMapping.keys():
                if functionMapKey not in name:
                    continue
                self.__fillFunctionMappings(
                    name,
                    reprFunc,
                    functionMapKey,
                    elementInfo,
                    elementJson)

            for subOptionKey in self.subOptionMapping.keys():
                if subOptionKey not in name:
                    continue
                self.__fillSubOptionMappings(
                    name,
                    reprFunc,
                    subOptionKey,
                    elementInfo,
                    elementJson)

            if type(element).__name__ in self.allWidgetDefinitions:
                wdList = self.allWidgetDefinitions[type(element).__name__]
                for wd in wdList:
                    if wd.internalName == "" \
                    or wd.editType == PropertyEditTypes.command:
                        continue
                    subElementInfo = ElementInfo(
                        element,
                        elementInfo.type,
                        elementInfo.name,
                        elementInfo.parent,
                        elementInfo.extraOptions,
                        elementInfo.createAfter,
                        elementInfo.customImportPath)

                    sub_element_value = PropertyHelper.getValues(wd, subElementInfo)

                    if self.__hasWidgetValueChanged(element, elementInfo, wd, name, sub_element_value):
                        if isinstance(sub_element_value, str) \
                        and wd.loaderFunc == "eval(value)":
                            new_value = sub_element_value
                        else:
                            new_value = reprFunc(sub_element_value)
                        elementJson[name + wd.internalName] = new_value

            if hasattr(element, "options"):
                self.__writeOptions(
                    elementInfo,
                    element,
                    name,
                    reprFunc,
                    elementJson)

            # special options for specific elements
            if elementInfo.type == "DirectRadioButton":
                elementNameDict = {}
                others = []
                for key, value in self.guiElementsDict.items():
                    elementNameDict[value.element] = value.name
                for otherElement in elementInfo.element["others"]:
                    if otherElement in elementNameDict:
                        others.append("{}".format(elementNameDict[otherElement]))
                elementJson["others"] = others

        # transparency attribute
        elementJson["transparency"] = reprFunc(elementInfo.element.getTransparency())

        if self.hasError:
            base.messenger.send("showWarning", ["Saved Project with errors! See log for more information"])
        return elementJson

    def __fillFunctionMappings(self, name, reprFunc, functionMapKey, elementInfo, elementJson):
        for option, value in self.functionMapping[functionMapKey].items():
            if name + option not in elementInfo.valueHasChanged \
            or not elementInfo.valueHasChanged[name + option]:
                # skip unchanged values
                continue

            if callable(getattr(element, value)):
                optionValue = reprFunc(getattr(element, value)())
            else:
                optionValue = reprFunc(getattr(element, value))

            if option in self.specialPropMapping.keys():
                optionValue = self.specialPropMapping[option][optionValue]
            elementJson[name + option] = optionValue

    def __fillSubOptionMappings(self, name, reprFunc, subOptionKey, elementInfo, elementJson):
        for option, value in self.subOptionMapping[subOptionKey].items():
            if name + option not in elementInfo.valueHasChanged \
            or not elementInfo.valueHasChanged[name + option]:
                # skip unchanged values
                continue
            optionValue = reprFunc(element[value])
            elementJson[name + option] = optionValue

    def __hasWidgetValueChanged(self, element, elementInfo, widgetDefinition, name, value):
        if widgetDefinition.internalName in self.explIncludeOptions:
            return True

        if hasattr(element, "options"):
            # we can check from the elements options
            for option in element.options():

                if option[DGG._OPT_DEFAULT] == widgetDefinition.internalName \
                and option[DGG._OPT_VALUE] == value:
                    return False

                fullComponentName = name + option[DGG._OPT_DEFAULT]
                notInValueHasChanged = (
                    fullComponentName not in elementInfo.valueHasChanged \
                    or not elementInfo.valueHasChanged[fullComponentName])

                if option[DGG._OPT_DEFAULT] == widgetDefinition.internalName \
                and notInValueHasChanged:
                    return False
        else:
            # we need to create a new element and compare that
            newWidget = type(element)()
            fullComponentName = name + widgetDefinition.internalName
            if fullComponentName in elementInfo.valueHasChanged \
            and elementInfo.valueHasChanged[fullComponentName]:
                return True

            try:
                if value == self.__getOriginalWidgetDefinitionValue(widgetDefinition, newWidget):
                    return False
            except Exception:
                # this may happen if something hasn't
                # been set in the vanilla widget. E.g.
                # the geom of an OnscreenGeom. So there
                # must have been changes in the widget
                pass
        return True

    def __writeOptions(self, elementInfo, element, name, reprFunc, elementJson):
        for option in element.options():
            optionFullName = name + option[DGG._OPT_DEFAULT]

            if option[DGG._OPT_DEFAULT] in self.ignoreOptions \
            or optionFullName not in elementInfo.valueHasChanged \
            or not elementInfo.valueHasChanged[optionFullName] \
            or (elementInfo.type in self.ignoreMapping \
            and optionFullName in self.ignoreMapping[elementInfo.type]) \
            or self.__shouldIgnoreOption(option):
                # skip unchanged and ignored values and options
                continue

            try:
                element_value = self.__getValueOfElement(element, option)

                if option[DGG._OPT_VALUE] != element[option[DGG._OPT_DEFAULT]] \
                and option[DGG._OPT_DEFAULT] in self.specialPropMapping:
                    element_value = self.specialPropMapping[option[DGG._OPT_DEFAULT]][reprFunc(element_value)]

                if not (isinstance(element_value, type) \
                and reprFunc(element_value).startswith("<class")):
                    elementJson[optionFullName] = reprFunc(element_value)
                else:
                    elementJson[optionFullName] = reprFunc(element_value)
            except Exception:
                logging.exception(f"Problem while writing option {optionFullName}")
                self.hasError = True
            except IgnoreException:
                continue

    def __getOriginalWidgetDefinitionValue(self, widgetDefinition, newWidget):
        if widgetDefinition.getFunctionName is not None \
        and type(widgetDefinition.getFunctionName) == str:
            origWidgetValue = getattr(
                newWidget,
                widgetDefinition.getFunctionName)()
        elif widgetDefinition.getFunctionName is not None:
            return widgetDefinition.getFunctionName()

        return getattr(
            newWidget,
            widgetDefinition.internalName)

    def __shouldIgnoreOption(self, option):
        for ignoreOption in self.ignoreOptionsWithSub:
            if option[DGG._OPT_DEFAULT] in self.keepExactIgnoreOptionsWithSub:
                return False
            if option[DGG._OPT_DEFAULT].startswith(ignoreOption):
                return True
        return False

    def __getValueOfElement(self, element, option):
        funcName = "get{}{}".format(option[DGG._OPT_DEFAULT][0].upper(), option[DGG._OPT_DEFAULT][1:])
        propName = "{}".format(option[DGG._OPT_DEFAULT])
        # Savety check. I currently only know of this function that isn't set by default
        if hasattr(element, funcName) \
        and not option[DGG._OPT_DEFAULT] in self.ignoreFunction:
            if funcName == "getColor" \
            and not element.hasColor():
                raise IgnoreException()
            return getattr(element, funcName)()
        elif hasattr(element, propName):
            if callable(getattr(element, propName)):
                return getattr(element, propName)()
            else:
                return getattr(element, propName)
        elif option[DGG._OPT_DEFAULT] in self.functionMapping["base"]:
            funcName = self.functionMapping["base"][option[DGG._OPT_DEFAULT]]
            if hasattr(element, funcName):
                return getattr(element, funcName)()
            else:
                logging.warning("Can't call: {}".format(option[DGG._OPT_DEFAULT]))
                raise Exception("Can't call function")

        try:
            return element[option[DGG._OPT_DEFAULT]]
        except Exception as e:
            logging.warning("Can't write: {}".format(option[DGG._OPT_DEFAULT]))
            raise

    class IgnoreException(Exception):
        pass
