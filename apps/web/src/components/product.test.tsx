import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { SessionContext } from "./app-provider";
import { ReceiptProgress, ReceiptUpload } from "./upload";
import { Purchases } from "./screens/purchases";
import { InventoryDetail } from "./screens/inventory";
import { InsightDetail } from "./screens/insights";
import { Assistant } from "./screens/assistant";
import { Settings } from "./screens/settings";
import { WalletActions } from "./screens/wallet";
import { Overview } from "./screens/overview";
import { insight, lot, message, pass, receipt, session } from "@/test/fixtures";

const navigation = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation, usePathname: () => "/" }));
const show = (children: ReactNode) => render(<SessionContext.Provider value={session}>{children}</SessionContext.Provider>);
beforeEach(() => {
  vi.spyOn(session.api, "purchases").mockResolvedValue([]);
  vi.spyOn(session.api, "receipts").mockResolvedValue([]);
  vi.spyOn(session.api, "categories").mockResolvedValue({ groups: [], has_more: false });
  vi.spyOn(session.api, "merchants").mockResolvedValue({ groups: [], has_more: false });
  vi.spyOn(session.api, "conversations").mockResolvedValue([]);
  vi.spyOn(session.api, "messages").mockResolvedValue([]);
  vi.spyOn(session.api, "insights").mockResolvedValue([]);
});

it("shows overview loading, financial failure and retry without inventing totals", async () => {
  const summary = vi.spyOn(session.api, "summary").mockRejectedValueOnce(new Error("Temporarily offline")).mockResolvedValue({ period: { start_date: "2026-09-01", end_date: "2026-10-01", timezone: "Asia/Kolkata" }, currencies: [] });
  vi.spyOn(session.api, "comparison").mockResolvedValue({ period: { start_date: "2026-09-01", end_date: "2026-10-01", timezone: "Asia/Kolkata" }, comparison_period: { start_date: "2026-08-01", end_date: "2026-09-01", timezone: "Asia/Kolkata" }, currencies: [] });
  show(<Overview />);
  expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  await screen.findAllByText("Temporarily offline");
  await userEvent.click(screen.getAllByRole("button", { name: /Try again/ })[0]);
  await screen.findByText(/Your picture starts/);
  expect(summary).toHaveBeenCalledTimes(2);
});

it("submits purchase filters to the service and recovers receipt-list failures", async () => {
  vi.mocked(session.api.receipts).mockRejectedValueOnce(new Error("Offline")).mockResolvedValue([]);
  show(<Purchases />);
  await screen.findByText("Your story starts with a receipt");
  await userEvent.type(screen.getByRole("searchbox"), " Rice ");
  await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));
  await waitFor(() => expect(session.api.purchases).toHaveBeenLastCalledWith({ query: "Rice", limit: 20, offset: 0 }, expect.any(AbortSignal)));
  await userEvent.click(screen.getByRole("button", { name: /Try again/ }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
});

it("uploads a receipt with progress, and renders the processed purchase link", async () => {
  vi.spyOn(session.api, "upload").mockImplementation(async (_file, progress) => { progress(100); return receipt; });
  vi.spyOn(session.api, "receipt").mockResolvedValue({ ...receipt, status: "PROCESSED", purchase_id: "purchase-1" });
  show(<ReceiptUpload />);
  await userEvent.upload(screen.getByLabelText("Receipt file"), new File(["image"], "receipt.png", { type: "image/png" }));
  await userEvent.click(screen.getByRole("button", { name: /Upload receipt/ }));
  expect((await screen.findByRole("link", { name: /View purchase/ })).getAttribute("href")).toBe("/purchases/purchase-1");
  expect(session.api.upload).toHaveBeenCalledOnce();
});

it("keeps the selected receipt on a duplicate upload error so the user can recover", async () => {
  vi.spyOn(session.api, "upload").mockRejectedValue(new Error("Receipt already uploaded"));
  show(<ReceiptUpload />);
  await userEvent.upload(screen.getByLabelText("Receipt file"), new File(["image"], "receipt.png", { type: "image/png" }));
  await userEvent.click(screen.getByRole("button", { name: /Upload receipt/ }));
  await screen.findByText("Receipt already uploaded");
  expect(screen.getByRole<HTMLButtonElement>("button", { name: /Upload receipt/ }).disabled).toBe(false);
});

it("bounds receipt polling and keeps manual refresh available", async () => {
  vi.useFakeTimers();
  const read = vi.spyOn(session.api, "receipt").mockResolvedValue(receipt);
  show(<ReceiptProgress initial={receipt} />);
  await act(async () => {});
  for (let i = 0; i < 40; i++) await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(read).toHaveBeenCalledTimes(41);
  await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
  expect(read).toHaveBeenCalledTimes(41);
  expect(screen.getByText(/taking longer than usual/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Refresh status/ }));
  await act(async () => {});
  expect(read).toHaveBeenCalledTimes(42);
});

it("stops polling for needs-review and explains the available recovery", async () => {
  vi.useFakeTimers();
  const read = vi.spyOn(session.api, "receipt").mockResolvedValue({ ...receipt, status: "NEEDS_REVIEW" });
  show(<ReceiptProgress initial={receipt} />);
  await act(async () => {});
  expect(screen.getByText(/review requires support/)).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(150000); });
  expect(read).toHaveBeenCalledOnce();
});

