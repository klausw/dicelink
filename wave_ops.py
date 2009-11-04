import logging
import re

from waveapi import document
from waveapi import model
from waveapi import ops

import charsheet
import config
import eval
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
  doc = blip.GetDocument()
  txt = doc.GetText()

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
      
  charsheet.SetCharacterAccessors(WaveCharacterGetter, WaveCharacterSaver)
  # update info from character sheets if present - currently disabled
  if 'dicelink: Status' in txt:
    #persist.SaveBlipMap('Status', blip.GetWaveId(), blip.GetWaveletId(), blip.GetId())
    pass
  elif charsheet.isCharSheet(txt):
    logging.debug('save char sheet, txt=%s, id=%s', txt, blip.GetId())
    char = charsheet.CharSheet(txt)
    if char:
      char.save()
      persist.SetDefaultChar(creator, char.name)
      SetStatus(context, 'Updated character %s' % char.name)
  elif '[' in txt:
    offset = 0
    for m in EXPR_RE.finditer(txt):
      if '=' in m.group(2) or 'ParseError' in m.group():
        continue
      out_lst = []
      char = None
      charname = None
      if m.group(1):
	charname = m.group(1)
      else:
	charname = persist.GetDefaultChar(creator)
      if charname:
	char = charsheet.GetChar(charname)
	if not char:
	  out_lst.append(['"%s" not found' % charname, ('style/color', 'red')])

      if char:
	sym = char.dict
      else:
	sym = {}
      env = {
	'opt_nat20': True,
	'opt_crit_notify': sym.get('CritNotify', 20),
      }
      try:
        logging.debug('eval: char="%s", expr="%s"', charname, m.group(2))
        for result in eval.ParseExpr(m.group(2), sym, env):
	  if out_lst:
	    out_lst.append([', '])
	  if 'Secret' in sym:
	    out_lst.append(['='])
	    out_lst.append([result.secretval(), ('style/fontWeight', 'bold')])
	  else:
	    out_lst.append([result.detail()+'=', ('style/color', '#aa00ff')])
	    out_lst.append([result.publicval(), ('style/fontWeight', 'bold')])
      except eval.ParseError, e:
        out_lst.append([str(e), ('style/color', 'red')])
      if out_lst:
	if char and not m.group(1):
	  offset += SetTextWithAttributes(doc, m.start()+1+offset, m.start()+1+offset,
	    [[char.name + ':']])
	out_lst = [[' ']] + out_lst
	offset += SetTextWithAttributes(doc, m.end(2)+offset, m.end(2)+offset, out_lst)
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
