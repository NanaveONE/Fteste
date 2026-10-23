# Correção 28 — Android NDK r27c / std::from_chars(float)

A execução 39881305806 avançou até o Ninja e falhou em `rex/string/numeric.h` (linhas 195 e 322). O NDK r27c usa libc++ sem o overload de ponto flutuante de `std::from_chars` nesse alvo.

O script `scripts/fix_rexglue_android_float_chars.py` modifica **somente** `build/deps/rexglue-xerenge/include/rex/string/numeric.h`, depois do clone do SDK e antes do build. Não modifica os arquivos do Fable II, nem publica material privado. É idempotente e falha se o cabeçalho não corresponder à revisão esperada.

**Limitação:** o fallback Android usa `strtof`/`strtod` do Bionic, que respeitam o locale C padrão do processo. Para um jogo com locale numérico alterado, será necessária uma alternativa estritamente independente de locale. O patch resolve especificamente a ausência de overload no build; não comprova execução do jogo.

Depois de aplicar e fazer push, execute novamente `gh workflow run build-fable2-arm64-26.yml --repo NanaveONE/Fteste -f release_tag=guest-input-26`.
