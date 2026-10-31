<div align="center">

# Hoja de ruta de Distilly

### De Colleague Skill (`colleague.skill`) a Distilly — Destila personas en Skills reutilizables para agentes de IA y bots compatibles

<br>

Empezamos con una idea sencilla: **cuando un colega se va, su conocimiento se va con él. ¿Podemos conservarlo?**

En dos semanas, 13.000+ personas nos dieron la respuesta.

Pero la comunidad nos demostró que esto va mucho más allá de los colegas —
destilaron profesores, exparejas, a sí mismos, incluso personajes de ficción.

**Así que decidimos convertir Colleague Skill (`colleague.skill`) en Distilly.**

Cualquier persona puede convertirse en un `.skill` reutilizable para agentes de IA y bots compatibles.

<br>

*Última actualización: 2026-08-23*

[**Inglés**](../../ROADMAP.md) · [**Chino**](ROADMAP_ZH.md) · [**Alemán**](ROADMAP_DE.md) · [**Japonés**](ROADMAP_JA.md) · [**Ruso**](ROADMAP_RU.md) · [**Portugués**](ROADMAP_PT.md) · [**Coreano**](ROADMAP_KO.md)

</div>

---

## Lo que ya está hecho (v1.0)

| Funcionalidad | Estado |
|---------------|:------:|
| Flujo completo de creación con selección de familia (`colleague`, `relationship`, `celebrity`) mediante `/distilly` | Hecho |
| Recopilación automática de Lark (mensajes + docs + hojas de cálculo) | Hecho |
| Recopilación automática de DingTalk | Hecho |
| Recopilación automática de Slack | Hecho |
| Historial de chat de WeChat (exportación SQLite) | Hecho |
| Importación de Email / PDF / imagen / Markdown | Hecho |
| Arquitectura de doble modelo: Work Skill + Persona | Hecho |
| Correcciones en conversación y evolución incremental | Hecho |
| Control de versiones y reversión | Hecho |
| [Galería comunitaria](https://titanwings.github.io/colleague-skill-site/) con más de 99 skills | Hecho |

---

## Fases de la hoja de ruta

### Fase 1 — Construcción de la comunidad

> 13k estrellas no deberían ser solo un número. Queremos que todos sean parte de esto.

**Lo que verás:**

- **GitHub Discussions** — basta de conversar en Issues, tendremos espacios de discusión dedicados
- **`CONTRIBUTING.md`** — guía de contribución clara, amigable para principiantes
- **Etiquetas `good-first-issue`** — tareas de inicio para nuevos colaboradores
- **Lanzamiento oficial v1.0.0** — primera Release versionada, se acabó el "solo haz pull de main"
- **Tablero público de hoja de ruta** — lo estás leyendo ahora, pero también tendremos una versión en vivo con GitHub Projects

**Puedes ayudar:** traducir documentación, enviar tu .skill, probar en Windows, ayudar a gestionar Issues

---

### Fase 2 — Distilly: Más allá de los colegas

> Colleague Skill (`colleague.skill`) fue el comienzo. Distilly es el futuro.

**Ya disponible:**

- **`/distilly` como entrada universal canónica** — elige `colleague`, `relationship` o `celebrity` y destila a cualquier persona, incluso a ti mismo
- **Skills generados portátiles** — nombres canónicos con el formato `{character}-{slug}` para los hosts de Agent compatibles

**Aún pendiente:**

- **Mejora de categorías en la Galería** — Colega / Celebridad / Relación / Personaje / Yo / Meta-Skill, navega por tipo
- **Más fuentes de datos**
  - Soporte para WeCom (WeChat Work)
  - Lectura automática de iMessage
- **Compatibilidad de plataformas** — corrección de compatibilidad con Windows

**Puedes ayudar:** enviar solicitudes de tipos de persona, crear nuevos recopiladores de fuentes de datos, participar en discusiones de diseño de la Galería

---

### Fase 3 — Ecosistema de Skills

> Cuando una persona se convierte en un skill, ¿puede un grupo de personas convertirse en un equipo?

**Estamos explorando:**

- **Colaboración multi-skill** — `/meeting @zhangsan @lisi @wangwu`, tres personas discuten un tema juntas
- **Grafo de relaciones** — define las dinámicas entre personas: quién colabora con quién, dónde está la tensión
- **Instalación con un clic** — instala skills de la comunidad como plugins
- **Evolución activa** — los skills absorben periódicamente nuevas fuentes de datos, manteniéndose actualizados

**Puedes ayudar:** proponer tus escenarios ideales de composición de skills, participar en discusiones sobre mecanismos de distribución

---

### Fase 4 — Multimodal: Darles vida

> Ahora mismo, los .skills solo pueden hablar. Queremos que envíen fotos, stickers, hablen con su voz y, eventualmente, generen videos.

**Paso 1: Expresión visual**
- Envío automático de stickers y memes al estilo de la persona en la conversación
- Generación de "fotos de vida" en su estilo — ¿qué publicarían hoy?
- Cada skill tiene su propio paquete de stickers y recursos de imagen

**Paso 2: Voz**
- Hablar con su voz — clonada a partir de grabaciones de reuniones, mensajes de voz
- Enviar respuestas de voz directamente en el chat

**Paso 3: Video (exploratorio)**
- Generación de videos cortos "un día en su vida"
- Humano digital / avatar animado

**Puedes ayudar:** compartir ideas de casos de uso multimodal, contribuir recursos de stickers, probar la clonación de voz

---

## Participa

| Cómo | Dónde |
|------|-------|
| Envía tu .skill | [PR a la Galería](https://titanwings.github.io/colleague-skill-site/) |
| Discute y propone | [GitHub Discussions](https://github.com/titanwings/distilly/discussions) (próximamente) |
| Chatea en tiempo real | [Discord](https://discord.gg/NVX66RxWZv) |
| Reporta errores | [Issue](https://github.com/titanwings/distilly/issues/new) |
| Contribuye código | Busca etiquetas `good-first-issue`, o simplemente abre un PR |

**Necesitamos especialmente:**
- Usuarios de Windows — ayúdanos a probar y corregir problemas de compatibilidad
- Hablantes de varios idiomas — ayuda a traducir la documentación
- Desarrolladores de fuentes de datos — crea nuevos recopiladores (WeCom, Notion, Google Docs...)
- Diseñadores — la Galería y el sitio web necesitan tu ojo experto

---

<div align="center">

**Esta hoja de ruta pertenece a la comunidad. Las prioridades cambian según tu feedback.**

¿Tienes ideas? Ven a [Discord](https://discord.gg/NVX66RxWZv) o inicia una Discussion.

Cada `.skill` es una relación que continúa.

</div>
