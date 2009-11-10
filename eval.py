import logging
import random
import re
import sys

# TODO:
# explode(dice): dice + explode(roll(count(>=6, dice), 6))
# support Name: "My Name" with quotes
# treat &gt; &lt; &amp; as operator synonyms to support encoded input?

# Expression evaluator
#
# Intent is to have intuitive behavior, and lightweight syntax that doesn't
# intrude too much on narrative text that is mixed with the expressions.
#
# Symbol names may contain whitespace, this makes parsing a bit more complicated.
#
# Syntax:
# - whitespace not permitted except where specifically shown
# - case insensitive
# - no nested parens (but may assign complex things to a Symbol)
#
# Expr: Object (Whitespace* '+' Whitespace* Object)*
# Object: Func '(' Expr ')' | Dice | Symbol | Number
# Func: Number 'x' | 'max'
# DieRoll: Number 'd' Number ('b' Number)?
#
# Examples:

OBJECT_RE = re.compile(r'''
  (?P<func>
    (?P<name>
      \w+
    )
    \(
      (?P<expr> .* )
    \)
  ) |
  (?P<dice>
    (?P<num_dice> \d* )
    d 
    (?P<sides> \d+ ) 
    (?: b (?P<limit> \d+ ) )? 
  ) |
  (?P<symbol>
    \w*[_A-Za-z]\w*
    (?:
      \s+
      [_A-Za-z]\w*
    )*
  ) |
  (?P<number>
    -?\d+
  ) |
  "(?P<string>
    [^"]*
  )"
''', re.X | re.I)

NUMBER_RE = re.compile(r'\d+')

INTERPOLATE_RE = re.compile(r'\{([^}]*)\}')

PLUSMINUS_RE = re.compile(r'\s* ([-+])? \s*', re.X)

def LookupSym(name, sym, skip_prefix):
  while True:
    if name in sym:
      return sym[name]
      break
    if not skip_prefix:
      break
    space = name.find(' ')
    if space == -1:
      break
    name = name[space+1:]
  return None

class ParseError(Exception):
  def __init__(self, msg):
    self.msg = msg
  def __str__(self):
    return 'ParseError: %s' % self.msg

MAX_ROLLS=2000
MAX_OBJECTS = 900 # <1000, or Python breaks first on recursion

class Result(object):
  def __init__(self, value, detail, flags, is_constant=True, is_numeric=True):
    self._value = value
    self._detail = detail
    self._is_numeric = is_numeric
    self.is_constant = is_constant
    self.is_list = False
    self._show_as_list = False
    if is_constant:
      self.constant_sum = value
    else:
      self.constant_sum = 0
    self.flags = flags
  def value(self):
    return self._value
  def detail(self):
    maybe_constant = ''
    if self.constant_sum != 0:
      maybe_constant = '+' + str(self.constant_sum)
    if not self._detail:
      return ''
    return (self._detail + maybe_constant).replace('--','').replace('+-', '-')
  def detail_paren(self):
    if self._detail:
      return '(%s)' % self.detail()
    else:
      return '%s' % self.value()
  def is_numeric(self):
    return self._is_numeric
  def show_as_list(self):
    return self._show_as_list
  def publicval(self):
    maybe_value = []
    if self.is_numeric():
      maybe_value = [str(self.value())]
    return ':'.join(maybe_value + self.flags.keys())
  def secretval(self):
    if 'Nat20' in self.flags:
      return 'Nat20'
    else:
      return self.publicval()
  def __str__(self):
    return self.detail() + '=' + self.publicval()
  def __repr__(self):
    return 'Result(value=%s, constant_sum=%s, detail=%s, is_constant=%s, is_numeric=%s)' % (self._value, self.constant_sum, repr(self._detail), self.is_constant, self.is_numeric())

class ResultList(Result):
  def __init__(self, items):
    Result.__init__(self, 0, map(lambda x: x.detail(), items), {})
    self._items = items
    self._detail = ''
    self._show_as_list = True # set to False for dice rolls
    self.is_list = True
  def items(self):
    return self._items
  def value(self):
    return sum([x.value() for x in self._items])
  def is_numeric(self):
    return any([x.is_numeric() for x in self._items])
  def detail(self):
    return self._detail + ', '.join(['%s=%s' % (x.detail(), x.publicval()) for x in self._items])

