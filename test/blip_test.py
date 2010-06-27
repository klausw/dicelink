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

