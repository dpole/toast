
//
// created by jmadsen on Wed Oct 19 16:38:09 2016

// -----------------------------------------------------------------------
/// This global method should be used on LINUX or MacOSX platforms with gcc
/// compiler for activating NaN detection and FPE signals, and forcing
/// abortion of the application at the time these are detected.
/// Meant to be used for debug purposes, can be activated by compiling the
/// "run" module with the flag FPE_DEBUG set in the environment.
// -----------------------------------------------------------------------

#ifndef signal_detection_hpp_
#define signal_detection_hpp_ 1

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"

#include <mpi.h>

#include <iostream>
#include <cstdlib>
#include <stdlib.h>  /* abort(), exit() */
#include <set>
#include <string>
#include <sstream>
#include <iomanip>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <functional>
#include <cfenv>
#include <execinfo.h> // for StackBacktrace()
#include <cxxabi.h>
#include <deque>
#include <cmath>
#include <vector>

// Define C++11
#ifndef CXX11
#   if __cplusplus > 199711L   // C++11
#       define CXX11
#   endif
#endif

// Define C++14
#ifndef CXX14
#   if __cplusplus > 201103L   // C++14
#       define CXX14
#   endif
#endif

// compatible compiler
#if (defined(__GNUC__) || defined(__clang__) || defined(_INTEL_COMPILER))
#   if !defined(SIGNAL_COMPAT_COMPILER)
#       define SIGNAL_COMPAT_COMPILER
#   endif
#endif

// compatible operating system
#if (defined(__linux__) || defined(__MACH__))
#   if !defined(SIGNAL_COMPAT_OS)
#       define SIGNAL_COMPAT_OS
#   endif
#endif

#if defined(SIGNAL_COMPAT_COMPILER) && defined(SIGNAL_COMPAT_OS)
#   if !defined(SIGNAL_AVAILABLE)
#       define SIGNAL_AVAILABLE
#   endif
#endif

#if defined(__linux__)
#   include <features.h>
#   include <csignal>
#elif defined(__MACH__)      /* MacOSX */
#   include <signal.h>
#endif

//============================================================================//
//  these are not in the original POSIX.1-1990 standard so we are defining
//  them in case the OS hasn't
//  POSIX-1.2001
#ifndef SIGTRAP
#   define SIGTRAP 5
#endif
//  not specified in POSIX.1-2001, but nevertheless appears on most other
//  UNIX systems, where its default action is typically to terminate the
//  process with a core dump.
#ifndef SIGEMT
#   define SIGEMT 7
#endif
//  POSIX-1.2001
#ifndef SIGURG
#   define SIGURG 16
#endif
//  POSIX-1.2001
#ifndef SIGXCPU
#   define SIGXCPU 24
#endif
//  POSIX-1.2001
#ifndef SIGXFSZ
#   define SIGXFSZ 25
#endif
//  POSIX-1.2001
#ifndef SIGVTALRM
#   define SIGVTALRM 26
#endif
//  POSIX-1.2001
#ifndef SIGPROF
#   define SIGPROF 27
#endif
//  POSIX-1.2001
#ifndef SIGINFO
#   define SIGINFO 29
#endif

//============================================================================//

namespace toast
{

typedef std::deque<std::string> str_list_t;

namespace internal
{
inline std::string dummy_str_return(std::string str) { return str; }
}

//----------------------------------------------------------------------------//

template <typename _Tp>
_Tp get_env(const std::string& env_id, _Tp _default = _Tp())
{
    char* env_var = std::getenv(env_id.c_str());
    if(env_var)
    {
        std::string str_var = std::string(env_var);
        std::istringstream iss(str_var);
        _Tp var = _Tp();
        iss >> var;
        return var;
    }
    // return default if not specified in environment
    return _default;
}

//----------------------------------------------------------------------------//
//  delimit line : e.g. delimit_line("a B\t c", " \t") --> { "a", "B", "c"}
inline str_list_t
delimit(const std::string& _str, const std::string& _delims,
        std::string (*strop)(std::string) = internal::dummy_str_return)
{
    str_list_t _list;
    size_t _beg = 0;
    size_t _end = 0;
    while(true)
    {
        _beg = _str.find_first_not_of(_delims, _end);
        if(_beg == std::string::npos)
            break;
        _end = _str.find_first_of(_delims, _beg);
        if(_beg < _end)
            _list.push_back(strop(_str.substr(_beg, _end - _beg)));
    }
    return _list;
}

//----------------------------------------------------------------------------//

enum class sys_signal : int
{
    sHangup = SIGHUP,
    sInterrupt = SIGINT,
    sQuit = SIGQUIT,
    sIllegal = SIGILL,
    sTrap = SIGTRAP,
    sAbort = SIGABRT,
    sEmulate = SIGEMT,
    sFPE = SIGFPE,
    sKill = SIGKILL,
    sBus = SIGBUS,
    sSegFault = SIGSEGV,
    sSystem = SIGSYS,
    sPipe = SIGPIPE,
    sAlarm = SIGALRM,
    sTerminate = SIGTERM,
    sUrgent = SIGURG,
    sStop = SIGTSTP,
    sCPUtime = SIGXCPU,
    sFileSize = SIGXFSZ,
    sVirtualAlarm = SIGVTALRM,
    sProfileAlarm = SIGPIPE
};

//----------------------------------------------------------------------------//

class signal_settings
{
public:
    typedef std::set<sys_signal> signal_set_t;
    typedef void (*signal_function_t)(int errcode);

public:
    static bool is_active() { return signals_active; }
    static void set_active(bool val) { signals_active = val; }
    static void enable(const sys_signal&);
    static void disable(const sys_signal&);
    static std::string str(const sys_signal&);
    static std::string str();
    static void check_environment();
    static void set_exit_action(signal_function_t _f) { signals_exit_func = _f; }
    static void exit_action(int errcode) { signals_exit_func(errcode); }

