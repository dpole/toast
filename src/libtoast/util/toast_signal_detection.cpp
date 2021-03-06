//
//
// created by jmadsen on Wed Oct 19 16:38:09 2016
//
//
//
//

#include "toast_util_internal.hpp"
#include <sstream>
#include <string>
#include <cstdlib>


namespace toast
{

//============================================================================//

namespace internal { void dummy_func(int) { return; } }

//============================================================================//

bool signal_settings::signals_active = false;

//============================================================================//

std::set<sys_signal> signal_settings::signals_default =
{
    sys_signal::sHangup,
    sys_signal::sInterrupt,
    sys_signal::sQuit,
    sys_signal::sIllegal,
    sys_signal::sTrap,
    sys_signal::sAbort,
    sys_signal::sEmulate,
    sys_signal::sKill,
    sys_signal::sBus,
    sys_signal::sSegFault,
    sys_signal::sSystem,
    sys_signal::sPipe,
    sys_signal::sAlarm,
    sys_signal::sTerminate,
    sys_signal::sUrgent,
    sys_signal::sStop,
    sys_signal::sCPUtime,
    sys_signal::sFileSize,
    sys_signal::sVirtualAlarm,
    sys_signal::sProfileAlarm,
};

//============================================================================//

std::set<sys_signal> signal_settings::signals_enabled = signal_settings::signals_default;

//============================================================================//

std::set<sys_signal> signal_settings::signals_disabled =
{
    sys_signal::sFPE
};

//============================================================================//

signal_settings::signal_function_t signal_settings::signals_exit_func =
        internal::dummy_func;

//============================================================================//

void
insert_and_remove(const sys_signal& _type,             // signal type
                  signal_settings::signal_set_t* _ins, // set to insert into
                  signal_settings::signal_set_t* _rem) // set to remove from

{
    _ins->insert(_type);
    auto itr = _rem->find(_type);
    if(itr != _rem->end())
        _rem->erase(itr);
}

//============================================================================//

void signal_settings::enable(const sys_signal& _type)
{
    insert_and_remove(_type, &signals_enabled, &signals_disabled);
}

//============================================================================//

void signal_settings::disable(const sys_signal& _type)
{
    insert_and_remove(_type, &signals_disabled, &signals_enabled);
}

//============================================================================//

void signal_settings::check_environment()
{
    typedef std::pair<std::string, sys_signal> match_t;

    auto _list =
    {
        match_t("HANGUP",       sys_signal::sHangup),
        match_t("INTERRUPT", 	sys_signal::sInterrupt),
        match_t("QUIT",         sys_signal::sQuit),
        match_t("ILLEGAL",      sys_signal::sIllegal),
        match_t("TRAP",         sys_signal::sTrap),
        match_t("ABORT",        sys_signal::sAbort),
        match_t("EMULATE",      sys_signal::sEmulate),
        match_t("FPE",          sys_signal::sFPE),
        match_t("KILL",         sys_signal::sKill),
        match_t("BUS",          sys_signal::sBus),
        match_t("SEGFAULT", 	sys_signal::sSegFault),
        match_t("SYSTEM",       sys_signal::sSystem),
        match_t("PIPE",         sys_signal::sPipe),
        match_t("ALARM",        sys_signal::sAlarm),
        match_t("TERMINATE", 	sys_signal::sTerminate),
        match_t("URGENT",       sys_signal::sUrgent),
        match_t("STOP",         sys_signal::sStop),
        match_t("CPUTIME",      sys_signal::sCPUtime),
        match_t("FILESIZE", 	sys_signal::sFileSize),
        match_t("VIRTUALALARM", sys_signal::sVirtualAlarm),
        match_t("PROFILEALARM", sys_signal::sProfileAlarm),
    };

    for(auto itr : _list)
    {
        int _enable = get_env<int>("SIGNAL_ENABLE_" + itr.first, 0);
        int _disable = get_env<int>("SIGNAL_DISABLE_" + itr.first, 0);

        if(_enable > 0)
            signal_settings::enable(itr.second);
        if(_disable > 0)
            signal_settings::disable(itr.second);
    }

    int _enable_all = get_env<int>("SIGNAL_ENABLE_ALL", 0);
    if(_enable_all > 0)
        for(const auto& itr : signal_settings::signals_disabled)
            signal_settings::enable(itr);

    int _disable_all = get_env<int>("SIGNAL_DISABLE_ALL", 0);
    if(_disable_all > 0)
        for(const auto& itr : signal_settings::signals_enabled)
            signal_settings::disable(itr);

}

//============================================================================//

std::string signal_settings::str(const sys_signal& _type)
{
    typedef std::tuple<std::string, int, std::string> descript_tuple_t;

    std::stringstream ss;
    auto descript = [&] (const descript_tuple_t& _data)
    {
        ss << " Signal: " << std::get<0>(_data)
           << " (error code: " << std::get<1>(_data) << ") "
           << std::get<2>(_data);
    };

    // some of these signals are not handled but added in case they are
    // enabled in the future
    static std::vector<descript_tuple_t> descript_data =
    {
        descript_tuple_t("SIGHUP", SIGHUP, "terminal line hangup"),
        descript_tuple_t("SIGINT", SIGINT, "interrupt program"),
        descript_tuple_t("SIGQUIT", SIGQUIT, "quit program"),
        descript_tuple_t("SIGILL", SIGILL, "illegal instruction"),
        descript_tuple_t("SIGTRAP", SIGTRAP, "trace trap"),
        descript_tuple_t("SIGABRT", SIGABRT, "abort program (formerly SIGIOT)"),
        descript_tuple_t("SIGEMT", SIGEMT, "emulate instruction executed"),
        descript_tuple_t("SIGFPE", SIGFPE, "floating-point exception"),
        descript_tuple_t("SIGKILL", SIGKILL, "kill program"),
        descript_tuple_t("SIGBUS", SIGBUS, "bus error"),
        descript_tuple_t("SIGSEGV", SIGSEGV, "segmentation violation"),
        descript_tuple_t("SIGSYS", SIGSYS, "non-existent system call invoked"),
        descript_tuple_t("SIGPIPE", SIGPIPE, "write on a pipe with no reader"),
        descript_tuple_t("SIGALRM", SIGALRM, "real-time timer expired"),
        descript_tuple_t("SIGTERM", SIGTERM, "software termination signal"),
        descript_tuple_t("SIGURG", SIGURG, "urgent condition present on socket"),
        descript_tuple_t("SIGSTOP", SIGSTOP, "stop (cannot be caught or ignored)"),
        descript_tuple_t("SIGTSTP", SIGTSTP, "stop signal generated from keyboard"),
        descript_tuple_t("SIGCONT", SIGCONT, "continue after stop"),
        descript_tuple_t("SIGCHLD", SIGCHLD, "child status has changed"),
        descript_tuple_t("SIGTTIN", SIGTTIN, "background read attempted from control terminal"),
        descript_tuple_t("SIGTTOU", SIGTTOU, "background write attempted to control terminal"),
        descript_tuple_t("SIGIO ", SIGIO, "I/O is possible on a descriptor"),
        descript_tuple_t("SIGXCPU", SIGXCPU, "cpu time limit exceeded"),
        descript_tuple_t("SIGXFSZ", SIGXFSZ, "file size limit exceeded"),
        descript_tuple_t("SIGVTALRM", SIGVTALRM, "virtual time alarm"),
        descript_tuple_t("SIGPROF", SIGPROF, "profiling timer alarm"),
        descript_tuple_t("SIGWINCH", SIGWINCH, "Window size change"),
        descript_tuple_t("SIGINFO", SIGINFO, "status request from keyboard"),
        descript_tuple_t("SIGUSR1", SIGUSR1, "User defined signal 1"),
        descript_tuple_t("SIGUSR2", SIGUSR2, "User defined signal 2")
    };

    int key = (int) _type;
    for(const auto& itr : descript_data)
        if(std::get<1>(itr) == key)
        {
            descript(itr);
            break;
        }

    return ss.str();
}

//============================================================================//

std::string signal_settings::str()
{
    std::stringstream ss;
    auto spacer = [&] () { return "    "; };

#if defined(SIGNAL_AVAILABLE)

    ss << std::endl
       << spacer() << "Signal detection activated. Signal exception settings:\n"
       << std::endl;

    ss << spacer() << "Enabled:" << std::endl;
    for(const auto& itr : signals_enabled)
        ss << spacer() << spacer() << signal_settings::str(itr) << std::endl;

    ss << "\n" << spacer() << "Disabled:" << std::endl;
    for(const auto& itr : signals_disabled)
        ss << spacer() << spacer() << signal_settings::str(itr) << std::endl;

#else

    ss << std::endl
       << spacer()
       << "Signal detection not available" << std::endl;

#endif

    return ss.str();
}

//============================================================================//

} // namespace toast

//============================================================================//
