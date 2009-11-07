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

def OnBlipSubmitted(properties, context):
  """Invoked when a blip was submitted."""
  blipId = properties['blipId']
  blip = context.GetBlipById(blipId)
  waveId = blip.GetWaveId()
  waveletId = blip.GetWaveletId()
  creator = blip.GetCreator()
  modifier = properties.get('modifiedBy', creator) # hacked waveapi
  doc = blip.GetDocument()
  txt = doc.GetText()

  logging.info('%s %s %s %s %s' % (waveId, modifier, len(txt), blipId, waveletId))

  def WaveCharacterSaver(sheet):
    name = sheet.name
    #logging.debug('WaveCharacterSaver: name="%s" blipId=%s', name, blipId)
    persist.SaveCharacter(name, creator, waveId, waveletId, blipId, str(sheet))
    #if blipId:
    #  SetTextOfBlip(context, waveId, waveletId, blipId, str(sheet))

  def WaveCharacterGetter(name):
    logging.debug('WaveCharacterGetter: name="%s"', name)
    sheet_txt = persist.GetCharacter(name, creator, waveId)
    if not sheet_txt:
      sheet_txt = persist.GetSheet(name) # backwards compatible
    if sheet_txt:
      return charsheet.CharSheet(sheet_txt)
    else:
      return None
      
  # FIXME: not thread safe? Use charsheet factory, or just factor out load/save better?
  charsheet.SetCharacterAccessors(WaveCharacterGetter, WaveCharacterSaver)

  # update info from character sheets if present - currently disabled
  if 'dicelink: Status' in txt:
    #persist.SaveBlipMap('Status', blip.GetWaveId(), blip.GetWaveletId(), blip.GetId())
    pass
  elif charsheet.isCharSheet(txt):
    char = charsheet.CharSheet(txt)
    if char:
      logging.info('save char sheet, name="%s", keys=%d, bytes=%d', char.name, len(char.dict), len(txt))
      char.save()
      persist.SetDefaultChar(creator, char.name)
      #SetStatus(context, 'Updated character %s' % char.name)
  elif '[' in txt:
    if modifier != creator:
      logging.info('Not evaluating, modifier "%s" != creator "%s"' % (modifier, creator))
      return
    def replacer(start, end, texts):
      return SetTextWithAttributes(doc, start, end, texts)
    def defaultgetter():
      return persist.GetDefaultChar(creator)
    controller.handle_text(txt, defaultgetter, replacer)
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
      #out_private.append('%s rolled %s: %d [%s]' % (creator, spec['spec'], num, detail))
      #persist.SaveMsg(creator, 'rolled %s: %d [%s]' % (spec['spec'], num, detail))

  #doc.GadgetSubmitDelta(document.Gadget(GADGET_URL), {'count': num})
