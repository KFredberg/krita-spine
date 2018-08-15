import os
import json
import re
import sys
import math
from PyQt5.QtWidgets import *
from krita import *


class SpineTools(DockWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spine Tools")
        self.directory = None
        self.msgBox = None
        self.fileFormat = 'png'
        self.bonePattern = re.compile("\[bone\]", re.IGNORECASE)
        self.mergePattern = re.compile("\[merge\]", re.IGNORECASE)
        self.slotPattern = re.compile("\[slot\]", re.IGNORECASE)
        mainWidget = QWidget(self)
        self.setWidget(mainWidget)
        boxLayout = QVBoxLayout()
        boxLayout.addWidget(self.createLayerTools())
        boxLayout.addWidget(self.createExportTools())
        mainWidget.setLayout(boxLayout)

    def canvasChanged(self, canvas):
        pass

    def createLayerTools(self):
        groupBox = QGroupBox("Layer Tools")

        buttonCreateBoneGroup = QPushButton("Create bone")
        buttonCreateSlotGroup = QPushButton("Create slot")
        buttonCreateMergeGroup = QPushButton("Create merge group")
        buttonAddAnchorTag = QPushButton("Add anchor tag")
        buttonAddBoneEndTag = QPushButton("Add bone end tag")

        buttonCreateBoneGroup.clicked.connect(self.createBoneGroup)
        buttonCreateSlotGroup.clicked.connect(self.createSlotGroup)
        buttonCreateMergeGroup.clicked.connect(self.createMergeGroup)
        buttonAddAnchorTag.clicked.connect(self.addAnchorTag)
        buttonAddBoneEndTag.clicked.connect(self.addBoneEndTag)

        vbox = QVBoxLayout()
        vbox.addWidget(buttonCreateBoneGroup)
        vbox.addWidget(buttonCreateSlotGroup)
        vbox.addWidget(buttonCreateMergeGroup)
        vbox.addWidget(buttonAddAnchorTag)
        vbox.addWidget(buttonAddBoneEndTag)
        vbox.addStretch(1)
        groupBox.setLayout(vbox)

        return groupBox

    def createExportTools(self):
        groupBox = QGroupBox("Export Tools")

        buttonExportToSpine = QPushButton("Export To Spine")
        buttonExportToSpine.clicked.connect(self.exportToSpine)

        radio1 = QRadioButton("Ignore background")

        radio1.setChecked(True)

        vbox = QVBoxLayout()
        vbox.addWidget(radio1)
        vbox.addWidget(buttonExportToSpine)
        vbox.addStretch(1)
        groupBox.setLayout(vbox)

        return groupBox

    def getSelectedLayers(self):
        window = Krita.instance().activeWindow()
        view = window.activeView()
        selected_nodes = view.selectedNodes()
        selectedLayers = []
        for node in selected_nodes:
            if "selectionmask" in node.type():
                continue
            selectedLayers.insert(0, node)
        if len(selectedLayers) is 0:
            self.alert("No layers selected")
            return
        else:
            return selectedLayers

    def removeTagsFromString(self, string):
        return re.sub(r'\[.*?\]', '', string).strip()

    def createGroupOfType(self, type):
        document = Krita.instance().activeDocument()
        if document is None:
            self.alert('Please select a document')
            return
        selectedLayers = self.getSelectedLayers()
        activeNode = selectedLayers[-1]
        parentNode = activeNode.parentNode()
        groupName = self.removeTagsFromString(activeNode.name())
        groupName += " [" + type + "]"
        groupNode = document.createGroupLayer(groupName)
        parentNode.addChildNode(groupNode, activeNode)
        for layer in selectedLayers:
            _parent = layer.parentNode()
            _parent.removeChildNode(layer)
            groupNode.addChildNode(layer, None)

    def createMergeGroup(self):
        self.createGroupOfType("merge")

    def createBoneGroup(self):
        self.createGroupOfType("bone")

    def createSlotGroup(self):
        self.createGroupOfType("slot")

    def addTag(self, tag):
        document = Krita.instance().activeDocument()
        if document is None:
            self.alert('Please select a document')
            return
        selectedLayers = self.getSelectedLayers()
        activeNode = selectedLayers[-1]
        parentNode = activeNode.parentNode()
        name = self.removeTagsFromString(parentNode.name())
        name += " [" + tag + "]"
        activeNode.setName(name)

    def addAnchorTag(self):
        self.addTag("anchor")

    def addBoneEndTag(self):
        self.addTag("bone_end")

    def getDistance(self, child):
        x1 = child['x']
        y1 = child['y']
        return math.hypot(x1, y1)

    def getAngle(self, child):
        x1 = child['x']
        y1 = child['y']
        angle = math.degrees(math.atan2(y1, x1))
        return angle

    def addRotationAndLengthToBones(self):
        for bone in self.spineBones:
            if bone['name'] != 'root':
                self.addRotationAndLengthToBone(bone)

    def rotateNodePosition(self, node, degrees):
        radians = math.radians(degrees)
        x = node['x']
        y = node['y']
        qx = math.cos(radians) * (x) + math.sin(radians) * (y)
        qy = -math.sin(radians) * (x) + math.cos(radians) * (y)
        node['x'] = qx
        node['y'] = qy

    def addRotationToNode(self, node, rotation):
        if 'rotation' in node:
            node['rotation'] += rotation
        else:
            node['rotation'] = rotation

    def compensateNode(self, node, rotation):
        self.addRotationToNode(node, -rotation)
        self.rotateNodePosition(node, rotation)

    def compensateAttachments(self, bone, rotation):
        for slot in self.spineSlots:
            if slot['bone'] == bone['name']:
                skinSlot = self.spineDefaultSkin[slot['name']]
                for key in skinSlot:
                    self.compensateNode(skinSlot[key], rotation)

    def getChildBones(self, bone):
        children = []
        for child in self.spineBones:
            if child['name'] != 'root':
                if bone['name'] == child['parent']:
                    children.append(child)
        return children

    def findLayerWithNameAndTag(self, node, name, tag):
        if name == self.removeTagsFromString(node.name()) and tag in node.name():
            return node
        if node.childNodes():
            for child in node.childNodes():
                layer = self.findLayerWithNameAndTag(child, name, tag)
                if layer is not None:
                    return layer

    def getBoneLayerWithName(self, name):
        rootNode = self.document.rootNode()
        return self.findLayerWithNameAndTag(rootNode, name, '[bone]')

    def getBoneTarget(self, bone, childBones):
        boneLayer = self.getBoneLayerWithName(bone['name'])
        boneEndLayer = None
        if boneLayer.childNodes():
            for child in boneLayer.childNodes():
                if '[bone_end]' in child.name():
                    boneEndLayer = child
                    break
        if boneEndLayer is not None:
            boneCenter = self.getCenter(boneLayer)
            boneEndCenter = self.getCenter(boneEndLayer)
            return {'x': boneEndCenter['x'] - boneCenter['x'], 'y': boneEndCenter['y'] - boneCenter['y']}
        if len(childBones) > 0:
            return childBones[0]
        return None

    def addRotationAndLengthToBone(self, bone):
        childBones = self.getChildBones(bone)
        target = self.getBoneTarget(bone, childBones)
        if target is not None:
            length = self.getDistance(target)
            bone['length'] = length
            rotation = self.getAngle(target)
            self.addRotationToNode(bone, rotation)
            self.compensateAttachments(bone, rotation)
            for childBone in childBones:
                self.compensateNode(childBone, rotation)

    def getCenter(self, node):
        center = {'x': 0, 'y': 0}
        rect = self.getNodeRect(node)
        center['x'] = rect.left() + rect.width() / 2
        center['y'] = (- rect.bottom() + rect.height() / 2)
        return center

    def getRootOffset(self, node):
        offset = {'x': 0, 'y': 0}
        if node.childNodes():
            for child in node.childNodes():
                if '[root]' in child.name():
                    rect = child.bounds()
                    offset['x'] = rect.left() + rect.width() / 2
                    offset['y'] = (- rect.bottom() + rect.height() / 2)
        return offset

    def saveJson(self, content, name):
        if name is None:
            name = 'spine.json'
        with open('{0}/{1}'.format(self.directory, name), 'w') as jsonFile:
            json.dump(content, jsonFile, indent=2)
        self.alert("Export Successful")

    def exportToSpine(self):
        document = Krita.instance().activeDocument()

        if document is None:
            self.alert("Please select a Document")
        else:
            if not self.directory:
                self.directory = os.path.dirname(
                    document.fileName()) if document.fileName() else os.path.expanduser("~")

            self.directory = QFileDialog.getExistingDirectory(
                None, "Select a folder", self.directory, QFileDialog.ShowDirsOnly)

            if not self.directory:
                self.alert('Abort!')
                return

            self.json = {
                "skeleton": {"images": self.directory},
                "bones": [{"name": "root"}],
                "slots": [],
                "skins": {"default": {}},
                "animations": {}
            }
            self.spineBones = self.json['bones']
            self.spineSlots = self.json['slots']
            self.spineDefaultSkin = self.json['skins']['default']

            Krita.instance().setBatchmode(True)
            self.document = document
            documentRootNode = document.rootNode()
            rootOffset = self.getRootOffset(documentRootNode)
            self.exportNode(documentRootNode, self.directory,
                            "root", rootOffset['x'], rootOffset['y'])
            Krita.instance().setBatchmode(False)
            self.addRotationAndLengthToBones()
            self.saveJson(self.json, None)

    def alert(self, message):
        output = ''
        if isinstance(message, str):
            output = message
        elif isinstance(message, list):
            for item in message:
                output += json.dumps(item)
        else:
            output = json.dumps(message)
        self.msgBox = self.msgBox if self.msgBox else QMessageBox()
        self.msgBox.setText(output)
        self.msgBox.exec_()

    def getBoneColor(self, node):
        name = node.name()
        if name.startswith('front_'):
            return '00ff04ff'
        if name.startswith('rear_'):
            return 'ff000dff'
        return 'e0da19ff'

    def appendBone(self, bone, parent, x, y, color):
        self.spineBones.append({
            'name': bone,
            'parent': parent,
            'x': x,
            'y': y,
            'color': color
        })

    def getNodeRect(self, node):
        anchorNode = node
        if node.childNodes():
            for child in node.childNodes():
                if '[anchor]' in child.name():
                    anchorNode = child
        rect = anchorNode.bounds()
        return rect

    def exportBone(self, node, directory, parent, xOffset, yOffset, slot):
        bone = self.bonePattern.sub('', node.name()).strip()
        rect = self.getNodeRect(node)
        x = rect.left() + rect.width() / 2 - xOffset
        y = (- rect.bottom() + rect.height() / 2) - yOffset
        color = self.getBoneColor(node)
        self.appendBone(bone, parent, x, y, color)
        xOffset += x
        yOffset += y
        self.exportNode(node, directory, bone, xOffset, yOffset, slot)

    def exportSlot(self, node, directory, bone, xOffset, yOffset):
        name = self.slotPattern.sub('', node.name()).strip()
        slot = {
            'name': name,
            'bone': bone,
            'attachment': None,
        }
        self.spineSlots.append(slot)
        self.exportNode(node, directory, bone, xOffset, yOffset, slot)

    def getName(self, node):
        return self.mergePattern.sub('', node.name()).strip()

    def saveNodeToImage(self, node, name, directory):
        layerFileName = '{0}/{1}.{2}'.format(directory, name, self.fileFormat)
        node.save(layerFileName, 96, 96)

    def addNodeToSkin(self, node, slot, name, xOffset, yOffset):
        rect = node.bounds()
        slotName = slot['name']
        if slotName not in self.spineDefaultSkin:
            self.spineDefaultSkin[slotName] = {}
            self.spineDefaultSkin[slotName][name] = {
                'x': rect.left() + rect.width() / 2 - xOffset,
                'y': (- rect.bottom() + rect.height() / 2) - yOffset,
                'rotation': 0,
                'width': rect.width(),
                'height': rect.height(),
            }

    def ignoreNode(self, node):
        if "selectionmask" in node.type():
            return True
        if not node.visible():
            return True
        if '[ignore]' in node.name():
            return True
        if '[anchor]' in node.name():
            return True
        if '[root]' in node.name():
            return True
        if '[bone_end]' in node.name():
            return True
        return False

    def exportAttachment(self, child, slot, name, bone, xOffset, yOffset):
        _slot = slot
        if _slot is None:
            _slot = {
                'name': name,
                'bone': bone,
                'attachment': name,
            }
            self.spineSlots.append(_slot)
        else:
            if not _slot['attachment']:
                _slot['attachment'] = name

        self.addNodeToSkin(child, _slot, name, xOffset, yOffset)

    def exportNode(self, node, directory, bone="root", xOffset=0, yOffset=0, slot=None):
        for child in node.childNodes():
            if self.ignoreNode(child):
                continue

            if child.childNodes():
                if self.bonePattern.search(child.name()):
                    self.exportBone(child, directory, bone,
                                    xOffset, yOffset, slot)
                    continue
                if self.slotPattern.search(child.name()):
                    self.exportSlot(child, directory, bone, xOffset, yOffset)
                    continue

            name = self.getName(child)
            self.saveNodeToImage(child, name, directory)

            self.exportAttachment(child, slot, name, bone, xOffset, yOffset)


Krita.instance().addDockWidgetFactory(DockWidgetFactory(
    "spineTools", DockWidgetFactoryBase.DockRight, SpineTools))
