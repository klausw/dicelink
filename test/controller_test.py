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

import logging
import unittest

import controller

class ControllerTest(unittest.TestCase):
  def test_already_evaluated(self):
    self.assertFalse(controller.already_evaluated('[if(d100>=0, 100+22, 33)]'))
    self.assertFalse(controller.already_evaluated('[with(L=("a", "b"), nth(0, L))]'))
    self.assertFalse(controller.already_evaluated('[if(2==(1+1), "yes", "no")]'))
    self.assertFalse(controller.already_evaluated('[with(r=1, 2]')) # unbalanced parens

    self.assertTrue(controller.already_evaluated('[d100+4 d100(101)+4=105]'))
    self.assertTrue(controller.already_evaluated('[Roll(4) =4]'))
    self.assertTrue(controller.already_evaluated('[Roll(4) =4:"with(Parens)"]'))
    self.assertTrue(controller.already_evaluated('[if(2==(1+1), "yes", "no") ="yes"]'))

  def test_anchors(self):
    self.assertEqual(controller.fix_anchor(' abc', 1, 4), (1, 4))
    self.assertEqual(controller.fix_anchor(' abc\n', 1, 5), (1, 4))

    self.assertEqual(controller.fix_anchor(' \n', 1, 2), (1, 1))
    self.assertEqual(controller.fix_anchor(' \nabc', 1, 5), (1, 1))
    self.assertEqual(controller.fix_anchor('  \n', 1, 3), (1, 1))
    self.assertEqual(controller.fix_anchor('  \nabc', 1, 6), (1, 1))

if __name__ == '__main__':
  logging.getLogger().setLevel(logging.DEBUG)
  unittest.main()

