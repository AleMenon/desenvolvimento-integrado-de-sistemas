cmake_minimum_required(VERSION 3.18)

project(
    desenvolvimento_integrado_de_sistemas
    VERSION 0.1.0
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(BLA_VENDOR OpenBLAS)

# Eigen 5 mantém o nome do pacote Eigen3, mas não aceita pedidos de versão 3.x.
find_package(Eigen3 REQUIRED NO_MODULE)
find_package(BLAS REQUIRED)

add_executable(
    environment_check
    tests/environment/smoke.cpp
)

target_link_libraries(
    environment_check
    PRIVATE
    Eigen3::Eigen
    BLAS::BLAS
)

target_compile_definitions(
    environment_check
    PRIVATE EIGEN_USE_BLAS
)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
add_library(matrix_operations server/cpp/matrix_operations.cpp)
target_include_directories(matrix_operations PUBLIC server/cpp)
target_link_libraries(matrix_operations PUBLIC Eigen3::Eigen BLAS::BLAS)
target_compile_definitions(matrix_operations PUBLIC EIGEN_USE_BLAS)

add_library(cgnr server/cpp/cgnr.cpp)
target_link_libraries(cgnr PUBLIC matrix_operations)

include(CTest)
if(BUILD_TESTING)
    add_executable(cgnr_runner tests/integration/cgnr_runner.cpp)
    target_link_libraries(cgnr_runner PRIVATE cgnr)
    add_executable(test_cgnr tests/unit/test_cgnr.cpp)
    target_link_libraries(test_cgnr PRIVATE cgnr)
    add_test(NAME cgnr_cpp COMMAND test_cgnr)
    add_test(NAME environment_cpp COMMAND environment_check)
    add_executable(matrix_operations_runner tests/integration/matrix_operations_runner.cpp)
    target_link_libraries(matrix_operations_runner PRIVATE matrix_operations)
    # Python é necessário somente para a comparação opcional via pytest.
endif()

# TASK-13: servidor HTTP/JSON C++ compatível com o cliente da TASK-09.
include(FetchContent)
find_package(nlohmann_json 3.11 QUIET)
find_package(Threads REQUIRED)
if(NOT nlohmann_json_FOUND)
    set(JSON_BuildTests OFF CACHE INTERNAL "")
    FetchContent_Declare(nlohmann_json
        URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
    )
    FetchContent_MakeAvailable(nlohmann_json)
endif()

find_path(CPP_HTTPLIB_INCLUDE_DIR NAMES httplib.h)
if(NOT CPP_HTTPLIB_INCLUDE_DIR)
    FetchContent_Declare(cpp_httplib
        URL https://github.com/yhirose/cpp-httplib/archive/refs/tags/v0.18.7.tar.gz
    )
    FetchContent_GetProperties(cpp_httplib)
    if(NOT cpp_httplib_POPULATED)
        FetchContent_Populate(cpp_httplib)
    endif()
    set(CPP_HTTPLIB_INCLUDE_DIR "${cpp_httplib_SOURCE_DIR}")
endif()

add_executable(reconstruction_server server/cpp/reconstruction_server.cpp)
target_include_directories(reconstruction_server PRIVATE "${CPP_HTTPLIB_INCLUDE_DIR}")
target_link_libraries(reconstruction_server PRIVATE cgnr nlohmann_json::nlohmann_json Threads::Threads)
# Instrumentação isolada para testes de estados assíncronos.
# O gancho só é compilado quando BUILD_TESTING=ON e não altera execuções normais.
if(BUILD_TESTING)
    target_compile_definitions(reconstruction_server PRIVATE TASK13_TEST_HOOKS)
endif()
# TASK-08 — Validação experimental com matrizes reais.
add_executable(cgnr_experiment_runner
    tests/integration/cgnr_experiment_runner.cpp
)
target_link_libraries(cgnr_experiment_runner PRIVATE cgnr)
