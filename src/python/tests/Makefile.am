SUBDIRS =

# Initialize compile and linking flags

AM_CPPFLAGS = \
-I$(top_srcdir)/src/libtoast \
$(PYTHON_CPPFLAGS)

AM_CFLAGS =
AM_CXXFLAGS =

AM_LDFLAGS = $(PYTHON_LDFLAGS)

AM_LIBS = $(PYTHON_LIBS)

# Append compile and linking flags based on configure variables
include $(top_srcdir)/src/build_options.am


toasttestsdir = $(pythondir)/toast/tests

toasttests_PYTHON = \
__init__.py \
_helpers.py \
binned.py \
cache.py \
cbuffer.py \
cov.py \
ctoast.py \
dist.py \
intervals.py \
map_ground.py \
map_satellite.py \
mpi.py \
ops_dipole.py \
ops_madam.py \
ops_pmat.py \
ops_simnoise.py \
ops_sim_pysm.py \
smooth.py \
ops_polyfilter.py \
ops_groundfilter.py \
ops_gainscrambler.py \
ops_applygain.py \
ops_memorycounter.py \
psd_math.py \
qarray.py \
rng.py \
fft.py \
runner.py \
tod.py \
tod_satellite.py \
sim_focalplane.py \
tidas.py \
spt3g.py \
timing.py


clean-local :
	@rm -f *.pyc