def never(x):
  return False

def RollDice(num_dice, sides, env):
  if sides <= 0:
    return Result(0, '', {})
  reroll_if = env.get('reroll_if', never)
  result = 0
  flags={}
  dice = [] # results for each roll
  details = [] # ascii details for each roll
  for i in xrange(num_dice):
    rolls = []
    this_die = 0
    while True:
      env['stats']['rolls'] += 1
      if env['stats']['rolls'] > MAX_ROLLS:
        raise ParseError('Max number of die rolls exceeded')
      if 'max' in env:
	this_die = sides
	rolls.append(this_die)
	break
      elif 'avg' in env:
        if reroll_if != never:
	  total = 0.0
	  valid = 0
	  for i in xrange(1, sides+1):
	    if not reroll_if(i):
	      total += i
	      valid += 1
	  this_die = total / valid
	else:
	  this_die = (sides + 1) / 2.0

        if 'explode' in env:
	  if reroll_if != never:
	    flags['NotImplemented'] = True
	  this_die *= sides / (sides - 1.0)
        rolls.append(this_die)
	break
      else:
	roll = random.randint(1, sides)
      rolls.append(roll)
      if 'explode' in env:
	this_die += roll
        if roll < sides:
	  break
      elif not(reroll_if(roll)):
	this_die = roll
	break
    # Collect results for one component die roll
    dice.append(this_die)

    if 'explode' in env:
      txt = str(this_die) + '!' * (len(rolls)-1)
      details.append(txt)
    else:
      details.append('\\'.join(map(str, rolls)))
  if 'count' in env:
    predicate = env['count']
    for die in dice:
      if predicate(die):
	result += 1
  elif 'take_highest' in env:
    result = max(dice)
    for idx, val in enumerate(dice):
      if val == result:
        details[idx] = '=>' + details[idx]
  elif 'take_lowest' in env:
    result = min(dice)
    for idx, val in enumerate(dice):
      if val == result:
        details[idx] = '=>' + details[idx]
  else:
    result = sum(dice)
  # Special cases for D&D-style d20 rolls
  if sides==20 and num_dice==1:
    if 'opt_nat20' in env and result==20:
      flags['Nat20'] = True
    if 'opt_crit_notify' in env and result >= env['opt_crit_notify']:
      flags['Critical'] = True

  detail = '%sd%d(%s)' % (
    {1:''}.get(num_dice, str(num_dice)),
    sides,
    ','.join(details))
  return Result(result, detail, flags, is_constant=False)
  

N_TIMES_RE = re.compile(r'(\d+) x', re.X)

def DynEnv(env, key, val):
  # shallow copy, so that stats remains shared
  env_copy = env.copy()
  env_copy[key] = val
  return env_copy

def Val(expr, sym, env):
  return ParseExpr(expr, sym, env).value()

def fn_max(sym, env, fexpr):
  return ParseExpr(fexpr, sym, DynEnv(env, 'max', True))

def fn_avg(sym, env, fexpr):
  return ParseExpr(fexpr, sym, DynEnv(env, 'avg', True))

def fn_mul(sym, env, mul_a, mul_b):
  val_a = ParseExpr(mul_a, sym, env)
  val_b = ParseExpr(mul_b, sym, env)
  mul_flags = val_a.flags
  mul_flags.update(val_b.flags)
  mul_val = val_a.value() * val_b.value()
  if val_a.is_constant and val_b.is_constant:
    mul_detail = ''
  else:
    mul_detail = '%s*%s' % (val_a.detail_paren(), val_b.detail_paren())
  return Result(mul_val, mul_detail, mul_flags,
                is_constant=(val_a.is_constant and val_b.is_constant))
  
def fn_div(sym, env, numer, denom):
  numval = ParseExpr(numer, sym, env)
  denval = ParseExpr(denom, sym, env)
  div_flags = numval.flags
  div_flags.update(denval.flags)
  if denval.value() == 0:
    div_val = 0
    div_flags['DivideByZero'] = True
  else:
    div_val = int(numval.value()) / int(denval.value())
  if numval.is_constant and denval.is_constant:
    div_detail = ''
  else:
    div_detail = '%s/%s' % (numval.detail_paren(), denval.detail_paren())
  return Result(div_val, div_detail, div_flags, 
        	is_constant=(numval.is_constant and denval.is_constant),
		is_numeric=(denval.value() != 0))

