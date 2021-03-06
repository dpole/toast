#!/usr/bin/env python3

# Copyright (c) 2015-2018 by the parties listed in the AUTHORS file.
# All rights reserved.  Use of this source code is governed by
# a BSD-style license that can be found in the LICENSE file.

# This script creates a CES schedule file that can be used as input
# to toast_ground_sim.py

import argparse
from datetime import datetime
import os

import dateutil.parser
from pylab import cm
from scipy.constants import degree

import ephem
import healpy as hp
import numpy as np
import toast.qarray as qa
import toast.timing as timing

XAXIS, YAXIS, ZAXIS = np.eye(3)


class TooClose(Exception):
    pass


class SunTooClose(TooClose):
    pass


class MoonTooClose(TooClose):
    pass


class Patch(object):

    hits = 0
    rising_hits = 0
    setting_hits = 0
    time = 0
    rising_time = 0
    setting_time = 0
    step = -1
    az_min = 0
    _area = None
    current_el_min = 0
    current_el_max = 0

    def __init__(self, name, weight, corners,
                 el_min=0, el_max=np.pi / 2, el_step=0,
                 alternate=False, site_lat=0, area=None):
        self.name = name
        self.weight = weight
        self.corners = corners
        self.el_min0 = el_min
        self.el_min = el_min
        self.el_max0 = el_max
        self.el_step = el_step
        self.alternate = alternate
        self._area = area
        # Use the site latitude to infer the lowest elevation that all
        # corners cross.
        self.site_lat = site_lat
        for corner in corners:
            el_max = np.pi / 2 - np.abs(corner._dec - self.site_lat)
            if el_max < self.el_max0:
                self.el_max0 = el_max
        self.el_max = self.el_max0
        self.el_lim = self.el_min0
        self.step_azel()

    def get_area(self, observer, nside=32, equalize=False):
        if self._area is None:
            autotimer = timing.auto_timer()
            npix = 12 * nside ** 2
            hitmap = np.zeros(npix)
            for corner in self.corners:
                corner.compute(observer)
            for pix in range(npix):
                lon, lat = hp.pix2ang(nside, pix, lonlat=True)
                center = ephem.FixedBody()
                center._ra = np.radians(lon)
                center._dec = np.radians(lat)
                center.compute(observer)
                hitmap[pix] = self.in_patch(center)
            self._area = np.sum(hitmap) / hitmap.size
            del autotimer
        if self._area == 0:
            raise RuntimeError('Patch has zero area!')
        if equalize:
            self.weight /= self._area
        return self._area

    def corner_coordinates(self, observer=None, unwind=False):
        """ Return the corner coordinates in horizontal frame.

        PyEphem measures the azimuth East (clockwise) from North.
        """
        autotimer = timing.auto_timer()
        azs = []
        els = []
        az0 = None
        for corner in self.corners:
            if observer is not None:
                corner.compute(observer)
            if unwind:
                if az0 is None:
                    az0 = corner.az
                azs.append(unwind_angle(az0, corner.az))
            else:
                azs.append(corner.az)
            els.append(corner.alt)
        del autotimer
        return np.array(azs), np.array(els)

    def in_patch(self, obj):
        """
        Determine if the object (e.g. Sun or Moon) is inside the patch
        by using a ray casting algorithm.  The ray is cast along a
        constant meridian to follow a great circle.
        """
        autotimer = timing.auto_timer()
        az0 = obj.az
        # Get corner coordinates, assuming they were already computed
        azs, els = self.corner_coordinates()
        els_cross = []
        for i in range(len(self.corners)):
            az1 = azs[i]
            el1 = els[i]
            j = (i + 1) % len(self.corners)
            az2 = unwind_angle(az1, azs[j])
            el2 = els[j]
            azmean = .5 * (az1 + az2)
            az0 = unwind_angle(azmean, np.float(obj.az), np.pi)
            if (az1 - az0) * (az2 - az0) > 0:
                # the constant meridian is not between the two corners
                continue
            el_cross = (el1 + (az1 - az0) * (el2 - el1) / (az1 - az2))
            if np.abs(obj.az - (az0 % (2 * np.pi))) < 1e-3:
                els_cross.append(el_cross)
            elif el_cross > 0:
                els_cross.append(np.pi - el_cross)
            else:
                els_cross.append(-np.pi - el_cross)

        els_cross = np.array(els_cross)
        if els_cross.size < 2:
            return False

        # Unwind the crossing elevations to minimize the scatter
        els_cross = np.sort(els_cross)
        if els_cross.size > 1:
            ptps = []
            for i in range(els_cross.size):
                els_cross_alt = els_cross.copy()
                els_cross_alt[:i] += 2 * np.pi
                ptps.append(np.ptp(els_cross_alt))
            i = np.argmin(ptps)
            if i > 0:
                els_cross[:i] += 2 * np.pi
                els_cross = np.sort(els_cross)
        el_mean = np.mean(els_cross)
        el0 = unwind_angle(el_mean, np.float(obj.alt))

        ncross = np.sum(els_cross > el0)

        if ncross % 2 == 0:
            # Even number of crossings means that the object is outside
            # of the patch
            return False
        del autotimer
        return True

    def step_azel(self):
        autotimer = timing.auto_timer()
        self.step += 1
        if self.el_step > 0 and self.alternate:
            # alternate between rising and setting scans
            if self.step % 2 == 0:
                # Schedule a rising scan
                self.el_min = self.el_lim
                self.el_max = self.el_max0
                if self.el_min >= self.el_max:
                    self.el_min = self.el_min0
                self.az_min = 0
            else:
                # Update the boundaries
                self.el_lim += self.el_step
                if self.el_lim > self.el_max0:
                    self.el_lim = self.el_min0
                # Schedule a setting scan
                self.el_min = self.el_min0
                self.el_max = self.el_lim
                if self.el_max <= self.el_min:
                    self.el_max = self.el_max0
                self.az_min = np.pi
        else:
            if self.alternate:
                self.az_min = (self.az_min + np.pi) % (2 * np.pi)
            else:
                self.el_min += self.el_step
                if self.el_min > self.el_max0:
                    self.el_min = self.el_min0
        del autotimer
        return

    def reset(self):
        self.step += 1
        self.el_min = self.el_min0
        self.az_min = 0


def to_JD(t):
    # Unix time stamp to Julian date
    # (days since -4712-01-01 12:00:00 UTC)
    return t / 86400. + 2440587.5


def to_MJD(t):
    # Convert Unix time stamp to modified Julian date
    # (days since 1858-11-17 00:00:00 UTC)
    return to_JD(t) - 2400000.5


def to_DJD(t):
    # Convert Unix time stamp to Dublin Julian date
    # (days since 1899-12-31 12:00:00)
    # This is the time format used by PyEphem
    return to_JD(t) - 2415020


def patch_is_rising(patch):
    rising = True
    for corner in patch.corners:
        if corner.alt > 0 and corner.az > np.pi:
            # The patch is setting
            rising = False
            break
    return rising


