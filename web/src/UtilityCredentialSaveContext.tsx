import { createContext, useContext, type ReactNode } from "react";

type BeforeUtilityCredentialSave = () => Promise<void>;

const UtilityCredentialSaveContext = createContext<BeforeUtilityCredentialSave | null>(null);

export function UtilityCredentialSaveProvider({
  beforeSave,
  children
}: {
  beforeSave: BeforeUtilityCredentialSave;
  children: ReactNode;
}) {
  return (
    <UtilityCredentialSaveContext.Provider value={beforeSave}>
      {children}
    </UtilityCredentialSaveContext.Provider>
  );
}

export function useBeforeUtilityCredentialSave(): BeforeUtilityCredentialSave | null {
  return useContext(UtilityCredentialSaveContext);
}
