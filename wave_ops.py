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
  logging.info("start=%s end=%s texts=%s", start, end, texts);
  old_len = end - start 
  if old_len > 0:
    blip.range(start, end).delete()
  new_len = 0
  for lst in reversed(texts):
    # Argh. No consistent way to insert text that works everywhere,
    # including before the first and after the last character.
    if start == 0:
      blip.at(start).insert(lst[0], bundled_annotations=lst[1:])
    else:
      blip.at(start-1).insert_after(lst[0], bundled_annotations=lst[1:])
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
  #blip.append(' ', [('link/manual', None)])
  #blip.append(element.Button('Configure', value='Configure'))

def OnButtonClicked(event, wavelet):
  blipId = event.blip_id
  blip = event.blip
  if not blip:
    logging.warning('Blip "%s" not found in context: %s' % (blipId, repr(event)))
    return

  button = event.button_name
  modifier = event.modified_by
  logging.info("button '%s' clicked by '%s'", button, modifier)
  if button == 'Configure':
    blip.all(element.Button).delete()
    blip.append(element.Check('inline', value='true'))
    blip.append(element.Label('inline', caption='support inline XdY+Z rolls'))
    blip.append(element.Button('Update', value='Update'))
  elif button == 'Update':
    for index, elem in enumerate(blip.elements):
      # Guard for LINE element that has no properties, can't use elem.name
      name = elem.get('name', '')
      value = elem.get('value', '')
      logging.info('element name="%s" value="%s"', name, value)
      if name == 'inline':
	logging.info('do something with inline')
    blip.all(element.Button).delete()
    blip.all(element.Check).delete()
    blip.all(element.Label).delete()
    blip.append(element.Button('Configure', value='Configure'))
    


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