def prioritize(args, visible):
    """ Order visible targets by priority and number of scans.
    """
    autotimer = timing.auto_timer()
    for i in range(len(visible)):
        for j in range(len(visible) - i - 1):
            if patch_is_rising(visible[j]):
                if args.equalize_time:
                    hits1 = visible[j].rising_time
                else:
                    hits1 = visible[j].rising_hits
                el1 = np.degrees(visible[j].current_el_max)
            else:
                if args.equalize_time:
                    hits1 = visible[j].setting_time
                else:
                    hits1 = visible[j].setting_hits
                el1 = np.degrees(visible[j].current_el_min)
            if patch_is_rising(visible[j + 1]):
                if args.equalize_time:
                    hits2 = visible[j + 1].rising_time
                else:
                    hits2 = visible[j + 1].rising_hits
                el2 = np.degrees(visible[j + 1].current_el_max)
            else:
                if args.equalize_time:
                    hits2 = visible[j + 1].setting_time
                else:
                    hits2 = visible[j + 1].setting_hits
                el2 = np.degrees(visible[j + 1].current_el_min)
            # Patch with the lower weight goes first.  Having more
            # earlier observing time and lower observing elevation
            # will increase the weight.
            weight1 = (hits1 + 1) * visible[j].weight
            weight2 = (hits2 + 1) * visible[j + 1].weight
            if args.elevation_penalty_limit > 0:
                lim = args.elevation_penalty_limit
                if el1 < lim:
                    weight1 *= (lim / el1) ** args.elevation_penalty_power
                if el2 < lim:
                    weight2 *= (lim / el2) ** args.elevation_penalty_power
            if weight1 > weight2:
                visible[j], visible[j + 1] = visible[j + 1], visible[j]
    if args.debug:
        print('Prioritized list of viewable patches: ', end='')
        for patch in visible:
            print('{}, '.format(patch.name), end='')
        print(flush=True)
    del autotimer
    return


def attempt_scan(
        args, observer, visible, not_visible, t, fp_radius, tstep,
        stop_timestamp, sun, moon, sun_el_max, fout, fout_fmt, ods):
    """ Attempt scanning the visible patches in order until success.
    """
    autotimer = timing.auto_timer()
    success = False
    for patch in visible:
        for rising in [True, False]:
            observer.date = to_DJD(t)
            el = get_constant_elevation(
                args, observer, patch, rising, fp_radius, not_visible)
            if el is None:
                continue
            success, azmins, azmaxs, aztimes, tstop = scan_patch(
                args, el, patch, t, fp_radius, observer, sun, not_visible,
                tstep, stop_timestamp, sun_el_max, rising)
            if success:
                try:
                    t, _ = add_scan(
                        args, t, tstop, aztimes, azmins, azmaxs, rising,
                        fp_radius, observer, sun, moon, fout, fout_fmt,
                        patch, el, ods)
                    patch.step_azel()
                    break
                except TooClose:
                    success = False
                    break
        if success:
            break
    del autotimer
    return success, t


def from_angles(az, el):
    elquat = qa.rotation(YAXIS, np.radians(90 - el))
    azquat = qa.rotation(ZAXIS, np.radians(az))
    return qa.mult(azquat, elquat)


def unwind_quat(quat1, quat2):
    if np.sum(np.abs(quat1 - quat2)) > np.sum(np.abs(quat1 + quat2)):
        return -quat2
    else:
        return quat2


def check_sso(observer, az1, az2, el, sso, angle, tstart, tstop):
    """
    Check if a solar system object (SSO) enters within "angle" of
    the constant elevation scan.
    """
    autotimer = timing.auto_timer()
    if az2 < az1:
        az2 += 360
    naz = max(3, np.int(.25 * (az2 - az1) * np.cos(np.radians(el))))
    quats = []
    for az in np.linspace(az1, az2, naz):
        quats.append(from_angles(az % 360, el))
    vecs = qa.rotate(quats, ZAXIS)

    tstart = to_DJD(tstart)
    tstop = to_DJD(tstop)
    t1 = tstart
    # Test every hour separately
    while t1 < tstop:
        t2 = min(tstop, t1 + 1 / 24)
        observer.date = t1
        sso.compute(observer)
        sun_az1, sun_el1 = np.degrees(sso.az), np.degrees(sso.alt)
        observer.date = t2
        sso.compute(observer)
        sun_az2, sun_el2 = np.degrees(sso.az), np.degrees(sso.alt)
        sun_quat1 = from_angles(sun_az1, sun_el1)
        sun_quat2 = from_angles(sun_az2, sun_el2)
        sun_quat2 = unwind_quat(sun_quat1, sun_quat2)
        t = np.linspace(0, 1, 10)
        sun_quats = qa.slerp(t, [0, 1], [sun_quat1, sun_quat2])
        sun_vecs = qa.rotate(sun_quats, ZAXIS).T
        dpmax = np.amax(np.dot(vecs, sun_vecs))
        min_dist = np.degrees(np.arccos(dpmax))
        if min_dist < angle:
            return True
        t1 = t2
    del autotimer
    return False


def attempt_scan_pole(
        args, observer, visible, not_visible, tstart, fp_radius, el_max, el_min,
        tstep, stop_timestamp, sun, moon, sun_el_max, fout, fout_fmt, ods):
    """ Attempt scanning the visible patches in order until success.
    """
    autotimer = timing.auto_timer()
    success = False
    for patch in visible:
        observer.date = to_DJD(tstart)
        # In pole scheduling, first elevation is just below the patch
        el = get_constant_elevation_pole(
            args, observer, patch, fp_radius, el_min, el_max, not_visible)
        if el is None:
            continue
        pole_success = True
        subscan = -1
        t = tstart
        while pole_success:
            (pole_success, azmins, azmaxs, aztimes, tstop
             ) = scan_patch_pole(
                    args, el, patch, t, fp_radius, observer, sun,
                    not_visible, tstep, stop_timestamp, sun_el_max)
            if pole_success:
                if success:
                    # Still the same scan
                    patch.hits -= 1
                t, subscan = add_scan(
                    args, t, tstop, aztimes, azmins, azmaxs, False,
                    fp_radius, observer, sun, moon, fout, fout_fmt, patch,
                    el, ods, subscan=subscan)
                el += np.radians(args.pole_el_step)
                success = True
        if success:
            break
    tstop = t
    if args.one_scan_per_day:
        day1 = int(to_MJD(tstart))
        while int(to_MJD(tstop)) == day1:
            tstop += 60.
    del autotimer
    return success, tstop


def get_constant_elevation(args, observer, patch, rising, fp_radius,
                           not_visible):
    """ Determine the elevation at which to scan.
    """
    autotimer = timing.auto_timer()
    azs, els = patch.corner_coordinates(observer)
    el = None
    if rising:
        ind = azs <= np.pi
        if np.sum(ind) == 0:
            not_visible.append((patch.name, 'No rising corners'))
        else:
            el = np.amax(els[ind]) + fp_radius
    else:
        ind = azs >= np.pi
        if np.sum(ind) == 0:
            not_visible.append((patch.name, 'No setting corners'))
        else:
            el = np.amin(els[ind]) - fp_radius

    if el is not None:
        if el < patch.el_min:
            not_visible.append((
                patch.name, 'el < el_min ({:.2f} < {:.2f}) rising = {}'.format(
                    el / degree, patch.el_min / degree, rising)))
            el = None
        elif el > patch.el_max:
            not_visible.append((
                patch.name, 'el > el_max ({:.2f} > {:.2f}) rising = {}'.format(
                    el / degree, patch.el_max / degree, rising)))
            el = None
    if el is None and args.debug:
        print('NOT VISIBLE: {}'.format(not_visible[-1]))
    del autotimer
    return el


