# Copyright (c) 2015-2018 by the parties listed in the AUTHORS file.
# All rights reserved.  Use of this source code is governed by
# a BSD-style license that can be found in the LICENSE file.

from ..mpi import MPI
from .mpi import MPITestCase

import sys
import os

import numpy as np
import numpy.testing as nt

import scipy.interpolate as si

from ..tod import OpMemoryCounter
from ..tod.tod import *
from ..tod.pointing import *
from ..tod.noise import *
from ..tod.sim_noise import *
from ..tod.sim_det_noise import *
from ..tod.sim_tod import *

from .. import rng as rng

from ._helpers import (create_outdir, create_distdata, boresight_focalplane,
    uniform_chunks)


class OpMemoryCounterTest(MPITestCase):

    def setUp(self):
        fixture_name = os.path.splitext(os.path.basename(__file__))[0]
        self.outdir = create_outdir(self.comm, fixture_name)

        # One observation per group
        self.data = create_distdata(self.comm, obs_per_group=1)

        # Detector properties.  We place one detector per process at the
        # boresight with evenly spaced polarization orientations.

        self.ndet = 4
        self.NET = 5.0
        self.rate = 20.0

        # Create detectors with default properties.
        dnames, dquat, depsilon, drate, dnet, dfmin, dfknee, dalpha = \
            boresight_focalplane(self.ndet, samplerate=self.rate, net=self.NET)

        # Total samples per observation
        self.totsamp = 100000

        # Chunks
        chunks = uniform_chunks(self.totsamp, nchunk=self.data.comm.group_size)

        # Populate the observations

        tod = TODHpixSpiral(
            self.data.comm.comm_group,
            dquat,
            self.totsamp,
            detranks=1,
            firsttime=0.0,
            rate=self.rate,
            nside=512,
            sampsizes=chunks)

        # construct an analytic noise model

        nse = AnalyticNoise(
            rate=drate,
            fmin=dfmin,
            detectors=dnames,
            fknee=dfknee,
            alpha=dalpha,
            NET=dnet
        )

        self.data.obs[0]["tod"] = tod
        self.data.obs[0]["noise"] = nse


    def test_counter(self):
        ob = self.data.obs[0]
        tod = ob['tod']
        # Ensure timestamps are cached before simulating noise
        blah = tod.local_times()
        del blah

        counter = OpMemoryCounter(silent=True)

        tot_old = counter.exec(self.data)

        # generate timestreams
        op = OpSimNoise()
        op.exec(self.data)

        tot_new = counter.exec(self.data)

        expected = self.data.comm.ngroups * self.totsamp * self.ndet * 8

        np.testing.assert_equal(tot_new - tot_old, expected)

        return
