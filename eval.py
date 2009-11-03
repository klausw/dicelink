import random
import re

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
      (?P<expr> [^)]* )
    \)
  ) |
  (?P<dice>
    (?P<num_dice> \d* )
    d 
    (?P<sides> \d+ ) 
    (?: b (?P<limit> \d+ ) )? 
  ) |
  (?P<symbol>
    [A-Z]\w+
    (?:
      \s+
      [A-Z]\w+
    )*
  ) |
  (?P<number>
    -?\d+
  )
''', re.X | re.I)

PLUSMINUS_RE = re.compile(r'\s* ([-+]) \s*', re.X)

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
  def __init__(self, value, details, flags):
    self.value = value
    self.details = details
    self.flags = flags
  def detail(self):
    return '+'.join(self.details).replace('--','').replace('+-', '-')
  def publicval(self):
    return ':'.join([str(self.value)] + self.flags.keys())
  def secretval(self):
    if 'Nat20' in self.flags:
      return 'Nat20'
    else:
      return self.publicval()
  def __str__(self):
    return self.detail() + '=' + self.publicval()

def RollDice(num_dice, sides, env):
  reroll_limit = env.get('reroll_limit', 1)
  out = []
  result = 0
  flags={}
  for i in xrange(num_dice):
    rolls = []
    while True:
      env['stats']['rolls'] += 1
      if env['stats']['rolls'] > MAX_ROLLS:
        raise ParseError('Max number of die rolls exceeded')
      if 'max' in env:
	roll = sides
      elif 'avg' in env:
        roll = (sides + reroll_limit) / 2.0
      else:
	roll = random.randint(1, sides)
      rolls.append(str(roll))
      if roll >= reroll_limit:
	result += roll
	out.append('\\'.join(rolls))
	break
  # Special cases for D&D-style d20 rolls
  if sides==20 and num_dice==1:
    if 'opt_nat20' in env and result==20:
      flags['Nat20'] = True
    if 'opt_crit_notify' in env and result >= env['opt_crit_notify']:
      flags['Critical'] = True

  detail = '%sd%d(%s)' % (
    {1:''}.get(num_dice, str(num_dice)),
    sides,
    ','.join(out))
  return Result(result, [detail], flags)
  

N_TIMES_RE = re.compile(r'(\d+) x', re.X)

def ParseExpr(expr, sym, parent_env):
  # ignore Nx(...) for now
  result = [Result(0, [], {})]

  # Make a shallow copy of the environment so that changes from child calls don't
  # propagate back up unintentionally.
  env = parent_env.copy()

  if not 'stats' in env:
    env['stats'] = {'rolls': 0, 'objects': 0}

  def DynEnv(key, val):
    # shallow copy, so that stats remains shared
    env_copy = env.copy()
    env_copy[key] = val
    return env_copy

  def Add(new_result, sign):
    result[0].value += sign * new_result.value
    if sign < 0:
      new_result.details[0] = '-'+new_result.details[0]
    result[0].details += new_result.details
    for k, v in new_result.flags.iteritems():
      result[0].flags[k] = v

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
    #print "matcher: expr start '%s'" % (expr[start:])

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
    dict = m.groupdict()
    if dict['dice']:
      limit = int(GetNotNone(dict, 'limit', env.get('reroll_limit', 1)))
      Add(RollDice(int(GetNotNone(dict, 'num_dice', 1)),
	            int(GetNotNone(dict, 'sides', 1)),
		    DynEnv('reroll_limit', limit)), sign)
    elif dict['number']:
      Add(Result(int(matched), [matched], {}), sign)
    elif dict['symbol']:
      expansion = LookupSym(matched, sym, start==0)
      if expansion is None:
        raise ParseError('Symbol "%s" not found' % matched)
      Add(ParseExpr(expansion, sym, env)[0], sign)
    elif dict['func']:
      fname = dict['name']
      fexpr = dict['expr']
      # print 'fexpr=%s' % fexpr
      if fname == 'max':
        Add(ParseExpr(fexpr, sym, DynEnv('max', True))[0], sign)
      elif fname == 'avg':
        Add(ParseExpr(fexpr, sym, DynEnv('avg', True))[0], sign)
      elif N_TIMES_RE.match(fname):
        ntimes = int(N_TIMES_RE.match(fname).group(1))
	if ntimes > 100:
	  raise ParseError('ntimes: number too big')
	rolls = [ParseExpr(fexpr, sym, env)[0] for _ in xrange(ntimes)]
	return rolls
      else:
        raise ParseError('Unknown function "%s"' % fname)

    start += m.end()

  return result

if __name__ == '__main__':
  random.seed(2) # specially picked, first d20 gets a 20

  sym = {
    'Deft Strike': 'd4+4',
    'Sneak Attack': '2d8+7',
    'Recursive': 'Recursive',
    'Armor': '2',
    'NegArmor': '-2',
    'Trained': '5',
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
    ('Deft Strike', 6),
    ('Deft Strike + Sneak Attack + 2', 17),
    ('Deft Strike + -1', 5),
    ('Deft Strike - 1', 5),
    ('Deft Strike - 2d4', -1),
    ('max(Deft Strike+Sneak Attack) + 4d10', 45),
    ('max(3d6) + 3d6 + avg(3d6b3) + max(d8)', 50.5),
    ('12x(d20+7)', ''),
    ('3x(Deft Strike)', ''),
    ('10d6b7', 'ParseError'),
    ('Recursive + 2', 'ParseError'),
    ('50x(50d6)', 'ParseError'),
  ]

  for expr, expected in tests:
    result_str = 'Error'
    result_val = None
    try:
      result = ParseExpr(expr, sym, env)
      result_val = result[0].value
      result_str = '%s' % map(str, result)
    except ParseError, e:
      result_str = str(e)
    status='FAIL'
    if isinstance(expected, str):
      if expected in result_str:
        status='PASS'
    else:
      if result_val == expected:
        status='PASS'
    print status, expr, result_str, result_val, expected

