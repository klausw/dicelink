import logging
import re

from waveapi import document
from waveapi import model
from waveapi import ops

import controller
import config
import charstore_gae
import dicelink # for canonical_campaign only, FIXME

#GADGET_URL='http://dicelink.appspot.com/static/counter.xml'

def SetTextOfBlip(context, waveId, waveletId, blipId, text):
  context.builder.DocumentDelete(waveId, waveletId, blipId)
  context.builder.DocumentInsert(waveId, waveletId, blipId, text)

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

def OnRobotAdded(properties, context):
  """Invoked when the robot has been added."""
  root_wavelet = context.GetRootWavelet()
  if not root_wavelet:
    logging.warning("can't create welcome blip, no root_wavelet")
    logging.info('properties: %s', repr(properties))
    logging.info('context: %s', repr(context))
    return
  blip = root_wavelet.CreateBlip()
  doc = blip.GetDocument()
  SetTextWithAttributes(doc, 0, 0, [
	  ['DiceLink joined. '],
	  ['Privacy policy, Help', ('link/manual', 'https://wave.google.com/wave/#restored:wave:googlewave.com!w%252BeDRGxAAiN')],
	  [' '],
  ])
  #doc.AppendElement(
  #    document.FormElement(
  #        document.ELEMENT_TYPE.BUTTON, 'test', value='Test!'))

  #counter = document.Gadget(GADGET_URL)
  #doc.AppendElement(counter)

def OnButtonClicked(properties, context):
  logging.info("button clicked:\n%s\n%s", repr(properties), repr(context))
  blipId = properties['blipId']
  blip = context.GetBlipById(blipId)
  if not blip:
    logging.warning('Blip "%s" not found in context: %s' % (blipId, repr(context)))
    return

  modifier = properties.get('modifiedBy')
  button = properties.get('button')

  doc = blip.GetDocument()
  txt = doc.GetText()
  for key, elem in blip.GetElements().iteritems():
    if elem.type == document.ELEMENT_TYPE.BUTTON:
      if elem.name == 'test':
	doc.ReplaceElement(key,
	  document.FormElement(document.ELEMENT_TYPE.BUTTON, 'Roll', value='Roll!'))
	doc.InsertElement(key,
	  document.FormElement(document.ELEMENT_TYPE.INPUT, 'test2', value='Test?'))
      else:
	doc.ReplaceElement(key,
	  document.FormElement(document.ELEMENT_TYPE.BUTTON, 'test', value='Test again!'))
    logging.info("element: %s %s", repr(key), repr(elem))

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

  charstore_gae.DeleteCharactersInBlip(waveId, waveletId, blipId)

# Cleanup: Wave leaves newlines annotated as links? Ignore everything
# after "\n", and ensure the preceding part has non-whitespace content.
def bad_anchor(txt):
  newline_pos = txt.find('\n')
  if newline_pos >= 0:
    txt = txt[:newline_pos]
  txt = txt.strip()
  return not len(txt) > 0

TRAILING_AT_RE = re.compile('@ \s* $', re.X)

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

  def replacer(start, end, texts):
    return SetTextWithAttributes(doc, start, end, texts)
  def sheetTxt():
    replacements = []
    for anno in blip.GetAnnotations():
      if 'link/' in anno.name:
        link = dicelink.canonical_campaign(anno.value)
        if '!w+' in link:
	  start, end = controller.fix_anchor(txt, anno.range.start, anno.range.end)
	  if start == end:
            logging.info('ignoring malformed anchor text')
            continue
          logging.debug('found link %s (%d-%d)', repr(link), anno.range.start, anno.range.end)
	  if TRAILING_AT_RE.search(txt[:start]):
            logging.info('Converting wave link %s to wave ID %s', repr(txt[start:end]), link)
	    replacements.append((start, end, link))
    parts = []
    lastIdx = 0
    for start, end, link in sorted(replacements, key=lambda x: x[0]):
      if lastIdx < start:
        parts.append(txt[lastIdx:start])
      parts.append(link)
      lastIdx = end
    if lastIdx < len(txt):
      parts.append(txt[lastIdx:])
    return ''.join(parts)

  storage = charstore_gae.GaeCharStore(creator, modifier, waveId, waveletId, blipId)
  controller.process_text(txt, replacer, storage, sheetTxt)

  #doc.GadgetSubmitDelta(document.Gadget(GADGET_URL), {'count': num})

