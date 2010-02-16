class PermissionError(Exception):
  def __init__(self, msg):
    self.msg = msg
  def __str__(self):
    return 'PermissionError: ' + self.msg

class CharStore(object):
  def __init__(self):
    pass

  def get(self, name, altcontext=None, key=None):
    return None

  def put(self, sheet):
    return

  def getdefault(self):
    return None

  def setdefault(self, name):
    return

  def list(self, name):
    return []

  def clear(self, name):
    return

  def waveid(self, unused_dummy):
    return None

class InMemoryCharStore(CharStore):
  def __init__(self):
    self.characters = {}
    self.default = None

  def get(self, name, altcontext=None, key=None):
    return self.characters.get(name, None)

  def put(self, sheet):
    self.characters[sheet.name] = sheet

  def getdefault(self):
    return self.default

  def setdefault(self, name):
    self.default = name