def fn_bonus(sym, env, fexpr):
  bonus_res = ParseExpr(fexpr, sym, env)
  return Result(bonus_res.constant_sum, '', {})

def fn_d(sym, env, num_dice, sides):
  return RollDice(Val(num_dice, sym, env), Val(sides, sym, env), env)

def fn_explode(sym, env, fexpr):
  return ParseExpr(fexpr, sym, DynEnv(env, 'explode', True))

RELOPS = {
  '==': lambda x, y: x == y,
  '!=': lambda x, y: x != y,

  '<': lambda x, y: x < y,
  '<=': lambda x, y: x <= y,

  '>': lambda x, y: x > y,
  '>=': lambda x, y: x >= y,
}

RELOP_RE = re.compile(r'\s* ([=<>!]+) \s*', re.X)

def details_highlight(ret, all):
  for item in all._items:
    if item.value() == ret.value():
      item._detail = '=>' + item._detail
      break
  detail = '(%s)' % all.detail()
  return Result(ret.value(), detail, {}, is_constant=False)

def fn_highest(sym, env, fexpr):
  ret = ParseExpr(fexpr, sym, DynEnv(env, 'take_highest', True))
  if ret.is_list:
    # This was a vector-valued expression. Try again.
    all = ParseExpr(fexpr, sym, env)
    ret = sorted(all._items, key=lambda x: x.value(), reverse=True)[0]
    return details_highlight(ret, all)
  else:
    return ret

def fn_lowest(sym, env, fexpr):
  ret = ParseExpr(fexpr, sym, DynEnv(env, 'take_lowest', True))
  if ret.is_list:
    # This was a vector-valued expression. Try again.
    all = ParseExpr(fexpr, sym, env)
    ret = sorted(all._items, key=lambda x: x.value())[0]
    return details_highlight(ret, all)
  else:
    return ret

def relation(sym, env, expr):
  m = RELOP_RE.search(expr)
  if not m:
    raise ParseError('"%s" is not a valid filter')
  op = RELOPS.get(m.group(1))
  if not op:
    raise ParseError('"%s" is not a valid filter')
  return expr[:m.start()].strip(), op, expr[m.end():].strip()

def predicate(sym, env, expr):
  lhs, op, rhs = relation(sym, env, expr)
  #logging.debug('rhs=%s', rhs)
  if lhs:
    raise ParseError('Bad predicate, unexpected "%s"' % lhs)
  thresh = Val(rhs, sym, env)
  return lambda x: op(x, thresh)

def fn_reroll_if(sym, env, filter, fexpr):
  pred = predicate(sym, env, filter)
  return ParseExpr(fexpr, sym, DynEnv(env, 'reroll_if', pred))

def fn_count(sym, env, filter, fexpr):
  pred = predicate(sym, env, filter)
  return ParseExpr(fexpr, sym, DynEnv(env, 'count', pred))

RESULT_TRUE = Result(1, '', {})
RESULT_FALSE = Result(0, '', {})

def boolean(sym, env, cond):
  if '(' in cond:
    ret = ParseExpr(cond, sym, env)
    return (ret.value() != 0)
  lhs, op, rhs = relation(sym, env, cond)
  lval = Val(lhs, sym, env)
  rval = Val(rhs, sym, env)
  if op(lval, rval):
    return True
  else:
    return False

def fn_if(sym, env, cond, iftrue, iffalse):
  if boolean(sym, env, cond):
    return ParseExpr(iftrue, sym, env)
  else:
    return ParseExpr(iffalse, sym, env)

def fn_and(sym, env, *args):
  for arg in args:
    if not boolean(sym, env, arg):
      return RESULT_FALSE
  return RESULT_TRUE

def fn_or(sym, env, *args):
  for arg in args:
    if boolean(sym, env, arg):
      return RESULT_TRUE
  return RESULT_FALSE

def fn_not(sym, env, arg):
  if boolean(sym, env, arg):
    return RESULT_FALSE
  return RESULT_TRUE

def fn_with(sym, env, binding, expr):
  lhs, rhs = binding.split('=')
  lhs = lhs.strip()
  rhs = rhs.strip()
  rhs_val = sym.get(rhs)
  if not rhs_val:
    rhs_val = ParseExpr(rhs, sym, env)
  return eval_with(sym, env, {lhs: rhs_val}, expr)

