export {
  normalizeRemoteOrigin,
  normalizeRemoteRepository,
  readGitRemote,
  type GitRemoteReader,
} from "./remote";

export {
  getEventOrigin,
  getEventRepository,
  resolveCwdOrigin,
  resolveEventRepositories,
  resolveRepository,
  type OriginBindingStore,
} from "./resolve";
