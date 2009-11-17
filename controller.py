#!/usr/bin/python
# -*- coding: utf-8 -*-

import cgi
import logging
import random
import re

import charsheet
import eval

EXPR_RE = re.compile(r'''
  \[
  (?:        # "CharacterName:", optional
    \s*
    (?P<name> [^]:]* )
    (?P<sep> :+)
  )?
  \s*
  (?P<expr> [^]]* )    # expression
  \]
  ''', re.X)

SPECIAL_EXPR_RE = re.compile(r'^\[ \! (.*) \]$', re.X)

PARENS_RE = re.compile(r'\(.*\)')
WORD_RE = re.compile(ur'([\w\u0080-\uffff]+)')
STRIKETHROUGH_RE = re.compile(r'\/\* (.*?) \*\/', re.X)

def handle_text(txt, defaultgetter, defaultsetter, replacer, storage):
  # calls replacer(start, end, texts) => offset_delta
  offset = 0
  for mexpr in EXPR_RE.finditer(txt):
    out_lst = []
    log_info = []
    expr = mexpr.group('expr').strip()
    expr_outside_parens = PARENS_RE.sub('', expr)
    if '=' in expr_outside_parens or 'Error:' in mexpr.group():
      continue
    charname = None
    char = None
    expansions = []
    name_match = mexpr.group('name')
    name_start = mexpr.start()+1
    expr_start = mexpr.start('expr')
    expr_end = mexpr.end('expr')

    #logging.debug('charname=%s expr=%s', repr(charname), repr(expr))
    maybe_special = SPECIAL_EXPR_RE.match(mexpr.group())
    if maybe_special:
      # "[:" prefix for special commands
      out, log = do_special(storage, maybe_special.group(1).strip())
      out_lst += out
      log_info += log
    else:
      if name_match is not None:
	charname = name_match.strip()
	if mexpr.group('sep') == '::':
	  defaultsetter(charname)
	# "[:" disables the default char for this roll by setting charname=''
      else:
	charname = defaultgetter()
      # charname==None or charname=='' mean no default char

      sym, char, template, out, log = get_char_and_template(storage, charname)
      out_lst += out
      log_info += log

      expr, expansions = get_expansions(expr, char, template)

      out, log = handle_expr(sym, expr)
      out_lst += out
      log_info += log

    if out_lst:
      if char and not name_match:
	offset += replacer(name_start+offset, name_start+offset,
	  [[char.name + ':']])
      for expand, start, end in expansions:
        offset += replacer(expr_start + start + offset, expr_start + end + offset, [[expand]])

      out_lst = [[' ']] + out_lst
      offset += replacer(expr_end+offset, expr_end+offset, out_lst)

    if log_info:
      logging.info(' '.join(log_info))

def do_special(storage, expr):
  out = []
  logs = []

  def error(msg):
    out.append(['Error: ' + msg, ('style/color', 'red')])
    logs.append(msg)
    
  m = WORD_RE.match(expr)
  if not m:
    error('Missing command after "[!"')
    return out, logs

  cmd = m.group(1)
  arg = expr[m.end():].strip()

  special_fn = storage.getspecial(cmd)
  if not special_fn:
    error('Unknown "[!" special command "%s"' % cmd)
    return out, logs
  logs.append('special: %s %s' % (expr, repr(arg)))
  # FIXME: special commands with prototype other than (charname)?
  # Commands taking a character arg 
  if not arg:
    error('Usage: "[!%s CharacterName]"' % cmd)
    return out, logs
  out.append(['=', ('style/color', '#aa00ff')])
  for msg, log in special_fn(arg):
    if msg:
      out.append(msg)
    if log:
      logs.append(log)
  return out, logs

