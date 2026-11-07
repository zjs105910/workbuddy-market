export type NativeDiagnostic = {
  readonly stage:
    | "setup"
    | "mount-create"
    | "mount-attach"
    | "execution"
    | "verification"
    | "mount-detach"
    | "cleanup";
  readonly confirmedInfrastructure: boolean;
  readonly message: string;
  readonly details: string;
};

export class NativeInfrastructureError extends Error {
  readonly diagnostic: NativeDiagnostic;
  constructor(diagnostic: NativeDiagnostic) {
    super(diagnostic.message);
    this.diagnostic = diagnostic;
  }
}

export function nativeFailure(options: {
  stage: NativeDiagnostic["stage"];
  error: unknown;
}): NativeDiagnostic {
  return options.error instanceof NativeInfrastructureError
    ? options.error.diagnostic
    : {
        stage: options.stage,
        confirmedInfrastructure: false,
        message: "Unclassified native stage failure.",
        details: options.error instanceof Error ? options.error.message : String(options.error),
      };
}
