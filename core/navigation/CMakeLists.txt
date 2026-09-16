include(FetchContent)

set(SIH26168_EIGEN_VERSION "3.4.0")
set(SIH26168_EIGEN_COMMIT "3147391d946bb4b6c68edd901f2add6ac1f31f8c")

FetchContent_Declare(
    eigen
    GIT_REPOSITORY https://gitlab.com/libeigen/eigen.git
    GIT_TAG ${SIH26168_EIGEN_COMMIT}
    GIT_PROGRESS TRUE
    SOURCE_SUBDIR cmake/sih26168-header-only
)
FetchContent_MakeAvailable(eigen)

set(_eigen_macros "${eigen_SOURCE_DIR}/Eigen/src/Core/util/Macros.h")
if(NOT EXISTS "${_eigen_macros}")
    message(FATAL_ERROR "Pinned Eigen headers are unavailable at ${_eigen_macros}")
endif()
file(STRINGS "${_eigen_macros}" _eigen_version_lines
    REGEX "^#define EIGEN_(WORLD|MAJOR|MINOR)_VERSION[ \\t]+[0-9]+$")
foreach(_component WORLD MAJOR MINOR)
    string(REGEX MATCH
        "EIGEN_${_component}_VERSION[ \\t]+([0-9]+)"
        _match
        "${_eigen_version_lines}")
    if(_match STREQUAL "")
        message(FATAL_ERROR "Cannot resolve Eigen ${_component} version from ${_eigen_macros}")
    endif()
    set(_eigen_${_component} "${CMAKE_MATCH_1}")
endforeach()
set(_eigen_resolved_version
    "${_eigen_WORLD}.${_eigen_MAJOR}.${_eigen_MINOR}")
if(NOT _eigen_resolved_version VERSION_EQUAL SIH26168_EIGEN_VERSION)
    message(FATAL_ERROR
        "Eigen version mismatch: expected ${SIH26168_EIGEN_VERSION}, resolved ${_eigen_resolved_version}")
endif()
message(STATUS
    "SIH26168 Eigen ${_eigen_resolved_version} (${SIH26168_EIGEN_COMMIT})")

add_library(sih26168_eigen INTERFACE)
add_library(Eigen3::Eigen ALIAS sih26168_eigen)
target_include_directories(
    sih26168_eigen
    SYSTEM INTERFACE "${eigen_SOURCE_DIR}"
)

if(MSVC)
    if(NOT CMAKE_GENERATOR_PLATFORM STREQUAL "x64")
        message(FATAL_ERROR "The SIH26168 Windows native build requires -A x64")
    endif()
    if(NOT CMAKE_VS_PLATFORM_TOOLSET_HOST_ARCHITECTURE STREQUAL "x64")
        message(FATAL_ERROR "The SIH26168 Windows native build requires -T host=x64")
    endif()
endif()

add_library(sih26168_navigation_smoke STATIC src/smoke.cpp)
target_include_directories(sih26168_navigation_smoke PUBLIC ${PROJECT_SOURCE_DIR}/core/include)
target_compile_features(sih26168_navigation_smoke PUBLIC cxx_std_20)
add_executable(sih26168_navigation_smoke_test tests/smoke_test.cpp)
target_link_libraries(sih26168_navigation_smoke_test PRIVATE sih26168_navigation_smoke)
add_test(NAME navigation-smoke COMMAND sih26168_navigation_smoke_test)

add_library(sih26168_navigation_core STATIC src/navigation_core.cpp)
target_include_directories(
    sih26168_navigation_core
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
target_compile_features(sih26168_navigation_core PUBLIC cxx_std_20)
target_link_libraries(sih26168_navigation_core PUBLIC Eigen3::Eigen)

add_executable(
    sih26168_navigation_core_tests
    tests/test_navigation_core.cpp
)
target_link_libraries(
    sih26168_navigation_core_tests
    PRIVATE sih26168_navigation_core
)
add_test(
    NAME navigation-core-native
    COMMAND sih26168_navigation_core_tests
        "${CMAKE_CURRENT_BINARY_DIR}/cpp_test_results.json"
        "${CMAKE_CURRENT_BINARY_DIR}/cpp_jacobian_results.json"
)

add_executable(
    sih26168_navigation_replay
    verification/replay_main.cpp
)
target_link_libraries(
    sih26168_navigation_replay
    PRIVATE sih26168_navigation_core
)