def get_char_and_template(storage, charname):
  out = []
  log = []
  sym = {}
  char = None
  if charname:
    char = charsheet.GetChar(storage, charname)
    if char:
      sym = char.dict
      log.append('Char "%s" (%d),' % (char.name, len(char.dict)))
    else:
      out.append(['Sheet "%s" not found. ' % charname, ('style/color', 'red')])

  template = None
  if '_template' in sym:
    template_name = sym['_template'].replace('"', '').strip()
    template = charsheet.GetChar(storage, template_name)
    if template:
      logging.debug('Using template "%s" for "%s"' % (template.name, char.name))
      for k, v in template.dict.iteritems():
	# don't overwrite existing entries
	sym.setdefault(k, v)
      log.append('template "%s" (%d),' % (template_name, len(template.dict)))
    else:
      out.append(['Template "%s" not found. ' % template_name, ('style/color', 'red')])
  return sym, char, template, out, log

def get_expansions(expr, char, template):
  expansions = []
  if char:
    shortcuts = char.shortcuts
    if template:
      shortcuts.update(template.shortcuts)
    for ex in reversed(list(WORD_RE.finditer(expr))):
      expand = char.shortcuts.get(ex.group())
      #logging.debug('expansion: w=%s, ex=%s', repr(ex.group()), repr(expand))
      if expand:
	expr = expr[:ex.start()] + expand + expr[ex.end():]
	expansions.append((expand, ex.start(), ex.end()))
  return expr, reversed(expansions)

def markup(txt):
  out = []
  pos = 0
  for m in STRIKETHROUGH_RE.finditer(txt):
    out.append([txt[pos:m.start()], ('style/color', '#aa00ff')])
    out.append([m.group(1), ('style/color', '#cc88ff'), ('style/textDecoration', 'line-through')]) 
    pos = m.end()
  out.append([txt[pos:], ('style/color', '#aa00ff')])
  return out

def handle_expr(sym, expr):
  out = []
  log = []
  env = {
    'opt_nat20': True,
    'opt_crit_notify': int(sym.get('_critNotify', sym.get('CritNotify', 20))),
  }
  try:
    log.append('[%s]:' % expr)
    raw_result = eval.ParseExpr(expr, sym, env)
    if raw_result.show_as_list():
      results = raw_result.items()
    else:
      results = [raw_result]
    for result in results:
      if out:
	out.append([', '])
      else:
	log.append(repr(result.stats))
      detail=''
      value=''
      # callers may need to use cgi.escape() to prevent XSS from user-supplied string tags?
      if '_secret' in sym or 'Secret' in sym:
	value = result.secretval()
      else:
      	value = result.publicval()
	detail = result.detail()
      detail += '='
      out += markup(detail)
      out.append([value, ('style/fontWeight', 'bold')])
      log.append(detail + value)
  except eval.ParseError, e:
    out.append([e.__str__(), ('style/color', 'red')])
    log.append(e.__str__())
  return out, log

