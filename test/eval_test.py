import sys
sys.path.append('.')
sys.path.append('..')

import unittest
import eval
import random
import logging
import re
import os

#from google.appengine.ext import db

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
    'e$$': eval.Function(['Count', 'TN'], 'count(>= TN, explode(d(Count, 6)))'),
    '$es$': eval.Function(['x', 'y'], 'e(x,y)'),
    'fact$': eval.Function(['n'], 'if(n <= 1, n, mul(n, fact(n - 1)))'),
    'fib$': eval.Function(['n'], 'if(n==0, 0, if(n==1, 1, fib(n-1) + fib(n-2)))'),
    'a$bb$c': eval.Function(['x', 'y'], 'x+y'),
    'bw$$': eval.Function(['n', 'TN'], 'with(roll=sort(d(n, 6)), if(n==0, 0, count(>=TN, roll) + bw(count(==6, roll), TN)))'),
    'W': '1',
    'Sword': 'd(W, 8) + 4',
    'Dagger': 'd(W, 4) + 2',
    '$W': eval.Function(['n'], 'with(W=n, Weapon)'),
    'Weapon': 'Sword',
    'Strike': '1W + StrMod',
    'Destroy': '2W + StrMod',
    'conflicttest$': eval.Function(['x'], '"my value"'),
    'MeleeBonus': 'Enh + StrP',
    'withEnhFour': 'with(Enh=4, $)',
    'withEnhUnicode': u'with(Enh=4, $)',
    'withEnh$': eval.Function(['N'], 'with(Enh=N, $)'),
    'withStr$': eval.Function(['Str'], '$'),
    'L10': 'val(d10-1)',
    'SuccessMarker$$': eval.Function(['TN', 'roll'], 'if(roll <= TN, "success {roll} vs {TN} doS:{(TN-roll)/10}", "failure {roll} vs {TN} doF:{(roll-TN)/10}")'),
    'Difficulty': 0,
    'sBasic$': eval.Function(['Stat'], 'with(Difficulty=Difficulty+Stat/2,$)'), 
    'dbonus$': eval.Function(['n'], 'with(Difficulty=Difficulty+n, $)'),
    'blast': eval.Function([], 'map($)'),
    'MaxFlag': 0,
    'maybeMax': 'if(MaxFlag, max($), $)',
    'useMax': 'with(MaxFlag=1, $)',
  }

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
    ('max(3, 7)', 7),
    ('max(3, 11, 7)', 11),
    ('min(3, 11, 7)', 3),
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
    ('maybeMax d10+d6', 13),
    ('useMax maybeMax d10+d6', 16),
    ('maybeMax, useMax maybeMax, maybeMax', 0),

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
    ('with(L=("a", "b", "c", "a"), count(=="a", L))', 2),
    ('with(L=("a", "b", "c", "a"), pick(=="a", L))', '("a", /*"b"*/, /*"c"*/, "a")'),
    ('with(L=("a", "b", "c", "a"), filter(_=="a", L))', '("a", "a")'),
    ('with(L=("a", "b", "c", "a"), filter(=="a", L))', '("a", "a")'),
    ('with(L=("a", "b", "c", "a"), len(L))', 4),
    ('with(L=("a", "b", "c", "a"), len(pick(=="a", L)))', 2),
    ('with(L=("a", "b", "c", "a"), count(=="a", L))', 2),
    ('with(L=list(("a", 11), ("b", 12)), len(L))', 2),
    ('with(L=list(("a", 11), ("b", 12)), nth(1, nth(0, filter(nth(0, _)=="a", L))))', 11),
    ('with(L=list(("a", 11), ("b", 12)), filter(nth(0, _)=="a", L))', 11),
    ('with(a=(0, 1), b=(2, 3), concat(a, b))', '(0, 1, 2, 3)=6'),
    ('with(a=(0, 1), b=(2, 3), append(a, b))', '(0, 1, (2, 3)=5)=6'),

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
    ('with(r=1, 2', r'/ParseError: Missing closing parenthesis/'),
  ]

class EvalTest(unittest.TestCase):
  def test_sym(self):
    sym_tests = [
      ('Deft Strike', 'd4+4'),
      ('Foo', None),
      ('Not Deft Strike', None),
      ('Sneak Attack', '2d8+7'),
    ]
    for name, result in sym_tests:
      self.assertEqual(eval.LookupSym(name, sym), result, 'symbol lookup %s != %s' % (repr(name), repr(result)))
    # FIXME: put into proper test
    #for k in ['$es$', 'a$bb$c']:
    #  print "expand:", sym[k].name(k), sym[k].expansion


  def test_eval(self):
    random.seed(2) # specially picked, first d20 gets a 20

    ok = 0
    bad = 0

    for expr, expected in tests:
      result_str = 'Error'
      result_val = None
      try:
	result = eval.ParseExpr(expr, sym, env)
	result_val = result.value()
	result_str = str(result)
      except eval.ParseError, e:
	result_str = e.__class__.__name__ + ': ' + str(e)
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
      else:
	ok += 1
	logging.debug("%s %s %s", status, expr, result_str)
      self.assertEqual(status, 'pass', '%s %s # got %s, expected %s' % (expr, result_str, result_val, repr(expected)))

    self.assert_(ok>0, 'TEST DRIVER BROKEN, no passing tests')
    self.assertEqual(bad, 0, 'FAILING TESTS')

if __name__ == '__main__':
  if 'DEBUG' in os.environ:
    logging.getLogger().setLevel(logging.DEBUG)
  unittest.main()
