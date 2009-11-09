import cgi
import logging
import random
import re

import charsheet
import eval

EXPR_RE = re.compile(r'''
  \[
  (?: 
    ([^]:]*)
  : \s* )?
  ([^]]*)
  \]
  ''', re.X)

def handle_text(txt, defaultgetter, replacer):
  # calls replacer(start, end, texts) => offset_delta
  offset = 0
  for m in EXPR_RE.finditer(txt):
    out_lst = []
    if '=' in m.group(2) or 'ParseError' in m.group():
      continue
    char = None
    charname = None
    if m.group(1):
      charname = m.group(1)
    else:
      charname = defaultgetter()
    if charname:
      char = charsheet.GetChar(charname)
      if not char:
	out_lst.append(['"%s" not found' % charname, ('style/color', 'red')])

    out_lst += handle_expr(char, m.group(2))
    if out_lst:
      if char and not m.group(1):
	offset += replacer(m.start()+1+offset, m.start()+1+offset,
	  [[char.name + ':']])
      out_lst = [[' ']] + out_lst
      offset += replacer(m.end(2)+offset, m.end(2)+offset, out_lst)

def handle_expr(char, expr):
  log_info = []
  out_lst = []
  if char:
    sym = char.dict
    log_info.append('Char "%s" (%d),' % (char.name, len(char.dict)))
  else:
    sym = {}
  if '_template' in sym:
    template_name = sym['_template'].replace('"', '').strip()
    template = charsheet.GetChar(template_name)
    if template:
      logging.debug('Using template "%s" for "%s"' % (template.name, char.name))
      for k, v in template.dict.iteritems():
	sym.setdefault(k, v)
      log_info.append('template "%s" (%d),' % (template_name, len(template.dict)))
    else:
      logging.debug('template "%s" for "%s" not found' % (template_name, char.name))
  env = {
    'opt_nat20': True,
    'opt_crit_notify': int(sym.get('_critNotify', sym.get('CritNotify', 20))),
  }
  try:
    log_info.append('"%s":' % expr)
    for result in eval.ParseExpr(expr, sym, env):
      if out_lst:
	out_lst.append([', '])
      else:
	log_info.append(repr(result.stats))
      detail=''
      value=''
      # use cgi.escape() to prevent XSS from user-supplied string tags
      if '_secret' in sym or 'Secret' in sym:
	value = result.secretval()
	out_lst.append([cgi.escape(result.secretval()), ('style/fontWeight', 'bold')])
      else:
	detail = result.detail()
	value = cgi.escape(result.publicval())
      out_lst.append([detail+'=', ('style/color', '#aa00ff')])
      out_lst.append([value, ('style/fontWeight', 'bold')])
      log_info.append('%s=%s' % (detail, value))
  except eval.ParseError, e:
    out_lst.append([str(e), ('style/color', 'red')])
    log_info.append(str(e))
  logging.info(' '.join(log_info))
  return out_lst

if __name__ == '__main__':
  random.seed(2) # specially picked, first d20 gets a 20
  logging.getLogger().setLevel(logging.DEBUG)

  charsheet.SetCharacterAccessors(charsheet.GetInMemoryCharacter, charsheet.SaveInMemoryCharacter)

  charsheet.CharSheet('''
    Name: Test
    Attack: d20 + 5
    e(NumDice, TN): count(>= TN, explode(d(NumDice, 6)))
    (NumDice)e(TN): count(>= TN, explode(d(NumDice, 6)))
    fact(n): if(n <= 1, n, mul(n, fact(n - 1)))
    fib(n): if(or(n==0, n==1), n, fib(n-1) + fib(n-2))
    BW(Dice, TN): "NotImplemented"
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
  ''').save()
  
  charsheet.CharSheet('''
    Name: Warrior
    _template: "D20Template" # Import
    Strength: 18 # Override the template's value
    Axe: d12 + StrMod # Can refer to values from the template
  ''').save()

  tests = [
    '[Warrior: Axe]',
    '[Warrior: Speed]',
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
  ]
  
  for input in tests:
    out_msg = [input]
 
    def defaultgetter():
      return 'Test'

    def replacer(start, end, texts):
      new = out_msg[0][:start]
      for rtxt in texts:
	new += rtxt[0]
      new += out_msg[0][end:]
      out_msg[0] = new
      return len(new) - (end - start)

    handle_text(input, defaultgetter, replacer)
    print out_msg[0]
