# Fable II Android — Correções 08 (auditoria do Fteste)

Este pacote contém alterações **reais** de código a partir da integração 07.
**Não é um APK jogável** e não resolve a incompatibilidade de runtime/renderer
sem compilar e depurar a versão real do jogo em Android.

## Correções confirmadas

1. `prepare_android_target.py`: agora substitui a declaração de `exe_dir`
   apenas dentro de `Fable2App::OnConfigurePaths`, em vez de substituir duas
   ocorrências. Era a causa exata do CI vermelho (`data path: expected one
   upstream anchor, found 2`). Testes regressivos simulam as duas ocorrências
   e, quando disponível, usam o submódulo Fable-2-Recomp real.
2. `Fable2App::OnPostInitLogging`: no Android, `fable2_config.toml` é criado
   sob `FABLE2_USER_ROOT`, que `Fable2Activity` aponta para a pasta gravável
   do aplicativo. Saves e cache mantêm o mesmo comportamento. Desktop intacto.
3. `CMakeLists.txt` da cópia do Fable II: na compilação Android, deixa de
   executar o staging desktop de scripts Lua, arquivos `.cmd`, README e
   imagem de ícone no diretório nativo da biblioteca. Esses passos não são
   apropriados no destino Android. O jogo Android não inclui automaticamente
   os scripts Lua de mod/debug usados no desktop.
4. `Fable2LauncherActivity`: verifica o SHA-256 + tamanho de um XEX
   compatível *antes* de copiar os GB do jogo; copia para `game.pending`,
   verifica `data/gold_version.txt`, `data/startup.vfsconfig`, TU1 misturado
   e arquivo de idioma alemão quando aplicável. Após a cópia, verifica o
   XEX novamente e só então comuta `game.pending` para `game`, preservando
   `game.backup` durante a troca. A instalação antiga não é sobrescrita
   durante a cópia. A importação não aceita imagem ISO diretamente.
5. `Fable2GameCompatibility.java`: tabela local dos 6 hashes publicados no
   `constants/game_versions.json` do Fable-2-Recomp **na revisão pinada**.
   Não inclui bytes de jogos ou arquivos comerciais. O teste compara a
   tabela ao catálogo real se o submódulo estiver disponível.
6. `compare_sdk_abi.py`: adicionalmente verifica diferença nos métodos
   virtuais de `IGraphicsSystem`. Rejeita a compatibilidade de binários
   cruzados apenas por terem ambos `kGpuPluginAbiVersion = 1`.
7. Novos testes Java + Python e regressões reais de CMake.

## Limitações explícitas

- ABI diverge nos dois forks do ReXGlue. Este pacote **detecta e impede
  pressuposições erradas**, mas **não reconcilia as implementações internas**.
  É obrigatório construir o jogo, runtime e Plume **com a mesma árvore de SDK**
  e corrigir os erros de compilação/comportamento desse SDK para Fable II.
- EDRAM, shaders dinâmicos, texturas, Vulkan swapchain, áudio, threads e saves
  continuam sem validação no Android. Precisam de build e logs de hardware real.
- Não houve compilação do APK aqui por falta de SDK/NDK e conteúdo legal do jogo.
- Os testes de Java cobrem apenas a classe independente do SDK Android, não
  compilam todas as Activities com `android.jar`.
- A importação por staging usa espaço adicional temporário equivalente à
  nova cópia de Fable II; garanta armazenamento livre suficiente.

## Validação

`python3 -m unittest discover -s tests -v` passa nos testes locais disponíveis.
O teste de patch contra o submódulo pinado é executado quando ele existe no
checkout (por exemplo, no GitHub Actions com `submodules: recursive`).

Verifique no GitHub Actions se o commit de correção eliminou a falha
`prepare_android_target.py: data path...`; a execução anterior da main estava
falhando. Isto não prova build ARM64.

## Instrução de aplicação

Aplique o ZIP 08 sobre `~/Fteste` e execute a suíte. Não comite `build/` nem
`default.xex`/`data/` ou qualquer conteúdo comercial.
