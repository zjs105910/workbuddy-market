---
id: refactor-boundaries
title: Refactor when boundaries improve
axis: refactor-tolerance
category: architecture
section: engineering
applies-when:
  - changing code near a weak module boundary
---
## Refactor when boundaries improve

Reshape nearby code when the change creates a smaller interface, removes duplicated policy, or puts ownership in one module. Keep the refactor tied to the behavior being changed.
