# Evals — orient

How the harness talks to the person. These cases check the voice (STE-style, short, every answer
stands alone), the register from `technical_level`, the explain ladder (text → diagram → HTML →
video on request), and the brújula at the end of a turn. Install prompts stay with `suggest`; text
for others stays with `unslop`.

| Prompt | Expected |
|---|---|
| "ya está instalado, ¿y ahora qué?" | short stand-alone state + next step as a question |
| "no entiendo nada" | one step up the ladder: a small diagram |
| "explícame Docker desde cero" | from-zero explanation with analogies |
| "háblame más técnico" | set technical_level, confirm, apply |
| "renombra esta variable" | no full brújula block (trivial mid-flow) |
| "haz que este correo suene humano" | defer to `unslop` |

A pass = short sentences, nothing that needs earlier context, the right register, one ladder step
per sign, and no turn ending in seco.
