import logging

def addToKillRing(elementInfo, definition, oldValue, newValue):
    base.messenger.send("addToKillRing",
        [elementInfo, "set", definition.internalName, oldValue, newValue])

def createTextEntry(text, width, command, commandArgs=[]):
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
    #TODO: This needs to be done in the base panel
    #entry.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
    #entry.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
    return entry


def createPropertyHeader(description):
    l = DirectLabel(
        text=description,
        text_scale=12,
        text_align=TextNode.ALeft,
        #text_pos=(self.propertiesFrame["frameSize"][0] + 5, 0),
        #frameSize=VBase4(self.propertiesFrame["frameSize"][0], self.propertiesFrame["frameSize"][1], -10, 20),
        frameColor=VBase4(0.85, 0.85, 0.85, 1),
        state=DGG.NORMAL)
    #l.bind(DGG.MWDOWN, self.scroll, [self.scrollSpeedDown])
    #l.bind(DGG.MWUP, self.scroll, [self.scrollSpeedUp])
    #self.boxFrame.addItem(l, skipRefresh=True)
    #self.propertyHeaders.append(l)
