import sys
sys.path.append('.')
sys.path.append('..')

import unittest
import logging
import re

import mockblip

CONTENT_ASSERT_RE = re.compile('^(.*) \#\% \s* (.*)$', re.X)
class BlipTest(unittest.TestCase):
  def test_blips(self):
    context = mockblip.MakeContext()
    for blip in mockblip.BlipIterator(context):
      out = mockblip.doBlip(blip, context)
      for line in out.split('\n'):
	m = CONTENT_ASSERT_RE.search(line)
	if m:
	  actual = m.group(1)
	  expected = m.group(2)
	  #logging.info('expected=%s actual=%s', repr(expected), repr(actual))
	  self.assertTrue(expected in actual, '%s is not in %s' % (repr(expected), repr(actual)))
	
      self.assertTrue(out, 'No result for test blip: %s' % repr(out))

if __name__ == '__main__':
  logging.getLogger().setLevel(logging.DEBUG)
  unittest.main()

