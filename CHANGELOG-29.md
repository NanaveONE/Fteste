# Correção 29 — ReXGlue Android NDK

Corrige a contagem do patch 28: o cabeçalho oficial possui duas chamadas com prefixo `std::from_chars(range.data(), ...)` (uma inteira e uma float). A verificação anterior esperava somente uma e interrompia o build com `BLOCKED: Expected float parser not found`. Mantém validação de quatro blocos `#if REX_PLATFORM_MAC`. O patch altera apenas a cópia do SDK em `build/deps/`.
