/*
Copyright (c) 2015-2018 by the parties listed in the AUTHORS file.
All rights reserved.  Use of this source code is governed by
a BSD-style license that can be found in the LICENSE file.
*/

/** \file rss.hpp
 * Resident set size handler
 *
 */

#ifndef rss_hpp_
#define rss_hpp_

#include <unistd.h>
#include <ios>
#include <iostream>
#include <fstream>
#include <string>
#include <iomanip>
#include <stdio.h>
#include <cstdint>

#include <cereal/cereal.hpp>
#include <cereal/access.hpp>
#include <cereal/macros.hpp>
#include <cereal/types/chrono.hpp>
#include <cereal/types/deque.hpp>
#include <cereal/types/vector.hpp>

//============================================================================//

#if defined(__unix__) || defined(__unix) || defined(unix) || \
    (defined(__APPLE__) && defined(__MACH__))
#   include <unistd.h>
#   include <sys/resource.h>
#   if defined(__APPLE__) && defined(__MACH__)
#       include <mach/mach.h>
#   endif
#else
#   error "Cannot define getPeakRSS( ) or getCurrentRSS( ) for an unknown OS."
#endif

// RSS - Resident set size (physical memory use, not in swap)

namespace toast
{

namespace rss
{

    // Using the SI convention for kilo-, mega-, giga-, and peta-
    // because this is more intuitive
    namespace units
    {
    const int64_t byte     = 1;
    const int64_t kilobyte = 1000*byte;
    const int64_t megabyte = 1000*kilobyte;
    const int64_t gigabyte = 1000*megabyte;
    const int64_t petabyte = 1000*gigabyte;
    const double  Bi       = 1.0;
    const double  KiB      = 1024.0 * Bi;
    const double  MiB      = 1024.0 * KiB;
    const double  GiB      = 1024.0 * MiB;
    const double  PiB      = 1024.0 * GiB;
    }

    /**
     * Returns the peak (maximum so far) resident set size (physical
     * memory use) measured in bytes, or zero if the value cannot be
     * determined on this OS.
     */
    static inline
    int64_t get_peak_rss()
    {
        struct rusage rusage;
        getrusage( RUSAGE_SELF, &rusage );
#if defined(__APPLE__) && defined(__MACH__)
        return (int64_t) (rusage.ru_maxrss / units::KiB * units::kilobyte);
#else
        return (int64_t) (rusage.ru_maxrss / units::KiB * units::megabyte);
#endif
    }

    /**
     * Returns the current resident set size (physical memory use) measured
     * in bytes, or zero if the value cannot be determined on this OS.
     */
    static inline
    int64_t get_current_rss()
    {

#if defined(__APPLE__) && defined(__MACH__)
        // OSX
        struct mach_task_basic_info info;
        mach_msg_type_number_t infoCount = MACH_TASK_BASIC_INFO_COUNT;
        if(task_info(mach_task_self(), MACH_TASK_BASIC_INFO,
                     (task_info_t) &info, &infoCount) != KERN_SUCCESS)
            return (int64_t) 0L;      /* Can't access? */
        return (int64_t) (info.resident_size / units::KiB * units::kilobyte);

#else // Linux
        long rss = 0L;
        FILE* fp = fopen("/proc/self/statm", "r");
        if(fp == nullptr)
            return (int64_t) 0L;
        if(fscanf(fp, "%*s%ld", &rss) != 1)
        {
            fclose(fp);
            return (int64_t) 0L;
        }
        fclose(fp);
        return (int64_t) (rss * (int64_t) sysconf( _SC_PAGESIZE) / units::KiB *
                          units::kilobyte);

#endif
    }

    //========================================================================//

    struct usage
    {
        typedef usage           this_type;
        typedef int64_t         size_type;
        size_type               m_peak_rss;
        size_type               m_curr_rss;

        usage()
        : m_peak_rss(0), m_curr_rss(0)
        { }

        usage(size_type minus)
        : m_peak_rss(0), m_curr_rss(0)
        {
            record();
            if(minus > 0)
            {
                if(minus < m_curr_rss)
                    m_curr_rss -= minus;
                else
                    m_curr_rss = 1;

                if(minus < m_peak_rss)
                    m_peak_rss -= minus;
                else
                    m_peak_rss = 1;
            }
        }

        usage(const usage& rhs)
        : m_peak_rss(rhs.m_peak_rss),
          m_curr_rss(rhs.m_curr_rss)
        { }

