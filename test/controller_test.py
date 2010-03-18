import sys
sys.path.append('.')
sys.path.append('..')

import logging
import unittest

import controller

class ControllerTest(unittest.TestCase):
  def test_already_evaluated(self):
    self.assertFalse(controller.already_evaluated('[if(d100>=0, 100+22, 33)]'))
    self.assertTrue(controller.already_evaluated('[d100+4 d100(101)+4=105]'))
    self.assertTrue(controller.already_evaluated('[Roll(4) =4]'))
    self.assertTrue(controller.already_evaluated('[Roll(4) =4:"with(Parens)"]'))

if __name__ == '__main__':
  logging.getLogger().setLevel(logging.DEBUG)
  unittest.main()

