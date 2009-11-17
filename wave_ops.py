import logging
import re

from waveapi import document
from waveapi import model
from waveapi import ops

import charsheet
import controller
import config
import persist
import roll

#GADGET_URL='http://dicelink.appspot.com/static/counter.xml'

def GetBlipMapId(name):
  data = persist.GetBlipMap(name)
  logging.debug('GetBlipMapId: name="%s" data=%s' % (name, data))
  return data

def SetTextOfBlip(context, waveId, waveletId, blipId, text):
  context.builder.DocumentDelete(waveId, waveletId, blipId)
  context.builder.DocumentInsert(waveId, waveletId, blipId, text)

def SetStatus(context, msg):
  waveId, waveletId, blipId = GetBlipMapId('Status')
  if blipId:
    SetTextOfBlip(context, waveId, waveletId, blipId, msg)

def SetTextWithAttributes(doc, start, end, texts):
  old_len = end - start 
  new_text = ''.join([p[0] for p in texts])
  doc.SetTextInRange(document.Range(start, end), new_text)
  for lst in texts:
    len_text = len(lst[0])
    for anno, val in lst[1:]:
      doc.SetAnnotation(document.Range(start, start+len_text), anno, val)
    start += len_text
  return len(new_text) - old_len

EXPR_RE = re.compile(r'''
  \[
  (?: 
    ([^]:]*)
  : \s* )?
  ([^]]*)
  \]
  ''', re.X)

def OnRobotAdded(properties, context):
  """Invoked when the robot has been added."""
  root_wavelet = context.GetRootWavelet()
  blip = root_wavelet.CreateBlip()
  doc = blip.GetDocument()
  SetTextWithAttributes(doc, 0, 0, [
	  ['DiceLink joined. '],
	  ['Privacy policy, Help', ('link/manual', 'https://wave.google.com/wave/#restored:wave:googlewave.com!w%252BeDRGxAAiN')],
  ])

  #counter = document.Gadget(GADGET_URL)
  #doc.AppendElement(counter)

def OnBlipDeleted(properties, context):
  """Invoked when a blip was deleted."""
  blipId = properties['blipId']
  wavelets = context.GetWavelets()
  if not wavelets:
    logging.warning('OnBlipDeleted: no wavelets in context')
    return
  if len(wavelets) > 1:
    logging.warning('OnBlipDeleted: more than one wavelet in context')
    return
  waveletId = wavelets[0].GetId()
  waveId = wavelets[0].GetWaveId()

  persist.DeleteCharacterBlip(waveId, waveletId, blipId)

