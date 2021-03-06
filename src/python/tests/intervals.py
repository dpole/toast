# Copyright (c) 2015-2018 by the parties listed in the AUTHORS file.
# All rights reserved.  Use of this source code is governed by
# a BSD-style license that can be found in the LICENSE file.

from ..mpi import MPI
from .mpi import MPITestCase

import sys
import os

import numpy as np
import numpy.testing as nt

from ..dist import *
from ..tod.interval import *
from ..tod.sim_interval import *


class IntervalTest(MPITestCase):

    def setUp(self):
        self.rate = 123.456
        self.duration = 24 * 3601.23
        self.gap = 3600.0
        self.start = 5432.1
        self.first = 10
        self.nint = 3


    def test_tochunks(self):
        intrvls = regular_intervals(self.nint, self.start, self.first,
            self.rate, self.duration, self.gap)
        totsamp = self.nint * (intrvls[0].last - intrvls[0].first + 1)
        totsamp += self.nint * (intrvls[1].first - intrvls[0].last - 1)
        sizes = intervals_to_chunklist(intrvls, totsamp,
            startsamp=self.first+10)
        # for it in intrvls:
        #     print(it.first," ",it.last," ",it.start," ",it.stop)
        # print(sizes)
        nt.assert_equal(np.sum(sizes), totsamp)


    def test_regular(self):
        intrvls = regular_intervals(self.nint, self.start, self.first,
                                    self.rate, self.duration, self.gap)

        goodsamp = self.nint * ( int(self.duration * self.rate) + 1 )

        check = 0

        for it in intrvls:
            #print(it.first," ",it.last," ",it.start," ",it.stop)
            check += it.last - it.first + 1

        nt.assert_equal(check, goodsamp)
        return
