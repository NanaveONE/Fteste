# Memgate73: recuperar cache histórico de 583 após regressão para 572

A execução real #40127885383 gerou um cache de **572** entradas, comparado aos
**583** previamente verificados; a diferença de 11 representa falhas adicionais
de tradução atuais e **não** conclui os cinco shaders MemExport.

O reconciliador existente agora admite uma restauração para diagnóstico,
mas **somente** no caso observado de 572 entradas:

- Confere SHA-256 de ambos os bancos SBK e de **todos os 588** contêineres
  extraídos, exigindo os mesmos nomes e o formato esperado.
- Identifica cada entrada com a tupla `(hash XenosRecomp, estágio VS/PS,
  SHA-256 do contêiner original)`; as 572 entradas **precisam ser subconjunto
  exato** das 583 entradas do cache histórico. Qualquer entrada nova é rejeitada.
- O arquivo de diagnóstico43 precisa possuir contagem original **583/588**, a
  lista correta dos cinco shaders MemExport e um cache histórico válido
  zstd/SMOL-V verificado sobre o mesmo conjunto de 588 arquivos de entrada.
- A nova compilação gerada é preservada em
  `build/fable2-shaders/shader_cache-generated73.cpp`; o `shader_cache.cpp`
  passa a conter os 583 históricos somente após essas verificações.
- `cache-reconcile.json` registra as 11 entradas recuperadas, sem expor hashes
  de shaders privados ou fragmentos de fontes ao log público.

O fluxo 583 gerado continua sujeito à verificação Probe56 original, e o caso
588 mantém sua checagem estrita de cinco shaders VS extras. Todas as demais
contagens e divergências de identidade continuam **bloqueadas**.

**Não é um fix do tradutor XenosRecomp.** É um *fallback* restrito que permite
prosseguir ao teste de compilação ARM64 da GPU com um cache privado cuja
integridade é revalidada. A equivalência dos shaders atuais aos antigos, os
commits MemExport e a sincronização completa CPU/GPU **não estão provados**.
