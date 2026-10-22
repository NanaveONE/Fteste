# Shader translation status (Fable II Android)

- Confirmed private source: both `.sbk` user inputs have the same 588 Xenos shader containers, 137 VS, 451 PS.
- The XenosRecomp `shader.h` layout reads all 588 as in-bounds; only 576 microcode sequences are distinct.
- Source validation does not mean HLSL translation, DXC compile or SPIR-V pass.
- `validate_xenosrecomp_cache.py` checks the actual produced compressed SPIR-V and provenance against the private `xenos-scan/` files. It fails closed if 100% coverage is absent.
- To run XenosRecomp for real, see `CHANGELOG-11.md`. Public CI compiles the Linux host tool without private game assets.
- Vulkan Plume must still be fixed for Fable-specific GPU commands and EDRAM even after 100% shader translation.