FUNCTIONS = {
  'max': fn_max,
  'avg': fn_avg,
  'mul': fn_mul,
  'div': fn_div,
  'bonus': fn_bonus,

  # new, document!
  'd': fn_d,
  'explode': fn_explode,
  'reroll_if': fn_reroll_if,
  'count': fn_count,
  'highest': fn_highest,
  'lowest': fn_lowest,
  'if': fn_if,
  'or': fn_or,
  'and': fn_and,
  'not': fn_not,
  'with': fn_with,
}

DOLLAR_RE = re.compile(r'\$')

def eval_with(sym, env, bindings, expr):
  sym_save = {}
  for key, value in bindings.iteritems():
    old = sym.get(key)
    if old:
      #logging.debug('eval_with: dyn bind %s, %s => %s', key, old, value)
      sym_save[key] = old
    sym[key] = value
  
  ret = ParseExpr(expr, sym, env)
  sym.update(sym_save)
  return ret

class Function(object):
  def __init__(self, proto, expansion):
    self.proto = proto
    self.expansion = expansion

  def name(self, key):
    out = []
    pos = 0
    for idx, item in enumerate(DOLLAR_RE.finditer(key)):
      out.append(key[pos:item.start()])
      out.append('(%s)' % self.proto[idx])
      pos = item.end()
    out.append(key[pos:])
    return ''.join(out)

  def eval(self, sym, env, args):
    bindings = {}
    for idx, item in enumerate(args):
      key = self.proto[idx]
      bindings[key] = ParseExpr(item, sym, env)
    return eval_with(sym, env, bindings, self.expansion)

