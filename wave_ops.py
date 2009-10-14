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

def OnRobotAdded(properties, context):
  """Invoked when the robot has been added."""
  root_wavelet = context.GetRootWavelet()
  blip = root_wavelet.CreateBlip()
  doc = blip.GetDocument()
  doc.SetText('DiceLink joined.')

  #counter = document.Gadget(GADGET_URL)
  #doc.AppendElement(counter)

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
    text = lst[0]
    for anno, val in lst[1:]:
      doc.SetAnnotation(document.Range(start, start+len(text)), anno, val)
    start += len(text)
  return len(new_text) - old_len

# End expression on end of line, or punctuation other than ','
EXPR_RE = re.compile(r'((?: [A-Z] \w* \s*)+) : \s* ([^.;:?!]+)', re.X)

def OnBlipSubmitted(properties, context):
  """Invoked when a blip was submitted."""
  blip = context.GetBlipById(properties['blipId'])
  creator = blip.GetCreator()
  doc = blip.GetDocument()
  txt = doc.GetText()

  def WaveCharacterSaver(sheet):
    name = sheet.name
    waveId, waveletId, blipId = GetBlipMapId('char_%s' % name)
    logging.debug('WaveCharacterSaver: name="%s" blipId=%s', name, blipId)
    persist.SaveSheet(name, str(sheet))
    if blipId:
      SetTextOfBlip(context, waveId, waveletId, blipId, str(sheet))

  def WaveCharacterGetter(name):
    logging.debug('WaveCharacterGetter: name="%s"', name)
    sheet_txt = persist.GetSheet(name)
    if sheet_txt:
      return charsheet.CharSheet(sheet_txt)
    else:
      return None
      
  charsheet.SetCharacterAccessors(WaveCharacterGetter, WaveCharacterSaver)
  # update info from character sheets if present
  if 'dicelink: Status' in txt:
    persist.SaveBlipMap('Status', blip.GetWaveId(), blip.GetWaveletId(), blip.GetId())
  elif charsheet.isCharSheet(txt):
    logging.debug('save char sheet, txt=%s, id=%s', txt, blip.GetId())
    char = charsheet.CharSheet(txt)
    persist.SaveBlipMap('char_%s' % char.name, blip.GetWaveId(), blip.GetWaveletId(), blip.GetId())
    persist.SaveSheet(char.name, str(char))
    SetStatus(context, 'Updated character %s' % char.name)
  elif ':' in txt:
    for m in EXPR_RE.finditer(txt):
      out_lst = []
      try:
        char = charsheet.GetChar(m.group(1))
	if char:
	  sym = char.dict
	else:
	  sym = {}
	env = {
	  'opt_nat20': True,
	  'opt_crit_notify': sym.get('CritNotify', 20),
	}
        for result in eval.ParseExpr(m.group(2), sym, env):
	  if out_lst:
	    out_lst.append([', '])
	  if 'Secret' in sym:
	    out_lst.append([result.secretval(), ('style/fontWeight', 'bold')])
	  else:
	    out_lst.append(['%s=' % result.detail(), ('style/color', '#aa00ff')])
	    out_lst.append([result.publicval(), ('style/fontWeight', 'bold')])
      except eval.ParseError, e:
        out_lst.append([str(e), ('style/color', 'red')])
      if out_lst:
	out_lst = [' '] + out_lst + [' ']
	SetTextWithAttributes(doc, len(txt), len(txt), out_lst)
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
	[' ['],
	[detail, ('style/color', 'gray')],
	[']'],
      ])
      #out_private.append('%s rolled %s: %d [%s]' % (creator, spec['spec'], num, detail))
      #persist.SaveMsg(creator, 'rolled %s: %d [%s]' % (spec['spec'], num, detail))

  #doc.GadgetSubmitDelta(document.Gadget(GADGET_URL), {'count': num})