def get_constant_elevation_pole(args, observer, patch, fp_radius, el_min,
                                el_max, not_visible):
    """ Determine the elevation at which to scan.
    """
    autotimer = timing.auto_timer()
    _, els = patch.corner_coordinates(observer)
    el = np.amin(els) - fp_radius

    if el < el_min:
        not_visible.append((
            patch.name, 'el < el_min ({:.2f} < {:.2f})'.format(
                el / degree, el_min / degree)))
        el = None
    elif el > el_max:
        not_visible.append((
            patch.name, 'el > el_max ({:.2f} > {:.2f})'.format(
                el / degree, el_max / degree)))
        el = None
    if el is None and args.debug:
        print('NOT VISIBLE: {}'.format(not_visible[-1]))
    del autotimer
    return el


def scan_patch(args, el, patch, t, fp_radius, observer, sun, not_visible,
               tstep, stop_timestamp, sun_el_max, rising):
    """ Attempt scanning the patch specified by corners at elevation el.
    """
    autotimer = timing.auto_timer()
    success = False
    # and now track when all corners are past the elevation
    tstop = t
    to_cross = np.ones(len(patch.corners), dtype=np.bool)
    azmins, azmaxs, aztimes = [], [], []
    scan_started = False
    while True:
        tstop += tstep / 10
        if tstop > stop_timestamp or tstop - t > 86400:
            not_visible.append((patch.name, 'Ran out of time rising = {}'
                                ''.format(rising)))
            if args.debug:
                print('NOT VISIBLE: {}'.format(not_visible[-1]))
            break
        observer.date = to_DJD(tstop)
        if sun_el_max < np.pi / 2:
            sun.compute(observer)
            if sun.alt > sun_el_max:
                not_visible.append(
                    (patch.name, 'Sun too high {:.2f} rising = {}'
                     ''.format(np.degrees(sun.alt), rising)))
                if args.debug:
                    print('NOT VISIBLE: {}'.format(not_visible[-1]))
                break
        azs, els = patch.corner_coordinates(observer)
        has_extent = current_extent(azmins, azmaxs, aztimes, patch.corners,
                                    fp_radius, el, azs, els, rising, tstop)
        if has_extent:
            scan_started = True

        if rising:
            good = azs <= np.pi
            to_cross[np.logical_and(els > el + fp_radius, good)] = False
        else:
            good = azs >= np.pi
            to_cross[np.logical_and(els < el - fp_radius, good)] = False

        # If we are alternating rising and setting scans, reject patches
        # that appear on the wrong side of the sky.
        if patch.az_min > 0 and np.any((np.array(azmins) % (2 * np.pi))
                                       < patch.az_min):
            success = False
            break

        if not np.any(to_cross):
            # All corners made it across the CES line.
            success = True
            break

        if scan_started and not has_extent:
            # The patch went out of view before all corners
            # could cross the elevation line.
            success = False
            break
    del autotimer
    return success, azmins, azmaxs, aztimes, tstop


def unwind_angle(alpha, beta, multiple=2 * np.pi):
    """ Minimize absolute difference between alpha and beta.

    Minimize the absolute difference by adding a multiple of
    2*pi to beta to match alpha.
    """
    while np.abs(alpha - beta - multiple) < np.abs(alpha - beta):
        beta += multiple
    while np.abs(alpha - beta + multiple) < np.abs(alpha - beta):
        beta -= multiple
    return beta


def scan_patch_pole(args, el, patch, t, fp_radius, observer, sun, not_visible,
                    tstep, stop_timestamp, sun_el_max):
    """ Attempt scanning the patch specified by corners at elevation el.

    The pole scheduling mode will not wait for the patch to drift across.
    It simply attempts to scan for the required time: args.pole_ces_time.
    """
    autotimer = timing.auto_timer()
    success = False
    tstop = t
    azmins, azmaxs, aztimes = [], [], []
    while True:
        tstop += tstep / 10
        if tstop - t >= args.pole_ces_time:
            # Succesfully scanned the maximum time
            if len(azmins) > 0:
                success = True
            else:
                not_visible.append((patch.name, 'No overlap at {:.2f}'
                                    ''.format(el / degree)))
                if args.debug:
                    print('NOT VISIBLE: {}'.format(not_visible[-1]))
            break
        if tstop > stop_timestamp or tstop - t > 86400:
            not_visible.append((patch.name, 'Ran out of time'))
            if args.debug:
                print('NOT VISIBLE: {}'.format(not_visible[-1]))
            break
        observer.date = to_DJD(tstop)
        sun.compute(observer)
        if sun.alt > sun_el_max:
            not_visible.append((patch.name, 'Sun too high {:.2f}'
                                ''.format(sun.alt / degree)))
            if args.debug:
                print('NOT VISIBLE: {}'.format(not_visible[-1]))
            break
        azs, els = patch.corner_coordinates(observer)
        if np.amax(els) + fp_radius < el:
            not_visible.append((patch.name, 'Patch below {:.2f}'
                                ''.format(el / degree)))
            if args.debug:
                print('NOT VISIBLE: {}'.format(not_visible[-1]))
            break
        radius = max(np.radians(1), fp_radius)
        current_extent_pole(
            azmins, azmaxs, aztimes, patch.corners, radius, el, azs, els,
            tstop)
    del autotimer
    return success, azmins, azmaxs, aztimes, tstop


def current_extent_pole(
        azmins, azmaxs, aztimes, corners, fp_radius, el, azs, els, tstop):
    """ Get the azimuthal extent of the patch along elevation el.

    Pole scheduling does not care if the patch is "rising" or "setting".
    """
    autotimer = timing.auto_timer()
    azs_cross = []
    for i in range(len(corners)):
        if np.abs(els[i] - el) < fp_radius:
            azs_cross.append(azs[i])
        j = (i + 1) % len(corners)
        if np.abs(els[j] - el) < fp_radius:
            azs_cross.append(azs[j])
        if np.abs(els[i] - el) < fp_radius \
           or np.abs(els[j] - el) < fp_radius:
            continue
        elif (els[i] - el) * (els[j] - el) < 0:
            # Record the location where a line between the corners
            # crosses el.
            az1 = azs[i]
            az2 = azs[j]
            el1 = els[i] - el
            el2 = els[j] - el
            if az2 - az1 > np.pi:
                az1 += 2 * np.pi
            if az1 - az2 > np.pi:
                az2 += 2 * np.pi
            az_cross = (az1 + el1 * (az2 - az1) / (el1 - el2)) % (2 * np.pi)
            azs_cross.append(az_cross)

    # Translate the azimuths at multiples of 2pi so they are in a
    # compact cluster

    for i in range(1, len(azs_cross)):
        azs_cross[i] = unwind_angle(azs_cross[0], azs_cross[i])

    if len(azs_cross) > 0:
        azs_cross = np.sort(azs_cross)
        azmin = azs_cross[0]
        azmax = azs_cross[-1]
        azmax = unwind_angle(azmin, azmax)
        if azmax - azmin > np.pi:
            # Patch crosses the zero meridian
            azmin, azmax = azmax, azmin
        if len(azmins) > 0:
            azmin = unwind_angle(azmins[-1], azmin)
            azmax = unwind_angle(azmaxs[-1], azmax)
        azmins.append(azmin)
        azmaxs.append(azmax)
        aztimes.append(tstop)
    del autotimer
    return


