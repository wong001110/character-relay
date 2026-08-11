const MAX_PORTRAIT_BYTES = 8 * 1024 * 1024;

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Preserve the raw response below.
  }
  return raw || `Request failed with ${response.status}`;
}

function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read the selected image."));
    reader.onload = () => {
      const value = typeof reader.result === "string" ? reader.result : "";
      const marker = value.indexOf(",");
      if (!value.startsWith("data:") || marker < 0) {
        reject(new Error("Could not encode the selected image."));
        return;
      }
      resolve(value.slice(marker + 1));
    };
    reader.readAsDataURL(file);
  });
}

export function characterPortraitUrl(cardId: string, version?: number): string {
  const suffix = version ? `?v=${version}` : "";
  return `/api/characters/portraits/${encodeURIComponent(cardId)}${suffix}`;
}

export const characterPortraitApi = {
  async upload(cardId: string, file: File): Promise<{ url: string }> {
    if (!file.type.startsWith("image/")) {
      throw new Error("Choose an image file.");
    }
    if (file.size <= 0 || file.size > MAX_PORTRAIT_BYTES) {
      throw new Error("Character portraits must be 8 MB or smaller.");
    }
    const contentBase64 = await readBase64(file);
    const response = await fetch(`/api/characters/${encodeURIComponent(cardId)}/portrait`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mime_type: file.type || "image/*",
        content_base64: contentBase64
      })
    });
    if (!response.ok) throw new Error(await errorMessage(response));
    return response.json() as Promise<{ url: string }>;
  },

  async remove(cardId: string): Promise<void> {
    const response = await fetch(`/api/characters/${encodeURIComponent(cardId)}/portrait`, {
      method: "DELETE",
      credentials: "include"
    });
    if (!response.ok) throw new Error(await errorMessage(response));
  }
};