    static const signal_set_t& enabled() { check_environment(); return signals_enabled; }
    static const signal_set_t& disabled() { check_environment(); return signals_disabled; }
    static const signal_set_t& get_enabled() { return signals_enabled; }
    static const signal_set_t& get_disabled() { return signals_disabled; }

private:
    static bool                 signals_active;
    static signal_set_t         signals_default;
    static signal_set_t         signals_enabled;
    static signal_set_t         signals_disabled;
    static signal_function_t    signals_exit_func;
};

//----------------------------------------------------------------------------//

} // namespace toast

//============================================================================//

#if defined(SIGNAL_AVAILABLE)

//============================================================================//

namespace toast
{

//----------------------------------------------------------------------------//

static struct sigaction signal_termaction, signal_oldaction;

// declarations
inline bool EnableSignalDetection(signal_settings::signal_set_t ops
                                  = signal_settings::signal_set_t());
inline void DisableSignalDetection();

//----------------------------------------------------------------------------//

inline void StackBackTrace(std::ostream& ss)
{
    typedef std::string::size_type          size_type;

    //   from http://linux.die.net/man/3/backtrace_symbols_fd
#   define BSIZE 50
    void* buffer[ BSIZE ];
    size_type nptrs = backtrace( buffer, BSIZE );
    char** strings = backtrace_symbols( buffer, nptrs );
    if(strings == NULL)
    {
        perror( "backtrace_symbols" );
        return;
    }

    std::deque<std::deque<std::string>>     dmang_buf;
    std::deque<size_type>                   dmang_len;

    // lambda for demangling a string when delimiting
    auto _transform = [] (std::string _str)
    {
        int _ret = 0;
        char* _demang = abi::__cxa_demangle(_str.c_str(), 0, 0, &_ret);
        if(_demang && _ret == 0)
            return std::string(const_cast<const char*>(_demang));
        else
            return _str;
    };

    for(size_type j = 0; j < nptrs; ++j)
    {
        auto _delim = delimit(strings[j], " \t\n\r");
        // found a GCC compiler but when passing _transform to delimit
        for(auto& itr : _delim)
            itr = _transform(itr);

        // find trailing " + ([0-9]+)"
        auto itr = _delim.begin();
        for(; itr != _delim.end(); ++itr)
            if(*itr == "+")
                break;

        // get rid of trailing " + ([0-9]+)"
        if(itr != _delim.end())
            _delim.erase(itr, _delim.end());

        // get rid of hex strings if not last param
        for(itr = _delim.begin(); itr != _delim.end(); ++itr)
            if(itr->substr(0, 2) == "0x")
            {
                if(itr+1 == _delim.end())
                    continue;
                _delim.erase(itr);
                --itr;
            }

        // accumulate the max lengths of the strings
        for(size_type i = 0; i < _delim.size(); ++i)
        {
            dmang_len.resize(std::max(dmang_len.size(), _delim.size()), 0);
            dmang_len[i] = std::max(dmang_len[i], _delim[i].length());
        }

        // add
        dmang_buf.push_back(_delim);
    }

    free(strings);

    ss << std::endl << "Call Stack:" << std::endl;
    int nwidth = std::max(2, static_cast<int32_t>(std::log10(nptrs))+1);
    for(size_type j = 0; j < nptrs; ++j)
    {
        // print the back-trace numver
        ss << "["<< std::setw(nwidth) << nptrs-j-1 << "/"
           << std::setw(nwidth) << nptrs << "] : ";
        // loop over fields
        for(size_type i = 0; i < dmang_len.size(); ++i)
        {
            std::stringstream _ss;
            // if last param, don't set width
            int mwidth = (i+1 < dmang_len.size()) ? dmang_len.at(i) : 0;
            _ss << std::setw(mwidth) << std::left
                << ((i < dmang_buf.at(j).size())
                    ? dmang_buf.at(j).at(i)
                    : std::string(" "));
            ss << _ss.str() << "  ";
        }
        ss << std::endl;
    }

    // c++filt can demangle:
    // http://gcc.gnu.org/onlinedocs/libstdc++/manual/ext_demangling.html
}

//----------------------------------------------------------------------------//

inline void TerminationSignalMessage(int sig, siginfo_t* sinfo,
                                     std::ostream& message)
{
    sys_signal _sig = (sys_signal) (sig);

    //------------------------------------------------------------------------//
    auto mpi_is_initialized = [] ()
    {
        int32_t _init = 0;
        MPI_Initialized(&_init);
        return (_init != 0) ? true : false;
    };
    //------------------------------------------------------------------------//
    auto mpi_rank = [=] ()
    {
        int32_t _rank = 0;
        if(mpi_is_initialized())
            MPI_Comm_rank(MPI_COMM_WORLD, &_rank);
        return std::max(_rank, (int32_t) 0);
    };
    //------------------------------------------------------------------------//

    message << "\n" << "### ERROR ### ";
    if(mpi_is_initialized())
        message << " [ MPI rank : " << mpi_rank() << " ] ";
    message << "Error code : " << sig;
    if(sinfo)
        message << " @ " << sinfo->si_addr;
    message << " : " << signal_settings::str(_sig);

    if(sig == SIGSEGV)
    {
        if(sinfo)
            switch (sinfo->si_code)
            {
                case SEGV_MAPERR:
                    message << "Address not mapped to object.";
                    break;
                case SEGV_ACCERR:
                    message << "Invalid permissions for mapped object.";
                    break;
                default:
                    message << "Unknown error: " << sinfo->si_code << ".";
                    break;
            }
        else
            message << "Segmentation fault (unknown).";
    }

    message << std::endl;
    try
    {
        signal_settings::exit_action(sig);
    }
    catch(std::exception& e)
    {
        std::cerr << "signal_settings::exit_action(" << sig
                  << ") threw an exception" << std::endl;
        std::cerr << e.what() << std::endl;
    }

    StackBackTrace(message);
}

//----------------------------------------------------------------------------//

inline void TerminationSignalHandler(int sig, siginfo_t* sinfo,
                                     void* /* context */)
{
    sys_signal _sig = (sys_signal) (sig);

    if(signal_settings::get_enabled().find(_sig) ==
       signal_settings::get_enabled().end())
        return;

    std::stringstream message;
    TerminationSignalMessage(sig, sinfo, message);

    if(signal_settings::enabled().find(sys_signal::sAbort) !=
       signal_settings::enabled().end())
    {
        signal_settings::disable(sys_signal::sAbort);
        signal_settings::disable(_sig);
        DisableSignalDetection();
        EnableSignalDetection(signal_settings::enabled());
        std::cerr << message.str() << std::endl;
    }

    // throw an exception instead of ::abort() so it can be caught
    // if the error can be ignored if desired
    throw std::runtime_error(message.str());
}

//----------------------------------------------------------------------------//

inline bool EnableSignalDetection(signal_settings::signal_set_t operations)
{
    // don't re-enable
    if(signal_settings::is_active())
        return false;

    if(operations.empty())
        operations = signal_settings::enabled();
    std::set<int> _signals;
    for(auto itr = operations.cbegin(); itr != operations.cend(); ++itr)
        _signals.insert(static_cast<int>(*itr));

    sigfillset(&signal_termaction.sa_mask);
    for(auto& itr : _signals)
        sigdelset(&signal_termaction.sa_mask, itr);
    signal_termaction.sa_sigaction = TerminationSignalHandler;
    signal_termaction.sa_flags = SA_SIGINFO;
    for(auto& itr : _signals)
        sigaction(itr, &signal_termaction, &signal_oldaction);

    signal_settings::set_active(true);

    return true;
}

//----------------------------------------------------------------------------//

inline void DisableSignalDetection()
{
    // don't re-disable
    if(!signal_settings::is_active())
        return;

    sigemptyset(&signal_termaction.sa_mask);
    signal_termaction.sa_handler = SIG_DFL;

    auto _disable = [] (const signal_settings::signal_set_t& _set)
    {
        for(auto itr = _set.cbegin(); itr != _set.cend(); ++itr)
        {
            int _itr = static_cast<int>(*itr);
            sigaction(_itr, &signal_termaction, 0);
        }
    };

    _disable(signal_settings::get_enabled());
    _disable(signal_settings::get_disabled());

    signal_settings::set_active(false);
}

//----------------------------------------------------------------------------//

} // namespace toast

//============================================================================//

#else /* Not a supported architecture */

//============================================================================//

namespace toast
{
static bool EnableSignalDetection() { return false; }
static void DisableSignalDetection() { }
} // namespace toast

//============================================================================//

#endif

#pragma GCC diagnostic pop

#endif /* signal_detection_hpp_ */
