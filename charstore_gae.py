import charstore
import charsheet
import persist
import logging

def DeleteCharactersInBlip(waveId, waveletId, blipId):
  persist.DeleteCharacterBlip(waveId, waveletId, blipId)

class GaeCharStore(charstore.CharStore):
  def __init__(self, creator, modifier, waveId, waveletId, blipId):
    self.creator = creator
    self.modifier = modifier
    self.waveId = waveId
    self.waveletId = waveletId
    self.blipId = blipId

  def get(self, name, altcontext=None, key=None):
    fromWave = self.waveId
    if altcontext is not None:
      fromWave = altcontext
    sheet_txt = persist.GetCharacter(name, self.modifier, fromWave, self.waveletId)
    if not sheet_txt:
      sheet_txt = persist.GetSheet(name) # backwards compatible
    if not sheet_txt:
      return None
    sheet = charsheet.CharSheet(sheet_txt)
    if fromWave != self.waveId:
      # Privacy/security check: permissions for other-Wave characters?
      perms = sheet.dict.get('_access')
      #logging.info('perms=%s, key=%s', repr(perms), repr(key))
      if perms is None or (perms.lower() != 'public' and perms != key):
	return None
    return sheet

  def put(self, sheet):
    name = sheet.name
    persist.SaveCharacter(name, self.creator, self.waveId, self.waveletId, self.blipId, sheet.__str__())
    #if blipId:
    #  SetTextOfBlip(context, waveId, waveletId, blipId, sheet.__str__())

  def getdefault(self):
    return persist.GetDefaultChar(self.modifier)

  def setdefault(self, name):
    return persist.SetDefaultChar(self.modifier, name)

  def list(self, name):
    out = []
    def show(txt, *attrs):
      if not attrs:
	attrs = [('style/color', '#444444')]
      msg = [txt] + list(attrs)
      out.append((msg, None))

    chars = list(persist.FindCharacter(name, self.modifier, self.waveId, self.waveletId))
    if not chars:
      show('no matches for "%s"' % name, ('style/color', 'red'))
    for idx, char in enumerate(chars):
      if char.owner == self.modifier:
	show('\nowned by you, ')
      else:
	show('owner %s, ' % char.owner)
      date = char.date
      if date:
	show('updated %s UTC, ' % char.date.replace(microsecond=0))
      else:
	show('no date, please update or clear this character, ', ('style/color', 'red'))
      show('size=%d, ' % len(char.text))
      if idx == 0:
	show('active, ', ('style/fontWeight', 'bold'))
      if char.wave == self.waveId:
	show('this wave, ')
      else:
	show('wave ')
	# FIXME: other wave instances?
	url = 'https://wave.google.com/wave/#restored:wave:' + char.wave.replace('+', '%252B')
	show(char.wave, ('link/manual', url))
	show(', ')
      if char.wave == self.waveId and char.wavelet == self.waveletId:
	show('this wavelet')
      elif '!conv+root' in char.wavelet:
	show('root wavelet')
      else:
	show('wavelet %s' % char.wavelet)
    return out

  def clear(self, name):
    msg = persist.ClearCharacterForOwner(name, self.modifier)
    return [([msg, ('style/color', '#777777')], msg)]
