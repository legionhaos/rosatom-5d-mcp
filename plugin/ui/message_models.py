"""Qt models exposed by the STE Slicer AI Assistant UI.

The models deliberately contain presentation data only. Agent, MCP and slicer
logic stays outside the UI layer and feeds these models through the controller.
The code is compatible with the Python version shipped with Cura 3.6.
"""

try:
    from PyQt5.QtCore import QAbstractListModel, QModelIndex, Qt, pyqtSignal, pyqtSlot
except ImportError:
    try:
        from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, pyqtSignal, pyqtSlot
    except ImportError:
        try:
            from PySide2.QtCore import QAbstractListModel, QModelIndex, Qt, Signal as pyqtSignal, Slot as pyqtSlot
        except ImportError:
            try:
                from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Signal as pyqtSignal, Slot as pyqtSlot
            except ImportError:
                class QModelIndex(object):
                    def isValid(self):
                        return False
                    def row(self):
                        return 0

                class Qt(object):
                    UserRole = 256
                    DisplayRole = 0

                def pyqtSlot(*args, **kwargs):
                    def _dec(f):
                        return f
                    return _dec

                class pyqtSignal(object):
                    def __init__(self, *types):
                        pass
                    def emit(self, *args):
                        pass
                    def connect(self, slot):
                        pass

                class QAbstractListModel(object):
                    def __init__(self, parent=None):
                        self.parent = parent
                    def beginInsertRows(self, index, first, last):
                        pass
                    def endInsertRows(self):
                        pass
                    def beginRemoveRows(self, index, first, last):
                        pass
                    def endRemoveRows(self):
                        pass
                    def beginResetModel(self):
                        pass
                    def endResetModel(self):
                        pass
                    def dataChanged(self, top_left, bottom_right, roles=None):
                        pass
                    dataChanged = pyqtSignal()



class _ListModel(QAbstractListModel):
    """Small append/update model suitable for QtQuick 2.x ListView."""

    _roles = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._items)

    def roleNames(self):
        return dict((role, name.encode("utf-8")) for name, role in self._roles.items())

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        for name, item_role in self._roles.items():
            if role == item_role:
                return item.get(name, "")
        return None

    def _append(self, item):
        position = len(self._items)
        self.beginInsertRows(QModelIndex(), position, position)
        self._items.append(dict(item))
        self.endInsertRows()
        return position

    def _update(self, row, values):
        if row < 0 or row >= len(self._items):
            return False
        self._items[row].update(values)
        top_left = self.index(row, 0)
        self.dataChanged.emit(top_left, top_left, list(self._roles.values()))
        return True

    @pyqtSlot()
    def clear(self):
        if not self._items:
            return
        self.beginResetModel()
        self._items = []
        self.endResetModel()


class MessageListModel(_ListModel):
    """Conversation messages: user, assistant, system and tool_trace."""

    _roles = {
        "kind": Qt.UserRole + 1,
        "text": Qt.UserRole + 2,
        "timestamp": Qt.UserRole + 3,
        "status": Qt.UserRole + 4,
        "toolName": Qt.UserRole + 5,
        "toolArguments": Qt.UserRole + 6,
        "toolResult": Qt.UserRole + 7,
        "durationMs": Qt.UserRole + 8,
        "attachmentCount": Qt.UserRole + 9,
    }

    def append_user(self, text, timestamp="", attachment_count=0):
        return self._append({
            "kind": "user",
            "text": text,
            "timestamp": timestamp,
            "status": "complete",
            "toolName": "",
            "toolArguments": "",
            "toolResult": "",
            "durationMs": 0,
            "attachmentCount": attachment_count,
        })

    def append_assistant(self, text, timestamp="", status="complete"):
        return self._append({
            "kind": "assistant",
            "text": text,
            "timestamp": timestamp,
            "status": status,
            "toolName": "",
            "toolArguments": "",
            "toolResult": "",
            "durationMs": 0,
            "attachmentCount": 0,
        })

    def append_system(self, text, timestamp="", status="info"):
        return self._append({
            "kind": "system",
            "text": text,
            "timestamp": timestamp,
            "status": status,
            "toolName": "",
            "toolArguments": "",
            "toolResult": "",
            "durationMs": 0,
            "attachmentCount": 0,
        })

    def append_tool(self, tool_name, text, arguments="", result="", status="pending", duration_ms=0):
        return self._append({
            "kind": "tool_trace",
            "text": text,
            "timestamp": "",
            "status": status,
            "toolName": tool_name,
            "toolArguments": arguments,
            "toolResult": result,
            "durationMs": duration_ms,
            "attachmentCount": 0,
        })


class AttachmentListModel(_ListModel):
    _roles = {
        "name": Qt.UserRole + 1,
        "path": Qt.UserRole + 2,
        "kind": Qt.UserRole + 3,
        "sizeText": Qt.UserRole + 4,
        "status": Qt.UserRole + 5,
    }

    def append_file(self, name, path, kind, size_text="", status="ready"):
        return self._append({
            "name": name,
            "path": path,
            "kind": kind,
            "sizeText": size_text,
            "status": status,
        })

    def remove_at(self, row):
        if row < 0 or row >= len(self._items):
            return None
        self.beginRemoveRows(QModelIndex(), row, row)
        item = self._items.pop(row)
        self.endRemoveRows()
        return item

    def paths(self):
        return [item.get("path", "") for item in self._items]


class ToolLogModel(_ListModel):
    _roles = {
        "toolName": Qt.UserRole + 1,
        "label": Qt.UserRole + 2,
        "status": Qt.UserRole + 3,
        "arguments": Qt.UserRole + 4,
        "result": Qt.UserRole + 5,
        "durationMs": Qt.UserRole + 6,
    }

    def append_call(self, tool_name, label, arguments="", status="pending"):
        return self._append({
            "toolName": tool_name,
            "label": label,
            "status": status,
            "arguments": arguments,
            "result": "",
            "durationMs": 0,
        })

    def finish_call(self, row, status, result="", duration_ms=0):
        return self._update(row, {
            "status": status,
            "result": result,
            "durationMs": duration_ms,
        })
