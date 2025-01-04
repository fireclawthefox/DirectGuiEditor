import tempfile

import sys
import os
import logging
import platform

from direct.showbase.DirectObject import DirectObject

from panda3d.core import (
    Filename,
    Point3,
    Vec3,
    loadPrcFileData,
    WindowProperties,
    ConfigVariableInt,
    ConfigVariableBool,
    ConfigVariableString,
    ConfigVariableSearchPath,
    TextNode,
    TextProperties,
    TextPropertiesManager
)

from direct.gui import DirectGuiGlobals as DGG

from direct.gui.DirectFrame import DirectFrame
#from direct.gui.DirectScrolledFrame import DirectScrolledFrame
import direct.gui.DirectGui as DirectGui
from DirectGuiDesigner.directGuiOverrides.DirectScrolledFrame import DirectScrolledFrame
from direct.gui.DirectDialog import OkDialog
from direct.gui.DirectDialog import OkCancelDialog

from direct.directtools.DirectUtil import ROUND_TO

from DirectGuiDesigner.export.ExporterPy import ExporterPy
from DirectGuiDesigner.export.ExporterProject import ExporterProject

from DirectGuiDesigner.loader.Project import ProjectLoader

from DirectGuiDesigner.dialogs.SettingsDialog import GUI as SettingsDialog

from DirectGuiDesigner.core.ElementHandler import ElementHandler
from DirectGuiDesigner.core.ElementInfo import ElementInfo
from DirectGuiDesigner.core.CustomWidgets import CustomWidgets
from DirectGuiDesigner.core.KillRing import KillRing

from DirectGuiDesigner.GUI.MainView import MainView

from DirectFolderBrowser.DirectFolderBrowser import DirectFolderBrowser

from DirectGuiExtension import DirectGuiHelper as DGH

from DirectGuiExtension.DirectTooltip import DirectTooltip

from DirectGuiDesigner.core import WidgetDefinition
from DirectGuiDesigner.core.PropertyHelper import PropertyHelper


