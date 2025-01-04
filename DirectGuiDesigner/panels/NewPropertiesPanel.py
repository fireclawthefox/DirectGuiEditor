#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = "Fireclaw the Fox"
__license__ = """
Simplified BSD (BSD 2-Clause) License.
See License.txt or http://opensource.org/licenses/BSD-2-Clause for more info
"""

import logging
import sys
import copy

from panda3d.core import (
    VBase4,
    LVecBase4f,
    TextNode,
    Point3,
    TextProperties,
    TransparencyAttrib,
    PGButton,
    PGFrameStyle,
    MouseButton,
    NodePath,
    ConfigVariableString,
    Filename)
from direct.showbase.DirectObject import DirectObject

from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectLabel import DirectLabel
from direct.gui.DirectFrame import DirectFrame
from direct.gui.DirectScrolledFrame import DirectScrolledFrame
from direct.gui.DirectEntry import DirectEntry
from direct.gui.DirectButton import DirectButton
from DirectGuiDesigner.directGuiOverrides.DirectOptionMenu import DirectOptionMenu
from direct.gui.DirectCheckButton import DirectCheckButton

from DirectFolderBrowser.DirectFolderBrowser import DirectFolderBrowser

from DirectGuiExtension import DirectGuiHelper as DGH
from DirectGuiExtension.DirectBoxSizer import DirectBoxSizer
from DirectGuiExtension.DirectAutoSizer import DirectAutoSizer
from DirectGuiExtension.DirectCollapsibleFrame import DirectCollapsibleFrame

from DirectGuiDesigner.core import WidgetDefinition
from DirectGuiDesigner.core.PropertyHelper import PropertyHelper
from DirectGuiDesigner.panels.properties.Number import create
from dataclasses import dataclass

DGG.BELOW = "below"
MWUP = PGButton.getPressPrefix() + MouseButton.wheel_up().getName() + '-'
MWDOWN = PGButton.getPressPrefix() + MouseButton.wheel_down().getName() + '-'

SCROLLBARWIDTH = 20


@dataclass
class PropertiesPanelData:
    mainBoxFrame
    boxFrames
    definition2PropertyWidget
    widgetNameProp
    headers
    propertyHeaders
    sections




TODO: MAKE CREATE FUNCTIONS RETURN ONLY ONE WIDGET WHICH CAN BE ADDED TO THE GRID
TODO: MOVE ALL CREATE INTO DEDICATED WIDGET FILES



