import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useResource } from "./use-resource";

it("retains polling data during refresh and discards late results after a key change", async () => {
  let finish: (value: string) => void = () => {};
  const loader = vi.fn().mockResolvedValueOnce("processing").mockImplementationOnce(() => new Promise<string>(resolve => { finish = resolve; })).mockResolvedValueOnce("other account");
  const { result, rerender } = renderHook(({ id }) => useResource(loader, id), { initialProps: { id: "one" } });
  await waitFor(() => expect(result.current.data).toBe("processing"));
  act(() => result.current.refresh());
  expect(result.current.data).toBe("processing");
  rerender({ id: "two" });
  expect(result.current.data).toBeUndefined();
  await waitFor(() => expect(result.current.data).toBe("other account"));
  await act(async () => finish("stale result"));
  expect(result.current.data).toBe("other account");
});
