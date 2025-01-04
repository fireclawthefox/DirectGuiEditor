
def create(self, definition, elementInfo, n, numberType=float):
    entryList = []

    def update(text, elementInfo):
        base.messenger.send("setDirtyFlag")
        values = []
        for value in entryList:
            try:
                values.append(numberType(value.get(True)))
            except Exception:
                if value.get(True) == "":
                    values.append(None)
                else:
                    logging.exception("ERROR: NAN", value.get(True))
                    values.append(numberType(0))
        try:
            oldValue = PropertyHelper.getValues(definition, elementInfo)
            differ = False
            if oldValue is not None:
                for i in range(n):
                    if oldValue[i] != values[i]:
                        differ = True
                        break
            elif values is not None and values != []:
                differ = True
            if differ:
                self.__addToKillRing(elementInfo, definition, oldValue, values)
        except Exception as e:
            logging.exception(f"{definition.internalName} not supported by undo/redo yet")
        allValuesSet = True
        allValuesNone = True
        for value in values:
            if value is None:
                allValuesSet = False
            if value is not None:
                allValuesNone = False
        if allValuesNone:
            values = None
        elif allValuesSet:
            values = tuple(values)
        if allValuesNone or allValuesSet:
            PropertyHelper.setValue(definition, elementInfo, values)
    self.__createPropertyHeader(definition.visibleName)
    values = PropertyHelper.getValues(definition, elementInfo)
    if type(values) is int or type(values) is float:
        values = [values] * n
    if definition.nullable:
        if values is None:
            values = [""] * n
    width = DGH.getRealWidth(self.boxFrame) / n - self.getScrollBarWidth() / n
    entryBox = DirectBoxSizer()
    for i in range(n):
        value = PropertyHelper.getFormated(values[i])
        entry = self.__createTextEntry(str(value), width, update, [elementInfo])
        entryList.append(entry)
        entryBox.addItem(entry)
    self.boxFrame.addItem(entryBox, skipRefresh=True, updateFunc=entryBox.refresh)
    return entryBox