def ParseExpr(expr, sym, parent_env):
  # ignore Nx(...) for now
  result = Result(0, '', {})
  result._is_numeric = False

  # Make a shallow copy of the environment so that changes from child calls don't
  # propagate back up unintentionally.
  env = parent_env.copy()

  if not 'stats' in env:
    env['stats'] = {'rolls': 0, 'objects': 0}

  def Add(new_result, sign):
    result._value += sign * new_result.value()
    result.constant_sum += sign * new_result.constant_sum
    if new_result.is_numeric() or new_result.is_list:
      result._is_numeric = True
    new_detail = new_result._detail
    if new_detail and not new_result.is_constant:
      if sign < 0:
	result._detail = result._detail + '-' + new_detail
      else:
        if result._detail:
	  result._detail = result._detail + '+' + new_detail
	else:
	  result._detail = new_detail
    if not new_result.is_constant:
      result.is_constant = False
    for k, v in new_result.flags.iteritems():
      result.flags[k] = v

  def GetNotNone(dict, key, default):
    """Like {}.get(), but return default if the key is present with value None"""
    val = dict.get(key, None)
    if not val in (None, ''):
      return val
    else:
      return default

  expr = str(expr).lstrip()
  start = 0
  sign = +1
  while True:
    env['stats']['objects'] += 1
    if env['stats']['objects'] > MAX_OBJECTS:
      raise ParseError('Max number of objects exceeded')
    #logging.debug('matcher: expr "%s" <!> "%s', expr[:start], expr[start:])

    # Optional +/-
    msign = PLUSMINUS_RE.match(expr[start:])
    if msign:
      if msign.group(1) == '-':
        sign = -1
      else:
        sign = 1
      start += msign.end()

    m = OBJECT_RE.match(expr[start:])
    if not m:
      break
    matched = m.group(0)
    match_end = m.end()
    #logging.debug('expr "%s"', matched)
    dict = m.groupdict()
    if dict['dice']:
      limit = int(GetNotNone(dict, 'limit', 0))
      if limit:
        reroll_pred = lambda x: x < limit
      else:
        reroll_pred = env.get('reroll_if', never)
      Add(RollDice(int(GetNotNone(dict, 'num_dice', 1)),
	           int(GetNotNone(dict, 'sides', 1)),
	           DynEnv(env, 'reroll_if', reroll_pred)), sign)
    elif dict['number']:
      Add(Result(int(matched), matched, {}), sign)
    elif dict['symbol']:
      expansion = LookupSym(matched, sym, start==0)
      if expansion is None:
        fname = ''
	args = []
	fidx = 0
        for nm in NUMBER_RE.finditer(matched):
	  args.append(int(nm.group()))
	  fname += matched[fidx:nm.start()] + '$'
	  fidx = nm.end()
	fname += matched[fidx:]
	#logging.debug('maybe-fn: fname="%s" args=%s', fname, repr(args))
	func = LookupSym(fname, sym, start==0)
	if func is None:
	  raise ParseError('Symbol "%s" not found' % matched)
	
	if not isinstance(func, Function):
	  raise ParseError('Symbol "%s" is not a function' % matched)
	expansion = func.eval(sym, env, args)
      if not isinstance(expansion, Result):
        expansion = ParseExpr(expansion, sym, env)
      Add(expansion, sign)
    elif dict['string']:
      def eval_string(match):
        return str(ParseExpr(match.group(1), sym, env).value())
      # set flag, including double quotes
      new_string = INTERPOLATE_RE.sub(eval_string, matched)
      result.flags[new_string] = True
    elif dict['func']:
      fname = dict['name']
      fexpr = dict['expr']

      # The regex is greedy, in "f(1)+g(2)" it will match "1)+g(".
      # This makes the simple cases fast, but for complex expressions we need to
      # handle parenthesis balancing properly.
      args = []
      argidx = 0
      if '(' in fexpr or '"' in fexpr:
        open_parens = 0
	in_quotes = False
	for idx, char in enumerate(fexpr):
	  if char == '(' and not in_quotes:
	    open_parens += 1
	  elif char == ')' and not in_quotes:
	    open_parens -= 1
	    if open_parens < 0:
	      break
	  elif char == '"':
	    in_quotes = not in_quotes
	  elif char == ',' and open_parens == 0 and not in_quotes:
	    args.append(fexpr[argidx:idx])
	    argidx = idx+1
	if open_parens > 0:
	  raise ParseError('Missing closing parenthesis in "%s"' % fexpr)
	args.append(fexpr[argidx:])
	fexpr = fexpr[:idx+1]
	match_end = m.start('expr') + idx + 1
      else:
	args = fexpr.split(',')
        
      # print 'fexpr=%s' % fexpr
      fn = FUNCTIONS.get(fname, None)
      func = None
      if not fn:
        func = sym.get(fname + ('$' * len(args)))
      if func and isinstance(func, Function):
	Add(func.eval(sym, env, args), sign)
      elif fn:
	try:
          ret = fn(sym, env, *args)
	except TypeError, e:
	  logging.info('TypeError: %s', e, exc_info=True)
	  raise ParseError('%s: unexpected args %s' % (fname, repr(args)))
        Add(ret, sign)
      elif N_TIMES_RE.match(fname):
        ntimes = int(N_TIMES_RE.match(fname).group(1))
	if ntimes > 100:
	  raise ParseError('ntimes: number too big')
	rolls = ResultList([ParseExpr(fexpr, sym, env) for _ in xrange(ntimes)])
	return rolls
      else:
        raise ParseError('Unknown function "%s(%s)"' % (fname, ','.join(['_']*len(args))))

    start += match_end

  result.stats = env['stats']
  return result

