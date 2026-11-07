import { accountOutcomeSchema, checklistSchema } from "@shadowclone/cloud/browser";
import { request } from "./api";
import { botButton, botField } from "./botControls";
import { renderChecklist } from "./botChecklist";
import { create } from "./dom";

export function showAccountSetup(options: {
  readonly container: HTMLElement;
  readonly status: HTMLElement;
  readonly repository: string;
  readonly onApp: () => void;
}): void {
  const { container, status } = options;
  const repository = botField({
    label: "Repository (owner/repository)",
    value: options.repository,
  });
  const bot = botField({ label: "Bot's GitHub login, such as octo-shadow", value: "" });
  const agentLabel = create({ tag: "label", className: "field" });
  const agent = create({ tag: "select" });
  const agents = [
    { value: "claude/api-key", text: "Claude, with your Claude subscription token" },
    { value: "codex/api-key", text: "Codex, with an OpenAI API key" },
    { value: "codex/plan", text: "Codex, with your ChatGPT plan login (experimental)" },
  ];

  for (const choice of agents) {
    const option = create({ tag: "option", text: choice.text });

    option.value = choice.value;
    agent.append(option);
  }

  agentLabel.append(create({ tag: "span", text: "Agent" }), agent);
  const result = create({ tag: "div" });
  const app = create({
    tag: "button",
    className: "quiet-button",
    text: "Use a GitHub App instead",
  });

  app.type = "button";
  app.addEventListener("click", options.onApp);

  const submit = async (approveSkills: boolean) => {
    const outcome = await request({
      path: "/api/bot/account",
      body: {
        repository: repository.input.value.trim(),
        botLogin: bot.input.value.trim(),
        approveSkills,
        engine: agent.value.startsWith("codex") ? "codex" : "claude",
        codexAuth: agent.value.endsWith("plan") ? "plan" : "api-key",
      },
      schema: accountOutcomeSchema,
    });

    result.replaceChildren();

    if (outcome.kind === "needs-account") {
      const signup = create({ tag: "a", text: `Create the GitHub account ${outcome.login}` });

      signup.href = outcome.signupUrl;
      signup.target = "_blank";
      signup.rel = "noreferrer";
      result.append(signup);
      status.textContent =
        "Create the account in a private window or with the account switcher, then continue.";
      return;
    }

    if (outcome.kind === "needs-approval") {
      result.append(
        create({
          tag: "p",
          text: `Setup pushes these files to your private repository ${outcome.skillsRepository}:`,
        }),
        create({
          tag: "pre",
          text: outcome.files.map((file) => `${file.path} (${file.bytes} bytes)`).join("\n"),
        }),
        botButton({
          text: "Push the skills and set up the repository",
          status,
          action: () => submit(true),
        }),
      );
      status.textContent = "Review the files before you continue.";
      return;
    }

    result.append(...outcome.warnings.map((warning) => create({ tag: "p", text: warning })));
    renderChecklist({ container: result, checklist: checklistSchema.parse(outcome.checklist) });
    status.textContent =
      "Add the tokens on GitHub, then merge the setup pull request. Run shadowclone bot status to check progress.";
  };

  container.append(
    create({
      tag: "p",
      text:
        "Your bot is a GitHub account that you create and name. It gets its own profile and " +
        "contributions. You add its token and your agent's token on GitHub; Shadowclone never sees them.",
    }),
    repository.label,
    bot.label,
    agentLabel,
    botButton({ text: "Continue", status, action: () => submit(false) }),
    result,
    app,
  );
}
