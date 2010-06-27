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
	  (?P<reroll_limit> \d+ )
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
    if not dict['output']:
      out.append(dict)
  return out

MAX_NUM=1000
MAX_SIDES=100
MAX_REROLL_LIMIT=5

def RollDice(spec):
  num = int(spec['num'])
  if num == 0:
    num = 1
  sides = int(spec['sides'])
  reroll_limit = int(spec['reroll_limit'])
  delta = int(spec['delta'])

  # some sanity checks to help prevent CPU burning abuse
  if num > MAX_NUM:
    return 0, ('Error: number of dice must be <= %d' % MAX_NUM)
  if sides > MAX_SIDES:
    return 0, ('Error: number of sides must be <= %d' % MAX_SIDES)
  if reroll_limit > sides or reroll_limit > MAX_REROLL_LIMIT:
    return 0, ('Error: reroll_limit number must be <= number of sides and <= %d' % MAX_REROLL_LIMIT)

  detail = []
  result = 0
  for n in xrange(num):
    rolls = []
    while True:
      roll = random.randint(1, sides)
      rolls.append(str(roll))
      if roll >= reroll_limit:
        result += roll
        detail.append('\\'.join(rolls))
	break

  result += delta

  return result, ','.join(detail)

def RollDie(spec):
  matches = GetRollMatches(spec)
  if matches:
    return RollDice(matches[0])
  else:
    return int(spec), spec

if __name__ == '__main__':
  random.seed(42)
  for spec in GetRollMatches('d6, 2d6+10, 6d8b2+10'):
    print repr(spec)
    result, detail = RollDice(spec)
    print '%s: %d (%s)' % (spec['spec'], result, detail)
