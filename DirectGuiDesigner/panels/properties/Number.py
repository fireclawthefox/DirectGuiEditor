import logging
from PropertyBase import createTextEntry, createPropertyHeader, addToKillRing

def create(definition, elementInfo, numberType, width):
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
            addToKillRing(elementInfo, definition, oldValue, value)
        except Exception:
            logging.exception(f"{definition.internalName} not supported by undo/redo yet")
        PropertyHelper.setValue(definition, elementInfo, value)
    createPropertyHeader(definition.visibleName)
    value = PropertyHelper.getValues(definition, elementInfo)
    if value is None and not definition.nullable:
        logging.error(f"Got None value for not nullable element {definition.internalName}")
    if value is not None:
        value = PropertyHelper.getFormated(value, numberType is int)
    entry = createTextEntry(str(value), width, update, [elementInfo])
    #TODO: Do this in base
    #self.boxFrame.addItem(entry, skipRefresh=True)
    return entry

def updateInt(definition, elementInfo, width):
    value = PropertyHelper.getValues(definition, elementInfo)
    if value is None and not definition.nullable:
        logging.error(f"Got None value for not nullable element {definition.internalName}")
    if value is not None:
        value = PropertyHelper.getFormated(value, True)
    element["width"] = width/12
    element.enterText(str(value))

def updateFloat(definition, elementInfo, width):
    value = PropertyHelper.getValues(definition, elementInfo)
    if value is None and not definition.nullable:
        logging.error(f"Got None value for not nullable element {definition.internalName}")
    if value is not None:
        value = PropertyHelper.getFormated(value, False)
    element["width"] = width/12
    element.enterText(str(value))
