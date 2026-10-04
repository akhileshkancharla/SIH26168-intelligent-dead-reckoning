add_library(sih26168_gnss_precheck STATIC src/fix_precheck.cpp)
target_include_directories(sih26168_gnss_precheck PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>)
target_compile_features(sih26168_gnss_precheck PUBLIC cxx_std_20)

add_executable(sih26168_gnss_precheck_tests tests/test_fix_precheck.cpp)
target_link_libraries(sih26168_gnss_precheck_tests PRIVATE sih26168_gnss_precheck)
add_test(NAME gnss-precheck-native COMMAND sih26168_gnss_precheck_tests)
