import logging
import re

from waveapi import element
from waveapi import ops

import controller
import config
import charstore_gae
import dicelink # for canonical_campaign only, FIXME

#GADGET_URL='http://dicelink.appspot.com/static/counter.xml'

def SetTextWithAttributes(blip, start, end, texts):
  logging.debug("start=%s end=%s texts=%s", start, end, texts);
  old_len = end - start 
  if old_len > 0:
    blip.range(start, end).delete()
  new_len = 0
  for lst in reversed(texts):
    blip.at(start).insert(lst[0], bundled_annotations=lst[1:])
    new_len += len(lst[0])
  return new_len - old_len

def OnRobotAdded(event, wavelet):
  """Invoked when the robot has been added."""
  if not wavelet:
    logging.warning("can't create welcome blip, no wavelet")
    return
  blip = wavelet.reply()
  blip.append('DiceLink joined. ')
  blip.append('Privacy policy, Help', [('link/manual', 'https://wave.google.com/wave/#restored:wave:googlewave.com!w%252BeDRGxAAiN')])
  #doc.AppendElement(
  #    document.FormElement(
  #        document.ELEMENT_TYPE.BUTTON, 'test', value='Test!'))

  #counter = document.Gadget(GADGET_URL)
  #doc.AppendElement(counter)

def OnButtonClicked(event, wavelet):
  logging.info("button clicked:\n%s\n%s", repr(event), repr(wavelet))
  blipId = event.blip_id
  blip = event.blip
  if not blip:
    logging.warning('Blip "%s" not found in context: %s' % (blipId, repr(event)))
    return

  modifier = event.modified_by
  #button = event.button_name

  doc = blip.GetDocument()
  txt = doc.GetText()
  for index, elem in enumerate(blip.elements):
    if issubclass(elem, element.Button):
      if elem.name == 'test':
	blip.append(element.Button('Roll', value='Roll!'))
	blip.append(element.Input('test2', value='Test?'))
      else:
	blip.append(element.Button('test', value='Test again!'))
    logging.info("element: %s %s", repr(index), repr(elem))

def OnBlipDeleted(event, wavelet):
  """Invoked when a blip was deleted."""
  blipId = event.blip_id
  waveletId = wavelet.wavelet_id
  waveId = wavelet.wave_id

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

def OnBlipSubmitted(event, wavelet):
  """Invoked when a blip was submitted."""
  blipId = event.blip_id
  blip = event.blip
  if not blip:
    logging.warning('Blip "%s" not found in context: %s' % (blipId, repr(context)))
    return
  waveId = wavelet.wave_id
  waveletId = wavelet.wavelet_id
  creator = blip.creator
  modifier = event.modified_by
  if not modifier:
    logging.warning('No "modifiedBy" property available, using creator. FIXME!')
    modifier = creator
  txt = blip.text

  def replacer(start, end, texts):
    return SetTextWithAttributes(blip, start, end, texts)
  def sheetTxt():
    replacements = []
    for anno in blip.annotations:
      if 'link/' in anno.name:
        link = dicelink.canonical_campaign(anno.value)
        if '!w+' in link:
	  start, end = controller.fix_anchor(txt, anno.start, anno.end)
	  if start == end:
            logging.info('ignoring malformed anchor text')
            continue
          logging.debug('found link %s (%d-%d)', repr(link), anno.start, anno.end)
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