def current_extent(azmins, azmaxs, aztimes, corners, fp_radius, el, azs, els,
                   rising, tstop):
    """ Get the azimuthal extent of the patch along elevation el.

    Find the pairs of corners that are on opposite sides
    of the CES line.  Record the crossing azimuth of a
    line between the corners.

    """
    autotimer = timing.auto_timer()
    azs_cross = []
    for i in range(len(corners)):
        j = (i + 1) % len(corners)
        for el0 in [el - fp_radius, el, el + fp_radius]:
            if (els[i] - el0) * (els[j] - el0) < 0:
                # The corners are on opposite sides of the elevation line
                az1 = azs[i]
                az2 = azs[j]
                el1 = els[i] - el0
                el2 = els[j] - el0
                az2 = unwind_angle(az1, az2)
                az_cross = (az1 + el1 * (az2 - az1) / (el1 - el2)) % (2 * np.pi)
                azs_cross.append(az_cross)
            if fp_radius == 0:
                break
    if len(azs_cross) == 0:
        return False

    azs_cross = np.array(azs_cross)
    if rising:
        good = azs_cross < np.pi
    else:
        good = azs_cross > np.pi
    ngood = np.sum(good)
    if ngood == 0:
        return False
    elif ngood > 1:
        azs_cross = azs_cross[good]

    # Unwind the crossing azimuths to minimize the scatter
    azs_cross = np.sort(azs_cross)
    if azs_cross.size > 1:
        ptp0 = azs_cross[-1] - azs_cross[0]
        ptps = azs_cross[:-1] + 2 * np.pi - azs_cross[1:]
        ptps = np.hstack([ptp0, ptps])
        i = np.argmin(ptps)
        azs_cross[:i] += 2 * np.pi
        np.roll(azs_cross, i)

    if len(azs_cross) > 1:
        azmin = azs_cross[0] % (2 * np.pi)
        azmax = azs_cross[-1] % (2 * np.pi)
        if azmax - azmin > np.pi:
            # Patch crosses the zero meridian
            azmin, azmax = azmax, azmin
        azmins.append(azmin)
        azmaxs.append(azmax)
        aztimes.append(tstop)
        return True
    del autotimer
    return False


def add_scan(args, tstart, tstop, aztimes, azmins, azmaxs, rising, fp_radius,
             observer, sun, moon, fout, fout_fmt, patch, el, ods, subscan=-1):
    """ Make an entry for a CES in the schedule file.
    """
    autotimer = timing.auto_timer()
    ces_time = tstop - tstart
    if ces_time > args.ces_max_time:  # and not args.pole_mode:
        nsub = np.int(np.ceil(ces_time / args.ces_max_time))
        ces_time /= nsub
    aztimes = np.array(aztimes)
    azmins = np.array(azmins)
    azmaxs = np.array(azmaxs)
    azmaxs[0] = unwind_angle(azmins[0], azmaxs[0])
    for i in range(1, azmins.size):
        azmins[i] = unwind_angle(azmins[0], azmins[i])
        azmaxs[i] = unwind_angle(azmaxs[0], azmaxs[i])
        azmaxs[i] = unwind_angle(azmins[i], azmaxs[i])
    # for i in range(azmins.size-1):
    #    if azmins[i+1] - azmins[i] > np.pi:
    #        azmins[i+1], azmaxs[i+1] = azmins[i+1]-2*np.pi, azmaxs[i+1]-2*np.pi
    #    if azmins[i+1] - azmins[i] < np.pi:
    #        azmins[i+1], azmaxs[i+1] = azmins[i+1]+2*np.pi, azmaxs[i+1]+2*np.pi
    rising_string = 'R' if rising else 'S'
    t1 = np.amin(aztimes)
    entries = []
    while t1 < tstop:
        subscan += 1
        if args.operational_days:
            # See if adding this scan would exceed the number of desired
            # operational days
            if subscan == 0:
                tz = args.timezone / 24
                od = int(to_MJD(tstart) + tz)
                ods.add(od)
            if len(ods) > args.operational_days:
                # Prevent adding further entries to the schedule once
                # the number of operational days is full
                break
        t2 = min(t1 + ces_time, tstop)
        if tstop - t2 < ces_time / 10:
            # Append leftover scan to the last full subscan
            t2 = tstop
        ind = np.logical_and(aztimes >= t1, aztimes <= t2)
        if np.all(aztimes > t2):
            ind[0] = True
        if np.all(aztimes < t1):
            ind[-1] = True
        if azmins[ind][0] < azmaxs[ind][0]:
            azmin = np.amin(azmins[ind])
            azmax = np.amax(azmaxs[ind])
        else:
            # we are, scan from the maximum to the minimum
            azmin = np.amax(azmins[ind])
            azmax = np.amin(azmaxs[ind])
        if args.scan_margin > 0:
            delta_az = azmax - unwind_angle(azmax, azmin)
            sub_az = delta_az * np.abs(np.random.randn()) * args.scan_margin \
                * .5
            add_az = delta_az * np.abs(np.random.randn()) * args.scan_margin \
                * .5
            azmin = (azmin - sub_az) % (2 * np.pi)
            azmax = (azmax + add_az) % (2 * np.pi)
            if t2 == tstop:
                delta_t = tstop - tstart
                add_t = delta_t * np.abs(np.random.randn()) * args.scan_margin
                t2 += add_t
        # Add the focal plane radius to the scan width
        fp_radius_eff = fp_radius / np.cos(el)
        azmin = (azmin - fp_radius_eff) % (2 * np.pi) / degree
        azmax = (azmax + fp_radius_eff) % (2 * np.pi) / degree
        ces_start = datetime.utcfromtimestamp(t1).strftime(
            '%Y-%m-%d %H:%M:%S %Z')
        ces_stop = datetime.utcfromtimestamp(t2).strftime(
            '%Y-%m-%d %H:%M:%S %Z')
        # Get the Sun and Moon locations at the beginning and end
        observer.date = to_DJD(t1)
        sun.compute(observer)
        moon.compute(observer)
        sun_az1, sun_el1 = sun.az / degree, sun.alt / degree
        moon_az1, moon_el1 = moon.az / degree, moon.alt / degree
        moon_phase1 = moon.phase
        observer.date = to_DJD(t2)
        sun.compute(observer)
        moon.compute(observer)
        sun_az2, sun_el2 = sun.az / degree, sun.alt / degree
        moon_az2, moon_el2 = moon.az / degree, moon.alt / degree
        # It is possible that the Sun or the Moon gets too close to the
        # scan, even if they are far enough from the actual patch.
        if check_sso(observer, azmin, azmax, el / degree, sun,
                     args.sun_avoidance_angle, t1, t2):
            if args.debug:
                print('Sun too close', flush=True)
            raise SunTooClose
        if check_sso(observer, azmin, azmax, el / degree, moon,
                     args.moon_avoidance_angle, t1, t2):
            if args.debug:
                print('Moon too close', flush=True)
            raise MoonTooClose
        moon_phase2 = moon.phase
        # Create an entry in the schedule
        entries.append(
            fout_fmt.format(
                ces_start, ces_stop, to_MJD(t1), to_MJD(t2),
                patch.name,
                azmin, azmax, el / degree,
                rising_string,
                sun_el1, sun_az1, sun_el2, sun_az2,
                moon_el1, moon_az1, moon_el2, moon_az2,
                0.005 * (moon_phase1 + moon_phase2), patch.hits, subscan))
        t1 = t2 + args.gap_small

    # Write the entries
    for entry in entries:
        if args.debug:
            print(entry)
        fout.write(entry)
    fout.flush()

    patch.hits += 1
    patch.time += ces_time
    if rising:
        patch.rising_hits += 1
        patch.rising_time += ces_time
    else:
        patch.setting_hits += 1
        patch.setting_time += ces_time

    # Advance the time
    tstop += args.gap
    del autotimer
    return tstop, subscan


