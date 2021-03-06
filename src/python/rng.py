# Copyright (c) 2015-2018 by the parties listed in the AUTHORS file.
# All rights reserved.  Use of this source code is governed by 
# a BSD-style license that can be found in the LICENSE file.


import numpy as np

from . import timing as timing
from .ctoast import ( rng_dist_uint64, rng_dist_uniform_01,
    rng_dist_uniform_11, rng_dist_normal,
    rng_dist_uint64_mt, rng_dist_uniform_01_mt,
    rng_dist_uniform_11_mt, rng_dist_normal_mt)


def random(samples, counter=(0,0), sampler="gaussian", key=(0,0)):
    """
    High level interface to internal Random123 library.

    This provides an interface for calling the internal functions to generate
    random values from common distributions.

    Args:
        samples (int): The number of samples to return.
        counter (tuple): Two uint64 values which (along with the key) define
            the starting state of the generator.
        sampler (string): The distribution to sample from.  Allowed values are
            "gaussian", "uniform_01", "uniform_m11", and "uniform_uint64".
        key (tuple): Two uint64 values which (along with the counter) define
            the starting state of the generator.
    Returns:
        array: The random values of appropriate type for the sampler.
    """
    autotimer = timing.auto_timer()
    ret = None
    if sampler == "gaussian":
        ret = rng_dist_normal(samples, key[0], key[1], counter[0], counter[1])
    elif sampler == "uniform_01":
        ret = rng_dist_uniform_01(samples, key[0], key[1], counter[0], counter[1])
    elif sampler == "uniform_m11":
        ret = rng_dist_uniform_11(samples, key[0], key[1], counter[0], counter[1])
    elif sampler == "uniform_uint64":
        ret = rng_dist_uint64(samples, key[0], key[1], counter[0], counter[1])
    else:
        raise ValueError("Undefined sampler. Choose among: gaussian, uniform_01, uniform_m11, uniform_uint64")
    return ret

import ctypes as ct
import numpy as np
import numpy.ctypeslib as npc

def random_mt(blocks, samples, counter=[(0,0)], sampler="gaussian", key=[(0,0)]):
    """
    High level interface to internal Random123 library.

    This provides an interface for calling the internal functions to generate
    random values from common distributions.

    Args:
        samples (int): The number of samples to return.
        counter (tuple): Two uint64 values which (along with the key) define
            the starting state of the generator.
        sampler (string): The distribution to sample from.  Allowed values are
            "gaussian", "uniform_01", "uniform_m11", and "uniform_uint64".
        key (tuple): Two uint64 values which (along with the counter) define
            the starting state of the generator.
    Returns:
        array: The random values of appropriate type for the sampler.
    """
    autotimer = timing.auto_timer()
    nkeys = len(key)
    nctrs = len(counter)
    
    key0 = np.zeros(blocks, dtype=np.uint64)
    key1 = np.zeros(blocks, dtype=np.uint64)
    ctr0 = np.zeros(blocks, dtype=np.uint64)
    ctr1 = np.zeros(blocks, dtype=np.uint64)

    for i in range(0, blocks):
        key0[i] = key[i%nkeys][0]
        key1[i] = key[i%nkeys][1]
        ctr0[i] = counter[i%nctrs][0]
        ctr1[i] = counter[i%nctrs][1]
        
    ret = None
    if sampler == "gaussian":
        ret = rng_dist_normal_mt(ct.c_ulong(blocks), ct.c_ulong(samples),
                                 key0, key1, ctr0, ctr1)
    elif sampler == "uniform_01":
        ret = rng_dist_uniform_01_mt(ct.c_ulong(blocks), ct.c_ulong(samples),
                                     key0, key1, ctr0, ctr1)
    elif sampler == "uniform_m11":
        ret = rng_dist_uniform_11_mt(ct.c_ulong(blocks), ct.c_ulong(samples),
                                     key0, key1, ctr0, ctr1)
    elif sampler == "uniform_uint64":
        ret = rng_dist_uint64_mt(ct.c_ulong(blocks), ct.c_ulong(samples),
                                 key0, key1, ctr0, ctr1)
    else:
        raise ValueError("Undefined sampler. Choose among: gaussian, uniform_01, uniform_m11, uniform_uint64")
    return ret
