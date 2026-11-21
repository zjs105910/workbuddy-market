export type InitializeConsent = {
  readonly learn: boolean;
  readonly skills: boolean;
  readonly background: boolean;
};

export type PersonalInitOptions =
  | { readonly kind: "interactive"; readonly advanced: boolean }
  | { readonly kind: "status"; readonly json: boolean }
  | { readonly kind: "consent"; readonly consent: InitializeConsent };

function decision(options: {
  readonly arguments: ReadonlySet<string>;
  readonly positive: string;
  readonly negative: string;
}): boolean | null {
  const positive = options.arguments.has(options.positive);
  const negative = options.arguments.has(options.negative);

  if (positive && negative) {
    throw new Error(`Choose either ${options.positive} or ${options.negative}`);
  }

  if (!positive && !negative) return null;

  return positive;
}

export function parsePersonalInit(
  arguments_: readonly string[],
): PersonalInitOptions | null {
  const allowed = new Set([
    "--advanced",
    "--status",
    "--json",
    "--learn",
    "--no-learn",
    "--skill-maintenance",
    "--no-skill-maintenance",
    "--background-learning",
    "--no-background-learning",
  ]);

  if (arguments_.some((argument) => !allowed.has(argument))) return null;

  const argumentsSet = new Set(arguments_);
  const status = argumentsSet.has("--status");

  if (status || argumentsSet.has("--json")) {
    if (
      !status ||
      [...argumentsSet].some(
        (argument) => argument !== "--status" && argument !== "--json",
      )
    ) {
      return null;
    }

    return { kind: "status", json: argumentsSet.has("--json") };
  }

  const learn = decision({
    arguments: argumentsSet,
    positive: "--learn",
    negative: "--no-learn",
  });
  const skills = decision({
    arguments: argumentsSet,
    positive: "--skill-maintenance",
    negative: "--no-skill-maintenance",
  });
  const background = decision({
    arguments: argumentsSet,
    positive: "--background-learning",
    negative: "--no-background-learning",
  });
  const decisions = [learn, skills, background];

  if (decisions.some((value) => value !== null)) {
    if (decisions.some((value) => value === null)) {
      throw new Error(
        "Explicit setup requires learning, skill maintenance, and background learning decisions",
      );
    }

    if (learn === false && background) {
      throw new Error("Background learning requires session learning");
    }

    if (learn === null || skills === null || background === null) return null;

    return { kind: "consent", consent: { learn, skills, background } };
  }

  return { kind: "interactive", advanced: argumentsSet.has("--advanced") };
}