def get_visible(args, observer, sun, moon, patches, el_min):
    """ Determine which patches are visible.
    """
    autotimer = timing.auto_timer()
    visible = []
    not_visible = []
    # DEBUG begin
    # import healpy as hp
    # import matplotlib.pyplot as plt
    # hp.mollview(np.zeros(12) + hp.UNSEEN, coord='C', cbar=False)
    # DEBUG end
    for patch in patches:
        # Reject all patches that have even one corner too close
        # to the Sun or the Moon and patches that are completely
        # below the horizon
        in_view = False
        patch_el_max = -1000
        patch_el_min = 1000
        # lons, lats = [], []  # DEBUG
        for i, corner in enumerate(patch.corners):
            corner.compute(observer)
            patch_el_min = min(patch_el_min, corner.alt)
            patch_el_max = max(patch_el_max, corner.alt)
            # lons.append(corner.az)  # DEBUG
            # lats.append(corner.alt)  # DEBUG
            if corner.alt > el_min:
                # At least one corner is visible
                in_view = True
            if not args.delay_sso_check:
                if args.sun_avoidance_angle > 0:
                    angle = np.degrees(ephem.separation(sun, corner))
                    if angle < args.sun_avoidance_angle:
                        # Patch is too close to the Sun
                        not_visible.append((
                            patch.name,
                            'Too close to Sun {:.2f}'.format(angle)))
                        in_view = False
                        break
                if args.moon_avoidance_angle > 0:
                    angle = np.degrees(ephem.separation(moon, corner))
                    if angle < args.moon_avoidance_angle:
                        # Patch is too close to the Moon
                        not_visible.append((
                            patch.name,
                            'Too close to Moon {:.2f}'.format(angle)))
                        in_view = False
                        break
            if i == len(patch.corners) - 1 and not in_view:
                not_visible.append((
                    patch.name,
                    'Below el_min = {:.2f} at el = {:.2f}..{:.2f}.'.format(
                        np.degrees(el_min), np.degrees(patch_el_min),
                        np.degrees(patch_el_max))))
        # DEBUG begin
        # if patch.name in ['north', 'south']:
        #    color, lw = 'red', 4
        # else:
        #    color, lw = 'black', 2
        # hp.projplot(np.degrees(lons), np.degrees(lats), '-', threshold=1,
        #            lonlat=True, coord='C', color=color, lw=lw)
        # DEBUG end
        if in_view:
            patch.current_el_min = patch_el_min
            patch.current_el_max = patch_el_max
            if not args.delay_sso_check:
                # Finally, check that the Sun or the Moon are not
                # inside the patch
                if args.moon_avoidance_angle >= 0 and patch.in_patch(moon):
                    not_visible.append((patch.name, 'Moon in patch'))
                    in_view = False
                if args.sun_avoidance_angle >= 0 and patch.in_patch(sun):
                    not_visible.append((patch.name, 'Sun in patch'))
                    in_view = False
        if in_view:
            visible.append(patch)
            if args.debug:
                print('In view: {}. el = {:.2f}..{:.2f}'.format(
                    patch.name, np.degrees(patch_el_min),
                    np.degrees(patch_el_max)), flush=True)
        else:
            if args.debug:
                print('NOT VISIBLE: {}'.format(not_visible[-1]))
    # DEBUG begin
    # import pdb
    # pdb.set_trace()
    # DEBUG end
    del autotimer
    return visible, not_visible


def build_schedule(
        args, start_timestamp, stop_timestamp, patches, observer, sun, moon):
    autotimer = timing.auto_timer()
    sun_el_max = args.sun_el_max * degree
    el_min = args.el_min * degree
    el_max = args.el_max * degree
    fp_radius = args.fp_radius * degree

    fname_out = args.out
    dir_out = os.path.dirname(fname_out)
    if not os.path.isdir(dir_out):
        print('Creating output directory: {}'.format(dir_out), flush=True)
        os.makedirs(dir_out)
    fout = open(fname_out, 'w')

    fout.write('#{:15} {:15} {:>15} {:>15} {:>15}\n'.format(
        'Site', 'Telescope',
        'Latitude [deg]', 'Longitude [deg]', 'Elevation [m]'))
    fout.write(' {:15} {:15} {:15.3f} {:15.3f} {:15.1f}\n'.format(
        args.site_name, args.telescope, np.degrees(observer.lat),
        np.degrees(observer.lon), observer.elevation))

    fout_fmt0 = '#{:20} {:20} {:14} {:14} ' \
                '{:35} {:8} {:8} {:8} {:5} ' \
                '{:8} {:8} {:8} {:8} ' \
                '{:8} {:8} {:8} {:8} {:5} ' \
                '{:5} {:3}\n'

    fout_fmt = ' {:20} {:20} {:14.6f} {:14.6f} ' \
               '{:35} {:8.2f} {:8.2f} {:8.2f} {:5} ' \
               '{:8.2f} {:8.2f} {:8.2f} {:8.2f} ' \
               '{:8.2f} {:8.2f} {:8.2f} {:8.2f} {:5.2f} ' \
               '{:5} {:3}\n'

    fout.write(
        fout_fmt0.format(
            'Start time UTC', 'Stop time UTC', 'Start MJD', 'Stop MJD',
            'Patch name', 'Az min', 'Az max', 'El', 'R/S',
            'Sun el1', 'Sun az1', 'Sun el2', 'Sun az2',
            'Moon el1', 'Moon az1', 'Moon el2', 'Moon az2', 'Phase',
            'Pass', 'Sub'))

    t = start_timestamp
    tstep = 600

    # Operational days
    ods = set()

    last_successful = t
    while t < stop_timestamp:
        if t - last_successful > 86400:
            # Reset the individual patch az and el limits
            for patch in patches:
                patch.reset()
            # Only try this once for every day
            t, last_successful = last_successful, t

        # Determine which patches are observable at time t.

        if args.debug:
            tstring = datetime.utcfromtimestamp(t).strftime(
                '%Y-%m-%d %H:%M:%S %Z')
            print('t =  {}'.format(tstring), flush=True)
        # Determine which patches are visible
        observer.date = to_DJD(t)
        sun.compute(observer)
        if sun.alt > sun_el_max:
            if args.debug:
                print('Sun elevation is {:.2f} > {:.2f}. Moving on.'.format(
                    sun.alt / degree, sun_el_max / degree), flush=True)
            t += tstep
            continue
        moon.compute(observer)

        visible, not_visible = get_visible(
            args, observer, sun, moon, patches, el_min)

        if len(visible) == 0:
            if args.debug:
                tstring = datetime.utcfromtimestamp(t).strftime(
                    '%Y-%m-%d %H:%M:%S %Z')
                print('No patches visible at {}: {}'.format(
                    tstring, not_visible), flush=True)
            t += tstep
            continue

        # Order the targets by priority and attempt to observe with both
        # a rising and setting scans until we find one that can be
        # succesfully scanned.
        # If the criteria are not met, advance the time by a step
        # and try again

        prioritize(args, visible)

        if args.pole_mode:
            success, t = attempt_scan_pole(
                args, observer, visible, not_visible, t, fp_radius, el_max,
                el_min, tstep, stop_timestamp, sun, moon, sun_el_max,
                fout, fout_fmt, ods)
        else:
            success, t = attempt_scan(
                args, observer, visible, not_visible, t, fp_radius, tstep,
                stop_timestamp, sun, moon, sun_el_max, fout, fout_fmt, ods)

        if args.operational_days and len(ods) > args.operational_days:
            break

        if not success:
            if args.debug:
                tstring = datetime.utcfromtimestamp(t).strftime(
                    '%Y-%m-%d %H:%M:%S %Z')
                print('No patches could be scanned at {}: {}'.format(
                    tstring, not_visible), flush=True)
            t += tstep
        else:
            last_successful = t

    fout.close()
    del autotimer
    return


