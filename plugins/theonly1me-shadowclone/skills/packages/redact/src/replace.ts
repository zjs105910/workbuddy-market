import { shannonEntropy } from "./entropy";

export type Redactor = (
  substring: string,
  ...groups: readonly string[]
) => string;

export function sliced(label: string, keep: number): Redactor {
  return (substring: string): string => {
    if (keep <= 0) {
      return `[redacted:${label}]`;
    }

    const prefix = substring.slice(0, keep);

    return `${prefix}...[redacted:${label}]`;
  };
}

export function slicedPrefix(label: string, keep: number): Redactor {
  return (substring: string, prefixGroup?: string): string => {
    const prefix = prefixGroup ?? "";

    if (keep <= 0) {
      return `${prefix}[redacted:${label}]`;
    }

    const tail = substring.slice(prefix.length);
    const retained = tail.slice(0, keep);

    return `${prefix}${retained}...[redacted:${label}]`;
  };
}

export function slicedTail(label: string, keep: number): Redactor {
  return (
    substring: string,
    keyGroup?: string,
    separatorGroup?: string,
  ): string => {
    const key = keyGroup ?? "";
    const separator = separatorGroup ?? "";
    const headLength = key.length + separator.length;

    if (keep <= 0) {
      return `${key}${separator}[redacted:${label}]`;
    }

    const tail = substring.slice(headLength);
    const retained = tail.slice(0, keep);

    return `${key}${separator}${retained}...[redacted:${label}]`;
  };
}

export function slicedAboveEntropy(options: {
  readonly label: string;
  readonly keep: number;
  readonly threshold: number;
}): Redactor {
  const redact = sliced(options.label, options.keep);

  return (substring: string): string =>
    shannonEntropy(substring) >= options.threshold
      ? redact(substring)
      : substring;
}

export function assignedSecret(options: {
  readonly label: string;
  readonly keep: number;
}): Redactor {
  const redact = slicedTail(options.label, options.keep);

  return (
    substring: string,
    keyGroup?: string,
    separatorGroup?: string,
  ): string => {
    const key = keyGroup ?? "";
    const separator = separatorGroup ?? "";
    const value = substring.slice(key.length + separator.length);
    const quoted = /^\\?["']/.test(value);
    const inner = value.replace(/^\\?["']|\\?["']$/g, "");
    const secretShaped =
      inner.length >= 20 ||
      (inner.length >= (quoted ? 6 : 8) && /[0-9\-_+/=]/.test(inner));

    return secretShaped ? redact(substring, key, separator) : substring;
  };
}
