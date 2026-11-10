import unittest
from workbench.domain import *

class DomainBoundaryTests(unittest.TestCase):
    def test_boundaries(self):
        with self.assertRaises(ValueError):standard_u(1,0)
        self.assertEqual(merge_ranges([[10,20],[0,10],[30,40]]),[[0,20],[30,40]])
        with self.assertRaises(ValueError):merge_ranges([[2,1]])
        self.assertEqual(capacity([{'lab':'a','date':'d'}],{}),{'a@d':1})
        self.assertEqual(cmc(0,'0.1','0.02',2),'0.01')
