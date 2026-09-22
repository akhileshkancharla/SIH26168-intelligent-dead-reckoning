cmake_minimum_required(VERSION 3.20)

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(SIH26168NavigationJni LANGUAGES CXX)
    set(CMAKE_CXX_STANDARD 20)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)
    set(CMAKE_CXX_EXTENSIONS OFF)
    enable_testing()
    add_subdirectory("../../core/navigation" "${CMAKE_CURRENT_BINARY_DIR}/navigation-core")
endif()

add_library(
    sih26168_navigation_jni_boundary STATIC
    src/navigation_jni_boundary.cpp
    src/navigation_jni_wire.cpp
)
target_include_directories(
    sih26168_navigation_jni_boundary
    PUBLIC "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
)
target_compile_features(sih26168_navigation_jni_boundary PUBLIC cxx_std_20)
target_link_libraries(sih26168_navigation_jni_boundary PUBLIC sih26168_navigation_core)
set_target_properties(sih26168_navigation_jni_boundary PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(ANDROID)
    add_library(sih26168_navigation_jni SHARED src/navigation_jni.cpp)
    target_compile_features(sih26168_navigation_jni PRIVATE cxx_std_20)
    target_link_libraries(sih26168_navigation_jni PRIVATE sih26168_navigation_jni_boundary)
endif()

if(NOT ANDROID)
    add_executable(sih26168_navigation_jni_tests tests/test_navigation_jni.cpp)
    target_link_libraries(sih26168_navigation_jni_tests PRIVATE sih26168_navigation_jni_boundary)
    add_test(NAME navigation-jni-boundary COMMAND sih26168_navigation_jni_tests)
endif()
