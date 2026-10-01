add_library(
    sih26168_alignment_candidate STATIC
    src/candidate_alignment_estimator.cpp
)
target_include_directories(
    sih26168_alignment_candidate
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
target_compile_features(sih26168_alignment_candidate PUBLIC cxx_std_20)
target_link_libraries(sih26168_alignment_candidate PUBLIC Eigen3::Eigen)

add_executable(
    sih26168_alignment_candidate_tests
    tests/test_candidate_alignment_estimator.cpp
)
target_link_libraries(
    sih26168_alignment_candidate_tests
    PRIVATE sih26168_alignment_candidate
)
add_test(
    NAME alignment-candidate-native
    COMMAND sih26168_alignment_candidate_tests
)

add_library(
    sih26168_alignment_estimate STATIC
    src/alignment_estimate.cpp
)
target_include_directories(
    sih26168_alignment_estimate
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/core/include>
)
target_compile_features(sih26168_alignment_estimate PUBLIC cxx_std_20)
target_link_libraries(
    sih26168_alignment_estimate
    PUBLIC Eigen3::Eigen
)

add_executable(
    sih26168_alignment_estimate_tests
    tests/test_alignment_estimate.cpp
)
target_link_libraries(
    sih26168_alignment_estimate_tests
    PRIVATE sih26168_alignment_estimate
)
add_test(
    NAME alignment-estimate-native
    COMMAND sih26168_alignment_estimate_tests
)
