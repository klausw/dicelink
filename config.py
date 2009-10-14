config = {
  'Name': 'dicelink',
}

def getConfig(item, default):
  return config.get(item, default)