def parse_args():
    autotimer = timing.auto_timer()
    parser = argparse.ArgumentParser(
        description='Generate ground observation schedule.',
        fromfile_prefix_chars='@')

    parser.add_argument('--site_name',
                        required=False, default='LBL',
                        help='Observing site name')
    parser.add_argument('--telescope',
                        required=False, default='Telescope',
                        help='Observing telescope name')
    parser.add_argument('--site_lon',
                        required=False, default='-122.247',
                        help='Observing site longitude [PyEphem string]')
    parser.add_argument('--site_lat',
                        required=False, default='37.876',
                        help='Observing site latitude [PyEphem string]')
    parser.add_argument('--site_alt',
                        required=False, default=100, type=np.float,
                        help='Observing site altitude [meters]')
    parser.add_argument('--scan_margin',
                        required=False, default=0, type=np.float,
                        help='Random fractional margin [0..1] added to the '
                        'scans to smooth out edge effects')
    parser.add_argument('--elevation_penalty_limit',
                        required=False, default=0, type=np.float,
                        help='Assign a penalty to observing elevations below '
                        'this limit [degrees]')
    parser.add_argument('--elevation_penalty_power',
                        required=False, default=2, type=np.float,
                        help='Power in the elevation penalty function [> 0] ')
    parser.add_argument('--equalize_area',
                        required=False, default=False, action='store_true',
                        help='Adjust priorities to account for patch area')
    parser.add_argument('--equalize_time',
                        required=False, action='store_true',
                        dest='equalize_time',
                        help='Modulate priority by integration time.')
    parser.add_argument('--equalize_scans',
                        required=False, action='store_false',
                        dest='equalize_time',
                        help='Modulate priority by number of scans.')
    parser.set_defaults(equalize_time=False)
    parser.add_argument('--patch',
                        required=True, action='append',
                        help='Patch definition: '
                        'name,weight,lon1,lat1,lon2,lat2 ... '
                        'OR name,weight,lon,lat,width')
    parser.add_argument('--patch_coord',
                        required=False, default='C',
                        help='Sky patch coordinate system [C,E,G]')
    parser.add_argument('--el_min',
                        required=False, default=30, type=np.float,
                        help='Minimum elevation for a CES')
    parser.add_argument('--el_max',
                        required=False, default=80, type=np.float,
                        help='Maximum elevation for a CES')
    parser.add_argument('--el_step',
                        required=False, default=0, type=np.float,
                        help='Optional step to apply to minimum elevation')
    parser.add_argument('--alternate',
                        required=False, default=False, action='store_true',
                        help='Alternate between rising and setting scans')
    parser.add_argument('--fp_radius',
                        required=False, default=0, type=np.float,
                        help='Focal plane radius [deg]')
    parser.add_argument('--sun_avoidance_angle',
                        required=False, default=30, type=np.float,
                        help='Minimum distance between the Sun and '
                        'the bore sight [deg]')
    parser.add_argument('--moon_avoidance_angle',
                        required=False, default=20, type=np.float,
                        help='Minimum distance between the Moon and '
                        'the bore sight [deg]')
    parser.add_argument('--sun_el_max',
                        required=False, default=90, type=np.float,
                        help='Maximum allowed sun elevation [deg]')
    parser.add_argument('--start',
                        required=False, default='2000-01-01 00:00:00',
                        help='UTC start time of the schedule')
    parser.add_argument('--stop',
                        required=False,
                        help='UTC stop time of the schedule')
    parser.add_argument('--operational_days',
                        required=False, type=np.int,
                        help='Number of operational days to schedule '
                        '(empty days do not count)')
    parser.add_argument('--timezone', required=False, type=np.int, default=0,
                        help='Offset to apply to MJD to separate operational '
                        'days [hours]')
    parser.add_argument('--gap',
                        required=False, default=100, type=np.float,
                        help='Gap between CES:es [seconds]')
    parser.add_argument('--gap_small',
                        required=False, default=10, type=np.float,
                        help='Gap between split CES:es [seconds]')
    parser.add_argument('--one_scan_per_day',
                        required=False, default=False, action='store_true',
                        help='Pad each operational day to have only one CES')
    parser.add_argument('--ces_max_time',
                        required=False, default=900, type=np.float,
                        help='Maximum length of a CES [seconds]')
    parser.add_argument('--debug',
                        required=False, default=False, action='store_true',
                        help='Write diagnostics, including patch plots.')
    parser.add_argument('--polmap',
                        required=False,
                        help='Include polarization from map in the plotted '
                        'patches when --debug')
    parser.add_argument('--polmin',
                        required=False, type=np.float,
                        help='Lower plotting range for polarization map')
    parser.add_argument('--polmax',
                        required=False, type=np.float,
                        help='Upper plotting range for polarization map')
    parser.add_argument('--delay_sso_check',
                        required=False, default=False, action='store_true',
                        help='Only apply SSO check during simulated scan.')
    parser.add_argument('--pole_mode',
                        required=False, default=False, action='store_true',
                        help='Pole scheduling mode (no drift scan)')
    parser.add_argument('--pole_el_step',
                        required=False, default=0.25, type=np.float,
                        help='Elevation step in pole scheduling mode [deg]')
    parser.add_argument('--pole_ces_time',
                        required=False, default=3000, type=np.float,
                        help='Time to scan at constant elevation in pole mode')
    parser.add_argument('--out',
                        required=False, default='schedule.txt',
                        help='Output filename')

    args = timing.add_arguments_and_parse(parser, timing.FILE(noquotes=True))

    if args.operational_days is None and args.stop is None:
        raise RuntimeError('You must provide --stop or --operational_days')

    stop_time = None
    if args.start.endswith('Z'):
        start_time = dateutil.parser.parse(args.start)
        if args.stop is not None:
            if not args.stop.endswith('Z'):
                raise RuntimeError('Either both or neither times must be '
                                   'given in UTC')
            stop_time = dateutil.parser.parse(args.stop)
    else:
        if args.timezone < 0:
            tz = '-{:02}00'.format(-args.timezone)
        else:
            tz = '+{:02}00'.format(args.timezone)
        start_time = dateutil.parser.parse(args.start + tz)
        if args.stop is not None:
            if args.stop.endswith('Z'):
                raise RuntimeError('Either both or neither times must be '
                                   'given in UTC')
            stop_time = dateutil.parser.parse(args.stop + tz)

    start_timestamp = start_time.timestamp()
    if stop_time is None:
        # Keep scheduling until the desired number of operational days is full.
        stop_timestamp = 2 ** 60
    else:
        stop_timestamp = stop_time.timestamp()
    del autotimer
    return args, start_timestamp, stop_timestamp


