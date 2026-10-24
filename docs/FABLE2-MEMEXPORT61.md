# MemExport61 — barreira cooperativa e ponto de integração Plume

O novo `fable_memexport_world61.h` fornece uma barreira **efetiva apenas sobre
participantes instrumentados**. A chamada de exclusão aguarda a saída dos
participantes ativos, impede novas entradas até a conclusão da transação e
rejeita timeouts. Um escritor ativo não é considerado suspenso apenas porque
um XThread recebeu `Suspend()`.

O `CoverageProof::EveryMemoryWriterIsInstrumented()` deve ser implementado no
SDK **exato** do ReXGlue e comprovar que todas as threads guest, executores
recompilados, escritores do kernel, produtores assíncronos e caminhos de
mapeamento/invalidação são cobertos, inclusive os que surgem depois do pedido
de exclusão. Sem essa comprovação, `CooperativeWorld::IsVerifiedFor()` falha.

A camada `apply_fable_plume61.py` conecta o header de memória física real
MemExport60 ao Plume, expõe `InstallCertifiedRexWorld61` e mantém o host
válido até a destruição de `PlumeDrawContext`. **Não há chamada automática**:
o runtime stock ainda não possui o `CoverageProof` necessário. Essa condição
é deliberada para não gravar memória guest concorrente com CPU/JIT.

Os testes usam a API mock do ReXGlue para exercitar duas threads reais do host,
entrada bloqueada por exclusão, timeout, falta de cobertura, fence e escrita
atômica no journal. Não são provas de execução gráfica real.

Limitações adicionais: os cinco shaders seguem em cache experimental, falta
validar predicação, formatos Xenos não-RGBA32, ordem das escritas, coerência
com caches GPU/EDRAM e a operação completa em um dispositivo Android.

**Resultado:** preparação de integração, não avanço automático para 588/588,
nem APK jogável. Não publicar game binaries nem shaders proprietários.