def OnBlipSubmitted(properties, context):
  """Invoked when a blip was submitted."""
  blipId = properties['blipId']
  blip = context.GetBlipById(blipId)
  if not blip:
    logging.warning('Blip "%s" not found in context: %s' % (blipId, repr(context)))
    return
  waveId = blip.GetWaveId()
  waveletId = blip.GetWaveletId()
  creator = blip.GetCreator()
  modifier = properties.get('modifiedBy')
  if not modifier:
    logging.warning('No "modifiedBy" property available, using creator. FIXME!')
    modifier = creator
  doc = blip.GetDocument()
  txt = doc.GetText()

  logging.info('%s %s %s %s %s' % (waveId, modifier, len(txt), blipId, waveletId))

  def WaveCharacterSaver(sheet):
    name = sheet.name
    #logging.debug('WaveCharacterSaver: name="%s" blipId=%s', name, blipId)
    persist.SaveCharacter(name, creator, waveId, waveletId, blipId, sheet.__str__())
    #if blipId:
    #  SetTextOfBlip(context, waveId, waveletId, blipId, sheet.__str__())

  def WaveCharacterGetter(name):
    logging.debug('WaveCharacterGetter: name="%s"', name)
    sheet_txt = persist.GetCharacter(name, modifier, waveId, waveletId)
    if not sheet_txt:
      sheet_txt = persist.GetSheet(name) # backwards compatible
    if sheet_txt:
      return charsheet.CharSheet(sheet_txt)
    else:
      return None

  def WaveCharacterLister(name):
    out = []
    logging.debug('called lister')
    def show(txt, *attrs):
      if not attrs:
	attrs = [('style/color', '#444444')]
      msg = [txt] + list(attrs)
      out.append((msg, None))

    chars = list(persist.FindCharacter(name, modifier, waveId, waveletId))
    if not chars:
      show('no matches for "%s"' % name, ('style/color', 'red'))
    for idx, char in enumerate(chars):
      if char.owner == modifier:
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
      if char.wave == waveId:
	show('this wave, ')
      else:
	show('wave ')
	# FIXME: other wave instances?
	url = 'https://wave.google.com/wave/#restored:wave:' + char.wave.replace('+', '%252B')
	show(char.wave, ('link/manual', url))
	show(', ')
      if char.wave == waveId and char.wavelet == waveletId:
	show('this wavelet')
      elif '!conv+root' in char.wavelet:
	show('root wavelet')
      else:
	show('wavelet %s' % char.wavelet)
    return out

  def WaveCharacterClearer(name):
    msg = persist.ClearCharacterForOwner(name, modifier)
    return [([msg, ('style/color', '#777777')], msg)]
      
  # FIXME: not thread safe? Use charsheet factory, or just factor out load/save better?
  storage = charsheet.CharacterAccessor(WaveCharacterGetter, WaveCharacterSaver)
  storage.add_special('list', WaveCharacterLister)
  storage.add_special('clear', WaveCharacterClearer)

  # update info from character sheets if present - currently disabled
  if 'dicelink: Status' in txt:
    #persist.SaveBlipMap('Status', blip.GetWaveId(), blip.GetWaveletId(), blip.GetId())
    pass
  elif charsheet.isCharSheet(txt):
    char = charsheet.CharSheet(txt)
    if char:
      logging.info('save char sheet, name="%s", keys=%d, bytes=%d', char.name, len(char.dict), len(txt))
      char.save(storage)
      persist.SetDefaultChar(modifier, char.name)
      #SetStatus(context, 'Updated character %s' % char.name)
  elif '[' in txt:
    def replacer(start, end, texts):
      return SetTextWithAttributes(doc, start, end, texts)
    def defaultgetter():
      return persist.GetDefaultChar(modifier)
    def defaultsetter(name):
      return persist.SetDefaultChar(modifier, name)
    controller.handle_text(txt, defaultgetter, defaultsetter, replacer, storage)
#  elif ':' in txt:
#    logging.debug('interact: %s' % txt)
#    out_public, out_private = charsheet.Interact(txt)
#    logging.debug('interaction result: %s', (out_public, out_private))
#    status_wave, status_wavelet, status_blip = GetBlipMapId('Status')
#
#    if out_private:
#      priv_root_wavelet = context.GetRootWavelet()
#      priv_blip = priv_root_wavelet.CreateBlip()
#      priv_blip.GetDocument().SetText(out_private)
#
#    # suppress public output if we'd send both public and private to
#    # the same wave.
#    if out_public and out_private and (status_wave == blip.GetWaveId() or not status_wave):
#      out_public = None
#
#    if out_public:
#      if status_wave:
#	blip_data = context.builder.WaveletAppendBlip(status_wave, status_wavelet)
#	blip = ops.OpBasedBlip(blip_data, context)
#	context.blips[blip.GetId()] = blip
#      else:
#	root_wavelet = context.GetRootWavelet()
#	blip = root_wavelet.CreateBlip()
#       blip.GetDocument().SetText(out_public)
#
  else:
    offset = 0
    for spec in roll.GetRollMatches(txt):
      num, detail = roll.RollDice(spec)
      logging.info('inline: %s=%s (%s)', spec['spec'], num, detail)
      match_start = spec['start'] + offset
      match_end = spec['end'] + offset
      offset += SetTextWithAttributes(doc, match_start, match_end, [
	[spec['spec'], ('style/color', '#aa00ff')],
	['=%d' % num, ('style/fontWeight', 'bold')],
	[' ('],
	[detail, ('style/color', 'gray')],
	[')'],
      ])
      #out_private.append('%s rolled %s: %d [%s]' % (modifier, spec['spec'], num, detail))
      #persist.SaveMsg(modifier, 'rolled %s: %d [%s]' % (spec['spec'], num, detail))

  #doc.GadgetSubmitDelta(document.Gadget(GADGET_URL), {'count': num})