def parse_patch_explicit(args, parts):
    """ Parse an explicit patch definition line
    """
    autotimer = timing.auto_timer()
    corners = []
    print('Explicit-corners format ', end='', flush=True)
    name = parts[0]
    i = 2
    while i + 1 < len(parts):
        print(' ({}, {})'.format(parts[i], parts[i + 1]), end='', flush=True)
        try:
            # Assume coordinates in degrees
            lon = float(parts[i]) * degree
            lat = float(parts[i + 1]) * degree
        except ValueError:
            # Failed simple interpreration, assume pyEphem strings
            lon = parts[i]
            lat = parts[i + 1]
        i += 2
        if args.patch_coord == 'C':
            corner = ephem.Equatorial(lon, lat, epoch='2000')
        elif args.patch_coord == 'E':
            corner = ephem.Ecliptic(lon, lat, epoch='2000')
        elif args.patch_coord == 'G':
            corner = ephem.Galactic(lon, lat, epoch='2000')
        else:
            raise RuntimeError('Unknown coordinate system: {}'.format(
                args.patch_coord))
        corner = ephem.Equatorial(corner)
        if corner.dec > 80 * degree or corner.dec < -80 * degree:
            raise RuntimeError(
                '{} has at least one circumpolar corner. '
                'Circumpolar targeting not yet implemented'.format(name))
        patch_corner = ephem.FixedBody()
        patch_corner._ra = corner.ra
        patch_corner._dec = corner.dec
        corners.append(patch_corner)
    del autotimer
    return corners


def parse_patch_rectangular(args, parts):
    """ Parse a rectangular patch definition line
    """
    autotimer = timing.auto_timer()
    corners = []
    print('Rectangular format ', end='', flush=True)
    name = parts[0]
    try:
        # Assume coordinates in degrees
        lon_min = float(parts[2]) * degree
        lat_max = float(parts[3]) * degree
        lon_max = float(parts[4]) * degree
        lat_min = float(parts[5]) * degree
    except ValueError:
        # Failed simple interpreration, assume pyEphem strings
        lon_min = parts[2]
        lat_max = parts[3]
        lon_max = parts[4]
        lat_min = parts[5]
    if args.patch_coord == 'C':
        coordconv = ephem.Equatorial
    elif args.patch_coord == 'E':
        coordconv = ephem.Ecliptic
    elif args.patch_coord == 'G':
        coordconv = ephem.Galactic
    else:
        raise RuntimeError('Unknown coordinate system: {}'.format(
            args.patch_coord))

    nw_corner = coordconv(lon_min, lat_max, epoch='2000')
    ne_corner = coordconv(lon_max, lat_max, epoch='2000')
    se_corner = coordconv(lon_max, lat_min, epoch='2000')
    sw_corner = coordconv(lon_min, lat_min, epoch='2000')

    if lon_min < lon_max:
        delta_lon = lon_max - lon_min
    else:
        delta_lon = lon_max + 2 * np.pi - lon_min
    area = (np.cos(np.pi / 2 - lat_max) - np.cos(np.pi / 2 - lat_min)
            ) * delta_lon

    corners_temp = []
    add_side(nw_corner, ne_corner, corners_temp, coordconv)
    add_side(ne_corner, se_corner, corners_temp, coordconv)
    add_side(se_corner, sw_corner, corners_temp, coordconv)
    add_side(sw_corner, nw_corner, corners_temp, coordconv)

    for corner in corners_temp:
        if corner.dec > 80 * degree or corner.dec < -80 * degree:
            raise RuntimeError(
                '{} has at least one circumpolar corner. '
                'Circumpolar targeting not yet implemented'.format(name))
        patch_corner = ephem.FixedBody()
        patch_corner._ra = corner.ra
        patch_corner._dec = corner.dec
        corners.append(patch_corner)
    del autotimer
    return corners, area


def add_side(corner1, corner2, corners_temp, coordconv):
    """ Add one side of a rectangle.

    Add one side of a rectangle with enough interpolation points.
    """
    autotimer = timing.auto_timer()
    step = np.radians(1)
    corners_temp.append(ephem.Equatorial(corner1))
    lon1 = corner1.ra
    lon2 = corner2.ra
    lat1 = corner1.dec
    lat2 = corner2.dec
    if lon1 == lon2:
        lon = lon1
        if lat1 < lat2:
            lat_step = step
        else:
            lat_step = -step
        for lat in np.arange(lat1, lat2, lat_step):
            corners_temp.append(
                ephem.Equatorial(coordconv(lon, lat, epoch='2000')))
    elif lat1 == lat2:
        lat = lat1
        if lon1 < lon2:
            lon_step = step / np.cos(lat)
        else:
            lon_step = -step / np.cos(lat)
        for lon in np.arange(lon1, lon2, lon_step):
            corners_temp.append(
                ephem.Equatorial(coordconv(lon, lat, epoch='2000')))
    else:
        raise RuntimeError('add_side: both latitude and longitude change')
    del autotimer
    return


def parse_patch_center_and_width(args, parts):
    """ Parse center-and-width patch definition
    """
    autotimer = timing.auto_timer()
    corners = []
    print('Center-and-width format ', end='', flush=True)
    try:
        # Assume coordinates in degrees
        lon = float(parts[2]) * degree
        lat = float(parts[3]) * degree
    except ValueError:
        # Failed simple interpreration, assume pyEphem strings
        lon = parts[2]
        lat = parts[3]
    width = float(parts[4]) * degree
    if args.patch_coord == 'C':
        center = ephem.Equatorial(lon, lat, epoch='2000')
    elif args.patch_coord == 'E':
        center = ephem.Ecliptic(lon, lat, epoch='2000')
    elif args.patch_coord == 'G':
        center = ephem.Galactic(lon, lat, epoch='2000')
    else:
        raise RuntimeError('Unknown coordinate system: {}'.format(
            args.patch_coord))
    center = ephem.Equatorial(center)
    # Synthesize 8 corners around the center
    phi = center.ra
    theta = center.dec
    r = width / 2
    ncorner = 8
    angstep = 2 * np.pi / ncorner
    for icorner in range(ncorner):
        ang = angstep * icorner
        delta_theta = np.cos(ang) * r
        delta_phi = np.sin(ang) * r / np.cos(theta + delta_theta)
        patch_corner = ephem.FixedBody()
        patch_corner._ra = phi + delta_phi
        patch_corner._dec = theta + delta_theta
        corners.append(patch_corner)
    del autotimer
    return corners


