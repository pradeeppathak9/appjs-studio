/** Move the item at `from` to position `to` (drag-and-drop reorder). */
export function moveItem<T>(items: T[], from: number, to: number): T[] {
  const next = [...items];
  const [it] = next.splice(from, 1);
  next.splice(to, 0, it);
  return next;
}
