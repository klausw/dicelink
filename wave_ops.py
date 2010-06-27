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

import logging
import re

from waveapi import element
from waveapi import ops

import controller
import config
import charstore_gae
import charsheet # for GadgetStateChanged, FIXME
import dicelink # for canonical_campaign only, FIXME

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
  blip.append(' ', [('link/manual', None)])
  blip.append(element.Button('Configure', value='Configure'))

def OnButtonClicked(event, wavelet):
  blipId = event.blip_id
  blip = event.blip
  modifier = event.modified_by
  if not blip:
    logging.warning('Blip "%s" not found in context: %s' % (blipId, repr(event)))
    return

  storage = charstore_gae.GaeCharStore(blip.creator, modifier, wavelet.wave_id, wavelet.wavelet_id, event.blip_id)
  config = storage.getconfig()

  button = event.button_name
  logging.info("button '%s' clicked by '%s'", button, modifier)
  if button == 'Configure':
    blip.all(element.Button).delete()
    blip.append(element.Check('inline', value=config.get('inline').lower()))
    blip.append(element.Label('inline', caption='expand XdY+Z rolls outside [] expressions '))
    blip.append(element.Button('Update', value='Update'))
  elif button == 'Update':
    for index, elem in enumerate(blip.elements):
      # Guard for LINE element that has no properties, can't use elem.name
      name = elem.get('name', '')
      value = elem.get('value', '')
      logging.info('element name="%s" value="%s"', name, value)
      if name == 'inline':
	if value == 'true':
	  config['inline'] = 'True'
	else:
	  config['inline'] = 'False'
    blip.all(element.Button).delete()
    blip.all(element.Check).delete()
    blip.all(element.Label).delete()
    storage.setconfig(config)
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
    sheet_txt = ''.join(parts)
    if len(sheet_txt) > 0 and sheet_txt[-1] != '\n':
      sheet_txt += '\n'
    # Expand gadget values
    for index, elem in enumerate(blip.elements):
      logging.info('Sheet element %s at %s', elem.type, index)
      if elem.type == 'GADGET':
	name = elem.get('name')
	value = None
	for keyname in ('value', 'pool'):
	  value = elem.get(keyname)
	  if value is not None:
	    break
	if name is not None and value is not None:
	  gadget_add = '%s: %s #!GADGET index=%d key=%s' % (name, value, index, keyname)
	  logging.info('Add gadget to sheet: "%s"', gadget_add)
	  sheet_txt += '%s\n' % (gadget_add)

    return sheet_txt

  storage = charstore_gae.GaeCharStore(creator, modifier, waveId, waveletId, blipId)
  controller.process_text(txt, replacer, storage, sheetTxt)

  #doc.GadgetSubmitDelta(document.Gadget(GADGET_URL), {'count': num})

def OnGadgetStateChanged(event, wavelet):
  txt = event.blip.text
  if charsheet.isCharSheet(txt):
    return OnBlipSubmitted(event, wavelet)