class PropertiesPanel(DirectObject):
    scrollSpeedUp = -0.001
    scrollSpeedDown = 0.001

    def __init__(self, parent, getEditorRootCanvas, getEditorPlacer, tooltip):
        height = DGH.getRealHeight(parent)
        self.parent = parent
        self.getEditorRootCanvas = getEditorRootCanvas
        self.getEditorPlacer = getEditorPlacer
        self.tooltip = tooltip
        self.customWidgetDefinitions = {}
        self.cachedPropertyFrames = {}
        self.frameCount = 0
        self.isRefreshing = False
        self.setupDone = False
        self.mainBoxFrame = None
        color = (
            (0.8, 0.8, 0.8, 1),  # Normal
            (0.9, 0.9, 1, 1),  # Click
            (0.8, 0.8, 1, 1),  # Hover
            (0.5, 0.5, 0.5, 1))  # Disabled

        # Sizer
        # |- Box
        #    |- Label
        #    |- Scrolled frame
        #       |- Box
        #          |- Properties...

        self.lblHeader = DirectLabel(
            text="Properties",
            text_scale=16,
            text_align=TextNode.ALeft,
            text_fg=(1, 1, 1, 1),
            frameColor=VBase4(0, 0, 0, 0),
            )

        self.propertiesFrame = DirectScrolledFrame(
            # make the frame fit into our background frame
            frameSize=VBase4(
                self.parent["frameSize"][0], self.parent["frameSize"][1],
                self.parent["frameSize"][2]+DGH.getRealHeight(self.lblHeader), self.parent["frameSize"][3]),
            # set the frames color to transparent
            frameColor=VBase4(1, 1, 1, 1),
            scrollBarWidth=SCROLLBARWIDTH,
            verticalScroll_scrollSize=20,
            verticalScroll_thumb_relief=DGG.FLAT,
            verticalScroll_incButton_relief=DGG.FLAT,
            verticalScroll_decButton_relief=DGG.FLAT,
            verticalScroll_thumb_frameColor=color,
            verticalScroll_incButton_frameColor=color,
            verticalScroll_decButton_frameColor=color,
            horizontalScroll_thumb_relief=DGG.FLAT,
            horizontalScroll_incButton_relief=DGG.FLAT,
            horizontalScroll_decButton_relief=DGG.FLAT,
            horizontalScroll_thumb_frameColor=color,
            horizontalScroll_incButton_frameColor=color,
            horizontalScroll_decButton_frameColor=color,
            state=DGG.NORMAL)

        self.box = DirectBoxSizer(
            frameColor=(0.25, 0.25, 0.25, 1),
            autoUpdateFrameSize=False,
            orientation=DGG.VERTICAL)

        self.sizer = DirectAutoSizer(
            suppressMouse=True,
            updateOnWindowResize=False,
            parent=parent,
            child=self.box,
            frameColor=(0,1,0,1))

        self.propertiesFrame.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        self.propertiesFrame.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])

        self.box.addItem(self.lblHeader, skipRefresh=True)
        self.box.addItem(self.propertiesFrame)

    def setCustomWidgetDefinitions(self,customWidgetDefinitions):
        self.customWidgetDefinitions = customWidgetDefinitions

    def scroll(self, scrollStep, event):
        """Scrolls the properties frame vertically with the given step.
        A negative step will scroll down while a positive step value will scroll
        the frame upwards"""
        if self.propertiesFrame.verticalScroll.isHidden():
            return
        self.propertiesFrame.verticalScroll.scrollStep(scrollStep)

    def getScrollBarWidth(self):
        if self.propertiesFrame.verticalScroll.isHidden():
            return 0
        return SCROLLBARWIDTH

    def resizeFrame(self):
        """Refreshes the sizer and recalculates the framesize to fit the parents
        frame size"""
        self.sizer.refresh()
        self.propertiesFrame["frameSize"] = (
                self.box["frameSize"][0], self.box["frameSize"][1],
                self.box["frameSize"][2]+DGH.getRealHeight(self.lblHeader), self.box["frameSize"][3])

        if self.setupDone:
            self.propertiesFrame["canvasSize"] = (
                self.propertiesFrame["frameSize"][0],
                self.propertiesFrame["frameSize"][1]-self.getScrollBarWidth(),
                self.mainBoxFrame.bounds[2],
                0)

            self.frameCount += 1
            if self.frameCount % 16 == 0:
                self.refreshProperties()
                self.frameCount = 0

    def setupProperties(self, headerText, elementInfo, elementDict):
        """Creates the set of editable properties for the given element"""
        self.elementInfo = elementInfo
        self.elementDict = elementDict

        if self.elementInfo in self.cachedPropertyFrames.keys():
            cacheProp = self.cachedPropertyFrames[self.elementInfo]
            self.panelData = self.cachedPropertyFrames[self.elementInfo]
            self.mainBoxFrame.show()
            self.updateCanvasSize()
        else:
            self.CreateProperties()
            self.cachedPropertyFrames[self.elementInfo] = self.panelData

    def CreateProperties(self):
        # create the frame that will hold all our properties
        self.panelData = PropertiesPanelData()
        self.panelData.mainBoxFrame = DirectBoxSizer(
            orientation=DGG.VERTICAL,
            frameColor=VBase4(0, 0, 0, 0),
            parent=self.propertiesFrame.getCanvas(),
            suppressMouse=True,
            state=DGG.NORMAL)
        self.panelData.mainBoxFrame.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        self.panelData.mainBoxFrame.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])

        # Create the header for the properties
        lbl = DirectLabel(
            text=headerText,
            text_scale=18,
            text_pos=(-10, 0),
            text_align=TextNode.ACenter,
            frameSize=VBase4(
                -self.propertiesFrame["frameSize"][1],
                self.propertiesFrame["frameSize"][1],
                -10,
                20),
            frameColor=VBase4(0.7, 0.7, 0.7, 1),
            state=DGG.NORMAL)
        lbl.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        lbl.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])

        self.panelData.mainBoxFrame.addItem(lbl)

        has_error = False
        error_count = 0
        # Set up all the properties
        try:

            allDefinitions = {**WidgetDefinition.DEFINITIONS, **self.customWidgetDefinitions}

            self.panelData.boxFrames = {}
            self.panelData.definition2PropertyWidget = {}
            self.panelData.widgetNameProp = None
            self.panelData.headers = []
            self.panelData.propertyHeaders = []
            self.panelData.sections = []

            # check if we have a definition for this specific GUI element
            if self.elementInfo.type in allDefinitions:
                # create the main set of properties to edit
                wd = allDefinitions[self.elementInfo.type]
                # create a header for this type of element
                self.panelData.headers.append(self.__createInbetweenHeader(self.elementInfo.type))

                section = self.createSection()
                self.panelData.mainBoxFrame.addItem(section)

                # Designer specific entries
                self.panelData.widgetNameProp = self.__createNameProperty(self.elementInfo)

                self.__createRootReParent(self.elementInfo)

                # create the set of properties to edit on the main component
                for definition in wd:
                    try:
                        self.panelData.definition2PropertyWidget[definition] = self.createProperty(definition, self.elementInfo)
                    except:
                        #e = sys.exc_info()[1]
                        has_error = True
                        error_count += 1
                        logging.exception("Failed to load property for properties panel")

                self.updateSection(section)

                # create the sub component set of properties to edit
                for componentName, componentDefinition in self.elementInfo.element._DirectGuiBase__componentInfo.items():
                    widget = componentDefinition[0]
                    wConfigure = componentDefinition[1]
                    wType = componentDefinition[2]
                    wGet = componentDefinition[3]
                    group = componentDefinition[4]

                    # store the sub widget as an element info object
                    subWidgetElementInfo = copy.copy(self.elementInfo)
                    subWidgetElementInfo.element = widget
                    subWidgetElementInfo.subComponentName = componentName

                    headerName = componentName
                    if group is not None:
                        widgetNPName = str(widget)
                        if len(widgetNPName) > 35:
                            widgetNPName = widgetNPName[-35:]
                            widgetNPName = "..." + widgetNPName
                        headerName = f"{wType} - [{widgetNPName}]"

                    # check if this component has definitions
                    if wType in allDefinitions:
                        # write the header for this component
                        self.panelData.headers.append(self.__createInbetweenHeader(headerName))
                        subsection = self.createSection()
                        self.panelData.mainBoxFrame.addItem(subsection)
                        subWd = allDefinitions[wType]
                        for definition in subWd:
                            # create the property for all definitions of this
                            # sub widget
                            try:
                                self.panelData.definition2PropertyWidget[definition] = self.createProperty(
                                    definition,
                                    subWidgetElementInfo)
                            except:
                                #e = sys.exc_info()[1]
                                has_error = True
                                error_count += 1
                                logging.exception("Failed to load property for properties panel")

                        self.updateSection(subsection)

            self.setupDone = True
        except Exception:
            e = sys.exc_info()[1]
            base.messenger.send("showWarning", [str(e)])
            logging.exception("Error while loading properties panel")

        if has_error:
            base.messenger.send("showWarning", [f"There were {error_count} Errors while loading the properties panel.\nSee log file for more details."])

        #
        # Reset property Frame framesize
        #
        self.updateCanvasSize()

    def refreshProperties(self):
        if self.isRefreshing:
            return
        self.isRefreshing = True

        has_error = False
        error_count = 0

        # Set up all the properties
        try:

            propertyHeader = self.panelData.mainBoxFrame["items"][0].element
            propertyHeader["frameSize"] = VBase4(
                -self.propertiesFrame["frameSize"][1],
                self.propertiesFrame["frameSize"][1],
                -10,
                20)

            for header in self.panelData.headers:
                header["frameSize"] = VBase4(self.propertiesFrame["canvasSize"][0], self.propertiesFrame["canvasSize"][1], -10, 20)

            for header in self.panelData.propertyHeaders:
                header["frameSize"] = VBase4(self.propertiesFrame["canvasSize"][0], self.propertiesFrame["canvasSize"][1], -10, 20)
                #header["text_pos"] = (self.propertiesFrame["frameSize"][0] + 5, 0)

            for section in self.panelData.sections:
                self.updateSection(section)

            allDefinitions = {**WidgetDefinition.DEFINITIONS, **self.customWidgetDefinitions}

            if self.panelData.widgetNameProp is not None:
                width = DGH.getRealWidth(self.propertiesFrame) - self.getScrollBarWidth()
                self.panelData.widgetNameProp["width"] = width/12

            # check if we have a definition for this specific GUI element
            if self.elementInfo.type in allDefinitions:
                # create the main set of properties to edit
                wd = allDefinitions[self.elementInfo.type]

                # create the set of properties to edit on the main component
                for definition in wd:
                    try:
                        if definition not in self.panelData.definition2PropertyWidget.keys():
                            continue
                        self.updateProperty(
                            definition,
                            self.elementInfo,
                            self.panelData.definition2PropertyWidget[definition])
                    except:
                        #e = sys.exc_info()[1]
                        has_error = True
                        error_count += 1
                        logging.exception("Failed to load property for properties panel")

                # create the sub component set of properties to edit
                for componentName, componentDefinition in self.elementInfo.element._DirectGuiBase__componentInfo.items():
                    widget = componentDefinition[0]
                    wConfigure = componentDefinition[1]
                    wType = componentDefinition[2]
                    wGet = componentDefinition[3]
                    group = componentDefinition[4]

                    # store the sub widget as an element info object
                    subWidgetElementInfo = copy.copy(self.elementInfo)
                    subWidgetElementInfo.element = widget
                    subWidgetElementInfo.subComponentName = componentName

                    # check if this component has definitions
                    if wType in allDefinitions:
                        subWd = allDefinitions[wType]
                        for definition in subWd:
                            # create the property for all definitions of this
                            # sub widget
                            try:
                                if definition not in self.panelData.definition2PropertyWidget.keys():
                                    continue
                                self.updateProperty(
                                    definition,
                                    subWidgetElementInfo,
                                    self.panelData.definition2PropertyWidget[definition])
                            except:
                                #e = sys.exc_info()[1]
                                has_error = True
                                error_count += 1
                                logging.exception("Failed to load property for properties panel")

        except Exception:
            e = sys.exc_info()[1]
            base.messenger.send("showWarning", [str(e)])
            logging.exception("Error while loading properties panel")

        if has_error:
            base.messenger.send("showWarning", [f"There were {error_count} Errors while loading the properties panel.\nSee log file for more details."])

        #
        # Reset property Frame framesize
        #
        self.updateCanvasSize()

        self.panelData.mainBoxFrame.refresh()
        self.isRefreshing = False

    def updateCanvasSize(self):
        self.propertiesFrame["canvasSize"] = (
            self.propertiesFrame["frameSize"][0],
            self.propertiesFrame["frameSize"][1]-self.getScrollBarWidth(),
            self.panelData.mainBoxFrame.bounds[2],
            0)
        self.propertiesFrame.setCanvasSize()

        self.panelData.mainBoxFrame.refresh()

        a = self.propertiesFrame["canvasSize"][2]
        b = abs(self.propertiesFrame["frameSize"][2]) + self.propertiesFrame["frameSize"][3]
        scrollDefault = 200
        s = -(scrollDefault / (a / b))

        self.propertiesFrame["verticalScroll_scrollSize"] = s
        self.propertiesFrame["verticalScroll_pageSize"] = s

    def createSection(self):
        section = DirectCollapsibleFrame(
            collapsed=True,
            frameColor=(1, 1, 1, 1),
            headerheight=24,
            frameSize=(
                self.propertiesFrame["frameSize"][0],
                self.propertiesFrame["frameSize"][1],
                0, 20))

        self.accept(section.getCollapsedEvent(), self.sectionCollapsed, extraArgs=[section])
        self.accept(section.getExtendedEvent(), self.sectionExtended, extraArgs=[section])

        section.toggleCollapseButton["text_scale"] = 12
        tp = section.toggleCollapseButton["text_pos"]
        section.toggleCollapseButton["text_pos"] = (tp[0] + 5, -12)

        section.toggleCollapseButton.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        section.toggleCollapseButton.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        section.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        section.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])

        self.boxFrame = DirectBoxSizer(
            pos=(0, 0, -section["headerheight"]),
            frameSize=(
                self.propertiesFrame["frameSize"][0],
                self.propertiesFrame["frameSize"][1]-self.getScrollBarWidth(),
                0, 0),
            orientation=DGG.VERTICAL,
            itemAlign=DirectBoxSizer.A_Left,
            frameColor=VBase4(0, 0, 0, 0),
            parent=section,
            suppressMouse=True,
            state=DGG.NORMAL)
        self.boxFrame.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        self.boxFrame.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])

        self.panelData.boxFrames[section] = self.boxFrame
        self.panelData.sections.append(section)

        return section

    def sectionExtended(self, section):
        self.updateCanvasSize()
        self.refreshProperties()

    def sectionCollapsed(self, section):
        self.updateCanvasSize()
        self.refreshProperties()

    def updateSection(self, section):
        self.panelData.boxFrames[section].refresh()
        fs = self.panelData.boxFrames[section]["frameSize"]
        section["frameSize"] = (fs[0], fs[1]-self.getScrollBarWidth(), fs[2]-section["headerheight"], fs[3])
        section.setCollapsed()
        section.updateFrameSize()

    def createProperty(self, definition, elementInfo):
        if definition.editType == WidgetDefinition.PropertyEditTypes.int:
            return self.__createNumberInput(definition, elementInfo, int)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.float:
            return self.__createNumberInput(definition, elementInfo, float)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.bool:
            return self.__createBoolProperty(definition, elementInfo)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.text:
            return self.__createTextProperty(definition, elementInfo)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.base2:
            return self.__createBaseNInput(definition, elementInfo, 2)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.base3:
            return self.__createBaseNInput(definition, elementInfo, 3)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.base4:
            return self.__createBaseNInput(definition, elementInfo, 4)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.command:
            return self.__createCustomCommand(definition, elementInfo)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.path:
            return self.__createPathProperty(definition, elementInfo)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.optionMenu:
            return self.__createOptionMenuProperty(definition, elementInfo)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.list:
            return self.__createListProperty(definition, elementInfo)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.tuple:
            return self.__createTupleProperty(definition, elementInfo)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.fitToChildren:
            return self.__createFitToChildren(definition, elementInfo)
        else:
            logging.error(f"Edit type {definition.editType} not in Edit type definitions")
            return None

    def updateProperty(self, definition, elementInfo, element):
        #TODO: Need to fix this
        if definition.internalName == "font": return
        if definition.editType == WidgetDefinition.PropertyEditTypes.int:
            valueA = PropertyHelper.getValues(definition, elementInfo)
            if valueA is None and not definition.nullable:
                logging.error(f"Got None value for not nullable element {definition.internalName}")
            if valueA is not None:
                valueA = PropertyHelper.getFormated(valueA, True)
            width = DGH.getRealWidth(self.propertiesFrame) - self.getScrollBarWidth()
            element["width"] = width/12
            element.enterText(str(valueA))
        elif definition.editType == WidgetDefinition.PropertyEditTypes.float:
            valueA = PropertyHelper.getValues(definition, elementInfo)
            if valueA is None and not definition.nullable:
                logging.error(f"Got None value for not nullable element {definition.internalName}")
            if valueA is not None:
                valueA = PropertyHelper.getFormated(valueA, False)
            width = DGH.getRealWidth(self.propertiesFrame) - self.getScrollBarWidth()
            element["width"] = width/12
            element.enterText(str(valueA))
        elif definition.editType == WidgetDefinition.PropertyEditTypes.bool:
            valueA = PropertyHelper.getValues(definition, elementInfo)
            element["indicatorValue"] = valueA
        elif definition.editType == WidgetDefinition.PropertyEditTypes.text:
            text = PropertyHelper.getValues(definition, elementInfo)
            width = DGH.getRealWidth(self.propertiesFrame) - self.getScrollBarWidth()
            element["width"] = width/12
            element.enterText(text)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.base2:
            n = 2
            values = PropertyHelper.getValues(definition, elementInfo)
            if type(values) is int or type(values) is float:
                values = [values] * n
            if definition.nullable:
                if values is None:
                    values = [""] * n
            width = DGH.getRealWidth(self.propertiesFrame) / n - self.getScrollBarWidth() / n
            for i in range(len(values)):
                value = PropertyHelper.getFormated(values[i])
                element[i]["width"] = width/12
                element[i].enterText(str(value))
        elif definition.editType == WidgetDefinition.PropertyEditTypes.base3:
            n = 3
            values = PropertyHelper.getValues(definition, elementInfo)
            if type(values) is int or type(values) is float:
                values = [values] * n
            if definition.nullable:
                if values is None:
                    values = [""] * n
            width = DGH.getRealWidth(self.propertiesFrame) / n - self.getScrollBarWidth() / n
            for i in range(len(values)):
                value = PropertyHelper.getFormated(values[i])
                element[i]["width"] = width/12
                element[i].enterText(str(value))
        elif definition.editType == WidgetDefinition.PropertyEditTypes.base4:
            n = 4
            values = PropertyHelper.getValues(definition, elementInfo)
            if type(values) is int or type(values) is float:
                values = [values] * n
            if definition.nullable:
                if values is None:
                    values = [""] * n
            width = DGH.getRealWidth(self.propertiesFrame) / n - self.getScrollBarWidth() / n
            for i in range(len(values)):
                value = PropertyHelper.getFormated(values[i])
                element[i]["width"] = width/12
                element[i].enterText(str(value))
        elif definition.editType == WidgetDefinition.PropertyEditTypes.command:
            pass #nothing to update here
        elif definition.editType == WidgetDefinition.PropertyEditTypes.path:
            path = PropertyHelper.getValues(definition, elementInfo)
            if type(path) is not str:
                path = ""
            width = DGH.getRealWidth(self.propertiesFrame) - self.getScrollBarWidth()
            element[0]["width"] = width/12
            element[1](path)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.optionMenu:
            pass # nothing to update here
        elif definition.editType == WidgetDefinition.PropertyEditTypes.list:
            pass # TODO: Maybe need update
            #self.__createListProperty(definition, elementInfo)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.tuple:
            pass # TODO: Maybe need update
            #self.__createTupleProperty(definition, elementInfo)
        elif definition.editType == WidgetDefinition.PropertyEditTypes.fitToChildren:
            pass #nothing to update here
        else:
            logging.error(f"Edit type {definition.editType} not in Edit type definitions")

    def clear(self):
        if not hasattr(self, "mainBoxFrame"): return
        if self.panelData.mainBoxFrame is not None:
            self.panelData.mainBoxFrame.hide()

    def __createInbetweenHeader(self, description):
        l = DirectLabel(
            text=description,
            text_scale=16,
            text_align=TextNode.ACenter,
            frameSize=VBase4(self.propertiesFrame["frameSize"][0], self.propertiesFrame["frameSize"][1], -10, 20),
            frameColor=VBase4(0.85, 0.85, 0.85, 1),
            state=DGG.NORMAL)
        l.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        l.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        return l

    def __createPropertyHeader(self, description):
        l = DirectLabel(
            text=description,
            text_scale=12,
            text_align=TextNode.ALeft,
            text_pos=(self.propertiesFrame["frameSize"][0] + 5, 0),
            frameSize=VBase4(self.propertiesFrame["frameSize"][0], self.propertiesFrame["frameSize"][1], -10, 20),
            frameColor=VBase4(0.85, 0.85, 0.85, 1),
            state=DGG.NORMAL)
        l.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        l.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        self.panelData.propertyHeaders.append(l)
        return l

    def __addToKillRing(self, elementInfo, definition, oldValue, newValue):
        base.messenger.send("addToKillRing",
            [elementInfo, "set", definition.internalName, oldValue, newValue])

    def __createTextEntry(self, text, width, command, commandArgs=[]):
        def focusOut():
            base.messenger.send("reregisterKeyboardEvents")
            command(*[entry.get()] + entry["extraArgs"])
        entry = DirectEntry(
            initialText=text,
            relief=DGG.SUNKEN,
            frameColor=(1,1,1,1),
            scale=12,
            width=width/12,
            overflow=True,
            command=command,
            extraArgs=commandArgs,
            focusInCommand=base.messenger.send,
            focusInExtraArgs=["unregisterKeyboardEvents"],
            focusOutCommand=focusOut)
        entry.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        entry.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        return entry

    #
    # General input elements
    #

    def __createNumberInput(self, definition, elementInfo, numberType):
        def update(text, elementInfo):
            base.messenger.send("setDirtyFlag")
            value = numberType(0)
            try:
                value = numberType(text)
            except Exception:
                if text == "" and definition.nullable:
                    value = None
                else:
                    logging.exception("ERROR: NAN", value)
                    value = numberType(0)
            try:
                oldValue = PropertyHelper.getValues(definition, elementInfo)
                self.__addToKillRing(elementInfo, definition, oldValue, value)
            except Exception:
                logging.exception(f"{definition.internalName} not supported by undo/redo yet")
            PropertyHelper.setValue(definition, elementInfo, value)
        self.__createPropertyHeader(definition.visibleName)
        valueA = PropertyHelper.getValues(definition, elementInfo)
        if valueA is None and not definition.nullable:
            logging.error(f"Got None value for not nullable element {definition.internalName}")
        if valueA is not None:
            valueA = PropertyHelper.getFormated(valueA, numberType is int)
        width = DGH.getRealWidth(self.boxFrame) - self.getScrollBarWidth()
        entry = self.__createTextEntry(str(valueA), width, update, [elementInfo])
        self.boxFrame.addItem(entry, skipRefresh=True)
        return entry

    def __createTextProperty(self, definition, elementInfo):
        def update(text, elementInfo):
            base.messenger.send("setDirtyFlag")
            try:
                oldValue = PropertyHelper.getValues(definition, elementInfo)
                self.__addToKillRing(elementInfo, definition, oldValue, text)
            except:
                logging.exception(f"{definition.internalName} not supported by undo/redo yet")

            PropertyHelper.setValue(definition, elementInfo, text)
        self.__createPropertyHeader(definition.visibleName)
        text = PropertyHelper.getValues(definition, elementInfo)
        width = DGH.getRealWidth(self.boxFrame) - self.getScrollBarWidth()
        entry = self.__createTextEntry(text, width, update, [elementInfo])
        self.boxFrame.addItem(entry, skipRefresh=True)
        return entry

    def __createBoolProperty(self, definition, elementInfo):
        def update(value):
            base.messenger.send("setDirtyFlag")
            try:
                oldValue = PropertyHelper.getValues(definition, elementInfo)
                self.__addToKillRing(elementInfo, definition, oldValue, value)
            except:
                logging.exception(f"{definition.internalName} not supported by undo/redo yet")
            PropertyHelper.setValue(definition, elementInfo, value)
        self.__createPropertyHeader(definition.visibleName)
        valueA = PropertyHelper.getValues(definition, elementInfo)
        btn = DirectCheckButton(
            indicatorValue=valueA,
            scale=24,
            frameSize=(-.5,.5,-.5,.5),
            text_align=TextNode.ALeft,
            command=update)
        btn.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        btn.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        self.boxFrame.addItem(btn, skipRefresh=True)
        return btn

    def __createListProperty(self, definition, elementInfo):
        def update(text, elementInfo, entries):
            base.messenger.send("setDirtyFlag")
            value = []

            for entry in entries:
                #if entry.get() != "":
                value.append(entry.get())

            try:
                oldValue = PropertyHelper.getValues(definition, elementInfo)
                self.__addToKillRing(elementInfo, definition, oldValue, value)
            except Exception:
                logging.exception(f"{definition.internalName} not supported by undo/redo yet")

            PropertyHelper.setValue(definition, elementInfo, value)

        def addEntry(text="", updateEntries=True, updateMainBox=True):
            entry = self.__createTextEntry(str(text), width, update, [elementInfo])
            entriesBox.addItem(entry, skipRefresh=True)
            entries.append(entry)

            if updateEntries:
                for entry in entries:
                    oldArgs = entry["extraArgs"]
                    if len(oldArgs) > 1:
                        oldArgs = oldArgs[:-1]
                    entry["extraArgs"] = oldArgs + [entries]

            if updateMainBox:
                entriesBox.refresh()
                for section, boxFrame in self.panelData.boxFrames.items():
                    boxFrame.refresh()
                    self.updateSection(section)

        self.__createPropertyHeader(definition.visibleName)
        listItems = PropertyHelper.getValues(definition, elementInfo)

        # make sure we have a list
        if listItems is None or isinstance(listItems, str):
            listItems = [listItems]

        width = DGH.getRealWidth(self.boxFrame) - self.getScrollBarWidth()
        entriesBox = DirectBoxSizer(
            orientation=DGG.VERTICAL,
            itemAlign=DirectBoxSizer.A_Left,
            frameColor=VBase4(0,0,0,0),
            suppressMouse=True,
            state=DGG.NORMAL)
        entriesBox.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        entriesBox.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        self.boxFrame.addItem(entriesBox, skipRefresh=True)
        entries = []
        for i in range(len(listItems)):
            text = listItems[i]
            addEntry(text, i == len(listItems)-1, i == len(listItems)-1)
        btn = DirectButton(
            text="Add entry",
            pad=(0.25,0.25),
            scale=12,
            command=addEntry
            )
        btn.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        btn.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        self.boxFrame.addItem(btn, skipRefresh=True)
        return (entriesBox, addEntry)

    def __createTupleProperty(self, definition, elementInfo):
        def update(text, elementInfo, entries):
            base.messenger.send("setDirtyFlag")
            value = []

            for entry in entries:
                if entry.get() != "":
                    value.append(entry.get())

            value = tuple(value)

            try:
                oldValue = PropertyHelper.getValues(definition, elementInfo)
                self.__addToKillRing(elementInfo, definition, oldValue, value)
            except Exception:
                logging.exception(f"{definition.internalName} not supported by undo/redo yet")

            PropertyHelper.setValue(definition, elementInfo, value)

        def addEntry(text="", updateEntries=True, updateMainBox=True):
            entry = self.__createTextEntry(text, width, update, [elementInfo])
            entriesBox.addItem(entry, skipRefresh=True)
            entries.append(entry)

            if updateEntries:
                for entry in entries:
                    oldArgs = entry["extraArgs"]
                    if len(oldArgs) > 1:
                        oldArgs = oldArgs[:-1]
                    entry["extraArgs"] = oldArgs + [entries]

            if updateMainBox:
                entriesBox.refresh()
                for section, boxFrame in self.panelData.boxFrames.items():
                    boxFrame.refresh()
                    self.updateSection(section)

        self.__createPropertyHeader(definition.visibleName)
        listItems = PropertyHelper.getValues(definition, elementInfo)
        width = DGH.getRealWidth(self.boxFrame) - self.getScrollBarWidth()
        entriesBox = DirectBoxSizer(
            orientation=DGG.VERTICAL,
            itemAlign=DirectBoxSizer.A_Left,
            frameColor=VBase4(0,0,0,0),
            suppressMouse=True,
            state=DGG.NORMAL)
        entriesBox.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        entriesBox.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        self.boxFrame.addItem(entriesBox, skipRefresh=True)
        entries = []
        for i in range(len(listItems)):
            text = listItems[i]
            addEntry(text, i==len(listItems)-1, i==len(listItems)-1)
        btn = DirectButton(
            text="Add entry",
            pad=(0.25,0.25),
            scale=12,
            command=addEntry
            )
        btn.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        btn.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        self.boxFrame.addItem(btn, skipRefresh=True)
        return (entriesBox, addEntry)

    def __createCustomCommandProperty(self, description, updateElement, updateAttribute, elementInfo):
        def update(text, elementInfo):
            base.messenger.send("setDirtyFlag")
            self.elementInfo.extraOptions[updateAttribute] = text

            for elementId, self.elementInfo in self.elementDict.items():
                if elementId in text:
                    text = text.replace(elementId, "elementDict['{}'].element".format(elementId))
                elif self.elementInfo.name in text:
                    text = text.replace(self.elementInfo.name, "elementDict['{}'].element".format(elementId))

            command = ""
            if text:
                try:
                    command = eval(text)
                except Exception:
                    logging.debug(f"command evaluation not supported: {text}")
                    logging.debug("set command without evalution")
                    command = text

            try:
                base.messenger.send("addToKillRing",
                    [updateElement, "set", updateAttribute, curCommand, text])
            except Exception:
                logging.debug(f"{updateAttribute} not supported by undo/redo yet")

            if updateAttribute in self.initOpDict:
                if hasattr(updateElement, self.initOpDict[updateAttribute]):
                    getattr(updateElement, self.initOpDict[updateAttribute])(command)
            elif updateAttribute in self.subControlInitOpDict:
                if hasattr(updateElement, self.subControlInitOpDict[updateAttribute][0]):
                    control = getattr(updateElement, self.subControlInitOpDict[updateAttribute][0])
                    if hasattr(control, self.subControlInitOpDict[updateAttribute][1]):
                        getattr(control, self.subControlInitOpDict[updateAttribute][1])(command)
            else:
                updateElement[updateAttribute] = (command)
        self.__createPropertyHeader(description)
        curCommand = ""
        if updateAttribute in elementInfo.extraOptions:
            curCommand = elementInfo.extraOptions[updateAttribute]
        width = (DGH.getRealWidth(parent) - 10) - self.getScrollBarWidth()
        entryWidth = width / 13
        entry = self.__createTextEntry(curCommand, entryWidth, update, [elementInfo])
        self.boxFrame.addItem(entry, skipRefresh=True)

    def __createPathProperty(self, definition, elementInfo):

        def update(text):
            value = text
            if text == "" and definition.nullable:
                value = None
            elif definition.loaderFunc is not None and text != "":
                try:
                    if type(definition.loaderFunc) is str:
                        value = eval(definition.loaderFunc)
                    else:
                        value = definition.loaderFunc(value)
                except Exception:
                    logging.exception("Couldn't load path with loader function")
                    value = text
            base.messenger.send("setDirtyFlag")
            try:
                PropertyHelper.setValue(definition, elementInfo, value, text)
            except Exception:
                base.messenger.send("showWarning", [f"couldn't load file '{text}'"])
                logging.exception("Couldn't load file: {}".format(text))
                elementInfo.element[definition.internalName] = None

        def setPath(path):
            update(path)

            # make sure to take the actual value to write it to the textbox in
            # case something hapened while updating the value
            v = PropertyHelper.getValues(definition, elementInfo)
            if v is None:
                v = ""
            entry.set(v)

        def selectPath(confirm):
            if confirm:
                value = Filename.fromOsSpecific(self.browser.get())
                setPath(str(value))
            self.browser.hide()

        def showBrowser():
            self.browser = DirectFolderBrowser(
                selectPath,
                True,
                ConfigVariableString("work-dir-path", "~").getValue(),
                "",
                tooltip=self.tooltip)
            self.browser.show()
        self.__createPropertyHeader(definition.visibleName)
        path = PropertyHelper.getValues(definition, elementInfo)
        if type(path) is not str:
            path = ""
        width = DGH.getRealWidth(self.boxFrame) - self.getScrollBarWidth()
        entry = self.__createTextEntry(path, width, update)
        self.boxFrame.addItem(entry, skipRefresh=True)

        btn = DirectButton(
            text="Browse",
            text_align=TextNode.ALeft,
            command=showBrowser,
            pad=(0.25,0.25),
            scale=12
            )
        btn.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        btn.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        self.boxFrame.addItem(btn, skipRefresh=True)
        return (entry, setPath)

    def __createOptionMenuProperty(self, definition, elementInfo):
        def update(selection):
            oldValue = PropertyHelper.getValues(definition, elementInfo)
            value = definition.valueOptions[selection]
            # Undo/Redo setup
            try:
                if oldValue != value:
                    self.__addToKillRing(elementInfo, definition, oldValue, value)
            except Exception as e:
                logging.exception(f"{definition.internalName} not supported by undo/redo yet")

            value_str = ""
            if definition.loaderFunc is not None:
                value_str = value
                try:
                    if type(definition.loaderFunc) is str:
                        value = eval(definition.loaderFunc)
                    else:
                        value = definition.loaderFunc(value)
                except Exception:
                    logging.exception("Couldn't load path with loader function")
                    value = value_str
            # actually set the value on the element
            PropertyHelper.setValue(definition, elementInfo, value, value_str)

        self.__createPropertyHeader(definition.visibleName)
        if definition.valueOptions is None:
            return
        value = PropertyHelper.getValues(definition, elementInfo)
        selectedElement = list(definition.valueOptions.keys())[0]
        for k, v in definition.valueOptions.items():
            if v == value:
                selectedElement = k
                break
        menu = DirectOptionMenu(
            items=list(definition.valueOptions.keys()),
            scale=12,
            popupMenuLocation=DGG.BELOW,
            initialitem=selectedElement,
            command=update)
        menu.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        menu.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        self.boxFrame.addItem(menu, skipRefresh=True)
        return menu

    def __createCustomCommand(self, definition, elementInfo):
        self.__createPropertyHeader(definition.visibleName)
        btn = DirectButton(
            text="Run Command",
            pad=(0.25,0.25),
            scale=12,
            command=getattr(elementInfo.element, definition.valueOptions)
            )
        btn.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        btn.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        self.boxFrame.addItem(btn, skipRefresh=True)
        return btn

    def __createFitToChildren(self, definition, elementInfo):
        self.__createPropertyHeader("Fit to children")
        #
        # Fit frame to children
        #
        l, r, b, t = [None,None,None,None]

        def getMaxSize(rootElement, baseElementInfo, l, r, b, t):
            if not hasattr(rootElement, "getChildren"):
                return [l,r,b,t]
            if len(rootElement.getChildren()) <= 0:
                return [l,r,b,t]
            for child in rootElement.getChildren():
                childElementInfo = None
                if child.getName() in self.elementDict.keys():
                    childElementInfo = self.elementDict[child.getName()]
                elif len(child.getName().split("-")) > 1 and child.getName().split("-")[1] in self.elementDict.keys():
                    childElementInfo = self.elementDict[child.getName().split("-")[1]]

                if childElementInfo is None: continue

                element = childElementInfo.element
                el = DGH.getRealLeft(element) + element.getX(baseElementInfo.element)
                er = DGH.getRealRight(element) + element.getX(baseElementInfo.element)
                eb = DGH.getRealBottom(element) + element.getZ(baseElementInfo.element)
                et = DGH.getRealTop(element) + element.getZ(baseElementInfo.element)

                if l is None:
                    l = el
                if r is None:
                    r = er
                if b is None:
                    b = eb
                if t is None:
                    t = DGH.getRealTop(element) + element.getZ()

                l = min(l, el)
                r = max(r, er)
                b = min(b, eb)
                t = max(t, et)

                l,r,b,t = getMaxSize(child, baseElementInfo, l, r, b, t)
            return [l, r, b, t]

        def fitToChildren(elementInfo, l, r, b, t):
            l, r, b, t = getMaxSize(elementInfo.element, elementInfo, l, r, b, t)
            if l is None or r is None or b is None or t is None:
                return
            elementInfo.element["frameSize"] = [l, r, b, t]

        btn = DirectButton(
            text="Fit to children",
            pad=(0.25,0.25),
            scale=12,
            command=fitToChildren,
            extraArgs=[elementInfo, l, r, b, t]
            )
        btn.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
        btn.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
        self.boxFrame.addItem(btn, skipRefresh=True)
        return btn

    #
    # Designer specific input fields
    #
    def __createNameProperty(self, elementInfo):
        def update(text):
            base.messenger.send("setDirtyFlag")
            name = elementInfo.element.guiId.replace("-", "")
            if text != "":
                name = text
            base.messenger.send("setName", [elementInfo, name])
        self.__createPropertyHeader("Name")
        text = elementInfo.name
        width = DGH.getRealWidth(self.boxFrame) - self.getScrollBarWidth()
        entry = self.__createTextEntry(text, width, update)
        self.boxFrame.addItem(entry, skipRefresh=True)
        return entry

    def __createRootReParent(self, elementInfo):
        def update(name):
            base.messenger.send("setDirtyFlag")
            parent = self.getEditorPlacer(name)
            elementInfo.element.reparentTo(parent)
            if name == "canvasRoot":
                elementInfo.parent = None
            else:
                elementInfo.parent = parent
            base.messenger.send("refreshStructureTree")

        self.__createPropertyHeader("Change Root parent")

        def createReparentButton(txt, arg):
            btn = DirectButton(
                text=txt,
                pad=(0.25,0.25),
                scale=12,
                command=update,
                extraArgs=[arg]
                )
            btn.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
            btn.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
            self.boxFrame.addItem(btn, skipRefresh=True)
        createReparentButton("Root", "canvasRoot")
        createReparentButton("Center Left", "canvasLeftCenter")
        createReparentButton("Center Right", "canvasRightCenter")
        createReparentButton("Top Left", "canvasTopLeft")
        createReparentButton("Top Right", "canvasTopRight")
        createReparentButton("Top Center", "canvasTopCenter")
        createReparentButton("Bottom Left", "canvasBottomLeft")
        createReparentButton("Bottom Right", "canvasBottomRight")
        createReparentButton("Bottom Center", "canvasBottomCenter")
