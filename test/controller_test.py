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

if __name__ == '__main__':
  logging.getLogger().setLevel(logging.DEBUG)
  unittest.main()