if __name__ == '__main__':
  random.seed(2) # specially picked, first d20 gets a 20
  logging.getLogger().setLevel(logging.DEBUG)

  storage = charsheet.CharacterAccessor(charsheet.GetInMemoryCharacter, charsheet.SaveInMemoryCharacter)
  storage.add_special('list', lambda n: [(['\nlist1'], ''), (['\nlist2'], '')])

  charsheet.CharSheet('''
    Name: Test
    a:Attack: d20 + 5 ">4"
    e(NumDice, TN): count(>= TN, explode(d(NumDice, 6)))
    (NumDice)e(TN): count(>= TN, explode(d(NumDice, 6)))
    fact(n): if(n <= 1, n, mul(n, fact(n - 1)))
    fib(n): if(or(n==0, n==1), n, fib(n-1) + fib(n-2))
    BW(n, TN): with(roll=sort(d(n, 6)), if(n==0, 0, count(>=TN, roll) + BW(count(==6, roll), TN)))
    SpecialResult(n): if(or(n<=8, n>=12), n "Nothing", if(or(n==9, n==12), n "Special Hit", n "Hit"))
    SpecialHit: SpecialResult(3d6)
  ''').save(storage)

  charsheet.CharSheet('''
    Name: D20Template

    Strength: "UndefinedStrength" # Notify user if they forgot to override it
    StrMod: div(Strength - 10, 2)
    JumpSkill: 0 # Default used when the user doesn't override it
    Jump: d20 + JumpSkill + StrMod
    Speed: 6
    CA: Combat Advantage: 2
  ''').save(storage)
  
  charsheet.CharSheet('''
    Name: Warrior
    _template: "D20Template" # Import
    Strength: 18 # Override the template's value
    Axe: d12 + StrMod # Can refer to values from the template
    Warrior's Strike: d8+5
    Double Strike: Warrior's Strike + Warrior's Strike
    withStr(Strength): $
    withStrBonus(N): with(Strength=Strength+N, $)
    springy: with(JumpSkill=10, $)
  ''').save(storage)

  charsheet.CharSheet('''
    Name: MultiWeapon
    _template: "D20Template" # Import

    Weapon: Longsword # default weapon
    Longsword: d(TimesW,8) + 2
    Dagger: d(TimesW,4)
    Maul: d(mul(2, TimesW), 6)

    TimesW: 1 # Weapon dice multiplier, don't edit
    (N)W: with(TimesW=N, Weapon)

    StrMod: 4
    DexMod: 2

    b:Basic: 1W + StrMod
    dx: DexDamage: 1W + DexMod
    DailyDamage: 2W + StrMod + DexMod 
    #with sword:with(Weapon=Sword, $)
    #lval $ d6
  ''').save(storage)


  charsheet.CharSheet('''
    Name: mw2
    # Default weapon properties, set this for your favorite weapon
    #name: "unarmed"; n_dice: 1; n_sides: 4; enh: 0; proficiency: 0; misc_hit: 0; misc_damage: 0; crit_sides: 6
    name: "Longsword+2"; n_dice: 1; n_sides: 8; enh: 2; proficiency: 3; misc_hit: 1; misc_damage: 1; crit_sides: 6
    # Weapon-specific overrides
    withMaul: with(name="Maul+1", n_sides=6, n_dice=2, enh=1, proficiency=2, misc_damage=0, misc_hit=0, $)
    times_w: 1 # power specific dice multiplier
    WeaponHit: enh + proficiency + misc_hit + name
    WeaponDamage: d(mul(n_dice, times_w), n_sides) + enh + misc_damage + name
    WeaponDamage2: d8 + enh + misc_damage + name
    (times_w)W: WeaponDamage
    critical: d(enh, crit_sides) + max($)
    critical2: max($) + d(enh, crit_sides)
    # Simple static values for testing
    StrMod: 4
    DexMod: 2
    HalfLevel: 3
    StrAttack: d20 + StrMod + HalfLevel + WeaponHit
    DexAttack: d20 + DexMod + HalfLevel + WeaponHit
    p1:Power One Attack: StrAttack "vs AC"
    p1d:Power One Damage: 2W + StrMod
    p2:Power Two Attack: DexAttack "vs Reflex"
    p2d:Power Two Damage: 1W + DexMod
  ''').save(storage)

  charsheet.CharSheet('''
    Name: Params
    Broadsword(n): d8+n
    Broadsword: Broadsword(0)

    hit(roll, modifiedtarget): if(roll>=modifiedtarget, roll "hit, bonus={bonus}", roll "miss by {modifiedtarget - roll}, bonus={bonus}")
    bonus: 0 # default value
    attack(target): hit(d100, target + bonus)
    attack(target)b(newBonus): with(bonus=newBonus, attack(target))
    attackT(target)b(bonus): attack(target)
    attack: attack(50) # default target 
  ''').save(storage)

  charsheet.CharSheet(u'''
    Name: macrotest
    # Uses experimental features, the macro feature isn't final.
    # See DiceLink Feature and Development Discussions (#2) .
    Enh: 2
    Pow: Enh + 100
    super: with(Enh=4, $)
    enh(Enh): $
    add(n): with(Enh=Enh+n, $)
  ''').save(storage)

  charsheet.CharSheet('''
    Name: BadTemplate
    _template: "Missing"
    Attack: d8
  ''').save(storage)

  charsheet.CharSheet('''
    Name: TrailingSpace 
    Skill: 5
  ''').save(storage)

  charsheet.CharSheet(u'''
    Name: 天地
    力: 17
    力2: 力 "力2 is {力}"
  ''').save(storage)

  tests = [
    '[Warrior:Axe]',
    '[ Warrior: Speed ]',
    '[Warrior: Jump]',
    '[Warrior: bonus(Jump)]',
    '[D20Template: Speed]',
    '[D20Template: Jump]',
    'Roll [Attack]', 
    'What is [fib(7)]?',
    '[fact(50)]',
    '[20e5]',
    '[e(10, 5)]',
    '[10x(SpecialHit)]',
    '[count(!=4, 6d6)+1]',
    '[d6+count(>=4, 6d6)+1]',
    '[if(d6>2, "yes", "no")]',
    '[5x(Attack)]',
    '[top(3, 4d6)]',
    '[top(3, 4x(3d6))]',
    '[BW(12,4)]',
    '[a]',
    '[ a ]',
    '[ Test : a ]',
    '[a+fact(3)]',
    '[Params: Broadsword(5)] [Params: Broadsword4] [Params: Broadsword]',
    '[Params: attack(80)] [Params: attack] [Params: attackT90b2] [Params: attack70b7]',
    "[Warrior: Double Strike] [Warrior: Warrior's Strike]",
    "ERROR: [BadCharacter: Attack]",
    "ERROR: [BadTemplate: Attack]",
    "ERROR: [:foo]",
    "ERROR: [!list]",
    "[!list Test]",
    "[! list Test ]",

    '[Warrior:: withStr22 bonus(Jump)]',
    '[springy withStr22 bonus(Jump)]',
    '[springy withStrBonus4 bonus(Jump)]',
    '[::d6]',
    'NONAME: [d20]',

    '[MultiWeapon:: with(Weapon=Maul, DailyDamage)]',
    '[DailyDamage]',
    '[with(Weapon=Dagger, DexDamage)]',
    '[b]',
    '[b + 2]',
    '[b+dx+CA]',

    '[mw2::withMaul Power One Attack]',
    '[Power Two Attack]',
    '[WeaponDamage]',
    '[WeaponDamage2]',
    '[withMaul critical Power One Damage]',
    '[withMaul critical2 Power One Damage]',

    u'[macrotest::Pow] [super Pow] [enh7 Pow] [add10 Pow] [super add10 Pow]',
    u'[天地:: 力] [力]',
    u'[力2]',
    u'[天地mistype: 力]',

    '[TrailingSpace: Skill]',
  ]
  
  defaultchar = ['Test']
  for input in tests:
    out_msg = [input]

    def defaultgetter():
      return defaultchar[0]

    def defaultsetter(name):
      defaultchar[0] = name

    colors = { '#ff0000': '\033[31m', 'red': '\033[31m', '#aa00ff': '\033[35m' }
    def replacer(start, end, texts):
      before = out_msg[0][:start]
      after = out_msg[0][end:]
      new = ''
      for rtxt in texts:
        txt = rtxt[0]
        for anno, val in rtxt[1:]:
          if anno == 'style/fontWeight':
            txt = '\033[1m' + txt + '\033[0m'
          elif anno == 'style/color':
	    col = colors.get(val, '\033[36m')
            txt = col + txt + '\033[0m'
	  elif val == 'line-through':
	    txt = '\033[7m' + txt + '\033[0m'
        new += txt
      out_msg[0] = before + new + after
      return len(new) - (end - start)

    handle_text(input, defaultgetter, defaultsetter, replacer, storage)
    print out_msg[0]

