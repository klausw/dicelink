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

import random
import re

import eval
import roll
import charstore

# Name: Value
# Long Name: complex value; Another Name: another value
ITEMS_RE=re.compile(ur'''
  [ \t]*
  (?:
    (?P<abbr> [\w\u0080-\uffff]+ (?: \(\) )?)
    : [ \t]*
  )?
  (?P<sym>
    [(]?[_a-z\u0080-\uffff][\w\u0080-\uffff' (),]*
  )? : [ \t]*
  (?P<exp>
    [^;\n]*?
  )
  [ \t]*
  (?: [;\n] | $ )
''', re.X | re.I | re.S)

NUMBER_RE=re.compile(r'^\d+$')

ATTACK_ROLL_RE=re.compile(r'(\S+) \s+ vs \s+ (\w+)', re.X)
DAMAGE_ROLLS_RE=re.compile(r',? \s* (\S+) \s+ (.*)', re.X)

class UnresolvedException(Exception):
  def __init__(self, msg):
    self.msg = msg

  def __str__(self):
    return 'Unresolved: %s' % msg

PROTOTYPE_RE = re.compile(r'\s* \( \s* (.*?) \s* \) \s*', re.X)

class CharSheet(object):
  def __init__(self, txt):
    self.txt = txt
    self.dict = {}
    self.keys = []
    self.span = {}
    self.shortcuts = {}
    for start, end, abbr, key, value in itemsFromText(txt):
      if NUMBER_RE.match(value):
        value = int(value)
      if key is not None and '(' in key:
        fname = ''
	args = []
	fidx = 0
        for nm in PROTOTYPE_RE.finditer(key):
	  fname += key[fidx:nm.start()]
	  for arg in nm.group(1).split(','):
	    arg = arg.strip()
	    args.append(arg)
	    fname += '$'
	  fidx = nm.end()
	fname += key[fidx:]
	#print 'function definition: fname="%s" args=%s' % (fname, repr(args))
        key = fname
	value = eval.Function(args, value)

      if key is not None:
	self.keys.append(key)
	self.span[key] = (start, end)
	self.dict[key] = value
      if abbr:
	if key is None:
	  self.shortcuts[abbr] = value
	else:
	  self.shortcuts[abbr] = key
    self.name = self.dict.get('Name', '')

  def hit(self, attack, defense):
    to_meet = self.dict.get(defense, None)
    if not to_meet:
      raise UnresolvedException('unknown defense "%s" for %s' % (defense, self.name))
    return attack >= to_meet
      
  def getAttack(self, power):
    if not power in self.dict:
      raise UnresolvedException('no attack "%s" for %s' % (power, self.name))
    spec = self.dict[power]
    
    m = ATTACK_ROLL_RE.match(spec)
    if m:
      attack_roll, defense = m.groups()
      spec = spec[m.end(2):]
    else:
      attack_roll, defense = ('', '')
    m = DAMAGE_ROLLS_RE.match(spec)
    if m:
      damage_tag, damage_rolls = m.groups()
    else:
      damage_tag, damage_rolls = ('', '')

    return attack_roll.lower(), defense, damage_tag, damage_rolls.lower()
      
  def text(self):
    out = []
    appended = 0
    for key in self.keys:
      start, end = self.span[key]
      if appended < start:
        out.append(self.txt[appended:start])
      value = self.dict[key]
      if isinstance(value, eval.Function):
        out.append('%s: %s' % (value.name(key), value.expansion))
      else:
	out.append('%s: %s' % (key, value))
      appended = end
    if appended < len(self.txt):
      out.append(self.txt[appended:])
    return ''.join(out)

  def __str__(self):
    return self.text()
      
CHARSHEET_RE = re.compile(r'^[^[]*\bName:', re.S)
def isCharSheet(txt):
  return CHARSHEET_RE.match(txt)

COMMENT_RE = re.compile(r'^(.*?)(#.*)$', re.M)
REMOVE_QUOTE_RE = re.compile(r'"[^"]*"')
def replaceCommentSimple(str):
  if str.group(2) is None:
    return str.group(1)
  else:
    return str.group(1) + ' ' * len(str.group(2))

def replaceComment(str):
  if '"' in str.group(1):
    # complicated case - might be a # inside "" string
    txt = str.group(0)
    copy = REMOVE_QUOTE_RE.sub(lambda m: ' ' * len(m.group(0)), txt)
    hashpos = copy.find('#')
    if hashpos >= 0:
      return txt[:hashpos] + ' ' * len(txt[hashpos:])
    else:
      return txt
    
  else:
    return replaceCommentSimple(str)

def itemsFromText(orig_txt):
  if not isCharSheet(orig_txt):
    return

  txt = orig_txt
  # strip comments
  txt = COMMENT_RE.sub(replaceComment, txt)

  # save items and positions
  def StripNotNone(txt):
    if not txt:
      return txt
    return txt.strip()

  for m in ITEMS_RE.finditer(txt):
    start, end = m.start(2), m.end(3)
    abbr, key, value = map(StripNotNone, m.groups())
    yield start, end, abbr, key, value
