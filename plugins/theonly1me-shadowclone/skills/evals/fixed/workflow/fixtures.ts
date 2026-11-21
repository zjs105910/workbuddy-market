export const corrections = [
  {
    sessionId: "synthetic-version-control",
    messages: [
      { role: "user" as const, text: "Please tidy the sample changelog." },
      { role: "assistant" as const, text: "I updated the changelog and created a commit." },
      { role: "user" as const, text: "Across all my repositories, never create a Git commit or change branches unless my current request explicitly authorizes that action. Asking for a code change alone does not authorize a commit. Treat this as my standing preference." },
    ],
  },
  {
    sessionId: "synthetic-answer-length",
    messages: [
      { role: "user" as const, text: "Explain what the sample configuration controls." },
      { role: "assistant" as const, text: "The sample configuration controls its sample options. Here is an extended explanation of each option and several unrelated implementation details." },
      { role: "user" as const, text: "For all engineering work, keep your final answer at most 80 words unless my current request asks for a different length. This is my standing preference across projects, not just for this explanation." },
    ],
  },
];