if __name__ == '__main__':
  random.seed(2) # specially picked, first d20 gets a 20
  logging.getLogger().setLevel(logging.DEBUG)

  sym = {
    'Deft Strike': 'd4+4',
    'Sneak Attack': '2d8+7',
    'Recursive': 'Recursive',
    'Armor': '2',
    'NegArmor': '-2',
    'Trained': '5',
    'Level': '3',
    'HalfLevel': 'div(Level, 2)',
    'Str': '18',
    'StrMod': 'div(Str - 10, 2)',
    'StrP': 'StrMod + HalfLevel',
    'Enh': '2',
    'Bash': 'd20 + StrP + Enh',
    'Hometown': '"New York"',
    'e$$': Function(['Count', 'TN'], 'count(>= TN, explode(d(Count, 6)))'),
    '$es$': Function(['x', 'y'], 'e(x,y)'),
    'fact$': Function(['n'], 'if(n <= 1, n, mul(n, fact(n - 1)))'),
    'fib$': Function(['n'], 'if(n==0, 0, if(n==1, 1, fib(n-1) + fib(n-2)))'),
    'a$bb$c': Function(['x', 'y'], 'x+y'),
    'W': '1',
    'Sword': 'd(W, 8) + StrMod + Enh',
    'Dagger': 'd(W, 4) + StrMod + Enh',
    'Weapon': 'Sword',
    'Strike': 'Weapon',
    'Destroy': 'with(W=2, Weapon)'
  }

  sym_tests = [
    ('with Deft Strike', True, 'd4+4'),
    ('Not Deft Strike', False, None),
    ('Sneak Attack', False, '2d8+4'),
    ('Foo', False, None),
  ]
  for name, flag, result in sym_tests:
    print name, LookupSym(name, sym, flag), result

  env = {
    'opt_nat20': True,
    'opt_crit_notify': 19,
  }

  tests = [
    ('d20+5', 'Nat20'),
    ('42', 42),
    ('  42   ', 42),
    ('2+4', 6),
    (' 2 +  4  ', 6),
    ('5 + Trained - Armor', 8),
    ('5 - Armor + Trained', 8),
    ('5 + NegArmor + Trained', 8),
    ('2 - NegArmor', 4),
    ('d20+12', 31),
    ('3d6', 8),
    ('12d6b2', 51),
    ('Deft Strike', "d4(2)+4=6"),
    ('Deft Strike + Sneak Attack + 2', 'd4(2)+2d8(1,1)+13=17'),
    ('Deft Strike + -1', "d4(2)+3=5"),
    ('Deft Strike - 1', "d4(2)+3=5"),
    ('Deft Strike - 2d4', "d4(2)-2d4(4,3)+4=-1"),
    ('max(Deft Strike+Sneak Attack) + 4d10', 45),
    ('max(3d6) + 3d6 + avg(3d6b3) + max(d8)', 50.5),
    ('avg(d6b2)', 4.0),
    ('avg(explode(d6))', 4.2),
    ('12x(Bash)', ''),
    ('3x(Deft Strike)', ''),
    ('div(7, 2)', 3),
    ('div(3d6+5, 2)', 9),
    ('d20+5 "Prone"', 16),
    ('42 "Push {StrMod} squares"', 42),
    ('Bash', 24),
    ('bonus(Bash)', 7),
    ('Hometown', '="New York"'),
    ('div(Bash, 0)', '/0=DivideByZero'),
    ('mul(Level, 2)', 6),
    ('mul(d6, d10)', 30),
    ('count(>=4, 10d6)', 5),
    ('count(>=5, explode(10d4))', 3),
    ('count(>=5, explode(d(10,4)))', 3),
    ('lowest(6d6)', 2),
    ('highest(2d6 + 2)', 5),
    ('highest(3x(3d6))', 10),
    ('lowest(2x(d20+12))', 15),
    ('e(10, 7)', 2),
    ('10es7', 2),
    ('fact(5)', 120),
    ('fib(7)', 13),
    ('if(not(and(1!=2, 1==2)), 100, 200)', 100),
    ('with(Weapon=Dagger, Strike)', 7),
    ('with(Weapon=Dagger, Destroy)', 10),
    ('with(Weapon=Dagger+1, Destroy)', 8),
    ('Strike', 7),
    ('Destroy', 9),
    ('with(W=3, with(Enh=4, Strike))', 27),

    ('if(1==1, "with,comma", "more,comma")', '="with,comma"'),
    ('if(1==2, 3 "with,comma", 4 "unbalanced)paren")', '=4:"unbalanced)paren"'),
    ('if(1==2, 3, mul(2,3)', "Missing closing parenthesis"),

    ('10d6b7', 'ParseError'),
    ('Recursive + 2', 'ParseError'),
    ('50x(50d6)', 'ParseError'),
  ]

  for k in ['$es$', 'a$bb$c']:
    print "expand:", sym[k].name(k), sym[k].expansion

  args = sys.argv[1:]
  if args:
    tests = [(x, 0) for x in args]

  for expr, expected in tests:
    result_str = 'Error'
    result_val = None
    try:
      result = ParseExpr(expr, sym, env)
      result_val = result.value()
      result_str = str(result)
    except ParseError, e:
      result_str = str(e)
    status='FAIL'
    if isinstance(expected, str):
      if expected in result_str:
        status='pass'
    else:
      if result_val == expected:
        status='pass'
    if status == 'FAIL':
      print status, expr, result_str, '# got %s, expected %s' % (result_val, repr(expected))
    else:
      print status, expr, result_str

