# Fable II Android Plume GPU plugin (source port from Xerenge's renderer).
# Xerenge is GPL-3.0-or-later. Retain attribution/license upon distribution.
#
# IMPORTANT: compiling a plugin with Fable-specific shaders does NOT mean that
# the draw state/EDRAM/shader pipeline is already compatible with Fable II.
cmake_minimum_required(VERSION 3.25)
project(fable2_plume LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

foreach(required IN ITEMS REXSDK_DIR XERENGE_ROOT PLUME_ROOT XENOS_RECOMP_ROOT
                          FABLE2_SHADER_CACHE_CPP FABLE2_SHADER_HLSL_DIR
                          FABLE2_PLUME_DRAW_CPP FABLE2_PLUME_GRAPHICS_CPP)
  if(NOT DEFINED ${required} OR "${${required}}" STREQUAL "")
    message(FATAL_ERROR "Missing required -D${required}=...")
  endif()
endforeach()
set(XERENGE_REXGLUE "${XERENGE_ROOT}/rexglue")
set(XERENGE_SRC "${XERENGE_REXGLUE}/src")
if(NOT EXISTS "${FABLE2_SHADER_CACHE_CPP}" OR
   NOT EXISTS "${FABLE2_SHADER_HLSL_DIR}" OR
   NOT EXISTS "${XERENGE_SRC}/plume_renderer/plugin_main.cpp" OR
   NOT EXISTS "${FABLE2_PLUME_DRAW_CPP}" OR
   NOT EXISTS "${FABLE2_PLUME_GRAPHICS_CPP}")
  message(FATAL_ERROR "Fable shader cache, HLSL directory, or Xerenge renderer missing")
endif()
# Do not silently use generated/shader_cache.cpp from Burnout Revenge.
message(STATUS "Fable II shader cache: ${FABLE2_SHADER_CACHE_CPP}")

# ReXGlue GPU ABI and runtime MUST be the same source build used for libfable2
# and librexruntime. API header equality by itself is insufficient.
if(FABLE2_MEMGATE71_DIAGNOSTIC)
  # Import the SAME gate DSO before adding the SDK; the diagnostic ReXGlue
  # CMake hook links to it rather than compiling a second process-wide gate.
  if(NOT ANDROID OR NOT IS_ABSOLUTE "${FABLE2_MEMGATE71_LIB}" OR
     NOT EXISTS "${FABLE2_MEMGATE71_LIB}")
    message(FATAL_ERROR "Memgate71 GPU requires the exact guest gate .so")
  endif()
  file(READ "${REXSDK_DIR}/CMakeLists.txt" _fable_sdk_cmake)
  if(NOT _fable_sdk_cmake MATCHES "FABLE2_MEMGATE71_SHARED_RUNTIME")
    message(FATAL_ERROR "ReXGlue Memgate71 pinned SDK scopes not installed")
  endif()
  set(FABLE2_MEMGATE71_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../sdk/fable_memgate71.cpp")
  set(FABLE2_MEMGATE71_INCLUDE "${CMAKE_CURRENT_SOURCE_DIR}/../sdk")
  add_library(fable2_memgate71 SHARED IMPORTED GLOBAL)
  set_target_properties(fable2_memgate71 PROPERTIES IMPORTED_LOCATION "${FABLE2_MEMGATE71_LIB}")
endif()
add_subdirectory("${REXSDK_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/rexglue-sdk")
set(PLUME_SDL_VULKAN_ENABLED OFF CACHE BOOL "" FORCE)
set(PLUME_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
add_subdirectory("${PLUME_ROOT}" "${CMAKE_CURRENT_BINARY_DIR}/plume")
set_target_properties(plume PROPERTIES POSITION_INDEPENDENT_CODE ON)

set(SOURCES
  "${FABLE2_PLUME_GRAPHICS_CPP}"
  "${XERENGE_SRC}/plume_renderer/plume_shader_cache.cpp"
  "${XERENGE_SRC}/plume_renderer/plume_swapchain.cpp"
  "${XERENGE_SRC}/plume_renderer/plume_postfx.cpp"
  # Isolated Fable II-specific draw state handling; never patch the Xerenge source checkout.
  "${FABLE2_PLUME_DRAW_CPP}"
  "${XERENGE_SRC}/plume_renderer/plume_etc2_cache.cpp"
  "${XERENGE_SRC}/plume_renderer/plume_interp.cpp"
  "${XERENGE_SRC}/plume_renderer/plume_framegen.cpp"
  "${XERENGE_SRC}/plume_renderer/plume_settings.cpp"
  "${XERENGE_SRC}/plume_renderer/plume_colour_table.cpp"
  "${XERENGE_SRC}/plume_renderer/plugin_main.cpp"
  "${XERENGE_SRC}/plume_renderer/shader_source_info.cpp"
  "${XENOS_RECOMP_ROOT}/thirdparty/smol-v/source/smolv.cpp"
  "${FABLE2_SHADER_CACHE_CPP}"
)
# The Xerenge shader cache looks for a separate Bootstrap-suffixed symbol set.
# This is generated from captured Fable II microcode, NEVER from Burnout data.
if(FABLE2_RUNTIME_SHADER_CACHE_CPP)
  if(NOT EXISTS "${FABLE2_RUNTIME_SHADER_CACHE_CPP}")
    message(FATAL_ERROR "Fable runtime shader cache missing: ${FABLE2_RUNTIME_SHADER_CACHE_CPP}")
  endif()
  list(APPEND SOURCES "${FABLE2_RUNTIME_SHADER_CACHE_CPP}")
  message(STATUS "Fable II runtime shader cache: ${FABLE2_RUNTIME_SHADER_CACHE_CPP}")
endif()
if(ANDROID)
  list(APPEND SOURCES "${XERENGE_SRC}/plume_renderer/frame_clock_provider_android.cpp")
endif()

# Compile the HLSL metadata generator for the build HOST, not Android ARM64;
# a host utility must run at compile time even when cross-compiling.
find_program(HOST_CXX NAMES clang++ c++ g++ NO_CMAKE_FIND_ROOT_PATH REQUIRED)
set(HOST_SHADER_GEN "${CMAKE_CURRENT_BINARY_DIR}/host/shader_source_info_gen")
add_custom_command(
  OUTPUT "${HOST_SHADER_GEN}"
  COMMAND "${CMAKE_COMMAND}" -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/host"
  COMMAND "${HOST_CXX}" -std=c++20 -O2 -I "${XERENGE_SRC}"
          "${XERENGE_REXGLUE}/tools/shader_source_info_gen.cpp"
          "${XERENGE_SRC}/plume_renderer/shader_source_info.cpp"
          -o "${HOST_SHADER_GEN}"
  DEPENDS "${XERENGE_REXGLUE}/tools/shader_source_info_gen.cpp"
          "${XERENGE_SRC}/plume_renderer/shader_source_info.cpp"
          "${XERENGE_SRC}/plume_renderer/shader_source_info.h"
  VERBATIM
)
file(GLOB FABLE2_HLSL CONFIGURE_DEPENDS "${FABLE2_SHADER_HLSL_DIR}/*.hlsl")
set(SHADER_INFO_CPP "${CMAKE_CURRENT_BINARY_DIR}/shader_source_info_table.cpp")
add_custom_command(
  OUTPUT "${SHADER_INFO_CPP}"
  COMMAND "${HOST_SHADER_GEN}" "${FABLE2_SHADER_HLSL_DIR}" "${SHADER_INFO_CPP}"
  DEPENDS "${HOST_SHADER_GEN}" ${FABLE2_HLSL}
  COMMENT "Extracting Fable II shader metadata for the GPU renderer"
  VERBATIM
)
list(APPEND SOURCES "${SHADER_INFO_CPP}")

add_library(rexgpu-plume SHARED ${SOURCES})
set_target_properties(rexgpu-plume PROPERTIES
  OUTPUT_NAME "rexgpu-plume" CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN ON POSITION_INDEPENDENT_CODE ON)
# FABLE2_PLUME_46_BUILDSCRIPT: override only plume_draw.h for the Fable build.
# Its GuestDrawSnapshot layout MUST be consistent in all Plume translation units.
if(NOT DEFINED FABLE2_PLUME_OVERLAY_DIR OR
   NOT EXISTS "${FABLE2_PLUME_OVERLAY_DIR}/plume_renderer/plume_draw.h")
  message(FATAL_ERROR "Fable Plume46 patched snapshot header missing")
endif()
target_include_directories(rexgpu-plume BEFORE PRIVATE
  "${FABLE2_PLUME_OVERLAY_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_definitions(rexgpu-plume PRIVATE XERENGE_HAS_SHADER_CACHE=1 FABLE2_PLUME_PORT=1)
target_include_directories(rexgpu-plume PRIVATE
  "${XERENGE_SRC}" "${PLUME_ROOT}"
  "${XENOS_RECOMP_ROOT}/thirdparty/smol-v/source"
  "${REXSDK_DIR}/thirdparty/renderdoc"
  "${XERENGE_REXGLUE}/thirdparty/smaa")

if(NOT TARGET xxHash::xxhash)
  add_subdirectory("${XENOS_RECOMP_ROOT}/thirdparty/xxHash/cmake_unofficial"
                   "${CMAKE_CURRENT_BINARY_DIR}/xenos-xxhash")
endif()
if(NOT TARGET libzstd)
  set(ZSTD_BUILD_PROGRAMS OFF CACHE BOOL "" FORCE)
  set(ZSTD_BUILD_SHARED OFF CACHE BOOL "" FORCE)
  set(ZSTD_BUILD_STATIC ON CACHE BOOL "" FORCE)
  add_subdirectory("${XENOS_RECOMP_ROOT}/thirdparty/zstd/build/cmake"
                   "${CMAKE_CURRENT_BINARY_DIR}/xenos-zstd")
endif()

set(ETCPAK "${XERENGE_REXGLUE}/thirdparty/etcpak")
if(NOT EXISTS "${ETCPAK}/ProcessRGB.cpp")
  message(FATAL_ERROR "Missing Xerenge etcpak submodule: run git submodule update --init --recursive")
endif()
add_library(fable2-etcpak STATIC "${ETCPAK}/ProcessRGB.cpp"
  "${ETCPAK}/Tables.cpp" "${ETCPAK}/Dither.cpp")
set_target_properties(fable2-etcpak PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(fable2-etcpak PUBLIC "${ETCPAK}")

target_link_libraries(rexgpu-plume PRIVATE plume rex::runtime
  libzstd xxHash::xxhash fable2-etcpak z)

# Memgate71: link the EXACT shared gate DSO used by the guest/runtime bundle.
# Entry/exit callbacks are opt-in; real Plume queue/DMA scope coverage is NOT
# certified merely because this ABI is present.
if(FABLE2_MEMGATE71_DIAGNOSTIC)
  target_sources(rexgpu-plume PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/fable_memgate71_gpu.cpp")
  target_include_directories(rexgpu-plume PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../sdk")
  target_link_libraries(rexgpu-plume PRIVATE fable2_memgate71)
endif()

if(ANDROID)
  set(ADRENO_ROOT "${XERENGE_REXGLUE}/android/thirdparty/libadrenotools")
  if(NOT EXISTS "${ADRENO_ROOT}/CMakeLists.txt")
    message(FATAL_ERROR "Missing libadrenotools submodule in Xerenge")
  endif()
  add_subdirectory("${ADRENO_ROOT}" "${CMAKE_CURRENT_BINARY_DIR}/adrenotools" EXCLUDE_FROM_ALL)
  target_link_libraries(rexgpu-plume PRIVATE adrenotools)
  add_dependencies(rexgpu-plume main_hook file_redirect_hook gsl_alloc_hook)
endif()

message(WARNING "Plume is still Xerenge's renderer logic. Fable II's GPU states,"
                "runtime-generated shaders and EDRAM resolves are NOT validated.")
