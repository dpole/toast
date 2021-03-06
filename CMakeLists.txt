cmake_minimum_required(VERSION 3.1.3 FATAL_ERROR)

#-----------------------------------------------------------------------
# - Enforce an out-of-source builds before anything else
#
if(${CMAKE_SOURCE_DIR} STREQUAL ${CMAKE_BINARY_DIR})
  message(STATUS "TOAST requires an out-of-source build.")
  message(STATUS "Please remove these files from ${CMAKE_BINARY_DIR} first:")
  message(STATUS "\tCMakeCache.txt")
  message(STATUS "\tCMakeFiles")
  message(STATUS "Once these files are removed, create a separate directory")
  message(STATUS "and run CMake from there")
  message(FATAL_ERROR "in-source build detected")
endif()

project(TOAST C CXX)

STRING(TOLOWER "${CMAKE_PROJECT_NAME}" LPROJECT_NAME)
set(CMAKE_BUILD_TYPE Release CACHE STRING "CMake build type")
# Above cache variable isn't immediately set in first build
if("${CMAKE_BUILD_TYPE}" STREQUAL "")
    set(CMAKE_BUILD_TYPE Release)
endif()
string(TOUPPER ${CMAKE_BUILD_TYPE} UPPER_BUILD_TYPE)

# Prefix our module paths for preference over CMake ones if exist
set(CMAKE_MODULE_PATH
    ${PROJECT_SOURCE_DIR}/cmake/Modules
    ${PROJECT_SOURCE_DIR}/cmake/Packages
    ${CMAKE_MODULE_PATH})

set(CMAKE_USER_MAKE_RULES_OVERRIDE_C
    ${CMAKE_SOURCE_DIR}/cmake/Modules/MakeRulesC.cmake)

set(CMAKE_USER_MAKE_RULES_OVERRIDE_CXX
    ${CMAKE_SOURCE_DIR}/cmake/Modules/MakeRulesCXX.cmake)

include(MakeRulesC)
include(MakeRulesCXX)
include(GenericFunctions)
set_project_version("2" "2" "0" "Time Ordered Astrophysics Scalable Tools")
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_INSTALL_MESSAGE LAZY)
set(PROJECT_BUGREPORT "work@theodorekisner.com")

# clear CMAKE_PREFIX_PATH if not explicitly specified on command line
# - this helps find_package() ensure the current package being search for
#   has <package_name>_ROOT and/or <package_name>_DIR at the beginning
#   of CMAKE_PREFIX_PATH
parse_command_line_options()
if(NOT "${CMAKE_ARGS}" MATCHES "CMAKE_PREFIX_PATH")
    unset(CMAKE_PREFIX_PATH CACHE)
endif()

include(GenericOptions)
include(Packages)
include(LibraryBuildOptions)
include(InstallDirs)
include(MacroUtilities)
include(LibrarySuffixes)

add_feature(CMAKE_INSTALL_PREFIX "Installation prefix")
add_feature(CMAKE_CXX_FLAGS "CXX flags")
add_feature(CMAKE_BUILD_TYPE "Build type")
add_feature(CMAKE_CXX_FLAGS_${UPPER_BUILD_TYPE} "CXX flags for ${CMAKE_BUILD_TYPE}")
add_feature(CMAKE_GENERATOR "Build file generator")

if(BUILD_TESTING)
    if(DEFINED CTEST_SITE AND "${CTEST_SITE}" STREQUAL "")
        unset(CTEST_SITE CACHE)
    endif()
    get_os_node_name(_SITE)
    set(CTEST_SITE "${_SITE}" CACHE STRING "OS name over network")
    add_feature(CTEST_SITE "Site name (e.g. hostname)")
endif(BUILD_TESTING)

foreach(_INCLUDE_DIR ${EXTERNAL_INCLUDE_DIRS})
    include_directories(SYSTEM ${_INCLUDE_DIR})
endforeach()


#-----------------------------------------------------------------------
# BUILD_CXXSTD
# Choose C++ Standard to build against, if supported.
# Mark as advanced because most users will not need it.
include(ConfigureCXXSTD)

add_subdirectory(src)

#------------------------------------------------------------------------------#

file(GLOB PYTHON_EXAMPLES
    ${CMAKE_SOURCE_DIR}/examples/*.py
    ${CMAKE_SOURCE_DIR}/pipelines/*.py)

install(FILES ${PYTHON_EXAMPLES} DESTINATION ${CMAKE_INSTALL_BINDIR}
    PERMISSIONS
    OWNER_READ    GROUP_READ    WORLD_READ
    OWNER_WRITE
    OWNER_EXECUTE GROUP_EXECUTE WORLD_EXECUTE)

execute_process(COMMAND ${CMAKE_COMMAND} -E copy_directory
    ${CMAKE_SOURCE_DIR}/examples ${CMAKE_BINARY_DIR}/examples)
#------------------------------------------------------------------------------#

include(Documentation)
if(DOXYGEN_DOCS)
    SET(CMAKE_INSTALL_MESSAGE NEVER)
    Generate_Documentation(Doxyfile.${PROJECT_NAME})
    SET(CMAKE_INSTALL_MESSAGE LAZY)
endif()

#------------------------------------------------------------------------------#

add_option(BUILD_TESTING "Enable CTest and CDash submission" OFF)

include(CMakeUninstallTarget)
include(Testing)

print_features()

if(EXISTS ${CMAKE_BINARY_DIR}/compile-testing)
    execute_process(COMMAND ${CMAKE_COMMAND} -E remove_directory
        ${CMAKE_BINARY_DIR}/compile-testing)
endif(EXISTS ${CMAKE_BINARY_DIR}/compile-testing)
