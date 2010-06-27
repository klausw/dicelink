class Error(Exception):
  def __init__(self, msg):
    self.msg = msg
  def __str__(self):
    return 'CharstoreError: ' + self.msg

class PermissionError(Error):
  def __init__(self, msg):
    self.msg = msg
  def __str__(self):
    return 'PermissionError: ' + self.msg

class AppengineError(Error):
  def __init__(self, msg):
    self.msg = msg
  def __str__(self):
    return 'AppengineError: ' + self.msg

# All values must be strings, use repr() serialized format
WAVE_CONFIG_DEFAULT = {
  'inline': 'True' # expand inline XdY+Z rolls without []
}

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

  def getconfig(self):
    return WAVE_CONFIG_DEFAULT.copy()

  def setconfig(self, config):
    return

  def list(self, name):
    return []

  def clear(self, name):
    return []

  def waveid(self, unused_dummy):
    return []

class InMemoryCharStore(CharStore):
  def __init__(self):
    self.characters = {}
    self.config = WAVE_CONFIG_DEFAULT.copy()
    self.default = None

  def get(self, name, altcontext=None, key=None):
    return self.characters.get(name, None)

  def put(self, sheet):
    self.characters[sheet.name] = sheet

  def getdefault(self):
    return self.default

  def setdefault(self, name):
    self.default = name

  def getconfig(self):
    return self.config

  def setconfig(self, config):
    self.config = config

  def clear(self, name):
    if name in self.characters:
      del self.characters[name]
      return [(['cleared: 1'], None)]
    else:
      return [(['cleared: 0'], None)]
