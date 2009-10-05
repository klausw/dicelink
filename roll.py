import re
import random

# Examples:
# d6
# 2d6+10
# 6d8b2+10
ROLL_RE = re.compile(r'''
      (?P<spec>
        (?P<num> \d+ )?        # {6}d8b2+10, optional
	d                      # 6{d}8b2+10
	(?P<sides> \d+ )       # 6d{8}b2+10
	(?:                    # 6d8{b(2)}+10, optional
	  b
	  (?P<brutal> \d+ )
	)?
	(?P<delta> [+-]\d+ )?  # 6d8b2{+10}, optional
      )
      (?P<output>              # 6d8b2+10{=33 [...]}
        = \d+
	(?:
	  \s*
	  \[
	    [^]]*
	  \]
	)?
      )?
	''', re.X)

def GetRollMatches(txt):
  out = []
  for m in ROLL_RE.finditer(txt):
    dict = m.groupdict(0)
    dict['start'], dict['end'] = m.span()
    out.append(dict)
  return out

MAX_NUM=1000
MAX_SIDES=100
MAX_BRUTAL=5

def RollDice(spec):
  num = int(spec['num'])
  if num == 0:
    num = 1
  sides = int(spec['sides'])
  brutal = int(spec['brutal'])
  delta = int(spec['delta'])

  # some sanity checks to help prevent CPU burning abuse
  if num > MAX_NUM:
    return 0, ('Error: number of dice must be <= %d' % MAX_NUM)
  if sides > MAX_SIDES:
    return 0, ('Error: number of sides must be <= %d' % MAX_SIDES)
  if brutal > sides or brutal > MAX_BRUTAL:
    return 0, ('Error: brutal number must be <= number of sides and <= %d' % MAX_BRUTAL)

  detail = []
  result = 0
  for n in xrange(num):
    while True:
      roll = random.randint(1, sides)
      if roll < brutal:
        detail.append('(%d)' % roll)
      else:
        result += roll
        detail.append('%d,' % roll)
	break

  result += delta
  detail.append('%+d' % delta)

  return result, ''.join(detail)

if __name__ == '__main__':
  random.seed(42)
  for spec in GetRollMatches('d6, 2d6+10, 6d8b2+10=33 [foo]'):
    print repr(spec)
    result, detail = RollDice(spec)
    print '%s: %d [%s]' % (spec['spec'], result, detail)
