/**
 * Keeps the global-corpus grant transition explicit at the Portal boundary.
 * The API owns authorization; this module only prevents the UI from treating
 * an existing enabled grant as a terminal state.
 */
export function nextGlobalCorpusGrantEnabled(currentlyEnabled: boolean): boolean {
  return !currentlyEnabled;
}
