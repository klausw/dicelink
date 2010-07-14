# Copyright 2009, 2010 Klaus Weidner <klausw@google.com>
# 
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
# 
#        http://www.apache.org/licenses/LICENSE-2.0
# 
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import charstore
import charsheet
import persist
import logging

import google.appengine.runtime.apiproxy_errors

def DeleteCharactersInBlip(waveId, waveletId, blipId):
  try:
    persist.DeleteCharacterBlip(waveId, waveletId, blipId)
  except google.appengine.runtime.apiproxy_errors.Error, e:
    raise charstore.AppengineError(str(e))
    

class GaeCharStore(charstore.CharStore):
  def __init__(self, creator, modifier, waveId, waveletId, blipId):
    self.creator = creator
    self.modifier = modifier
    self.waveId = waveId
    self.waveletId = waveletId
    self.blipId = blipId

  def get(self, name, altcontext=None, key=None):
    try:
      fromWave = self.waveId
      if altcontext is not None:
	fromWave = altcontext
      sheet_txt, foundWave, foundOwner = persist.GetCharacter(name, self.modifier, fromWave, self.waveletId)

      if not sheet_txt:
	return None
      sheet = charsheet.CharSheet(sheet_txt)
      if foundWave != self.waveId and foundOwner != self.modifier:
	# Privacy/security check: permissions for other-Wave characters?
	perms = sheet.dict.get('_access')
	#logging.info('perms=%s, key=%s', repr(perms), repr(key))
	if perms is None:
	  raise charstore.PermissionError('Sheet "%s" exists but is not public, add "_access: public" to the sheet blip to share it.' % name)
	if perms.lower() != 'public':
	  if key is None:
	    raise charstore.PermissionError('Sheet "%s" is password protected. Change "@%s" to "@%s=PASSWORD" in the _template line.' % (name, fromWave, fromWave))
	  if key != perms:
	    raise charstore.PermissionError('Sheet "%s" is password protected, the supplied password is incorrect.' % name)
      return sheet
    except google.appengine.runtime.apiproxy_errors.Error, e:
      raise charstore.AppengineError(str(e))

  def put(self, sheet):
    try:
      name = sheet.name
      persist.SaveCharacter(name, self.creator, self.waveId, self.waveletId, self.blipId, sheet.__str__())
      #if blipId:
      #  SetTextOfBlip(context, waveId, waveletId, blipId, sheet.__str__())
    except google.appengine.runtime.apiproxy_errors.Error, e:
      raise charstore.AppengineError(str(e))

  def getdefault(self):
    return persist.GetDefaultChar(self.modifier)

  def setdefault(self, name):
    try:
      return persist.SetDefaultChar(self.modifier, name)
    except google.appengine.runtime.apiproxy_errors.Error, e:
      raise charstore.AppengineError(str(e))

  def getconfig(self):
    return persist.GetConfig(self.waveId, charstore.WAVE_CONFIG_DEFAULT)

  def setconfig(self, config):
    return persist.SaveConfig(self.waveId, config)
  
  def list(self, name):
    out = []
    def show(txt, *attrs):
      if not attrs:
	attrs = [('style/color', '#444444')]
      msg = [txt] + list(attrs)
      out.append((msg, None))

    try:
      chars = list(persist.FindCharacter(name, self.modifier, self.waveId, self.waveletId))
    except google.appengine.runtime.apiproxy_errors.Error, e:
      raise charstore.AppengineError(str(e))

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
    try:
      msg = persist.ClearCharacterForOwner(name, self.modifier)
    except google.appengine.runtime.apiproxy_errors.Error, e:
      raise charstore.AppengineError(str(e))
    return [([msg, ('style/color', '#777777')], msg)]

  def waveid(self, unused_dummy):
    msg = ' @%s ' % (self.waveId)
    return [([msg], msg)]
