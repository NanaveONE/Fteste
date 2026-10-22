# Fable II Android: integração 02

Data: 2026-10-22

**Novo código entregue**

- Activity Android para escolher uma pasta **extraída** pelo seletor nativo de
  documentos. Importa `default.xex` e `data/` em streaming (sem carregar os
  arquivos inteiros na memória), trata nomes inseguros, limita profundidade e
  quantidade de documentos e grava um marcador apenas após cópia completa.
- O menu Iniciar verifica dados essenciais e bibliotecas nativas antes de
  abrir a Activity SDL do Fable II.
- AndroidManifest usa a Activity do Fable II; não é uma adaptação de nomenclatura
  do Burnout.
- CMake overlay coloca `fable_2` como biblioteca compartilhada para Android e
  seleciona o backend chamado `plume` como alvo **a ser implementado para Fable**.
- Script para empacotar e assinar APK ARM64 **apenas se** existirem as
  bibliotecas reais de jogo, runtime ReXGlue e plugin Plume. Não gera APK falso.
- Documento de arquitetura sobre compatibilidade da renderização.
- Sete testes unitários e validação de sintaxe do empacotador.

**Bloqueadores**

Ainda é necessário construir o SDK Android compatível, gerar o C++ específico
para o jogo, integrar runtime e implementar GPU Vulkan para o conjunto de
comandos e shaders de Fable II. As bibliotecas nativas não foram produzidas;
**nenhum APK funcional foi criado**. A Activity/empacotador não são prova de
jogabilidade. O código Java e a compilação Android ainda precisam ser testados
com Android SDK/NDK em ambiente com ferramentas Android instaladas.

**Termux para publicar**

Baixe e extraia este ZIP na pasta `~/Fteste` e rode:

```bash
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-Fable2-Android-integracao-02.zip -d .
python -m unittest discover -s tests -v
bash -n scripts/package_android_apk.sh
git add .github .gitignore CHANGELOG-02.md docs port scripts tests
git commit -m "Adicionar importador Android e empacotador nativo Fable II"
git push
```

`git submodule update --init --recursive` ainda é necessário para executar
`scripts/verify_port_layout.py`. Não envie ISOs, `default.xex` ou `data/`.
