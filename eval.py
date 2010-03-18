import copy
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

OBJECT_RE = re.compile(ur'''
  (?:
    \(
      (?P<parexpr> .* )
    \)
  ) |
  (?:
    (?P<func>
      [\w\u0080-\uffff]+
    )
    \(
      (?P<fexpr> .* )
    \)
  ) |
  (?:
    (?P<fpipe>
      [\w\u0080-\uffff]+
    )
    \s*
    \$  # func $ arg
    \s*
    (?P<fpinput>
      .*
    )
  ) |
  (?P<dice>
    (?P<num_dice> \d* )
    d 
    (?P<sides> \d+ ) 
    (?: b (?P<limit> \d+ ) )? 
  ) |
  (?P<symbol>
    [\w\u0080-\uffff]*
    [_A-Za-z\u0080-\uffff]
    [\w\u0080-\uffff']*
    (?:
      \s+
      [\w\u0080-\uffff]*
      [_A-Za-z\u0080-\uffff]
      [\w\u0080-\uffff']*
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

OP_RE = re.compile(r'''
  \s*
  ( \-
  | \+
  | \<=
  | \<
  | \>=
  | \>
  | \!=
  | ==
  | \*
  | \/
  | , 
  )? \s*
''', re.X)

OP_PRECEDENCE = {
  '*': 2,
  '/': 2,
  '+': 1,
  '-': 1,
  # rest has prio zero
  ',': -1,
}

class SymRef(object):
  def __init__(self, target):
    self.target = target

def LookupSym(name, sym):
  ret = sym.get(name, None)
  expansions = [name]
  while isinstance(ret, SymRef):
    expansions.append(ret.target)
    if ret.target in expansions[:-1]:
      raise ParseError('Recursive symbol expansion %s' % repr(expansions))
    ret = sym.get(ret.target, None)
  return ret

class ParseError(Exception):
  def __init__(self, msg):
    self.msg = msg
  def __str__(self):
    return self.msg

MAX_ROLLS=2000
MAX_OBJECTS = 900 # <1000, or Python breaks first on recursion

DEBUG_PARSER = False

class Result(object):
  def __init__(self, value, detail, flags, is_constant=True, is_numeric=True):
    self._value = value
    self._detail = detail
    self._is_numeric = is_numeric
    self.is_constant = is_constant
    self.is_list = False
    self.is_multivalue = False
    self.stats = None
    if is_constant:
      self.constant_sum = value
    else:
      self.constant_sum = 0
    self.flags = flags
  def value(self):
    return self._value
  def has_detail(self):
    return self._detail
  def detail(self, additional=''):
    maybe_constant = ''
    if self.constant_sum != 0:
      maybe_constant = '+' + str(self.constant_sum) # digits
    if not self.has_detail():
      return ''
    return (self._detail + additional + maybe_constant).replace('--','').replace('+-', '-')
  def detailvalue(self):
    maybe_detail = self.detail()
    maybe_value = self.publicval()
    if maybe_detail and maybe_value:
      return '%s=%s' % (maybe_detail, maybe_value)
    else:
      return maybe_detail + maybe_value
  def detail_paren(self):
    if self.has_detail():
      return '(%s)' % self.detail()
    else:
      return '%s' % self.value()
  def is_numeric(self):
    return self._is_numeric
  def show_as_list(self):
    return False
  def publicval(self):
    maybe_value = []
    if self.is_numeric():
      maybe_value = [str(self.value())]
    return ':'.join(maybe_value + sorted(self.flags.keys()))
  def secretval(self):
    if 'Nat20' in self.flags:
      return 'Nat20'
    else:
      return self.publicval()
  def __str__(self):
    return self.detail() + '=' + self.publicval()
  def __repr__(self):
    def notFalse(desc, x):
      if x:
	return ', ' + desc + repr(x)
      else:
	return ''

    return '%s(%s%s%s%s%s%s)' % (self.__class__.__name__, self._value,
      notFalse('flags=', self.flags.keys()),
      notFalse('constant_sum=', self.constant_sum),
      notFalse('detail=', self._detail),
      {True: ", const", False: ""}[self.is_constant],
      {True: ", num", False: ""}[self.is_numeric()])

class ResultList(Result):
  def __init__(self, items):
    Result.__init__(self, 0, map(lambda x: x.detail(), items), {})
    self._items = items
    self._detail = ''
    self._delim = ', '
    self.is_list = True
  def show_as_list(self):
    return True
  def to_scalar(self):
    return Result(self.value(), self.detail(), self.flags, is_constant=False, is_numeric=True)
  def items(self):
    return self._items
  def value(self):
    return self._value + sum([x.value() for x in self._items])
  def is_numeric(self):
    return any([x.is_numeric() for x in self._items])
  def has_detail(self):
    return True
  def detail(self):
    return Result.detail(self, '(%s)' % self._delim.join([x.detailvalue() for x in self._items]))
  def __repr__(self):
    return Result.__repr__(self) + ': ' + ', '.join([x.__repr__() for x in self._items])

class ResultMultiValue(ResultList):
  def __init__(self, items):
    ResultList.__init__(self, items)
    self.is_multivalue = True

class ResultDice(ResultList):
  def __init__(self, items):
    ResultList.__init__(self, items)
  def show_as_list(self):
    return False
  def detail_paren(self):
    return self.detail()
  def detail(self):
    return Result.detail(self, '(%s)' % self._delim.join([x.detailvalue() for x in self._items]))

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
      txt = '!' * (len(rolls)-1)
      details.append(txt)
    elif len(rolls) > 1:
      details.append('\\'.join(map(str, rolls)))
    else:
      details.append('')
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
  #return Result(result, detail, flags, is_constant=False)
  ret = ResultDice([Result(x, d, {}, is_constant=False) for x, d in zip(dice, details)])
  # FIXME, move to constructor
  ret.is_constant = False
  ret._delim = ','
  ret._detail = '%sd%d' % (
    {1:''}.get(num_dice, str(num_dice)),
    sides)
  ret.flags = flags
  return ret
  

N_TIMES_RE = re.compile(r'(\d+) x', re.X)

def DynEnv(env, key, val):
  # shallow copy, so that stats remains shared
  env_copy = env.copy()
  env_copy[key] = val
  return env_copy

def Val(expr, sym, env):
  return ParseExpr(expr, sym, env).value()

def ValOrString(expr, sym, env):
  val = ParseExpr(expr, sym, env)
  if val.is_numeric():
    return val.value()
  else:
    return val.publicval()

def fn_repeat(sym, env, num, fexpr):
  ntimes = ParseExpr(num, sym, env).value()
  if ntimes <= 0:
    raise ParseError("repeat: repeat count must be >0")
  out = []
  for i in xrange(ntimes):
    new_env = {
      '_': Result(0, '', {'#'+str(i+1): True}),
      '_i': i,
      '_n': ntimes}
    out.append(eval_with(sym, env, new_env, fexpr))
  return ResultList(out)

def fn_map(sym, env, fexpr, *list):
  if len(list) == 0:
    args, unused_rest = first_paren_expr(fexpr)
    if len(args) <= 2:
      raise ParseError("map: need a list or multiple arguments")
    fexpr = args[0]
    list = args[1:]
  if len(list) == 1:
    val = ParseExpr(list[0], sym, env)
    if val.is_list:
      all = val._items
    else:
      all = [val]
  else:
    all = [ParseExpr(x, sym, env) for x in list]
  if not '_' in fexpr:
    fexpr = '(%s)+_' % fexpr
  out = []
  for i, item in enumerate(all):
    new_env = {
      '_': item,
      '_i': i,
      '_n': len(all)}
    out.append(eval_with(sym, env, new_env, fexpr))
  return ResultList(out)

def fn_max(sym, env, *args):
  if len(args) == 1:
    return ParseExpr(args[0], sym, DynEnv(env, 'max', True))
  else:
    max = None
    for arg in args:
      val = ParseExpr(arg, sym, env).value()
      if max is None or val > max:
	max = val
    return Result(max, [], {})

def fn_min(sym, env, *args):
  if len(args) <= 1:
    raise ParseError('min() needs at least two args.')
  else:
    min = None
    for arg in args:
      val = ParseExpr(arg, sym, env).value()
      if min is None or val < min:
	min = val
    return Result(min, [], {})

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

def fn_high(sym, env, fexpr):
  return fn_top(sym, env, '1', fexpr)

def fn_low(sym, env, fexpr):
  return fn_bottom(sym, env, '1', fexpr)

def fn_sort(sym, env, fexpr):
  all = ParseExpr(fexpr, sym, env)
  if not all.is_list:
    raise ParseError('sort(%s): arg is not a list or dice roll' % fexpr)
  all._items = sorted(all._items, key=lambda x: x.value())
  return all

def fn_rsort(sym, env, fexpr):
  all = ParseExpr(fexpr, sym, env)
  if not all.is_list:
    raise ParseError('rsort(%s): arg is not a list or dice roll' % fexpr)
  all._items = sorted(all._items, key=lambda x: x.value(), reverse=True)
  return all

def fn_len(sym, env, fexpr):
  all = ParseExpr(fexpr, sym, env)
  if not all.is_list:
    raise ParseError('len(%s): arg is not a list or dice roll' % fexpr)
  ret = 0
  for item in all.items():
    if item.is_numeric():
      ret += 1
  return Result(ret, '', {})

def filter_list(list, pred):
  all = copy.deepcopy(list)
  for i, old in enumerate(all._items):
    if pred(i, old):
      continue
    new = copy.deepcopy(RESULT_NIL)
    maybe_detail = ''
    if old.has_detail():
      maybe_detail = '%s=' % old.detail()
    new._detail = '/*%s%s*/' % (maybe_detail, old.value())
    all._items[i] = new
  return all

def fn_pick(sym, env, filter, fexpr):
  all = ParseExpr(fexpr, sym, env)
  if not all.is_list:
    raise ParseError('pick(%s): arg is not a list or dice roll' % fexpr)
  pred = predicate(sym, env, filter)
  return filter_list(all, lambda i, item: pred(item.value()))

  raise ParseError('not implemented')

def fn_slice(sym, env, fexpr, start_expr, end_expr=None):
  all = ParseExpr(fexpr, sym, env)
  if not all.is_list:
    raise ParseError('slice(%s): arg is not a list or dice roll' % fexpr)
  num = len(all._items)
  start = ParseExpr(start_expr, sym, env).value()
  if end_expr is None:
    if start >= 0:
      end = start
      start = 0
    else:
      end = num
  else:
    end = ParseExpr(end_expr, sym, env).value()
  if start < 0:
    start = num + start
  if end < 0:
    end = num + end
  if start < 0 or start > num or end < 0 or end > num:
    raise ParseError('slice: index out of range')
  return filter_list(all, lambda i, item: i>= start and i < end)

def fn_top(sym, env, num, fexpr):
  all = fn_sort(sym, env, fexpr)
  return fn_slice(sym, env, all, - ParseExpr(num, sym, env).value())

def fn_bottom(sym, env, num, fexpr):
  all = fn_sort(sym, env, fexpr)
  return fn_slice(sym, env, all, ParseExpr(num, sym, env).value())

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
  thresh = ValOrString(rhs, sym, env)
  return lambda x: op(x, thresh)

def fn_reroll_if(sym, env, filter, fexpr):
  pred = predicate(sym, env, filter)
  return ParseExpr(fexpr, sym, DynEnv(env, 'reroll_if', pred))

def fn_count(sym, env, filter, fexpr=None):
  if fexpr is None:
    pred = lambda x: True
    fexpr = filter
  else:
    pred = predicate(sym, env, filter)
  val = ParseExpr(fexpr, sym, env)
  if not val.is_list:
    raise ParseError('cannot count non-list "%s"' % fexpr)
  ret = 0
  for item in val.items():
    if item.is_numeric() and pred(item.value()):
      ret += 1
  return Result(ret, val.detail(), val.flags, is_constant=False)
  #return ParseExpr(fexpr, sym, DynEnv(env, 'count', pred))

RESULT_TRUE = Result(1, '', {}, is_numeric=False)
RESULT_FALSE = Result(0, '', {}, is_numeric=False)
RESULT_NIL = Result(0, '', {}, is_numeric=False)

def boolean(sym, env, cond):
  return ParseExpr(cond, sym, env).value()

def fn_if(sym, env, cond, iftrue, iffalse):
  if boolean(sym, env, cond):
    return ParseExpr(iftrue, sym, env)
  else:
    return ParseExpr(iffalse, sym, env)

def fn_cond(sym, env, *args):
  nargs = len(args)
  for i in xrange(0, len(args), 2):
    if i == nargs-1:
      # lonely leftover arg, treat as default value
      return ParseExpr(args[i], sym, env)
    cond = args[i]
    arg = args[i+1]
    if boolean(sym, env, cond):
      return ParseExpr(arg, sym, env)
  return RESULT_NIL

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

BINDING_SPLIT_RE = re.compile(r'(.*?)(==|=)(.*)')

def fn_with(sym, env, *args):
  if len(args) < 2:
    raise ParseError('with() needs at least two arguments')
  bindings = args[:-1]
  expr = args[-1]
  new_env = {}
  for binding in bindings:
    m = BINDING_SPLIT_RE.match(binding)
    if m is None:
      raise ParseError('Binding term "%s" in "with(%s)" does not contain "="' % (binding.strip(), ', '.join([x.strip() for x in args])))
    lhs, op, rhs = m.groups()
    lhs = lhs.strip()
    rhs = rhs.strip()
    if op == '==':
      # bind symbol synonym
      rhs_val = SymRef(rhs)
      if not rhs_val:
	raise ParseError('"%s" is not a symbol, did you mean = instead of == in "%s"?' % (rhs, binding))
    else:
      #symval = sym.get(rhs)
      #if symval:
      #	if isinstance(symval, Function) or isinstance(symval, basestring):
      #	  env['warnings'].append('use of %s to bind a symbol, did you mean == in "%s"?' % (op, binding))
      rhs_val = ParseExpr(rhs, sym, env)
    new_env[lhs] = rhs_val
  return eval_with(sym, env, new_env, expr)

def fn_val(sym, env, expr):
  return Result(ParseExpr(expr, sym, env).value(), '', {})

def fn_lval(sym, env, expr):
  arg = ParseExpr(expr, sym, env)
  if not arg.is_list:
    raise ParseError('lval(%s): arg is not a list or dice roll' % expr)
  return ResultList([x for x in arg.items() if x.is_numeric()])

def fn_sval(sym, env, expr):
  arg = ParseExpr(expr, sym, env)
  return Result(0, '', arg.flags, is_numeric=False)

def fn_list(sym, env, *args):
  items = []
  for arg in args:
    items.append(ParseExpr(arg, sym, env))
  return ResultList(items)

def fn_nth(sym, env, num, expr):
  num = ParseExpr(num, sym, env).value()
  arg = ParseExpr(expr, sym, env)
  if not arg.is_list:
    raise ParseError('nth(%s): arg is not a list or dice roll' % expr)
  return arg.items()[num]

def fn_range(sym, env, e1, e2=None, e3=None):
  args = [ParseExpr(e1, sym, env).value()]
  if e2:
    args.append(ParseExpr(e2, sym, env).value())
  if e3:
    args.append(ParseExpr(e3, sym, env).value())
  
  rg = range(*args)
  values = [Result(x, '', {}, is_constant=True) for x in rg]
  return ResultList(values)

def fn_flag(sym, env, expr, name):
  val = ParseExpr(expr, sym, env)
  name = name.strip().replace('"', '')
  if name in val.flags or '"' + name + '"' in val.flags:
    return RESULT_TRUE
  else:
    return RESULT_FALSE

def fn_conflicttest(sym, env, expr):
  return Result(42, 'builtin', {})

FUNCTIONS = {
  'max': fn_max,
  'min': fn_min,
  'avg': fn_avg,
  'mul': fn_mul,
  'div': fn_div,
  'bonus': fn_bonus,
  'repeat': fn_repeat, # binds _ and _i
  'd': fn_d,
  'explode': fn_explode,
  'count': fn_count,
  'len': fn_len,
  'slice': fn_slice,
  'pick': fn_pick,
  'sort': fn_sort,
  'rsort': fn_rsort,
  'high': fn_high,
  'low': fn_low,
  'top': fn_top,
  'bottom': fn_bottom,
  'if': fn_if,
  'or': fn_or,
  'and': fn_and,
  'not': fn_not,
  'with': fn_with,
  'val': fn_val,
  'cond': fn_cond,
  'lval': fn_lval,
  ### undocumented
  'conflicttest': fn_conflicttest,
  'reroll_if': fn_reroll_if,
  'list': fn_list,
  'nth': fn_nth,
  'map': fn_map, # binds _ and _i
  #'range': fn_range, # needs sanity check for ranges!
  'sval': fn_sval,
  'flag': fn_flag,
  ### new, document!
  # func $ args

  ### planned:
  # flagged
}

DOLLAR_RE = re.compile(r'\$')

def eval_with(sym, env, bindings, expr):
  sym_save = {}
  sym_remove = {}
  for key, value in bindings.iteritems():
    old = sym.get(key)
    if old is None:
      sym_remove[key] = True
    else:
      sym_save[key] = old
    sym[key] = value
  
  ret = ParseExpr(expr, sym, env)
  sym.update(sym_save)
  for key in sym_remove:
    del sym[key]
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

def first_paren_expr(fexpr):
  args = []
  argidx = 0
  open_parens = 0
  in_quotes = False
  for idx, char in enumerate(fexpr):
    if char == '(' and not in_quotes:
      open_parens += 1
    elif char == ')' and not in_quotes:
      open_parens -= 1
      if open_parens < 0:
	idx -= 1 # do not want
	break
    elif char == '"':
      in_quotes = not in_quotes
    elif char == ',' and open_parens == 0 and not in_quotes:
      args.append(fexpr[argidx:idx])
      argidx = idx+1
  if open_parens > 0:
    raise ParseError('Missing closing parenthesis in "%s"' % fexpr)
  args.append(fexpr[argidx:idx+1])
  fexpr = fexpr[:idx+1]
  return args, fexpr

def eval_fname(sym, env, fname, args, trailexpr):
  #logging.debug('fname=%s args=%s trailexpr=%s', repr(fname), repr(args), repr(trailexpr))
  func = None
  if '$' in fname:
    func = sym.get(fname)
  else:
    func = sym.get(fname + ('$' * len(args)))
  if not func:
    fn = FUNCTIONS.get(fname, None)

  #args = [x.strip() for x in args]
  if func and isinstance(func, Function):
    # FIXME, duplication
    consume = 0
    if '$' in func.expansion:
      func = Function(func.proto, func.expansion.replace('$', trailexpr))
      #logging.debug('magic function: %s', repr(func.expansion))
      consume = len(trailexpr)
    return (func.eval(sym, env, args), consume)
  elif fn:
    try:
      return (fn(sym, env, *args), 0)
    except TypeError, e:
      logging.info('TypeError: %s', e, exc_info=True)
      raise ParseError('%s: unexpected args %s' % (fname, repr(args)))
  return (None, 0)

def ParseExpr(expr, sym, parent_env):
  if isinstance(expr, Result):
    return expr
  # ignore Nx(...) for now
  result = []
  ops = []

  # Make a shallow copy of the environment so that changes from child calls don't
  # propagate back up unintentionally.
  env = parent_env.copy()

  if 'stats' in env:
    env['stats']['level'] += 1
  else:
    env['stats'] = {'rolls': 0, 'objects': 0, 'level': 1}
    env['warnings'] = []

  def AddOperator(op):
    DEBUG('got operator %s', op)
    if ops and OP_PRECEDENCE.get(ops[-1], 0) >= OP_PRECEDENCE.get(op, 0):
      Reduce(result.pop(), ops.pop())
    ops.append(op)

  def ShiftVal(new_result):
    DEBUG('ShiftVal: %s', repr(new_result))
    result.append(new_result)

  def Reduce(rhs, op):
    # must not modify constants such as RESULT_NIL
    if not result:
      raise ParseError('Missing operand in expression "%s"' % expr)
    lhs = copy.deepcopy(result.pop())

    if op == ',':
      if lhs.is_multivalue:
	lhs._items.append(copy.deepcopy(rhs))
      else:
	lhs = ResultMultiValue([lhs, copy.deepcopy(rhs)])
      result.append(lhs)
      return

    need_parens = False
    lhs_detailparen = lhs.detail_paren()
    rhs_detailparen = rhs.detail_paren()
    if lhs.is_list:
      # flatten into scalar
      lhs = lhs.to_scalar()
    if rhs.is_list:
      rhs = rhs.to_scalar()
    DEBUG('Reduce, op=%s, lhs=%s, rhs=%s', op, repr(lhs), repr(rhs))

    lval = lhs._value
    rval = rhs.value()
    is_relop = False
    need_detail = (not rhs.is_constant)
    if op == '+':
      lval += rval
      lhs.constant_sum += rhs.constant_sum
      if need_detail and not lhs._detail:
	lhs._detail = rhs._detail
	need_detail = False
    elif op == '-':
      lval -= rval
      lhs.constant_sum -= rhs.constant_sum
    elif op in ('*', '/'):
      if op == '*':
	lval *= rval
      elif op == '/':
	lval /= rval
      else:
	raise ParseError('bad op: "%s"', op)
      if lhs.is_constant and rhs.is_constant:
	lhs.constant_sum = lval
      else:
	lhs.constant_sum = 0
	need_detail = True
	need_parens = True
    elif op in ('==', '!=', '<', '<=', '>', '>='):
      is_relop = True
      if op == '==':
	lval = (lval == rval and lhs.publicval() == rhs.publicval())
      elif op == '!=':
	lval = (lval != rval or lhs.publicval() != rhs.publicval())
      elif op == '<':
	lval = (lval < rval)
      elif op == '<=':
	lval = (lval <= rval)
      elif op == '>':
	lval = (lval > rval)
      elif op == '>=':
	lval = (lval >= rval)

      lhs.constant_sum = 0
      lhs._is_numeric = False

    lhs._value = lval
    if rhs.is_numeric() and not is_relop:
      lhs._is_numeric = True
    if need_detail:
      if not need_parens:
	lhs_detailparen = lhs._detail
	rhs_detailparen = rhs._detail
      lhs._detail = op.join([lhs_detailparen, rhs_detailparen])
    if not rhs.is_constant:
      lhs.is_constant = False
    lhs.flags.update(rhs.flags)
    DEBUG('Reduce to %s', lhs)
    result.append(lhs)

  def GetNotNone(dict, key, default):
    """Like {}.get(), but return default if the key is present with value None"""
    val = dict.get(key, None)
    if not val in (None, ''):
      return val
    else:
      return default

  def DEBUG(*args):
    if DEBUG_PARSER:
      logging.debug('ParseExpr: ' + '  ' * env['stats']['level'] + args[0], *args[1:])

  if isinstance(expr, basestring):
    expr = expr.lstrip()
  else:
    expr = str(expr)
  start = 0
  while True:
    env['stats']['objects'] += 1
    if env['stats']['objects'] > MAX_OBJECTS:
      raise ParseError('Evaluation limit exceeded. Bad recursion?')
    DEBUG('expr %s{}%s', expr[:start], expr[start:])

    # Optional operator
    maybe_plus = False
    mop = OP_RE.match(expr[start:])
    if mop:
      op = mop.group(1)
      start += mop.end()
      if op:
	AddOperator(mop.group(1))

	# If first item is negative, need to subtract it from zero (NIL will do)
	if mop.group(1) == '-' and not result:
	  ShiftVal(RESULT_NIL)
      elif result:
	#treat "X Y" as "X + Y"?
	maybe_plus = True

    m = OBJECT_RE.match(expr[start:])
    if not m:
      if not expr[start:]:
	break
      if start:
	raise ParseError("Unsupported syntax '%s' at end of '%s'" % (expr[start:], expr))
      else:
	raise ParseError("Unsupported syntax '%s'" % expr)
    if maybe_plus:
      AddOperator('+')
    DEBUG('dict: %s', ', '.join([k for k, v in m.groupdict().iteritems() if v]))
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
      ShiftVal(RollDice(int(GetNotNone(dict, 'num_dice', 1)),
	           int(GetNotNone(dict, 'sides', 1)),
	           DynEnv(env, 'reroll_if', reroll_pred)))
    elif dict['number']:
      DEBUG('number: %d', int(matched))
      ShiftVal(Result(int(matched), '', {}))
    elif dict['parexpr']:
      pexpr = dict['parexpr']
      args, pexpr = first_paren_expr(pexpr)
      match_end = m.start('parexpr') + len(pexpr) + 1
      ShiftVal(ParseExpr(pexpr, sym, env))
    elif dict['symbol']:
      orig_matched = matched
      expansion = LookupSym(matched, sym)
      if expansion is None:
	# Not a normal symbol lookup, look for special symbols
	
	# No spaces allowed in magic symbols, end match at space if present
	if ' ' in matched:
	  sidx = matched.index(' ')
	  matched = matched[:sidx]
	  match_end = start + len(matched) + 1
	
	# is it a magic symbol?
	expansion = LookupSym(matched, sym)
	if expansion and isinstance(expansion, basestring): # FIXME, hack
	  if not '$' in expansion:
	    raise ParseError('Symbol "%s" is not magic (no $ in expansion), missing operator before "%s" in "%s"?' % (matched, expr[match_end:], expr))
	  # actual magic happens below
	else:
	  # a(b)c(d)e style function called as a10c2e ?
	  fname = ''
	  args = []
	  fidx = 0
	  for nm in NUMBER_RE.finditer(matched):
	    args.append(int(nm.group()))
	    fname += matched[fidx:nm.start()] + '$'
	    fidx = nm.end()
	  fname += matched[fidx:]
	  #logging.debug('maybe-fn: fname="%s" args=%s', fname, repr(args))
	  func = LookupSym(fname, sym)
	  if func is None:
	    if orig_matched == matched:
	      raise ParseError('Symbol "%s" not found' % matched)
	    else:
	      raise ParseError('Symbol "%s" or "%s" not found' % (orig_matched, matched))
	  
	  if not isinstance(func, Function):
	    raise ParseError('Symbol "%s" is not a function, missing operator before "%s" in "%s"?' % (matched, expr[match_end:], expr))

	  if '$' in func.expansion:
	    #logging.debug('magic function: %s, args=%s', repr(func.expansion), repr(args))
	    expansion, offset = eval_fname(sym, env, fname, args, expr[start + match_end:])
	    match_end += offset
	  else:
	    expansion = func.eval(sym, env, args)
      if not isinstance(expansion, Result):
	if expansion and isinstance(expansion, basestring): # FIXME, hack
	  if '$' in expansion:
	    # magic symbol
	    marg = expr[match_end:]
	    expansion = expansion.replace('$', '(' + marg + ')')
	    match_end = len(expr)
        expansion = ParseExpr(expansion, sym, env)
      DEBUG('symbol %s: %s', matched, expansion)
      ShiftVal(expansion)
    elif dict['string']:
      def eval_string(match):
        return ParseExpr(match.group(1), sym, env).publicval().replace('"', '')
      # set flag, including double quotes
      new_string = INTERPOLATE_RE.sub(eval_string, matched)
      ShiftVal(Result(0, [], {new_string: True}, is_numeric=False))
    elif dict['fpipe']:
      fname = dict['fpipe']
      fexpr = dict['fpinput']
      DEBUG('fpipe name=%s, input=%s', repr(fname), repr(fexpr))
      ret, unused_offset = eval_fname(sym, env, fname, [fexpr], '')
      if ret:
	ShiftVal(ret)
      else:
        raise ParseError('Unknown function "%s(%s)"' % (fname, fexpr))
    elif dict['func']:
      fname = dict['func']
      fexpr = dict['fexpr']

      # The regex is greedy, in "f(1)+g(2)" it will match "1)+g(".
      # This makes the simple cases fast, but for complex expressions we need to
      # handle parenthesis balancing properly.
      if '(' in fexpr or '"' in fexpr:
	args, fexpr = first_paren_expr(fexpr)
	match_end = m.start('fexpr') + len(fexpr) + 1
      else:
	args = fexpr.split(',')
      DEBUG('args=%s', repr(args))

      ret, offset = eval_fname(sym, env, fname, args, expr[start + match_end:])
      if ret:
	ShiftVal(ret)
	match_end += offset
      elif N_TIMES_RE.match(fname):
        ntimes = int(N_TIMES_RE.match(fname).group(1))
	if ntimes > 100:
	  raise ParseError('ntimes: number too big')
	rolls = ResultList([ParseExpr(fexpr, sym, env) for _ in xrange(ntimes)])
	ShiftVal(rolls)
      else:
        raise ParseError('Unknown function "%s(%s)"' % (fname, ','.join(['_']*len(args))))

    start += match_end

  # No results? Set to NIL
  if not result:
    result.append(RESULT_NIL)

  while len(result)>1:
    DEBUG('Emptying stack, op=%s', op)
    if ops:
      op = ops.pop()
    else:
      op = '+'
    Reduce(result.pop(), op)
    
  #for new_result, op in zip(result[1:], ops[1:]):
  #  result[0] = Reduce(result[0], new_result, op)

  # Add stats for debugging
  ret = result[0]
  ret.stats = env['stats']
  env['stats']['level'] -= 1
  if env['stats']['level'] == 0:
    for warn in env['warnings']:
      ret.flags['{Warning: %s}' % warn] = True
  DEBUG('=%s', repr(ret))
  return ret

if __name__ == '__main__':
  random.seed(2) # specially picked, first d20 gets a 20
  logging.getLogger().setLevel(logging.DEBUG)

  sym = {
    'Deft Strike': 'd4+4',
    'Sneak Attack': '2d8+7',
    'Recursive': 'Recursive',
    'Armor': 2,
    'NegArmor': -2,
    'Trained': 5,
    'Level': 3,
    'HalfLevel': 'div(Level, 2)',
    'Str': '18',
    'StrMod': 'div(Str - 10, 2)',
    'StrP': 'StrMod + HalfLevel',
    'Enh': 2,
    'Bash': 'd20 + StrP + Enh',
    'Hometown': '"New York"',
    "Quot'1": 1,
    "Test Quot'2": 2,
    "weird 1z'3": 3,
    'e$$': Function(['Count', 'TN'], 'count(>= TN, explode(d(Count, 6)))'),
    '$es$': Function(['x', 'y'], 'e(x,y)'),
    'fact$': Function(['n'], 'if(n <= 1, n, mul(n, fact(n - 1)))'),
    'fib$': Function(['n'], 'if(n==0, 0, if(n==1, 1, fib(n-1) + fib(n-2)))'),
    'a$bb$c': Function(['x', 'y'], 'x+y'),
    'bw$$': Function(['n', 'TN'], 'with(roll=sort(d(n, 6)), if(n==0, 0, count(>=TN, roll) + bw(count(==6, roll), TN)))'),
    'W': '1',
    'Sword': 'd(W, 8) + 4',
    'Dagger': 'd(W, 4) + 2',
    '$W': Function(['n'], 'with(W=n, Weapon)'),
    'Weapon': 'Sword',
    'Strike': '1W + StrMod',
    'Destroy': '2W + StrMod',
    'conflicttest$': Function(['x'], '"my value"'),
    'MeleeBonus': 'Enh + StrP',
    'withEnhFour': 'with(Enh=4, $)',
    'withEnhUnicode': u'with(Enh=4, $)',
    'withEnh$': Function(['N'], 'with(Enh=N, $)'),
    'withStr$': Function(['Str'], '$'),
    'L10': 'val(d10-1)',
    'SuccessMarker$$': Function(['TN', 'roll'], 'if(roll <= TN, "success {roll} vs {TN} doS:{(TN-roll)/10}", "failure {roll} vs {TN} doF:{(roll-TN)/10}")'),
    'Difficulty': 0,
    'sBasic$': Function(['Stat'], 'with(Difficulty=Difficulty+Stat/2,$)'), 
    'dbonus$': Function(['n'], 'with(Difficulty=Difficulty+n, $)'),
    'blast': Function([], 'map($)'),
  }

  sym_tests = [
    ('Deft Strike', 'd4+4'),
    ('Foo', None),
    ('Not Deft Strike', None),
    ('Sneak Attack', '2d8+7'),
  ]
  for name, result in sym_tests:
    assert LookupSym(name, sym) == result, 'symbol lookup %s != %s' % (repr(name), repr(result))

  env = {
    'opt_nat20': True,
    'opt_crit_notify': 19,
  }

  tests = [
    ('0', r'/^=0$/'),
    ('d20+5', 'd20(20)+5=25:Critical:Nat20'),
    ('42', 42),
    ('  42   ', 42),
    ('2+4', 6),
    (' 2 +  4  ', 6),
    ('5 + Trained - Armor', 8),
    ('5 - Armor + Trained', 8),
    ('5 + NegArmor + Trained', 8),
    ('2 - NegArmor', 4),
    ('d20+12', 'd20(19)+12=31:Critical'),
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
    ('12x(Bash)', 'd20(8)+7=15, d20(20)+7=27:Critical:Nat20,'),
    ('3x(Deft Strike)', '(d4(4)+4=8, d4(3)+4=7, d4(2)+4=6)=21'),
    ('div(7, 2)', 3),
    ('7 / 2', 3),
    ('7 * 2', 14),
    ('div(3d6+5, 2)', 9),
    ('d20+5 "Prone"', 16),
    ('42 "Push {StrMod} squares"', 42),
    ('Bash', 24),
    ('bonus(Bash)', 7),
    ('div(Bash, 0)', '/0=DivideByZero'),
    ('mul(Level, 2)', 6),
    ('mul(d6, d10)', 30),
    ('count(>=4, 10d6)', 5),
    ('count(>=5, explode(10d4))', 3),
    ('count(>=5, explode(d(10,4)))', 3),
    ('e(10, 7)', 3),
    ('10es7', 1),
    ('with(Weapon==Dagger, Strike)', 7),
    ('with(Weapon==Dagger, Destroy)', 11),
    ('with(Weapon=Dagger+1, Destroy)', 10),
    ('Strike', 9),
    ('Destroy', 12),
    ('with(Enh=4, 3W + StrMod)', 25),

    ('low(6d6)', 2),
    ('high(2d6) + 2', 6),
    ('high(2d6 + 2)', r'/ParseError.*not a list/'),
    ('high(3x(3d6))', 12),
    ('low(2x(d20+12))', 13),
    ('top(2, 3d20)', '3d20(/*2*/,3,12)=15'),
    ('top(2, 3x(d20+4))', '(/*d20(1)+4=5*/,'),
    ('len(3d6)', 3),
    ('len(3x(d20))', 3),
    ('sort(6d10)', '6d10(3,5,6,7,8,9)=38'),
    ('slice(6d10, 2)', '6d10(3,5,/*6*/,/*1*/,/*1*/,/*5*/)=8'),
    ('slice(6d10, -2)', '6d10(/*2*/,/*8*/,/*3*/,/*1*/,2,3)=5'),
    ('slice(6d10, 0, 1)', '6d10(3,/*6*/,/*5*/,/*4*/,/*7*/,/*3*/)=3'),
    ('pick(<3, 10d10)', 3),
    ('bw(12,4)', 8),
    ('bw(12,4)', 3),
    ('bw(8,4)', 2),
    ('bw(7,4)', 7),
    ('bw(6,4)', 2),
    ('bw(5,4)', 4),
    ('repeat(3, d20+2)', '(d20(9)+2=11, d20(14)+2=16, d20(19)+2=21:Critical)=48'),
    ('val(3d6)', r'/^=10$/'),
    ('lval(3d6)', r'/^\(3, 6, 1\)/'),
    ('lval(top(4, 10d20))', r'/^\(13, 14, 18, 20\)/'),
    ('sval(3d6 "hit" "marked")', r'/^="hit":"marked"/'),
    ('len $ 3d6', 3),
    ('len$explode$3d6', 3),
    ('d(1,d(1,1))+10', 11),
    ('d(1,d(1,1) ) + 10', 11),
    ('d( 1 , d( 1 , 1 ) ) + 10', 11),
    #FIXME#('with(n=d20, if(n>20, n, d20))', '/*d20(17)*/d20(8)=8'),
    #FIXME#('if(count(==3,10d6)>2,"many","few")', -1),
    ('with(c=count(==3,10d6), if(c>2,"many","few"))', 'few'), 
    ('with(a=L10, list(a, a, a, a, a, a, a, a))', '(4, 4, 4, 4, 4, 4, 4, 4)=32'),
    ('with(a==L10, list(a, a, a, a, a, a, a, a))', '(4, 7, 9, 7, 4, 9, 3, 7)=50'),
    ('SuccessMarker(50, d100)', '="failure 66 vs 50 doF:1"'),
    ('6d6*3 "cut"', '6d6(5,6,2,4,3,5)*3=75'),
    ('d6+2+(d4+1)*2+4', 'd6(6)+(d4(3)+1)*2+6=20'),
    ('blast d20, "orc 1", "orc 2" + 2, "orc 3"', '(d20(1)=1:"orc 1", d20(10)+2=12:"orc 2", d20(15)=15:"orc 3")'),

    # everything after this doesn't roll dice, order doesn't matter.
    ('Hometown', '="New York"'),
    ('fact(5)', 120),
    ('fib(7)', 13),
    ('if(not(and(1!=2, 1==2)), 100, 200) + 10', 110),
    ('if(1==1, "with,comma", "more,comma") + "foo"', '="foo":"with,comma"'),
    ('if(1==2, 3 "with,comma", 4 "unbalanced)paren") + 10', '=14:"unbalanced)paren"'),
    ('if("a"=="a", 1, 2)', 1),
    ('if("a"=="b", 1, 2)', 2),
    ('with(x="a" "b", y="b" "a", if(x==y, 1, 2))', 1),
    ('with(x="a" "b", y="a", if(x==y, 1, 2))', 2),
    ('with(x="a" "b", y="a:b", if(x==y, 1, 2))', 2),
    ('with(x=1, y=2, with(x=y, y=x, "x is {x}, y is {y}"))', 'x is 2, y is 1'),
    ('len(list(1,2,3,4))', 4),
    ('1,2,3', '(1, 2, 3)=6'),

    ('len(pick(>=3, list(1,2,3,4)))', r'/^=2$/'),
    ('count(pick(>=3, list(1,2,3,4)))', '(/*1*/, /*2*/, 3, 4)=2'),
    ('with(l=list(1,2,3), count(pick(>=3, l)) + len(l))', 4),
    ('nth(3, list(10,11,12,13))', 13),
    ('cond(1==0, "zero", 1==1, "one", 1==2, "two")', '"one"'),
    ('cond(3==0, "zero", 3==1, "one", 3==2, "two")', r'/^=$/'),
    ('cond(3==0, "zero", 3==1, "one", 3==2, "two", "other")', '"other"'),
    #('conflicttest(3)', 'builtin'),
    ('conflicttest(3)', 'my value'),
    ('MeleeBonus', 7),
    ('withEnhFour MeleeBonus', 9),
    ('withEnhFour MeleeBonus, MeleeBonus', '(9, 9)=18'),
    ('withEnhUnicode MeleeBonus', 9),
    ('withEnh8 MeleeBonus', 13),
    ('withEnh8 withStr20 MeleeBonus', 14),
    ("Quot'1", 1),
    ("Test Quot'2", 2),
    ("weird 1z'3", 3),
    ('"a {Hometown} b"', r'/^="a New York b"$/'),
    ('with(x=Enh + Hometown, "a {x} b")', r'/^="a 2:New York b"$/'),
    ('(4+3)-(2+1)', 4),
    ('(4+(3-2))-(2+1)', 2),
    ('1+2+3-4', 2),
    ('1+2*3-4', 3), # would be 5 without precedence rule
    ('1+(2*3)-4', 3), 
    ('(1+2)*3-4', 5),
    ('-NegArmor', 2),
    ('1==1', 1),
    ('1==2', 0),
    ('1+2==1+1+1', 1),
    ('if((1==1), 2, 3)', 2),
    ('if((1==2), 2, 3)', 3),
    ('if(2+(1==1), 2, 3)', 2), # boolean treated as numeric, not sure if this is expected
    ('', r'/^=$/'),
    ('sBasic10 Difficulty', 5),
    ('sBasic(10) Difficulty', 5),
    ('dbonus10 Difficulty', 10),
    ('dbonus(10) Difficulty', 10),
    ('dbonus10 sBasic8 Difficulty', 14),
    ('dbonus(10) sBasic(8) Difficulty', 14),
    ('1 2 3*4 5 6', 26),
    ('3*4 "flag"', '=12:"flag"'),
    ('repeat(4, _ + _i*_i)', '(0:#1, 1:#2, 4:#3, 9:#4)=14'),
    ('map(_+_i, ("a", "b", 5"c"))', '(0:"a", 1:"b", 7:"c")=8'),
    ('map(_+_i, "a", "b", 5"c")', '(0:"a", 1:"b", 7:"c")=8'),
    ('map(42, "a", "b", 5"c")', '(42:"a", 42:"b", 47:"c")'),
    ('map(_i*cond(flag(_, "b"), 10), ("a", "b", "c", "b"))', 40), 
    ('map $ _*2, 10, 11, 12', '(20, 22, 24)=66'),
    ('with(pool=15, attacks=3, repeat(attacks, d(pool - _n - _i, 1)))', r'/12d1.*11d1.*10d1.*=33/'),
    ('len $ 3d6, 1, 2, 3', 4),
    ('d1 + 2*2 + 1', '+5=6'),
    ('d1 + 2*d1 + 1', '+2*d1(1)+1=4'),
    ('d1 + d1*2 + 1', '+d1(1)*2+1=4'),
    ('withEnh4 (Enh+1, Enh+2)', '(5, 6)=11'),
    ('withEnhFour (Enh+1, Enh+2)', '(5, 6)=11'),
    ('withEnhFour Enh+1, Enh+2', '(5, 6)=11'),
    ('with(X=Enh, withEnh(7) X)', 2),
    ('with(X==Enh, withEnh(7) X)', 7),
    ('with(X==Enh, withEnh(X) X)', 2),

    # Expected errors
    ('10d6b7', 'ParseError'),
    ('Recursive + 2', 'ParseError'),
    ('50x(50d6)', 'ParseError'),
    ('Enh xyz', 'missing operator'),
    ('if(1==2, 3, mul(2,3)', r'/ParseError.*Missing closing parenthesis/'),
    ('Nonexistent Thing', r'/ParseError.*Nonexistent Thing/'),
    ('with(x=2, x) + x', r'/ParseError: Symbol "x" not found/'),
    ('with(x=2, x, y)', r'/ParseError: Binding term "x"/'),
    ('with(X==Enh, with(Enh==X, X))', r'/ParseError: Recursive/'),
  ]

  # FIXME: put into proper test
  for k in ['$es$', 'a$bb$c']:
    print "expand:", sym[k].name(k), sym[k].expansion

  args = sys.argv[1:]
  if args:
    DEBUG_PARSER = True
    tests = [(x, 0) for x in args]

  ok = 0
  bad = 0
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
    if hasattr(expected, 'iterfind'):
      if expected.search(str):
        status='pass'
    if isinstance(expected, basestring):
      m = re.search(r'^/(.*)/$', expected)
      if m:
        pattern = re.compile(m.group(1))
	if pattern.search(result_str):
	  status='pass'
      elif expected in result_str:
        status='pass'
    else:
      if result_val == expected:
        status='pass'
    if status == 'FAIL':
      bad += 1
      print status, expr, result_str, '# got %s, expected %s' % (result_val, repr(expected))
    else:
      ok += 1
      print status, expr, result_str

  print '%d ok, %d fail, ran %d/%d' % (ok, bad, ok+bad, len(tests))
  assert ok>0, 'TEST DRIVER BROKEN'
  assert bad==0, 'FAILING TESTS'
