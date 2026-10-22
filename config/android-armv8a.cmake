# Cache inicial para Android NDK + CMake. Ainda nao e um CMakeLists de Fable II.
# Invocacao futura: cmake -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31 ...
set(ANDROID_ABI "arm64-v8a" CACHE STRING "Target ABI")
set(ANDROID_PLATFORM "android-31" CACHE STRING "Target Android API")
set(CMAKE_C_FLAGS_INIT "-march=armv8-a" CACHE STRING "Baseline Snapdragon 650")
set(CMAKE_CXX_FLAGS_INIT "-march=armv8-a" CACHE STRING "Baseline Snapdragon 650")
# Nao habilitar FP16, dotprod, armv8.2-a ou outras extensoes novas sem testar.
