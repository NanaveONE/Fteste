# Correção 35 — frame limiter Android

Copie `scripts/` e `tests/` para a raiz do repositório Fteste.

No `scripts/build_android_native.sh`, imediatamente após a chamada ao script `fix_fable2_gpu_progress_34.py`, adicione:

```bash
python3 "$root/scripts/fix_fable2_frame_limiter_35.py" --worktree "$work"
```

Execute os testes, commit e novo workflow. A mudança afeta somente a pausa do host; o tempo de espera em Android pode ser diferente do Windows.
