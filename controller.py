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
    ([^]:]*)
    :
  )?
  \s*
  ( [^]]* )    # expression
  \]
  ''', re.X)

PARENS_RE = re.compile(r'\(.*\)')
WORD_RE = re.compile(r'(\w+)')

def handle_text(txt, defaultgetter, replacer):
  # calls replacer(start, end, texts) => offset_delta
  offset = 0
  for mexpr in EXPR_RE.finditer(txt):
    out_lst = []
    log_info = []
    expr = mexpr.group(2)
    expr_outside_parens = PARENS_RE.sub('', expr)
    if '=' in expr_outside_parens or 'ParseError' in mexpr.group():
      continue
    charname = None
    name_start = mexpr.start()+1
    expr_start = mexpr.start(2)
    expr_end = mexpr.end(2)

    if mexpr.group(1):
      charname = mexpr.group(1).strip()
      if charname == '':
        # "[:" prefix for special commands
	pass
    else:
      charname = defaultgetter()

    sym, char, template, out, log = get_char_and_template(charname)
    out_lst += out
    log_info += log

    expr, expansions = get_expansions(expr, char, template)

    out, log = handle_expr(sym, expr)
    out_lst += out
    log_info += log
    if out_lst:
      if char and not charname:
	offset += replacer(name_start+offset, name_start+offset,
	  [[char.name + ':']])
      for expand, start, end in expansions:
        offset += replacer(expr_start + start + offset, expr_start + end + offset, [[expand]])

      out_lst = [[' ']] + out_lst
      offset += replacer(expr_end+offset, expr_end+offset, out_lst)

    logging.info(' '.join(log_info))

STRIKETHROUGH_RE = re.compile(r'\/\* (.*?) \*\/', re.X)

def get_char_and_template(charname):
  out = []
  log = []
  sym = {}
  char = None
  if charname:
    char = charsheet.GetChar(charname)
    if char:
      sym = char.dict
      log.append('Char "%s" (%d),' % (char.name, len(char.dict)))
    else:
      out.append(['Sheet "%s" not found. ' % charname, ('style/color', 'red')])

  template = None
  if '_template' in sym:
    template_name = sym['_template'].replace('"', '').strip()
    template = charsheet.GetChar(template_name)
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
    out.append([str(e), ('style/color', 'red')])
    log.append(str(e))
  return out, log

if __name__ == '__main__':
  random.seed(2) # specially picked, first d20 gets a 20
  logging.getLogger().setLevel(logging.DEBUG)

  charsheet.SetCharacterAccessors(charsheet.GetInMemoryCharacter, charsheet.SaveInMemoryCharacter)

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
  ''').save()

  charsheet.CharSheet('''
    Name: D20Template

    Strength: "UndefinedStrength" # Notify user if they forgot to override it
    StrMod: div(Strength - 10, 2)
    JumpSkill: 0 # Default used when the user doesn't override it
    Jump: d20 + JumpSkill + StrMod
    Speed: 6
    CA: Combat Advantage: 2
  ''').save()
  
  charsheet.CharSheet('''
    Name: Warrior
    _template: "D20Template" # Import
    Strength: 18 # Override the template's value
    Axe: d12 + StrMod # Can refer to values from the template
    Warrior's Strike: d8+5
    Double Strike: Warrior's Strike + Warrior's Strike
  ''').save()

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
  ''').save()

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
  ''').save()

  charsheet.CharSheet('''
    Name: BadTemplate
    _template: "Missing"
    Attack: d8
  ''').save()

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
    '[MultiWeapon: with(Weapon=Maul, DailyDamage)]',
    '[MultiWeapon: DailyDamage]',
    '[MultiWeapon: with(Weapon=Dagger, DexDamage)]',
    '[MultiWeapon: b]',
    '[MultiWeapon: b + 2]',
    '[MultiWeapon: b+dx+CA]',
    '[a]',
    '[ a ]',
    '[ Test : a ]',
    '[a+fact(3)]',
    '[Params: Broadsword(5)] [Params: Broadsword4] [Params: Broadsword]',
    '[Params: attack(80)] [Params: attack] [Params: attackT90b2] [Params: attack70b7]',
    "[Warrior: Double Strike] [Warrior: Warrior's Strike]",
    "[BadCharacter: Attack]",
    "[BadTemplate: Attack]",
  ]
  
  for input in tests:
    out_msg = [input]
 
    def defaultgetter():
      return 'Test'

    colors = { '#ff0000': '\033[31m', '#aa00ff': '\033[35m' }
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

    handle_text(input, defaultgetter, replacer)
    print out_msg[0]

