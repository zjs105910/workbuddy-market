# Changelog

## [0.0.26](https://github.com/theonly1me/shadowclone/compare/v0.0.25...v0.0.26) (2026-10-09)


### Features

* always apply plain english and split the code into workspace packages ([#185](https://github.com/theonly1me/shadowclone/issues/185)) ([95ca1ef](https://github.com/theonly1me/shadowclone/commit/95ca1ef8bc472d566fa743eeee145664e0b8a9fd))
* **cloud:** run for up to three hours, save unfinished work, and work with codex ([#182](https://github.com/theonly1me/shadowclone/issues/182)) ([e6a7680](https://github.com/theonly1me/shadowclone/commit/e6a7680a3b1dd86e4b05210fff8eaec595c5677e))
* **cloud:** set up a named bot account with tokens entered on github ([#181](https://github.com/theonly1me/shadowclone/issues/181)) ([5fe1c05](https://github.com/theonly1me/shadowclone/commit/5fe1c05d48311fd7fb9c75f974bf6c343345a9a5))
* let the agent run the whole setup from one pasted line ([#186](https://github.com/theonly1me/shadowclone/issues/186)) ([2a022f5](https://github.com/theonly1me/shadowclone/commit/2a022f5440a2418a8c4c89cb74ad3096adb519d2))
* **review:** review the current branch without a pull request ([#178](https://github.com/theonly1me/shadowclone/issues/178)) ([0e0f23b](https://github.com/theonly1me/shadowclone/commit/0e0f23b68fa453a5ddd8b421696bb455daf8d2a6))


### Fixes

* **review:** compare dependencies and diagnostics with the merge base ([#179](https://github.com/theonly1me/shadowclone/issues/179)) ([037e233](https://github.com/theonly1me/shadowclone/commit/037e233b2c2d08336b7fccffed7149ff2390dfe1))

## [0.0.25](https://github.com/theonly1me/shadowclone/compare/v0.0.24...v0.0.25) (2026-10-08)


### Features

* **review:** run at claude code's default effort unless --effort is set ([#175](https://github.com/theonly1me/shadowclone/issues/175)) ([7a44a38](https://github.com/theonly1me/shadowclone/commit/7a44a3868620b8b73df238a3780cd91a7c10bdfa))

## [0.0.24](https://github.com/theonly1me/shadowclone/compare/v0.0.23...v0.0.24) (2026-10-08)


### Features

* check dependencies and account for every review candidate ([#174](https://github.com/theonly1me/shadowclone/issues/174)) ([517a416](https://github.com/theonly1me/shadowclone/commit/517a4163aa7c18eabce7dbe50ea5b8ede4060619))
* review pull requests locally and from the github clone ([#172](https://github.com/theonly1me/shadowclone/issues/172)) ([96f95f3](https://github.com/theonly1me/shadowclone/commit/96f95f3377a848f5359829ab7b8b9eb5afa963fc))

## [0.0.23](https://github.com/theonly1me/shadowclone/compare/v0.0.22...v0.0.23) (2026-10-06)


### Features

* react to a request when the clone starts working on it ([#170](https://github.com/theonly1me/shadowclone/issues/170)) ([8e497ef](https://github.com/theonly1me/shadowclone/commit/8e497efbf64ec73c3093903fb23845f16bb976b3))


### Fixes

* accept an issue dispatch when github leaves out the empty head input ([#165](https://github.com/theonly1me/shadowclone/issues/165)) ([d751394](https://github.com/theonly1me/shadowclone/commit/d751394446e3d04fb4eb566e24f61de6dfd8644f))
* accept the default branch ruleset when github omits its default update parameter ([#162](https://github.com/theonly1me/shadowclone/issues/162)) ([8f515f5](https://github.com/theonly1me/shadowclone/commit/8f515f5104dc05244fcedf5fff01ef29f620d0a3))
* exempt people from the default branch ruleset so they merge without a bypass prompt ([#169](https://github.com/theonly1me/shadowclone/issues/169)) ([07d67fe](https://github.com/theonly1me/shadowclone/commit/07d67feee8f7dbef4815a0d5e95294b0b291d719))
* let the clone mark its own pr ready for review ([#163](https://github.com/theonly1me/shadowclone/issues/163)) ([35f3ee2](https://github.com/theonly1me/shadowclone/commit/35f3ee21b2d49ef531e13384819af792cbb360d5))
* point the skill map's collapse chevron left ([#166](https://github.com/theonly1me/shadowclone/issues/166)) ([52276d5](https://github.com/theonly1me/shadowclone/commit/52276d55c2d6bf9a86a767203c27b4555a81b650))
* resume the clone's pr after the last ci run on its own push finishes ([#171](https://github.com/theonly1me/shadowclone/issues/171)) ([13ad35a](https://github.com/theonly1me/shadowclone/commit/13ad35a07aec8fc46fe23ef332190cee657f9c1f))

## [0.0.22](https://github.com/theonly1me/shadowclone/compare/v0.0.21...v0.0.22) (2026-10-05)


### Fixes

* keep user skills that name another skill's file in backticks ([#154](https://github.com/theonly1me/shadowclone/issues/154)) ([cb3a944](https://github.com/theonly1me/shadowclone/commit/cb3a9447c8943e8b8592ac73b431f6893f1b6c38))
* start clone setup from the equipped build and show why a preview fails ([#155](https://github.com/theonly1me/shadowclone/issues/155)) ([6cee926](https://github.com/theonly1me/shadowclone/commit/6cee9268d879343a626c7b99f4fc8664aaf58c8d))

## [0.0.21](https://github.com/theonly1me/shadowclone/compare/v0.0.20...v0.0.21) (2026-10-05)


### Fixes

* route personal skills by name so they fit the native budget ([#152](https://github.com/theonly1me/shadowclone/issues/152)) ([92b867a](https://github.com/theonly1me/shadowclone/commit/92b867a6ddbcdcc13b4c55b9c49b75c0baf236d6))

## [0.0.20](https://github.com/theonly1me/shadowclone/compare/v0.0.19...v0.0.20) (2026-10-05)


### Features

* remove the eval command from the shipped cli and move the evaluations out of src ([#151](https://github.com/theonly1me/shadowclone/issues/151)) ([2f18eb4](https://github.com/theonly1me/shadowclone/commit/2f18eb4bcb239fad1ee68c140d05e2c73218c7ea))


### Documentation

* add the no-comments eval of code written with and without a comment ban ([#149](https://github.com/theonly1me/shadowclone/issues/149)) ([b1d38c2](https://github.com/theonly1me/shadowclone/commit/b1d38c282949c6c3ace49609d8a4308ac77fdd2a))

## [0.0.19](https://github.com/theonly1me/shadowclone/compare/v0.0.18...v0.0.19) (2026-10-04)


### Features

* equip a whole category, collapse map groups, and name the limit when a model call stops ([94040e1](https://github.com/theonly1me/shadowclone/commit/94040e1f8adf80504e5c2c844a2b9c95d7c98598))


### Fixes

* let the wizard apply builds when agent instructions and skills are shared through links ([290fa4b](https://github.com/theonly1me/shadowclone/commit/290fa4be194180e2dd0fa7ed08cedd858fe2b13e))
* name builds in seconds by turning off thinking for the claude code fast tier ([e95b2be](https://github.com/theonly1me/shadowclone/commit/e95b2beb07cdc3b05c1d36c27abb31bdab1b45b0))

## [0.0.18](https://github.com/theonly1me/shadowclone/compare/v0.0.17...v0.0.18) (2026-10-04)


### Features

* add the choose-by-consequence skill ([67f5eea](https://github.com/theonly1me/shadowclone/commit/67f5eea92b2a7502ad2dc21d25dd62aaed0e4b8b))
* add the planning skill with a review page ([ba36df8](https://github.com/theonly1me/shadowclone/commit/ba36df8b2dba101d74a37728ace2b5edc41671bd))
* add the review findings verification skill ([06f281b](https://github.com/theonly1me/shadowclone/commit/06f281bbc165789511bf70830edb1cd6bdd7bba9))
* add the write-plain-english skill with a checker ([0d9ae80](https://github.com/theonly1me/shadowclone/commit/0d9ae80c86e4428b90d459acb4fa59cb8d567a61))
* bring the remaining bundled skills to the quality bar ([6f9e0d4](https://github.com/theonly1me/shadowclone/commit/6f9e0d4a019462c0c0707eaf200a83e807e81be8))
* capture the user's writing voice with consent, and keep sync going past a linked agent file ([179f681](https://github.com/theonly1me/shadowclone/commit/179f68186a8fa0c2a23e2bb9cc592e51a861c1d3))
* check shipped guidance for private material ([28be732](https://github.com/theonly1me/shadowclone/commit/28be73230e2c845681632da6f85ee490995735a0))
* flag instruction-shaped text in learned rules before publication ([04f6e4a](https://github.com/theonly1me/shadowclone/commit/04f6e4a554fa8f8073c800d6561e3cc19cc192e8))
* fold scoped fix discipline into scope-confirmed-changes ([1ea94db](https://github.com/theonly1me/shadowclone/commit/1ea94dbd4c917fa70b546f92aedb7ec05aaf1184))
* give a failed learned skill draft one repair turn ([f8ee3ab](https://github.com/theonly1me/shadowclone/commit/f8ee3ab6eb2c73d02bd23e4dc366b99a8859287f))
* lint bundled skills against the quality bar ([40ca632](https://github.com/theonly1me/shadowclone/commit/40ca6327b44bd01321e5ccb9324e7ec249b67294))
* merge the testing skills into tests-that-catch-bugs ([b552eec](https://github.com/theonly1me/shadowclone/commit/b552eecff951cd0397673c84fd3b60cdb2735e24))
* migrate builds away from retired bundled skill ids ([535c097](https://github.com/theonly1me/shadowclone/commit/535c097e33e25963febf6f5add76d576cf29e1c9))
* publish supporting files of bundled skills ([4f4adf5](https://github.com/theonly1me/shadowclone/commit/4f4adf5900ca951009eb8e92e19d7a3b45c66205))
* reject en dashes in repository prose ([398e120](https://github.com/theonly1me/shadowclone/commit/398e120d18fb15190dc14966cff0dcbaa4ad1ad4))
* route bundled skills by the moment they apply ([31c6db6](https://github.com/theonly1me/shadowclone/commit/31c6db6ef6a6487c3088bbb130cf0ae6d88b0004))
* show every skill on a scrollable star map and name the build with the fast model ([5d805fe](https://github.com/theonly1me/shadowclone/commit/5d805fe776a278dbf673d6636e7e19a88e1130e2))
* update unedited installed copies of bundled skills during sync ([155c2ff](https://github.com/theonly1me/shadowclone/commit/155c2ffcebfb87dd0bc0b4ba36b8a66ca5210d59))
* verify the real outcome before handoff ([d4316a4](https://github.com/theonly1me/shadowclone/commit/d4316a49aacc927eb468b7f126c01e7d310573d4))


### Fixes

* block codex repository installs that hide a team AGENTS.md ([e371c9c](https://github.com/theonly1me/shadowclone/commit/e371c9cfdf7626808f576f6220e6ab31dcf904de))
* keep repository installs out of team files and commits, and remove empty skill folders ([f134152](https://github.com/theonly1me/shadowclone/commit/f13415246f865c43eb3328ec12411f3e71c785c3))
* replace only shipped versions of bundled skills during sync ([b8113a6](https://github.com/theonly1me/shadowclone/commit/b8113a61132e7ac7ab9dddc5c920c373696189a0))
* report agents that setup skipped and name the blocking link ([d6cd1d0](https://github.com/theonly1me/shadowclone/commit/d6cd1d0857e80df792bf48738d3e4206cb9c6987))
* report every rule that a learning merge drops ([be31bbd](https://github.com/theonly1me/shadowclone/commit/be31bbd80f4f788713ef4452be48b1f681cb2fc9))
* skip agents whose instruction file is a symbolic link during setup ([ff035b5](https://github.com/theonly1me/shadowclone/commit/ff035b559a379b242b684f978ab97dd9c12d3c47))
* update bundled skills only when the user runs sync ([028e091](https://github.com/theonly1me/shadowclone/commit/028e091df2b0325fa3eb961a3d2cca2a7f9852f2))


### Documentation

* record the bundled skill quality and delivery design ([b62d8e9](https://github.com/theonly1me/shadowclone/commit/b62d8e95d3309b6c5d1863e9a94a757e6a69d86c))
* record the wizard map, build naming, and voice capture design ([7568ddf](https://github.com/theonly1me/shadowclone/commit/7568ddf14fec214389251a43b9eabeadeef0932f))

## [0.0.17](https://github.com/theonly1me/shadowclone/compare/v0.0.16...v0.0.17) (2026-10-03)


### Features

* add personal github clones ([8451dac](https://github.com/theonly1me/shadowclone/commit/8451dac2ea7b0a3a21cdc11c3d89942f72e0c2ec))
* block clone pushes to the default branch with a ruleset ([a09f8af](https://github.com/theonly1me/shadowclone/commit/a09f8af6a99849402ee72ad9e8b47fbb57d9b36d))
* **eval:** add reusable preference evaluations and publish results ([0a53945](https://github.com/theonly1me/shadowclone/commit/0a539453ace85697401c5339b5b64b96f91da11f))
* remove shell history as a capture source ([3cf3a7a](https://github.com/theonly1me/shadowclone/commit/3cf3a7a520bdc922da349a7d132e6caffed67271))
* remove the shadowclone run command ([0772bc9](https://github.com/theonly1me/shadowclone/commit/0772bc94f8744f22f14feccbc80ea1fb4438ad3e))
* ship the ready-for-review shadowclone-work skill and remove the task harness ([cff2b0d](https://github.com/theonly1me/shadowclone/commit/cff2b0d988226d5f5e550b1be7697372953a01a2))
* state the evidence each bundled skill reports ([b2236f6](https://github.com/theonly1me/shadowclone/commit/b2236f69b0ce41480f37ed640048dca0fb0e0e14))


### Fixes

* count only user-authored text as learning evidence ([1d5a725](https://github.com/theonly1me/shadowclone/commit/1d5a725129d9b910fe92b5bb795c3d9742e58eab))
* open the cursor store fallback with an encoded sqlite uri ([93c44e3](https://github.com/theonly1me/shadowclone/commit/93c44e3f0e443e8cb4afe4e81f483c62d8294078))
* retry hdiutil commands for read-only eval workspaces ([fa01ff1](https://github.com/theonly1me/shadowclone/commit/fa01ff10a6ef26da3ce5b6984742f6da64f0c375))


### Documentation

* require conventional-commit pull request titles ([a51fddf](https://github.com/theonly1me/shadowclone/commit/a51fddf1f37669025f0331d1567816edb1acc949))

## [0.0.16](https://github.com/theonly1me/shadowclone/compare/v0.0.15...v0.0.16) (2026-10-03)


### Features

* **pi:** add native harness integration ([#94](https://github.com/theonly1me/shadowclone/issues/94)) ([316aefd](https://github.com/theonly1me/shadowclone/commit/316aefda2e2c6f00726e274c2a6ab9338de83011))

## [0.0.15](https://github.com/theonly1me/shadowclone/compare/v0.0.14...v0.0.15) (2026-10-01)


### Features

* **eval:** add fixed four-setup preference benchmark ([286030f](https://github.com/theonly1me/shadowclone/commit/286030faf125e65b3af6db4a27ab7e3345f10271))

## [0.0.14](https://github.com/theonly1me/shadowclone/compare/v0.0.13...v0.0.14) (2026-09-30)


### Features

* add verified engineering workflows ([#90](https://github.com/theonly1me/shadowclone/issues/90)) ([b7d2c5b](https://github.com/theonly1me/shadowclone/commit/b7d2c5b8107edfd4aefb09f6e2fab37bcd5b2084))

## [0.0.13](https://github.com/theonly1me/shadowclone/compare/v0.0.12...v0.0.13) (2026-09-30)


### Fixes

* upgrade plugin setup and polish skill navigation ([#88](https://github.com/theonly1me/shadowclone/issues/88)) ([bd239ea](https://github.com/theonly1me/shadowclone/commit/bd239ea9e56a8ee44d7566ea987680adcc9de9de))

## [0.0.12](https://github.com/theonly1me/shadowclone/compare/v0.0.11...v0.0.12) (2026-09-29)


### Features

* **eval:** add the preference study for Codex and Claude and remove superseded protocols ([#86](https://github.com/theonly1me/shadowclone/issues/86)) ([247e960](https://github.com/theonly1me/shadowclone/commit/247e960d9defa8910a67b59ce0590f50195b05a9))


### Fixes

* **environment:** preserve skill publication and review decisions ([#83](https://github.com/theonly1me/shadowclone/issues/83)) ([340a15f](https://github.com/theonly1me/shadowclone/commit/340a15f66c22d89cee65bf58e69640f8e85e6ecc))

## [0.0.11](https://github.com/theonly1me/shadowclone/compare/v0.0.10...v0.0.11) (2026-09-27)


### Features

* maintain portable skills and add the agent build wizard ([#79](https://github.com/theonly1me/shadowclone/issues/79)) ([d9cf211](https://github.com/theonly1me/shadowclone/commit/d9cf2112ef095f121998e45016a158cec07ae0d8))


### Fixes

* **release:** publish from the run that gated the tagged release commit ([#77](https://github.com/theonly1me/shadowclone/issues/77)) ([5c4e5d5](https://github.com/theonly1me/shadowclone/commit/5c4e5d5c8d8e8fa695a531766a76cf8887f16c7b))


### Documentation

* add readme header banner ([#80](https://github.com/theonly1me/shadowclone/issues/80)) ([c0c27bb](https://github.com/theonly1me/shadowclone/commit/c0c27bb1bc834238ad49b466d55c422f3d59b14a))

## [0.0.10](https://github.com/theonly1me/shadowclone/compare/v0.0.9...v0.0.10) (2026-09-26)


### Features

* set up repositories for every agent and shrink session-start context ([#74](https://github.com/theonly1me/shadowclone/issues/74)) ([4b7872d](https://github.com/theonly1me/shadowclone/commit/4b7872d3c651edef07dfdef4d1e340c068623747))

## [0.0.9](https://github.com/theonly1me/shadowclone/compare/v0.0.8...v0.0.9) (2026-09-15)


### Fixes

* defer failed skill assessments ([#71](https://github.com/theonly1me/shadowclone/issues/71)) ([078e227](https://github.com/theonly1me/shadowclone/commit/078e22714ec2d80133e296abae73e7435712e081))

## [0.0.8](https://github.com/theonly1me/shadowclone/compare/v0.0.7...v0.0.8) (2026-09-15)


### Fixes

* tolerate unavailable Git metadata ([#69](https://github.com/theonly1me/shadowclone/issues/69)) ([f708ed0](https://github.com/theonly1me/shadowclone/commit/f708ed0332d5ae04eec69b4e498f69a2b0298558))

## [0.0.7](https://github.com/theonly1me/shadowclone/compare/v0.0.6...v0.0.7) (2026-09-14)


### Fixes

* skip linked repository guidance during setup ([#67](https://github.com/theonly1me/shadowclone/issues/67)) ([29915bc](https://github.com/theonly1me/shadowclone/commit/29915bc0407d9aa5aec48496794fefd11dace89e))

## [0.0.6](https://github.com/theonly1me/shadowclone/compare/v0.0.5...v0.0.6) (2026-09-14)


### Features

* **cli:** add profile onboarding wizard ([#56](https://github.com/theonly1me/shadowclone/issues/56)) ([8020e4d](https://github.com/theonly1me/shadowclone/commit/8020e4d5debfdc09a9d098b8c8022f6bc836392f))
* **engine:** bound learning execution ([#54](https://github.com/theonly1me/shadowclone/issues/54)) ([620f664](https://github.com/theonly1me/shadowclone/commit/620f6640888314a0c9feab238be84533a72102c5))
* eval results ([b6bfd07](https://github.com/theonly1me/shadowclone/commit/b6bfd075b58fac792c787316f95d067deda9a644))
* **guidance:** add seed preference and skill library ([#55](https://github.com/theonly1me/shadowclone/issues/55)) ([ac8ab3f](https://github.com/theonly1me/shadowclone/commit/ac8ab3f7c602eb05a6a6c4ddd5673087299a715a))
* **profile:** add persistent rule lifecycle ([#53](https://github.com/theonly1me/shadowclone/issues/53)) ([09374ec](https://github.com/theonly1me/shadowclone/commit/09374ec766c764f0c6c8191dccebe27c22c21b9e))


### Fixes

* complete security and data-handling remediation ([#64](https://github.com/theonly1me/shadowclone/issues/64)) ([6643de6](https://github.com/theonly1me/shadowclone/commit/6643de66287d494fb67cf543bd9d58ceb448b275))
* enforce repository identity and safety boundaries ([#51](https://github.com/theonly1me/shadowclone/issues/51)) ([3f59d8f](https://github.com/theonly1me/shadowclone/commit/3f59d8f95c50dff111227e611b74210b2c1476c0))


### Documentation

* align consent and capability claims ([#52](https://github.com/theonly1me/shadowclone/issues/52)) ([c9e0e09](https://github.com/theonly1me/shadowclone/commit/c9e0e096aba15b8fbe2242d79cc3cb4f9df5923a))
* **architecture:** clarify that tool results are always excluded ([7a9274f](https://github.com/theonly1me/shadowclone/commit/7a9274fd85055df6c7f2b718d0502ac1f03e6581))

## [0.0.5](https://github.com/theonly1me/shadowclone/compare/v0.0.4...v0.0.5) (2026-09-06)


### Features

* **eval:** add an --engine flag with capability aware selection ([a606fbd](https://github.com/theonly1me/shadowclone/commit/a606fbd8b541f94055d04c4063800b5582044404))
* **eval:** add an --engine flag with capability aware selection ([bf53d99](https://github.com/theonly1me/shadowclone/commit/bf53d9953d6a34c698839b7821d684d9203af2d5))
* **eval:** add automatic transfer evaluations for codex and claude code ([4eb0e92](https://github.com/theonly1me/shadowclone/commit/4eb0e92b75aeda15630cb91bb58b21bcd61fed6a))
* **eval:** add automatic transfer evaluations for codex and claude code ([318ddf0](https://github.com/theonly1me/shadowclone/commit/318ddf0282acacfb818321a90f8ce53d46060523))
* **redact:** add a shannon entropy layer for unknown-vendor secrets ([ba1a52f](https://github.com/theonly1me/shadowclone/commit/ba1a52f081b6d56d94ec60a924234aedf5296786))
* **redact:** add a shannon entropy layer for unknown-vendor secrets ([611ad00](https://github.com/theonly1me/shadowclone/commit/611ad00359b7c53dc0dc7abb22fca7341f4d8a57))


### Fixes

* **cli:** reject repeated eval flags and keep dashes in a run task ([4215058](https://github.com/theonly1me/shadowclone/commit/421505831c7bfd86a4c2be5fd8655b7845990805))
* **config:** report the failing config setting by name again ([4127b92](https://github.com/theonly1me/shadowclone/commit/4127b924895daaa1f7436a47ce9a09b8fa6eaaa1))
* **eval:** allowlist slash commands and redact engine failure messages ([2e28191](https://github.com/theonly1me/shadowclone/commit/2e28191060e3211f23b08e6f04dc9e81cf385d30))
* **eval:** canonicalize sandbox paths and confirm evaluation spend ([2ab203c](https://github.com/theonly1me/shadowclone/commit/2ab203c2c39878202b57a774c8f35ce06a3882b8))
* **eval:** strip leading slash commands and surface replay errors ([439c889](https://github.com/theonly1me/shadowclone/commit/439c88970c7e0fd0bd76fb078c449c9f85e5b4f4))
* **eval:** strip leading slash commands and surface replay errors ([e406202](https://github.com/theonly1me/shadowclone/commit/e406202fdeb320bb4999ef8c9524da0256ac84ab))
* **observe:** match interruption markers carried in text blocks ([f99b051](https://github.com/theonly1me/shadowclone/commit/f99b05195720c9fc08ffb1ac960e180f8a458e5b))
* **observe:** match interruption markers carried in text blocks ([93cdeac](https://github.com/theonly1me/shadowclone/commit/93cdeac44b71024bfda60606cf372714d0b9157e))
* **signal:** restore literal wildcard matching for blocked origins ([8a7a3ae](https://github.com/theonly1me/shadowclone/commit/8a7a3ae18bc3fe18da141469d03b74040231fb0e))


### Documentation

* describe the transfer eval and the agent-context source ([631d45a](https://github.com/theonly1me/shadowclone/commit/631d45a16479ecf03991147f5061d244bf6ebc3e))

## [0.0.4](https://github.com/theonly1me/shadowclone/compare/v0.0.3...v0.0.4) (2026-09-06)


### Fixes

* **cursor:** support wal mode without shm files via immutable fallback ([bc35a50](https://github.com/theonly1me/shadowclone/commit/bc35a50566c2438e31332fbecce19359c9d0c66e))
* **cursor:** support wal mode without shm files via immutable fallback ([4ca0731](https://github.com/theonly1me/shadowclone/commit/4ca0731ecd06f77c61e4107a8b9bd3bc8b6b1099))
* **eval:** address shadowclone self-review findings ([b81bd0f](https://github.com/theonly1me/shadowclone/commit/b81bd0f6ba64a33b10a800f308e056353351e64b))
* **eval:** use uuid session ids, extract prompt text, and drop structural telemetry on deep learn ([ce9fb74](https://github.com/theonly1me/shadowclone/commit/ce9fb74b49cce674c54f688ec48836e53dbf854f))
* **eval:** use uuid session ids, extract prompt text, and drop structural telemetry on deep learn ([32e1581](https://github.com/theonly1me/shadowclone/commit/32e1581da50ce73922dd03773eb9f13136df57d0))

## [0.0.3](https://github.com/theonly1me/shadowclone/compare/v0.0.2...v0.0.3) (2026-09-06)


### Features

* **dispatch:** enforce dispatch ceiling, host-side push, and git exclude agent ([f15886e](https://github.com/theonly1me/shadowclone/commit/f15886e9556253a1b4885175deee47699234baaf))
* **dispatch:** enforce dispatch ceiling, host-side push, and git exclude agent ([3e63567](https://github.com/theonly1me/shadowclone/commit/3e63567b341438e5126504772cca1301fd0d9f15))
* **eval:** add replay eval command, action fingerprints, and delta scoring (closes [#14](https://github.com/theonly1me/shadowclone/issues/14)) ([67705bb](https://github.com/theonly1me/shadowclone/commit/67705bb615d5f5c45902da90d78278f165960fde))
* **eval:** add replay eval command, action fingerprints, and delta scoring (closes [#14](https://github.com/theonly1me/shadowclone/issues/14)) ([b20c60b](https://github.com/theonly1me/shadowclone/commit/b20c60ba88620e2d1ec309d1cd0bfd9d7f30f9b9))
* **profile:** scoped pruning, truthful evidence, and git exclude ([8911b09](https://github.com/theonly1me/shadowclone/commit/8911b09c3e9ed3f97e0e475b920b0544a9f1d48e))
* **profile:** scoped pruning, truthful evidence, and git exclude ([5c1b081](https://github.com/theonly1me/shadowclone/commit/5c1b0816c1a33c61180bcbe0263d6ebeef025bf7))
* **redact:** sliced redaction and adversarial corpus ([50cd650](https://github.com/theonly1me/shadowclone/commit/50cd65009a8dc57d0858a4e64e315e8ef577f074))
* **redact:** sliced redaction and adversarial corpus ([2141655](https://github.com/theonly1me/shadowclone/commit/214165579f21c69af1533632a92461d98031bcf8))
* **signal:** add marker staleness detection, antigravity cancel mapping, and learn dry-run ([574e929](https://github.com/theonly1me/shadowclone/commit/574e92976c26688ffd7de647e05d692d44b64df3))
* **signal:** add marker staleness detection, antigravity cancel mapping, and learn dry-run ([c3b237a](https://github.com/theonly1me/shadowclone/commit/c3b237a1b247d73572854766a4864f042a294be5))


### Fixes

* **docs:** replace amnesia hook with agreed cross-session lead in launch brief ([a7ae94f](https://github.com/theonly1me/shadowclone/commit/a7ae94f2be36dbf644a4d25c5291aefd363a52ad))
* **eval:** add cost confirmation preview and isolate session working directories ([66af631](https://github.com/theonly1me/shadowclone/commit/66af63192343b273fcbfc67ea14bffc78fdb75d5))
* **profile:** drop in-flight duplicate rules and checkpoint merge distillation ([537d22a](https://github.com/theonly1me/shadowclone/commit/537d22ace3745f18035483a713b9a1b40df3b37b))
* **redact:** handle compound secret assignments and file URLs in home scrubbing ([a1c444a](https://github.com/theonly1me/shadowclone/commit/a1c444a04c504b36309b3b8b5fc83bff1d2fb721))


### Documentation

* **readme:** rewrite positioning, add evaluation architecture, and launch brief ([dfb2758](https://github.com/theonly1me/shadowclone/commit/dfb27588f31746d8461b9c7e67016b99c711eabd))
* **readme:** rewrite positioning, add evaluation architecture, and motivation ([4750129](https://github.com/theonly1me/shadowclone/commit/475012957519590409cb222136a2361bd6c22549))

## [0.0.2](https://github.com/theonly1me/shadowclone/compare/v0.0.1...v0.0.2) (2026-09-05)


### Features

* add --help and --version to the cli ([5ed2bf1](https://github.com/theonly1me/shadowclone/commit/5ed2bf19fae1cc7524da9b2a09ec04e5ae2d5c47))
* add codex and cursor providers ([5800691](https://github.com/theonly1me/shadowclone/commit/5800691c3ea57b48654fae0d69775a3dea1ae58f))
* add opt-in transcript indexing ([e6895de](https://github.com/theonly1me/shadowclone/commit/e6895de57921b5f00e7a2cc57294904db5e42ef1))
* add provider capabilities and antigravity observation ([688ab6c](https://github.com/theonly1me/shadowclone/commit/688ab6cd104c23b9c7f0d484491fd3e644e93a90))
* add provider capabilities and antigravity observation ([23cee6c](https://github.com/theonly1me/shadowclone/commit/23cee6cd77cb329aa9df83ec7421ec2b7801a878))
* add the headless worktree clone ([4214994](https://github.com/theonly1me/shadowclone/commit/421499473db098e719bd20b43b4fa38f86bdb533))
* add the live session clone ([3926132](https://github.com/theonly1me/shadowclone/commit/392613265e616c6b8829c63a9d418f5ed05199e9))
* build phase zero foundation ([8904ab5](https://github.com/theonly1me/shadowclone/commit/8904ab5c6a60ef03153457dd6b57e8073192d936))
* build the offline mirror ([57ec82e](https://github.com/theonly1me/shadowclone/commit/57ec82edf5da6f11f73dd02d6db47c4e5a3b1115))
* distillation consolidation pass and telemetry dropping ([28843ef](https://github.com/theonly1me/shadowclone/commit/28843efa5ae54c0b5cbf799bbebf72d761d03bb0))
* distillation consolidation pass and telemetry dropping ([8568492](https://github.com/theonly1me/shadowclone/commit/8568492a7a908dd5591f5ed593e27feb6bed7c7d))
* publish shadowclone to npm with per-platform binaries ([d94847d](https://github.com/theonly1me/shadowclone/commit/d94847d744f68b07231102357cf88894bab69c91))
* publish shadowclone to npm with per-platform binaries ([987cb4a](https://github.com/theonly1me/shadowclone/commit/987cb4a7c658f11e0864dc904799b44a25231611))
* quickstart and auto-init/install UX ([1bf1c45](https://github.com/theonly1me/shadowclone/commit/1bf1c45660222d530d8e376af7b681c815d301f7))
* quickstart and auto-init/install UX ([325e020](https://github.com/theonly1me/shadowclone/commit/325e0209be603574e21699f597aadc2647520a08))
* ship a single npm package that brings its own runtime ([d1c98d4](https://github.com/theonly1me/shadowclone/commit/d1c98d4eedb46e7ee1fcbc1beb22f9bb0fedde6e))
* ship a single npm package that brings its own runtime ([7dcf207](https://github.com/theonly1me/shadowclone/commit/7dcf207238b77e5c7e12382c10244ab6a0a1c1a1))


### Fixes

* annotate the cursor stat result for the lint gate ([ce303e1](https://github.com/theonly1me/shadowclone/commit/ce303e16d33657cd5223926610ace83347e24516))
* bound correction context egress ([839a8c7](https://github.com/theonly1me/shadowclone/commit/839a8c7c083a6b121af52a992789d6112eef3285))
* fall back to unmerged rules when the merge response is unusable ([8f3e792](https://github.com/theonly1me/shadowclone/commit/8f3e79208d3bcb5c5c1394b88d1c5f94482abe41))
* ignore unreadable cursor database ([70b0bca](https://github.com/theonly1me/shadowclone/commit/70b0bca6a0d4caaf7fcd5642511d861250945b38))
* ignore unreadable cursor database ([f769c80](https://github.com/theonly1me/shadowclone/commit/f769c80b41cedc6bfd975e882a84630aef30470f))
* keep distilled rules and remove emptied profile files during the prune ([5399a77](https://github.com/theonly1me/shadowclone/commit/5399a77308719f57069daa66e451c6b29d5c02d1))
* keep learned boundaries advisory ([1a2cfd6](https://github.com/theonly1me/shadowclone/commit/1a2cfd63f1e7009786cfa2c3e99b51105897c49a))
* keep learned tool denials advisory ([d09ef1c](https://github.com/theonly1me/shadowclone/commit/d09ef1cde1b129fa6238c06930227febef871638))
* only auto-install the live clone inside a git work tree ([8be0bd1](https://github.com/theonly1me/shadowclone/commit/8be0bd186fb394511dfea0beb4db79cee0f4eaa8))
* report managed engine policy accurately ([188e2b5](https://github.com/theonly1me/shadowclone/commit/188e2b5f19ff832bd9b64eac213a60a0ceaff525))
* use an optional chain in the checkpoint rule guard ([46908e3](https://github.com/theonly1me/shadowclone/commit/46908e35fbef561dda38e7fe30ba7fa47c7cb111))
* use an optional chain in the distillation capability check ([9925ad5](https://github.com/theonly1me/shadowclone/commit/9925ad545e9eb446a0dce0b956d9451b6fb3e600))


### Documentation

* add amnesia copy to README ([0841108](https://github.com/theonly1me/shadowclone/commit/0841108003a18224733fafb594df730e3c2b0435))
* add amnesia copy to README ([9d7881b](https://github.com/theonly1me/shadowclone/commit/9d7881bbf0cfc69bb731daa4d449b63554ba7010))
* add the competitive landscape and what to borrow from trace ([0f5d6ed](https://github.com/theonly1me/shadowclone/commit/0f5d6ede1e62e4b48e30e630d0068870fdc20db0))
* align readme, claude.md, and contributing with the transcript design ([817a036](https://github.com/theonly1me/shadowclone/commit/817a0367f3916e63efcabd2fc8b1690008f8a7f5))
* align readme, claude.md, and contributing with the transcript design ([7e86115](https://github.com/theonly1me/shadowclone/commit/7e8611557abc32e91dc9e0981527952a325fb498))
* architect the pivot to agent transcript learning ([b5b22e2](https://github.com/theonly1me/shadowclone/commit/b5b22e2f990c670e9e17677aa5143cc7e0d97ba4))
* architect the pivot to agent transcript learning ([baf32c6](https://github.com/theonly1me/shadowclone/commit/baf32c671e411394b2f0c10cf22cf7b78a03a491))
* compile the profile into a subagent and label the learn mockup ([256383b](https://github.com/theonly1me/shadowclone/commit/256383b21fd978b20c3df98c7f6e0d9071e99cd4))
* cut the readme to shape and split wall paragraphs ([0293343](https://github.com/theonly1me/shadowclone/commit/02933430f367f9f8b8504913a6a7e983cd42ced0))
* cut the readme to shape and split wall paragraphs ([511688a](https://github.com/theonly1me/shadowclone/commit/511688a645c5ef1d3e1cf77b178860aa963a8f78))
* document the gate, releasing, and security reporting ([aeec81c](https://github.com/theonly1me/shadowclone/commit/aeec81c15322d9c082e8ff2862781996fa569831))
* highlight architectural advantages ([5354cf4](https://github.com/theonly1me/shadowclone/commit/5354cf4ff191f0cc0e9b0561c39cf8794483c5da))
* keep antigravity observation only ([e23ad7d](https://github.com/theonly1me/shadowclone/commit/e23ad7d3f3918b3fab39fdeaa01db45ee4160b2c))
* list antigravity capture source ([fb29eef](https://github.com/theonly1me/shadowclone/commit/fb29eef99704a13841a124fea028fdba576b83c9))
* plan provider expansion ([c24608f](https://github.com/theonly1me/shadowclone/commit/c24608f41902309691b8fe140e69bb6fa1782888))
* put the mirror first and compile the profile into a subagent ([1a04ff1](https://github.com/theonly1me/shadowclone/commit/1a04ff13b2b5e2c60ce39ffe275bbd1e57374ecd))
* put the mirror first and make phase 2 the go or no go ([062baad](https://github.com/theonly1me/shadowclone/commit/062baadd281c83c63c703e651db6d41b22addda8))
* renumber the provider expansion design doc ([a4528fe](https://github.com/theonly1me/shadowclone/commit/a4528fe9b2ba9ddaa9054c02cc0527b47c37490f))
* skip deprecated gemini cli ([9ed5bf5](https://github.com/theonly1me/shadowclone/commit/9ed5bf5db988389712aa7cc0eafaa4e553984584))
* track executable replay evaluation ([2d8e084](https://github.com/theonly1me/shadowclone/commit/2d8e08492237f3a9c8d85c3a330a075ad39d16f5))
