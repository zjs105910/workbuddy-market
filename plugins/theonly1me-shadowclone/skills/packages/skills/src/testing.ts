export function fixtureSkill(name = "typed-changes"): string {
  return `---\nname: ${name}\ndescription: Make typed code changes when implementing a requested feature.\ndisable-model-invocation: true\nmetadata:\n  owner: local\n---\n\n# Typed changes\n\nPreserve the requested behavior.\n`;
}

export { sampleSkillText } from "./skills/qualityFixtures";
