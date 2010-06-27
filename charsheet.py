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


INTERACT_ACTION_RE = re.compile(r'(.*?) \s+ (attacks?|damages?|heals?) \s+ (.*) : \s* (.*)', re.X)

def GetAttackMatches(txt):
  for m in INTERACT_ACTION_RE.finditer(txt):
    #print m.groups()
    subject, verb, object, spec = m.groups()
    yield subject, verb, object, spec


def Interact(storage, txt):
  out_public = []
  out_private = []

  def OutPrivate(msg):
    out_private.append(msg)

  def OutPublic(msg):
    out_public.append(msg)

  for subject, verb, object, spec in GetAttackMatches(txt):
    attacker = storage.get(subject)
    if not attacker:
      OutPrivate('Attacker %s not found' % attacker)
      continue
    target = storage.get(object)
    if not target:
      OutPrivate('Target %s not found' % target)
      continue

    def DoAttack(msg, atk_roll, defense):
      atk, detail = roll.RollDie(atk_roll)
      is_hit = target.hit(atk, defense)
      OutPrivate('%s, rolled %s=%d [%s] vs %s, %s.' % (msg, atk_roll, atk, detail, defense, {True: 'hit', False: 'miss'}[is_hit]))
      OutPublic('%s, rolled %d vs %s, %s.' % (msg, atk, defense, {True: 'hit', False: 'miss'}[is_hit]))
      return is_hit

    def DoDamage(msg, tag, dmg_roll):
      dmg, detail = roll.RollDie(dmg_roll)
      old_val = target.dict.get(tag, None)
      if old_val is None:
        msg = 'Key "%s" not found' % tag
	OutPrivate(msg)
	return
      target.dict[tag] += dmg
      new_val = target.dict[tag]
      storage.put(target)
      OutPrivate('%s, applies %s %s=%s [%s] (total %s, was %s).' % (msg, tag, dmg_roll, dmg, detail, new_val, old_val))
      OutPublic('%s, applies %s %s (total %s, was %s).' % (msg, tag, dmg, new_val, old_val))

    if spec in attacker.dict:
      atk_roll, defense, tag, dmg_roll = attacker.getAttack(spec)
      if verb in ('attack', 'attacks'):
	msg = '%s attacks %s with %s' % (attacker.name, target.name, spec)
	DoAttack(msg, atk_roll, defense)
      elif verb in ('damage', 'damages'):
        msg = '%s damages %s with %s' % (attacker.name, target.name, spec)
        DoDamage(msg, tag, dmg_roll)
      break
    
    if verb in ('attack', 'attacks'):
      m = ATTACK_ROLL_RE.match(spec)
      if m:
        atk_roll, defense = m.groups()
	spec = spec[m.end(2):]
	msg = '%s attacks %s' % (attacker.name, target.name)
	DoAttack(msg, atk_roll, defense)
    
    if verb in ('damage', 'damages'):
      msg = '%s damages %s' % (attacker.name, target.name)
      m = DAMAGE_ROLLS_RE.match(spec)
      if m:
	DoDamage(msg, m.group(1), m.group(2))
      else:
	DoDamage(msg, 'Damage', spec)

    if verb in ('heal', 'heals'):
      OutPrivate('healing not implemented')

  
  return '\n'.join(out_public), '\n'.join(out_private)
 
if __name__ == '__main__':
  random.seed(42)

  storage = charstore.InMemoryCharStore()

  storage.put(CharSheet('''Name: Flint
  HP: 31; Damage: 0
  AC: 21; Ref: 18; Fort: 17; Will: 13
  Deft Strike: D20+12 vs AC, Damage D4+4
  Piercing Strike: D20+12 vs Ref, Damage D4+4
  Sneak Attack: Damage 2D8+7
  # Foo=1; HP: 0

  Notes go here.
  '''))

  storage.put(CharSheet('''Name: Orc A
  HP: 20; Damage: 0
  AC: 17; Ref: 12; Fort: 16; Will: 11
  Bash: D20+11 vs AC, Damage D8+5

  More notes.'''))

  actions = [
  	'Flint attacks Orc A: d20+5 vs AC',
	'Flint damages Orc A: Damage 2d6+10',
	'Orc A attacks Flint: Bash',
	'Flint attacks Orc A: Deft Strike',
	'Flint attacks Orc A: Piercing Strike',
	'Flint damages Orc A: Sneak Attack',
	'Flint damages Orc A: 17',
  ]
  for action in actions:
    print Interact(storage, action)
  
#  while flint.dict['Damage'] < flint.dict['HP'] and orc.dict['Damage'] < orc.dict['HP']:
#    power = ['Deft Strike', 'Piercing Strike'][random.randint(0, 1)]
#    resolve(flint, power, orc)
#    resolve(orc, 'Bash', flint)

  print storage.get('Flint')
  print storage.get('Orc A')

  storage.put(CharSheet('''Name: Comments
  # comment
  # "comment" # foo
  a: 1 # +10
  b: 1 + "#" + 1
  c: 1 + "#" + "#" + 1
  d: 1 + "#" + 1 # + 10
  e: 1 + "#" + 1 + "#2" # + 10
  f: 1 + "#" + 1 + "#2" # + 10 # + 20
  g: 1 + "#" + 1 + "#2" # "#
  h: 1 + "#" + 1 + "#2" # ""#
  MultiAttack(num): repeat(num, with(multiAttackPenalty=num+_i+"#{_i}of{num}", $))
  '''))

  print storage.get('Comments')
  for c in ('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'MultiAttack$'):
    print storage.get('Comments').dict.get(c).__repr__()

  storage.put(CharSheet('''Name: MultiAttackTest
_template: "ExaltedTemplate"
multiAttackPenalty: 0
Attack: exaltedd(15 - multiAttackPenalty, 7)
MultiAttack(num): repeat(num, with(multiAttackPenalty=num+_i+"#{_i}of{num}", $))
t1: repeat(3, d1)
tx(num): repeat(num, $)
ty(num): repeat(num, with(test=2+"z", $)) 
  '''))
  print storage.get('MultiAttackTest')