it("records inventory corrections with exact quantities and reuses an uncertain request key", async () => {
  vi.spyOn(session.api, "item").mockResolvedValue({ id: "item-1", name: "Rice", unit: "kg", quantity_remaining: "2", lot_count: 1 });
  vi.spyOn(session.api, "itemLots").mockResolvedValue([lot]);
  const action = vi.spyOn(session.api, "inventoryAction").mockRejectedValue(new Error("Connection lost"));
  show(<InventoryDetail id="item-1" />);
  await userEvent.click(await screen.findByRole("button", { name: /Record an update/ }));
  await userEvent.selectOptions(screen.getByLabelText("Action"), "CORRECTION");
  await userEvent.type(screen.getByLabelText(/Actual quantity remaining/), "0.000001");
  await userEvent.type(screen.getByLabelText("Reason"), "Checked pantry");
  await userEvent.click(screen.getByRole("button", { name: "Record update" }));
  await screen.findByText("Connection lost");
  await userEvent.click(screen.getByRole("button", { name: "Record update" }));
  await waitFor(() => expect(action).toHaveBeenCalledTimes(2));
  expect(action.mock.calls[0][1]).toEqual(action.mock.calls[1][1]);
  expect(action.mock.calls[0][1]).toMatchObject({ expected_version: 1, event_type: "CORRECTION", quantity_remaining: "0.000001" });
  expect(screen.getByText(/Model estimate/)).toBeTruthy();
});

it("dismisses insights with the server version and renders evidence as text", async () => {
  vi.spyOn(session.api, "insight").mockResolvedValue({ ...insight, source_data: { note: "<script>bad()</script>" } });
  const update = vi.spyOn(session.api, "updateInsight").mockResolvedValue({ ...insight, status: "DISMISSED" });
  show(<InsightDetail id={insight.id} />);
  await screen.findByText("<script>bad()</script>");
  expect(document.querySelector("script")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Dismiss insight" }));
  expect(update).toHaveBeenCalledWith(insight.id, "DISMISSED", 3);
});

it("retries Wallet synchronization without claiming the pass was saved", async () => {
  const sync = vi.spyOn(session.api, "syncPass").mockResolvedValue({ ...pass, status: "PENDING" });
  const refresh = vi.fn(); show(<WalletActions pass={pass} onChange={refresh} />);
  await userEvent.click(screen.getByRole("button", { name: /Retry synchronization/ }));
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  expect(sync).toHaveBeenCalledWith(pass.id);
});

it("saves preferences and reloads the profile", async () => {
  vi.spyOn(session.api, "preferences").mockResolvedValue(session.profile);
  const save = vi.spyOn(session.api, "savePreferences").mockResolvedValue({ ...session.profile, currency: "USD" });
  const reload = vi.spyOn(session, "reload"); show(<Settings />);
  const currency = await screen.findByLabelText(/Preferred currency/);
  await userEvent.clear(currency); await userEvent.type(currency, "usd");
  await userEvent.click(screen.getByRole("button", { name: "Save preferences" }));
  await screen.findByText("Preferences saved.");
  expect(save).toHaveBeenCalledWith({ currency: "USD", timezone: "Asia/Kolkata", locale: "en-IN" });
  expect(reload).toHaveBeenCalledOnce();
});

it("does not duplicate a new assistant conversation or turn after an uncertain failure", async () => {
  const create = vi.spyOn(session.api, "createConversation").mockResolvedValue({ id: "conversation-1", title: "Question", updated_at: receipt.created_at });
  const send = vi.spyOn(session.api, "sendMessage").mockRejectedValueOnce(new Error("Connection lost")).mockResolvedValue({ user_message: { ...message, role: "USER" }, assistant_message: message, replayed: true });
  show(<Assistant />);
  await userEvent.type(screen.getByLabelText("Message Raseed"), "What did I spend?");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByText("Connection lost");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
  expect(create).toHaveBeenCalledOnce();
  expect(send.mock.calls[0]).toEqual(send.mock.calls[1]);
});

it("bounds assistant polling even while refreshed messages are loading", async () => {
  vi.useFakeTimers(); vi.mocked(session.api.messages).mockResolvedValue([{ ...message, status: "PROCESSING" }]);
  show(<Assistant id="conversation-1" />);
  await act(async () => {});
  for (let i = 0; i < 40; i++) await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(session.api.messages).toHaveBeenCalledTimes(41);
  await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
  expect(session.api.messages).toHaveBeenCalledTimes(41);
  expect(screen.getByRole("button", { name: /Refresh pending response/ })).toBeTruthy();
});

it("lets users return from an empty page of conversation history", async () => {
  const conversations = Array.from({ length: 20 }, (_, i) => ({ id: String(i), title: "Conversation " + i, updated_at: receipt.created_at }));
  vi.mocked(session.api.conversations).mockResolvedValueOnce(conversations).mockResolvedValueOnce([]).mockResolvedValueOnce(conversations);
  show(<Assistant />);
  await userEvent.click(await screen.findByRole("button", { name: "Next" }));
  await screen.findByText("No conversations on this page.");
  await userEvent.click(screen.getByRole("button", { name: "Previous" }));
  await screen.findByRole("link", { name: "Conversation 0" });
  expect(session.api.conversations).toHaveBeenLastCalledWith({ limit: 20, offset: 0 }, expect.any(AbortSignal));
});
