#!/usr/bin/env python3
"""Integrate the existing Fable II Android installer with a direct ISO picker.

Preserves the folder importer and Fable-2-Recomp compatibility gate. Does not
replace any proprietary assets. Fail-closed, idempotent, and transactional.
"""
from __future__ import annotations

import argparse
from pathlib import Path

LAUNCHER = 'port/android/java/com/nanaveone/fable2/Fable2LauncherActivity.java'
EXTRACTOR = 'port/android/java/com/nanaveone/fable2/Fable2IsoExtractor.java'
INSTALLER = 'port/android/java/com/nanaveone/fable2/Fable2IsoInstaller.java'

REPLACEMENTS = [
    (
        '    private static final int PICK_GAME_FOLDER = 42;\n',
        '    private static final int PICK_GAME_FOLDER = 42;\n'
        '    private static final int PICK_GAME_ISO = 43;\n',
    ),
    (
        '    private Button importButton;\n',
        '    private Button importButton;\n'
        '    private Button isoButton;\n',
    ),
    (
        '        layout.addView(importButton);\n',
        '        layout.addView(importButton);\n'
        '        isoButton = new Button(this);\n'
        '        isoButton.setText("Selecionar ISO original do Fable II");\n'
        '        isoButton.setOnClickListener(v -> pickIso());\n'
        '        layout.addView(isoButton);\n',
    ),
    (
        '                : "Selecione uma pasta extraída com default.xex e data/.\\nNão selecione uma ISO.\\n"\n'
        '                + "Os dados serão copiados para o armazenamento privado do aplicativo.");',
        '                : "Selecione a ISO original do Fable II ou uma pasta extraída com default.xex e data/.\\n"\n'
        '                + "Os dados serão copiados para o armazenamento do aplicativo.");',
    ),
    (
        '    private void pickFolder() {\n',
        '    private void pickIso() {\n'
        '        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT);\n'
        '        picker.addCategory(Intent.CATEGORY_OPENABLE);\n'
        '        picker.setType("*/*"); // .iso MIME varies among Android file providers.\n'
        '        picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);\n'
        '        startActivityForResult(picker, PICK_GAME_ISO);\n'
        '    }\n\n'
        '    private void pickFolder() {\n',
    ),
    (
        '        super.onActivityResult(requestCode, resultCode, data);\n'
        '        if (requestCode != PICK_GAME_FOLDER || resultCode != RESULT_OK || data == null\n',
        '        super.onActivityResult(requestCode, resultCode, data);\n'
        '        if (requestCode == PICK_GAME_ISO) {\n'
        '            if (resultCode == RESULT_OK && data != null && data.getData() != null)\n'
        '                importIso(data.getData());\n'
        '            return;\n'
        '        }\n'
        '        if (requestCode != PICK_GAME_FOLDER || resultCode != RESULT_OK || data == null\n',
    ),
    (
        '        importButton.setEnabled(false);\n'
        '        playButton.setEnabled(false);\n',
        '        importButton.setEnabled(false);\n'
        '        isoButton.setEnabled(false);\n'
        '        playButton.setEnabled(false);\n',
    ),
    (
        '                    importButton.setEnabled(true);\n'
        '                    progress.setVisibility(android.view.View.GONE);\n',
        '                    importButton.setEnabled(true);\n'
        '                    isoButton.setEnabled(true);\n'
        '                    progress.setVisibility(android.view.View.GONE);\n',
    ),
    (
        '    private static final class GameDocument {\n',
        '    private void importIso(Uri iso) {\n'
        '        importButton.setEnabled(false);\n'
        '        isoButton.setEnabled(false);\n'
        '        playButton.setEnabled(false);\n'
        '        progress.setVisibility(android.view.View.VISIBLE);\n'
        '        status.setText("Lendo ISO original do Fable II...");\n'
        '        worker.execute(() -> {\n'
        '            try {\n'
        '                Fable2IsoInstaller.install(getContentResolver(), iso, gameRoot,\n'
        '                        message -> runOnUiThread(() -> status.setText(message)));\n'
        '                runOnUiThread(() -> {\n'
        '                    isoButton.setEnabled(true);\n'
        '                    importButton.setEnabled(true);\n'
        '                    progress.setVisibility(android.view.View.GONE);\n'
        '                    updateReadyState();\n'
        '                });\n'
        '            } catch (Exception error) {\n'
        '                runOnUiThread(() -> {\n'
        '                    isoButton.setEnabled(true);\n'
        '                    importButton.setEnabled(true);\n'
        '                    progress.setVisibility(android.view.View.GONE);\n'
        '                    updateReadyState();\n'
        '                    new AlertDialog.Builder(this).setTitle("Falha ao extrair ISO")\n'
        '                            .setMessage(error.getMessage())\n'
        '                            .setPositiveButton("OK", null).show();\n'
        '                });\n'
        '            }\n'
        '        });\n'
        '    }\n\n'
        '    private static final class GameDocument {\n',
    ),
]


def patch(root: Path, check: bool = False) -> str:
    root = root.resolve()
    for dependency in (EXTRACTOR, INSTALLER):
        if not (root / dependency).is_file():
            raise ValueError('Arquivo da integração ausente: ' + dependency)
    target = root / LAUNCHER
    original = target.read_text(encoding='utf-8')
    content = original
    for before, after in REPLACEMENTS:
        # One pattern occurs twice: enable buttons in both success and failure.
        expected = 2 if before.startswith('                    importButton.setEnabled(true);') else 1
        expected_after = (2 if before.startswith('        importButton.setEnabled(false);')
                          else expected)
        if content.count(after) == expected_after:
            continue
        if content.count(before) != expected or content.count(after):
            raise ValueError('Arquivo launcher diferente do esperado; correção não aplicada: ' + repr(before[:75]))
        content = content.replace(before, after)
    if check and content != original:
        raise ValueError('Integração ISO ainda não aplicada')
    if not check and content != original:
        target.write_text(content, encoding='utf-8')
        return 'updated'
    return 'verified'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(patch(args.root, args.check))
    except (OSError, ValueError) as error:
        parser.exit(2, 'BLOCKED: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
