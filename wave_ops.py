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
  #logging.info("start=%s end=%s texts=%s", start, end, texts);
  old_len = end - start 
  if old_len > 0:
    blip.range(start, end).delete()
  new_len = 0
  for lst in reversed(texts):
    item = lst[0]
    annos = lst[1:]
    # Argh. No consistent way to insert text that works everywhere,
    # including before the first and after the last character.
    if start == 0 and new_len == 0:
      blip.all().insert(item, bundled_annotations=annos)
    elif start == 0:
      blip.at(start).insert(item, bundled_annotations=annos)
    else:
      blip.at(start-1).insert_after(item, bundled_annotations=annos)

    # update length, assuming non-text element is replaced by one character.
    if isinstance(item, basestring):
      new_len += len(item)
    else:
      new_len += 1
  return new_len - old_len

def greeting_blip(blip):
  blip.append('DiceLink joined. ')
  blip.append('Privacy policy, Help', [('link/manual', 'https://wave.google.com/wave/#restored:wave:googlewave.com!w%252BeDRGxAAiN')])
  blip.append(' ', [('link/manual', None)])

def OnRobotAdded(event, wavelet):
  """Invoked when the robot has been added."""
  if not wavelet:
    logging.warning("can't create welcome blip, no wavelet")
    return
  blip = wavelet.reply()
  greeting_blip(blip)
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
    repl = blip.reply()
    repl.append('''%s

# expand XdY+Z rolls outside [] expressions? (true/false)
Inline rolls: %s

# Use "Import:" lines to make character sheets defined in other waves available in this wave.
#
# You can link waves (drag&drop), or specify the waveid as shown by the [!waveid] DiceLink command.
#
# Examples:
#   Import: PlayerAWaveLink
#   Import: @googlewave.com!w+3f7a # Player B
#   Import: @googlewave.com!w+da47 # DicePoolWave
%s

# The global template is a character sheet with definitions available for all rolls in this wave.
#
# Specify the sheet name here. (If it's in a different wave, Import that wave first.)
#
# Example:
#   Global template: DicePool
Global template: %s

# Edit and save the blip to apply the new settings. (You can delete it when done.)
''' % (
    controller.SETTINGS_BLIP_HEAD,
    config.get('inline').lower(),
    ''.join(['Import: %s\n' % x for x in config.get('imports')]), 
    config.get('global'),
  ))

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

def expand_wave_links(txt, annotations, replacer):
  replacements = []
  for anno in annotations:
    if 'link/' in anno.name:
      link = dicelink.canonical_campaign(anno.value)
      if '!w+' in link:
	start, end = controller.fix_anchor(txt, anno.start, anno.end)
	if start == end:
	  logging.info('ignoring malformed anchor text')
	  continue
	logging.debug('found link %s (%d-%d)', repr(link), anno.start, anno.end)
	new = replacer(txt, start, end, link)
	if new is not None:
	  replacements.append((start, end, new))
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

TRAILING_AT_RE = re.compile('@ \s* $', re.X)
def replace_wave_at(txt, start, end, link):
  if TRAILING_AT_RE.search(txt[:start]):
    logging.info('Converting wave link %s to wave ID %s', repr(txt[start:end]), link)
    return link
  else:
    return None

def replace_wave_inline(txt, start, end, link):
  return '@%s # %s' % (link, txt[start:end])

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
  def sheetTxt(is_settings):
    if is_settings:
      sheet_txt = expand_wave_links(blip.text, blip.annotations, replace_wave_inline)
    else:
      sheet_txt = expand_wave_links(blip.text, blip.annotations, replace_wave_at)
    if len(sheet_txt) > 0 and sheet_txt[-1] != '\n':
      sheet_txt += '\n'
    # Expand gadget values
    for index, elem in enumerate(blip.elements):
      #logging.info('Sheet element %s at %s', elem.type, index)
      if elem.type == 'GADGET':
	logging.info('Gadget element at %s', index)
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
