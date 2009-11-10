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

PARENS_RE = re.compile(r'\(.*\)')

def handle_text(txt, defaultgetter, replacer):
  # calls replacer(start, end, texts) => offset_delta
  offset = 0
  for m in EXPR_RE.finditer(txt):
    out_lst = []
    expr = m.group(2)
    expr_outside_parens = PARENS_RE.sub('', expr)
    if '=' in expr_outside_parens or 'ParseError' in m.group():
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

    # no longer needed, things should get unescaped on input and escaped on output outside the controller
    #expr = expr.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    out_lst += handle_expr(char, expr)
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
    raw_result = eval.ParseExpr(expr, sym, env)
    if raw_result.show_as_list():
      results = raw_result.items()
    else:
      results = [raw_result]
    for result in results:
      if out_lst:
	out_lst.append([', '])
      else:
	log_info.append(repr(result.stats))
      detail=''
      value=''
      # callers may need to use cgi.escape() to prevent XSS from user-supplied string tags?
      if '_secret' in sym or 'Secret' in sym:
	out_lst.append([result.secretval(), ('style/fontWeight', 'bold')])
      else:
	detail = result.detail()
      out_lst.append([detail+'=', ('style/color', '#aa00ff')])
      out_lst.append([result.publicval(), ('style/fontWeight', 'bold')])
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
    Attack: d20 + 5 ">4"
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
    '[count(!=4, 6d6)+1]',
    '[d6+count(>=4, 6d6)+1]',
    '[if(d6>2, "yes", "no")]',
    '[5x(Attack)]',
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
        new += txt
      out_msg[0] = before + new + after
      return len(new) - (end - start)

    handle_text(input, defaultgetter, replacer)
    print out_msg[0]

