---
name: testing-first
description: Build observable behavior through a red-green cycle at a stable public seam. Use when the user asks for test-first work, TDD, or a regression test before implementation.
metadata:
  shadowclone-category: testing
  shadowclone-section: engineering
  shadowclone-applies-when: changing observable behavior with a test-first workflow
  shadowclone-axis: testing-approach
---
# Test First Through a Public Seam

## Use when

Following a test-first workflow for behavior that a caller can observe. Settle the intended interface before choosing test structure.

## Process

1. State one behavior as concrete input and observable output.
2. Write a test through the narrowest stable caller interface, using an expected result obtained independently of the implementation.
3. Run it and confirm it fails because the behavior is missing or wrong.
4. Implement the smallest complete slice that makes it pass, including every required layer.
5. Repeat for the next behavior once the current test is green.
6. Run affected checks and remove code justified only by an unwritten future test.

## Guardrails

Keep each cycle to one behavioral claim; several assertions can describe that outcome. Prefer real collaborators inside the module and replace dependencies only at established external boundaries.

Do not weaken an assertion to make a failing implementation pass. If harmless refactoring breaks a test without changing behavior, move it to a more stable interface. Avoid recreating the production calculation to derive expected values.

## Completion

Requested behaviors have tests observed failing first, implementation passes through public interfaces, and affected checks pass.

Report each test name with the assertion that failed first and its passing run, then the affected checks with their result. Keep the reply to these facts. When a pull request exists, put full command output in its verification section instead of the reply.
