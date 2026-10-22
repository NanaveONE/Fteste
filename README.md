# Fable II Android — integracao inicial usando Xerenge

**Estado:** organizacao e preparacao de fontes; **NAO e um APK** e **NAO executa Fable II ainda**.

## Por que estas bases
- Xerenge (shipa-2/Xerenge): usa ReXGlue, possui AndroidManifest, Java/JNI,
  SDL e build de bibliotecas nativas para Android. Seu renderizador Plume
  ainda possui dependencias especificas de Burnout Revenge.
- Fable-2-Recomp (himdo/Fable-2-Recomp): possui manifest de recompilacao,
  hooks e runtime especificos para Fable II GOTY. O Vulkan do projeto
  ainda nao esta pronto para gameplay completo em Android.

## No Termux
```sh
pkg install git bash -y
unzip Fable2-Android-Xerenge-base.zip
cd fable2-xerenge-base
bash scripts/prepare.sh
bash scripts/device-info.sh
```
A primeira clonagem precisa de internet. `prepare.sh` nao altera os repos
clonados quando ja existem; guarda copias de referencia em `bridge/`.
Nao envie ISOs, `default.xex` nem `data/` para GitHub.

## Arquitetura alvo
- Android 12 / API 31
- Snapdragon 650 / ARMv8-A / arm64-v8a (verificar se a ROM expoe ABI de 64 bits)
- Adreno 510: dependencias Vulkan devem ser avaliadas no driver real

## Bloqueadores para gameplay
1. Substituir `burnout` e seus hooks por `fable_2` nos alvos CMake de Android;
   nao copiar ou executar o codigo do Burnout como se fosse Fable.
2. Reconciliar versoes / APIs ReXGlue entre os dois repositorios.
3. Fazer o renderer Plume receber draw calls do Fable II, incluindo
   shaders, formatos, EDRAM, caches e outros recursos dependentes do jogo.
4. Gerar C++ a partir do `default.xex` de uma copia propria compativel e compilar
   a biblioteca ARM64; preparar os arquivos de dados localmente, fora do repo.
5. Integrar atividade SDL, pasta de dados, lifecycle, controles, audio e saves.
6. Verificar se o driver suporta os recursos realmente usados pelo renderer.
   O manifest Xerenge atual exige Vulkan 1.1, e remover essa declaracao nao
   acrescenta o suporte ausente ao driver.
7. Compilar, diagnosticar, testar jogo real e corrigir crashes / desempenho.

## Licencas
Xerenge: GPL-3.0-or-later, segundo seu README. Fable-2-Recomp: MIT.
Se combinar arquivos derivados de Xerenge num unico projeto distribuido,
observar as exigencias da GPL e as licencas dos componentes de terceiros.
Este pacote nao inclui os fontes dos dois projetos nem recursos comerciais.

## Fontes
https://github.com/shipa-2/Xerenge
https://github.com/himdo/Fable-2-Recomp
