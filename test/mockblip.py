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

import sys
sys.path.append('.')
sys.path.append('..')

import codecs
import logging
import random
import re
import glob

import controller
import charstore

GAE_AVAILABLE = False
try:
  import charstore_gae
  import dicelink
  GAE_AVAILABLE = True
except ImportError:
  pass

COLOR_MAP = { '#ff0000': '\033[31m', 'red': '\033[31m', '#aa00ff': '\033[35m' }

class AnsiDoc(object):
  def __init__(self, text):
    self.text = text

  def annotate(self, start, end, texts):
    before = self.text[:start]
    after = self.text[end:]
    new = ''
    for rtxt in texts:
      txt = rtxt[0]
      for anno, val in rtxt[1:]:
	if anno == 'style/fontWeight':
	  txt = '\033[1m' + txt + '\033[0m'
	elif anno == 'style/color':
	  col = COLOR_MAP.get(val, '\033[36m')
	  txt = col + txt + '\033[0m'
	elif val == 'line-through':
	  txt = '\033[7m' + txt + '\033[0m'
      new += txt
    self.text = before + new + after
    return len(new) - (end - start)

  def escape(self):
    return self.text

BLIP_START_RE = re.compile(r'^ --- [-\s]* (.*?) [-\s]* $', re.X)

def BlipIterator(context, files=None):
  if files is None:
    files = glob.glob('testdata/blips-*')
  for testfile in files:
    if '-gae' in testfile and not GAE_AVAILABLE:
      logging.info('no GAE storage, skipping file %s', testfile)
      continue

    blip = []
    for line in codecs.open(testfile, 'r', 'utf-8'):
      m = BLIP_START_RE.search(line)
      if m:
	if blip:
	  yield blip
	blip = []
	settings = m.group(1)
	if settings:
	  for setting in settings.split(','):
	    key, val = setting.strip().split(' ')
	    key = key.strip()
	    val = val.strip()

	    if key == 'seed':
	      random.seed(int(val))
	    else:
	      assert(key in context)
	      context[key] = val
      else:
	blip.append(line)
    if blip:
      yield blip

def MakeContext():
  context = {
    'creator': 'testCreator',
    'modifier': 'testModifier',
    'waveId': 'testWaveId',
    'waveletId': 'testWaveletId',
    'blipId': '#',
    '_blipCount': 0,
    '_storageFactory': None,
    '_makedoc': None,
  }

  if GAE_AVAILABLE:
    logging.info('Using GAE storage')
    def gaeStorageFactory(context):
      blipId = context['blipId']
      if blipId == '#':
	blipId = 'testBlip.%s' % str(context['_blipCount'])
	context['_blipCount'] += 1
      return charstore_gae.GaeCharStore(
	  context['creator'], context['modifier'],
	  context['waveId'], context['waveletId'],
	  blipId)
    context['_storageFactory'] = gaeStorageFactory
    context['_makedoc'] = dicelink.HTMLDoc
  else:
    logging.info('Using memory storage')
    memStorage = charstore.InMemoryCharStore()
    #memStorage.add_special('list', lambda n: [(['\nlist1'], ''), (['\nlist2'], '')])
    def memStorageFactory(context):
      return memStorage
    context['_storageFactory'] = memStorageFactory
    context['_makedoc'] = AnsiDoc
  return context

def doBlip(blip, context):
  input = ''.join(blip)
  storage = context['_storageFactory'](context)

  doc = context['_makedoc'](input)
  def replacer(start, end, texts):
    return doc.annotate(start, end, texts)

  controller.process_text(input, replacer, storage)
  return doc.escape()

if __name__ == '__main__':
  context = MakeContext()
  for blip in BlipIterator(context, sys.argv[1:]):
    print doBlip(blip, context).encode('utf-8')