class DirectGuiDesigner(DirectObject):
    # dict of all elements in the visual editor
    # Key = guiID; Value = elementInfo
    elementDict = {}

    def __init__(self, parent):
        logging.debug("Start Designer")

        DirectObject.__init__(self)

        fn = Filename.fromOsSpecific(os.path.dirname(__file__))
        fn.makeTrueCase()
        self.icon_dir = str(fn) + "/"
        loadPrcFileData("", f"model-path {self.icon_dir}")

        self.parent = parent

        self.log_file = ""
        self.config_file = ""

        self.dirty = False
        self.hasSaved = False
        self.killRing = KillRing()

        self.lastDirPath = ConfigVariableString("work-dir-path", "~").getValue()
        self.lastFileNameWOExtension = "export"

        wp = WindowProperties()
        if platform.system() == "Windows":
            wp.setIconFilename("icons/DirectGuiDesigner.ico")
        else:
            wp.setIconFilename("icons/DirectGuiDesigner64.png")
        base.win.requestProperties(wp)

        self.selectedElement = None

        map = base.win.get_keyboard_map()

        self.is_down = base.mouseWatcherNode.is_button_down
        self.key_lcontrol = map.get_mapped_button("lcontrol")
        self.key_rcontrol = map.get_mapped_button("rcontrol")
        self.key_lshift = map.get_mapped_button("lshift")
        self.key_rshift = map.get_mapped_button("rshift")

        self.dlgHelp = None
        self.dlgHelpShadow = None

        self.dlgSettings = None
        self.dlgSettingsShadow = None

        self.dlgQuit = None
        self.dlgQuitShadow = None

        self.dlgWarning = None
        self.dlgWarningShadow = None

        self.dlgInfo = None
        self.dlgInfoShadow = None

        self.dlgNewProject = None
        self.dlgNewProjectShadow = None

        self.openDialogCloseFunctions = []

        self.copyOptionsElementInfo = None

        self.copiedElement = None

        self.theCutElement = None

        self.screenSize = base.getSize()

        # Delay initial setup by 0.5s to let the window set it's final
        # size and we'll be able to use the screen corner/edge variables
        self.setup_gui()

        self.enable_events()

        # editor close and crash handling
        sys.excepthook = self.excHandler
        base.win.setCloseRequestEvent("quitApp")

        # Load user custom widgets
        self.customWidgetsHandler.loadCustomWidgets()

        # Exception save-file-handling
        tmpPath = os.path.join(tempfile.gettempdir(), "DGDExceptionSave.gui")
        if os.path.exists(tmpPath):
            logging.info("Loading crash session file {}".format(tmpPath))
            allWidgetDefinitions = {
                **WidgetDefinition.DEFINITIONS,
                **self.customWidgetsHandler.getCustomWidgetDefinitions()}
            projectLoader = ProjectLoader(
                tmpPath,
                self.visualEditorInfo,
                self.elementHandler,
                self.customWidgetsHandler,
                self.mainView.getEditorPlacer,
                allWidgetDefinitions,
                True)
            self.elementDict = projectLoader.get()
            base.messenger.send("refreshStructureTree")
            base.messenger.send("setDirtyFlag")
            base.messenger.send("showInfo", ["Loaded previously crashed session!"])
            os.remove(tmpPath)
            logging.info("Removed crash session file")
        logging.debug("Startup complete")

        # refresh the editor area.
        self.mainView.editorFrame.setVisualEditorParent(False)

        taskMgr.doMethodLater(ConfigVariableInt("autosave-delay", 60).getValue(), self.autosaveTask, 'autosave task')

    def enable_editor(self):
        self.enable_events()

        self.mainView.mainSizer.refresh()

    def disable_editor(self):
        self.disable_events()

    def setup_gui(self):
        self.tt = DirectTooltip(
            text = "Tooltip",
            #text_fg = (1,1,1,1),
            pad=(0.2, 0.2),
            scale = 16,
            text_align = TextNode.ALeft,
            frameColor = (1, 1, 0.7, 1),
            parent=base.pixel2d,
            sortOrder=1000)

        self.mainView = MainView(self, self.tt, self.parent)

        self.visualEditorInfo = ElementInfo(self.mainView.editorFrame.visualEditor, "Editor")
        self.propertiesEditor(self.visualEditorInfo)

        #
        # ELEMENT HANDLERS
        #
        self.elementHandler = ElementHandler(self.mainView.propertiesFrame, self.mainView.getEditorRootCanvas)
        self.customWidgetsHandler = CustomWidgets(self.mainView.toolboxFrame, self.elementHandler)
        self.mainView.propertiesFrame.setCustomWidgetDefinitions(self.customWidgetsHandler.getCustomWidgetDefinitions())

        # connect the handler with the editor frame
        self.mainView.editorFrame.setElementHandler(self.elementHandler)

    def enable_events(self):
        """Setup general events for the editor. Both some user inputs (like selecting an object with 'mouse3')
        and some events for internal functions (for example 'refreshStructureTree' which will update the
        structure panel to reflect the current state of the current project).
        """
        self.registerKeyboardEvents()

        # these keys will not be ignored until the application is closed
        self.accept("escape", self.inteligentEscape)
        self.accept("mouse3", self.selectElement, extraArgs=[self.visualEditorInfo, None])
        self.accept("mouse2", self.mainView.editorFrame.dragEditorFrame, extraArgs=[True])
        self.accept("mouse2-up", self.mainView.editorFrame.dragEditorFrame, extraArgs=[False])
        self.accept("wheel_up", self.mainView.editorFrame.zoom, extraArgs=[.1])
        self.accept("wheel_down", self.mainView.editorFrame.zoom, extraArgs=[-.1])

        # here we have custom events that do not represent a keyboard action
        self.accept("unregisterKeyboardEvents", self.ignoreKeyboardEvents)
        self.accept("reregisterKeyboardEvents", self.registerKeyboardEvents)

        self.accept("quitApp", self.quitApp)

        # TASK AND MENU BAR FEATURES
        self.accept("newProject", self.new)
        self.accept("saveProject", self.save)
        self.accept("exportProject", self.export)
        self.accept("loadProject", self.load)
        self.accept("DirectGuiDesigner_toggleGrid", self.mainView.editorFrame.toggleGrid)
        self.accept("toggleVisualEditorParent", self.mainView.editorFrame.toggleVisualEditorParent)
        self.accept("setVisualEditorParent", self.mainView.editorFrame.setVisualEditorParent)
        self.accept("setVisualEditorCanvasSize", self.mainView.editorFrame.setVisualEditorCanvasSize)

        # DATA
        self.accept("updateElementDict-afterLoad", self.updateElementDict)

        # REFRESH PANELS
        self.accept("refreshStructureTree", self.__refreshStructureTree)
        self.accept("refreshProperties", self.refreshProperties)

        # Element handling
        self.accept("createControl", self.__createControl)
        self.accept("selectElement", self.selectElement)
        self.accept("removeElement", self.removeElement)
        self.accept("copyOptions", self.copyOptions)
        self.accept("pasteOptions", self.pasteOptions)
        self.accept("cutElement", self.cutElement)
        self.accept("copyElement", self.copyElement)
        self.accept("pasteElement", self.pasteElement)
        self.accept("moveElementInStructure", self.moveElementInStructure)
        self.accept("setName", self.setName)

        # DRAG AND DROP
        self.accept("dragStart", self.dragStart)
        self.accept("dragStop", self.dragStop)

        # UNDO/REDO
        self.accept("undo", self.undo)
        self.accept("redo", self.redo)
        self.accept("cycleRedo", self.cycleKillRing)
        self.accept("toggleElementVisibility", self.toggleElementVisibility)
        self.accept("setParentOfElement", self.setParentOfElement)
        self.accept("addToKillRing", self.addToKillRing)

        # HELP DIALOG
        self.accept("showHelp", self.showHelp)

        # SETTINGS
        self.accept("showSettings", self.showSettings)
        self.accept("Settings_OK", self.hideSettings, [True])
        self.accept("Settings_CANCEL", self.hideSettings, [False])

        # ZOOM
        self.accept("setEditorZoom", self.mainView.editorFrame.setZoom)
        self.accept("resetZoom", self.mainView.editorFrame.resetZoom)
        self.accept("setZoomValeMinMax", self.mainView.toolBar.setZoomMinMax)
        self.accept("setZoomValue", self.mainView.toolBar.setZoomValue)
        self.accept("zoom-in", self.mainView.editorFrame.zoom, extraArgs=[.1])
        self.accept("zoom-out", self.mainView.editorFrame.zoom, extraArgs=[-.1])
        self.accept("zoom-reset", self.mainView.editorFrame.resetZoom)

        # SAVE INDICATOR
        self.accept("setDirtyFlag", self.setDirty)
        self.accept("clearDirtyFlag", self.setClean)

        # SAVING/LOADING
        self.accept("setLastPath", self.setLastPath)

        # FEEDBACK
        self.accept("showWarning", self.showWarning)
        self.accept("showInfo", self.showInfo)

        # WINDOW HANDLING
        self.accept("window-event", self.windowEventHandler)

    def disable_events(self):
        """Ignore all events that has been accepted previously."""
        self.ignore_all()

    def is_dirty(self):
        """Return True if the current project has unsaved changes, else returns False."""
        return self.dirty

    def setDirty(self):
        """Set dirty tag of self to True and add '*' to the window title."""
        base.messenger.send("request_dirty_name")
        self.dirty = True

    def setClean(self):
        """Set dirty tag of self to False and remove '*' from the window title."""
        base.messenger.send("request_clean_name")
        self.dirty = False
        self.hasSaved = True

    def addToKillRing(self, editObject, action, objectType, oldValue, newValue):
        """Adds a change to the 'KillRing' to be able to undo and redo changes at a later time.

        :param editObject: The object that was changed (can be an element, ElementInfo or something else)
        :param str action: What kind of change it was, for example 'add' when an element was added
        :param str objectType: Can specify the type of the editObject or the type of sub-action to use
        :param oldValue: The old value
        :param newValue: The new value
        """
        if action == "set" and oldValue == newValue:
            logging.debug(f"action={action}, type={objectType} was not added to killring, reason: old={oldValue} equals new={newValue}")
            return
        logging.debug(f"Add to killring action={action}, type={objectType}, old={oldValue}, new={newValue}")
        self.killRing.push(editObject, action, objectType, oldValue, newValue)

    def undo(self):
        """Undo the latest change in the current branch of the 'KillRing'.
        If the user hasn't just cycled between redo branches this will be the latest change.
        """
        # undo this action
        workOn = self.killRing.pop()

        if workOn is None: return

        if workOn.action == "set":
            if workOn.objectType == "pos":
                logging.debug(f"undo Position to {workOn.oldValue}")
                workOn.editObject.element.setPos(workOn.oldValue)
            elif workOn.objectType == "pressEffect":
                logging.debug(f"try undo press effect to {workOn.oldValue}")
                workOn.editObject.extraOptions["pressEffect"] = workOn.oldValue
            elif workOn.objectType == "transparency":
                workOn.editObject.element.setTransparency(workOn.oldValue)
            else:
                try:
                    logging.debug(f"try undo {workOn.objectType} to {workOn.oldValue}")
                    workOn.editObject.element[workOn.objectType] = workOn.oldValue
                except:
                    logging.exception(f"property {workOn.objectType} currently not supported by undo/redo")

        elif workOn.action == "add" and workOn.objectType == "element":
            logging.debug(f"undo remove added element {workOn.editObject}")
            self.removeElement(workOn.editObject, False)

        elif workOn.action == "kill" and workOn.objectType == "element":
            logging.debug(f"undo last kill {workOn.editObject}")
            workOn.editObject.unstash()
            self.elementDict[workOn.oldValue[0]] = workOn.oldValue[1]
            base.messenger.send("refreshStructureTree")

        elif workOn.action == "copy":
            logging.debug(f"undo last copy {workOn.objectType}")
            if workOn.objectType == "element":
                self.removeElement(workOn.editObject.element, False)
            elif workOn.objectType == "properties":
                for key, value in workOn.oldValue.items():
                    if key == "pos":
                        workOn.editObject.element.setPos(value)
                    elif key == "hpr":
                        workOn.editObject.element.setHpr(value)
                    elif key == "scale":
                        workOn.editObject.element.setScale(value)
                    elif key == "text_fg":
                        workOn.editObject.element["text_fg"] = value
                    else:
                        workOn.editObject.element[key] = value[1]

        elif workOn.action == "cut":
            if workOn.objectType == "element":
                workOn.editObject.element.reparentTo(workOn.oldValue)
                self.setParentOfElement(workOn.editObject.element, workOn.oldValue)

        if self.selectedElement is not None:
            self.refreshProperties(self.selectedElement)
        base.messenger.send("setDirtyFlag")

    def redo(self):
        """Redo the latest change in the current branch of the 'KillRing'.
        If the user hasn't just cycled between redo branches this will be the latest change.
        """
        # redo this
        workOn = self.killRing.pull()

        if workOn is None:
            logging.debug("nothing to redo")
            return

        if workOn.action == "set":
            if workOn.objectType == "pos":
                if type(workOn.newValue) is list:
                    workOn.editObject.element.setPos(*workOn.newValue)
                else:
                    workOn.editObject.element.setPos(workOn.newValue)
            elif workOn.objectType == "pressEffect":
                workOn.editObject.extraOptions["pressEffect"] = workOn.newValue
            else:
                try:
                    workOn.editObject.element[workOn.objectType] = workOn.newValue
                except:
                    logging.exception(f"property {workOn.objectType} currently not supported by undo/redo")

        elif workOn.action == "add" and workOn.objectType == "element":
            workOn.editObject.unstash()
            self.elementDict[workOn.oldValue[0]] = workOn.oldValue[1]
            base.messenger.send("refreshStructureTree")

        elif workOn.action == "kill" and workOn.objectType == "element":
            self.removeElement(workOn.editObject, False)

        elif workOn.action == "copy":
            if workOn.objectType == "element":
                workOn.editObject.unstash()
                self.elementDict[workOn.oldValue[0]] = workOn.oldValue[1]
                base.messenger.send("refreshStructureTree")
            elif workOn.objectType == "properties":
                for key, value in workOn.newValue.items():
                    if key == "pos":
                        workOn.editObject.element.setPos(value)
                    elif key == "hpr":
                        workOn.editObject.element.setHpr(value)
                    elif key == "scale":
                        workOn.editObject.element.setScale(value)
                    elif key == "text_fg":
                        workOn.editObject.element["text_fg"] = value
                    else:
                        workOn.editObject.element[key] = value[1]

        elif workOn.action == "cut":
            if workOn.objectType == "element":
                workOn.editObject.element.reparentTo(workOn.newValue)
                self.setParentOfElement(workOn.editObject.element, workOn.newValue)

        if self.selectedElement is not None:
            self.refreshProperties(self.selectedElement)
        base.messenger.send("setDirtyFlag")

    def cycleKillRing(self):
        """Cycles through the redo branches at the current depth of the kill ring"""
        self.undo()
        self.killRing.cycleChildren()
        self.redo()

    def setLastPath(self, path):
        self.lastDirPath = os.path.dirname(path)
        fn = os.path.splitext(os.path.basename(path))[0]
        if fn != "":
            self.lastFileNameWOExtension = os.path.splitext(os.path.basename(path))[0]

    def getAllEditorPlacers(self):
        """Get all default positions for elements on the canvas (for example topRight, leftCenter).

        :return list: list of nodePaths
        """
        return self.mainView.editorFrame.getAllEditorPlacers()

    def getEditorFrame(self):
        return self.mainView.editorFrame.visualEditor

    def getEditorRootCanvas(self):
        return self.mainView.getEditorRootCanvas()

    def do_exception_save(self):
        allWidgetDefinitions = {
            **WidgetDefinition.DEFINITIONS,
            **self.customWidgetsHandler.getCustomWidgetDefinitions()}
        ExporterProject(
            "",
            self.elementDict,
            self.getEditorFrame,
            self.getEditorRootCanvas,
            self.getAllEditorPlacers,
            allWidgetDefinitions,
            not self.mainView.editorFrame.visEditorInAspect2D,
            exceptionSave=True)

    def excHandler(self, ex_type, ex_value, ex_traceback):
        logging.error("Unhandled exception", exc_info=(ex_type, ex_value, ex_traceback))
        print("Try to save file after unhandled exception. Please restart the app to automatically load the exception save file!")
        self.do_exception_save()

    def autosaveTask(self, task):
        """Task to autosave the current project (by default every minute)."""
        task.delayTime = ConfigVariableInt("autosave-delay", 60).getValue()
        try:
            filename = ""
            if self.hasSaved:
                filename = os.path.join(self.lastDirPath, self.lastFileNameWOExtension + ".gui~")
            allWidgetDefinitions = {
                **WidgetDefinition.DEFINITIONS,
                **self.customWidgetsHandler.getCustomWidgetDefinitions()}
            ExporterProject(
                filename,
                self.elementDict,
                self.getEditorFrame,
                self.getEditorRootCanvas,
                self.getAllEditorPlacers,
                allWidgetDefinitions,
                not self.mainView.editorFrame.visEditorInAspect2D,
                autosave=True)
        except Exception as e:
            logging.error("Autosave failed")
            logging.exception(e)
            print("autosave failed")
        return task.again

    def inteligentEscape(self):
        dlgList = [self.dlgHelp, self.dlgSettings, self.dlgQuit, self.dlgWarning, self.dlgInfo, self.dlgNewProject]
        if not all(dlg is None for dlg in dlgList):
            self.openDialogCloseFunctions[-1](None)
        else:
            self.selectElement(self.visualEditorInfo, None)

    def registerKeyboardEvents(self):
        """Register events for user input."""
        speedUp = 5
        speedDown = 0.5
        self.keyEvents = {
            "+": [self.mainView.editorFrame.zoom, [.1]],
            "-": [self.mainView.editorFrame.zoom, [-.1]],
            "control-0": [self.mainView.editorFrame.resetZoom],

            "control-n": [self.new],
            "control-s": [self.save],
            "control-e": [self.export],
            "control-o": [self.load],
            "control-q": [self.quitApp],
            "control-c": [self.copyElement],
            "control-x": [self.cutElement],
            "control-v": [self.pasteElement],
            "shift-control-c": [self.copyOptions],
            "shift-control-v": [self.pasteOptions],
            "control-delete": [self.removeElement],
            "control-d": [self.removeElement],
            "control-g": [self.mainView.toolBar.cb_grid.commandFunc, [None]],
            "control-h": [self.toggleElementVisibility],
            "f1": [self.showHelp],
            "control-z": [self.undo],
            "control-y": [self.redo],
            "shift-control-y": [self.cycleKillRing],

            "page_up": [self.moveElementInStructure, [1]],
            "page_down": [self.moveElementInStructure, [-2]],

            "arrow_left": [self.moveElement, ["left"]],
            "arrow_right": [self.moveElement, ["right"]],
            "arrow_up": [self.moveElement, ["up"]],
            "arrow_down": [self.moveElement, ["down"]],

            "arrow_left-repeat": [self.moveElement, ["left"]],
            "arrow_right-repeat": [self.moveElement, ["right"]],
            "arrow_up-repeat": [self.moveElement, ["up"]],
            "arrow_down-repeat": [self.moveElement, ["down"]],

            "shift-arrow_left": [self.moveElement, ["left", speedUp]],
            "shift-arrow_right": [self.moveElement, ["right", speedUp]],
            "shift-arrow_up": [self.moveElement, ["up", speedUp]],
            "shift-arrow_down": [self.moveElement, ["down", speedUp]],

            "shift-arrow_left-repeat": [self.moveElement, ["left", speedUp]],
            "shift-arrow_right-repeat": [self.moveElement, ["right", speedUp]],
            "shift-arrow_up-repeat": [self.moveElement, ["up", speedUp]],
            "shift-arrow_down-repeat": [self.moveElement, ["down", speedUp]]
        }

        for event, actionSet in self.keyEvents.items():
            if len(actionSet) == 2:
                self.accept(event, actionSet[0], extraArgs=actionSet[1])
            else:
                self.accept(event, actionSet[0])

    def ignoreKeyboardEvents(self):
        """Ignore events for user input."""
        for event, actionSet in self.keyEvents.items():
            self.ignore(event)

    def windowEventHandler(self, window=None):
        """Handle resizing of the window."""
        # call showBase windowEvent which would otherwise get overridden and breaking the app
        base.windowEvent(window)

        if window != base.win:
            # This event isn't about our window.
            return

        if window is not None: # window is none if panda3d is not started
            if self.screenSize == base.getSize():
                return
            self.screenSize = base.getSize()
            self.screenWidth = abs(base.a2dRight) + abs(base.a2dLeft)
            self.screenWidthPx = base.getSize()[0]
            self.screenHeightPx = base.getSize()[1]

            # resize the main splitter to fit the remaining window space
            #self.mainView.mainSplitter["frameSize"] = self.mainView.getMainSplitterSize()

    def propertiesEditor(self, elementInfo):
        self.mainView.propertiesFrame.setupProperties("Editor Properties", elementInfo, self.elementDict)

    def __refreshStructureTree(self):
        """Update the structure tree panel to reflect the current state of the project."""
        self.mainView.structureFrame.refreshStructureTree(self.elementDict, self.selectedElement)

    def __createControl(self, element, skipAddToKillRing=False, parentInfo=None, skipAddItemFunc=False):
        """Create a new element and reparent it to the selected object.

        :param str element: The type of element to add (for example 'DirectScrolledFrame')
        :param ElementInfo parentInfo: Parent of the created element. If None: 'selectedElement' is parent instead.
        :param skipAddItemFunc: Weather or not the addItemFunction will be called for custom widgets.
        :return: The new element
        """
        funcName = "create{}".format(element)
        parent = None
        elementInfo = None
        widget = self.customWidgetsHandler.getWidget(element)
        if self.selectedElement is not None and parentInfo is None:
            parentInfo = self.selectedElement
        if parentInfo is not None:
            if parentInfo.type == "DirectScrolledFrame":
                parent = parentInfo.element.canvas
            else:
                parent = parentInfo.element
        if hasattr(self.elementHandler, funcName):
            if widget is None:
                elementInfo = getattr(self.elementHandler, funcName)(parent)
            else:
                elementInfo = getattr(self.elementHandler, funcName)(widget, parent)
        else:
            logging.error("Undefined control: {}".format(element))
            return

        if elementInfo is None: return

        if type(elementInfo) is tuple:
            if parentInfo is not None and parentInfo.type == "DirectScrolledList":
                parentInfo.element.addItem(elementInfo[0].element)
            elif parentInfo is not None:
                widget = self.customWidgetsHandler.getWidget(parentInfo.type)
                if widget is not None and not skipAddItemFunc:
                    # call custom widget add function
                    widget.callAddItemFunc(parentInfo, elementInfo)
            for entry in elementInfo:
                if parentInfo is not None and entry.parent is None:
                    entry.parent = parentInfo
                sort = self.getMaxSort(entry)
                entry.element.reparentTo(entry.element.getParent(), sort)
                self.elementDict[entry.element.guiId] = entry
        else:
            if parentInfo is not None:
                elementInfo.parent = parentInfo
                if parentInfo.type == "DirectScrolledList":
                    parentInfo.element.addItem(elementInfo.element)
                widget = self.customWidgetsHandler.getWidget(parentInfo.type)
                if widget is not None and not skipAddItemFunc:
                    # call custom widget add function
                    widget.callAddItemFunc(parentInfo, elementInfo)
            sort = self.getMaxSort(elementInfo)
            elementInfo.element.reparentTo(elementInfo.element.getParent(), sort)
            self.elementDict[elementInfo.element.guiId] = elementInfo
        base.messenger.send("refreshStructureTree")
        base.messenger.send("setDirtyFlag")

        if not skipAddToKillRing:
            if type(elementInfo) is tuple:
                base.messenger.send("addToKillRing",
                    [elementInfo[0].element, "add", "element", (elementInfo[0].element.guiId, elementInfo[0]), None])
            else:
                base.messenger.send("addToKillRing",
                    [elementInfo.element, "add", "element", (elementInfo.element.guiId, elementInfo), None])

        self.fixElementSortAll()

        return elementInfo

    def selectElement(self, elementInfo, args=None):
        """Select the element in 'elementInfo'.

        :param ElementInfo elementInfo: The elementInfo for the element to select
        :param args: Not currently used
        """
        if elementInfo is self.selectedElement:
            return

        if self.selectedElement is not None:
            # handle coloring for selected and cut elements
            if self.selectedElement is self.theCutElement:
                self.selectedElement.element.setColorScale(0.5, 0.5, 0.5, 0.5)

            else:
                self.selectedElement.element.clearColorScale()

            self.ignoreKeyboardEvents()
            self.registerKeyboardEvents()
        if elementInfo is None:
            base.messenger.send("showWarning", ["Element can't be selected"])
            return
        if elementInfo.element is self.mainView.editorFrame.visualEditor:
            # we don't need to select the editor itself
            self.selectedElement = None
            self.refreshProperties(elementInfo)
            base.messenger.send("refreshStructureTree")
            return
        if elementInfo.element is None:
            return
        self.selectedElement = elementInfo
        # handle coloring for selected and cut elements
        if self.selectedElement is self.theCutElement:
            elementInfo.element.setColorScale(0.5, 0.5, 0, 0.5)
        else:
            elementInfo.element.setColorScale(1, 1, 0, 1)

        self.refreshProperties(elementInfo)
        base.messenger.send("refreshStructureTree")

    def refreshProperties(self, elementInfo):
        """Clear the properties panel and populate it with the properties of the new elementInfo.

        :param ElementInfo elementInfo: The info for the new selected element
        """
        self.mainView.propertiesFrame.clear()
        propFuncName = "properties{}".format(elementInfo.type)
        try:
            widget = self.customWidgetsHandler.getWidget(elementInfo.type)
            if elementInfo.type == "Editor":
                getattr(self, propFuncName)(elementInfo)
            if hasattr(self.elementHandler, propFuncName):
                if widget is None:
                    getattr(self.elementHandler, propFuncName)(elementInfo, self.elementDict)
                else:
                    getattr(self.elementHandler, propFuncName)(elementInfo, self.elementDict, widget)
        except:
            e = sys.exc_info()[1]
            base.messenger.send("showWarning", [str(e)])
            logging.exception("Error while loading properties panel")

    def dragStart(self, elementInfo, event):
        """Called when element is clicked. Selects element and sets up the drag task to enable moving the element.

        :param ElementInfo elementInfo: The info of the clicked element
        :param event: The mouse event
        """
        self.selectElement(elementInfo, event)
        element = elementInfo.element
        taskMgr.remove("dragDropTask")
        parent = element.getParent()
        sp = element.getPos()
        pos = element.getPos(parent)
        element.setPos(pos)
        vWidget2render2d = element.getPos(render2d)
        vMouse2render2d = Point3(event.getMouse()[0], 0, event.getMouse()[1])
        editVec = Vec3(vWidget2render2d - vMouse2render2d)
        t = taskMgr.add(self.dragTask, "dragDropTask")
        t.startPos = sp
        t.elementInfo = elementInfo
        t.editVec = editVec
        t.mouseVec = vMouse2render2d
        t.hasMoved = False

    def dragTask(self, t):
        """Task for repositioning the selected element by dragging it."""
        mwn = base.mouseWatcherNode
        if mwn.hasMouse():
            vMouse2render2d = Point3(mwn.getMouse()[0], 0, mwn.getMouse()[1])
            newPos = vMouse2render2d + t.editVec

            if self.mainView.editorFrame.snapToGrid and (t.mouseVec - vMouse2render2d).length() < 0.01:
                return t.cont

            try:
                oldPos = t.elementInfo.element.getPos()
            except AssertionError:  # Required to handle the close button on DirectScrolledWindowFrame
                self.removeElement(t.elementInfo.element)
                return

            t.elementInfo.element.setPos(render2d, newPos)

            if self.mainView.editorFrame.snapToGrid:

                newPos = t.elementInfo.element.getPos()
                modifier = 0.5
                if self.is_down(self.key_lcontrol) or self.is_down(self.key_rcontrol):
                    modifier = 0.25
                if self.is_down(self.key_lshift) or self.is_down(self.key_rshift):
                    modifier = 1
                newPos.set(
                    ROUND_TO(newPos[0], self.mainView.editorFrame.grid.getGridSpacing()*modifier),
                    ROUND_TO(newPos[1], self.mainView.editorFrame.grid.getGridSpacing()*modifier),
                    ROUND_TO(newPos[2], self.mainView.editorFrame.grid.getGridSpacing()*modifier))
                t.elementInfo.element.setPos(newPos)

            # check if the item has actually moved
            if not self.dirty and oldPos != t.elementInfo.element.getPos():
                base.messenger.send("setDirtyFlag")
            if oldPos != t.elementInfo.element.getPos():
                t.hasMoved = True

        return t.cont

    def dragStop(self, event):
        """Called when element is no longer clicked to stop dragging it."""
        t = taskMgr.getTasksNamed("dragDropTask")[0]
        #parent = t.elementInfo.element.getParent()
        pos = t.elementInfo.element.getPos()

        if ConfigVariableBool("keep-in-canvas", False).getValue():
            if pos.x < self.mainView.editorFrame.getEditorCanvasSize()[0]:
                t.elementInfo.element.setX(self.mainView.editorFrame.getEditorCanvasSize()[0])
            if pos.x > self.mainView.editorFrame.getEditorCanvasSize()[1]:
                t.elementInfo.element.setX(self.mainView.editorFrame.getEditorCanvasSize()[1])
            if pos.z < self.mainView.editorFrame.getEditorCanvasSize()[2]:
                t.elementInfo.element.setZ(self.mainView.editorFrame.getEditorCanvasSize()[2])
            if pos.z > self.mainView.editorFrame.getEditorCanvasSize()[3]:
                t.elementInfo.element.setZ(self.mainView.editorFrame.getEditorCanvasSize()[3])

        if t.hasMoved:
            definition = PropertyHelper.getDefinition(t.elementInfo, "pos")
            PropertyHelper.setValue(definition, t.elementInfo, pos)
            self.refreshProperties(t.elementInfo)
            base.messenger.send("addToKillRing",
                                [t.elementInfo, "set", "pos", t.startPos, t.elementInfo.element.getPos()])

        taskMgr.remove("dragDropTask")

    def moveElement(self, direction, speedMult=1):
        """Move the selected element using the arrow keys."""
        if self.selectedElement is None: return
        workOn = self.selectedElement.element

        # Make sure elements always move the same amount no matter their scale
        # The parents scale will be ignored, elements will move
        # respective to their parents scale not the visual editor frame
        scale = workOn.getScale()
        moverScaleX = 1 / scale.getX()
        moverScaleZ = 1 / scale.getZ()

        startPos = workOn.getPos()

        speed = 0.01
        if not self.mainView.editorFrame.visEditorInAspect2D:
            speed = 5

        if direction == "left":
            workOn.setX(workOn, -speed*moverScaleX*speedMult)
        elif direction == "right":
            workOn.setX(workOn, speed*moverScaleX*speedMult)
        elif direction == "up":
            workOn.setZ(workOn, speed*moverScaleZ*speedMult)
        elif direction == "down":
            workOn.setZ(workOn, -speed*moverScaleZ*speedMult)
        self.refreshProperties(self.selectedElement)
        base.messenger.send("setDirtyFlag")
        base.messenger.send("addToKillRing",
            [self.selectedElement, "set", "pos", startPos, workOn.getPos()])

    def removeElement(self, element=None, includeWithKillCycle=True):
        """Remove element from the project."""
        workOn = None
        selectEditor = False
        if element is not None:
            workOn = element
            if self.selectedElement is not None and element == self.selectedElement.element:
                selectEditor = True
                self.selectedElement = None
        elif self.selectedElement is not None:
            taskMgr.remove("dragDropTask")
            selectEditor = True
            workOn = self.selectedElement.element
            self.selectedElement = None
        else:
            return

        oldParent = None
        if not workOn.isEmpty() and not workOn.isStashed():
            self.canvasParents = [
                "canvasTopCenter","canvasBottomCenter","canvasLeftCenter","canvasRightCenter",
                "canvasTopLeft","canvasTopRight","canvasBottomLeft","canvasBottomRight"]
            name = workOn.getName()
            if name.split("-")[1] in self.elementDict.keys():
                name = name.split("-")[1]
            if name in self.elementDict.keys():

                if includeWithKillCycle:
                    base.messenger.send("addToKillRing",
                        [workOn, "kill", "element", (name, self.elementDict[name]), None])

                if self.elementDict[name].parent is not None \
                and (self.elementDict[name].parent.getName() if hasattr(self.elementDict[name].parent, "getName") else self.elementDict[name].parent.name) not in self.canvasParents \
                and self.elementDict[name].parent.type == "DirectScrolledList":
                    self.elementDict[name].parent.element.removeItem(workOn)

                # Check if our parent is a custom widget
                if self.elementDict[name].parent is not None \
                and isinstance(self.elementDict[name].parent, ElementInfo) \
                and self.customWidgetsHandler.getWidget(self.elementDict[name].parent.type) is not None:
                    widget = self.customWidgetsHandler.getWidget(self.elementDict[name].parent.type)
                    if widget.removeItemFunction is not None:
                        # call custom widget remove function
                        try:
                            getattr(self.elementDict[name].parent.element, widget.removeItemFunction)(workOn)
                        except:
                            try:
                                getattr(self.elementDict[name].parent.element, widget.removeItemFunction)()
                            except Exception as e:
                                logging.error("Error while calling remove item function {} of item {}".format(widget.removeItemFunction, name))
                                logging.exception(e)
                del self.elementDict[name]
        try:
            workOn.stash()
        except Exception as e:
            print(e)

        #workOn.destroy()

        # cleanup
        for key, value in self.elementDict.copy().items():
            if value is None or value.element.isEmpty() or value.element.isStashed():
                del self.elementDict[key]

        if selectEditor:
            self.selectElement(self.visualEditorInfo)
        self.fixElementSortAll()
        base.messenger.send("refreshStructureTree")
        base.messenger.send("setDirtyFlag")

    def toggleElementVisibility(self, element=None):
        workOn = None
        if element is not None:
            workOn = element
        elif self.selectedElement is not None:
            workOn = self.selectedElement.element
        else:
            return

        if workOn.isHidden():
            workOn.show()
        else:
            workOn.hide()
        base.messenger.send("refreshStructureTree")

    def getMaxSort(self, elementInfo):
        """Returns the next sort value of the parent of the given "child" element"""
        children = list(elementInfo.element.getParent().getChildren().getPaths())
        if elementInfo.parent is None:
            children = children[9:]
        return len(children)+1

    def fixElementSortAll(self):
        fixedParents = []
        for name, elementInfo in self.elementDict.items():
            if elementInfo.parent in fixedParents:
                continue
            fixedParents.append(elementInfo.parent)

            children = list(elementInfo.element.getParent().getChildren().getPaths())
            if elementInfo.parent is None:
                children = children[9:]

            #sort = len(children)
            sort = 1
            for child in children:
                child.reparentTo(child.getParent(), sort)
                sort += 1

    def moveElementInStructure(self, direction=1, childElementInfo=None):
        # make sure the sort values of all elements are correct
        self.fixElementSortAll()

        workOn = None
        if childElementInfo is not None:
            workOn = childElementInfo
        elif self.selectedElement is not None:
            workOn = self.selectedElement
        else:
            return

        parent = workOn.element.getParent()
        workOnParent = self.getElementInfo(parent)
        #self.getElementSort(workOn)
        newSort = max(0, workOn.element.getSort()+direction)

        self.reparentElement(workOn, workOnParent, newSort)

        # make sure the sort is correct afterward
        self.fixElementSortAll()


    def reparentElement(self, childElementInfo=None, parentElementInfo=None, sortInParent=0):
        workOn = None
        if childElementInfo is not None:
            workOn = childElementInfo.element
        elif self.selectedElement is not None:
            workOn = self.selectedElement.element
        else:
            return

        workOnParent = None
        if parentElementInfo is not None:
            workOnParent = parentElementInfo.element
        else:
            workOnParent = workOn.getParent()

        workOn.reparentTo(workOnParent, sortInParent)

        base.messenger.send("refreshStructureTree")

        #TODO: Drag and drop in the strucutre view?
        #TODO: Up/Down pgup/gpdown to move selected element up or down in the tree

    def __findFirstGUIElement(self, root):
        """Find the closest ancestor of the root that is an actual gui element.
        For example if root is the canvas of a scrolledFrame, the scrolledFrame would be returned.
        If a valid ancestor can not be found None would be returned instead.
        """
        if hasattr(root, "getParent"):
            if not root.getParent().isEmpty():
                name = root.getParent().getName()
                if len(root.getName().split("-")) > 1:
                    name = root.getName().split("-")[1]
                if name in self.elementDict:
                    return self.elementDict[name]
                return self.__findFirstGUIElement(root.getParent())
            else:
                return None
        return None

    def getElementInfo(self, nameOrElement):
        """Returns the element info for the given GUI ID or GUI element or
        None if it is not in the dictionary"""
        if nameOrElement in self.elementDict:
            return self.elementDict[nameOrElement]
        elif type(nameOrElement) == str:
            logging.error(f"couldn't find element info for GUI ID {nameOrElement}")
            return None
        else:
            element = self.__findFirstGUIElement(nameOrElement)
            if element is None:
                logging.error(f"couldn't find element info for element {nameOrElement}")
            return element

    def setName(self, elementInfo, name):
        """Set name of element in 'elementInfo' to 'name'."""
        guiId = elementInfo.element.guiId
        e = self.elementDict[guiId]
        e.name = name
        if e.type == "DirectEntry":
            if (e.parent is not None
            and e.parent.type == "DirectEntryScroll"):
                parentID = e.parent.element.guiId
                self.elementDict[parentID].extraOptions["entry"] = name
        base.messenger.send("refreshStructureTree")

    def setParentOfElement(self, element, parent):
        """Set the parent tag in the elements elementInfo to the correct parent based on 'parent'.

        :param element: The element
        :param parent: Some NodePath
        """
        self.canvasParents = [
            "canvasTopCenter","canvasBottomCenter","canvasLeftCenter","canvasRightCenter",
            "canvasTopLeft","canvasTopRight","canvasBottomLeft","canvasBottomRight"]

        if parent is self.mainView.getEditorRootCanvas():
            self.elementDict[element.guiId].parent = None
        else:
            parentElement = None
            if parent.getName() in self.elementDict.keys():
                parentElement = self.elementDict[parent.getName()]
            elif len(parent.getName().split("-")) > 1 and parent.getName().split("-")[1] in self.elementDict.keys():
                parentElement = self.elementDict[parent.getName().split("-")[1]]
            elif parent.getName() in self.canvasParents:
                parentElement = parent
            else:
                # check if we can find an element as parent of the current NP
                # This happens for elements that have a canvas or other sub NPs
                parentElement = self.__findFirstGUIElement(parent)
            self.elementDict[element.guiId].parent = parentElement

    def copyElement(self):
        """Copy the selected element (store element in 'self.copiedElement' to be copied later)."""
        if self.selectedElement is None: return
        self.copiedElement = self.selectedElement

    def cutElement(self):
        """Cut the selected element (store element in 'self.theCutElement' to be cut and pasted later)."""
        if self.selectedElement is None: return
        # handle color scale of last cut element
        if self.theCutElement is not None:
            self.theCutElement.element.clearColorScale()

        self.theCutElement = self.selectedElement
        # set color scale for new cut element
        self.theCutElement.element.setColorScale(0.5, 0.5, 0, 0.5)

    def pasteElement(self):
        """Paste element that was copied or cut to currently selected element."""
        # check if we want to have a cut or copy action

        if self.theCutElement is not None:
            # CUT
            # the previous action was a cutting action, so we don't want to copy
            return self.pasteCutElement()

        if self.copiedElement is None: return

        # COPY
        # stores the ids of the source elements that have been copied already
        self.copyCreatedElementIds = []
        self.newElementIds = []
        # store list of all elements that should be copied,
        # used to break loops when pasting onto a child of the copied element
        self.elementsToCopy = self.copiedElement.element.get_children()
        self.elementsToCopy.append(self.copiedElement.element)
        self.__copyBranch(self.copiedElement, self.selectedElement)

        if self.newElementIds == []:
            return
        e = self.elementDict[self.newElementIds[0]]
        base.messenger.send("addToKillRing",
            [e, "copy", "element", (self.newElementIds[0], e), None])

    def __copyBranch(self, startObject, parent=None):
        """Copy 'startObject' and its child-elements to 'parent'."""
        for elementName, elementInfo in self.elementDict.copy().items():
            if elementInfo.element.guiId in self.copyCreatedElementIds: continue
            if elementInfo.element not in self.elementsToCopy: continue
            if elementInfo.parent == startObject or elementInfo == startObject:
                newElement = self.__createControl(elementInfo.type, skipAddToKillRing=True, parentInfo=parent, skipAddItemFunc=True)
                if type(newElement) is tuple:
                    newElement = newElement[0]
                self.newElementIds.append(newElement.element.guiId)
                self.copyCreatedElementIds.append(elementInfo.element.guiId)
                if parent is not None:
                    newParent = None
                    if type(parent) is ElementInfo:
                        newParent = parent.element
                    else:
                        newParent = parent
                    self.setParentOfElement(newElement.element, newParent)
                    if isinstance(newParent, (DirectGui.DirectScrolledFrame, DirectScrolledFrame)):
                        newParent = newParent.canvas
                    newElement.element.reparentTo(newParent)
                self.__copyOptions(elementInfo, newElement, parent is not None, skipAddToKillRing=True, parentInfo=parent)

                self.__copyBranch(elementInfo, newElement)

    def pasteCutElement(self):
        """Paste the cut element to the selected element."""
        if self.theCutElement is None: return
        if self.theCutElement == self.selectedElement: return
        oldParent = self.theCutElement.element.getParent()

        if self.selectedElement is None:
            parent = self.mainView.getEditorPlacer("root")

            self.theCutElement.element.reparentTo(parent)
            self.theCutElement.parent = None

        else:
            if self.theCutElement.element.isAncestorOf(self.selectedElement.element): return

            parent = self.selectedElement
            self.theCutElement.parent = parent
            if isinstance(parent.element, (DirectGui.DirectScrolledFrame, DirectScrolledFrame)):
                parent = parent.element.canvas
            else:
                parent = parent.element

            self.theCutElement.element.reparentTo(parent)

            widget = self.customWidgetsHandler.getWidget(self.selectedElement.type)
            if widget is not None:
                # call custom widget add function
                widget.callAddItemFunc(self.selectedElement, self.theCutElement, forceOpenDialog=True)

        self.theCutElement.element.clearColorScale()

        base.messenger.send("addToKillRing",
                            [self.theCutElement, "cut", "element", oldParent, parent])

        self.theCutElement = None

        base.messenger.send("refreshStructureTree")

    def copyOptions(self):
        """Copy the selected elements options (properties)."""
        if self.selectedElement is None: return
        self.copyOptionsElementInfo = self.selectedElement

    def pasteOptions(self):
        """Paste options to the selected element."""
        if self.copyOptionsElementInfo is None: return

        if self.selectedElement is None:  # if no element is selected
            base.messenger.send("showInfo", ["Please select an element to paste to"])
            return

        self.__copyOptions(self.copyOptionsElementInfo, self.selectedElement)

    def __copyOptions(self, elementInfoFrom, elementInfoTo, copyPosition=False, skipAddToKillRing=False, parentInfo=None):
        elementFrom = elementInfoFrom.element
        elementTo = elementInfoTo.element
        if elementFrom is None or elementTo is None: return
        try:
            # store for undo
            oldOptions = elementTo._optionInfo.copy()
            oldOptions["hpr"] = elementTo.getHpr()
            oldOptions["scale"] = elementTo.getScale()
            oldOptions["pos"] = elementTo.getPos()
            oldOptions["text_fg"] = None

            text = elementTo["text"]
            text_fg = None
            for compName in elementFrom.components():
                comp = elementFrom.component(compName)
                if hasattr(comp, "fg"):
                    text_fg = comp.fg
                    break

            hpr = elementFrom.getHpr()
            scale = elementFrom.getScale()
            if copyPosition:
                pos = elementFrom.getPos()
            elementTo.copyOptions(elementFrom)
            elementTo["text"] = text
            if text_fg is not None:

                for compName in elementTo.components():
                    comp = elementTo.component(compName)
                    if hasattr(comp, "fg"):
                        oldOptions["text_fg"] = comp.fg
                        break

                elementTo["text_fg"] = text_fg
            elementTo.setHpr(hpr)
            elementTo.setScale(scale)

            # store for redo
            newOptions = elementTo._optionInfo.copy()
            newOptions["hpr"] = elementTo.getHpr()
            newOptions["scale"] = elementTo.getScale()
            newOptions["pos"] = elementTo.getPos()
            newOptions["text_fg"] = text_fg

            if copyPosition:
                elementTo.setPos(pos)
                newOptions["pos"] = elementTo.getPos()

            # make sure the changed values are set correct
            for key, changed in elementInfoFrom.valueHasChanged.items():
                p = ["pos"] if copyPosition else []
                if key in ["hpr", "scale"] + p:
                    continue
                elementInfoTo.valueHasChanged[key] = changed

            # handle addItemExtra args and AddItemNode
            elementInfoTo.addItemExtraArgs = elementInfoFrom.addItemExtraArgs.copy()
            elementInfoTo.addItemNode = elementInfoFrom.addItemNode
            if parentInfo is not None:
                widget = self.customWidgetsHandler.getWidget(parentInfo.type)
                if widget is not None:
                    # call custom widget add function
                    widget.callAddItemFunc(parentInfo, elementInfoTo)

            if not skipAddToKillRing:
                base.messenger.send("addToKillRing",
                    [elementTo, "copy", "properties", oldOptions, newOptions])
        except Exception as e:
            logging.error("Couldn't copy element options")
            logging.exception(e)
            base.messenger.send("showWarning", ["Couldn't copy element options"])

    def new(self):
        """Create a new project if there are no unsaved changes, otherwise ask user."""
        if self.dirty:
            self.dlgNewProject = OkCancelDialog(
                text="You have unsaved changes!\nReally create new project?",
                relief=DGG.RIDGE,
                frameColor=(1,1,1,1),
                frameSize=(-0.5,0.5,-0.3,0.2),
                sortOrder=1,
                button_relief=DGG.FLAT,
                button_frameColor=(0.8, 0.8, 0.8, 1),
                command=self.__newProject,
                scale=300,
                pos=(base.getSize()[0]/2, 0, -base.getSize()[1]/2),
                parent=base.pixel2d)
            self.dlgNewProjectShadow = DirectFrame(
                pos=(base.getSize()[0]/2 + 10, 0, -base.getSize()[1]/2 - 10),
                sortOrder=0,
                frameColor=(0,0,0,0.5),
                frameSize=self.dlgNewProject.bounds,
                scale=300,
                parent=base.pixel2d)
            return False
        else:
            self.__newProject(1)
            return True

    def __newProject(self, selection):
        """Create a new project."""
        if selection == 1:
            for name, elementInfo in list(self.elementDict.items()):
                self.removeElement(elementInfo.element)
            self.selectedElement = None
            self.elementDict = {}
            base.messenger.send("clearDirtyFlag")
        if self.dlgNewProject is not None:
            self.dlgNewProject.destroy()
            self.dlgNewProjectShadow.destroy()
            self.dlgNewProject = None
            self.dlgNewProjectShadow = None

    def save(self):
        """Save project to file."""
        self.selectElement(self.visualEditorInfo)
        allWidgetDefinitions = {
            **WidgetDefinition.DEFINITIONS,
            **self.customWidgetsHandler.getCustomWidgetDefinitions()}
        ExporterProject(
            os.path.join(self.lastDirPath, self.lastFileNameWOExtension + ".gui"),
            self.elementDict,
            self.getEditorFrame,
            self.getEditorRootCanvas,
            self.getAllEditorPlacers,
            allWidgetDefinitions,
            not self.mainView.editorFrame.visEditorInAspect2D,
            tooltip=self.tt)

    def export(self):
        """Export project as python file."""
        self.selectElement(self.visualEditorInfo)
        allWidgetDefinitions = {
            **WidgetDefinition.DEFINITIONS,
            **self.customWidgetsHandler.getCustomWidgetDefinitions()}
        ExporterPy(
            os.path.join(self.lastDirPath, self.lastFileNameWOExtension + ".py"),
            self.elementDict,
            self.customWidgetsHandler,
            self.getEditorFrame,
            self.getEditorRootCanvas,
            self.getAllEditorPlacers,
            allWidgetDefinitions,
            self.tt,
            not self.mainView.editorFrame.visEditorInAspect2D)

    def load(self):
        """Load project from a .gui file."""
        self.selectElement(self.visualEditorInfo)

        allWidgetDefinitions = {
            **WidgetDefinition.DEFINITIONS,
            **self.customWidgetsHandler.getCustomWidgetDefinitions()}
        projectLoader = ProjectLoader(
            os.path.join(self.lastDirPath, self.lastFileNameWOExtension + ".gui"),
            self.visualEditorInfo,
            self.elementHandler,
            self.customWidgetsHandler,
            self.mainView.getEditorPlacer,
            allWidgetDefinitions,
            False,
            self.tt,
            self.new)

    def load_file(self, filename):
        """Directly load the passed .gui file."""
        self.selectElement(self.visualEditorInfo)

        allWidgetDefinitions = {
            **WidgetDefinition.DEFINITIONS,
            **self.customWidgetsHandler.getCustomWidgetDefinitions()}
        ProjectLoader(
            filename,
            self.visualEditorInfo,
            self.elementHandler,
            self.customWidgetsHandler,
            self.mainView.getEditorPlacer,
            allWidgetDefinitions,
            directLoading=True)

    def updateElementDict(self, newDict):
        self.elementDict.update(newDict)
        base.messenger.send("refreshStructureTree")

    def __quit(self, selection):
        if selection == 1:
            base.userExit()
        else:
            self.dlgQuit.destroy()
            self.dlgQuitShadow.destroy()
            self.dlgQuit = None
            self.dlgQuitShadow = None
            del self.openDialogCloseFunctions[-1]

    def quitApp(self):
        if self.dlgQuit is not None: return
        if ConfigVariableBool("skip-ask-for-quit", False).getValue() or self.dirty == False:
            self.__quit(1)
            return

        self.dlgQuit = OkCancelDialog(
            text="You have unsaved changes!\nReally Quit?",
            state=DGG.NORMAL,
            relief=DGG.RIDGE,
            frameColor=(1,1,1,1),
            scale=300,
            pos=(base.getSize()[0]/2, 0, -base.getSize()[1]/2),
            sortOrder=1,
            button_relief=DGG.FLAT,
            button_frameColor=(0.8, 0.8, 0.8, 1),
            command=self.__quit,
            parent=base.pixel2d)
        self.dlgQuitShadow = DirectFrame(
            state=DGG.NORMAL,
            sortOrder=0,
            frameColor=(0,0,0,0.5),
            frameSize=(0, base.getSize()[0], -base.getSize()[1], 0),
            parent=base.pixel2d)
        self.openDialogCloseFunctions.append(self.__quit)

    def showSettings(self):
        """Show settings panel."""
        if self.dlgSettings is not None:
            return

        base.messenger.send("unregisterKeyboardEvents")
        self.dlgSettingsShadow = DirectFrame(
            state=DGG.NORMAL,
            sortOrder=0,
            frameColor=(0,0,0,0.5),
            frameSize=(0, base.getSize()[0], -base.getSize()[1], 0),
            parent=base.pixel2d)

        self.dlgSettings = SettingsDialog(base.pixel2d)

        self.dlgSettings.lblSearchPath["state"] = DGG.NORMAL
        self.dlgSettings.lblSearchPath.bind(DGG.ENTER, self.tt.show, ["A colon separated list of paths to search for models, images and other assets"])
        self.dlgSettings.lblSearchPath.bind(DGG.EXIT, self.tt.hide)
        self.dlgSettings.txtSearchPaths.bind(DGG.ENTER, self.tt.show, ["A colon separated list of paths to search for models, images and other assets"])
        self.dlgSettings.txtSearchPaths.bind(DGG.EXIT, self.tt.hide)

        self.dlgSettings.setPos = self.dlgSettings.frmMain.setPos
        self.dlgSettings.setPos(base.getSize()[0] // 2, 0, -base.getSize()[1] // 2)
        self.dlgSettings.cbAskForQuit["indicatorValue"] = not ConfigVariableBool("skip-ask-for-quit", False).getValue()
        self.dlgSettings.cbExecutableScripts["indicatorValue"] = ConfigVariableBool("create-executable-scripts", False).getValue()
        self.dlgSettings.cbShowToolbar["indicatorValue"] = ConfigVariableBool("show-toolbar", True).getValue()
        self.dlgSettings.txtCustomWidgetsPath.enterText(ConfigVariableString("custom-widgets-path", "").getValue())
        self.dlgSettings.txtWorkDir.enterText(ConfigVariableString("work-dir-path", "").getValue())
        self.dlgSettings.spinAutosaveDealy.setValue(ConfigVariableInt("autosave-delay", 60).getValue())

        paths = ""
        pathsConfig = ConfigVariableSearchPath("custom-model-path", "").getValue()
        for path in pathsConfig.getDirectories():
            if paths != "":
                paths = "{}:{}".format(paths, path)
            else:
                paths = str(path)
        self.dlgSettings.txtSearchPaths.enterText(paths)

        def selectWidgetsPath(confirm):
            if confirm:
                self.dlgSettings.txtCustomWidgetsPath.enterText(self.browser.get())
            self.browser.hide()
            self.browser = None
        def showWidgetsBrowser():
            self.browser = DirectFolderBrowser(selectWidgetsPath, False, ConfigVariableString("custom-widgets-path", "").getValue(), os.path.split(ConfigVariableString("custom-widgets-path", "").getValue())[1], tooltip=self.tt)
            self.browser.show()
        self.dlgSettings.btnBrowseWidgetPath["command"] = showWidgetsBrowser

        def addSearchPath(confirm):
            if confirm:
                prevPaths = self.dlgSettings.txtSearchPaths.get()
                self.dlgSettings.txtSearchPaths.enterText("{}:{}".format(prevPaths, self.browser.get()))
            self.browser.hide()
            self.browser = None
        def showSearchPathBrowser():
            self.browser = DirectFolderBrowser(addSearchPath, False, tooltip=self.tt)
            self.browser.show()
        self.dlgSettings.btnBrowseSearchPaths["command"] = showSearchPathBrowser

        def selectWorkDirPath(confirm):
            if confirm:
                self.dlgSettings.txtWorkDir.enterText(self.browser.get())
            self.browser.hide()
            self.browser = None
        def showWorkDirBrowser():
            self.browser = DirectFolderBrowser(selectWorkDirPath, False, ConfigVariableString("work-dir-path", "").getValue(), os.path.split(ConfigVariableString("work-dir-path", "").getValue())[1], tooltip=self.tt)
            self.browser.show()
        self.dlgSettings.btnBrowseWorkDir["command"] = showWorkDirBrowser

        self.openDialogCloseFunctions.append(self.hideSettings)

    def hideSettings(self, accept):
        """Hide settings panel and save settings if 'accept' is True."""
        base.messenger.send("reregisterKeyboardEvents")
        if accept:
            with open(self.config_file, "w") as prcFile:
                line = "skip-ask-for-quit {}\n".format("#t" if self.dlgSettings.cbAskForQuit["indicatorValue"] == 0 else "#f")
                prcFile.write(line)
                loadPrcFileData("", line)

                line = "create-executable-scripts {}\n".format("#f" if self.dlgSettings.cbExecutableScripts["indicatorValue"] == 0 else "#t")
                prcFile.write(line)
                loadPrcFileData("", line)

                line = "show-toolbar {}\n".format("#f" if self.dlgSettings.cbShowToolbar["indicatorValue"] == 0 else "#t")
                prcFile.write(line)
                loadPrcFileData("", line)

                prcFile.write("custom-widgets-path {}\n".format(self.dlgSettings.txtCustomWidgetsPath.get()))
                for path in self.dlgSettings.txtSearchPaths.get().split(":"):
                    line = "custom-model-path {}\n".format(path)
                    prcFile.write(line)
                    line = "model-path {}\n".format(path)
                    loadPrcFileData("", line)

                prcFile.write("work-dir-path {}\n".format(self.dlgSettings.txtWorkDir.get()))

                line = "autosave-delay {}\n".format(self.dlgSettings.spinAutosaveDealy.get())
                prcFile.write(line)
                loadPrcFileData("", line)

            # This somehow results in files that can't be changed by the code above anymore
            # So... no hidden config files for windows.
            #if platform.system() == "Windows":
            #    from ctypes import WinDLL
            #    from stat import FILE_ATTRIBUTE_HIDDEN
            #    from os import stat

            #    # Change the current files attributes to contain the "hidden" attribute
            #    kernel32 = WinDLL("kernel32")
            #    attrs = stat(self.config_file).st_file_attributes
            #    attrs = attrs | FILE_ATTRIBUTE_HIDDEN
            #    kernel32.SetFileAttributesW(self.config_file, attrs)


        self.dlgSettings.frmMain.hide()
        del self.dlgSettings
        self.dlgSettings = None

        self.dlgSettingsShadow.destroy()
        self.dlgSettingsShadow = None
        del self.openDialogCloseFunctions[-1]

    def showHelp(self):
        """Show help panel."""
        if self.dlgHelp is not None:
            self.hideHelp(None)
            return


        tpMgr = TextPropertiesManager.getGlobalPtr()

        tpHeader = TextProperties()
        tpHeader.setTextScale(1.5)
        tpHeader.setUnderscore(True)
        tpHeader.setGlyphShift(1)
        font = loader.loadFont("fonts/DejaVuSansMono-Bold.ttf")
        tpHeader.setFont(font)
        tpMgr.setProperties("header", tpHeader)

        tpSmall = TextProperties()
        tpSmall.setTextScale(0.75)
        tpMgr.setProperties("small", tpSmall)

        tpBold = TextProperties()
        font = loader.loadFont("fonts/DejaVuSansMono-Bold.ttf")
        tpBold.setFont(font)
        tpMgr.setProperties("bold", tpBold)

        text="""\1header\1~~~Direct GUI Visual Editor Help~~~\2

\1bold\1LMB\2 - Select an element / Press and drag to move element around
\1bold\1Esc\2 - Deselect currently selected Element
\1bold\1RMB\2 - Deselect currently selected Element
\1bold\1MMB\2 - Move Editor Area

\1bold\1Mouse Wheel\2 - Zoom

\1bold\1Ctrl-N  \2 - Create New GUI
\1bold\1Ctrl-S  \2 - Save as Project File
\1bold\1Ctrl-E  \2 - Export as Python File
\1bold\1Ctrl-O  \2 - Load Project File
\1bold\1Ctrl-Q  \2 - Quit Application
\1bold\1Ctrl-C  \2 - Copy selected Element
\1bold\1Ctrl-V  \2 - Paste copied Element
\1bold\1Ctrl-Shift-C\2 - Copy selected Elements settings
\1bold\1Ctrl-Shift-V\2 - Paste copied Element settings to selected element
\1bold\1Ctrl-Del\2 or \1bold\1Ctrl-D\2 - Delete selected Element
\1bold\1Ctrl-H  \2 - Toggle selected Element visibility
\1bold\1Ctrl-G  \2 - Toggle grid and snap to grid
\1bold\1Ctrl-Z  \2 - Undo
\1bold\1Ctrl-Y  \2 - Redo
\1bold\1Ctrl-Shift-Y\2 - Cycle through redos

\1bold\1Arrow Keys\2 - Move the selected Element (use Shift and Ctrl to change distance)

\1bold\1F1\2 - Show this help Dialog

Note: If the grid is shown elements will automatically snap to it when moved

Log messages are written to:

\1small\1{}\2


\1small\1LMB = Left Mouse Button | RMB = Right Mouse Button | MMB = Middle Mouse Button\2
""".format(self.log_file)
        self.dlgHelp = OkDialog(
            text=text,
            state=DGG.NORMAL,
            relief=DGG.RIDGE,
            frameColor=(1,1,1,1),
            sortOrder=1,
            scale=300,
            pos=(base.getSize()[0]/2, 0, -base.getSize()[1]/2),
            button_relief=DGG.FLAT,
            button_frameColor=(0.8, 0.8, 0.8, 1),
            command=self.hideHelp,
            parent=base.pixel2d)
        self.dlgHelpShadow = DirectFrame(
            state=DGG.NORMAL,
            sortOrder=0,
            frameColor=(0,0,0,0.5),
            frameSize=(0, base.getSize()[0], -base.getSize()[1], 0),
            parent=base.pixel2d)
        self.openDialogCloseFunctions.append(self.hideHelp)

    def hideHelp(self, args):
        """Hide help panel."""
        self.dlgHelp.destroy()
        self.dlgHelpShadow.destroy()
        self.dlgHelp = None
        self.dlgHelpShadow = None
        del self.openDialogCloseFunctions[-1]

    def showWarning(self, text):
        """Show an ok-dialog with a warning message: 'text'."""
        if self.dlgWarning is not None: return
        text = "WARNING!\n\n" + text
        self.dlgWarning = OkDialog(
            text=text,
            state=DGG.NORMAL,
            relief=DGG.RIDGE,
            frameColor=(1,1,1,1),
            sortOrder=1,
            scale=300,
            pos=(base.getSize()[0]/2, 0, -base.getSize()[1]/2),
            button_relief=DGG.FLAT,
            button_frameColor=(0.8, 0.8, 0.8, 1),
            command=self.hideWarning,
            parent=base.pixel2d)
        self.dlgWarningShadow = DirectFrame(
            state=DGG.NORMAL,
            sortOrder=0,
            frameColor=(0.25,0,0,0.5),
            frameSize=(0, base.getSize()[0], -base.getSize()[1], 0),
            parent=base.pixel2d)
        self.openDialogCloseFunctions.append(self.hideWarning)

    def hideWarning(self, args):
        """Hide warning dialog."""
        self.dlgWarning.destroy()
        self.dlgWarningShadow.destroy()
        self.dlgWarning = None
        self.dlgWarningShadow = None
        del self.openDialogCloseFunctions[-1]

    def showInfo(self, text):
        """Show an ok-dialog with a info message: 'text'."""
        if self.dlgInfo is not None: return
        text = "INFO:\n\n" + text
        self.dlgInfo = OkDialog(
            text=text,
            state=DGG.NORMAL,
            relief=DGG.RIDGE,
            frameColor=(1,1,1,1),
            sortOrder=1,
            scale=300,
            pos=(base.getSize()[0]/2, 0, -base.getSize()[1]/2),
            button_relief=DGG.FLAT,
            button_frameColor=(0.8, 0.8, 0.8, 1),
            command=self.hideInfo,
            parent=base.pixel2d)
        self.dlgInfoShadow = DirectFrame(
            state=DGG.NORMAL,
            sortOrder=0,
            frameColor=(0.15,0.15,0.25,0.5),
            frameSize=(0, base.getSize()[0], -base.getSize()[1], 0),
            parent=base.pixel2d)
        self.openDialogCloseFunctions.append(self.hideInfo)

    def hideInfo(self, args):
        """Hide info dialog."""
        self.dlgInfo.destroy()
        self.dlgInfoShadow.destroy()
        self.dlgInfo = None
        self.dlgInfoShadow = None
        del self.openDialogCloseFunctions[-1]