        usage& operator=(const usage& rhs)
        {
            if(this != &rhs)
            {
                m_peak_rss = rhs.m_peak_rss;
                m_curr_rss = rhs.m_curr_rss;
            }
            return *this;
        }

        void record();
        void record(const usage& rhs);

        friend bool operator<(const this_type& lhs, const this_type& rhs)
        { return lhs.m_peak_rss < rhs.m_peak_rss; }
        friend bool operator==(const this_type& lhs, const this_type& rhs)
        { return lhs.m_peak_rss == rhs.m_peak_rss; }
        friend bool operator!=(const this_type& lhs, const this_type& rhs)
        { return !(lhs.m_peak_rss == rhs.m_peak_rss); }
        friend bool operator>(const this_type& lhs, const this_type& rhs)
        { return rhs.m_peak_rss < lhs.m_peak_rss; }
        friend bool operator<=(const this_type& lhs, const this_type& rhs)
        { return !(lhs > rhs); }
        friend bool operator>=(const this_type& lhs, const this_type& rhs)
        { return !(lhs < rhs); }
        bool operator()(const this_type& rhs) const
        { return *this < rhs; }

        static usage max(const usage& lhs, const usage& rhs)
        {
            usage ret;
            ret.m_curr_rss = std::max(lhs.m_curr_rss, rhs.m_curr_rss);
            ret.m_peak_rss = std::max(lhs.m_peak_rss, rhs.m_peak_rss);
            return ret;
        }

        static usage min(const usage& lhs, const usage& rhs)
        {
            usage ret;
            ret.m_curr_rss = std::min(lhs.m_curr_rss, rhs.m_curr_rss);
            ret.m_peak_rss = std::min(lhs.m_peak_rss, rhs.m_peak_rss);
            return ret;
        }

        friend this_type operator-(const this_type& lhs, const this_type& rhs)
        {
            this_type r = lhs;

            if(rhs.m_peak_rss < r.m_peak_rss)
                r.m_peak_rss -= rhs.m_peak_rss;
            else
                r.m_peak_rss = 1;

            if(rhs.m_curr_rss < r.m_curr_rss)
                r.m_curr_rss -= rhs.m_curr_rss;
            else
                r.m_curr_rss = 1;

            return r;
        }

        this_type& operator-=(const this_type& rhs)
        {
            m_peak_rss -= rhs.m_peak_rss;
            m_curr_rss -= rhs.m_curr_rss;
            return *this;
        }

        double current(int64_t _unit = units::megabyte) const
        {
            return static_cast<double>(m_curr_rss) / _unit;
        }

        double peak(int64_t _unit = units::megabyte) const
        {
            return static_cast<double>(m_peak_rss) / _unit;
        }

        friend std::ostream& operator<<(std::ostream& os, const usage& m)
        {
            using std::setw;
            std::stringstream ss;
            ss.precision(1);
            int _w = 5;
            double _curr = (m.m_curr_rss < 0) ? 0.0 : m.m_curr_rss;
            double _peak = (m.m_peak_rss < 0) ? 0.0 : m.m_peak_rss;
            _curr /= units::megabyte;
            _peak /= units::megabyte;

            ss << std::fixed;
            ss << "rss curr|peak = "
               << std::setw(_w) << _curr << "|"
               << std::setw(_w) << _peak
               << " MB";
            os << ss.str();
            return os;
        }

        template <typename Archive> void
        serialize(Archive& ar, const unsigned int /*version*/)
        {
            ar(cereal::make_nvp("current", m_curr_rss),
               cereal::make_nvp("peak",    m_peak_rss));
        }

    };

    //------------------------------------------------------------------------//

    inline void usage::record()
    {
        // everything is kB
        m_curr_rss = std::max(m_curr_rss, get_current_rss());
        m_peak_rss = std::max(m_peak_rss, get_peak_rss());
    }

    //------------------------------------------------------------------------//

    inline void usage::record(const usage& rhs)
    {
        // everything is kB
        m_curr_rss = std::max(m_curr_rss - rhs.m_curr_rss,
                              get_current_rss() - rhs.m_curr_rss);
        m_peak_rss = std::max(m_peak_rss - rhs.m_peak_rss,
                              get_peak_rss() - rhs.m_peak_rss);
    }

    //------------------------------------------------------------------------//

} // namespace rss

} // namespace toast

//----------------------------------------------------------------------------//


#endif // rss_hpp_
