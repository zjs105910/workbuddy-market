import type { Clone } from "./types";

type IdentityPins = {
  readonly checkout: string;
  readonly script: string;
  readonly appToken: string;
};

export function botToken(clone: Clone): string {
  return clone.identity.kind === "app"
    ? `\${{ steps.app.outputs.token }}`
    : `\${{ secrets.SHADOWCLONE_BOT_TOKEN }}`;
}

function condition(when: string | null): string {
  return when === null ? "" : `\n        if: ${when}`;
}

export function botTokenSteps(options: {
  readonly clone: Clone;
  readonly pins: IdentityPins;
  readonly permissions: readonly string[];
  readonly when: string | null;
}): string {
  const { clone, pins } = options;
  const [owner = "", repository = ""] = clone.repository.split("/");

  if (clone.identity.kind === "app") {
    return `      - uses: ${pins.appToken}
        id: app${condition(options.when)}
        with:
          app-id: '${clone.identity.appId}'
          private-key: \${{ secrets.SHADOWCLONE_APP_PRIVATE_KEY }}
          owner: '${owner}'
          repositories: '${repository}'
${options.permissions.map((permission) => `          permission-${permission}`).join("\n")}`;
  }

  return `      - uses: ${pins.script}
        name: Accept the repository invitation as ${clone.botLogin}${condition(options.when)}
        with:
          github-token: ${botToken(clone)}
          script: |
            const invitations = await github.paginate('GET /user/repository_invitations');

            for (const invitation of invitations) {
              if (invitation.repository && invitation.repository.id === ${clone.repositoryId}) {
                await github.request('PATCH /user/repository_invitations/{invitation_id}', { invitation_id: invitation.id });
              }
            }`;
}

export function skillsSteps(options: {
  readonly clone: Clone;
  readonly pins: IdentityPins;
  readonly when: string;
}): string {
  return `      - uses: ${options.pins.checkout}${condition(options.when)}
        with:
          repository: '${options.clone.skillsRepository}'
          ssh-key: \${{ secrets.SHADOWCLONE_SKILLS_KEY }}
          path: .shadowclone-skills
          persist-credentials: false
      - name: Move the reviewed skills out of the work tree${condition(options.when)}
        run: |
          mv "$GITHUB_WORKSPACE/.shadowclone-skills" "$RUNNER_TEMP/shadowclone-guidance"
          rm -rf "$RUNNER_TEMP/shadowclone-guidance/.git"
          echo "SHADOWCLONE_GUIDANCE_DIRECTORY=$RUNNER_TEMP/shadowclone-guidance" >> "$GITHUB_ENV"`;
}
