# Integração 23 — ReXGlue host Codegen Linux confirmado e Fable II C++ privado

O artifact `fable2-rexglue-codegen-linux-x86_64.zip` produzido com o workflow 22 foi validado na prática em Linux x86_64. `rexglue --version` e `rexglue codegen --help` funcionam; as duas hashes SHA-256 correspondem ao manifesto. `default.xex` privado foi validado como Fable II GOTY EUA/Europa (SHA-256 `88c4ef2e...2372662`).

Novo script `scripts/generate_fable2_cpp_private.py`:

- Usa O MANIFESTO COMPLETO e a tabela de switches do próprio `himdo/Fable-2-Recomp` (o mesmo Fable II), sem criar um manifesto alternativo ou outro jogo.
- Valida os hashes e a arquitetura do verdadeiro artifact Codegen Linux e o perfil XEX no catálogo original.
- Gera C++ em `build/fable2-guest-codegen-private/` — nunca em repositórios públicos, nem no submódulo original.
- Não exige a pasta inteira `data/`, Android NDK, Vulkan nem shaders para essa etapa inicial; apenas `default.xex` e os arquivos PUBLICOS do Fable-2-Recomp.
- Trata saída antiga como bloqueio para não misturar perfis ou arquivos de jogos.
- Exige `sources.cmake` e arquivos C++ não vazios. Gera `codegen-summary.json` sanitizado, sem bytes de jogo ou códigos gerados.
- Não envia nem distribui nenhum ativo comercial. A ferramenta x86_64 roda em Linux x86_64, **não em Termux ARM64**.

Teste offline: 8 testes sintéticos, sem jogo. **Não afirma que os arquivos C++ reais já foram gerados**, nem que `libfable2.so`/Plume/APK já estejam compilados.