def parse_patches(args, observer, sun, moon, start_timestamp, stop_timestamp):
    # Parse the patch definitions
    autotimer = timing.auto_timer()
    patches = []
    total_weight = 0
    for patch_def in args.patch:
        parts = patch_def.split(',')
        name = parts[0]
        weight = float(parts[1])
        if np.isnan(weight):
            raise RuntimeError('Patch has NaN priority: {}'.format(patch_def))
        if weight == 0:
            raise RuntimeError('Patch has zero priority: {}'.format(patch_def))
        print('Adding patch "{}" {} '.format(name, weight), end='', flush=True)
        if len(parts[2:]) == 3:
            corners = parse_patch_center_and_width(args, parts)
            area = None
        elif len(parts[2:]) == 4:
            corners, area = parse_patch_rectangular(args, parts)
        else:
            corners = parse_patch_explicit(args, parts)
            area = None
        print('')
        patch = Patch(
            name, weight, corners, el_min=args.el_min * degree,
            el_max=args.el_max * degree, el_step=args.el_step * degree,
            alternate=args.alternate, site_lat=observer.lat, area=area)
        if args.equalize_area or args.debug:
            area = patch.get_area(observer, nside=32,
                                  equalize=args.equalize_area)
        total_weight += patch.weight
        patches.append(patch)

        print('Highest possible observing elevation: {:.2f} degrees.'
              ' Sky fraction = {:.4f}'.format(
                  patches[-1].el_max0 / degree, patch._area), flush=True)

    if args.debug:
        import matplotlib.pyplot as plt
        polmap = None
        if args.polmap:
            polmap = hp.read_map(args.polmap, [1, 2])
            bad = polmap[0] == hp.UNSEEN
            polmap = np.sqrt(polmap[0] ** 2 + polmap[1] ** 2) * 1e6
            polmap[bad] = hp.UNSEEN
        plt.style.use('default')
        cmap = cm.inferno
        cmap.set_under('w')
        plt.figure(figsize=[20, 4])
        plt.subplots_adjust(left=.1, right=.9)
        patch_color = 'black'
        sun_color = 'black'
        sun_lw = 8
        sun_avoidance_color = 'gray'
        moon_color = 'black'
        moon_lw = 2
        moon_avoidance_color = 'gray'
        alpha = 0.5
        avoidance_alpha = 0.01
        sun_step = np.int(86400 * 1)
        moon_step = np.int(86400 * .1)
        for iplot, coord in enumerate('CEG'):
            scoord = {'C': 'Equatorial', 'E': 'Ecliptic',
                      'G': 'Galactic'}[coord]
            title = scoord  # + ' patch locations'
            if polmap is None:
                nside = 256
                avoidance_map = np.zeros(12 * nside ** 2)
                # hp.mollview(np.zeros(12) + hp.UNSEEN, coord=coord, cbar=False,
                #            title='', sub=[1, 3, 1 + iplot], cmap=cmap)
            else:
                hp.mollview(polmap, coord='G' + coord, cbar=True, unit='$\mu$K',
                            min=args.polmin, max=args.polmax, norm='log',
                            cmap=cmap, title=title, sub=[1, 3, 1 + iplot],
                            notext=True, format='%.1f', xsize=1600)
            # Plot sun and moon avoidance circle
            sunlon, sunlat = [], []
            moonlon, moonlat = [], []
            sun_avoidance_angle = args.sun_avoidance_angle * degree
            moon_avoidance_angle = args.moon_avoidance_angle * degree
            for lon, lat, sso, angle_min, color, step, lw in [
                (sunlon, sunlat, sun, sun_avoidance_angle,
                 sun_avoidance_color, sun_step, sun_lw),
                (moonlon, moonlat, moon, moon_avoidance_angle,
                 moon_avoidance_color, moon_step, moon_lw)]:
                for t in range(np.int(start_timestamp),
                               np.int(stop_timestamp), step):
                    observer.date = to_DJD(t)
                    sso.compute(observer)
                    lon.append(sso.a_ra / degree)
                    lat.append(sso.a_dec / degree)
                    if angle_min <= 0:
                        continue
                    if polmap is None:
                        # accumulate avoidance map
                        vec = hp.dir2vec(lon[-1], lat[-1], lonlat=True)
                        pix = hp.query_disc(nside, vec, angle_min)
                        for p in pix:
                            avoidance_map[p] += 1
                    else:
                        # plot a circle around the location
                        clon, clat = [], []
                        phi = sso.a_ra
                        theta = sso.a_dec
                        r = angle_min
                        for ang in np.linspace(0, 2 * np.pi, 36):
                            dtheta = np.cos(ang) * r
                            dphi = np.sin(ang) * r / np.cos(theta + dtheta)
                            clon.append((phi + dphi) / degree)
                            clat.append((theta + dtheta) / degree)
                        hp.projplot(clon, clat, '-', color=color,
                                    alpha=avoidance_alpha, lw=lw,
                                    threshold=1, lonlat=True, coord='C')
            if polmap is None:
                avoidance_map[avoidance_map == 0] = hp.UNSEEN
                hp.mollview(avoidance_map, coord='C' + coord, cbar=False,
                            title='', sub=[1, 3, 1 + iplot], cmap=cmap)
            hp.graticule(30, verbose=False)

            # Plot patches
            for patch in patches:
                lon = [corner._ra / degree for corner in patch.corners]
                lat = [corner._dec / degree for corner in patch.corners]
                lon.append(lon[0])
                lat.append(lat[0])
                print('{} corners:\n lon = {}\n lat= {}'.format(
                    patch.name, lon, lat), flush=True)
                hp.projplot(lon, lat, '-', threshold=1, lonlat=True, coord='C',
                            color=patch_color, lw=2, alpha=alpha)
                if len(patches) > 10:
                    continue
                # label the patch
                it = np.argmax(lat)
                area = patch.get_area(observer)
                title = '{} {:.2f}%'.format(patch.name, 100 * area)
                hp.projtext(lon[it], lat[it], title, lonlat=True,
                            coord='C', color=patch_color, fontsize=14,
                            alpha=alpha)
            if polmap is not None:
                # Plot Sun and Moon trajectory
                hp.projplot(sunlon, sunlat, '-', color=sun_color, alpha=alpha,
                            threshold=1, lonlat=True, coord='C', lw=sun_lw)
                hp.projplot(moonlon, moonlat, '-', color=moon_color, alpha=alpha,
                            threshold=1, lonlat=True, coord='C', lw=moon_lw)
                hp.projtext(sunlon[0], sunlat[0], 'Sun', color=sun_color,
                            lonlat=True, coord='C', fontsize=14, alpha=alpha)
                hp.projtext(moonlon[0], moonlat[0], 'Moon', color=moon_color,
                            lonlat=True, coord='C', fontsize=14, alpha=alpha)

        plt.savefig('patches.png')
        plt.close()

    # Normalize the weights
    for i in range(len(patches)):
        patches[i].weight /= total_weight
    del autotimer
    return patches


def main():
    autotimer = timing.auto_timer(timing.FILE())

    args, start_timestamp, stop_timestamp = parse_args()

    observer = ephem.Observer()
    observer.lon = args.site_lon
    observer.lat = args.site_lat
    observer.elevation = args.site_alt  # In meters
    observer.epoch = '2000'
    observer.temp = 0  # in Celcius
    observer.compute_pressure()

    sun = ephem.Sun()
    moon = ephem.Moon()

    patches = parse_patches(args, observer, sun, moon,
                            start_timestamp, stop_timestamp)

    build_schedule(
        args, start_timestamp, stop_timestamp, patches, observer, sun, moon)

    del autotimer


if __name__ == '__main__':

    main()

    tman = timing.timing_manager()
    tman.report()
