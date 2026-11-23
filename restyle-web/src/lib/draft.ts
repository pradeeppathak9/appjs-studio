/** The photo being styled, kept across pages ("Try another style" reuses it), in memory only. */
import { useSyncExternalStore } from "react";
import { RATIOS, type Ratio } from "./image";

type Draft = { photo: File | null; previewUrl: string | null; ratio: Ratio };

let draft: Draft = { photo: null, previewUrl: null, ratio: RATIOS[1] };
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export const drafts = {
  setPhoto(photo: File | null) {
    if (draft.previewUrl) URL.revokeObjectURL(draft.previewUrl);
    draft = { ...draft, photo, previewUrl: photo ? URL.createObjectURL(photo) : null };
    emit();
  },
  setRatio(ratio: Ratio) {
    draft = { ...draft, ratio };
    emit();
  },
};

export function useDraft(): Draft {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => draft,
  );
}
